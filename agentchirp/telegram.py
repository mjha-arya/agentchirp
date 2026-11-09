"""Telegram Bot API: a voice note for the brief, plain text for problems."""
from __future__ import annotations

from pathlib import Path

import requests

from . import config

TIMEOUT_S = 60


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{config.telegram_token()}/{method}"


def _check(response: requests.Response) -> dict:
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram {response.status_code}: {payload.get('description')}")
    return payload["result"]


def send_text(text: str, chat_id: str | None = None) -> dict:
    return _check(requests.post(_api("sendMessage"),
                                data={"chat_id": chat_id or config.TELEGRAM_CHAT_ID,
                                      "text": text,
                                      "disable_web_page_preview": True},
                                timeout=TIMEOUT_S))


def send_voice(ogg: Path, caption: str, duration_s: int | None = None,
               chat_id: str | None = None) -> dict:
    data = {"chat_id": chat_id or config.TELEGRAM_CHAT_ID, "caption": caption}
    if duration_s:
        data["duration"] = int(duration_s)
    with ogg.open("rb") as fh:
        return _check(requests.post(_api("sendVoice"), data=data,
                                    files={"voice": (ogg.name, fh, "audio/ogg")},
                                    timeout=TIMEOUT_S))


def notify_login_expired() -> None:
    """Best-effort heads-up; a dead network must not mask the original fetch failure."""
    try:
        send_text("AgentChirp: X login expired — run `python -m agentchirp login`")
    except Exception as exc:  # noqa: BLE001 - reported by the caller, never fatal
        print(f"warning: could not send Telegram alert: {exc}", flush=True)
