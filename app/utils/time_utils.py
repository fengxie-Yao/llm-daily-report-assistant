from __future__ import annotations

from datetime import date, datetime, time, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from app.config import settings


def now_local() -> datetime:
    if ZoneInfo is None:
        return datetime.now()
    return datetime.now(ZoneInfo(settings.timezone))


def parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(hour=int(hour), minute=int(minute))


def merge_date_time(target_date: date, hhmm: str) -> datetime:
    if ZoneInfo is None:
        return datetime.combine(target_date, parse_hhmm(hhmm))
    return datetime.combine(target_date, parse_hhmm(hhmm), tzinfo=ZoneInfo(settings.timezone))


def add_minutes(moment: datetime, minutes: int) -> datetime:
    return moment + timedelta(minutes=minutes)


def format_hhmm(moment: datetime) -> str:
    return moment.strftime("%H:%M")


def next_work_slot_start(target_date: date, current: datetime) -> datetime:
    start = merge_date_time(target_date, settings.default_workday_start)
    lunch_start = merge_date_time(target_date, settings.lunch_start)
    lunch_end = merge_date_time(target_date, settings.lunch_end)
    if current < start:
        return start
    if lunch_start <= current < lunch_end:
        return lunch_end
    return current


def fit_minutes_in_workday(start_at: datetime, minutes: int):
    lunch_start = merge_date_time(start_at.date(), settings.lunch_start)
    lunch_end = merge_date_time(start_at.date(), settings.lunch_end)
    work_end = merge_date_time(start_at.date(), settings.default_workday_end)

    current = next_work_slot_start(start_at.date(), start_at)
    end_at = add_minutes(current, minutes)
    if current < lunch_start < end_at:
        end_at = add_minutes(end_at, int((lunch_end - lunch_start).total_seconds() // 60))
    if end_at > work_end:
        end_at = work_end
    return current, end_at
