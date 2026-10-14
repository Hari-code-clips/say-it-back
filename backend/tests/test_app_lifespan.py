"""App start-up: Cloud Trace is wired only when SIB_TRACE_TO_CLOUD is on."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.helpers import make_app


def test_trace_export_is_set_up_at_start_up_when_enabled(settings, monkeypatch):
    calls = []
    monkeypatch.setattr("sayitback.main.setup_cloud_trace", lambda: calls.append("trace") or True)
    app, *_ = make_app(settings.with_overrides(trace_to_cloud=True))
    with TestClient(app):  # entering the context runs the lifespan
        pass
    assert calls == ["trace"]


def test_nothing_is_exported_by_default(settings, monkeypatch):
    calls = []
    monkeypatch.setattr("sayitback.main.setup_cloud_trace", lambda: calls.append("trace") or True)
    app, *_ = make_app(settings)
    with TestClient(app):
        pass
    assert calls == []
