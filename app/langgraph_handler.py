from __future__ import annotations

import json
import re
import uuid
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple, TypedDict

from app.config import settings
from app.models import ParsedTaskDraft, PlanItem, Task
from app.utils.format_utils import format_daily_summary, format_plan, format_weekly_summary
from app.utils.time_utils import fit_minutes_in_workday, format_hhmm, now_local
from app.vector_rag_handler import VectorRagHandler

try:
    from langgraph.graph import END, StateGraph
except ImportError:  # pragma: no cover
    END = "__end__"
    StateGraph = None

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


KW_SUPPLEMENT = "\u8865\u5f55"
KW_DELETE = "\u5220\u9664"
KW_MODIFY = "\u4fee\u6539"
KW_CHANGE_TO = "\u6539\u4e3a"
KW_TODAY_WORK = "\u4eca\u5929\u7684\u5de5\u4f5c"
KW_CURRENT_TIME = "\u73b0\u5728\u65f6\u95f4"
KW_LARGE = "\u5927\u89c4\u6a21"
KW_LARGE_ALT = "\u5927\u578b"
KW_YESTERDAY = "\u6628\u5929"
KW_DAY_BEFORE = "\u524d\u5929"
KW_COMPLETED = "\u5df2\u5b8c\u7ed3"
KW_SET_COMPLETED = "\u8bbe\u7f6e\u4e3a\u5b8c\u7ed3"
KW_URGENT = "\u7d27\u6025"
KW_NORMAL = "\u4e00\u822c"
KW_COMMON = "\u666e\u901a"
KW_NOT_URGENT = "\u4e0d\u7d27\u6025"
KW_MINOR = "\u6b21\u8981"
KW_FRAME = "\u6846\u67b6\u642d\u5efa"
KW_CONTENT = "\u6838\u5fc3\u5185\u5bb9\u8865\u5145"
KW_REVIEW = "\u4fee\u6539\u4e0e\u6821\u5bf9"


class TaskGraphState(TypedDict, total=False):
    raw_text: str
    operation: str
    drafts: List[ParsedTaskDraft]
    memory: Dict
    related_items: List[Dict]
    retrieval_context: str


class SummaryGraphState(TypedDict, total=False):
    summary_type: str
    target_date: str
    start_date: str
    end_date: str
    tasks: List[Task]
    summary: str
    task_count: int


class PlanGraphState(TypedDict, total=False):
    operation: str
    tasks: List[Task]
    new_tasks: List[Task]
    ordered_tasks: List[Task]
    plan_items: List[PlanItem]
    branch: str
    branch_notes: List[str]


