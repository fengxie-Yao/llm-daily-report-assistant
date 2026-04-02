from __future__ import annotations

from datetime import date, datetime
from typing import Dict, Literal, Optional

from pydantic import BaseModel, Field


TaskStatus = Literal["pending", "completed", "cancelled"]
TaskOperation = Literal["add", "modify", "delete", "supplement", "summary", "unknown"]


class Task(BaseModel):
    id: str
    title: str
    priority: int = Field(ge=1, le=4, default=3)
    estimated_minutes: int = Field(default=60, ge=5)
    actual_minutes: Optional[int] = Field(default=None, ge=0)
    status: TaskStatus = "pending"
    due_date: date
    created_at: datetime
    updated_at: datetime
    source_text: Optional[str] = None
    is_large: bool = False
    parent_task_id: Optional[str] = None
    notes: Optional[str] = None


class TaskInputRequest(BaseModel):
    text: str


class SupplementRequest(BaseModel):
    text: str


class SummaryRequest(BaseModel):
    date: Optional[date] = None


class ParsedTaskDraft(BaseModel):
    title: str
    priority: int = 3
    estimated_minutes: int = 60
    is_large: bool = False
    operation: TaskOperation = "add"
    target_date: Optional[date] = None


class PlanItem(BaseModel):
    title: str
    priority: int
    estimated_minutes: int
    start_time: str
    end_time: str
    efficiency_tip: str
    carry_over: bool = False


class ApiResponse(BaseModel):
    message: str
    data: Dict = Field(default_factory=dict)
