"""把 `interrupt()` 数据包翻成人能读的挂起信息。

图停下来等人签字时，状态里躺着的是「哪个节点、要调什么工具、参数是什么」。
这一块顺着 tasks / subgraphs 把它挖出来，并补上动作 / 对象 / 日期 / 金额，
让审批卡说的是人话（见第 9.4 节）。
"""
from __future__ import annotations

import json

from web import orders
from web.runtime import hub
from web.runtime.identity import Desk


def _jsonable(obj):
    """把任意对象转成能进 JSON 的结构（不可序列化的走 str）。

    :param obj: 任意对象
    :return: 可 JSON 化的副本
    """
    return json.loads(json.dumps(obj, ensure_ascii=False, default=str))


def _interrupt_value(item) -> object:
    """从不同版本的 interrupt 包装里取出真正的值。

    :param item: Interrupt 对象 / 含 value 的 dict / 原值
    :return: 里面的 value
    """
    if item is None:
        return None
    if hasattr(item, "value"):
        return item.value
    if isinstance(item, dict) and "value" in item:
        return item["value"]
    return item


def _walk_interrupts(snap) -> tuple[list[str], object]:
    """顺着 tasks / subgraphs 把 interrupt() 数据包挖出来。"""
    path = list(snap.next or ())
    payload = None
    seen: set[int] = set()
    stack = [snap]
    while stack:
        current = stack.pop()
        ident = id(current)
        if ident in seen:
            continue
        seen.add(ident)
        for item in getattr(current, "interrupts", ()) or ():
            payload = _interrupt_value(item)
            if payload is not None:
                return path, payload
        for task in getattr(current, "tasks", ()) or ():
            name = getattr(task, "name", None)
            if name and name not in path:
                path.append(str(name))
            for item in getattr(task, "interrupts", ()) or ():
                payload = _interrupt_value(item)
                if payload is not None:
                    return path, payload
            child = getattr(task, "state", None)
            if child is None:
                continue
            if hasattr(child, "tasks") or hasattr(child, "interrupts"):
                if getattr(child, "next", None):
                    path.extend(str(x) for x in child.next if str(x) not in path)
                stack.append(child)
                continue
            if isinstance(child, dict):
                try:
                    nested = hub.GRAPH.get_state(child, subgraphs=True)
                except TypeError:
                    nested = hub.GRAPH.get_state(child)
                except Exception:
                    continue
                if nested.next:
                    path.extend(str(x) for x in nested.next if str(x) not in path)
                stack.append(nested)
    return path, payload


def _pending(desk: Desk) -> dict | None:
    """查这条会话现在挂在哪、要签什么字。

    :param desk: 这次请求的身份
    :return: {"path": 中断位置, "payload": 审批包} 或 None（没挂起）
    """
    try:
        snap = hub.GRAPH.get_state(desk.config, subgraphs=True)
    except TypeError:
        snap = hub.GRAPH.get_state(desk.config)
    path, payload = _walk_interrupts(snap)
    if payload is None:
        return None
    packed = _jsonable(payload)
    if not isinstance(packed, dict):
        packed = {"value": packed}
    return {
        "path": " → ".join(str(x) for x in path) or "interrupt",
        "payload": packed,
    }


def _status(desk: Desk) -> tuple[str, dict | None]:
    """状态栏那一句话：空闲还是「已挂起，等待签字」。

    :param desk: 这次请求的身份
    :return: (文案, 审批包或 None)
    """
    pending = _pending(desk)
    if pending is None:
        return "空闲：机坪等待下一条指令", None
    payload = pending["payload"]
    tool_names = ", ".join(
        call.get("name", "未知工具") for call in payload.get("tool_calls", [])
    )
    suffix = f"；待执行：{tool_names}" if tool_names else ""
    return f"已挂起，等待调度员签字。中断位置：{pending['path']}{suffix}", pending


def _enrich_pending(pending: dict | None) -> dict | None:
    """给审批包补上动作 / 对象 / 日期 / 金额，让审批卡说人话。

    原来只把 interrupt() 的原始 payload 丢给前端，界面上就是一行
    `book_car_rental {"rental_id": 3}`——用户看不懂，也不好判断该不该批。
    """
    if not pending:
        return pending
    payload = dict(pending.get("payload") or {})
    calls = []
    for call in payload.get("tool_calls") or []:
        item = dict(call)
        item.update(orders.describe_call(str(call.get("name") or ""), call.get("args") or {}) or {})
        calls.append(item)
    payload["tool_calls"] = calls
    total = 0
    for call in calls:
        amount = str(call.get("amount") or "").lstrip("¥")
        if amount.isdigit():
            total += int(amount)
    payload["total"] = f"¥{total}" if total else ""
    out = dict(pending)
    out["payload"] = payload
    return out
