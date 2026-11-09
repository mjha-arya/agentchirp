"""Turn the day's posts into a spoken script via the `claude` CLI.

There is no ANTHROPIC_API_KEY on this machine, so synthesis goes through the logged-in
`claude -p` subscription CLI, with the prompt on stdin because it is long.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import config

CLAUDE_TIMEOUT_S = 900
LIGHT_DAY_POSTS = 8          # fewer posts than this and the day gets the short treatment
MAX_POST_CHARS = 700         # trim very long posts before they go into the prompt

FOCUS = ("agentic engineering, AI writing code, app development, "
         "and new features in AI developer tools")


@dataclass(frozen=True)
class Segment:
    key: str
    title: str
    seconds: int
    guidance: str

    @property
    def words(self) -> int:
        """Spoken length at ~150 words/min."""
        return round(self.seconds / 60 * config.WORDS_PER_MINUTE)

    @property
    def spoken_length(self) -> str:
        if self.seconds >= 60 and self.seconds % 60 == 0:
            minutes = self.seconds // 60
            return f"{minutes} min" if minutes > 1 else "60 s"
        return f"{self.seconds} s"


# Manish, 2026-10-05: the whole brief is 90 seconds.
FULL_PLAN: tuple[Segment, ...] = (
    Segment("intro", "Intro", 5,
            "One sentence: the date and the day's headline theme."),
    Segment("top_trend", "Top trend", 30,
            "The single strongest thread of the day. Say who started it and who piled on, and "
            "what it means for someone building with agents."),
    Segment("quick_hits", "Quick hits", 20,
            "Two or three one-line items, each with the creator's name. Fast, no throat-clearing."),
    Segment("second_trend", "Second trend", 15,
            "The next distinct theme in two sentences — must not repeat the top trend. Name the creators."),
    Segment("deep_dive", "Deep dive", 15,
            "The one post most useful to a hands-on builder: what to try today, and whose idea it is."),
    Segment("outro", "Outro", 5,
            "One short closing sentence."),
)

LIGHT_PLAN: tuple[Segment, ...] = (
    Segment("intro", "Intro", 5,
            "One sentence: the date, and say plainly that it is a light day on X."),
    Segment("signal", "Today's signal", 50,
            "Everything worth hearing, in a handful of sentences, each with the creator's name."),
    Segment("outro", "Outro", 5,
            "One sentence to close."),
)


def plan(light: bool = False) -> tuple[Segment, ...]:
    return LIGHT_PLAN if light else FULL_PLAN


def plan_seconds(segments) -> int:
    return sum(s.seconds for s in segments)


def is_light_day(payload: dict) -> bool:
    return count_posts(payload) < LIGHT_DAY_POSTS


def count_posts(payload: dict) -> int:
    return sum(len(c.get("posts") or []) for c in payload.get("creators") or [])


def count_words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9'’\-]+", text or ""))


def estimate_seconds(text: str) -> float:
    return count_words(text) / config.WORDS_PER_MINUTE * 60


def spoken_text(markdown: str) -> str:
    """Strip the markdown down to the words the voice should actually say."""
    body = markdown or ""
    first = body.find("\n## ")
    if body.startswith("## "):
        first = 0
    elif first != -1:
        first += 1
    body = body[first:] if first != -1 else body

    lines: list[str] = []
    in_code = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code or stripped.startswith("#") or re.fullmatch(r"([-*_]\s*){3,}", stripped):
            continue
        if stripped.startswith("<!--") or stripped.startswith(">"):
            continue
        stripped = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", stripped)
        lines.append(stripped)

    text = "\n".join(lines)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)          # links -> their words
    text = re.sub(r"https?://\S+", "", text)                        # bare urls are unreadable
    text = re.sub(r"[*_`]{1,3}([^*_`]+)[*_`]{1,3}", r"\1", text)    # bold / italic / code
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _post_lines(payload: dict) -> list[str]:
    lines: list[str] = []
    for creator in payload.get("creators") or []:
        posts = creator.get("posts") or []
        if not posts:
            note = creator.get("status", "no-posts")
            lines.append(f"\n### {creator['name']} (@{creator['handle']}, "
                         f"{creator.get('category', '?')}) — nothing usable [{note}]")
            continue
        flag = " [fallback: latest posts, not last 24 h]" if creator.get("used_fallback") else ""
        lines.append(f"\n### {creator['name']} (@{creator['handle']}, "
                     f"{creator.get('category', '?')}){flag}")
        for post in posts:
            text = " ".join((post.get("text") or "").split())
            if len(text) > MAX_POST_CHARS:
                text = text[:MAX_POST_CHARS].rstrip() + " […]"
            lines.append(f"- ({post.get('time') or 'no timestamp'} · "
                         f"{post.get('likes', 0)} likes, {post.get('reposts', 0)} reposts, "
                         f"{post.get('replies', 0)} replies) {text}")
    return lines


def build_prompt(payload: dict, light: bool | None = None) -> str:
    light = is_light_day(payload) if light is None else light
    segments = plan(light)
    day = payload.get("date", "today")
    total = plan_seconds(segments)

    head = [
        "You are writing the script for a spoken morning voice note for Manish, a senior "
        "engineer who builds AI agents. It will be read aloud by a text-to-speech voice, so "
        "write words to be heard, not read.",
        "",
        f"Date: {day}. Posts collected: {count_posts(payload)} from X.",
        f"Focus relentlessly on {FOCUS}. Ignore politics, culture-war threads and personal chat.",
        "",
        "Hard rules:",
        "- Name the creator behind every single point (\"Simon Willison showed…\").",
        "- Only use what is in the posts below. Do not invent posts, numbers or quotes.",
        "- No URLs, no hashtags, no emoji, no markdown emphasis, no stage directions, no "
        "\"welcome back to the podcast\" filler.",
        f"- Output exactly {len(segments)} sections, in this order, each introduced by its "
        "heading line exactly as given, with plain prose underneath. Nothing before the first "
        "heading, nothing after the last section.",
        f"- Hard limit: the whole script must stay under {round(total / 60 * config.WORDS_PER_MINUTE)} "
        "words. Cut detail before you go over.",
        "",
        f"Segments (spoken at ~{config.WORDS_PER_MINUTE} words per minute, "
        f"{total} seconds total):",
    ]
    for segment in segments:
        head.append(f"- `## {segment.title}` — {segment.spoken_length}, aim for "
                    f"{segment.words} words. {segment.guidance}")

    if light:
        head += ["",
                 "This is a LIGHT day: there is little to report. Keep the whole script to "
                 f"{total} seconds (about {round(total / 60 * config.WORDS_PER_MINUTE)} words) "
                 "and say out loud, early on, that it is a quiet day."]

    head += ["", "Here are the posts:"] + _post_lines(payload)
    head += ["", "Now write the script."]
    return "\n".join(head)


def call_claude(prompt: str, timeout_s: int = CLAUDE_TIMEOUT_S) -> str:
    """`claude -p` with the prompt on stdin — there is no API key on this machine."""
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("the `claude` CLI is not on PATH")
    proc = subprocess.run([exe, "-p"], input=prompt, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout_s)
    out = (proc.stdout or "").strip()
    if proc.returncode != 0 or not out:
        raise RuntimeError(f"claude -p failed (exit {proc.returncode}): "
                           f"{(proc.stderr or out or '').strip()[:500]}")
    return out


def _tidy(script: str, segments) -> str:
    """Drop any preamble before the first heading and any trailing chatter."""
    titles = [s.title for s in segments]
    first = script.find("## ")
    if first > 0:
        script = script[first:]
    script = re.sub(r"^#{3,}\s+", "## ", script, flags=re.MULTILINE)
    missing = [t for t in titles if f"## {t}" not in script]
    if missing:
        raise RuntimeError(f"claude output is missing segments: {', '.join(missing)}")
    return script.strip()


def render(payload: dict, script: str, segments) -> str:
    seconds = estimate_seconds(spoken_text(script))
    day = payload.get("date", "today")
    header = [
        f"# AgentChirp brief — {day}",
        "",
        f"- Posts: {count_posts(payload)} from "
        f"{sum(1 for c in payload.get('creators') or [] if c.get('posts'))} creators",
        f"- Fetched: {payload.get('fetched_at', 'unknown')}",
        f"- Plan: {'light day' if len(segments) == len(LIGHT_PLAN) else 'full day'}, "
        f"{plan_seconds(segments)} s target",
        f"- Estimated spoken length: {seconds / 60:.1f} min "
        f"({count_words(spoken_text(script))} words at {config.WORDS_PER_MINUTE} wpm)",
        "",
        "",
    ]
    return "\n".join(header) + script.strip() + "\n"


def write_brief(day: date | None = None, input_path: Path | None = None,
                output_path: Path | None = None, on_log=None) -> Path:
    day = day or date.today()
    say = on_log or (lambda msg: print(msg, flush=True))
    raw = input_path or config.raw_path(day)
    payload = json.loads(Path(raw).read_text(encoding="utf-8"))

    light = is_light_day(payload)
    segments = plan(light)
    say(f"brief: {count_posts(payload)} posts, "
        f"{'light' if light else 'full'} plan ({plan_seconds(segments)} s target)")

    script = _tidy(call_claude(build_prompt(payload, light)), segments)
    out = Path(output_path or config.brief_path(day))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(payload, script, segments), encoding="utf-8")
    say(f"brief: wrote {out.name}, ~{estimate_seconds(spoken_text(script)) / 60:.1f} min")
    return out
