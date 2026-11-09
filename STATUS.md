# AgentChirp — build status

Built 2026-10-05 from `SPEC.md`. Everything that can be proven without touching X or your
Telegram has been run and is green. The two things only you can do — signing in to X and
approving the schedule — are waiting for you at the bottom.

## What was built

```
creators.yaml        9 creators in 3 categories, each with a verified flag
agentchirp/
  config.py          paths, creator parsing, .env reader for the Telegram token
  xfetch.py          login (headed) + fetch (headless), login-wall / CAPTCHA detection
  brief.py           segment plan, prompt, `claude -p`, markdown -> spoken text
  voice.py           edge-tts -> ogg/opus -> Telegram sendVoice, --dry-run
  telegram.py        sendVoice / sendMessage, token read at runtime
  runner.py          run = fetch -> brief -> voice, stage logs, idempotency
  logs.py            one dated line per stage
  __main__.py        python -m agentchirp login|fetch|brief|voice|run
schedule.ps1         registers the daily 10:50 task — WRITTEN, NOT RUN
README.md            what it is, setup, commands, troubleshooting
tests/               64 tests + two fake-post fixtures
.gitignore           data/ (your X session, posts, audio) stays out of git
```

### Commands

| Command | Does |
|---|---|
| `python -m agentchirp login` | headed Chromium on `data/browser-profile` at x.com/login, waits for x.com/home, exits. Never types, stores or asks for your password. |
| `python -m agentchirp fetch` | headless, same profile. Each handle in turn, posts from the last 24 h (fallback: latest 5) with text, time, url, likes, reposts, replies. Random 3–8 s between profiles. Saves `data/raw/x-YYYY-MM-DD.json`. |
| `python -m agentchirp brief` | `claude -p` (prompt on stdin) writes the six-segment script to `data/briefs/brief-YYYY-MM-DD.md`. |
| `python -m agentchirp voice` | edge-tts `en-GB-RyanNeural` → ogg/opus → `sendVoice` with a one-line caption. `--dry-run` writes the audio and sends nothing. |
| `python -m agentchirp run` | all three, a log line per stage in `data/logs/YYYY-MM-DD.log`, won't re-send a finished day without `--force`. |

### Decisions worth knowing

- **Segment timing** is derived, not hardcoded prose: 150 words/min × the spec's seconds gives
  intro 450, top trend 150, quick hits 75, second trend 150, deep dive 225, outro 450 — 1500
  words, 10 minutes. A test pins those numbers to the spec.
- **Light day** = fewer than 8 posts in total. The script condenses to 75 seconds (intro 10 s,
  "Today's signal" 50 s, outro 15 s) and is told to say out loud that it is a quiet day.
- **Login wall or CAPTCHA**: `fetch` stops, logs it, sends you the plain-text Telegram message
  "AgentChirp: X login expired — run `python -m agentchirp login`", and exits **2**. There is no
  bypass code anywhere, and a test asserts the scraper contains no click, fill or typing calls.
- **Four handles were found by web search**, not given, so they are `verified: false` in
  `creators.yaml` with a dated comment each. Please eyeball them once:
  Michael Wooldridge `@wooldridgemike`, Riley Brown `@rileybrown`,
  David Shapiro `@DaveShapi`, Yuchen Jin `@Yuchenj_UW`.
- **The token stays in Hermes.** `%LOCALAPPDATA%\hermes\.env` is parsed at runtime; a test scans
  the shipped files to make sure no token-shaped string got baked in.
- **No venv.** System Python 3.12 throughout, per the machine facts. `edge-tts` 7.2.8 was the one
  missing dependency and is now installed for system Python.

## Test results

**`python -m pytest` → 64 passed.** Config and creator parsing, the `.env` reader, the no-token
guard, segment timing, markdown→spoken-text, prompt construction, engagement-count parsing,
login-wall and CAPTCHA detection, dead-handle detection, 24 h selection and the latest-5
fallback, own-posts-only filtering, idempotency, `--force`, the exit-2 path, and the `--dry-run`
promise.

**Real brief + audio, proven on fake data (no X, no send):**

```
python -m agentchirp brief --date 2026-10-04 --input tests\fixtures\x-sample.json
  -> brief: 12 posts, full plan (600 s target)
  -> brief: wrote brief-2026-10-04.md, ~11.0 min      (1644 words)

python -m agentchirp voice --date 2026-10-04 --dry-run
  -> voice: speaking 1644 words from brief-2026-10-04.md
  -> voice: chirp-2026-10-04.ogg ready, 9.9 min, 3324 KB
  -> voice: --dry-run, not sending
```

`ffprobe` on the result: `codec_name=opus, sample_rate=48000, channels=1, duration=595.3` — the
OGG/Opus mono that Telegram wants for a voice note. The script came back with all six headings,
named the creator behind every point, and stayed on agentic engineering, AI writing code, app
development and tool features.

The light-day path was proven too:

```
python -m agentchirp brief --date 2026-10-03 --input tests\fixtures\x-light.json
  -> brief: 1 posts, light plan (75 s target)
  -> brief: wrote brief-2026-10-03.md, ~1.2 min       (180 words, 72 s)
```

`schedule.ps1` was validated with `-WhatIf` only. It resolved to
`...\Python312\python.exe -m agentchirp run`, daily at 10:50, in this folder.
**`Get-ScheduledTask AgentChirp` → does not exist. Nothing is scheduled.**

### Not run, deliberately

`login`, `fetch` and any real Telegram send — the spec says you log in first, and nothing should
arrive on your phone from a build. Sample artifacts from the fixture runs are sitting in
`data/briefs/` and `data/audio/` (gitignored) if you want to listen to one.

Only this folder was written to. Hermes and AgentK were read for reference and not modified.

## Next steps for you

1. **Sign in to X**, once:
   ```powershell
   cd agentchirp
   python -m agentchirp login
   ```
   A window opens on x.com/login. Sign in by hand; it closes itself and prints
   "Signed in — the session is saved in data/browser-profile."

2. **Check the four unverified handles** in `creators.yaml` (listed above). Change or delete any
   that are wrong — entries without a handle are skipped, not guessed at.

3. **Try one real end-to-end run without sending anything:**
   ```powershell
   python -m agentchirp fetch
   python -m agentchirp brief
   python -m agentchirp voice --dry-run
   ```
   Then play `data\audio\chirp-<today>.ogg` and read `data\briefs\brief-<today>.md`. If the
   voice or the pacing isn't right, `python -m agentchirp voice --voice en-GB-ThomasNeural
   --dry-run` tries another; the default lives in `agentchirp/config.py`.

4. **Send one for real** when you're happy: `python -m agentchirp run`.

5. **Approve the schedule** — only you should do this:
   ```powershell
   .\schedule.ps1 -WhatIf     # see exactly what it will register
   .\schedule.ps1             # register AgentChirp, daily 10:50
   ```
   It runs as you, when you're logged on, and needs no admin rights. `.\schedule.ps1 -Remove`
   undoes it.

If a morning ever goes quiet, `data\logs\<date>.log` has one line per stage, and the
troubleshooting section of `README.md` covers login expiry, CAPTCHAs, light days and dead
handles.
