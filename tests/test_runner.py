"""Idempotency, stage logging, and what happens when X puts up a wall."""
from datetime import date

from agentchirp import config, logs, runner, voice, xfetch

DAY = date(2026, 10, 4)


def _stub_stages(monkeypatch, calls):
    monkeypatch.setattr(runner, "fetch_stage",
                        lambda day, headless=True: calls.append("fetch") or runner.EXIT_OK)
    monkeypatch.setattr(runner, "brief_stage",
                        lambda day: calls.append("brief") or runner.EXIT_OK)

    def fake_voice(day, dry_run=False):
        calls.append("voice")
        voice.mark_sent(day, {"caption": "AgentChirp 2026-10-04", "seconds": 600})
        return runner.EXIT_OK

    monkeypatch.setattr(runner, "voice_stage", fake_voice)


def test_run_walks_the_three_stages_in_order(temp_data, monkeypatch):
    calls = []
    _stub_stages(monkeypatch, calls)
    assert runner.run(DAY) == runner.EXIT_OK
    assert calls == ["fetch", "brief", "voice"]
    assert voice.already_sent(DAY) is True


def test_a_finished_day_is_not_sent_twice(temp_data, monkeypatch):
    calls = []
    _stub_stages(monkeypatch, calls)
    runner.run(DAY)
    calls.clear()
    assert runner.run(DAY) == runner.EXIT_OK
    assert calls == []
    assert "already went out" in config.log_path(DAY).read_text(encoding="utf-8")


def test_force_re_runs_a_finished_day(temp_data, monkeypatch):
    calls = []
    _stub_stages(monkeypatch, calls)
    runner.run(DAY)
    calls.clear()
    assert runner.run(DAY, force=True) == runner.EXIT_OK
    assert calls == ["fetch", "brief", "voice"]


def test_a_dry_run_leaves_the_day_unfinished(temp_data, monkeypatch):
    monkeypatch.setattr(runner, "fetch_stage", lambda day, headless=True: runner.EXIT_OK)
    monkeypatch.setattr(runner, "brief_stage", lambda day: runner.EXIT_OK)
    monkeypatch.setattr(voice, "speak_brief",
                        lambda day, dry_run=False, on_log=None: {"sent": False})
    assert runner.run(DAY, dry_run=True) == runner.EXIT_OK
    assert voice.already_sent(DAY) is False


def test_a_login_wall_stops_the_run_with_exit_2_and_a_telegram_text(temp_data, monkeypatch):
    sent = []
    monkeypatch.setattr(xfetch, "fetch_day",
                        lambda *a, **k: (_ for _ in ()).throw(
                            xfetch.LoginWall("login wall at https://x.com/i/flow/login")))
    monkeypatch.setattr(runner.telegram, "notify_login_expired", lambda: sent.append(True))
    monkeypatch.setattr(runner, "brief_stage",
                        lambda day: (_ for _ in ()).throw(AssertionError("must not run")))

    assert runner.run(DAY) == runner.EXIT_BLOCKED
    assert sent == [True]
    log = config.log_path(DAY).read_text(encoding="utf-8")
    assert "blocked: login wall" in log
    assert "agentchirp login" in log
    assert voice.already_sent(DAY) is False


def test_a_captcha_is_treated_the_same_way(temp_data, monkeypatch):
    monkeypatch.setattr(xfetch, "fetch_day",
                        lambda *a, **k: (_ for _ in ()).throw(xfetch.Captcha("human check")))
    monkeypatch.setattr(runner.telegram, "notify_login_expired", lambda: None)
    assert runner.fetch_stage(DAY) == runner.EXIT_BLOCKED


def test_fetch_stage_reports_unresolved_handles(temp_data, monkeypatch):
    monkeypatch.setattr(xfetch, "fetch_day", lambda *a, **k: xfetch.FetchResult(
        payload={"date": DAY.isoformat(), "creators": []}, post_count=7, missing=["ghosthandle"]))
    assert runner.fetch_stage(DAY) == runner.EXIT_OK
    log = config.log_path(DAY).read_text(encoding="utf-8")
    assert "@ghosthandle" in log
    assert "saved 7 posts to x-2026-10-04.json" in log
    assert config.raw_path(DAY).exists()


def test_log_lines_are_dated_and_stage_tagged(temp_data):
    line = logs.log(DAY, "brief", "wrote something", echo=False)
    assert line.endswith("wrote something")
    assert " brief  " in line
    assert config.log_path(DAY).read_text(encoding="utf-8").strip() == line
