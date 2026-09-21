"""sseutil.py —— SSE 帧的打包与拆包。浏览器 EventSource 不支持 POST，前端手写解析。

对应教程：11.12 / 11.13。完整版问答走 JSON；Lite 聊天走 SSE，但规矩一样：
先验证再分片，拒答也走同一条协议，不要先把未过门禁的 Token 泼到屏幕上。

一帧长这样::

    event: citations
    data: [{"marker":"[1]","doc_id":"员工差旅管理制度.md#0"}]

    data: {"delta":"一线城市"}

    event: done
    data: {"status":"ok","conversation_id":"conv_..."}

空行是帧边界。前端按 ``\\n\\n`` 切，再按行读 ``event:`` / ``data:``。
本模块给服务端打包、给离线测试拆包，避免「页面一种协议、测试另一种」。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator


# 事件名白名单：问答流用 message/citations/done/error；控制台的长任务
# （评测逐条、Ragas 逐条）用 case/summary/progress。加事件必须登记在这里，
# 前端按名字分支处理——协议不登记，等于让浏览器猜。
# 白名单还有一层用处：收帧时挡住不认识的事件名，服务端被换成别的版本、
# 或者有人往同一个端口推自己的流时，页面会报"协议错误"，而不是静默按默认分支处理。
ALLOWED_EVENTS = ("message", "citations", "done", "error", "status", "case", "summary", "progress")


class SSEProtocolError(ValueError):
    """帧缺 data、event 不在白名单、或 JSON 坏了。对外只说协议错误，不回原始帧。"""


@dataclass
class SSEFrame:
    """拆出来的一帧。

    ``event`` 是事件名（已在白名单内）；``data`` 是解析后的 JSON 值——注意它可能是
    字典、列表，本项目里 citations 就是列表，别当字典用；``raw`` 是这条 data 行的原始
    文本，只在排障和断言时用，转发给前端没必要。
    """

    event: str
    data: Any
    raw: str = ""

    def as_dict(self) -> dict[str, Any]:
        """给测试/日志用的两字段形状（``event`` + ``data``）；``raw`` 不外传。"""
        return {"event": self.event, "data": self.data}


def json_dumps(payload: Any) -> str:
    """把 ``payload`` 压成单行 JSON：不转义中文、逗号冒号不留空格。

    紧凑是必须的：data 行里一旦出现换行，浏览器就会按空行把它切成两帧。
    不转义中文是为了课堂上看一眼裸流就能读懂内容。
    """
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def format_frame(data: Any, event: str = "message") -> str:
    """打一帧。``event`` 等于 message 时省略 event 行，兼容默认 SSE。

    ``data`` 是任意可 JSON 序列化的负载（字典、列表都行），缺省事件是 message。
    事件名不在 ``ALLOWED_EVENTS`` 里、或序列化后出现空行，都抛 ``SSEProtocolError``——
    这两种错误一旦发出去，浏览器那边会静默切错帧，宁可在这里拦住。
    返回以空行结尾的完整帧文本。
    """
    if event not in ALLOWED_EVENTS:
        raise SSEProtocolError(f"未知 SSE 事件：{event}")
    body = json_dumps(data)
    if "\n\n" in body:
        raise SSEProtocolError("SSE data 里不能出现空行，否则浏览器会切错帧")
    lines = []
    if event != "message":
        lines.append(f"event: {event}")
    lines.append(f"data: {body}")
    return "\n".join(lines) + "\n\n"


def format_delta(text: str) -> str:
    """把一小段正文 ``text`` 打成 message 帧，形状固定为 ``{"delta": ...}``。

    外层包一个 ``delta`` 键而不是直接发裸字符串：前端攒正文时靠这个键区分
    "这是一段正文"和"这是某种其它事件"，不必回头看 event 行。
    """
    return format_frame({"delta": text}, event="message")


def format_citations(citations: list[dict]) -> str:
    """把引用列表 ``citations``（每项含 ``marker`` / ``doc_id``）打成 citations 帧。

    列表为空也照样发一帧空列表：协议要求 done 之前必须出现过 citations，
    "这篇没有出处"和"忘了发"必须能分开。
    """
    return format_frame(citations, event="citations")


def format_done(payload: dict[str, Any]) -> str:
    """把结束负载 ``payload``（状态、会话号、引用等）打成 done 帧，流到此为止。"""
    return format_frame(payload, event="done")


def format_error(message: str, code: str = "ask_failed") -> str:
    """打成 error 帧。``message`` 是给人看的一句话，``code`` 是给程序分支的短代号。

    错误也走协议帧而不是直接断开连接：前端拿到 error 帧才能把占位气泡换成人话，
    半路断流只会留下一句"正在过门禁…"。
    """
    return format_frame({"message": message, "code": code}, event="error")


def iter_chunks(text: str, size: int = 12) -> Iterator[str]:
    """课堂演示用的假流式：按字切，不是按 token。size<=0 就整段一次发完。

    ``text`` 是要切的正文，``size`` 是每片字数。切成定长片是为了让演示里
    "一个字一个字往外冒"的效果稳定复现，跟真实模型的分片粒度不是一回事。
    """
    if size <= 0:
        if text:
            yield text
        return
    for start in range(0, len(text), size):
        yield text[start:start + size]


def stream_answer(answer: str, citations: list[dict], done: dict[str, Any], size: int = 12) -> Iterator[str]:
    """先引用、再正文、最后 done。顺序写死，前端靠这个顺序打开证据抽屉。

    ``answer`` 是已经过完门禁的答案全文，``citations`` 是它的引用角标，
    ``done`` 是结束帧的负载（会话号、状态等），``size`` 是每片字数（透传给 ``iter_chunks``）。

    逐帧产出文本。顺序写死的原因：前端要能在正文还没到齐时就把引用收好，
    顺序一乱就得回头补发，而 SSE 是一条单向的流，回头不了。
    """
    yield format_citations(citations)
    for chunk in iter_chunks(answer, size=size):
        yield format_delta(chunk)
    payload = dict(done)
    payload.setdefault("citations", citations)
    yield format_done(payload)


def parse_frame(block: str) -> SSEFrame:
    """拆一帧。``block`` 是两条空行之间的一段文本，返回 ``SSEFrame``。

    没有 data 行、事件名不在白名单、data 不是合法 JSON，三种情况都抛
    ``SSEProtocolError``；``:`` 开头的注释行按 SSE 规范忽略。
    """
    event = "message"
    data_lines: list[str] = []
    for line in block.split("\n"):
        if not line or line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line[6:].strip() or "message"
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if not data_lines:
        raise SSEProtocolError("SSE 帧缺少 data")
    if event not in ALLOWED_EVENTS:
        raise SSEProtocolError(f"未知 SSE 事件：{event}")
    raw = "\n".join(data_lines)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SSEProtocolError("SSE data 不是合法 JSON") from exc
    return SSEFrame(event=event, data=data, raw=raw)


def parse_stream(text: str) -> list[SSEFrame]:
    """把一段拼接好的 SSE 拆成帧。残缺的最后一块丢掉——流还在路上。

    ``text`` 是已经攒到手里的整段流文本，返回解析出的帧列表。
    只认 ``\n\n`` 作帧边界：最后那截没有空行收尾的，说明这一帧还没发完，
    宁可下一批数据到了再拼，也不拿半帧去解析。
    """
    frames = []
    remaining = text
    while True:
        index = remaining.find("\n\n")
        if index < 0:
            break
        block = remaining[:index]
        remaining = remaining[index + 2:]
        if not block.strip():
            continue
        frames.append(parse_frame(block))
    return frames


def join_deltas(frames: Iterable[SSEFrame]) -> str:
    """把 ``frames`` 里的正文片拼回全文。

    只吃 message 事件且 ``data.delta`` 是字符串的帧——citations、done 这些帧里也有
    字段，混进来会把角标当正文拼上。返回拼好的全文（可能为空串）。
    """
    parts = []
    for frame in frames:
        if frame.event == "message" and isinstance(frame.data, dict):
            delta = frame.data.get("delta")
            if isinstance(delta, str):
                parts.append(delta)
    return "".join(parts)


def last_done(frames: SequenceLike) -> dict[str, Any] | None:
    """取 ``frames`` 里最后一帧 done 的负载；一帧都没有就返回 ``None``。

    取最后一帧而不是第一帧：重试场景下流里可能有两次 done，后到的才是最终结局。
    """
    done = None
    for frame in frames:
        if frame.event == "done" and isinstance(frame.data, dict):
            done = frame.data
    return done


# typing 兼容：避免循环 import Sequence
from typing import Sequence as SequenceLike  # noqa: E402


def assert_safe_order(frames: SequenceLike) -> None:
    """协议门禁：citations 必须出现在第一段正文之前；done 必须在最后。

    ``frames`` 是待检查的帧序列，顺序不对就抛 ``SSEProtocolError``（返回 None）。
    规矩写成断言而不是"前端自己兼容"，是因为这几条正是证据抽屉的成立条件：
    引用要是能跟在正文后面，用户就会先读到没有出处的结论。
    """
    seen_delta = False
    seen_done = False
    seen_citations = False
    for frame in frames:
        if seen_done:
            raise SSEProtocolError("done 之后不能再发帧")
        if frame.event == "citations":
            if seen_delta:
                raise SSEProtocolError("引用必须在正文之前发出")
            seen_citations = True
        elif frame.event == "message":
            seen_delta = True
        elif frame.event == "done":
            if not seen_citations:
                raise SSEProtocolError("结束帧之前必须先发 citations（没有出处也要发空列表）")
            seen_done = True
        elif frame.event == "error":
            seen_done = True
    if not seen_done:
        raise SSEProtocolError("流没有结束帧")
