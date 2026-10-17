"""Unhandled errors reach Cloud Error Reporting (observability.report_error) carrying nothing the
request held: one JSON line on stderr with the stack frames and the exception's type, never its
message, so never a device key, its hash, a client address, a token or a request body. uvicorn's own
traceback of the same error, which prints the message, is dropped (ServerTracebackFilter)."""

from __future__ import annotations

import json
import logging

import pytest
from pydantic import BaseModel, ValidationError

from sayitback import __version__
from sayitback import observability as obs
from sayitback.caller import owner_hash
from sayitback.service import Briefings
from tests.helpers import DEVICE, PANEL, api_client, error_of, make_app

ADDRESS = "203.0.113.9"
BODY_TEXT = "BODY-TEXT-OF-THE-INSTRUCTION"
TOKEN = "live-ticket-0123456789abcdefghij"
SECRETS = (DEVICE, owner_hash(DEVICE), ADDRESS, BODY_TEXT, TOKEN)
EVENT_TYPE = "type.googleapis.com/google.devtools.clouderrorreporting.v1beta1.ReportedErrorEvent"


def reports(err: str) -> list[dict]:
    """The Error Reporting entries among captured stderr lines."""
    entries = [json.loads(line) for line in err.splitlines() if line.startswith("{")]
    return [e for e in entries if e.get("@type") == EVENT_TYPE]


def boom() -> None:
    raise RuntimeError(" ".join(SECRETS))


def raised(fn) -> BaseException:
    try:
        fn()
    except Exception as exc:
        return exc
    raise AssertionError("did not raise")


class Body(BaseModel):
    n: int


class TestTheReport:
    def test_it_is_a_reported_error_event_naming_the_service_and_revision(self, monkeypatch):
        monkeypatch.setenv("K_SERVICE", "say-it-back-api")
        monkeypatch.setenv("K_REVISION", "say-it-back-api-00007-xyz")
        entry = obs.error_report(raised(boom))
        assert entry["severity"] == "ERROR" and entry["@type"] == EVENT_TYPE
        assert entry["serviceContext"] == {
            "service": "say-it-back-api",
            "version": "say-it-back-api-00007-xyz",
        }
        assert set(entry) == {"severity", "@type", "message", "serviceContext"}

    def test_off_cloud_run_it_names_the_app_and_its_version(self, monkeypatch):
        monkeypatch.delenv("K_SERVICE", raising=False)
        monkeypatch.delenv("K_REVISION", raising=False)
        entry = obs.error_report(raised(boom))
        assert entry["serviceContext"] == {"service": "say-it-back-api", "version": __version__}

    def test_the_message_is_a_python_stack_trace_without_the_exception_text(self):
        trace = obs.error_report(raised(boom))["message"]
        assert trace.startswith("Traceback (most recent call last):\n  File ")
        assert ", in boom\n" in trace and 'raise RuntimeError(" ".join(SECRETS))' in trace
        assert trace.endswith("\nRuntimeError")
        for secret in SECRETS:
            assert secret not in trace, secret

    def test_a_validation_error_is_named_by_type_without_the_input_it_echoes(self):
        exc = raised(lambda: Body(n=BODY_TEXT))
        assert isinstance(exc, ValidationError) and BODY_TEXT in str(exc)  # what it would leak
        trace = obs.error_trace(exc)
        assert trace.endswith(".ValidationError") and BODY_TEXT not in trace

    def test_a_cause_adds_no_text(self):
        def chained() -> None:
            try:
                Body(n=BODY_TEXT)
            except ValidationError as inner:
                raise KeyError(DEVICE) from inner

        trace = obs.error_trace(raised(chained))
        assert trace.endswith("\nKeyError")
        assert BODY_TEXT not in trace and DEVICE not in trace

    def test_it_is_one_json_line_on_stderr(self, capsys):
        obs.report_error(raised(boom))
        err = capsys.readouterr().err
        assert err.endswith("\n") and err.count("\n") == 1
        (entry,) = reports(err)
        assert entry["message"].endswith("\nRuntimeError")


class TestThroughTheApp:
    def test_an_unhandled_error_is_reported_once_with_nothing_the_request_held(
        self, settings, monkeypatch, capsys, caplog
    ):
        async def fail(*_args, **_kwargs):
            raise RuntimeError(" ".join(SECRETS))

        monkeypatch.setattr(Briefings, "create", fail)
        app, *_ = make_app(settings)
        client = api_client(app, raise_server_exceptions=False, client=(ADDRESS, 50000))
        body = {**PANEL, "instruction": f"{BODY_TEXT} {TOKEN} {PANEL['instruction']}"}
        with caplog.at_level(logging.DEBUG):
            response = client.post("/api/briefings", json=body, headers={"X-Forwarded-For": ADDRESS})
        assert error_of(response) == (500, "internal_error")
        err = capsys.readouterr().err
        (entry,) = reports(err)
        assert ", in fail\n" in entry["message"] and entry["message"].endswith("\nRuntimeError")
        assert "unhandled error: RuntimeError" in caplog.text  # the plain line stays as it was
        for secret in SECRETS:
            assert secret not in err and secret not in caplog.text, secret
            assert secret not in response.text, secret


class Lines(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def server_log():
    """uvicorn's error logger after configure_logging, with a handler that keeps what passes."""
    obs.configure_logging()
    logger = logging.getLogger(obs.SERVER_LOGGER)
    lines, level = Lines(), logger.level
    logger.addHandler(lines)
    logger.setLevel(logging.INFO)
    yield logger, lines.records
    logger.removeHandler(lines)
    logger.setLevel(level)


class TestTheServersOwnTraceback:
    """Starlette re-raises what its 500 handler answered, and uvicorn logs it, message and all."""

    def test_an_error_the_handler_reported_is_not_logged_again(self, server_log, capsys):
        logger, passed = server_log
        exc = raised(boom)
        obs.report_error(exc)
        capsys.readouterr()
        logger.error("Exception in ASGI application\n", exc_info=exc)
        assert passed == [] and capsys.readouterr().err == ""

    def test_an_error_the_app_never_saw_is_reported_in_the_same_format(self, server_log, capsys):
        logger, passed = server_log
        logger.error("Exception in ASGI application\n", exc_info=raised(boom))
        (entry,) = reports(capsys.readouterr().err)
        assert ", in boom\n" in entry["message"] and passed == []

    def test_its_other_lines_pass(self, server_log):
        logger, passed = server_log
        logger.info("Started server process")
        assert [r.getMessage() for r in passed] == ["Started server process"]

    def test_the_filter_is_installed_once(self):
        obs.configure_logging()
        obs.configure_logging()
        filters = logging.getLogger(obs.SERVER_LOGGER).filters
        assert sum(isinstance(f, obs.ServerTracebackFilter) for f in filters) == 1
