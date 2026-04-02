from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from typing import List, Tuple

from app.config import settings
from app.models import ParsedTaskDraft, PlanItem, Task
from app.rag_handler import RagHandler
from app.utils.time_utils import fit_minutes_in_workday, format_hhmm, now_local


class LLMHandler:
    def __init__(self, rag_handler: RagHandler) -> None:
        self.rag_handler = rag_handler

    def parse_input(self, text: str) -> Tuple[str, List[ParsedTaskDraft]]:
        cleaned = text.strip()
        if "补录" in cleaned:
            return "supplement", self._parse_supplement(cleaned)
        if "删除" in cleaned:
            return "delete", self._parse_single_action(cleaned, "delete")
        if "改为" in cleaned or "修改" in cleaned:
            return "modify", self._parse_single_action(cleaned, "modify")
        return "add", self._parse_tasks(cleaned)

    def _parse_tasks(self, text: str) -> List[ParsedTaskDraft]:
        body = re.sub(r"今天的工作[:：]?", "", text)
        body = re.sub(r"现在时间\d{1,2}:\d{2}", "", body)
        parts = [item.strip(" ;；。\n\t") for item in re.split(r"\d+\.\s*|；|;", body) if item.strip(" ;；。\n\t")]
        drafts: List[ParsedTaskDraft] = []
        for part in parts:
            priority = self._extract_priority(part)
            is_large = "大规模" in part or "大型" in part
            title = re.sub(r"[（(].*?[)）]", "", part).strip()
            estimate = self._estimate_minutes(title, priority, is_large)
            drafts.append(
                ParsedTaskDraft(
                    title=title,
                    priority=priority,
                    estimated_minutes=estimate,
                    is_large=is_large or estimate >= settings.large_task_threshold_minutes,
                    operation="add",
                    target_date=now_local().date(),
                )
            )
        return drafts

    def _parse_single_action(self, text: str, action: str) -> List[ParsedTaskDraft]:
        match = re.search(r"[“\"']?(.*?)[”\"']?", text.replace("删除", "").replace("修改", "").replace("将", ""))
        title = match.group(1).replace("这个任务", "").strip() if match else text.strip()
        return [ParsedTaskDraft(title=title, operation=action, target_date=now_local().date())]

    def _parse_supplement(self, text: str) -> List[ParsedTaskDraft]:
        target_date = now_local().date()
        if "昨天" in text:
            target_date -= timedelta(days=1)
        elif "前天" in text:
            target_date -= timedelta(days=2)
        explicit = re.search(r"(\d{1,2})月(\d{1,2})日", text)
        if explicit:
            today = now_local().date()
            target_date = date(today.year, int(explicit.group(1)), int(explicit.group(2)))
        quoted = re.findall(r"[“\"']([^”\"']+)[”\"']", text)
        title = quoted[0] if quoted else text.replace("补录", "").replace("已完结", "").replace("设置为完结", "").strip("：: ")
        return [ParsedTaskDraft(title=title, operation="supplement", target_date=target_date)]

    def _extract_priority(self, text: str) -> int:
        if "紧急" in text:
            return 1
        if "一般" in text or "普通" in text:
            return 2
        if "不紧急" in text:
            return 3
        if "次要" in text:
            return 4
        return 3

    def _estimate_minutes(self, title: str, priority: int, is_large: bool) -> int:
        base = {1: 90, 2: 45, 3: 60, 4: 30}.get(priority, 60)
        if is_large:
            base = max(base, settings.large_task_threshold_minutes)
        return self.rag_handler.estimate_minutes(title, base)

    def drafts_to_tasks(self, drafts: List[ParsedTaskDraft], source_text: str) -> List[Task]:
        created = now_local()
        tasks: List[Task] = []
        for draft in drafts:
            task = Task(
                id=str(uuid.uuid4()),
                title=draft.title,
                priority=draft.priority,
                estimated_minutes=draft.estimated_minutes,
                due_date=draft.target_date or created.date(),
                created_at=created,
                updated_at=created,
                source_text=source_text,
                is_large=draft.is_large,
            )
            tasks.append(task)
            if draft.is_large:
                tasks.extend(self._split_large_task(task))
        return tasks

    def _split_large_task(self, task: Task) -> List[Task]:
        chunk = max(60, task.estimated_minutes // 3)
        phases = ["框架搭建", "核心内容补充", "修改与校对"]
        subtasks: List[Task] = []
        created = now_local()
        for index, phase in enumerate(phases):
            subtasks.append(
                Task(
                    id=str(uuid.uuid4()),
                    title=f"{task.title} - {phase}",
                    priority=task.priority,
                    estimated_minutes=chunk,
                    due_date=task.due_date + timedelta(days=index),
                    created_at=created,
                    updated_at=created,
                    source_text=task.source_text,
                    is_large=False,
                    parent_task_id=task.id,
                )
            )
        return subtasks

    def build_plan(self, tasks: List[Task]) -> List[PlanItem]:
        current = now_local()
        plan_items: List[PlanItem] = []
        root_ids = {task.id for task in tasks if task.is_large}
        effective_tasks: List[Task] = []
        for task in sorted(tasks, key=lambda item: (item.due_date, item.priority, item.created_at)):
            if task.status != "pending":
                continue
            if task.id in root_ids:
                continue
            if task.parent_task_id:
                if task.due_date > current.date():
                    continue
                effective_tasks.append(task)
                continue
            effective_tasks.append(task)

        for task in effective_tasks:
            slot_start, slot_end = fit_minutes_in_workday(current, task.estimated_minutes)
            carry_over = slot_end.strftime("%H:%M") == settings.default_workday_end and task.estimated_minutes > int(
                (slot_end - slot_start).total_seconds() // 60
            )
            plan_items.append(
                PlanItem(
                    title=task.title,
                    priority=task.priority,
                    estimated_minutes=task.estimated_minutes,
                    start_time=format_hhmm(slot_start),
                    end_time=format_hhmm(slot_end),
                    efficiency_tip=self.rag_handler.pick_efficiency_tip(task.title),
                    carry_over=carry_over or task.due_date < current.date(),
                )
            )
            current = slot_end
        return plan_items
