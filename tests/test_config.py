"""Config parsing: the creator list, the .env reader, date handling."""
import re

import pytest

from agentchirp import config


def test_shipped_creators_yaml_has_three_populated_categories():
    creators, skipped = config.load_creators()
    assert skipped == []
    assert {c.category for c in creators} == set(config.CATEGORIES)
    assert len(creators) == 9
    for category in config.CATEGORIES:
        assert len([c for c in creators if c.category == category]) == 3


def test_shipped_handles_are_clean_and_unique():
    creators, _ = config.load_creators()
    handles = [c.handle for c in creators]
    assert len(set(h.lower() for h in handles)) == len(handles)
    for handle in handles:
        assert handle and not handle.startswith("@") and " " not in handle
    assert config.X_BASE + "/dhh" in [c.url for c in creators]


def test_web_searched_handles_are_flagged_unverified():
    creators, _ = config.load_creators()
    unverified = {c.name for c in creators if not c.verified}
    assert unverified == {"Michael Wooldridge", "Riley Brown", "David Shapiro", "Yuchen Jin"}


def test_parse_creators_strips_at_sign_and_keeps_order():
    creators, skipped = config.parse_creators(
        "biggest:\n"
        "  - name: A\n    handle: '@aaa'\n"
        "  - name: B\n    handle: bbb\n    verified: false\n")
    assert skipped == []
    assert [(c.name, c.handle, c.verified) for c in creators] == [
        ("A", "aaa", True), ("B", "bbb", False)]


def test_parse_creators_skips_entries_it_cannot_use():
    creators, skipped = config.parse_creators(
        "biggest:\n"
        "  - name: Has Handle\n    handle: ok\n"
        "  - name: No Handle\n"
        "  - handle: nameless\n"
        "nonsense:\n"
        "  - name: Ignored\n    handle: ignored\n")
    assert [c.handle for c in creators] == ["ok"]
    assert any("No Handle has no handle" in s for s in skipped)
    assert any("no name" in s for s in skipped)
    assert any("nonsense" in s for s in skipped)


def test_parse_creators_rejects_a_non_mapping_file():
    with pytest.raises(ValueError):
        config.parse_creators("- just\n- a\n- list\n")


def test_parse_env_handles_exports_quotes_and_comments():
    env = config.parse_env(
        "# a comment\n"
        "\n"
        "export TELEGRAM_BOT_TOKEN=\"123:abc\"\n"
        "PLAIN=value with spaces\n"
        "QUOTED='sq'\n"
        "not a pair\n"
        "1BAD=x\n")
    assert env["TELEGRAM_BOT_TOKEN"] == "123:abc"
    assert env["PLAIN"] == "value with spaces"
    assert env["QUOTED"] == "sq"
    assert "1BAD" not in env


def test_telegram_token_comes_from_the_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv(config.TELEGRAM_TOKEN_KEY, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("TELEGRAM_BOT_TOKEN=999:zzz\n", encoding="utf-8")
    assert config.telegram_token(env_file) == "999:zzz"


def test_telegram_token_raises_when_nothing_provides_it(tmp_path, monkeypatch):
    monkeypatch.delenv(config.TELEGRAM_TOKEN_KEY, raising=False)
    with pytest.raises(RuntimeError, match=config.TELEGRAM_TOKEN_KEY):
        config.telegram_token(tmp_path / "missing.env")


def test_no_shipped_file_holds_a_token_value():
    """The spec is explicit: parse Hermes' .env, never bake the value in here."""
    paths = list((config.ROOT / "agentchirp").rglob("*.py"))
    paths += [p for p in config.ROOT.glob("*") if p.suffix in {".yaml", ".yml", ".ps1", ".md"}]
    assert len(paths) > 8
    for path in paths:
        body = path.read_text(encoding="utf-8", errors="replace")
        assert not re.search(r"\d{8,}:[A-Za-z0-9_-]{30,}", body), f"{path.name} looks like a token"


def test_parse_day_round_trips_and_defaults_to_today():
    from datetime import date
    assert config.parse_day("2026-10-04") == date(2026, 10, 4)
    assert config.parse_day(None) == date.today()
    with pytest.raises(ValueError):
        config.parse_day("4 October")


def test_paths_live_under_the_data_dir(temp_data):
    from datetime import date
    day = date(2026, 10, 4)
    assert config.raw_path(day).name == "x-2026-10-04.json"
    assert config.brief_path(day).name == "brief-2026-10-04.md"
    assert config.audio_path(day).name == "chirp-2026-10-04.ogg"
    assert config.log_path(day).name == "2026-10-04.log"
    for path in (config.raw_path(day), config.brief_path(day), config.audio_path(day),
                 config.log_path(day), config.done_marker(day), config.profile_dir()):
        assert temp_data in path.parents
