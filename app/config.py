from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


class Settings:
    app_name: str = os.getenv("APP_NAME", "LLM Daily Report Assistant")
    app_env: str = os.getenv("APP_ENV", "development")
    fastapi_host: str = os.getenv("FASTAPI_HOST", "0.0.0.0")
    fastapi_port: int = int(os.getenv("FASTAPI_PORT", "8000"))
    fastapi_reload: bool = os.getenv("FASTAPI_RELOAD", "true").lower() == "true"
    # 时区
    timezone: str = os.getenv("TIMEZONE", "Asia/Shanghai")

    # 根目录
    base_dir: Path = Path(__file__).resolve().parent.parent
    # 数据目录
    data_dir: Path = Path(os.getenv("DATA_DIR", str(base_dir / "data"))).resolve()
    # 记忆文件路径
    memory_file: Path = data_dir / os.getenv("MEMORY_FILE", "memory.json")
    # 任务文件路径
    tasks_file: Path = data_dir / os.getenv("TASKS_FILE", "tasks.json")

    # 总结生成时间
    daily_summary_time: str = os.getenv("DAILY_SUMMARY_TIME", "18:00")
    # 每周总结
    weekly_summary_weekday: int = int(os.getenv("WEEKLY_SUMMARY_WEEKDAY", "5"))
    # 工作开始时间
    default_workday_start: str = os.getenv("DEFAULT_WORKDAY_START", "08:00")
    # 工作结束时间
    default_workday_end: str = os.getenv("DEFAULT_WORKDAY_END", "19:00")
    # 午休开始时间
    lunch_start: str = os.getenv("LUNCH_START", "12:00")
    # 午休结束时间
    lunch_end: str = os.getenv("LUNCH_END", "13:30")
    # 大任务阈值
    large_task_threshold_minutes: int = int(os.getenv("LARGE_TASK_THRESHOLD_MINUTES", "180"))
    # API key
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    # 模型选择
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
