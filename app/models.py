from __future__ import annotations

from datetime import date, datetime
from typing import Dict, Literal, Optional

from pydantic import BaseModel, Field


TaskStatus = Literal["pending", "completed", "cancelled"]
TaskOperation = Literal["add", "modify", "delete", "supplement", "summary", "unknown"]

# 任务实体
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

# 任务请求
class TaskInputRequest(BaseModel):
    text: str

# 补充信息
class SupplementRequest(BaseModel):
    text: str

# 每日小结
class SummaryRequest(BaseModel):
    date: Optional[date] = None

# 任务解析
class ParsedTaskDraft(BaseModel):
    title: str
    priority: int = 3
    estimated_minutes: int = 60
    is_large: bool = False
    operation: TaskOperation = "add"
    target_date: Optional[date] = None

# 计划
class PlanItem(BaseModel):
    title: str
    priority: int
    estimated_minutes: int
    start_time: str
    end_time: str
    efficiency_tip: str
    carry_over: bool = False

# 消息类型接口
class ApiResponse(BaseModel):
    message: str
    data: Dict = Field(default_factory=dict)
