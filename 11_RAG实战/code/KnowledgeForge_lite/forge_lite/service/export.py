"""export.py —— 会话导出：把一个会话摊成 Markdown / JSON，带引用和轨迹。

蒸馏来源：完整版会话详情页的「导出」动作。
对应教程：11.13。课堂用途很实在：作业要交一次完整问答记录，或者贴到复盘文档里。

规矩：

- **只导自己的会话**：导出前先过 ``ConversationStore.get_conversation``，
  别人的会话拿不到正文，导出的就只是失败；
- **脱敏**：导出的对象里可能带 warn 里的电话邮箱，写文件前过 ``mask_pii``；
- **不掺模型**：纯 Markdown 组装，导出的东西可复现，不依赖再调一次 LLM。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from ..store.conversations import ConversationDetail, ConversationStore
from ..core.evidence import status_label
from ..core.quality import mask_pii


RESERVED_CHARS = r'<>:"/\\|?*\x00-\x1f'
UNSAFE_NAME = re.compile(f"[{RESERVED_CHARS}]")


def safe_filename(title: str, fallback: str = "conversation", limit: int = 40) -> str:
    """把会话标题变成可用文件名。空标题、纯符号都回落到 fallback。

    ``title`` 是会话标题（用户自己起的，什么字符都可能有）；``fallback`` 是标题被洗空
    （或本身为空）时的兜底名；``limit`` 是最终文件名的字符数上限——超了直接截断，
    不保留扩展名，因为扩展名是后面拼的，不在这条路径上。

    洗掉的字符见 ``RESERVED_CHARS``：Windows 与 POSIX 两边都不能出现在文件名里的那些。
    返回的是**不带扩展名的主干**，``.md`` / ``.json`` 由 ``build_export`` 拼。
    """
    text = UNSAFE_NAME.sub("", str(title or "")).strip().strip(".")
    text = re.sub(r"\s+", "-", text)
    if not text:
        text = fallback
    return text[:limit]


def _mask(value: Any) -> Any:
    """对 ``value`` 脱敏：字符串走 ``mask_pii``，非字符串原样返回。

    只处理字符串是因为导出对象里混着数字、布尔和 None——它们不可能夹带电话邮箱，
    没必要为它们编一个"脱敏后的数字"出来。
    """
    if isinstance(value, str):
        return mask_pii(value)
    return value


@dataclass
class ExportBundle:
    """一次导出：文件名、正文、以及给程序消费的结构。

    ``filename`` 是建议的文件名（已带 ``.md`` / ``.json``）；``content`` 是给人读的正文；
    ``media_type`` 是响应头要写的 MIME；``payload`` 是同一份内容的结构化版本——
    ``as_dict`` 特意**不带 content**，因为页面只需要文件名和 payload，正文由下载响应
    单独发，塞进 JSON 会让日志里多出一整篇问答复本。
    """

    filename: str
    content: str
    media_type: str
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """给接口/页面用的元信息：文件名、MIME、结构化 payload（不含正文）。"""
        return {
            "filename": self.filename,
            "media_type": self.media_type,
            "payload": self.payload,
        }


def detail_as_dict(detail: ConversationDetail | Mapping[str, Any]) -> dict[str, Any]:
    """把 ``detail`` 统一成字典：对象走 ``as_dict()``，已经是映射的浅拷一份。

    浅拷是为了后面可能加字段时不改到调用方的对象；两个分支合流之后，下面的渲染函数
    就只需要认字典一种形状。
    """
    if isinstance(detail, ConversationDetail):
        return detail.as_dict()
    return dict(detail)


def render_markdown(detail: ConversationDetail | Mapping[str, Any]) -> str:
    """一问一答带引用与轨迹，供人读。``detail`` 是会话详情对象或同形状的字典。

    返回整篇 Markdown 文本（结尾带换行）。正文与提示统一过 ``_mask`` 脱敏——
    导出文件会被贴进作业和复盘文档，这一步不能省。
    """
    data = detail_as_dict(detail)
    conversation = data.get("conversation") or {}
    messages = data.get("messages") or []
    runs = list(data.get("runs") or [])
    lines: list[str] = []
    title = str(conversation.get("title") or "未命名会话")
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- 会话编号：`{conversation.get('id') or '-'}`")
    lines.append(f"- 工牌：`{conversation.get('user_id') or '-'}`")
    lines.append(f"- 创建：{conversation.get('created_at') or '-'}")
    lines.append(f"- 最近更新：{conversation.get('updated_at') or '-'}")
    lines.append("")
    if not messages:
        lines.append("_这个会话还没有消息。_")
        return "\n".join(lines) + "\n"

    run_by_message = _runs_by_marker(runs)
    for message in messages:
        role = str(message.get("role") or "")
        content = _mask(message.get("content") or "")
        stamp = str(message.get("created_at") or "")
        if role == "user":
            lines.append(f"## 问 · {stamp}")
            lines.append("")
            lines.append(content.strip() or "_（空）_")
            lines.append("")
            continue
        lines.append(f"## 答 · {stamp}")
        lines.append("")
        lines.append(content.strip() or "_（空）_")
        lines.append("")
        citations = list(message.get("citations") or [])
        if citations:
            lines.append("出处：")
            for item in citations:
                marker = item.get("marker") or ""
                doc_id = item.get("doc_id") or "（未标注）"
                lines.append(f"- {marker} `{doc_id}`")
            lines.append("")
        run = run_by_message.get(str(message.get("id") or "")) or {}
        meta = _run_summary(run or message)
        if meta:
            lines.append(meta)
            lines.append("")
    if runs:
        lines.append("---")
        lines.append("")
        lines.append(f"_本次导出含 {len(runs)} 条运行记录；轨迹摘要见每段答案下方。_")
    return "\n".join(lines).rstrip() + "\n"


def _runs_by_marker(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """把 run 挂到助手消息上。会话柜里 run 行与助手消息共享 run_id。

    ``runs`` 是这次会话的全部 run 行，返回 ``run_id → run`` 的表；没有 id 的行直接丢掉，
    免得后面用空串当键把不同的 run 串在一起。
    """
    table: dict[str, dict[str, Any]] = {}
    for run in runs:
        key = str(run.get("id") or "")
        if key:
            table[key] = run
    return table


def _run_summary(run: Mapping[str, Any]) -> str:
    """把一行 run 压成一句引用块（状态 / 路由 / 提示），没有可写的内容就返回空串。

    ``run`` 既可能是会话柜里的 run 行，也可能是消息自带的 ``payload``：两处的字段名
    不完全一样，所以每个字段都按"先顶层、后 payload"的顺序找，找不到就跳过。
    返回空串而不是"状态：无"这种做法——渲染方靠空串判断"这行不必出现"。
    """
    parts = []
    status = run.get("status") or (run.get("payload") or {}).get("status")
    if status:
        parts.append(f"状态：{status_label(str(status))}")
    routes = run.get("routes") or (run.get("payload") or {}).get("routes")
    if routes:
        parts.append(f"路由：{routes}")
    warn = run.get("warn") or (run.get("payload") or {}).get("warn")
    if warn:
        parts.append(f"提示：{_mask(warn)}")
    if not parts:
        return ""
    return "> " + " ｜ ".join(str(part) for part in parts)


def render_json(detail: ConversationDetail | Mapping[str, Any]) -> str:
    """``detail`` 是会话详情对象或同形状字典，返回脱敏后的 JSON 字符串（缩进 2）。

    走 ``_walk`` 逐层脱敏而不是只处理顶层字符串：正文可能藏在 payload 的任意一层里，
    漏一层就等于把电话邮箱导出去了。
    """
    data = detail_as_dict(detail)
    safe = _walk(data)
    return json.dumps(safe, ensure_ascii=False, indent=2)


def _walk(value: Any) -> Any:
    """递归脱敏 ``value``：字符串过 ``_mask``，字典与列表逐层下钻，其余原样返回。

    返回的是新对象，原 ``value`` 不被改动——导出是只读动作，不该在会话柜的数据上留痕。
    """
    if isinstance(value, str):
        return _mask(value)
    if isinstance(value, Mapping):
        return {str(key): _walk(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_walk(item) for item in value]
    return value


def build_export(
    store: ConversationStore,
    conversation_id: str,
    user_id: str,
    fmt: str = "md",
) -> ExportBundle:
    """导出前先按工牌取会话。取不到会抛 ConversationError，交给接口翻 404。

    ``store`` 是会话存储（取会话时会按工牌核一遍，别人的在这里就拿不到）；
    ``conversation_id`` 是会话编号；``user_id`` 是请求者的工牌，也是权限判据；
    ``fmt`` 只有 ``"json"`` 一个特殊值，其余（含缺省 ``"md"``）都走 Markdown。

    返回 ``ExportBundle``：文件名取自会话标题（经 ``safe_filename`` 洗过），
    ``payload`` 里的字符串同样已脱敏。
    """
    detail = store.get_conversation(conversation_id, user_id)
    conversation = detail.conversation
    stem = safe_filename(conversation.title)
    if fmt == "json":
        return ExportBundle(
            filename=f"{stem}.json",
            content=render_json(detail),
            media_type="application/json",
            payload=_walk(detail.as_dict()),
        )
    return ExportBundle(
        filename=f"{stem}.md",
        content=render_markdown(detail),
        media_type="text/markdown; charset=utf-8",
        payload=_walk(detail.as_dict()),
    )
