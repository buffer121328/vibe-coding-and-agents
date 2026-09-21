"""节点级 SSE：把一次推进包装成推给前端的 text/event-stream。

事件就三类：`node`（亮灯 + 这一跳产生的消息）、`token`（正文增量）、
`snapshot`（跑完的整屏快照），外加 `busy` / `error` 两个状态。
"""
from __future__ import annotations

import json

from langgraph.types import Command

from infra.logging import log
from web.runtime import hub
from web.runtime.identity import Desk
from web.runtime.hub import RUN_LOCK
from web.runtime.snapshot import snapshot
from web.runtime.turn import _audit_decision, _run_payload, _turn_input


def _sse(event: dict) -> str:
    """把一个事件对象序列化成 SSE 的一帧。

    :param event: 事件 dict
    :return: 'data: {...}\n\n'
    """
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


def iter_chat(desk: Desk, message: str):
    """一轮对话的 SSE 生成器：busy → 节点/正文事件 → 快照 → busy 结束。

    :param desk: 这次请求的身份
    :param message: 用户发言
    """
    if not message.strip():
        yield _sse({"type": "snapshot", **snapshot(desk)})
        return
    with RUN_LOCK:
        hub.set_busy(True)
        try:
            yield _sse({"type": "busy", "busy": True})
            for event in _run_payload(desk, _turn_input(desk, message), message):
                yield _sse(event)
        except Exception as exc:
            log.exception(exc)
            yield _sse({"type": "error", "message": str(exc)})
            yield _sse({"type": "snapshot", **snapshot(desk)})
        finally:
            hub.set_busy(False)
            yield _sse({"type": "busy", "busy": False})


def iter_approve(desk: Desk):
    """批准执行的 SSE 生成器。

    :param desk: 这次请求的身份
    """
    _audit_decision(desk, True)
    with RUN_LOCK:
        hub.set_busy(True)
        try:
            yield _sse({"type": "busy", "busy": True})
            for event in _run_payload(desk, Command(resume={"approved": True})):
                yield _sse(event)
        except Exception as exc:
            log.exception(exc)
            yield _sse({"type": "error", "message": str(exc)})
            yield _sse({"type": "snapshot", **snapshot(desk)})
        finally:
            hub.set_busy(False)
            yield _sse({"type": "busy", "busy": False})


def iter_reject(desk: Desk):
    """驳回重规划的 SSE 生成器。

    :param desk: 这次请求的身份
    """
    _audit_decision(desk, False)
    with RUN_LOCK:
        hub.set_busy(True)
        try:
            yield _sse({"type": "busy", "busy": True})
            for event in _run_payload(
                desk,
                Command(resume={"approved": False, "reason": "用户点击了驳回，请重新给出方案"}),
                "驳回，请重新给出方案",
            ):
                yield _sse(event)
        except Exception as exc:
            log.exception(exc)
            yield _sse({"type": "error", "message": str(exc)})
            yield _sse({"type": "snapshot", **snapshot(desk)})
        finally:
            hub.set_busy(False)
            yield _sse({"type": "busy", "busy": False})
