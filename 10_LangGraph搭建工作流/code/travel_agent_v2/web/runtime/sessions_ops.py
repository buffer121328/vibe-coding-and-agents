"""身份与会话的写操作：登录 / 退出 / 新建 / 切换 / 改名 / 删除。

它们都干同一件事的两半：**改会话目录**（谁有几条对话、当前是哪条），
**写一笔审计**，然后把新的快照还给前端。改成「只改一处、审计一处」之后，
这几条路径就没有别的副作用了。
"""
from __future__ import annotations

from dataclasses import replace

from web import audit, orders, sessions
from web.auth import known_passengers
from web.runtime.hub import api_key_configured, model_name
from web.runtime.hub import TRACES
from web.runtime.identity import Desk
from web.runtime.snapshot import snapshot


def login_passenger(desk: Desk, passenger_id: str, role: str = "passenger") -> dict:
    """账号校验在 web.auth 完成；这里把登录这件事记进审计，再把首屏快照给他。"""
    orders.ensure_flight_orders(passenger_id, desk.actor)
    audit.write(
        audit.LOGIN,
        actor=desk.actor,
        passenger_id=passenger_id,
        thread_id=desk.thread_id,
        target=role,
    )
    return snapshot(desk)


def logout_passenger(desk: Desk) -> dict:
    """退出登录：记一笔审计，把这条会话的节点时间线清掉。

    身份本来就不在全局里，所以除了审计与清缓存，没有别的要「清空」。
    """
    audit.write(
        audit.LOGOUT,
        actor=desk.actor,
        passenger_id=desk.passenger_id,
        thread_id=desk.thread_id or "",
    )
    TRACES.pop(desk.thread_id or "", None)
    return {
        "authed": False,
        "history": [],
        "turns": [],
        "status": "请先登录",
        "pending": None,
        "prefs": [],
        "thread_id": "",
        "dialog_state": [],
        "next": [],
        "trace": [],
        "model": model_name(),
        "live": api_key_configured(),
        "busy": False,
        "passenger_id": None,
        "itinerary": {"legs": [], "airports": [], "passenger_id": None},
        "board": {
            "cars": {"total": 0, "booked": 0, "open": 0, "items": []},
            "hotels": {"total": 0, "booked": 0, "open": 0, "items": []},
            "trips": {"total": 0, "booked": 0, "open": 0, "items": []},
            "flights": {"total": 0, "legs": 0},
        },
        "identity": {"authed": False, "passenger_id": None},
        "accounts": known_passengers(),
        "cards": [],
        "explore": [],
        "route": "",
        "sessions": [],
        "orders": {"counts": {"all": 0, "upcoming": 0, "done": 0}, "items": []},
        "audit": {"total": 0, "by_action": {}, "failures": 0},
    }


def new_session(desk: Desk) -> dict:
    """新建一条对话：换 thread_id，历史清零，Store 里的档案不动。

    点一次就给一条新的（可预期），但 sessions.create 会顺手清掉上一条**没聊过
    也没改过名**的空草稿——列表里最多留一条「新对话 0 轮」，不会越点越乱。
    """
    session = sessions.create(desk.passenger_id, desk.actor)
    TRACES.pop(session["thread_id"], None)
    audit.write(
        audit.SESSION_NEW,
        actor=desk.actor,
        passenger_id=desk.passenger_id,
        thread_id=session["thread_id"],
    )
    return snapshot(replace(desk, thread_id=session["thread_id"]))


def open_session(desk: Desk, thread_id: str) -> dict:
    """切换到某条历史对话。只能切自己名下的。

    切完把这条「摸一下」：当前会话是靠 updated_at 解析出来的（见 resolve_desk），
    不摸一下，下一个请求又会回到原来那条上。
    """
    found = sessions.get(thread_id, desk.passenger_id)
    if not found:
        raise ValueError("这条对话不存在，或者不属于当前账号")
    sessions.touch(thread_id)
    audit.write(
        audit.SESSION_OPEN,
        actor=desk.actor,
        passenger_id=desk.passenger_id,
        thread_id=thread_id,
        target=found["title"],
    )
    return snapshot(replace(desk, thread_id=thread_id))


def rename_session(desk: Desk, thread_id: str, title: str) -> dict:
    """给一条会话改名（改完名字不算「使用过」，所以不动 updated_at）。

    :param desk: 这次请求的身份
    :param thread_id: 目标会话
    :param title: 新标题
    :return: 改名后的快照；不是自己的或不存在则抛 ValueError
    """
    if not sessions.rename(thread_id, desk.passenger_id, title):
        raise ValueError("这条对话不存在，或者不属于当前账号")
    audit.write(
        audit.SESSION_RENAME,
        actor=desk.actor,
        passenger_id=desk.passenger_id,
        thread_id=thread_id,
        target=title,
    )
    return snapshot(desk)


def delete_session(desk: Desk, thread_id: str) -> dict:
    """删除会话目录项。正在使用的那条不删，先把当前切到别处。"""
    if desk.thread_id == thread_id:
        raise ValueError("正在使用的对话不能删除，先切到别的对话")
    if not sessions.remove(thread_id, desk.passenger_id):
        raise ValueError("这条对话不存在，或者不属于当前账号")
    TRACES.pop(thread_id, None)
    audit.write(
        audit.SESSION_DELETE,
        actor=desk.actor,
        passenger_id=desk.passenger_id,
        thread_id=thread_id,
    )
    return snapshot(desk)
