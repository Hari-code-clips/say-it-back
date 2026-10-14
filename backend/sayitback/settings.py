"""Settings: every model id, threshold, limit and location comes from here.

`Settings.from_env()` reads environment variables only (ARCHITECTURE.md, "Configuration").
Limits that API.md fixes are fields with defaults, so tests can override them and no module
carries a magic number.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType

BACKEND_DIR = Path(__file__).resolve().parents[1]
THINKING_LEVELS = ("low", "medium", "high")  # Gemini 3.8 Flash has no "minimal" (it errors).
BACKENDS = ("developer-api", "agent-platform")
TURN_TAKING = ("manual", "auto")
STORES = ("local", "firestore")
MIN_OUTPUT_TOKENS = 1024  # below this an ordinary reply (plus its thinking) would be cut off
MAX_PROXY_HOPS = 8  # more X-Forwarded-For entries than any real chain of proxies appends

# Gemini 3.x guidance: leave temperature, top_p and top_k at their defaults and steer effort with
# thinking_level. These are the per-agent defaults; SIB_THINKING_<AGENT> overrides one of them.
DEFAULT_THINKING: Mapping[str, str] = MappingProxyType(
    {
        "extract_steps": "medium",
        "write_script": "low",
        "back_translate": "low",
        "transcribe_instruction": "low",
        "re_explain": "low",
        "blind_transcriber": "low",
        "judge_a": "medium",
        "judge_b": "medium",
    }
)

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"", "0", "false", "no", "off"}


class ConfigError(ValueError):
    """A configuration value is invalid. Raised at start-up, never at request time."""


def _flag(env: Mapping[str, str], name: str, default: bool = False) -> bool:
    raw = env.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ConfigError(f"{name} must be true or false, got {raw!r}")


def _number(env: Mapping[str, str], name: str, default: float, cast: type) -> float:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return cast(raw.strip())
    except ValueError as exc:
        kind = "an integer" if cast is int else "a number"
        raise ConfigError(f"{name} must be {kind}, got {raw!r}") from exc


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    return int(_number(env, name, default, int))


def _choice(env: Mapping[str, str], name: str, allowed: tuple[str, ...], default: str) -> str:
    value = env.get(name, default).strip().lower()
    if value not in allowed:
        raise ConfigError(f"{name} must be one of {', '.join(allowed)}, got {value!r}")
    return value


def _thinking(env: Mapping[str, str]) -> Mapping[str, str]:
    levels = dict(DEFAULT_THINKING)
    for agent in levels:
        raw = env.get(f"SIB_THINKING_{agent.upper()}")
        if raw:
            level = raw.strip().lower()
            if level not in THINKING_LEVELS:
                raise ConfigError(f"SIB_THINKING_{agent.upper()} must be one of {THINKING_LEVELS}")
            levels[agent] = level
    return MappingProxyType(levels)


def _origins(raw: str) -> tuple[str, ...]:
    return tuple(o.strip().rstrip("/") for o in raw.split(",") if o.strip())


@dataclass(frozen=True, eq=False)
class Settings:
    # Models (ARCHITECTURE.md table)
    flash_model: str = "gemini-3.8-flash"
    live_model: str = "gemini-3.8-live"
    tts_model: str = "gemini-3.8-flash-tts"
    live_voice: str = "Kore"
    tts_voice: str = "Kore"
    # Google platform switches
    agent_platform: bool = False
    cloud_project: str = ""
    cloud_location: str = "global"
    live_location: str = "us-central1"
    live_backend: str = ""  # "" follows the global switch
    tts_backend: str = ""
    # Judging
    judge_passes: int = 2
    covered_min_confidence: float = 0.75
    thinking: Mapping[str, str] = field(default_factory=lambda: DEFAULT_THINKING)
    # Persistence, HTTP and evaluation
    store: str = "local"
    data_dir: Path = BACKEND_DIR / ".data"
    allowed_origins: tuple[str, ...] = ("http://localhost:5173",)
    public_ws_base: str = ""
    eval_dir: Path = (BACKEND_DIR / ".." / "eval").resolve()
    rate_limit_per_min: int = 30
    daily_gemini_calls: int = 300  # global per UTC day; 0 refuses every Gemini-backed call
    daily_calls_per_ip: int = 100  # each client address's share of it, same costs; 0 = off
    # Who is calling (API.md, "Callers and ownership")
    trusted_proxy_hops: int = 1  # which X-Forwarded-For entry from the right is the client
    max_sockets_per_ip: int = 4  # open Live sockets per client address, per instance
    api_docs: bool = False  # serve /api/docs and /api/openapi.json (local development only)
    cors_max_age_s: int = 7200  # every cross-origin call is preflighted (custom header); 2 h is
    # the longest Chromium honours
    keep_audio: bool = False
    # Observability and integrations
    trace_to_cloud: bool = False
    bq_dataset: str = ""
    bq_location: str = "US"
    webhook_url: str = ""
    webhook_timeout_s: float = 5.0
    # Live relay
    live_turn_taking: str = "manual"
    ticket_ttl_s: int = 120
    max_tickets_per_round: int = 2
    ws_first_message_s: float = 5.0
    ws_first_cue_s: float = 30.0  # from `ready` to the first cue
    ws_max_session_s: float = 600.0
    ws_idle_s: float = 60.0
    ws_max_window_s: float = 35.0
    ws_max_binary_bytes: int = 8192
    ws_max_text_bytes: int = 1024
    live_connect_timeout_s: float = 20.0
    live_drain_s: float = 2.0
    live_lock_extra_s: float = 60.0
    live_record_wait_s: float = 5.0  # a live-mode check waits this long for round.live
    live_input_rate: int = 16000
    # Request limits (API.md "Limits")
    max_audio_bytes: int = 3 * 1024 * 1024
    max_audio_files: int = 3
    max_clip_seconds: float = 60.0
    max_instruction_chars: int = 1000
    max_custom_sop_chars: int = 8000
    max_custom_sop_title_chars: int = 200
    max_tts_chars: int = 600
    min_steps: int = 1
    max_steps: int = 6
    max_rounds: int = 3
    max_step_text_chars: int = 300
    max_essentials: int = 6
    decision_reason_min_chars: int = 5
    decision_reason_max_chars: int = 500
    decision_by_max_chars: int = 80
    list_max_limit: int = 100
    export_max_rows: int = 1000
    max_echo_chars: int = 40  # a 422 message quotes at most this much of a submitted value
    # Cost bounds on what the model writes (API.md, "Daily cap")
    max_sentences_per_step: int = 3  # instruction sentences per step in a round's scope
    max_line_chars: int = 160  # any spoken line: a sentence, a question or the closing
    max_output_tokens: int = 8192  # per Flash call, thinking tokens included
    # Check guards and delivery
    min_clip_seconds: float = 0.8
    silence_rms: float = 150.0  # int16 RMS of the loudest 100 ms; below this a clip is near-silent
    delivery_min_similarity: float = 0.8
    delivery_min_script_share: float = 0.7
    # Upstream resilience: attempts include the first call, so 2 means one retry.
    retry_attempts: int = 2
    retry_backoff_s: float = 2.0
    phase_timeout_s: float = 50.0  # one ADK phase
    request_timeout_s: float = 55.0  # a whole /api call that chains phases (Hosting cuts at 60 s)
    tts_cache_max_bytes: int = 32 * 1024 * 1024

    def with_overrides(self, **changes: object) -> Settings:
        return replace(self, **changes)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        e = os.environ if env is None else env
        enterprise = e.get("GOOGLE_GENAI_USE_ENTERPRISE")
        platform = (
            _flag(e, "GOOGLE_GENAI_USE_ENTERPRISE")
            if enterprise is not None
            else _flag(e, "GOOGLE_GENAI_USE_VERTEXAI")
        )
        defaults = cls()
        return cls(
            flash_model=e.get("SIB_FLASH_MODEL", defaults.flash_model).strip(),
            live_model=e.get("SIB_LIVE_MODEL", defaults.live_model).strip(),
            tts_model=e.get("SIB_TTS_MODEL", defaults.tts_model).strip(),
            live_voice=e.get("SIB_LIVE_VOICE", defaults.live_voice).strip(),
            tts_voice=e.get("SIB_TTS_VOICE", defaults.tts_voice).strip(),
            agent_platform=platform,
            cloud_project=e.get("GOOGLE_CLOUD_PROJECT", "").strip(),
            cloud_location=e.get("GOOGLE_CLOUD_LOCATION", "").strip() or defaults.cloud_location,
            live_location=e.get("SIB_LIVE_LOCATION", "").strip() or defaults.live_location,
            live_backend=_backend(e, "SIB_LIVE_BACKEND"),
            tts_backend=_backend(e, "SIB_TTS_BACKEND"),
            judge_passes=int(_number(e, "SIB_JUDGE_PASSES", defaults.judge_passes, int)),
            covered_min_confidence=_number(
                e, "SIB_COVERED_MIN_CONFIDENCE", defaults.covered_min_confidence, float
            ),
            thinking=_thinking(e),
            store=_choice(e, "SIB_STORE", STORES, defaults.store),
            allowed_origins=_origins(e.get("SIB_ALLOWED_ORIGINS", "")) or defaults.allowed_origins,
            public_ws_base=e.get("SIB_PUBLIC_WS_BASE", "").strip().rstrip("/"),
            eval_dir=Path(e["SIB_EVAL_DIR"]).expanduser().resolve()
            if e.get("SIB_EVAL_DIR")
            else defaults.eval_dir,
            rate_limit_per_min=_int(e, "SIB_RATE_LIMIT_PER_MIN", defaults.rate_limit_per_min),
            daily_gemini_calls=_int(e, "SIB_DAILY_GEMINI_CALLS", defaults.daily_gemini_calls),
            **_cost_bounds(e, defaults),
            **_public_surface(e, defaults),
            keep_audio=_flag(e, "SIB_KEEP_AUDIO"),
            phase_timeout_s=_number(e, "SIB_PHASE_TIMEOUT_S", defaults.phase_timeout_s, float),
            request_timeout_s=_number(
                e, "SIB_REQUEST_TIMEOUT_S", defaults.request_timeout_s, float
            ),
            trace_to_cloud=_flag(e, "SIB_TRACE_TO_CLOUD"),
            bq_dataset=e.get("SIB_BQ_DATASET", "").strip(),
            bq_location=e.get("SIB_BQ_LOCATION", "").strip() or defaults.bq_location,
            webhook_url=e.get("SIB_WEBHOOK_URL", "").strip(),
            live_turn_taking=_choice(e, "SIB_LIVE_TURN_TAKING", TURN_TAKING, "manual"),
        )._validated()

    def _validated(self) -> Settings:
        if self.judge_passes not in (1, 2):
            raise ConfigError("SIB_JUDGE_PASSES must be 1 or 2")
        if not 0.0 <= self.covered_min_confidence <= 1.0:
            raise ConfigError("SIB_COVERED_MIN_CONFIDENCE must be between 0 and 1")
        if self.rate_limit_per_min < 1:
            raise ConfigError("SIB_RATE_LIMIT_PER_MIN must be at least 1")
        if self.daily_gemini_calls < 0:
            raise ConfigError("SIB_DAILY_GEMINI_CALLS must be 0 or more (0 refuses every call)")
        if self.max_sentences_per_step < 1:
            raise ConfigError("SIB_MAX_SENTENCES_PER_STEP must be at least 1")
        if self.max_line_chars < 1:
            raise ConfigError("SIB_MAX_LINE_CHARS must be at least 1")
        if self.max_output_tokens < MIN_OUTPUT_TOKENS:
            raise ConfigError(f"SIB_MAX_OUTPUT_TOKENS must be at least {MIN_OUTPUT_TOKENS}")
        if self.daily_calls_per_ip < 0:
            raise ConfigError("SIB_DAILY_CALLS_PER_IP must be 0 or more (0 turns it off)")
        if not 0 <= self.trusted_proxy_hops <= MAX_PROXY_HOPS:
            raise ConfigError(f"SIB_TRUSTED_PROXY_HOPS must be between 0 and {MAX_PROXY_HOPS}")
        if self.max_sockets_per_ip < 1:
            raise ConfigError("SIB_MAX_SOCKETS_PER_IP must be at least 1")
        return self


def _cost_bounds(env: Mapping[str, str], d: Settings) -> dict[str, int]:
    """What the model may write (API.md, "Daily cap"): the script limits and the output ceiling."""
    return {
        "max_sentences_per_step": _int(env, "SIB_MAX_SENTENCES_PER_STEP", d.max_sentences_per_step),
        "max_line_chars": _int(env, "SIB_MAX_LINE_CHARS", d.max_line_chars),
        "max_output_tokens": _int(env, "SIB_MAX_OUTPUT_TOKENS", d.max_output_tokens),
    }


def _public_surface(env: Mapping[str, str], d: Settings) -> dict[str, int | bool]:
    """What the public service allows one caller (API.md, "Callers and ownership" and "Limits")."""
    return {
        "daily_calls_per_ip": _int(env, "SIB_DAILY_CALLS_PER_IP", d.daily_calls_per_ip),
        "trusted_proxy_hops": _int(env, "SIB_TRUSTED_PROXY_HOPS", d.trusted_proxy_hops),
        "max_sockets_per_ip": _int(env, "SIB_MAX_SOCKETS_PER_IP", d.max_sockets_per_ip),
        "api_docs": _flag(env, "SIB_API_DOCS", d.api_docs),
    }


def _backend(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip().lower()
    if value and value not in BACKENDS:
        raise ConfigError(f"{name} must be one of {', '.join(BACKENDS)}, got {value!r}")
    return value
