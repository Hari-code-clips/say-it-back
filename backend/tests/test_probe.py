"""The model probe (`uv run python -m sayitback.probe`, plan v0.5 Task 4): one tiny call per
configured model, one line each, exit 0 only when every model answers. Offline: the google-genai
clients are fakes injected through `client_factory`; nothing here sends a request."""

from __future__ import annotations

import asyncio
import contextlib
import re
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors

from sayitback import probe
from sayitback.settings import Settings

PROJECT_NUMBER = "123456789012"
API_KEY = "AIzaFAKEKEYnotreal0000000000000000000"
PLATFORM = Settings(agent_platform=True, cloud_project=PROJECT_NUMBER)
OK_LINE = re.compile(r"^OK (\S+) (\S+) (\S+) \d+ms$")
FAIL_LINE = re.compile(r"^FAIL (\S+) (\S+) (\S+) (\S+)$")


def api_error(code: int, status: str = "") -> errors.APIError:
    body = {"error": {"code": code, "status": status,
                      "message": f"projects/{PROJECT_NUMBER} key={API_KEY} refused"}}  # fmt: skip
    cls = errors.ClientError if 400 <= code < 500 else errors.ServerError
    return cls(code, body, None)


class FakeClients:
    """`client_factory(kind, settings)`: records where each client was built and every call.
    `fail` maps a model id to the exception its call raises, or "hang"."""

    def __init__(self, fail: dict[str, object] | None = None) -> None:
        self.fail = fail or {}
        self.built: list[tuple[str, str]] = []
        self.calls: list[tuple[str, str, object]] = []

    def __call__(self, kind: str, s: Settings) -> SimpleNamespace:
        location = s.live_location if kind == "live" else (
            s.tts_location_id if kind == "tts" else s.cloud_location
        )  # fmt: skip
        self.built.append((kind, location))
        return SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(generate_content=self._generate),
                live=SimpleNamespace(connect=self._connect),
            )
        )

    async def _outcome(self, model: str) -> None:
        failure = self.fail.get(model)
        if failure == "hang":
            await asyncio.sleep(60)
        elif isinstance(failure, BaseException):
            raise failure

    async def _generate(self, *, model, contents, config):
        self.calls.append(("generate", model, config))
        await self._outcome(model)
        return SimpleNamespace(text="OK")

    @contextlib.asynccontextmanager
    async def _connect(self, *, model, config):
        self.calls.append(("live", model, config))
        await self._outcome(model)
        yield SimpleNamespace()


def run(argv=(), settings=PLATFORM, clients=None, timeout_s=probe.PROBE_TIMEOUT_S, capsys=None):
    clients = clients or FakeClients()
    code = probe.main(list(argv), settings=settings, client_factory=clients, timeout_s=timeout_s)
    out = capsys.readouterr() if capsys else None
    return code, (out.out.splitlines() if out else []), (out.err if out else ""), clients


class TestClassifyError:
    @pytest.mark.parametrize(
        ("exc", "reason"),
        [
            (api_error(404, "NOT_FOUND"), "not_found"),
            (api_error(403, "PERMISSION_DENIED"), "permission"),
            (api_error(401, "UNAUTHENTICATED"), "permission"),
            (api_error(429, "RESOURCE_EXHAUSTED"), "quota"),
            (api_error(400, "INVALID_ARGUMENT"), "bad_request"),
            (api_error(500, "INTERNAL"), "other"),
            (TimeoutError(), "timeout"),
            (httpx.ReadTimeout("slow"), "timeout"),
            (ValueError("no key"), "other"),
        ],
    )
    def test_http_errors_and_timeouts(self, exc, reason):
        assert probe.classify_error(exc) == reason

    def test_a_live_close_frame_is_read_by_its_reason(self):
        """Live reports a refused setup as a websocket close (code 1008 or 1007), not an HTTP
        status: google-genai raises APIError(close code, reason text)."""
        not_found = errors.APIError(1008, "models/gemini-x is not found for API version v1beta")
        denied = errors.APIError(1008, "Permission denied on resource project")
        invalid = errors.APIError(1007, "Request contains an invalid argument.")
        assert probe.classify_error(not_found) == "not_found"
        assert probe.classify_error(denied) == "permission"
        assert probe.classify_error(invalid) == "bad_request"

    def test_a_handshake_refused_with_an_http_status(self):
        response = SimpleNamespace(status_code=404)
        exc = type("InvalidStatus", (Exception,), {})("server rejected WebSocket connection")
        exc.response = response
        assert probe.classify_error(exc) == "not_found"


