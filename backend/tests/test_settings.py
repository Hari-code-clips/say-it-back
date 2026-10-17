"""Settings from environment variables only (ARCHITECTURE.md, "Configuration")."""

from __future__ import annotations

from pathlib import Path

import pytest

from sayitback.settings import ConfigError, Settings


def test_defaults_match_the_configuration_table():
    s = Settings.from_env({})
    assert (s.flash_model, s.live_model, s.tts_model) == (
        "gemini-3.8-flash",
        "gemini-3.8-live",
        "gemini-3.8-flash-tts",
    )
    assert (s.live_voice, s.tts_voice) == ("Kore", "Kore")
    assert (s.judge_passes, s.covered_min_confidence) == (2, 0.75)
    assert (s.store, s.rate_limit_per_min, s.keep_audio) == ("local", 30, False)
    assert s.allowed_origins == ("http://localhost:5173",)
    assert (s.cloud_location, s.live_location) == ("global", "us-central1")
    assert (s.trace_to_cloud, s.bq_dataset, s.webhook_url, s.public_ws_base) == (False, "", "", "")
    assert s.eval_dir == (Path(__file__).resolve().parents[2] / "eval").resolve()


def test_every_variable_is_read():
    s = Settings.from_env(
        {
            "SIB_FLASH_MODEL": "f", "SIB_LIVE_MODEL": "l", "SIB_TTS_MODEL": "t", "SIB_LIVE_VOICE": "Puck",
            "SIB_TTS_VOICE": "Charon", "SIB_JUDGE_PASSES": "1", "SIB_COVERED_MIN_CONFIDENCE": "0.9",
            "SIB_STORE": "firestore", "SIB_ALLOWED_ORIGINS": "https://a.web.app/, https://b.app",
            "SIB_PUBLIC_WS_BASE": "wss://api.run.app/", "SIB_TRACE_TO_CLOUD": "true",
            "SIB_BQ_DATASET": "p.d", "SIB_WEBHOOK_URL": "https://chat.googleapis.com/x",
            "SIB_EVAL_DIR": "/tmp/evalset", "SIB_RATE_LIMIT_PER_MIN": "5", "SIB_KEEP_AUDIO": "1",
            "SIB_LIVE_TURN_TAKING": "auto",
        }
    )  # fmt: skip
    assert (s.flash_model, s.live_model, s.tts_model, s.live_voice, s.tts_voice) == (
        "f",
        "l",
        "t",
        "Puck",
        "Charon",
    )
    assert (s.judge_passes, s.covered_min_confidence, s.store) == (1, 0.9, "firestore")
    assert s.allowed_origins == ("https://a.web.app", "https://b.app")
    assert s.public_ws_base == "wss://api.run.app"
    assert (s.trace_to_cloud, s.bq_dataset, s.rate_limit_per_min, s.keep_audio) == (
        True,
        "p.d",
        5,
        True,
    )
    assert s.live_turn_taking == "auto"


def test_thinking_levels_default_and_override():
    s = Settings.from_env({"SIB_THINKING_JUDGE_A": "high"})
    assert s.thinking["judge_a"] == "high"
    assert s.thinking["blind_transcriber"] == "low"
    assert "minimal" not in s.thinking.values()  # Gemini 3.8 Flash rejects it


@pytest.mark.parametrize(
    "env",
    [
        {"SIB_THINKING_JUDGE_A": "minimal"},
        {"SIB_JUDGE_PASSES": "3"},
        {"SIB_COVERED_MIN_CONFIDENCE": "1.5"},
        {"SIB_COVERED_MIN_CONFIDENCE": "high"},
        {"SIB_STORE": "sqlite"},
        {"SIB_TRACE_TO_CLOUD": "maybe"},
        {"SIB_RATE_LIMIT_PER_MIN": "0"},
        {"SIB_LIVE_TURN_TAKING": "vad"},
    ],
)
def test_invalid_values_fail_at_start_up(env):
    with pytest.raises(ConfigError):
        Settings.from_env(env)


def test_limits_match_api_md():
    s = Settings()
    assert s.max_audio_bytes == 3 * 1024 * 1024 and s.max_audio_files == 3
    assert (s.max_instruction_chars, s.max_custom_sop_chars, s.max_tts_chars) == (1000, 8000, 600)
    assert (s.ticket_ttl_s, s.max_tickets_per_round, s.max_rounds) == (120, 2, 3)
    assert (s.ws_first_message_s, s.ws_max_session_s, s.ws_max_window_s) == (5.0, 600.0, 35.0)
    assert s.ws_first_cue_s == 30.0
    assert (s.ws_idle_s, s.ws_max_binary_bytes) == (60.0, 8192)
    assert (s.min_steps, s.max_steps, s.min_clip_seconds) == (1, 6, 0.8)
    # Daily cap: what the model may write (script limits, output ceiling)
    assert (s.max_sentences_per_step, s.max_line_chars, s.max_output_tokens) == (3, 160, 8192)


COST_BOUNDS = {
    "SIB_MAX_SENTENCES_PER_STEP": "max_sentences_per_step",
    "SIB_MAX_LINE_CHARS": "max_line_chars",
    "SIB_MAX_OUTPUT_TOKENS": "max_output_tokens",
}


def test_the_cost_bounds_default_and_are_read_from_the_environment():
    assert Settings.from_env({}).max_output_tokens == 8192
    s = Settings.from_env(
        {
            "SIB_MAX_SENTENCES_PER_STEP": " 2 ",
            "SIB_MAX_LINE_CHARS": "120",
            "SIB_MAX_OUTPUT_TOKENS": "4096",
        }
    )
    assert (s.max_sentences_per_step, s.max_line_chars, s.max_output_tokens) == (2, 120, 4096)


