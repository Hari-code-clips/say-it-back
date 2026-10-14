"""Backend selection: client kwargs per model kind, Developer API vs Agent Platform, from env."""

from __future__ import annotations

import contextlib

import pytest
from google.adk.models import Gemini

from sayitback import backends
from sayitback.settings import ConfigError, Settings

PLATFORM = {"GOOGLE_GENAI_USE_ENTERPRISE": "true", "GOOGLE_CLOUD_PROJECT": "demo-proj"}


def kwargs(env: dict[str, str]) -> dict[str, dict]:
    s = Settings.from_env(env)
    return {k: backends.client_kwargs(k, s) for k in ("flash", "live", "tts")}


def test_default_is_the_developer_api_for_every_kind():
    for kind_kwargs in kwargs({}).values():
        assert kind_kwargs == {"enterprise": False}


def test_enterprise_switch_selects_agent_platform_with_project_and_locations():
    got = kwargs(PLATFORM)
    assert got["flash"] == {"enterprise": True, "location": "global", "project": "demo-proj"}
    assert got["tts"] == got["flash"]
    assert got["live"] == {"enterprise": True, "location": "us-central1", "project": "demo-proj"}


def test_locations_come_from_env():
    got = kwargs(
        {**PLATFORM, "GOOGLE_CLOUD_LOCATION": "asia-south1", "SIB_LIVE_LOCATION": "europe-west4"}
    )
    assert got["flash"]["location"] == "asia-south1"
    assert got["tts"]["location"] == "asia-south1"
    assert got["live"]["location"] == "europe-west4"


def test_without_a_project_none_is_passed_so_adc_or_metadata_decides():
    got = kwargs({"GOOGLE_GENAI_USE_ENTERPRISE": "1"})
    assert "project" not in got["flash"]


def test_legacy_vertexai_flag_still_works():
    assert (
        kwargs({"GOOGLE_GENAI_USE_VERTEXAI": "true", "GOOGLE_CLOUD_PROJECT": "p"})["flash"][
            "enterprise"
        ]
        is True
    )


def test_enterprise_wins_when_both_flags_conflict():
    got = kwargs({"GOOGLE_GENAI_USE_ENTERPRISE": "false", "GOOGLE_GENAI_USE_VERTEXAI": "true"})
    assert got["flash"] == {"enterprise": False}


def test_live_can_stay_on_the_developer_api_while_the_rest_moves():
    got = kwargs({**PLATFORM, "SIB_LIVE_BACKEND": "developer-api"})
    assert got["live"] == {"enterprise": False}
    assert got["flash"]["enterprise"] is True


def test_tts_can_stay_on_the_developer_api_while_the_rest_moves():
    got = kwargs({**PLATFORM, "SIB_TTS_BACKEND": "developer-api"})
    assert got["tts"] == {"enterprise": False}
    assert got["flash"]["enterprise"] is True and got["live"]["enterprise"] is True


def test_live_can_move_to_agent_platform_alone():
    got = kwargs({"SIB_LIVE_BACKEND": "agent-platform", "GOOGLE_CLOUD_PROJECT": "p"})
    assert got["live"] == {"enterprise": True, "location": "us-central1", "project": "p"}
    assert got["flash"] == {"enterprise": False}


def test_an_unknown_backend_name_is_a_config_error():
    with pytest.raises(ConfigError, match="SIB_LIVE_BACKEND"):
        Settings.from_env({"SIB_LIVE_BACKEND": "vertex"})


def test_health_reports_the_backend_per_kind():
    s = Settings.from_env({**PLATFORM, "SIB_TTS_BACKEND": "developer-api"})
    assert backends.backends(s) == {
        "flash": "agent-platform",
        "live": "agent-platform",
        "tts": "developer-api",
    }


def test_retry_once_with_backoff_on_429_and_5xx():
    opts = backends.retry_options(Settings(retry_attempts=2, retry_backoff_s=1.5))
    assert opts.attempts == 2  # the first call plus one retry
    assert opts.initial_delay == 1.5
    assert set(opts.http_status_codes) == {429, 500, 502, 503, 504}


def test_thinking_levels_for_gemini_3_8():
    assert backends.thinking_config("low").thinking_level.value == "LOW"
    assert backends.thinking_config("medium").thinking_level.value == "MEDIUM"


class TestRealClients:
    """Build the actual google-genai clients offline: nothing here sends a request."""

    @pytest.fixture(autouse=True)
    def _fake_key(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-real")

    def test_developer_api_flash_and_live(self):
        s = Settings()
        flash, live = backends.make_flash(s), backends.make_live(s)
        assert flash.api_client.vertexai is False
        assert live._live_api_client.vertexai is False
        assert flash.model == "gemini-3.8-flash" and live.model == "gemini-3.8-live"

    def test_agent_platform_flash_uses_the_global_endpoint_and_live_a_regional_one(self):
        s = Settings.from_env(PLATFORM)
        flash, live = backends.make_flash(s), backends.make_live(s)
        assert flash.api_client.vertexai is True
        assert flash.api_client._api_client.location == "global"
        assert (
            str(flash.api_client._api_client._http_options.base_url)
            == "https://aiplatform.googleapis.com/"
        )
        assert live._live_api_client.vertexai is True
        assert (
            live._live_api_client._api_client._http_options.base_url
            == "https://us-central1-aiplatform.googleapis.com/"
        )

    def test_the_project_reaches_the_client(self):
        client = backends.make_genai_client("flash", Settings.from_env(PLATFORM))
        assert client._api_client.project == "demo-proj"

    def test_a_kind_pinned_to_the_developer_api_ignores_the_global_enterprise_env(
        self, monkeypatch
    ):
        for name, value in PLATFORM.items():
            monkeypatch.setenv(name, value)
        s = Settings.from_env({**PLATFORM, "SIB_TTS_BACKEND": "developer-api"})
        assert backends.make_genai_client("tts", s).vertexai is False
        assert backends.make_genai_client("flash", s).vertexai is True


@pytest.mark.asyncio
async def test_live_gemini_signals_only_once_the_connection_is_open(monkeypatch):
    opened = []

    @contextlib.asynccontextmanager
    async def fake_connect(self, llm_request):
        yield "connection"

    monkeypatch.setattr(Gemini, "connect", fake_connect)
    live = backends.make_live(Settings(), on_connected=lambda: opened.append(True))
    async with live.connect(object()) as conn:
        assert conn == "connection"
        assert opened == [True]


@pytest.mark.asyncio
async def test_live_gemini_does_not_signal_when_connect_fails(monkeypatch):
    opened = []

    @contextlib.asynccontextmanager
    async def failing_connect(self, llm_request):
        raise ConnectionError("rejected")
        yield  # pragma: no cover

    monkeypatch.setattr(Gemini, "connect", failing_connect)
    live = backends.make_live(Settings(), on_connected=lambda: opened.append(True))
    with pytest.raises(ConnectionError):
        async with live.connect(object()):
            pass
    assert opened == []
