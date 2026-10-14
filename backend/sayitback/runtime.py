"""Runtime: the settings plus the model objects every phase shares.

Production builds Gemini models from settings. Tests build a Runtime around fake models, so no
test touches the network. `get_runtime()` is what the `adk web` agent modules use.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache

from google import genai
from google.adk.models.base_llm import BaseLlm

from sayitback import backends
from sayitback.settings import Settings

LiveFactory = Callable[[Callable[[], None] | None], BaseLlm]
# Awaited once a request is known to need the model, just before its first call; it may raise to
# refuse. The HTTP API reserves the daily Gemini budget here. Direct callers (eval/) pass none.
BeforeCall = Callable[[], Awaitable[None]]


@dataclass(frozen=True, eq=False)
class Runtime:
    settings: Settings
    flash: BaseLlm
    live_factory: LiveFactory
    tts_client_factory: Callable[[], genai.Client]

    @classmethod
    def from_settings(cls, settings: Settings) -> Runtime:
        return cls(
            settings=settings,
            flash=backends.make_flash(settings),
            live_factory=lambda on_connected: backends.make_live(settings, on_connected),
            tts_client_factory=lambda: backends.make_genai_client("tts", settings),
        )


@lru_cache(maxsize=1)
def get_runtime() -> Runtime:
    """The environment-configured runtime, built once per process."""
    return Runtime.from_settings(Settings.from_env())
