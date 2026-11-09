"""python -m agentchirp <login|fetch|brief|voice|run>"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import brief as brief_mod
from . import config, runner, voice as voice_mod, xfetch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m agentchirp",
        description="Morning voice brief on what the AI / agentic-engineering crowd posted on X.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_login = sub.add_parser("login", help="open a window so you can sign in to X by hand (once)")
    p_login.add_argument("--timeout", type=int, default=600,
                         help="seconds to wait for the sign-in (default 600)")

    p_fetch = sub.add_parser("fetch", help="collect the last 24 h of posts from every creator")
    p_fetch.add_argument("--date", help="YYYY-MM-DD, default today")
    p_fetch.add_argument("--headed", action="store_true", help="show the browser (debugging)")

    p_brief = sub.add_parser("brief", help="write the spoken script with `claude -p`")
    p_brief.add_argument("--date", help="YYYY-MM-DD, default today")
    p_brief.add_argument("--input", type=Path, help="raw posts JSON (default data/raw/x-<date>.json)")
    p_brief.add_argument("--output", type=Path, help="where to write the brief markdown")

    p_voice = sub.add_parser("voice", help="speak the brief and send it as a Telegram voice note")
    p_voice.add_argument("--date", help="YYYY-MM-DD, default today")
    p_voice.add_argument("--dry-run", action="store_true", help="write the audio but do not send")
    p_voice.add_argument("--input", type=Path, help="brief markdown (default data/briefs/brief-<date>.md)")
    p_voice.add_argument("--voice", default=config.VOICE, help=f"edge-tts voice (default {config.VOICE})")

    p_run = sub.add_parser("run", help="fetch -> brief -> voice")
    p_run.add_argument("--date", help="YYYY-MM-DD, default today")
    p_run.add_argument("--force", action="store_true", help="re-send even if the day already went out")
    p_run.add_argument("--dry-run", action="store_true", help="do everything except the Telegram send")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    day = config.parse_day(getattr(args, "date", None))
    config.ensure_dirs()

    if args.command == "login":
        ok = xfetch.login(timeout_s=args.timeout)
        print("Signed in — the session is saved in data/browser-profile." if ok else
              "Not signed in. Run `python -m agentchirp login` again when you have a moment.")
        return runner.EXIT_OK if ok else runner.EXIT_ERROR

    if args.command == "fetch":
        return runner.fetch_stage(day, headless=not args.headed)

    if args.command == "brief":
        brief_mod.write_brief(day, input_path=args.input, output_path=args.output)
        return runner.EXIT_OK

    if args.command == "voice":
        info = voice_mod.speak_brief(day, dry_run=args.dry_run, input_path=args.input,
                                     voice=args.voice)
        if info["sent"]:
            voice_mod.mark_sent(day, info)
        return runner.EXIT_OK

    if args.command == "run":
        return runner.run(day, force=args.force, dry_run=args.dry_run)

    return runner.EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
