# AgentChirp

> **Your morning AI-trends podcast, made by an agent.** It reads what the top agentic-engineering voices posted on X in the last 24 hours, finds the trends, writes a timed spoken script, and sends it to Telegram as a voice note at 11:00.

**Read-only by design:** it never posts, likes, follows, replies or DMs, and it never sees your password. 60+ offline tests, idempotent stages, and `--dry-run` on everything.

```
X (Playwright, read-only) ──► claude -p (trend synthesis + script) ──► edge-tts ──► ffmpeg ──► Telegram voice note
```

**Stack:** Python · Playwright · Claude Code CLI · edge-tts · ffmpeg · Telegram Bot API · pytest

## How it works

```
fetch  ──>  data/raw/x-YYYY-MM-DD.json      Playwright, logged-in Chromium profile
brief  ──>  data/briefs/brief-YYYY-MM-DD.md `claude -p` turns posts into a spoken script
voice  ──>  data/audio/chirp-YYYY-MM-DD.ogg edge-tts -> ffmpeg -> Telegram sendVoice
```

The script has six segments, timed at ~150 words per minute:

| Segment | Spoken length | Words |
|---|---|---|
| Intro | 3 min | 450 |
| Top trend | 60 s | 150 |
| Quick hits | 30 s | 75 |
| Second trend | 60 s | 150 |
| Deep dive | 90 s | 225 |
| Outro | 3 min | 450 |

On a light day (fewer than 8 posts in total) it switches to a condensed 75-second script and says
out loud that it is a quiet day.

## Setup

Needs **system Python 3.12** — no virtualenv, because Windows Application Control blocks
`.venv\Scripts\python.exe` on this machine.

```powershell
python -m pip install playwright edge-tts pyyaml requests pytest
python -m playwright install chromium        # only if Chromium is missing
```

`ffmpeg` must be on PATH (it is, via winget), and the `claude` CLI must be on PATH and logged in —
there is no `ANTHROPIC_API_KEY` here, so synthesis goes through the subscription CLI.

The Telegram bot token is read at runtime from `%LOCALAPPDATA%\hermes\.env`
(`TELEGRAM_BOT_TOKEN`). It is never copied into this repo.

Then sign in to X once:

```powershell
python -m agentchirp login
```

A real browser window opens on x.com/login. Type your credentials there; AgentChirp waits for
x.com/home and closes the window itself. The session lives in `data/browser-profile` and
survives restarts, so you should only need this again when X expires it.

## Commands

```powershell
python -m agentchirp login                   # one-time hand sign-in (headed)
python -m agentchirp fetch                   # collect the last 24 h of posts
python -m agentchirp brief                   # write today's script with claude -p
python -m agentchirp voice                   # speak it and send the voice note
python -m agentchirp voice --dry-run         # make the audio, send nothing
python -m agentchirp run                     # fetch -> brief -> voice, logged
python -m agentchirp run --force             # re-send a day that already went out
```

Useful flags: `--date YYYY-MM-DD` on every command except `login`; `--input` / `--output` on
`brief`; `--input` and `--voice` on `voice`; `--headed` on `fetch` to watch it work.

Exit codes: `0` fine, `1` error, `2` X showed a login wall or a CAPTCHA.

### Scheduling

`schedule.ps1` registers the Windows Scheduled Task **AgentChirp**, daily at 10:50. It is not
registered yet — run it yourself when you are happy with the setup:

```powershell
.\schedule.ps1 -WhatIf     # dry run
.\schedule.ps1             # register
.\schedule.ps1 -Remove     # unregister
```

## Creators

Edit `creators.yaml` freely. Three categories — `biggest`, `academics`, `new` — and each entry
has a `name`, a `handle` and a `verified` flag. `verified: false` marks a handle that was found
by web search rather than given, and is worth eyeballing once. Entries without a handle are
skipped and logged, never guessed at.

## Where things land

```
creators.yaml                      the creator list (yours to edit)
agentchirp/                        the package
data/browser-profile/              your X session (gitignored, never commit)
data/raw/x-YYYY-MM-DD.json         the posts as collected
data/briefs/brief-YYYY-MM-DD.md    the spoken script
data/audio/chirp-YYYY-MM-DD.{mp3,ogg}
data/logs/YYYY-MM-DD.log           one line per stage
data/state/YYYY-MM-DD.done         "this day already went out" marker
tests/fixtures/                    fake posts, so brief + voice can be tested without X
```

`run` is idempotent: once a day's voice note has been sent, the marker in `data/state/` stops it
going out twice. `--force` overrides that. `--dry-run` never writes the marker.

## Troubleshooting

**"AgentChirp: X login expired" on Telegram, or `fetch` exits 2.**
X put up a login wall. Run `python -m agentchirp login`, sign in, then `python -m agentchirp run`.
AgentChirp will not try to work around a login wall.

**A CAPTCHA / "verify you are human" page.**
Same exit code, same message: it stops rather than fighting it. Run `login` and solve the check
in that window, then re-run. If it keeps happening, slow the pacing down by raising
`FETCH_DELAY_RANGE_S` in `agentchirp/config.py`.

**An empty or very light day.**
Below 8 posts, the brief condenses to about 75 seconds and says it is a quiet day. If a creator
had nothing in the last 24 h, `fetch` falls back to their latest 5 posts and the brief is told
they are older than overnight. If *nothing* at all comes back, `voice` refuses to send an empty
brief and says so.

**A handle stops resolving.**
`fetch` logs `skipped @handle: profile did not resolve` and carries on with the rest. Fix or
remove the entry in `creators.yaml`.

**`claude -p failed`.**
Check the CLI is logged in: `claude -p "say hi"`. There is no API key fallback by design.

**`TELEGRAM_BOT_TOKEN not found`.**
Check `%LOCALAPPDATA%\hermes\.env` still has the line. Do not copy the value in here.

**Scheduled task ran but nothing arrived.**
Read `data/logs/<date>.log` — there is one line per stage — and
`Get-ScheduledTask AgentChirp | Get-ScheduledTaskInfo` for the last result.

## Tests

```powershell
python -m pytest
```

Everything that needs no network is covered: config and creator parsing, the `.env` reader,
segment timing, markdown-to-spoken-text, prompt construction, engagement-count and login-wall
parsing, post selection and the 24 h fallback, idempotency, and the `--dry-run` promise.
To exercise the real brief and audio path without touching X:

```powershell
python -m agentchirp brief --date 2026-10-04 --input tests\fixtures\x-sample.json
python -m agentchirp voice --date 2026-10-04 --dry-run
```

---
Built by **Manish Jha**, secure and provable AI agents. [Profile →](https://github.com/mjha-arya)
