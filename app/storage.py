from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any) -> Any:
    # 读取json
    if not path.exists():
        write_json(path, default)
        return default
    with path.open("r", encoding="utf-8") as file:
        try:
            return json.load(file)
        except json.JSONDecodeError:
            write_json(path, default)
            return default


def write_json(path: Path, payload: Any) -> None:
    # 写入
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
