"""Caption building and the --dry-run promise, with no audio and no network."""
from datetime import date

from agentchirp import config, telegram, voice

DAY = date(2026, 10, 4)

BRIEF = (
    "# AgentChirp brief — 2026-10-04\n\n"
    "- Posts: 11 from 8 creators\n"
    "- Plan: full day, 600 s target\n\n"
    "## Intro\n\nGood morning.\n\n## Outro\n\nSee you tomorrow.\n")

LIGHT_BRIEF = BRIEF.replace("- Plan: full day, 600 s target",
                            "- Plan: light day, 75 s target").replace("Posts: 11 from 8", "Posts: 1 from 1")


def test_caption_is_one_line():
    caption = voice.caption_for(DAY, 592.4, posts=11)
    assert caption == "AgentChirp 2026-10-04 · ~10 min · 11 posts"
    assert "\n" not in caption


def test_caption_flags_a_quiet_day_and_never_rounds_to_zero():
    assert voice.caption_for(DAY, 72.0, posts=1, light=True) == \
        "AgentChirp 2026-10-04 · ~1 min · 1 posts · quiet day"
    assert "~1 min" in voice.caption_for(DAY, 4.0)


def test_brief_meta_reads_the_header():
    assert voice._brief_meta(BRIEF) == (11, False)
    assert voice._brief_meta(LIGHT_BRIEF) == (1, True)
    assert voice._brief_meta("## Intro\n\nno header at all") == (None, False)


def _stub_audio(monkeypatch):
    def fake_synth(text, mp3, voice_name=None):
        mp3.parent.mkdir(parents=True, exist_ok=True)
        mp3.write_bytes(b"fake-mp3")
        return mp3

    def fake_opus(mp3, ogg):
        ogg.parent.mkdir(parents=True, exist_ok=True)
        ogg.write_bytes(b"fake-ogg" * 200)
        return ogg

    monkeypatch.setattr(voice, "synthesize", fake_synth)
    monkeypatch.setattr(voice, "to_opus", fake_opus)
    monkeypatch.setattr(voice, "probe_duration", lambda path: None)


def test_dry_run_writes_audio_but_sends_nothing(temp_data, monkeypatch, tmp_path):
    _stub_audio(monkeypatch)
    monkeypatch.setattr(telegram, "send_voice",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not send")))
    brief_file = tmp_path / "brief.md"
    brief_file.write_text(BRIEF, encoding="utf-8")

    info = voice.speak_brief(DAY, dry_run=True, input_path=brief_file, on_log=lambda m: None)
    assert info["sent"] is False
    assert info["ogg"] == config.audio_path(DAY, "ogg")
    assert info["ogg"].exists() and config.audio_path(DAY, "mp3").exists()
    assert info["caption"].startswith("AgentChirp 2026-10-04")
    assert voice.already_sent(DAY) is False


def test_a_real_send_passes_caption_and_duration(temp_data, monkeypatch, tmp_path):
    _stub_audio(monkeypatch)
    calls = {}
    monkeypatch.setattr(voice.telegram, "send_voice",
                        lambda ogg, caption, duration_s=None: calls.update(
                            ogg=ogg, caption=caption, duration_s=duration_s))
    brief_file = tmp_path / "brief.md"
    brief_file.write_text(BRIEF, encoding="utf-8")

    info = voice.speak_brief(DAY, input_path=brief_file, on_log=lambda m: None)
    assert info["sent"] is True
    assert calls["ogg"] == config.audio_path(DAY, "ogg")
    assert calls["caption"] == info["caption"]
    assert calls["duration_s"] == round(info["seconds"])

    marker = voice.mark_sent(DAY, info)
    assert voice.already_sent(DAY) is True
    assert '"date": "2026-10-04"' in marker.read_text(encoding="utf-8")


def test_voice_defaults_to_a_natural_english_voice():
    assert config.VOICE == "en-GB-RyanNeural"
