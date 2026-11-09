"""Read-only scrape of X profiles through a persistent, hand-logged-in Chromium profile.

AgentChirp never posts, likes, follows, replies or DMs, and it never types a password: the
`login` command just opens a window and waits for Manish to sign in himself. If X puts up a
login wall or a CAPTCHA we stop and tell him — bypassing either is out of scope by design.
"""
from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from . import config
from .config import Creator


class LoginWall(RuntimeError):
    """X asked for credentials — the saved session is gone or expired."""


class Captcha(RuntimeError):
    """X asked for a human check."""


_COUNT_RE = re.compile(r"(\d+(?:[.,]\d+)*)\s*([KMB])?", re.IGNORECASE)
_SUFFIX = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}

_CAPTCHA_MARKERS = ("arkoselabs", "funcaptcha", "recaptcha", "captcha-delivery",
                    "verify you are human", "/account/access")
_LOGIN_URL_MARKERS = ("/login", "/i/flow/login", "/i/flow/signup", "/account/login_challenge")
_LOGIN_HTML_MARKERS = ('data-testid="loginbutton"', "sign in to x", "log in to x",
                       "sign up for x", "see what's happening in the world right now")
_MISSING_MARKERS = ("this account doesn't exist", "this account doesn’t exist",
                    "account suspended", "these posts are protected",
                    "caught in the act of being themselves")

TWEETS_JS = """
() => {
  const out = [];
  const metric = (art, name) => {
    const el = art.querySelector(`button[data-testid="${name}"], a[data-testid="${name}"]`);
    if (!el) return '';
    return el.getAttribute('aria-label') || el.innerText || '';
  };
  for (const art of document.querySelectorAll('article[data-testid="tweet"]')) {
    const textEl = art.querySelector('div[data-testid="tweetText"]');
    const timeEl = art.querySelector('time[datetime]');
    const linkEl = timeEl ? timeEl.closest('a[href*="/status/"]')
                          : art.querySelector('a[href*="/status/"]');
    const social = art.querySelector('div[data-testid="socialContext"]');
    out.push({
      text: textEl ? textEl.innerText : '',
      time: timeEl ? timeEl.getAttribute('datetime') : null,
      url: linkEl ? new URL(linkEl.getAttribute('href'), location.origin).href : null,
      likes_raw: metric(art, 'like') || metric(art, 'unlike'),
      reposts_raw: metric(art, 'retweet') || metric(art, 'unretweet'),
      replies_raw: metric(art, 'reply'),
      social_context: social ? social.innerText : ''
    });
  }
  return out;
}
"""


def parse_count(raw: str | None) -> int:
    """'1.2K reposts' -> 1200, '123,456 Likes. Like' -> 123456, '' -> 0."""
    if not raw:
        return 0
    match = _COUNT_RE.search(str(raw).replace("\u00a0", " "))
    if not match:
        return 0
    number, suffix = match.group(1), (match.group(2) or "").upper()
    try:
        if suffix:
            return int(float(number.replace(",", ".")) * _SUFFIX[suffix])
        return int(number.replace(",", "").replace(".", ""))
    except ValueError:
        return 0


def wall_kind(url: str, html: str) -> str | None:
    """-> 'captcha' | 'login' | None. CAPTCHA first: its page often also offers a log-in link."""
    low_url, low_html = (url or "").lower(), (html or "").lower()
    if any(m in low_url or m in low_html for m in _CAPTCHA_MARKERS):
        return "captcha"
    if any(m in low_url for m in _LOGIN_URL_MARKERS):
        return "login"
    if any(m in low_html for m in _LOGIN_HTML_MARKERS):
        return "login"
    return None


def looks_missing(html: str) -> bool:
    low = (html or "").lower()
    return any(m in low for m in _MISSING_MARKERS)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def select_posts(posts: list[dict], now: datetime | None = None,
                 window_hours: int = 24, fallback: int = 5) -> tuple[list[dict], bool]:
    """Posts from the last `window_hours`; if none, the latest `fallback`. -> (posts, used_fallback)."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_hours)
    dated = [p for p in posts if _parse_time(p.get("time"))]
    dated.sort(key=lambda p: _parse_time(p["time"]), reverse=True)
    recent = [p for p in dated if _parse_time(p["time"]) >= cutoff]
    if recent:
        return recent, False
    return dated[:fallback], True


def _clean(handle: str, rows: list[dict]) -> list[dict]:
    """Keep this profile's own posts, drop reposts of others, de-duplicate by url."""
    wanted = f"/{handle.lower()}/status/"
    seen: set[str] = set()
    out = []
    for row in rows:
        url = (row.get("url") or "")
        if wanted not in url.lower() or not (row.get("text") or "").strip():
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append({
            "text": (row.get("text") or "").strip(),
            "time": row.get("time"),
            "url": url,
            "likes": parse_count(row.get("likes_raw")),
            "reposts": parse_count(row.get("reposts_raw")),
            "replies": parse_count(row.get("replies_raw")),
        })
    return out