@pytest.mark.parametrize(("name", "valid"), [
    ("SIB_MAX_SENTENCES_PER_STEP", "1"),
    ("SIB_MAX_LINE_CHARS", "1"),
    ("SIB_MAX_OUTPUT_TOKENS", "1024"),  # the floor
    ("SIB_MAX_OUTPUT_TOKENS", "65536"),  # the model's own limit: allowed, not second-guessed
])  # fmt: skip
def test_the_lowest_allowed_values_are_accepted(name, valid):
    assert getattr(Settings.from_env({name: valid}), COST_BOUNDS[name]) == int(valid)


@pytest.mark.parametrize("name", list(COST_BOUNDS))
@pytest.mark.parametrize("bad", ["0", "-1", "abc", "1.5", "1e3", "8192 tokens"])
def test_a_cost_bound_that_is_not_a_positive_integer_fails_at_start_up(name, bad):
    with pytest.raises(ConfigError, match=name):
        Settings.from_env({name: bad})


@pytest.mark.parametrize("bad", ["1", "512", "1023"])
def test_an_output_ceiling_below_1024_fails_at_start_up(bad):
    """A ceiling that low would cut off ordinary replies, thinking included."""
    with pytest.raises(ConfigError, match="SIB_MAX_OUTPUT_TOKENS must be at least 1024"):
        Settings.from_env({"SIB_MAX_OUTPUT_TOKENS": bad})


# API v0.4 -------------------------------------------------------------------------------------

V04 = {
    "SIB_DELIVERY_MIN_SIMILARITY": ("delivery_min_similarity", 0.8, "0.9", 0.9),
    "SIB_DELIVERY_MIN_SCRIPT_SHARE": ("delivery_min_script_share", 0.7, "0.5", 0.5),
    "SIB_REPLY_MAX_CHARS": ("reply_max_chars", 60, "80", 80),
    "SIB_MAX_HAZARDS": ("max_hazards", 5, "2", 2),
    "SIB_JUDGE_B_MODEL": ("judge_b_model", "gemini-3.1-flash-lite", "m-lite", "m-lite"),
    "SIB_WEBHOOK_SECRET": ("webhook_secret", "", "k", "k"),
    "SIB_PHASE_TIMEOUT_S": ("phase_timeout_s", 110.0, "30", 30.0),
    "SIB_REQUEST_TIMEOUT_S": ("request_timeout_s", 120.0, "40", 40.0),
}


@pytest.mark.parametrize("name", list(V04))
def test_the_v04_settings_default_and_are_read_from_the_environment(name):
    field, default, raw, value = V04[name]
    assert getattr(Settings.from_env({}), field) == default == getattr(Settings(), field)
    assert getattr(Settings.from_env({name: raw}), field) == value


def test_the_hazard_report_has_its_own_thinking_level():
    assert Settings.from_env({}).thinking["hazard_report"] == "low"
    assert (
        Settings.from_env({"SIB_THINKING_HAZARD_REPORT": "high"}).thinking["hazard_report"]
        == "high"
    )
    with pytest.raises(ConfigError, match="SIB_THINKING_HAZARD_REPORT"):
        Settings.from_env({"SIB_THINKING_HAZARD_REPORT": "minimal"})


@pytest.mark.parametrize(
    "env",
    [
        {"SIB_DELIVERY_MIN_SIMILARITY": "1.5"},
        {"SIB_DELIVERY_MIN_SIMILARITY": "high"},
        {"SIB_DELIVERY_MIN_SCRIPT_SHARE": "-0.1"},
        {"SIB_REPLY_MAX_CHARS": "0"},
        {"SIB_REPLY_MAX_CHARS": "sixty"},
        {"SIB_MAX_HAZARDS": "0"},
        {"SIB_MAX_HAZARDS": "2.5"},
        {"SIB_PHASE_TIMEOUT_S": "0"},
        {"SIB_REQUEST_TIMEOUT_S": "-5"},
        {"SIB_WEBHOOK_URL": "not a url"},
        {
            "SIB_WEBHOOK_URL": "https://a.example,https://b.example,https://c.example,https://d.example"
        },
    ],
)
def test_invalid_v04_values_fail_at_start_up(env):
    with pytest.raises(ConfigError):
        Settings.from_env(env)


def test_the_extractor_thinks_low_by_default():
    """Real Agent Platform runs on 15 Oct 2026 (lifting-zone, the sample instruction): at `low` the
    extractor flagged the SOP-only tag-line step in 3 of 3 runs, at `medium` in 0 of 3, and took no
    longer. The flagged step is the demo's "Not in your briefing" moment, so low is the default."""
    from sayitback.settings import DEFAULT_THINKING

    assert DEFAULT_THINKING["extract_steps"] == "low"
    assert Settings.from_env({}).thinking["extract_steps"] == "low"


def test_the_judges_think_low_by_default():
    """The 15 Oct paid eval (58 answers, eval/reports/2026-10-15-paid-judges-*.md): at low and at medium,
    0 false passes of 68 and 87.5% exact; low passed 39 of 44 correct answers (medium 38), and is faster."""
    from sayitback.settings import DEFAULT_THINKING

    assert DEFAULT_THINKING["judge_a"] == DEFAULT_THINKING["judge_b"] == "low"
