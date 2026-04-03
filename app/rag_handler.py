from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from app.config import settings
from app.models import Task
from app.storage import read_json, write_json


class RagHandler:
    def __init__(self) -> None:
        self.memory_path = settings.memory_file
        self.default_payload = {
            "task_profiles": {},
            "efficiency_tips": {
                "撰写": "先列框架，再补充细节，最后统一润色。",
                "回复": "集中处理同类沟通，先给出简短确认，再补充细节。",
                "整理": "先筛核心资料，再分类归档，避免一开始陷入细节。",
                "对接": "提前列确认点，沟通后立即沉淀结论。",
            },
            "completion_log": [],
        }

    def load_memory(self) -> dict:
        return read_json(self.memory_path, self.default_payload)

    def save_memory(self, payload: dict) -> None:
        write_json(self.memory_path, payload)

    def estimate_minutes(self, title: str, fallback: int) -> int:
        memory = self.load_memory()
        profile = memory["task_profiles"].get(title)
        if profile and profile.get("average_minutes"):
            return int(profile["average_minutes"])
        for keyword in memory["efficiency_tips"].keys():
            if keyword in title:
                if keyword == "撰写":
                    return max(fallback, 120)
                if keyword == "回复":
                    return min(fallback, 30)
                if keyword == "整理":
                    return max(fallback, 60)
        return fallback

    def pick_efficiency_tip(self, title: str) -> str:
        memory = self.load_memory()
        for keyword, tip in memory["efficiency_tips"].items():
            if keyword in title:
                return tip
        return "优先完成关键产出，再处理收尾工作。"

    def update_from_tasks(self, tasks: List[Task]) -> None:
        memory = self.load_memory()
        durations: Dict[str, List[int]] = defaultdict(list)
        for task in tasks:
            if task.status != "completed":
                continue
            minutes = task.actual_minutes if task.actual_minutes is not None else task.estimated_minutes
            durations[task.title].append(minutes)
            memory["completion_log"].append(
                {
                    "task_id": task.id,
                    "title": task.title,
                    "date": task.due_date.isoformat(),
                    "minutes": minutes,
                }
            )
        for title, values in durations.items():
            memory["task_profiles"][title] = {
                "average_minutes": round(sum(values) / len(values)),
                "sample_size": len(values),
            }
        self.save_memory(memory)

    def remember_manual_completion(self, task: Task) -> None:
        memory = self.load_memory()
        memory["completion_log"].append(
            {
                "task_id": task.id,
                "title": task.title,
                "date": task.due_date.isoformat(),
                "minutes": task.actual_minutes or task.estimated_minutes,
                "source": "supplement",
            }
        )
        self.save_memory(memory)
