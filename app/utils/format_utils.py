from __future__ import annotations

from datetime import date
from typing import List

from app.models import PlanItem, Task


PRIORITY_LABELS = {
    1: "1级（紧急且重要）",
    2: "2级（紧急但次要）",
    3: "3级（不紧急但重要）",
    4: "4级（不紧急且次要）",
}


def format_plan(items: List[PlanItem], current_time: str) -> str:
    lines = [f"今日任务执行规划（当前时间：{current_time}）"]
    if not items:
        lines.append("暂无待处理任务。")
        return "\n".join(lines)
    for index, item in enumerate(items, start=1):
        carry = "【跨日累计】" if item.carry_over else ""
        lines.append(
            f"{index}. {item.start_time}-{item.end_time} {item.title} {carry}\n"
            f"   - 优先级：{PRIORITY_LABELS[item.priority]}\n"
            f"   - 预估耗时：{item.estimated_minutes} 分钟\n"
            f"   - 高效建议：{item.efficiency_tip}"
        )
    return "\n".join(lines)


def format_daily_summary(target_date: date, tasks: List[Task]) -> str:
    completed = [task for task in tasks if task.status == "completed"]
    pending = [task for task in tasks if task.status == "pending"]
    completion_rate = round((len(completed) / len(tasks) * 100), 1) if tasks else 0
    lines = [f"今日完成情况总结（日期：{target_date.isoformat()}）"]
    lines.append(f"- 计划任务：{len(tasks)} 项")
    lines.append(f"- 已完成：{len(completed)} 项")
    lines.append(f"- 未完成：{len(pending)} 项")
    lines.append(f"- 完成率：{completion_rate}%")
    if completed:
        lines.append("- 已完成任务：")
        for task in completed:
            actual = task.actual_minutes if task.actual_minutes is not None else task.estimated_minutes
            lines.append(f"  - {task.title}（{actual} 分钟）")
    if pending:
        lines.append("- 未完成任务：")
        for task in pending:
            lines.append(f"  - {task.title}（预计 {task.estimated_minutes} 分钟）")
    return "\n".join(lines)


def format_weekly_summary(start_date: date, end_date: date, tasks: List[Task]) -> str:
    completed = [task for task in tasks if task.status == "completed"]
    pending = [task for task in tasks if task.status == "pending"]
    lines = [f"本周工作总结（{start_date.isoformat()} 至 {end_date.isoformat()}）"]
    lines.append(f"- 总任务量：{len(tasks)}")
    lines.append(f"- 已完成：{len(completed)}")
    lines.append(f"- 未完成：{len(pending)}")
    if completed:
        lines.append("- 效率亮点：")
        for task in completed[:3]:
            lines.append(f"  - {task.title}")
    if pending:
        lines.append("- 改进方向：")
        for task in pending[:3]:
            lines.append(f"  - 尽快推进 {task.title}")
    return "\n".join(lines)
