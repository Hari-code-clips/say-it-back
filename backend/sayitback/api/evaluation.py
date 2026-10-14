"""Endpoints 16-19: the evaluation report, the labelled items, their audio, and a live try."""

from __future__ import annotations

from functools import partial
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from sayitback.api.context import CallerDep, ctx_of, rate_limited
from sayitback.daily_cap import check_calls
from sayitback.evalset import EVAL_SUPERVISOR_LANG, agreement, is_unsafe, public_item
from sayitback.pipeline import run_check

router = APIRouter(prefix="/api/eval")


@router.get("/latest")
async def latest(request: Request) -> dict[str, Any]:
    return ctx_of(request).evals.latest_report()


@router.get("/items")
async def items(request: Request) -> dict[str, Any]:
    data = ctx_of(request).evals.items_file()
    return {"items": [public_item(i) for i in data.get("items", [])]}


@router.get("/items/{item_id}/audio")
async def item_audio(item_id: str, request: Request) -> FileResponse:
    evals = ctx_of(request).evals
    return FileResponse(evals.audio_path(evals.item(item_id)), media_type="audio/wav")


@router.post("/items/{item_id}/try", dependencies=[Depends(rate_limited)])
async def try_item(item_id: str, request: Request, caller: CallerDep) -> dict[str, Any]:
    ctx = ctx_of(request)
    item = ctx.evals.item(item_id)
    steps, questions = ctx.evals.check_inputs(item)
    clip = ctx.evals.audio_path(item).read_bytes()
    result = await run_check(
        steps=steps,
        questions=questions,
        clips={item["questionId"]: clip},
        worker_lang=item["workerLang"],
        supervisor_lang=EVAL_SUPERVISOR_LANG,
        runtime=ctx.rt,
        before_call=partial(ctx.cap.reserve, check_calls(ctx.settings), caller.address),
    )
    predicted = {r.step_id: r.verdict for r in result.ratings}
    gold = item.get("gold", {})
    return {
        "item": public_item(item),
        "round": {
            "transcripts": [t.wire() for t in result.transcripts],
            "passA": [r.wire() for r in result.pass_a],
            "passB": [r.wire() for r in result.pass_b],
            "ratings": [r.wire() for r in result.ratings],
        },
        "agreement": agreement(gold, predicted),
        "unsafe": is_unsafe(gold, predicted),
    }
