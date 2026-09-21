"""写路径：一次推进（用户发言 / 批准 / 驳回）+ 收尾记账。

「推进」= 把输入交给图、把事件吐出来、跑完做两件收尾：按工具回执记账（订单中心）、
更新会话标题与轮数。审批的审计也在这——签字这件事发生在写路径上。
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from infra.logging import log
from web import audit, orders, sessions
from web.present.labels import NODE_LABELS
from web.runtime import hub
from web.runtime.identity import Desk
from web.runtime.events import _iter_stream, _messages_from_update, _token_from_messages_mode
from web.runtime.hub import RUN_LOCK, SKIP_NODES, _push_trace
from web.runtime.inspect import _status
from web.runtime.snapshot import snapshot
from web.runtime.turns import _graph_messages, _tool_calls_of


def _turn_input(desk: Desk, message: str):
    """这次推进该喂什么：挂起中→驳回+意见（resume），否则→一句新发言。

    :param desk: 这次请求的身份
    :param message: 用户发言
    :return: 给图的输入（dict 或 Command）
    """
    if hub.GRAPH.get_state(desk.config).next:
        return Command(resume={"approved": False, "reason": message})
    return {"messages": [("user", message)]}


def _run_payload(desk: Desk, payload, user_message: str = ""):
    """锁内执行一次图推进：节点灯、工具过程、正文 token。"""
    for namespace, mode, data in _iter_stream(desk, payload):
        if mode == "messages":
            token = _token_from_messages_mode(data)
            if token:
                yield {"type": "token", "text": token}
            continue
        if mode != "updates" or not isinstance(data, dict):
            continue
        for node, update in data.items():
            node_name = str(node)
            if node_name in SKIP_NODES or node_name.startswith("__"):
                continue
            _push_trace(desk, node_name, namespace)
            event = {
                "type": "node",
                "node": node_name,
                "label": NODE_LABELS.get(node_name, node_name),
                "namespace": [str(x) for x in (namespace or ())],
            }
            delta = _messages_from_update(update)
            if delta:
                event["messages"] = delta
            yield event
    # 一轮跑完再记账：这时工具回执都在历史里了，能判断成功还是失败
    _record_orders_from_history(desk)
    _after_turn(desk, user_message)
    yield {"type": "snapshot", **snapshot(desk)}


def chat_turn(desk: Desk, message: str) -> dict:
    """跑一轮对话（非流式），返回跑完的快照。

    :param desk: 这次请求的身份
    :param message: 用户发言
    :return: 快照
    """
    if not message.strip():
        return snapshot(desk)
    with RUN_LOCK:
        hub.set_busy(True)
        try:
            snap = None
            for event in _run_payload(desk, _turn_input(desk, message), message):
                if event.get("type") == "snapshot":
                    snap = event
            return snap or snapshot(desk)
        except Exception as exc:
            log.exception(exc)
            raise
        finally:
            hub.set_busy(False)


def approve(desk: Desk) -> dict:
    """批准并续跑，返回快照。

    :param desk: 这次请求的身份
    :return: 快照
    """
    _audit_decision(desk, True)
    with RUN_LOCK:
        hub.set_busy(True)
        try:
            snap = None
            for event in _run_payload(desk, Command(resume={"approved": True})):
                if event.get("type") == "snapshot":
                    snap = event
            return snap or snapshot(desk)
        finally:
            hub.set_busy(False)


def reject(desk: Desk) -> dict:
    """驳回并让专员重规划，返回快照。

    :param desk: 这次请求的身份
    :return: 快照
    """
    _audit_decision(desk, False)
    with RUN_LOCK:
        hub.set_busy(True)
        try:
            snap = None
            for event in _run_payload(
                desk,
                Command(resume={"approved": False, "reason": "用户点击了驳回，请重新给出方案"}),
                "驳回，请重新给出方案",
            ):
                if event.get("type") == "snapshot":
                    snap = event
            return snap or snapshot(desk)
        finally:
            hub.set_busy(False)


def _after_turn(desk: Desk, message: str) -> None:
    """一轮对话收尾：更新会话的标题、轮数和最近使用时间。"""
    if not desk.thread_id:
        return
    sessions.auto_title(desk.thread_id, desk.passenger_id, message)
    turns = sum(1 for msg in _graph_messages(desk) if getattr(msg, "type", "") == "human")
    sessions.touch(desk.thread_id, turns)


def _record_orders_from_history(desk: Desk) -> None:
    """扫描历史里的 (工具调用, 工具回执) 配对，把下单/退单写成订单。

    业务工具本身不知道订单表的存在——它们只管改库存。订单中心这层
    在运行时按工具名分派记账，好处是八个业务工具一行都不用改。
    upsert 带唯一键，所以同一条历史重复扫描不会记成两单。
    """
    calls: dict[str, tuple[str, dict]] = {}
    results: dict[str, str] = {}
    for msg in _graph_messages(desk):
        if isinstance(msg, AIMessage):
            for call in _tool_calls_of(msg):
                calls[call["id"]] = (call["name"], call["args"])
        elif isinstance(msg, ToolMessage):
            results[getattr(msg, "tool_call_id", "")] = str(msg.content or "")
    if not calls:
        return
    for call_id, (name, args) in calls.items():
        if name not in orders.TOOL_MAP:
            continue
        text = results.get(call_id, "")
        if not text:
            continue
        # 工具用自然语言汇报失败（"未找到" / "无法" / "失败"），这类不算下单成功
        if any(bad in text for bad in ("未找到", "无法", "失败", "不存在", "没有找到")):
            continue
        try:
            recorded = orders.record_tool_call(
                name,
                args,
                passenger_id=desk.passenger_id,
                username=desk.actor,
                thread_id=desk.thread_id or "",
            )
        except Exception:       # noqa: BLE001 —— 记账失败不能影响对话
            log.exception("订单记账失败")
            continue
        if recorded:
            audit.write(
                audit.BOOK if recorded["status"] == orders.CONFIRMED else audit.CANCEL,
                actor=desk.actor,
                passenger_id=desk.passenger_id,
                thread_id=desk.thread_id or "",
                target=f"{name}#{recorded['ref']}",
                detail={"title": recorded["title"], "args": args},
            )


def _audit_decision(desk: Desk, approved: bool) -> None:
    """把这次签字记进审计：谁、批的什么工具、什么参数。"""
    status, pending = _status(desk)
    payload = (pending or {}).get("payload") or {}
    calls = payload.get("tool_calls") or []
    audit.write(
        audit.APPROVE if approved else audit.REJECT,
        actor=desk.actor,
        passenger_id=desk.passenger_id,
        thread_id=desk.thread_id or "",
        target=", ".join(str(c.get("name")) for c in calls) or (pending or {}).get("path", ""),
        detail={"domain": payload.get("domain"), "tool_calls": calls},
        result=audit.OK if approved else audit.DENIED,
    )
