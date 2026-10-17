"""Replies the model's safety filter blocked (v0.5.1), told apart from silence and from errors.

Agent Platform can refuse a worker's clip at the prompt level ("prompt is blocked due to safety",
whatever the safety settings), and it does so nondeterministically: the same request passed, then
was blocked, then passed. backends.RefusalRetry asks again; adk_common.record_refusal notes in
state a reply that stayed blocked, and the guard flags it `model_refused`.
"""

from __future__ import annotations

from typing import Any

from google.genai import types

PROMPT_BLOCKS = frozenset(
    r.name for r in types.BlockedReason if r != types.BlockedReason.BLOCKED_REASON_UNSPECIFIED
)
# A candidate that stopped for one of these with no content was filtered, not answered
FILTERED = frozenset(
    {
        types.FinishReason.SAFETY,
        types.FinishReason.BLOCKLIST,
        types.FinishReason.PROHIBITED_CONTENT,
        types.FinishReason.SPII,
        types.FinishReason.RECITATION,
        types.FinishReason.IMAGE_SAFETY,
        types.FinishReason.IMAGE_PROHIBITED_CONTENT,
        types.FinishReason.IMAGE_RECITATION,
    }
)


def refusal_reason(llm_response: Any) -> str | None:
    """The block reason when the model's filter refused this reply, else None. ADK turns a blocked
    prompt (no candidate, only `prompt_feedback`) into `error_code` = the BlockedReason's name with
    no finish reason, and a candidate with no content into `error_code` = its FinishReason's."""
    content = getattr(llm_response, "content", None)
    if content and content.parts:
        return None
    code = str(getattr(llm_response, "error_code", None) or "")
    finish = getattr(llm_response, "finish_reason", None)
    if finish is None and code in PROMPT_BLOCKS:
        return code
    if finish in FILTERED:
        return finish.name
    return None
