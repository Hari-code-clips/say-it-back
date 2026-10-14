"""Endpoints 1, 2, 3, 12 and 15: health, catalog, supervisor speech-to-text, TTS, CSV export.

Everything here but health takes a device key (api/device.py). The TTS and the CSV export are the
caller's own: a round of its briefing, and its briefings.
"""

from __future__ import annotations

import csv
import io
from functools import partial
from typing import Any

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import Response

from sayitback import catalog, phases, validators
from sayitback.api.context import CallerDep, ctx_of, rate_limited
from sayitback.api.uploads import read_wav
from sayitback.backends import backends
from sayitback.daily_cap import TRANSCRIBE_CALLS, TTS_CALLS
from sayitback.errors import NotFound, Unprocessable
from sayitback.models import Briefing, TtsBody
from sayitback.prompts import PROMPT_VERSION
from sayitback.script_checks import clean
from sayitback.tts import part_of_script

router = APIRouter(prefix="/api")
CSV_COLUMNS = (
    "briefingId", "createdAt", "siteId", "taskId", "sopId", "sopVersion", "supervisorLang",
    "workerLang", "stepId", "stepText", "source", "finalVerdict", "rounds", "decision",
    "decisionReason", "decidedBy", "decidedAt",
)  # fmt: skip
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    s = ctx_of(request).settings
    return {
        "ok": True,
        "models": {"flash": s.flash_model, "live": s.live_model, "tts": s.tts_model},
        "backends": backends(s),
        "store": s.store,
        "judgePasses": s.judge_passes,
        "promptVersion": PROMPT_VERSION,
    }


@router.get("/catalog")
async def get_catalog() -> dict[str, Any]:
    return catalog.public_view()


@router.post("/transcribe", dependencies=[Depends(rate_limited)])
async def transcribe(
    request: Request, caller: CallerDep, audio: UploadFile, lang: str = Form(...)
) -> dict[str, str]:
    ctx = ctx_of(request)
    catalog.require_lang(lang, "lang")
    data, _info = await read_wav(audio, ctx.settings, "audio")
    await ctx.cap.reserve(TRANSCRIBE_CALLS, caller.address)
    return {"text": await phases.transcribe_instruction(ctx.rt, data, lang)}


@router.post("/tts", dependencies=[Depends(rate_limited)])
async def tts(body: TtsBody, request: Request, caller: CallerDep) -> Response:
    """Speak a line of round `n` of the caller's own briefing. Only the round's script can be
    spoken, so this is no way to turn the shared budget into arbitrary audio."""
    ctx = ctx_of(request)
    text = validators.clean_text(
        body.text, field="text", limit=ctx.settings.max_tts_chars, required=True
    )
    briefing = await ctx.repo.get(body.briefing_id, caller.owner)
    rnd = briefing.round_n(body.n)
    if rnd is None:
        raise NotFound("Round not found.", code="round_not_found")
    if not part_of_script(rnd.script, text):
        raise Unprocessable(
            "text is not part of this round's script.", code="tts_text_not_in_script"
        )
    reserve = partial(ctx.cap.reserve, TTS_CALLS, caller.address)
    return Response(await ctx.tts.speak(clean(text), before_call=reserve), media_type="audio/wav")


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(FORMULA_PREFIXES) else text  # spreadsheet formula guard


def csv_rows(b: Briefing) -> list[list[str]]:
    d = b.decision
    return [
        [
            _cell(v)
            for v in (
                b.id, b.created_at, b.site_id, b.task_id, b.sop.id, b.sop.version,
                b.supervisor_lang, b.worker_lang, s.id, s.text, s.source,
                b.latest_verdicts.get(s.id, ""), len(b.rounds), d.value if d else "",
                d.reason if d else "", d.by if d else "", d.at if d else "",
            )
        ]
        for s in b.steps
    ]  # fmt: skip


@router.get("/export/briefings.csv")
async def export_csv(request: Request, caller: CallerDep) -> Response:
    ctx = ctx_of(request)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for briefing in await ctx.repo.recent(ctx.settings.export_max_rows, caller.owner):
        writer.writerows(csv_rows(briefing))
    return Response(
        out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="briefings.csv"'},
    )
