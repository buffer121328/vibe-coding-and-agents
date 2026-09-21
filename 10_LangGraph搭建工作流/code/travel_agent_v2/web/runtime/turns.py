"""图里的消息 → 前端要的「轮次 / 历史」。

这层负责「翻译」：LangGraph 存的是 HumanMessage / AIMessage / ToolMessage 的流水，
前端要的是「用户一句 + 可折叠的工具过程 + 最后一条正文」。翻译只读，不动状态。
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

from web.runtime import hub
from web.runtime.identity import Desk


def _clip(text: str, limit: int = 800) -> str:
    """长文本截断（消息回执动辄几百字，前端不需要全文）。

    :param text: 原文
    :param limit: 上限字符数
    :return: 截断后的字符串
    """
    text = str(text or "")
    if len(text) > limit:
        return text[:limit] + " …"
    return text


def _tool_calls_of(msg) -> list[dict]:
    """取出消息里的工具调用，统一成 dict（兼容 pydantic 对象与 dict 两种形状）。

    :param msg: AIMessage
    :return: [{"id", "name", "args"}]
    """
    out = []
    for call in getattr(msg, "tool_calls", None) or []:
        if isinstance(call, dict):
            out.append(
                {
                    "id": call.get("id", ""),
                    "name": call.get("name", "?"),
                    "args": call.get("args") or {},
                }
            )
        else:
            out.append(
                {
                    "id": getattr(call, "id", "") or "",
                    "name": getattr(call, "name", "?"),
                    "args": getattr(call, "args", {}) or {},
                }
            )
    return out


def _one_bubble(msg) -> dict | None:
    """把一条消息翻成前端的一个「气泡」（工具回执 / 助手 / 用户）。

    :param msg: LangChain 消息对象
    :return: 气泡 dict；无内容的返回 None
    """
    if isinstance(msg, ToolMessage):
        return {
            "role": "tool",
            "name": getattr(msg, "name", "") or "tool",
            "content": _clip(msg.content, 420),
        }
    if isinstance(msg, AIMessage):
        calls = _tool_calls_of(msg)
        text = str(msg.content or "").strip()
        if not text and not calls:
            return None
        item = {"role": "assistant", "content": text}
        if calls:
            item["tool_calls"] = calls
        return item
    if getattr(msg, "type", "") == "human":
        return {"role": "user", "content": str(msg.content)}
    return None


def _collect_messages(snap, depth: int = 0) -> list:
    """父图 messages 在子图挂起时往往还没汇回来，顺着 tasks.state 把子图消息补上。"""
    values = getattr(snap, "values", None) or {}
    msgs = list(values.get("messages") or [])
    if depth >= 4:
        return msgs
    for task in getattr(snap, "tasks", ()) or ():
        child = getattr(task, "state", None)
        nested = None
        if child is None:
            continue
        if hasattr(child, "values"):
            nested = child
        elif isinstance(child, dict):
            try:
                nested = hub.GRAPH.get_state(child, subgraphs=True)
            except TypeError:
                try:
                    nested = hub.GRAPH.get_state(child)
                except Exception:
                    nested = None
            except Exception:
                nested = None
        if nested is None:
            continue
        child_msgs = _collect_messages(nested, depth + 1)
        if len(child_msgs) > len(msgs):
            msgs = child_msgs
    return msgs


def _graph_messages(desk: Desk) -> list:
    """取这条会话当前的完整消息列表（父图 + 子图挂起时的补全）。

    :param desk: 这次请求的身份
    :return: 消息列表
    """
    try:
        snap = hub.GRAPH.get_state(desk.config, subgraphs=True)
    except TypeError:
        snap = hub.GRAPH.get_state(desk.config)
    return _collect_messages(snap)


def _history(desk: Desk) -> list[dict]:
    """消息列表 → 前端要的历史（每条的 role / content / tool_calls）。

    :param desk: 这次请求的身份
    :return: 气泡列表
    """
    out = []
    for msg in _graph_messages(desk):
        item = _one_bubble(msg)
        if item:
            out.append(item)
    return out


def _turns(desk: Desk) -> list[dict]:
    """把图里的消息收成：用户一句 + 可折叠思考 + 最后一条正文（截断见 snapshot）。"""
    turns: list[dict] = []
    current = None

    def ensure_turn():
        """取当前这一轮；还没有就开一轮（内部闭包，给 _turns 用）。

        :return: 当前轮次 dict
        """
        nonlocal current
        if current is None:
            current = {"user": "", "thinking": [], "answer": ""}
            turns.append(current)
        return current

    for msg in _graph_messages(desk):
        if getattr(msg, "type", "") == "human":
            current = {"user": str(msg.content), "thinking": [], "answer": ""}
            turns.append(current)
            continue
        turn = ensure_turn()
        if isinstance(msg, AIMessage):
            for call in _tool_calls_of(msg):
                turn["thinking"].append(
                    {"type": "call", "name": call["name"], "args": call["args"]}
                )
            text = str(msg.content or "").strip()
            if text:
                if turn["answer"]:
                    turn["thinking"].append({"type": "note", "content": turn["answer"]})
                turn["answer"] = text
            continue
        if isinstance(msg, ToolMessage):
            turn["thinking"].append(
                {
                    "type": "result",
                    "name": getattr(msg, "name", "") or "tool",
                    "content": _clip(msg.content),
                }
            )
    return turns
