"""把图的一次 `stream()` 拆成统一形状的事件（低层适配）。

LangGraph 1.x 的 stream 返回值在不同参数组合下形状不一（带命名空间的三元组、
`(mode, data)` 二元组、裸 update），这一层只做一件事：抹平成统一的
`(namespace, mode, data)`，让上面的推进逻辑不用管版本差异。
"""
from __future__ import annotations

from langchain_core.messages import AIMessageChunk

from web.runtime import hub
from web.runtime.identity import Desk
from web.runtime.turns import _one_bubble


def _iter_stream(desk: Desk, payload):
    """兼容 LangGraph 1.x 多种 stream 返回形状。"""
    try:
        iterator = hub.GRAPH.stream(
            payload,
            desk.config,
            stream_mode=["updates", "messages"],
            subgraphs=True,
        )
    except TypeError:
        iterator = hub.GRAPH.stream(payload, desk.config, stream_mode="updates")

    for item in iterator:
        if isinstance(item, tuple) and len(item) == 3:
            yield item
        elif isinstance(item, tuple) and len(item) == 2:
            mode, data = item
            yield (), mode, data
        else:
            yield (), "updates", item


def _messages_from_update(update) -> list[dict]:
    """从一次节点更新里取出「新增的消息」并翻成气泡结构。

    :param update: LangGraph 的节点更新（dict）
    :return: 气泡 dict 列表（role / content / tool_calls）
    """
    if not isinstance(update, dict):
        return []
    msgs = update.get("messages")
    if msgs is None:
        return []
    if not isinstance(msgs, list):
        msgs = [msgs]
    out = []
    for msg in msgs:
        item = _one_bubble(msg)
        if item:
            out.append(item)
    return out


def _token_from_messages_mode(data) -> str:
    """从 stream_mode=messages 的 (chunk, metadata) 里抽出正文增量。"""
    chunk = data
    if isinstance(data, tuple) and data:
        chunk = data[0]
    if isinstance(chunk, AIMessageChunk):
        text = chunk.content
        if isinstance(text, str):
            return text
        if isinstance(text, list):
            parts = []
            for part in text:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict) and part.get("type") in {"text", "output_text"}:
                    parts.append(str(part.get("text") or ""))
            return "".join(parts)
    if isinstance(chunk, dict):
        content = chunk.get("content")
        if isinstance(content, str):
            return content
    return ""
