"""The network-free halves of the scraper: count parsing, wall detection, post selection."""
from datetime import datetime, timedelta, timezone

import pytest

from agentchirp import xfetch

NOW = datetime(2026, 10, 4, 9, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("raw,expected", [
    ("", 0),
    (None, 0),
    ("Like", 0),
    ("12 replies. Reply", 12),
    ("1,234 Likes. Like", 1234),
    ("1.2K reposts. Repost", 1200),
    ("3.4M Likes", 3_400_000),
    ("2B", 2_000_000_000),
    ("1.234", 1234),
])
def test_parse_count(raw, expected):
    assert xfetch.parse_count(raw) == expected


@pytest.mark.parametrize("url,html,expected", [
    ("https://x.com/simonw", "<article data-testid='tweet'>hi</article>", None),
    ("https://x.com/i/flow/login", "<div>whatever</div>", "login"),
    ("https://x.com/login", "", "login"),
    ("https://x.com/simonw", '<div data-testid="LoginButton">Sign in</div>', "login"),
    ("https://x.com/simonw", "<h1>Sign in to X</h1>", "login"),
    ("https://x.com/account/access", "<p>Please verify</p>", "captcha"),
    ("https://x.com/simonw", "<iframe src='https://client-api.arkoselabs.com/x'>", "captcha"),
    ("https://x.com/login", "<div>funcaptcha</div>", "captcha"),
])
def test_wall_kind(url, html, expected):
    assert xfetch.wall_kind(url, html) == expected


def test_looks_missing_spots_dead_handles():
    assert xfetch.looks_missing("<span>This account doesn’t exist</span>")
    assert xfetch.looks_missing("<span>Account suspended</span>")
    assert not xfetch.looks_missing("<article data-testid='tweet'>a normal timeline</article>")


def _post(hours_ago: float, url: str = "https://x.com/simonw/status/1") -> dict:
    return {"text": "hello", "url": url,
            "time": (NOW - timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z")}


def test_select_posts_keeps_the_last_24_hours_newest_first():
    posts = [_post(30), _post(2), _post(20), _post(1)]
    chosen, used_fallback = xfetch.select_posts(posts, now=NOW)
    assert used_fallback is False
    assert [p["time"] for p in chosen] == [_post(1)["time"], _post(2)["time"], _post(20)["time"]]


def test_select_posts_falls_back_to_the_latest_five():
    posts = [_post(h) for h in (25, 26, 27, 28, 29, 30, 31)]
    chosen, used_fallback = xfetch.select_posts(posts, now=NOW)
    assert used_fallback is True
    assert len(chosen) == 5
    assert chosen[0]["time"] == _post(25)["time"]


def test_select_posts_ignores_undated_rows_and_copes_with_nothing():
    chosen, used_fallback = xfetch.select_posts(
        [{"text": "no time", "time": None}, {"text": "junk", "time": "not a date"}], now=NOW)
    assert chosen == []
    assert used_fallback is True
    assert xfetch.select_posts([], now=NOW) == ([], True)


def test_clean_keeps_only_this_handle_and_deduplicates():
    rows = [
        {"text": "mine", "time": _post(1)["time"], "url": "https://x.com/SimonW/status/10",
         "likes_raw": "1.2K Likes", "reposts_raw": "30 reposts", "replies_raw": "4 replies"},
        {"text": "mine again (same url)", "time": _post(1)["time"],
         "url": "https://x.com/SimonW/status/10"},
        {"text": "someone else's, shown because simonw reposted it", "time": _post(2)["time"],
         "url": "https://x.com/dhh/status/11"},
        {"text": "   ", "time": _post(2)["time"], "url": "https://x.com/simonw/status/12"},
        {"text": "no url", "time": _post(2)["time"], "url": None},
    ]
    cleaned = xfetch._clean("simonw", rows)
    assert [p["text"] for p in cleaned] == ["mine"]
    assert cleaned[0] == {"text": "mine", "time": _post(1)["time"],
                          "url": "https://x.com/SimonW/status/10",
                          "likes": 1200, "reposts": 30, "replies": 4}


def test_save_writes_the_dated_raw_file(temp_data):
    from datetime import date

    from agentchirp import config
    path = xfetch.save({"date": "2026-10-04", "creators": []}, date(2026, 10, 4))
    assert path == config.raw_path(date(2026, 10, 4))
    assert '"date": "2026-10-04"' in path.read_text(encoding="utf-8")


def test_the_scraper_has_no_write_actions():
    """Read-only on X: no posting, liking, following, replying or DMing anywhere in here."""
    body = open(xfetch.__file__, encoding="utf-8").read().lower()
    for forbidden in ("tweetbutton", "post_tweet", "followbutton", "dmcomposer",
                      ".click(", ".fill(", "keyboard.type", "set_input_files"):
        assert forbidden not in body, f"{forbidden} would make AgentChirp write to X"
