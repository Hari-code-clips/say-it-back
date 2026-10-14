"""Shared fixtures. Every fixture is offline: fake models, a temp store, no environment."""

from __future__ import annotations

import faulthandler
import socket

import pytest
from fastapi.testclient import TestClient

from sayitback.settings import Settings
from tests.fakes import FakeTtsClient, Scenario, fake_runtime
from tests.helpers import api_client, drive_to_round, make_app


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """No ambient Google or SIB variable may change a test (the developer's shell has keys)."""
    import os

    for name in list(os.environ):
        if name.startswith(("SIB_", "GOOGLE_", "GEMINI_")):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        data_dir=tmp_path / ".data",
        eval_dir=tmp_path / "eval",
        retry_backoff_s=0.0,
        ws_first_message_s=2.0,
        ws_idle_s=5.0,
        live_connect_timeout_s=3.0,
        live_drain_s=0.5,
        rate_limit_per_min=1000,
    )


@pytest.fixture
def client(settings) -> TestClient:
    """The API over fakes (models and TTS), no store or webhook customisation."""
    app, *_ = make_app(settings, tts_client=FakeTtsClient())
    return api_client(app)


@pytest.fixture
def briefing(client) -> str:
    """The id of a briefing driven to round 1."""
    return drive_to_round(client)[0]


@pytest.fixture
def scenario() -> Scenario:
    return Scenario()


@pytest.fixture
def fake_rt(settings, scenario):
    runtime, llm = fake_runtime(scenario, settings)
    return runtime, llm


@pytest.fixture(autouse=True)
def hang_guard():
    """A test that hangs (a socket waiting forever) dumps its stack and exits instead of blocking."""
    faulthandler.dump_traceback_later(90, exit=True)
    yield
    faulthandler.cancel_dump_traceback_later()


LOCAL = {"127.0.0.1", "::1", "localhost", "testserver", "0.0.0.0", ""}  # noqa: S104


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """The suite must pass with no network: any connection or DNS lookup outside loopback fails."""
    real_connect, real_lookup = socket.socket.connect, socket.getaddrinfo

    def guarded_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if self.family != socket.AF_UNIX and host not in LOCAL:
            raise RuntimeError(f"network access is blocked in tests: {host!r}")
        return real_connect(self, address, *args, **kwargs)

    def guarded_lookup(host, *args, **kwargs):
        if host not in LOCAL and host is not None:
            raise RuntimeError(f"DNS lookup is blocked in tests: {host!r}")
        return real_lookup(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_lookup)
