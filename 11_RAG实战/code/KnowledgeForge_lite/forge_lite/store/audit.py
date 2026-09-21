"""audit.py —— 课堂审计账：谁用哪张工牌问了什么，答案有没有越权痕迹。

蒸馏来源：完整版 audit service（问答落审计、反馈落审计）。
对应教程：11.13（服务化不只是把接口挂上网，还得能事后翻账）。

Lite 不接 Kafka。账本是 ``runtime/audit.jsonl`` 一行一条，字段与完整版同形状：
actor / action / conversation_id / run_id / status / routes。写之前过 ``mask_pii``，
电话邮箱不许进账。课堂作业可以 grep 这本账，核对『员工有没有问出薪酬带宽』。
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from .. import config
from ..core.identity import Actor, resolve_actor
from ..core.quality import mask_pii


AUDIT_ACTIONS = {
    "ask",
    "create_conversation",
    "list_conversations",
    "get_conversation",
    "delete_conversation",
    "rename_conversation",
    "feedback",
    "preview_chunk",
    "list_catalog",
    "export_conversation",
    "read_trace",
}

SENSITIVE_SNIPPETS = ("薪酬", "带宽", "年薪", "身份证", "密码")


def audit_path() -> Path:
    """审计账本的落点：``runtime/audit.jsonl``。

    做成函数而不是模块级常量，是为了跟 ``config.RUNTIME_DIR`` 联动——测试用临时目录跑，
    账本也跟着搬过去，不会写回课堂那份旧账。返回账本文件的 ``Path``；
    文件此刻不一定存在，第一次 append 时才创建。
    """
    return config.RUNTIME_DIR / "audit.jsonl"


def _now() -> str:
    """当前时间戳，统一成 UTC 的 ISO 8601 字符串。

    账本会被跨时区的机器读（课堂演示就是），所以存 UTC、带偏移量，显示层再转本地：
    存本地时间会让"谁先谁后"变成一笔糊涂账。
    """
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AuditEvent:
    """账本里的一条流水，字段与完整版审计事件同形状。

    ``event_id`` 是这条记录的编号（``evt_`` 前缀 + uuid）；``action`` 是动作名，
    必须落在 ``AUDIT_ACTIONS`` 里；``user_id`` / ``actor_name`` / ``role`` / ``department``
    是提问那一刻工牌的快照——后来调了部门，旧账仍按当时的身份解释。
    ``created_at`` 是 UTC 时间戳。``conversation_id`` / ``run_id`` 指向会话柜里的记录，
    没关联时为空串；``status`` 是这次问答的结局（``ok`` / ``refuse``），
    ``routes`` 是实际走通的检索通道。``question`` / ``detail`` 是提问和补充说明，
    写盘前会脱敏；``extra`` 是留给后续加字段的扩展位，不塞业务主键。
    """

    event_id: str
    action: str
    user_id: str
    actor_name: str
    role: str
    department: str
    created_at: str
    conversation_id: str = ""
    run_id: str = ""
    status: str = ""
    routes: str = ""
    question: str = ""
    detail: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """摊平成可 JSON 序列化的字典，顺手把 ``question`` / ``detail`` 过一遍脱敏。

        脱敏放在这里而不是写在 ``record`` 里，是因为 ``append`` 是唯一的写盘出口：
        事件不管从哪条路来，过这个口子就一定会脱敏，漏不掉。
        返回扁平的字典（``extra`` 里的键仍嵌在它自己那一层，不展开）。
        """
        payload = asdict(self)
        payload["question"] = mask_pii(self.question)
        payload["detail"] = mask_pii(self.detail)
        return payload

    def looks_sensitive(self) -> bool:
        """这条流水有没有踩敏感词（关键词撞库，不是语义判断）。

        纯本地字符串匹配：课堂要看的是"账上有没有出现过薪酬、身份证这类词"，
        而且 ``sensitive_asks`` 得在不调模型的前提下扫全库，所以这里刻意不引分类器。
        返回 True 表示命中至少一个敏感词——它是个**可疑**标记，不是越权定论。
        """
        blob = f"{self.question} {self.detail}"
        return any(marker in blob for marker in SENSITIVE_SNIPPETS)


class AuditLog:
    """追加写 JSONL。读的时候按工牌过滤——员工不能翻管理员的账。

    ``path`` 是账本文件位置，不传就走 ``audit_path()``（``runtime/audit.jsonl``）；
    测试传临时路径就能各写各的，不碰课堂那份账。``_lock`` 用来挡多线程同时追加：
    服务端一个请求一个线程，一行 JSON 被两线程交错写进去就是一条坏账。
    """

    def __init__(self, path: str | Path | None = None) -> None:
        """记住账本位置并备好写锁；此时既不建目录也不碰文件。

        ``path`` 是账本文件位置，不传就走 ``audit_path()``（``runtime/audit.jsonl``）。
        文件由第一次 ``append`` 创建，所以构造账本对象本身没有任何副作用。
        """
        self.path = Path(path) if path else audit_path()
        self._lock = threading.Lock()

    def append(self, event: AuditEvent) -> AuditEvent:
        """把一条事件写成一行 JSON 追加到账本末尾，目录不存在就先建出来。

        ``event`` 是待落盘的事件对象；写出前走 ``event.as_dict()``，脱敏因此绕不过去。
        ``ensure_ascii=False`` 是为了让账本里的中文保持可读——课堂作业要直接 grep
        这本账，转义成 ``\\u65b0`` 就没法看了。返回原样的 ``event``，
        方便调用方接着用（例如回给页面做凭据）。
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event.as_dict(), ensure_ascii=False)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return event

    def record(
        self,
        action: str,
        user_id: str | Actor | None,
        *,
        conversation_id: str = "",
        run_id: str = "",
        status: str = "",
        routes: str = "",
        question: str = "",
        detail: str = "",
        extra: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """组装一条事件并落盘：全项目写审计都从这里过。

        ``action`` 必须是 ``AUDIT_ACTIONS`` 里的动作名，写错的当场抛 ``ValueError``——
        动作名是课堂作业的检索维度，放行错字等于把账本按坏键分堆。
        ``user_id`` 是提问人的工牌（id 字符串、``Actor``、None 都收，None 走默认工牌），
        这里解析一次就固化成快照字段，之后不再二次查身份。
        ``conversation_id`` / ``run_id`` / ``status`` / ``routes`` / ``question`` / ``detail``
        是可选补充，缺省为空串；``extra`` 是想额外记下的结构化数据，默认空字典。

        返回落盘后的 ``AuditEvent``，带生成好的 ``event_id`` 与时间戳。
        """
        if action not in AUDIT_ACTIONS:
            raise ValueError(f"未知审计动作：{action}")
        actor = resolve_actor(user_id)
        event = AuditEvent(
            event_id=f"evt_{uuid4().hex}",
            action=action,
            user_id=actor.user_id,
            actor_name=actor.display_name,
            role=actor.role,
            department=actor.department,
            created_at=_now(),
            conversation_id=conversation_id or "",
            run_id=run_id or "",
            status=status or "",
            routes=routes or "",
            question=mask_pii(question or ""),
            detail=mask_pii(detail or ""),
            extra=dict(extra or {}),
        )
        return self.append(event)

    def read(self, limit: int = 200) -> list[dict[str, Any]]:
        """读账本末尾的若干条；文件还不存在就返回空列表。

        ``limit`` 是最多读几条，取最新的那一头；小于 1 会被抬到 1，免得调用方传 0
        或负数时拿到一个既不是"全读"、也不是"不读"的怪结果。
        单行解析失败直接跳过而不是整本报错：账本只追加，半行 JSON 通常意味着
        上次进程被杀在写一半，为一行坏账废掉整本账是更糟的取舍。
        返回事件的原始字典列表，最新的排在最后。
        """
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        events = []
        for line in lines[-max(limit, 1):]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def for_actor(self, user_id: str | Actor | None, limit: int = 200) -> list[dict[str, Any]]:
        """按工牌过滤账本：管理员看全库，其他人只看自己那部分。

        ``user_id`` 是要查账的工牌；``limit`` 是最多返回几条（保留最新的一端）。
        非管理员先多取 ``limit * 4`` 条再过滤——课堂量级下"先读后筛"是够用的权衡，
        真要分页得学会话柜那样上 keyset 游标，这里不为它加一层 SQL。
        返回事件字典列表，最新的在最后；空列表表示这本账里没有这张工牌的事。
        """
        actor = resolve_actor(user_id)
        events = self.read(limit=max(limit, 1) * 4)
        if actor.role == "company_admin":
            return events[-limit:]
        return [item for item in events if item.get("user_id") == actor.user_id][-limit:]

    def sensitive_asks(self, user_id: str | Actor | None | str = None) -> list[dict[str, Any]]:
        """课堂作业：列出疑似越权提问。管理员看全库，其他人只看自己。

        ``user_id`` 是查账人的工牌，**不传（None）就直接扫全库**；传了则按 ``for_actor``
        的规矩来：管理员看全库，其他人只看自己那份。返回命中的事件字典列表，
        空列表表示账上没出现过敏感词。
        """
        events = self.for_actor(user_id, limit=500) if user_id is not None else self.read(limit=500)
        hits = []
        for item in events:
            blob = f"{item.get('question') or ''} {item.get('detail') or ''}"
            if any(marker in blob for marker in SENSITIVE_SNIPPETS):
                hits.append(item)
        return hits


_LOG: AuditLog | None = None
_LOCK = threading.Lock()


def get_audit() -> AuditLog:
    """取进程内的单例账本，第一次调用时才创建。

    每个请求都要写账，逐次新建 ``AuditLog`` 会把它的线程锁一起丢掉——锁丢了就挡不住
    两个请求交错写同一行。加锁创建是为了并发首调时也只建一个。返回共享的 ``AuditLog``。
    """
    global _LOG
    with _LOCK:
        if _LOG is None:
            _LOG = AuditLog()
        return _LOG


def reset_audit_for_tests() -> None:
    """测试夹具：丢掉进程单例，让下一条用例从干净状态开始。

    只清引用、不删文件——账本是"曾经发生过"的证据，测试也不该替它做删除决定。
    """
    global _LOG
    with _LOCK:
        _LOG = None
