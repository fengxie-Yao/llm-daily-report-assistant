from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

from app.config import settings
from app.models import Task
from app.storage import read_json, write_json


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _tokenize(text: str) -> List[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []

    words = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", normalized)
    tokens: List[str] = list(words)

    compact = re.sub(r"\s+", "", normalized)
    tokens.extend(compact[i : i + 2] for i in range(max(0, len(compact) - 1)))
    return [token for token in tokens if token]


def _vectorize(text: str) -> Counter:
    return Counter(_tokenize(text))


def _cosine_similarity(left: Counter, right: Counter) -> float:
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


class VectorRagHandler:
    """A lightweight local vector-retrieval layer.

    It builds simple token-frequency vectors from task titles and memory text,
    then uses cosine similarity for retrieval.
    """

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
        payload = read_json(self.memory_path, self.default_payload)
        normalized, changed = self._normalize_memory_payload(payload)
        if changed:
            self.save_memory(normalized)
        return normalized

    def save_memory(self, payload: dict) -> None:
        write_json(self.memory_path, payload)

    def _normalize_memory_payload(self, payload: dict) -> Tuple[dict, bool]:
        changed = False
        normalized = dict(payload or {})

        if not isinstance(normalized.get("task_profiles"), dict):
            normalized["task_profiles"] = {}
            changed = True

        if not isinstance(normalized.get("completion_log"), list):
            normalized["completion_log"] = []
            changed = True

        tips = normalized.get("efficiency_tips")
        if not isinstance(tips, dict):
            normalized["efficiency_tips"] = dict(self.default_payload["efficiency_tips"])
            return normalized, True

        tip_keys = set(tips.keys())
        expected_keys = set(self.default_payload["efficiency_tips"].keys())
        if tip_keys != expected_keys:
            normalized["efficiency_tips"] = dict(self.default_payload["efficiency_tips"])
            changed = True

        return normalized, changed

    def estimate_minutes(self, title: str, fallback: int) -> int:
        memory = self.load_memory()
        profiles = memory.get("task_profiles", {})

        if title in profiles and profiles[title].get("average_minutes"):
            return int(profiles[title]["average_minutes"])

        query_vector = _vectorize(title)
        best_minutes = fallback
        best_score = 0.0

        for profile_title, profile in profiles.items():
            average = profile.get("average_minutes")
            if not average:
                continue
            score = _cosine_similarity(query_vector, _vectorize(profile_title))
            if score > best_score and score >= 0.18:
                best_score = score
                best_minutes = int(average)

        for record in memory.get("completion_log", []):
            record_title = str(record.get("title", "")).strip()
            minutes = record.get("minutes")
            if not record_title or minutes is None:
                continue
            score = _cosine_similarity(query_vector, _vectorize(record_title))
            if score > best_score and score >= 0.24:
                best_score = score
                best_minutes = int(minutes)

        return best_minutes

    def pick_efficiency_tip(self, title: str) -> str:
        memory = self.load_memory()
        tips = memory.get("efficiency_tips", {})
        query_vector = _vectorize(title)

        best_tip = "优先完成关键产出，再处理收尾工作。"
        best_score = 0.0

        for keyword, tip in tips.items():
            score = _cosine_similarity(query_vector, _vectorize(keyword))
            if keyword in title:
                score += 0.35
            if score > best_score:
                best_score = score
                best_tip = tip

        return best_tip

    def retrieve_related_items(self, title: str, top_k: int = 3) -> List[Dict]:
        memory = self.load_memory()
        query_vector = _vectorize(title)
        candidates: List[Tuple[float, Dict]] = []

        for profile_title, profile in memory.get("task_profiles", {}).items():
            score = _cosine_similarity(query_vector, _vectorize(profile_title))
            if score > 0:
                candidates.append(
                    (
                        score,
                        {
                            "type": "task_profile",
                            "title": profile_title,
                            "score": round(score, 4),
                            "average_minutes": profile.get("average_minutes"),
                            "sample_size": profile.get("sample_size", 0),
                        },
                    )
                )

        for record in memory.get("completion_log", []):
            record_title = str(record.get("title", "")).strip()
            score = _cosine_similarity(query_vector, _vectorize(record_title))
            if score > 0:
                candidates.append(
                    (
                        score,
                        {
                            "type": "completion_log",
                            "title": record_title,
                            "score": round(score, 4),
                            "minutes": record.get("minutes"),
                            "date": record.get("date"),
                        },
                    )
                )

        candidates.sort(key=lambda item: item[0], reverse=True)
        return [payload for _, payload in candidates[:top_k]]

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
