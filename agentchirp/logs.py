"""One log line per stage, appended to data/logs/YYYY-MM-DD.log and echoed to the console."""
from __future__ import annotations

from datetime import date, datetime

from . import config


def log(day: date, stage: str, message: str, *, echo: bool = True) -> str:
    line = f"{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')} {stage:<6} {message}"
    path = config.log_path(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    if echo:
        print(line, flush=True)
    return line
