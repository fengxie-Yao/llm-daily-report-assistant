from __future__ import annotations

from datetime import timedelta
from typing import List

from fastapi import FastAPI, HTTPException

from app.config import settings
from app.llm_handler import LLMHandler
from app.models import ApiResponse, SummaryRequest, SupplementRequest, Task, TaskInputRequest
from app.rag_handler import RagHandler
from app.storage import read_json, write_json
from app.utils.format_utils import format_daily_summary, format_plan, format_weekly_summary
from app.utils.time_utils import format_hhmm, now_local

app = FastAPI(title=settings.app_name)
rag_handler = RagHandler()
llm_handler = LLMHandler(rag_handler)


def load_tasks() -> List[Task]:
    payload = read_json(settings.tasks_file, [])
    return [Task.model_validate(item) for item in payload]


def save_tasks(tasks: List[Task]) -> None:
    write_json(settings.tasks_file, [task.model_dump(mode="json") for task in tasks])


@app.get("/health", response_model=ApiResponse)
def health() -> ApiResponse:
    return ApiResponse(message="ok", data={"timezone": settings.timezone, "now": now_local().isoformat()})


@app.post("/task/input", response_model=ApiResponse)
def task_input(request: TaskInputRequest) -> ApiResponse:
    operation, drafts = llm_handler.parse_input(request.text)
    tasks = load_tasks()

    if operation == "delete":
        title = drafts[0].title
        remaining = [task for task in tasks if title not in task.title]
        save_tasks(remaining)
        return ApiResponse(message=f"已删除与“{title}”匹配的任务。", data={"deleted_title": title})

    if operation == "modify":
        title = drafts[0].title
        for task in tasks:
            if title in task.title:
                task.priority = 1
                task.updated_at = now_local()
        save_tasks(tasks)
        return ApiResponse(message=f"已将与“{title}”匹配的任务优先级调整为紧急。", data={"updated_title": title})

    created_tasks = llm_handler.drafts_to_tasks(drafts, request.text)
    tasks.extend(created_tasks)
    save_tasks(tasks)
    plan = llm_handler.build_plan(tasks)
    return ApiResponse(
        message="任务已录入并完成规划。",
        data={
            "created_count": len(created_tasks),
            "plan": format_plan(plan, format_hhmm(now_local())),
            "tasks": [task.model_dump(mode="json") for task in created_tasks],
        },
    )


@app.post("/task/complete/supplement", response_model=ApiResponse)
def task_complete_supplement(request: SupplementRequest) -> ApiResponse:
    _, drafts = llm_handler.parse_input(request.text)
    if not drafts:
        raise HTTPException(status_code=400, detail="无法识别补录内容。")

    draft = drafts[0]
    tasks = load_tasks()
    matched = None
    for task in tasks:
        if draft.title in task.title and task.due_date == draft.target_date:
            task.status = "completed"
            task.actual_minutes = task.actual_minutes or task.estimated_minutes
            task.updated_at = now_local()
            matched = task
            break

    if matched is None:
        raise HTTPException(status_code=404, detail="未找到可补录的任务，请补充更明确的任务标题或日期。")

    save_tasks(tasks)
    rag_handler.remember_manual_completion(matched)
    return ApiResponse(
        message=f"补录成功：{matched.due_date.isoformat()} 的“{matched.title}”已设置为完结。",
        data={"task": matched.model_dump(mode="json")},
    )


@app.post("/task/summary/daily", response_model=ApiResponse)
def daily_summary(request: SummaryRequest) -> ApiResponse:
    target_date = request.date or now_local().date()
    tasks = [task for task in load_tasks() if task.due_date == target_date]
    rag_handler.update_from_tasks([task for task in tasks if task.status == "completed"])
    return ApiResponse(
        message="已生成每日报告。",
        data={"summary": format_daily_summary(target_date, tasks), "task_count": len(tasks)},
    )


@app.post("/task/summary/weekly", response_model=ApiResponse)
def weekly_summary(request: SummaryRequest) -> ApiResponse:
    anchor = request.date or now_local().date()
    start_date = anchor - timedelta(days=anchor.weekday())
    end_date = start_date + timedelta(days=6)
    tasks = [task for task in load_tasks() if start_date <= task.due_date <= end_date]
    return ApiResponse(
        message="已生成每周总结。",
        data={
            "summary": format_weekly_summary(start_date, end_date, tasks),
            "task_count": len(tasks),
        },
    )
