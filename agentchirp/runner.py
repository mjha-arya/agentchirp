"""`run` — fetch, brief, voice, one log line per stage, and don't send the same day twice."""
from __future__ import annotations

from datetime import date
from functools import partial

from . import brief, config, logs, telegram, voice, xfetch

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BLOCKED = 2      # X login wall or CAPTCHA


def fetch_stage(day: date, headless: bool = True) -> int:
    """-> exit code. Saves data/raw/x-<day>.json, or warns Manish and returns 2."""
    say = partial(logs.log, day, "fetch")
    try:
        result = xfetch.fetch_day(day, headless=headless, on_log=lambda m: say(m))
    except (xfetch.LoginWall, xfetch.Captcha) as exc:
        say(f"blocked: {exc}")
        telegram.notify_login_expired()
        say("told Manish on Telegram to run `python -m agentchirp login`")
        return EXIT_BLOCKED
    path = xfetch.save(result.payload, day)
    if result.missing:
        say(f"handles that did not resolve: {', '.join('@' + h for h in result.missing)}")
    say(f"saved {result.post_count} posts to {path.name}")
    return EXIT_OK


def brief_stage(day: date) -> int:
    brief.write_brief(day, on_log=partial(logs.log, day, "brief"))
    return EXIT_OK


def voice_stage(day: date, dry_run: bool = False) -> int:
    info = voice.speak_brief(day, dry_run=dry_run, on_log=partial(logs.log, day, "voice"))
    if info["sent"]:
        voice.mark_sent(day, info)
    return EXIT_OK


def run(day: date | None = None, force: bool = False, dry_run: bool = False) -> int:
    day = day or date.today()
    config.ensure_dirs()
    say = partial(logs.log, day, "run")

    if voice.already_sent(day) and not force:
        say(f"{day.isoformat()} already went out — nothing to do (use --force to re-send)")
        return EXIT_OK

    say("start" + (" (forced)" if force else ""))
    code = fetch_stage(day)
    if code != EXIT_OK:
        say(f"stopped after fetch with exit {code}")
        return code
    brief_stage(day)
    voice_stage(day, dry_run=dry_run)
    say("done")
    return EXIT_OK
