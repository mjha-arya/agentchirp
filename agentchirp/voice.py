"""Brief -> edge-tts mp3 -> ogg/opus -> Telegram voice note."""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

from . import config, telegram
from .brief import count_words, estimate_seconds, spoken_text

FFMPEG_TIMEOUT_S = 300


def synthesize(text: str, mp3: Path, voice: str | None = None) -> Path:
    """edge-tts to mp3. Raises if the brief has no words in it."""
    import edge_tts

    if not (text or "").strip():
        raise RuntimeError("nothing to speak — the brief is empty")
    mp3.parent.mkdir(parents=True, exist_ok=True)

    async def _run() -> None:
        await edge_tts.Communicate(text, voice or config.VOICE).save(str(mp3))

    asyncio.run(_run())
    if not mp3.exists() or mp3.stat().st_size == 0:
        raise RuntimeError("edge-tts produced no audio")
    return mp3


def to_opus(mp3: Path, ogg: Path) -> Path:
    """Telegram voice notes must be OGG/Opus, mono, 48 kHz."""
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg is not on PATH")
    ogg.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run([exe, "-y", "-hide_banner", "-loglevel", "error", "-i", str(mp3),
                           "-vn", "-c:a", "libopus", "-b:a", "48k", "-ar", "48000", "-ac", "1",
                           str(ogg)],
                          capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_S)
    if proc.returncode != 0 or not ogg.exists():
        raise RuntimeError(f"ffmpeg failed (exit {proc.returncode}): {proc.stderr.strip()[:300]}")
    return ogg


def probe_duration(path: Path) -> float | None:
    exe = shutil.which("ffprobe")
    if not exe:
        return None
    proc = subprocess.run([exe, "-v", "error", "-show_entries", "format=duration",
                           "-of", "default=nw=1:nk=1", str(path)],
                          capture_output=True, text=True, timeout=60)
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return None


def caption_for(day: date, seconds: float, posts: int | None = None, light: bool = False) -> str:
    """One line, as the spec asks."""
    bits = [f"AgentChirp {day.isoformat()}", f"~{max(round(seconds / 60), 1)} min"]
    if posts is not None:
        bits.append(f"{posts} posts")
    if light:
        bits.append("quiet day")
    return " · ".join(bits)


def _brief_meta(markdown: str) -> tuple[int | None, bool]:
    posts = re.search(r"^- Posts:\s*(\d+)", markdown, re.MULTILINE)
    return (int(posts.group(1)) if posts else None), ("- Plan: light day" in markdown)


def speak_brief(day: date | None = None, dry_run: bool = False, input_path: Path | None = None,
                voice: str | None = None, on_log=None) -> dict:
    """-> {'ogg', 'mp3', 'seconds', 'caption', 'sent'}."""
    day = day or date.today()
    say = on_log or (lambda msg: print(msg, flush=True))
    brief_file = Path(input_path or config.brief_path(day))
    markdown = brief_file.read_text(encoding="utf-8")
    text = spoken_text(markdown)
    posts, light = _brief_meta(markdown)

    mp3 = config.audio_path(day, "mp3")
    ogg = config.audio_path(day, "ogg")
    say(f"voice: speaking {count_words(text)} words from {brief_file.name}")
    synthesize(text, mp3, voice)
    to_opus(mp3, ogg)
    seconds = probe_duration(ogg) or estimate_seconds(text)
    caption = caption_for(day, seconds, posts, light)
    say(f"voice: {ogg.name} ready, {seconds / 60:.1f} min, {ogg.stat().st_size // 1024} KB")

    sent = False
    if dry_run:
        say("voice: --dry-run, not sending")
    else:
        telegram.send_voice(ogg, caption, duration_s=round(seconds))
        sent = True
        say(f"voice: sent to Telegram chat {config.TELEGRAM_CHAT_ID}")
    return {"ogg": ogg, "mp3": mp3, "seconds": seconds, "caption": caption, "sent": sent}


def mark_sent(day: date, info: dict) -> Path:
    path = config.done_marker(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"date": day.isoformat(),
                                "caption": info.get("caption"),
                                "seconds": round(float(info.get("seconds") or 0))}, indent=2),
                    encoding="utf-8")
    return path


def already_sent(day: date) -> bool:
    return config.done_marker(day).exists()
