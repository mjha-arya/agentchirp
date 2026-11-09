"""Segment timing, markdown -> spoken text, and the prompt we hand to `claude -p`."""
import pytest

from agentchirp import brief, config


def test_full_plan_matches_the_spec_lengths():
    assert [(s.key, s.seconds) for s in brief.FULL_PLAN] == [
        ("intro", 5), ("top_trend", 30), ("quick_hits", 20),
        ("second_trend", 15), ("deep_dive", 15), ("outro", 5)]
    assert brief.plan_seconds(brief.FULL_PLAN) == 90   # Manish, 2026-10-05


def test_word_targets_follow_150_words_per_minute():
    assert config.WORDS_PER_MINUTE == 150
    words = {s.key: s.words for s in brief.FULL_PLAN}
    assert words == {"intro": 12, "top_trend": 75, "quick_hits": 50,
                     "second_trend": 38, "deep_dive": 38, "outro": 12}
    assert sum(words.values()) == 225


def test_spoken_lengths_read_naturally():
    lengths = [s.spoken_length for s in brief.FULL_PLAN]
    assert lengths == ["5 s", "30 s", "20 s", "15 s", "15 s", "5 s"]


def test_light_plan_fits_the_60_to_90_second_window():
    total = brief.plan_seconds(brief.LIGHT_PLAN)
    assert 60 <= total <= 90
    assert brief.plan(light=True) is brief.LIGHT_PLAN
    assert brief.plan(light=False) is brief.FULL_PLAN


def test_estimate_seconds_is_the_inverse_of_the_word_target():
    assert brief.estimate_seconds(" ".join(["word"] * 150)) == pytest.approx(60.0)
    assert brief.estimate_seconds("") == 0.0


def test_light_day_threshold(sample_payload, light_payload):
    assert brief.count_posts(sample_payload) == 12
    assert brief.is_light_day(sample_payload) is False
    assert brief.count_posts(light_payload) == 1
    assert brief.is_light_day(light_payload) is True


def test_spoken_text_drops_everything_the_voice_should_not_say():
    markdown = (
        "# AgentChirp brief — 2026-10-04\n\n"
        "- Posts: 11 from 8 creators\n"
        "- Plan: full day, 600 s target\n\n"
        "## Intro\n\n"
        "Good morning, it is the fourth of October.\n\n"
        "## Quick hits\n\n"
        "- **Simon Willison** shipped a plugin, see https://example.com/x\n"
        "- _swyx_ called it `consolidation`\n\n"
        "---\n"
        "> a note to the reader\n"
        "```python\nprint('not spoken')\n```\n")
    spoken = brief.spoken_text(markdown)
    assert spoken.startswith("Good morning")
    for unwanted in ("AgentChirp brief", "Posts: 11", "Intro", "Quick hits", "http",
                     "**", "`", "print(", "a note to the reader", "---"):
        assert unwanted not in spoken
    assert "Simon Willison shipped a plugin, see" in spoken
    assert "swyx called it consolidation" in spoken


def test_spoken_text_keeps_a_heading_only_script_intact():
    assert brief.spoken_text("## Intro\n\nHello there.\n") == "Hello there."
    assert brief.spoken_text("Plain text, no headings.") == "Plain text, no headings."


def test_prompt_carries_the_rules_the_spec_demands(sample_payload):
    prompt = brief.build_prompt(sample_payload)
    for segment in brief.FULL_PLAN:
        assert f"## {segment.title}" in prompt
        assert f"{segment.words} words" in prompt
    assert "Name the creator behind every single point" in prompt
    assert "agentic engineering" in prompt
    assert "90 seconds total" in prompt
    assert "Do not invent posts" in prompt
    # every creator with posts is quoted, and their posts come with engagement numbers
    assert "François Chollet (@fchollet, academics)" in prompt
    assert "Riley Brown (@rileybrown, new)" in prompt
    assert "7420 likes, 1100 reposts, 330 replies" in prompt
    assert "fallback: latest posts" in prompt          # Wooldridge entry
    assert "Percy Liang" in prompt and "nothing usable" in prompt


def test_light_prompt_says_out_loud_that_it_is_quiet(light_payload):
    prompt = brief.build_prompt(light_payload)
    assert "LIGHT day" in prompt
    assert "60 seconds" in prompt
    assert "## Deep dive" not in prompt


def test_long_posts_are_trimmed_before_they_reach_the_prompt():
    payload = {"date": "2026-10-04", "creators": [
        {"name": "Verbose", "handle": "verbose", "category": "new", "status": "ok",
         "posts": [{"text": "x" * 2000, "time": "2026-10-04T01:00:00Z",
                    "likes": 1, "reposts": 1, "replies": 1}]}]}
    prompt = brief.build_prompt(payload)
    assert "x" * brief.MAX_POST_CHARS in prompt
    assert "x" * (brief.MAX_POST_CHARS + 50) not in prompt
    assert "[…]" in prompt


def test_tidy_strips_preamble_and_insists_on_every_segment():
    good = "Sure, here you go!\n\n" + "\n\n".join(
        f"## {s.title}\n\nSome words." for s in brief.FULL_PLAN)
    tidied = brief._tidy(good, brief.FULL_PLAN)
    assert tidied.startswith("## Intro")
    assert "Sure, here you go" not in tidied

    with pytest.raises(RuntimeError, match="Outro"):
        brief._tidy("## Intro\n\nOnly one section.", brief.FULL_PLAN)


def test_render_puts_a_readable_header_above_the_script(sample_payload):
    script = "\n\n".join(f"## {s.title}\n\n" + " ".join(["word"] * s.words)
                         for s in brief.FULL_PLAN)
    rendered = brief.render(sample_payload, script, brief.FULL_PLAN)
    assert rendered.startswith("# AgentChirp brief — 2026-10-04")
    assert "- Posts: 12 from 8 creators" in rendered
    assert "- Plan: full day, 90 s target" in rendered
    assert "Estimated spoken length: 1.5 min (225 words at 150 wpm)" in rendered
    assert brief.spoken_text(rendered).startswith("word")


def test_write_brief_uses_claude_and_an_explicit_input(tmp_path, monkeypatch, temp_data):
    from datetime import date
    seen = {}

    def fake_claude(prompt, timeout_s=0):
        seen["prompt"] = prompt
        return "\n\n".join(f"## {s.title}\n\nWords for {s.title}." for s in brief.FULL_PLAN)

    monkeypatch.setattr(brief, "call_claude", fake_claude)
    fixture = config.ROOT / "tests" / "fixtures" / "x-sample.json"
    out = brief.write_brief(date(2026, 10, 4), input_path=fixture, on_log=lambda m: None)
    assert out == config.brief_path(date(2026, 10, 4))
    assert "Words for Deep dive." in out.read_text(encoding="utf-8")
    assert "Riley Brown" in seen["prompt"]
