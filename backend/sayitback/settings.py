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
from urllib.parse import urlsplit

BACKEND_DIR = Path(__file__).resolve().parents[1]
THINKING_LEVELS = ("low", "medium", "high")  # Gemini 3.8 Flash has no "minimal" (it errors).
BACKENDS = ("developer-api", "agent-platform")
TURN_TAKING = ("manual", "auto")
STORES = ("local", "firestore")
MIN_OUTPUT_TOKENS = 1024  # below this an ordinary reply (plus its thinking) would be cut off
MAX_PROXY_HOPS = 8  # more X-Forwarded-For entries than any real chain of proxies appends
MAX_WEBHOOK_URLS = 3  # SIB_WEBHOOK_URL is a comma-separated list of at most this many
MAX_RETRY_ATTEMPTS = 5  # SIB_RETRY_ATTEMPTS counts the first call
MAX_REFUSAL_RETRIES = 3  # SIB_REFUSAL_RETRIES: extra calls after a blocked reply; 0 = none
MAX_WEBHOOK_TIMEOUT_S = 10.0  # the decision awaits the webhooks; the browser gives up after 20 s
MAX_IDEMPOTENCY_TTL_S = 86400.0  # SIB_IDEMPOTENCY_TTL_S: a day at most (idempotency.py)
MAX_RETENTION_DAYS = 3650  # SIB_RETENTION_DAYS: ten years at most; 0 = keep

