"""Endpoint 20: WS /api/live/{id}/{n}, the Live relay."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket

from sayitback.api.context import ctx_of_ws
from sayitback.live_relay import LiveRelay

router = APIRouter()


@router.websocket("/api/live/{briefing_id}/{n}")
async def live(ws: WebSocket, briefing_id: str, n: int) -> None:
    await LiveRelay(ws, ctx_of_ws(ws).relay, briefing_id, n).run()