class LLMHandler:
    def __init__(self, rag_handler: VectorRagHandler) -> None:
        self.rag_handler = rag_handler
        self.task_graph = self._compile_task_graph()
        self.summary_graph = self._compile_summary_graph()
        self.plan_graph = self._compile_plan_graph()

    def parse_input(self, text: str) -> Tuple[str, List[ParsedTaskDraft]]:
        initial_state = TaskGraphState(raw_text=text.strip())
        if self.task_graph is None:
            state = self._load_memory(initial_state)
            state = self._retrieve_context(state)
            state = self._classify_input(state)
            state = self._extract_drafts(state)
            state = self._enrich_drafts(state)
        else:
            state = self.task_graph.invoke(initial_state)
        return state.get("operation", "unknown"), state.get("drafts", [])

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

    def build_plan(
        self,
        tasks: List[Task],
        operation: str = "add",
        new_tasks: Optional[List[Task]] = None,
    ) -> Tuple[List[PlanItem], Dict]:
        initial_state = PlanGraphState(
            operation=operation,
            tasks=tasks,
            new_tasks=new_tasks or [],
            branch_notes=[],
        )
        if self.plan_graph is None:
            state = self._prepare_plan(initial_state)
            state = self._apply_branch_logic(state)
            state = self._schedule_plan(state)
        else:
            state = self.plan_graph.invoke(initial_state)
        return state.get("plan_items", []), {
            "branch": state.get("branch", "default"),
            "notes": state.get("branch_notes", []),
        }

    def format_plan(self, items: List[PlanItem], current_time: str) -> str:
        return format_plan(items, current_time)

    def generate_daily_summary(self, tasks: List[Task], target_date: date) -> Dict:
        filtered = [task for task in tasks if task.due_date == target_date]
        initial = SummaryGraphState(summary_type="daily", target_date=target_date.isoformat(), tasks=filtered)
        state = self.summary_graph.invoke(initial) if self.summary_graph is not None else self._generate_summary(initial)
        return {"summary": state["summary"], "task_count": state["task_count"]}

    def generate_weekly_summary(self, tasks: List[Task], anchor: date) -> Dict:
        start_date = anchor - timedelta(days=anchor.weekday())
        end_date = start_date + timedelta(days=6)
        filtered = [task for task in tasks if start_date <= task.due_date <= end_date]
        initial = SummaryGraphState(
            summary_type="weekly",
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            tasks=filtered,
        )
        state = self.summary_graph.invoke(initial) if self.summary_graph is not None else self._generate_summary(initial)
        return {"summary": state["summary"], "task_count": state["task_count"]}

    def _compile_task_graph(self):
        if StateGraph is None:
            return None
        graph = StateGraph(TaskGraphState)
        graph.add_node("load_memory", self._load_memory)
        graph.add_node("retrieve_context", self._retrieve_context)
        graph.add_node("classify_input", self._classify_input)
        graph.add_node("extract_drafts", self._extract_drafts)
        graph.add_node("enrich_drafts", self._enrich_drafts)
        graph.add_edge("load_memory", "retrieve_context")
        graph.add_edge("retrieve_context", "classify_input")
        graph.add_edge("classify_input", "extract_drafts")
        graph.add_edge("extract_drafts", "enrich_drafts")
        graph.add_edge("enrich_drafts", END)
        graph.set_entry_point("load_memory")
        return graph.compile()

    def _compile_summary_graph(self):
        if StateGraph is None:
            return None
        graph = StateGraph(SummaryGraphState)
        graph.add_node("generate_summary", self._generate_summary)
        graph.add_edge("generate_summary", END)
        graph.set_entry_point("generate_summary")
        return graph.compile()

    def _compile_plan_graph(self):
        if StateGraph is None:
            return None
        graph = StateGraph(PlanGraphState)
        graph.add_node("prepare_plan", self._prepare_plan)
        graph.add_node("apply_branch_logic", self._apply_branch_logic)
        graph.add_node("schedule_plan", self._schedule_plan)
        graph.add_edge("prepare_plan", "apply_branch_logic")
        graph.add_edge("apply_branch_logic", "schedule_plan")
        graph.add_edge("schedule_plan", END)
        graph.set_entry_point("prepare_plan")
        return graph.compile()

    def _load_memory(self, state: TaskGraphState) -> TaskGraphState:
        state["memory"] = self.rag_handler.load_memory()
        return state

    def _retrieve_context(self, state: TaskGraphState) -> TaskGraphState:
        related_items = self.rag_handler.retrieve_related_items(state["raw_text"], top_k=3)
        state["related_items"] = related_items
        state["retrieval_context"] = self._format_related_context(related_items)
        return state

    def _classify_input(self, state: TaskGraphState) -> TaskGraphState:
        text = state["raw_text"]
        retrieval_context = state.get("retrieval_context", "")
        operation = self._llm_classify(text, retrieval_context) or self._rule_classify(text)
        state["operation"] = operation
        return state

    def _extract_drafts(self, state: TaskGraphState) -> TaskGraphState:
        text = state["raw_text"]
        operation = state.get("operation", "add")
        retrieval_context = state.get("retrieval_context", "")
        drafts = self._llm_extract_drafts(text, operation, retrieval_context)
        if drafts is None:
            if operation == "supplement":
                drafts = self._parse_supplement(text)
            elif operation in ("delete", "modify"):
                drafts = self._parse_single_action(text, operation)
            else:
                drafts = self._parse_tasks(text)
        state["drafts"] = drafts
        return state

    def _enrich_drafts(self, state: TaskGraphState) -> TaskGraphState:
        enriched: List[ParsedTaskDraft] = []
        for draft in state.get("drafts", []):
            estimate = draft.estimated_minutes or self._estimate_minutes(draft.title, draft.priority, draft.is_large)
            is_large = draft.is_large or estimate >= settings.large_task_threshold_minutes
            enriched.append(
                ParsedTaskDraft(
                    title=draft.title,
                    priority=draft.priority,
                    estimated_minutes=estimate,
                    is_large=is_large,
                    operation=draft.operation,
                    target_date=draft.target_date or now_local().date(),
                )
            )
        state["drafts"] = enriched
        return state

    def _generate_summary(self, state: SummaryGraphState) -> SummaryGraphState:
        tasks = state.get("tasks", [])
        if state.get("summary_type") == "daily":
            target_date = date.fromisoformat(state["target_date"])
            self.rag_handler.update_from_tasks([task for task in tasks if task.status == "completed"])
            base_summary = format_daily_summary(target_date, tasks)
            llm_summary = self._llm_polish_summary(base_summary, "daily")
            state["summary"] = llm_summary or base_summary
            state["task_count"] = len(tasks)
            return state

        start_date = date.fromisoformat(state["start_date"])
        end_date = date.fromisoformat(state["end_date"])
        base_summary = format_weekly_summary(start_date, end_date, tasks)
        llm_summary = self._llm_polish_summary(base_summary, "weekly")
        state["summary"] = llm_summary or base_summary
        state["task_count"] = len(tasks)
        return state

    def _prepare_plan(self, state: PlanGraphState) -> PlanGraphState:
        current = now_local().date()
        root_ids = {task.id for task in state.get("tasks", []) if task.is_large}
        effective_tasks: List[Task] = []
        for task in sorted(state.get("tasks", []), key=lambda item: (item.due_date, item.priority, item.created_at)):
            if task.status != "pending":
                continue
            if task.id in root_ids:
                continue
            if task.parent_task_id and task.due_date > current:
                continue
            effective_tasks.append(task)
        state["ordered_tasks"] = effective_tasks
        return state

    def _apply_branch_logic(self, state: PlanGraphState) -> PlanGraphState:
        ordered_tasks = list(state.get("ordered_tasks", []))
        branch_notes = list(state.get("branch_notes", []))
        operation = state.get("operation", "add")
        new_tasks = state.get("new_tasks", [])
        today = now_local().date()

        has_urgent_insert = operation == "add" and any(task.priority == 1 for task in new_tasks)
        has_carry_over = any(task.due_date < today for task in ordered_tasks)
        has_supplement_adjust = operation == "supplement"

        if has_urgent_insert:
            branch_notes.append("Detected newly added urgent tasks; inserted them at the front of today's plan.")
            urgent_ids = {task.id for task in new_tasks if task.priority == 1}
            urgent_tasks = [task for task in ordered_tasks if task.id in urgent_ids]
            remaining_tasks = [task for task in ordered_tasks if task.id not in urgent_ids]
            ordered_tasks = sorted(urgent_tasks, key=lambda item: (item.priority, item.created_at)) + remaining_tasks
            state["branch"] = "urgent_insert"

        if has_carry_over:
            branch_notes.append("Detected unfinished carry-over tasks; moved them to the front of today's schedule.")
            carry_over_tasks = [task for task in ordered_tasks if task.due_date < today]
            current_tasks = [task for task in ordered_tasks if task.due_date >= today]
            ordered_tasks = sorted(carry_over_tasks, key=lambda item: (item.priority, item.due_date)) + current_tasks
            if state.get("branch") is None:
                state["branch"] = "carry_over"

        if has_supplement_adjust:
            branch_notes.append("Supplement completion detected; removed completed items and re-ranked pending work.")
            ordered_tasks = [task for task in ordered_tasks if task.status == "pending"]
            if state.get("branch") is None:
                state["branch"] = "supplement_adjust"

        if not state.get("branch"):
            state["branch"] = "default"
            branch_notes.append("Generated plan with default priority and workday windows.")

        state["ordered_tasks"] = ordered_tasks
        state["branch_notes"] = branch_notes
        return state

    def _schedule_plan(self, state: PlanGraphState) -> PlanGraphState:
        current = now_local()
        plan_items: List[PlanItem] = []
        for task in state.get("ordered_tasks", []):
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
        state["plan_items"] = plan_items
        return state

    def _llm_classify(self, text: str, retrieval_context: str = "") -> Optional[str]:
        prompt = (
            "You are a task-intent classifier. Return exactly one word from: add, modify, delete, supplement. "
            "Do not explain.\n"
            f"Related memory:\n{retrieval_context or 'none'}\n"
            f"User input: {text}"
        )
        answer = self._call_llm(prompt)
        if answer in {"add", "modify", "delete", "supplement"}:
            return answer
        return None

    def _llm_extract_drafts(self, text: str, operation: str, retrieval_context: str = "") -> Optional[List[ParsedTaskDraft]]:
        prompt = (
            "You are a task extraction engine. Convert the user input into a JSON array. "
            "Each item must include title, priority, estimated_minutes, is_large. "
            "Priority must be an integer 1-4. "
            "If related memory contains similar tasks, use it to infer duration and scale. "
            "Return JSON only.\n"
            f"Operation: {operation}\n"
            f"Related memory:\n{retrieval_context or 'none'}\n"
            f"User input: {text}"
        )
        raw = self._call_llm(prompt)
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except Exception:
            return None
        if not isinstance(payload, list):
            return None

        drafts: List[ParsedTaskDraft] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            if not title:
                continue
            drafts.append(
                ParsedTaskDraft(
                    title=title,
                    priority=max(1, min(4, int(item.get("priority", 3)))),
                    estimated_minutes=max(5, int(item.get("estimated_minutes", 60))),
                    is_large=bool(item.get("is_large", False)),
                    operation=operation,
                    target_date=now_local().date(),
                )
            )
        return drafts or None

    def _llm_polish_summary(self, summary: str, summary_type: str) -> Optional[str]:
        prompt = (
            "Polish the following work summary without changing facts. Keep it concise and professional.\n"
            f"Summary type: {summary_type}\n"
            f"Original content:\n{summary}"
        )
        return self._call_llm(prompt)

    def _call_llm(self, prompt: str) -> Optional[str]:
        if not settings.openai_api_key or OpenAI is None:
            return None
        try:
            client = OpenAI(api_key=settings.openai_api_key)
            response = client.responses.create(model=settings.openai_model, input=prompt)
            output_text = getattr(response, "output_text", "")
            return output_text.strip() or None
        except Exception:
            return None

    def _rule_classify(self, text: str) -> str:
        cleaned = text.strip()
        if KW_SUPPLEMENT in cleaned:
            return "supplement"
        if KW_DELETE in cleaned:
            return "delete"
        if KW_CHANGE_TO in cleaned or KW_MODIFY in cleaned:
            return "modify"
        return "add"

    def _parse_tasks(self, text: str) -> List[ParsedTaskDraft]:
        body = re.sub(KW_TODAY_WORK + r"[:\uff1a]?", "", text)
        body = re.sub(KW_CURRENT_TIME + r"\d{1,2}:\d{2}", "", body)
        parts = [item.strip(" ;\uff1b.\n\t") for item in re.split(r"\d+\.\s*|\uff1b|;", body) if item.strip(" ;\uff1b.\n\t")]
        drafts: List[ParsedTaskDraft] = []
        for part in parts:
            priority = self._extract_priority(part)
            is_large = KW_LARGE in part or KW_LARGE_ALT in part
            title = re.sub(r"[\uff08(].*?[)\uff09]", "", part).strip()
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
        normalized = text.replace(KW_DELETE, "").replace(KW_MODIFY, "").replace("\u5c06", "")
        matches = re.findall(r"[\u201c\"']([^\u201d\"']+)[\u201d\"']", normalized)
        title = matches[0].strip() if matches else normalized.replace("\u8fd9\u4e2a\u4efb\u52a1", "").replace("\u6539\u4e3a\u7d27\u6025", "").strip()
        return [ParsedTaskDraft(title=title, operation=action, target_date=now_local().date())]

    def _parse_supplement(self, text: str) -> List[ParsedTaskDraft]:
        target_date = now_local().date()
        if KW_YESTERDAY in text:
            target_date -= timedelta(days=1)
        elif KW_DAY_BEFORE in text:
            target_date -= timedelta(days=2)
        explicit = re.search(r"(\d{1,2})\u6708(\d{1,2})\u65e5", text)
        if explicit:
            today = now_local().date()
            target_date = date(today.year, int(explicit.group(1)), int(explicit.group(2)))
        quoted = re.findall(r"[\u201c\"']([^\u201d\"']+)[\u201d\"']", text)
        title = quoted[0] if quoted else text.replace(KW_SUPPLEMENT, "").replace(KW_COMPLETED, "").replace(KW_SET_COMPLETED, "").strip("\uff1a: ")
        return [ParsedTaskDraft(title=title, operation="supplement", target_date=target_date)]

    def _extract_priority(self, text: str) -> int:
        if KW_URGENT in text:
            return 1
        if KW_NORMAL in text or KW_COMMON in text:
            return 2
        if KW_NOT_URGENT in text:
            return 3
        if KW_MINOR in text:
            return 4
        return 3

    def _estimate_minutes(self, title: str, priority: int, is_large: bool) -> int:
        base = {1: 90, 2: 45, 3: 60, 4: 30}.get(priority, 60)
        if is_large:
            base = max(base, settings.large_task_threshold_minutes)
        return self.rag_handler.estimate_minutes(title, base)

    def _split_large_task(self, task: Task) -> List[Task]:
        chunk = max(60, task.estimated_minutes // 3)
        phases = [KW_FRAME, KW_CONTENT, KW_REVIEW]
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

    def _format_related_context(self, related_items: List[Dict]) -> str:
        if not related_items:
            return ""
        lines: List[str] = []
        for index, item in enumerate(related_items, start=1):
            item_type = item.get("type", "unknown")
            title = item.get("title", "")
            score = item.get("score", 0)
            if item_type == "task_profile":
                lines.append(
                    f"{index}. task_profile | title={title} | score={score} | average_minutes={item.get('average_minutes')} | sample_size={item.get('sample_size', 0)}"
                )
            else:
                lines.append(
                    f"{index}. completion_log | title={title} | score={score} | minutes={item.get('minutes')} | date={item.get('date')}"
                )
        return "\n".join(lines)
