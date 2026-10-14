"""The seam between the eval runner and the backend's check workflow (docs/API.md, "Check workflow").

The backend is imported lazily, only when the real check is requested. backend_run_check() expects the
backend to expose sayitback.pipeline.run_check (async) and Pydantic models Step and Question in
sayitback.models. If the backend names them differently, change only this file.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
from typing import Any, Callable

RunCheck = Callable[..., Any]


def backend_run_check() -> RunCheck:
    pipeline = importlib.import_module("sayitback.pipeline")
    models = importlib.import_module("sayitback.models")

    async def check(*, steps: list[dict], questions: list[dict], clips: dict[str, bytes],
                    worker_lang: str, supervisor_lang: str) -> Any:
        return await pipeline.run_check(
            steps=[models.Step(**step) for step in steps],
            questions=[models.Question(**question) for question in questions],
            clips=clips,
            worker_lang=worker_lang,
            supervisor_lang=supervisor_lang,
        )

    return check


def call_check(run_check: RunCheck, payload: dict) -> dict:
    """Call the check (sync or async) and return the normalised result."""
    outcome = run_check(**payload)
    if inspect.isawaitable(outcome):
        outcome = asyncio.run(_await(outcome))
    return normalize_result(outcome)


async def _await(awaitable: Any) -> Any:
    return await awaitable


def normalize_result(result: Any) -> dict:
    """{ratings: {stepId: {verdict, flags, evidence}}, passB: bool, modelIds: {...}} from a CheckResult.

    Accepts Pydantic models, dataclasses or plain dicts, with camelCase or snake_case keys.
    """
    data = _plain(result)
    ratings: dict[str, dict] = {}
    for raw in data.get("ratings") or []:
        rating = _plain(raw)
        step_id = rating.get("stepId", rating.get("step_id"))
        ratings[str(step_id)] = {
            "verdict": _text(rating.get("verdict")),
            "flags": [str(flag) for flag in rating.get("flags") or []],
            "evidence": str(rating.get("quote") or rating.get("reason") or ""),
        }
    model_ids = data.get("modelIds", data.get("model_ids")) or {}
    return {
        "ratings": ratings,
        "passB": bool(data.get("passB", data.get("pass_b"))),
        "modelIds": {str(k): str(v) for k, v in dict(model_ids).items()},
    }


def _plain(obj: Any) -> dict:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump(by_alias=True)
    return dict(vars(obj))


def _text(value: Any) -> str:
    return str(getattr(value, "value", value) or "unclear")