class TestMain:
    def test_every_model_answers_exit_0(self, capsys):
        code, lines, _, clients = run(capsys=capsys)
        assert code == 0
        assert [OK_LINE.match(ln).group(1) for ln in lines] == ["flash", "judge_b", "tts", "live"]
        models = [OK_LINE.match(ln).group(2) for ln in lines]
        assert models == ["gemini-3.8-flash", "gemini-3.1-flash-lite", "gemini-3.8-flash-tts",
                          "gemini-3.8-live"]  # fmt: skip
        locations = [OK_LINE.match(ln).group(3) for ln in lines]
        assert locations == ["global", "global", "global", "us-central1"]

    def test_one_failure_prints_its_reason_and_exits_1(self, capsys):
        clients = FakeClients({"gemini-3.8-flash-tts": api_error(404, "NOT_FOUND")})
        code, lines, _, _ = run(clients=clients, capsys=capsys)
        assert code == 1
        fails = [FAIL_LINE.match(ln).groups() for ln in lines if ln.startswith("FAIL")]
        assert fails == [("tts", "gemini-3.8-flash-tts", "global", "not_found")]
        assert sum(ln.startswith("OK ") for ln in lines) == 3

    def test_a_hanging_model_times_out(self, capsys):
        clients = FakeClients({"gemini-3.8-live": "hang"})
        code, lines, _, _ = run(clients=clients, timeout_s=0.2, capsys=capsys)
        assert code == 1
        assert "FAIL live gemini-3.8-live us-central1 timeout" in lines

    def test_judge_b_is_skipped_when_it_is_the_flash_model(self, capsys):
        _, lines, _, _ = run(settings=PLATFORM.with_overrides(judge_b_model=""), capsys=capsys)
        assert [ln.split()[1] for ln in lines] == ["flash", "tts", "live"]

    def test_tts_runs_at_its_own_location_and_at_each_also_location(self, capsys):
        s = PLATFORM.with_overrides(tts_location="europe-west4")
        code, lines, _, clients = run(["--also-location", "us-central1"], settings=s, capsys=capsys)
        assert code == 0
        tts = [ln.split()[3] for ln in lines if ln.split()[1] == "tts"]
        assert tts == ["europe-west4", "us-central1"]
        assert ("tts", "us-central1") in clients.built and ("flash", "global") in clients.built

    def test_also_location_is_skipped_off_agent_platform(self, capsys):
        code, lines, err, _ = run(["--also-location", "us-central1"], settings=Settings(),
                                  capsys=capsys)  # fmt: skip
        assert code == 0
        assert [ln.split()[3] for ln in lines] == ["developer-api"] * 4
        assert "--also-location" in err

    def test_the_flash_probe_follows_the_gemini_3_rules(self, capsys):
        _, _, _, clients = run(capsys=capsys)
        configs = [c for kind, model, c in clients.calls if model == "gemini-3.8-flash"]
        assert len(configs) == 1
        config = configs[0]
        assert config.max_output_tokens == 64
        assert config.thinking_config.thinking_level.value == "MEDIUM"
        assert (config.temperature, config.top_p, config.top_k) == (None, None, None)

    def test_tts_asks_for_audio_and_live_for_an_audio_session(self, capsys):
        _, _, _, clients = run(capsys=capsys)
        tts = next(c for kind, model, c in clients.calls if model == "gemini-3.8-flash-tts")
        assert tts.response_modalities == ["AUDIO"]
        live = next(c for kind, model, c in clients.calls if kind == "live")
        assert live == {"response_modalities": ["AUDIO"]}

    def test_no_key_or_project_number_is_ever_printed(self, capsys, monkeypatch):
        monkeypatch.setenv("GOOGLE_API_KEY", API_KEY)
        failing = {m: api_error(403, "PERMISSION_DENIED") for m in
                   ("gemini-3.8-flash", "gemini-3.1-flash-lite", "gemini-3.8-flash-tts")}  # fmt: skip
        failing["gemini-3.8-live"] = RuntimeError(f"projects/{PROJECT_NUMBER} {API_KEY}")
        code, lines, err, _ = run(clients=FakeClients(failing), capsys=capsys)
        assert code == 1
        printed = "\n".join(lines) + err
        assert PROJECT_NUMBER not in printed and API_KEY not in printed
        assert "FAIL live gemini-3.8-live us-central1 other" in lines

    def test_a_client_that_cannot_be_built_is_a_failure_not_a_crash(self, capsys):
        def factory(kind, s):
            raise ValueError(f"Missing key inputs argument {API_KEY}")

        code, lines, err, _ = run(clients=factory, capsys=capsys)
        assert code == 1 and len(lines) == 4
        assert all(ln.startswith("FAIL ") and ln.endswith(" other") for ln in lines)
        assert API_KEY not in "\n".join(lines) + err


def test_the_probe_sends_exactly_the_services_tts_config(settings):
    """The probe once built its own TTS config with max_output_tokens and failed where the service
    would also fail, but for its own reason; it now uses tts.Tts.config_for, so the two cannot drift."""
    from sayitback.tts import Tts

    assert probe.tts_config(settings) == Tts.config_for(settings)
    assert probe.tts_config(settings).max_output_tokens is None