# Gemini 3.x guidance: leave temperature, top_p and top_k at their defaults and steer effort with
# thinking_level. These are the per-agent defaults; SIB_THINKING_<AGENT> overrides one of them.
DEFAULT_THINKING: Mapping[str, str] = MappingProxyType(
    {
        "extract_steps": "low",  # 15 Oct real runs: low flagged the SOP-only step 3/3, medium 0/3
        "write_script": "low",
        "back_translate": "low",
        "transcribe_instruction": "low",
        "re_explain": "low",
        "blind_transcriber": "low",
        # 15 Oct paid eval (58 answers): low and medium both 0 false passes of 68, 87.5% exact;
        # low passed 39 of 44 correct answers (medium 38) and ran 35% faster.
        # eval/reports/2026-10-15-paid-judges-*.md
        "judge_a": "low",
        "judge_b": "low",
        "hazard_report": "low",
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


def webhook_urls(raw: str) -> tuple[str, ...]:
    """SIB_WEBHOOK_URL: a comma-separated list of at most 3 http(s) URLs. A URL can hold a key, so
    an error names the entry's position, never its text."""
    urls = tuple(u.strip() for u in raw.split(",") if u.strip())
    if len(urls) > MAX_WEBHOOK_URLS:
        raise ConfigError(f"SIB_WEBHOOK_URL holds at most {MAX_WEBHOOK_URLS} URLs")
    for position, url in enumerate(urls, 1):
        try:
            parts = urlsplit(url)
            ok = parts.scheme in ("http", "https") and bool(parts.hostname)
        except ValueError:
            ok = False
        if not ok:
            raise ConfigError(f"SIB_WEBHOOK_URL entry {position} is not an http(s) URL")
    return urls


@dataclass(frozen=True, eq=False)
class Settings:
    # Models (ARCHITECTURE.md table)
    flash_model: str = "gemini-3.8-flash"
    live_model: str = "gemini-3.8-live"
    tts_model: str = "gemini-3.8-flash-tts"
    judge_b_model: str = "gemini-3.1-flash-lite"  # "" = the Flash model (judge_b_model_id)
    live_voice: str = "Kore"
    tts_voice: str = "Kore"
    # Google platform switches
    agent_platform: bool = False
    cloud_project: str = ""
    cloud_location: str = "global"
    live_location: str = "us-central1"
    tts_location: str = ""  # Agent Platform TTS only; "" = cloud_location (tts_location_id)
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
    # Privacy (16 Oct, consent.py and retention.py). SIB_REQUIRE_CONSENT defaults to true in the
    # environment (Settings.from_env, what the service runs); the dataclass default stays false so
    # code and tests that build Settings by hand keep their behaviour.
    require_consent: bool = False  # a check with a person's voice needs the round's consent
    retention_days: int = 90  # SIB_RETENTION_DAYS: each stored briefing's expireAt; 0 = keep
    # Observability and integrations
    trace_to_cloud: bool = False
    bq_dataset: str = ""
    bq_location: str = "US"
    # A webhook URL can hold a key, and the secret signs every post: neither is in the repr, so
    # no traceback or log line that prints the settings can show them.
    webhook_url: str = field(default="", repr=False)  # comma-separated, at most 3 (webhook_urls)
    webhook_secret: str = field(default="", repr=False)  # HMAC key for JSON posts; "" = unsigned
    webhook_timeout_s: float = 5.0  # all URLs together, awaited before the decision answers
    # Pilot e-permit link (outbox.py, docs/EPERMIT_ADAPTER.md). Off by default: SIB_OUTBOX stores
    # every delivery, retries it with backoff and shows its status on the record.
    outbox: bool = False
    outbox_max_attempts: int = 8  # then the delivery is `failed`
    outbox_backoff_s: float = 30.0  # the first retry's wait; it doubles, up to the next
    outbox_max_backoff_s: float = 3600.0
    outbox_retry_batch: int = 20  # briefings one POST /admin/outbox/retry works through
    outbox_token: str = field(default="", repr=False)  # bearer for that route; "" = no route
    ptw_url: str = field(default="", repr=False)  # the site's e-permit endpoint: one more target
    ptw_field_map: str = ""  # JSON: the generic adapter's field map; "" = the native record
    ptw_token: str = field(default="", repr=False)  # bearer sent to ptw_url; never logged
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
    # Script approval and hazard reports (API.md v0.4, endpoints 21-23)
    approve_by_max_chars: int = 80
    max_hazards: int = 5  # per briefing; over it 422 too_many_hazards
    max_hazard_seconds: float = 30.0  # a voice report; the upload's size limit is max_audio_bytes
    hazard_note_min_chars: int = 5  # the supervisor's acknowledgement; else 422 note_required
    hazard_note_max_chars: int = 500
    # Cost bounds on what the model writes (API.md, "Daily cap")
    max_sentences_per_step: int = 3  # instruction sentences per step in a round's scope
    max_line_chars: int = 160  # any spoken line: a sentence, a question or the closing
    max_output_tokens: int = 8192  # per Flash call, thinking tokens included
    # Check guards and delivery
    min_clip_seconds: float = 0.8
    silence_rms: float = 150.0  # int16 RMS of the loudest 100 ms; below this a clip is near-silent
    delivery_min_similarity: float = 0.8
    delivery_min_script_share: float = 0.7
    reply_max_chars: int = 60  # a "<qid>.reply" longer than this (normalised) is reply_too_long
    # Upstream resilience (v0.5.1): each Flash call attempt is cut off after call_timeout_s, and a
    # 429, 5xx or timed-out attempt is retried; attempts include the first call, so 3 means two
    # retries. All of it stays inside phase_timeout_s.
    retry_attempts: int = 3
    retry_backoff_s: float = 2.0
    refusal_retries: int = 1  # a reply the safety filter blocked is asked for again this often
    call_timeout_s: float = 40.0  # per attempt; never more than phase_timeout_s (call_http_options)
    phase_timeout_s: float = 110.0  # one ADK phase
    request_timeout_s: float = 120.0  # a whole /api call that chains phases; the browser calls
    # Cloud Run directly (no Hosting 60 s cut) and waits 125 s
    tts_cache_max_bytes: int = 32 * 1024 * 1024
    # Weak signal (idempotency.py, 2026-10-16): how long a check upload's Idempotency-Key keeps
    # its judged round for a retry; 0 ignores the header
    idempotency_ttl_s: float = 3600.0
    # Pilot accounts (auth.py, build-notes/34): "device" is today's anonymous device key
    auth_mode: str = "device"
    auth_project: str = ""  # firebase mode: the ID token's audience
    auth_org: str = ""  # firebase mode: the deployment's one org
    auth_allowed_domains: tuple[str, ...] = ()  # empty = any verified email
    bootstrap_admins: tuple[str, ...] = field(default=(), repr=False)  # emails, kept out of logs

    def with_overrides(self, **changes: object) -> Settings:
        return replace(self, **changes)

    @property
    def judge_b_model_id(self) -> str:
        """The model judge B runs on: SIB_JUDGE_B_MODEL, or the Flash model when that is empty."""
        return self.judge_b_model or self.flash_model

    @property
    def tts_location_id(self) -> str:
        """Where TTS runs on Agent Platform: SIB_TTS_LOCATION, or GOOGLE_CLOUD_LOCATION when that
        is empty."""
        return self.tts_location or self.cloud_location

    @property
    def webhook_urls(self) -> tuple[str, ...]:
        return webhook_urls(self.webhook_url)

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
            judge_b_model=e.get("SIB_JUDGE_B_MODEL", defaults.judge_b_model).strip(),
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
            **_v04(e, defaults),
            **_v05(e, defaults),
            **_permit_link(e, defaults),
            **_privacy(e, defaults),
            keep_audio=_flag(e, "SIB_KEEP_AUDIO"),
            phase_timeout_s=_number(e, "SIB_PHASE_TIMEOUT_S", defaults.phase_timeout_s, float),
            request_timeout_s=_number(
                e, "SIB_REQUEST_TIMEOUT_S", defaults.request_timeout_s, float
            ),
            idempotency_ttl_s=_number(
                e, "SIB_IDEMPOTENCY_TTL_S", defaults.idempotency_ttl_s, float
            ),
            trace_to_cloud=_flag(e, "SIB_TRACE_TO_CLOUD"),
            bq_dataset=e.get("SIB_BQ_DATASET", "").strip(),
            bq_location=e.get("SIB_BQ_LOCATION", "").strip() or defaults.bq_location,
            webhook_url=e.get("SIB_WEBHOOK_URL", "").strip(),
            webhook_secret=e.get("SIB_WEBHOOK_SECRET", "").strip(),
            live_turn_taking=_choice(e, "SIB_LIVE_TURN_TAKING", TURN_TAKING, "manual"),
            **_auth_settings(e),
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
        for name, value in (
            ("SIB_DELIVERY_MIN_SIMILARITY", self.delivery_min_similarity),
            ("SIB_DELIVERY_MIN_SCRIPT_SHARE", self.delivery_min_script_share),
        ):
            if not 0.0 <= value <= 1.0:
                raise ConfigError(f"{name} must be between 0 and 1")
        if self.reply_max_chars < 1:
            raise ConfigError("SIB_REPLY_MAX_CHARS must be at least 1")
        if self.max_hazards < 1:
            raise ConfigError("SIB_MAX_HAZARDS must be at least 1")
        if self.phase_timeout_s <= 0 or self.request_timeout_s <= 0:
            raise ConfigError("SIB_PHASE_TIMEOUT_S and SIB_REQUEST_TIMEOUT_S must be above 0")
        if self.call_timeout_s <= 0:
            raise ConfigError("SIB_CALL_TIMEOUT_S must be above 0")
        if not 0 <= self.idempotency_ttl_s <= MAX_IDEMPOTENCY_TTL_S:
            raise ConfigError(
                f"SIB_IDEMPOTENCY_TTL_S must be between 0 and {MAX_IDEMPOTENCY_TTL_S:g}"
            )
        if not 1 <= self.retry_attempts <= MAX_RETRY_ATTEMPTS:
            raise ConfigError(f"SIB_RETRY_ATTEMPTS must be between 1 and {MAX_RETRY_ATTEMPTS}")
        if not 0 <= self.refusal_retries <= MAX_REFUSAL_RETRIES:
            raise ConfigError(f"SIB_REFUSAL_RETRIES must be between 0 and {MAX_REFUSAL_RETRIES}")
        if not 0 < self.webhook_timeout_s <= MAX_WEBHOOK_TIMEOUT_S:
            raise ConfigError(
                f"SIB_WEBHOOK_TIMEOUT_S must be above 0 and at most {MAX_WEBHOOK_TIMEOUT_S:g}"
            )
        webhook_urls(self.webhook_url)
        _check_permit_link(self)
        if not 0 <= self.retention_days <= MAX_RETENTION_DAYS:
            raise ConfigError(f"SIB_RETENTION_DAYS must be 0 (keep) to {MAX_RETENTION_DAYS}")
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


def _v04(env: Mapping[str, str], d: Settings) -> dict[str, int | float]:
    """API v0.4: the delivery check, the hazard limit."""
    return {
        "delivery_min_similarity": _number(
            env, "SIB_DELIVERY_MIN_SIMILARITY", d.delivery_min_similarity, float
        ),
        "delivery_min_script_share": _number(
            env, "SIB_DELIVERY_MIN_SCRIPT_SHARE", d.delivery_min_script_share, float
        ),
        "reply_max_chars": _int(env, "SIB_REPLY_MAX_CHARS", d.reply_max_chars),
        "max_hazards": _int(env, "SIB_MAX_HAZARDS", d.max_hazards),
    }


def _v05(env: Mapping[str, str], d: Settings) -> dict[str, str | float]:
    """API v0.5: the webhooks' time budget, TTS's own Agent Platform location; v0.5.1: each Flash
    call attempt's cut-off, how many attempts a call gets, and how often a blocked reply is asked
    for again."""
    return {
        "webhook_timeout_s": _number(env, "SIB_WEBHOOK_TIMEOUT_S", d.webhook_timeout_s, float),
        "tts_location": env.get("SIB_TTS_LOCATION", "").strip(),
        "call_timeout_s": _number(env, "SIB_CALL_TIMEOUT_S", d.call_timeout_s, float),
        "retry_attempts": _int(env, "SIB_RETRY_ATTEMPTS", d.retry_attempts),
        "refusal_retries": _int(env, "SIB_REFUSAL_RETRIES", d.refusal_retries),
    }


def _permit_link(env: Mapping[str, str], d: Settings) -> dict[str, object]:
    """The pilot e-permit link: the outbox (SIB_OUTBOX*) and the vendor target (SIB_PTW_*)."""
    return {
        "outbox": _flag(env, "SIB_OUTBOX", d.outbox),
        "outbox_max_attempts": _int(env, "SIB_OUTBOX_MAX_ATTEMPTS", d.outbox_max_attempts),
        "outbox_backoff_s": _number(env, "SIB_OUTBOX_BACKOFF_S", d.outbox_backoff_s, float),
        "outbox_max_backoff_s": _number(
            env, "SIB_OUTBOX_MAX_BACKOFF_S", d.outbox_max_backoff_s, float
        ),
        "outbox_retry_batch": _int(env, "SIB_OUTBOX_RETRY_BATCH", d.outbox_retry_batch),
        "outbox_token": env.get("SIB_OUTBOX_TOKEN", "").strip(),
        "ptw_url": env.get("SIB_PTW_URL", "").strip(),
        "ptw_field_map": env.get("SIB_PTW_FIELD_MAP", "").strip(),
        "ptw_token": env.get("SIB_PTW_TOKEN", "").strip(),
    }


PERMIT_LINK_NEEDS_ACCOUNTS = (
    "The e-permit link (SIB_OUTBOX, SIB_PTW_URL) needs SIB_AUTH_MODE=firebase: in device mode no "
    "person stands behind a decision."
)


def _check_permit_link(s: Settings) -> None:
    """At start-up: the outbox's numbers, the vendor URL (never named: it may hold a key), a field
    map that parses, a bearer token only over https (or to this machine, for a local try), and
    accounts (security fixes A, H1): in device mode any browser decides, so the link that releases
    a real permit is refused. SIB_WEBHOOK_URL (the demo stub, Google Chat) needs no accounts."""
    if not 1 <= s.outbox_max_attempts <= 50 or not 1 <= s.outbox_retry_batch <= 100:
        raise ConfigError("SIB_OUTBOX_MAX_ATTEMPTS must be 1-50 and SIB_OUTBOX_RETRY_BATCH 1-100")
    if not 0 < s.outbox_backoff_s <= s.outbox_max_backoff_s:
        raise ConfigError("SIB_OUTBOX_BACKOFF_S must be above 0, at most SIB_OUTBOX_MAX_BACKOFF_S")
    if (s.ptw_field_map or s.ptw_token) and not s.ptw_url:
        raise ConfigError("SIB_PTW_FIELD_MAP and SIB_PTW_TOKEN need SIB_PTW_URL")
    if s.ptw_url:
        try:
            parts = urlsplit(s.ptw_url)
            ok = parts.scheme in ("http", "https") and bool(parts.hostname)
        except ValueError:
            ok = False
        if not ok:
            raise ConfigError("SIB_PTW_URL is not an http(s) URL")
        local = parts.hostname in ("localhost", "127.0.0.1")
        if s.ptw_token and parts.scheme != "https" and not local:
            raise ConfigError("SIB_PTW_TOKEN is sent only over https: SIB_PTW_URL must be https")
        from sayitback.webhook import parse_field_map  # here: webhook imports this module

        parse_field_map(s.ptw_field_map)
    if (s.outbox or s.ptw_url) and s.auth_mode != "firebase":
        raise ConfigError(PERMIT_LINK_NEEDS_ACCOUNTS)


def _privacy(env: Mapping[str, str], d: Settings) -> dict[str, bool | int]:
    """Privacy (16 Oct): the worker's consent before a check of their voice (default on in the
    environment), and how many days a stored briefing is kept (0 = keep)."""
    return {
        "require_consent": _flag(env, "SIB_REQUIRE_CONSENT", True),
        "retention_days": _int(env, "SIB_RETENTION_DAYS", d.retention_days),
    }


def _backend(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip().lower()
    if value and value not in BACKENDS:
        raise ConfigError(f"{name} must be one of {', '.join(BACKENDS)}, got {value!r}")
    return value


def _auth_settings(env: Mapping[str, str]) -> dict[str, object]:
    """Pilot accounts (auth.py): SIB_AUTH_MODE and what firebase mode needs. A firebase deployment
    with no project or org stops at start-up (auth.check_settings), never at a request."""
    from sayitback.auth import AUTH_MODES, check_settings, csv_lower

    values: dict[str, object] = {
        "auth_mode": _choice(env, "SIB_AUTH_MODE", AUTH_MODES, "device"),
        "auth_project": (
            env.get("SIB_AUTH_PROJECT", "").strip() or env.get("GOOGLE_CLOUD_PROJECT", "").strip()
        ),
        "auth_org": env.get("SIB_AUTH_ORG", "").strip(),
        "auth_allowed_domains": csv_lower(env.get("SIB_AUTH_ALLOWED_DOMAINS", "")),
        "bootstrap_admins": csv_lower(env.get("SIB_BOOTSTRAP_ADMINS", "")),
    }
    check_settings(values)
    return values