def _guard(page) -> None:
    kind = wall_kind(page.url, page.content())
    if kind == "captcha":
        raise Captcha(f"CAPTCHA / human check at {page.url}")
    if kind == "login":
        raise LoginWall(f"login wall at {page.url}")


@dataclass
class FetchResult:
    payload: dict
    post_count: int
    missing: list[str]


def fetch_day(day: date | None = None, creators: list[Creator] | None = None,
              headless: bool = True, scrolls: int = 3,
              on_log=None) -> FetchResult:
    """Open each profile in turn and collect its recent posts. Raises LoginWall / Captcha."""
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright

    day = day or date.today()
    if creators is None:
        creators, skipped = config.load_creators()
    else:
        skipped = []
    say = on_log or (lambda msg: print(msg, flush=True))
    for note in skipped:
        say(f"skipped {note}")

    entries: list[dict] = []
    missing: list[str] = []
    total = 0

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(config.profile_dir()), channel="chrome", headless=headless,  # real Chrome; X rejects bundled Chromium
            viewport={"width": 1280, "height": 1600})
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            for index, creator in enumerate(creators):
                if index:
                    time.sleep(random.uniform(*config.FETCH_DELAY_RANGE_S))
                entry = {"name": creator.name, "handle": creator.handle,
                         "category": creator.category, "verified": creator.verified,
                         "status": "ok", "used_fallback": False, "posts": []}
                try:
                    page.goto(creator.url, wait_until="domcontentloaded", timeout=45_000)
                    _guard(page)
                    try:
                        page.wait_for_selector('article[data-testid="tweet"]', timeout=20_000)
                    except PWTimeout:
                        _guard(page)
                        if looks_missing(page.content()):
                            entry["status"] = "missing"
                            missing.append(creator.handle)
                            say(f"skipped @{creator.handle}: profile did not resolve")
                            entries.append(entry)
                            continue
                        entry["status"] = "no-posts"
                        say(f"@{creator.handle}: no posts rendered")
                        entries.append(entry)
                        continue
                    rows = page.evaluate(TWEETS_JS)
                    for _ in range(max(scrolls, 0)):
                        page.mouse.wheel(0, 2400)
                        page.wait_for_timeout(1200)
                        rows += page.evaluate(TWEETS_JS)
                    posts, used_fallback = select_posts(_clean(creator.handle, rows))
                    entry["posts"] = posts
                    entry["used_fallback"] = used_fallback
                    if not posts:
                        entry["status"] = "no-posts"
                    total += len(posts)
                    say(f"@{creator.handle}: {len(posts)} posts"
                        + (" (fallback: latest 5)" if used_fallback else ""))
                except (LoginWall, Captcha):
                    raise
                except Exception as exc:  # noqa: BLE001 - one bad profile must not sink the run
                    entry["status"] = "error"
                    entry["error"] = f"{type(exc).__name__}: {exc}"
                    say(f"@{creator.handle}: error {entry['error']}")
                entries.append(entry)
        finally:
            ctx.close()

    payload = {
        "date": day.isoformat(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "window_hours": 24,
        "post_count": total,
        "creators": entries,
    }
    return FetchResult(payload=payload, post_count=total, missing=missing)


def save(payload: dict, day: date) -> "object":
    path = config.raw_path(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def login(timeout_s: int = 600) -> bool:
    """Headed window on the persistent profile. We never type, store or ask for the password."""
    from playwright.sync_api import sync_playwright

    config.profile_dir().mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(config.profile_dir()), channel="chrome", headless=False,
            viewport={"width": 1280, "height": 900})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(f"{config.X_BASE}/login")
            print("Sign in to X in the window that just opened. AgentChirp waits, watches for\n"
                  "x.com/home, then closes by itself. It will never ask for your password.",
                  flush=True)
            deadline = time.time() + timeout_s
            ok = False
            while time.time() < deadline:
                try:
                    if page.url.rstrip("/").endswith("x.com/home"):
                        ok = True
                        break
                    if "/login" not in page.url and "/i/flow" not in page.url:
                        page.goto(f"{config.X_BASE}/home", wait_until="domcontentloaded")
                        if wall_kind(page.url, page.content()) is None:
                            ok = True
                            break
                except Exception:  # window closed by hand
                    break
                time.sleep(3)
            return ok
        finally:
            try:
                ctx.close()
            except Exception:
                pass
