"""快照：把只读投影拼成一份「当前这一屏该看到什么」。

拼的时候带两条纪律：历史和轮次只发最近一段（`SNAPSHOT_*`），超了就把
`history_truncated` 置真让界面照实说；挂起信息先过一遍 `inspect` 补成人话。
"""
from __future__ import annotations

from web.runtime import hub
from web.runtime.identity import Desk
from web.runtime import hub
from web.runtime.hub import api_key_configured, model_name, _trace
from web.runtime.inspect import _enrich_pending, _status
from web.runtime.reads import (
    audit_view,
    explore_cities,
    orders_view,
    sessions_view,
    _board,
    _collect_cards,
    _dialog_state,
    _itinerary,
    _prefs,
    _route_svg,
)
from web.runtime.turns import _history, _turns


SNAPSHOT_TURNS = 30


SNAPSHOT_HISTORY = 80


def snapshot(desk: Desk) -> dict:
    """首屏 / 每轮收尾的完整快照。

    历史和轮数只发最近一段（SNAPSHOT_TURNS / SNAPSHOT_HISTORY），
    截断时把 history_truncated 置真，界面照实说一句「只显示最近 N 轮」。
    """
    status, pending = _status(desk)
    pending = _enrich_pending(pending)
    snap = hub.GRAPH.get_state(desk.config)
    turns = _turns(desk)
    history = _history(desk)
    return {
        "history": history[-SNAPSHOT_HISTORY:],
        "turns": turns[-SNAPSHOT_TURNS:],
        "history_truncated": len(turns) > SNAPSHOT_TURNS or len(history) > SNAPSHOT_HISTORY,
        "status": status,
        "pending": pending,
        "prefs": _prefs(desk),
        "thread_id": desk.thread_id,
        "dialog_state": _dialog_state(desk),
        "next": list(snap.next or ()),
        "trace": _trace(desk),
        "model": model_name(),
        "live": api_key_configured(),
        "busy": hub.is_busy(),
        "passenger_id": desk.passenger_id,
        "itinerary": _itinerary(desk),
        "route": _route_svg(desk),
        "board": _board(desk),
        "identity": {
            "authed": True,
            "passenger_id": desk.passenger_id,
            "username": desk.actor,
            "role": desk.role,
        },
        "sessions": sessions_view(desk),
        "cards": _collect_cards(desk),
        "explore": explore_cities(),
        "orders": orders_view(desk),
        "audit": audit_view(desk),
    }
