"""Paths, creator list and the one secret we borrow at runtime.

The Telegram token lives in %LOCALAPPDATA%\\hermes\\.env and stays there: we parse the file
every time we need it and never write the value anywhere inside this repo.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# tests point this somewhere temporary
DATA = Path(os.environ.get("AGENTCHIRP_DATA") or ROOT / "data")
CREATORS_FILE = Path(os.environ.get("AGENTCHIRP_CREATORS") or ROOT / "creators.yaml")

CATEGORIES = ("biggest", "academics", "new")

TELEGRAM_CHAT_ID = "8843609758"
TELEGRAM_ENV_FILE = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / ".env"
TELEGRAM_TOKEN_KEY = "TELEGRAM_BOT_TOKEN"

X_BASE = "https://x.com"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
VOICE = "en-GB-RyanNeural"
WORDS_PER_MINUTE = 150
FETCH_DELAY_RANGE_S = (3.0, 8.0)   # polite pacing between profiles


def profile_dir() -> Path:
    return DATA / "browser-profile"


def raw_dir() -> Path:
    return DATA / "raw"


def brief_dir() -> Path:
    return DATA / "briefs"


def audio_dir() -> Path:
    return DATA / "audio"


def log_dir() -> Path:
    return DATA / "logs"


def state_dir() -> Path:
    return DATA / "state"


def raw_path(day: date) -> Path:
    return raw_dir() / f"x-{day.isoformat()}.json"


def brief_path(day: date) -> Path:
    return brief_dir() / f"brief-{day.isoformat()}.md"


def audio_path(day: date, suffix: str = "ogg") -> Path:
    return audio_dir() / f"chirp-{day.isoformat()}.{suffix}"


def log_path(day: date) -> Path:
    return log_dir() / f"{day.isoformat()}.log"


def done_marker(day: date) -> Path:
    return state_dir() / f"{day.isoformat()}.done"


def parse_day(value: str | None) -> date:
    """--date YYYY-MM-DD, or today."""
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


@dataclass(frozen=True)
class Creator:
    name: str
    handle: str
    category: str
    verified: bool = True

    @property
    def url(self) -> str:
        return f"{X_BASE}/{self.handle}"


def parse_creators(text: str) -> tuple[list[Creator], list[str]]:
    """-> (creators, skipped). An entry with no handle is skipped, not guessed at."""
    import yaml

    doc = yaml.safe_load(text) or {}
    if not isinstance(doc, dict):
        raise ValueError("creators.yaml must be a mapping of category -> list of creators")

    creators: list[Creator] = []
    skipped: list[str] = []
    for category in CATEGORIES:
        for entry in doc.get(category) or []:
            if not isinstance(entry, dict):
                skipped.append(f"{category}: {entry!r} is not a mapping")
                continue
            name = str(entry.get("name") or "").strip()
            handle = str(entry.get("handle") or "").strip().lstrip("@")
            if not name:
                skipped.append(f"{category}: entry with no name ({entry!r})")
                continue
            if not handle:
                skipped.append(f"{category}: {name} has no handle")
                continue
            creators.append(Creator(name=name, handle=handle, category=category,
                                    verified=bool(entry.get("verified", True))))

    unknown = [k for k in doc if k not in CATEGORIES]
    skipped += [f"unknown category {k!r} ignored" for k in unknown]
    return creators, skipped


def load_creators(path: Path | None = None) -> tuple[list[Creator], list[str]]:
    path = path or CREATORS_FILE
    return parse_creators(path.read_text(encoding="utf-8"))


def parse_env(text: str) -> dict[str, str]:
    """Minimal .env reader: KEY=value, optional `export`, # comments, optional quotes."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip().lstrip("\ufeff")
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^export\s+", "", line)
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key] = value
    return out


def telegram_token(env_file: Path | None = None) -> str:
    """Read the bot token straight from Hermes' .env; env var wins only if the file has none."""
    env_file = env_file or TELEGRAM_ENV_FILE
    try:
        value = parse_env(env_file.read_text(encoding="utf-8", errors="replace")).get(
            TELEGRAM_TOKEN_KEY, "")
    except OSError:
        value = ""
    value = value or os.environ.get(TELEGRAM_TOKEN_KEY, "")
    if not value:
        raise RuntimeError(f"{TELEGRAM_TOKEN_KEY} not found in {env_file}")
    return value


def ensure_dirs() -> None:
    for d in (raw_dir(), brief_dir(), audio_dir(), log_dir(), state_dir()):
        d.mkdir(parents=True, exist_ok=True)
