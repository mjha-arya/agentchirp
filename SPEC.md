# AgentChirp — build spec

AgentChirp reads X (Twitter) posts from a fixed list of AI / agentic-engineering creators every
morning, works out the trends, and sends Manish a Telegram **voice message** at 11:00.

Origin: Manish's request to Hermes on 2026-10-05 (state.db session 20261002_202251_11be652c).
An earlier Claude Code attempt failed at step 1: X showed a login wall because the automation
browser had its own empty profile. Design below fixes that with a one-time login.

## Machine facts (Windows 11, verified)
- Use **system Python 3.12** (`python`). Do NOT create or use a .venv: Windows Application
  Control blocks venv python.exe on this machine.
- `playwright` is installed for system Python. `edge-tts` is NOT — `python -m pip install edge-tts`.
- `claude` CLI is on PATH and logged in (subscription). There is NO ANTHROPIC_API_KEY. For LLM
  synthesis call `claude -p "<prompt>"` via subprocess (pass the prompt on stdin if it is long).
- Telegram: read `TELEGRAM_BOT_TOKEN` from `%LOCALAPPDATA%\hermes\.env` at runtime (parse the
  file; never copy the value into this repo). Chat id: `8843609758`. Send with Bot API `sendVoice`
  (OGG/Opus). ffmpeg is on PATH for mp3 -> ogg/opus conversion.
- Reference pattern for a Playwright persistent-profile login: `..\AgentK` (`python -m agentk login`).

## Creators (config file, Manish will edit it)
Put these in `creators.yaml`, 3 categories:
- biggest: DHH (@dhh), Simon Willison (@simonw), swyx (@swyx)
- academics: François Chollet (@fchollet), Michael Wooldridge, Percy Liang (@percyliang)
- new: Riley Brown, David Shapiro, Yuchen Jin
For names without a handle, find the correct X handle with a web search and mark it
`verified: false` in the YAML with a comment. Skip and log any handle that does not resolve.

## Build
Package `agentchirp`, run as `python -m agentchirp <command>`:

1. `login` — opens a **headed** Playwright Chromium with persistent profile `data/browser-profile`
   at x.com/login. Manish logs in by hand; the command waits until x.com/home loads, then exits.
   The code must never type, store or ask for the X password.
2. `fetch` — headless, same profile. For each handle open x.com/<handle>, collect posts from the
   last 24 h (fallback: latest 5): text, time, url, likes, reposts, replies. Polite pacing
   (random 3–8 s between profiles). If the login wall or a CAPTCHA appears: stop, log it, exit
   code 2, and send Manish a short Telegram TEXT message "AgentChirp: X login expired — run
   `python -m agentchirp login`". Never try to bypass. Save `data/raw/x-YYYY-MM-DD.json`.
3. `brief` — read the day's JSON, call `claude -p` to write the script. Six segments with these
   spoken lengths (~150 words/min): intro 3 min, top trend 60 s, quick hits 30 s, second trend
   60 s, deep dive 90 s, outro 3 min. Focus: agentic engineering, AI code writing, app
   development, new tool features. Name the creator behind each point. If the day is light,
   condense to 60–90 s total and say so. Save `data/briefs/brief-YYYY-MM-DD.md`.
4. `voice` — edge-tts (natural English voice, e.g. en-GB-RyanNeural) -> ogg/opus ->
   Telegram `sendVoice` with a one-line caption. `--dry-run` writes the file but does not send.
5. `run` — fetch -> brief -> voice, with a log line per stage in `data/logs/YYYY-MM-DD.log`.
   Idempotent: re-running a finished day does not re-send unless `--force`.
6. `schedule.ps1` — registers Windows Scheduled Task `AgentChirp` daily 10:50 running
   `python -m agentchirp run`. **Write it, do NOT run it.** Manish approves the schedule.

Also: `README.md` (what it is, setup, commands, troubleshooting: login expired, CAPTCHA, empty
day), `.gitignore` (data/), `git init` + one commit. Small pytest tests for the parts that need
no network (config parsing, brief segment timing, idempotency).

## Test before you finish
- `pytest` green.
- `python -m agentchirp brief` and `voice --dry-run` on a small FAKE sample JSON in
  `tests/fixtures/` so the brief + audio path is proven without X.
- Do NOT run `login`, `fetch` or a real Telegram send — Manish has to log in first.

## Rules
- Write only inside this folder (`Genie\Agents\AgentChirp`). Do not modify Hermes or AgentK.
- Read-only on X: never post, like, follow, reply or DM.
- Finish with `STATUS.md`: what was built, test results, and the exact next steps for Manish.
