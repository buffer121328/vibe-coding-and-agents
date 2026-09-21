"""catalog.py —— 知识目录：工牌能看见哪些文档、点开哪一块原文。

蒸馏来源：完整版 documents catalog + ``docApi.chunks``（前端点引用去拉分块）。
对应教程：11.13（ACL 不只拦检索，预览原文也必须过同一把尺子）。

聊天页右侧「证据抽屉」不是另开一套权限。问句检索走 ``authorize_chunks``，
点角标跳原文也走 ``authorize_chunks``——否则员工搜不到密级，却能从抽屉里把密级读出来。
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .. import config
from ..core.identity import Actor, authorize_chunks, catalog_of, resolve_actor


@dataclass
class DocumentCard:
    """目录里的一张卡片：文件名、部门、密级、可见切块数。

    ``source`` 是文件名（也是切块的来源键）；``department`` 归属部门；
    ``sensitivity`` 密级（``public`` / ``department`` / ``restricted``）；
    ``acl`` 访问标签；``chunk_count`` 是**在这张工牌下**可见的切块数，不是文件总块数——
    数字变小本身就是权限生效的证据，课堂演示时正好拿它对照；``preview`` 是开头两块的
    截断预览（够一眼认出是哪篇，不必拉全文）；``trust`` 是来源可信度，入库时由投毒
    扫描那侧打上，缺省 ``internal``。
    """

    source: str
    department: str
    sensitivity: str
    acl: str
    chunk_count: int
    preview: str
    trust: str = "internal"

    def as_dict(self) -> dict[str, Any]:
        """转成给前端的扁平字典：卡片字段逐个摊平，没有嵌套。"""
        return asdict(self)


@dataclass
class ChunkPreview:
    """一块原文。前端点 [n] 角标就打开这一块，高亮命中句。

    ``source`` 是文件名，``chunk_index`` 是这一块在文件里的序号（两者合起来才是全局唯一
    的 ``文件名#切块号``）；``text`` 是正文；``department`` / ``sensitivity`` / ``acl``
    是随块带出的权限三件套，前端据此在抽屉里显示密级标；``key`` 是拼好的身份钥匙，
    构造时自动补，调用方不用自己拼（手拼最容易漏掉 ``#`` 或写成 1 起始的序号）。
    """

    source: str
    chunk_index: int
    text: str
    department: str
    sensitivity: str
    acl: str
    key: str = ""

    def __post_init__(self) -> None:
        """没给 ``key`` 就自动拼上，让"身份钥匙"的拼法只有这一处定义。

        调用方显式传了 ``key`` 就不覆盖（少数场景下要用检索那侧的原字符串）。
        """
        if not self.key:
            self.key = f"{self.source}#{self.chunk_index}"

    def as_dict(self) -> dict[str, Any]:
        """转成给前端的扁平字典，含自动补好的 ``key``，供页面直接拿去请求原文。"""
        return asdict(self)


@dataclass
class CatalogSnapshot:
    """一次目录查询的完整结果：谁的视角、看到哪些文档、被挡了几篇。

    ``actor`` 是提问人的四个字段（``user_id`` / ``name`` / ``role`` / ``department``），
    随目录一起返回是为了让页面能写出"当前以 IT 员工身份浏览"——否则用户看到的文档数
    和预期的对不上时，没人知道是库空还是权限裁的。``documents`` 是可见文档卡片列表
    （按文件名排序）；``hidden_count`` 是被这张工牌挡掉的文档数，只给**数量**不给
    文件名：列出来就等于泄露了"存在什么文件"。
    """

    actor: dict[str, str]
    documents: list[DocumentCard] = field(default_factory=list)
    hidden_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        """转成给前端的字典；顺手补一个 ``visible_count``，前端不必自己数列表长度。"""
        return {
            "actor": self.actor,
            "documents": [item.as_dict() for item in self.documents],
            "hidden_count": self.hidden_count,
            "visible_count": len(self.documents),
        }


def load_chunks(path: str | Path | None = None) -> list[dict]:
    """读 BM25 同源语料。没有入库就空列表——目录空着比抛 500 更诚实。

    ``path`` 是切块 JSON 的路径，不传就用 ``config.CHUNKS_JSON``；测试传临时文件，
    不必碰真实语料。返回 ``[{source, chunk_index, text, ...}]``，只保留带 ``source``
    的字典条目——缺来源的块没资格进权限判断（认不出归属就没法裁），宁可丢掉。

    读法上有意"宽容"：文件不存在、JSON 坏掉、顶层不是列表，统统返回空列表而不是
    抛异常。目录页在还没入库时也要能打开，显示"暂无文档"远好过给用户一个 500。
    """
    target = Path(path) if path else config.CHUNKS_JSON
    if not target.exists():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict) and item.get("source")]


def _stamp_policy(chunk: dict) -> dict:
    """旧索引可能缺部门/密级。读目录时按文件名补齐，避免漏标变成全员可见。

    ``chunk`` 是语料里的原始切块字典。用 ``setdefault`` 而不是直接赋值：索引里已经
    标好的权限以它为准，这里只补缺的——不然重新入库一次就会把人工标注的密级抹掉。

    返回补齐后的新字典，原字典不动。所有读语料的路径（列表、预览、检索）都要先过它，
    否则某个入口漏了补标，同一块资料在不同页面上会显示成不同权限。
    """
    policy = catalog_of(str(chunk.get("source") or ""))
    stamped = dict(chunk)
    stamped.setdefault("department", policy["department"])
    stamped.setdefault("sensitivity", policy["sensitivity"])
    stamped.setdefault("acl", policy["acl"])
    return stamped


def visible_chunks(user_id: str | Actor | None, chunks: list[dict] | None = None) -> list[dict]:
    """目录、预览、角标跳原文，全部走检索同一把 authorize_chunks。

    ``user_id`` 是工牌 id（也可以是 ``Actor`` 或 None，交给 ``resolve_actor`` 解析）；
    ``chunks`` 是可选的切块列表，不传就现场 ``load_chunks()``。传进来主要是为了测试
    和已入库那一跑复用同一份语料，省一次磁盘读。

    返回该工牌可见的切块列表。刻意不提供"先取后过滤"的变体：一旦有第二个入口，
    迟早会有人图省事用它，密级就成了摆设。
    """
    corpus = [_stamp_policy(item) for item in (chunks if chunks is not None else load_chunks())]
    return authorize_chunks(corpus, user_id)


def _preview_of(texts: Iterable[str], limit: int = 80) -> str:
    """把几段正文压成一行预览，先用空白归一化再截断。

    ``texts`` 是要拼接的文本片段（一般取文件开头一块或两块），``limit`` 是字符上限，
    默认 80。归一化空白是为了让卡片高度一致——原文里的换行和缩进会把预览撑成
    高低不齐的几行，列表页看着像坏了。返回截断后的单行字符串，不补省略号：
    截断位置看起来自然比加个"…"更像原句。
    """
    joined = " ".join(" ".join(text.split()) for text in texts if text)
    return joined[:limit]


def list_documents(user_id: str | Actor | None, chunks: list[dict] | None = None) -> CatalogSnapshot:
    """按工牌列出可见文档。hidden_count 告诉课堂：不是库空，是工牌裁过。

    ``user_id`` 是工牌 id（``Actor`` 或 None 也认）；``chunks`` 可选，不传就现场读语料。

    返回 ``CatalogSnapshot``。文档按文件名排序、每篇按 ``chunk_index`` 排序后再取前两块
    做预览——顺序不能靠语料里恰好排对了，否则同一份数据在两次入库后可能显示不同的预览。
    ``hidden_count`` 用原始文档数减可见文档数算，不减切块数：卡片的粒度是文件。
    """
    actor = resolve_actor(user_id)
    raw = [_stamp_policy(item) for item in (chunks if chunks is not None else load_chunks())]
    visible = authorize_chunks(raw, actor)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for chunk in visible:
        grouped[str(chunk["source"])].append(chunk)
    cards = []
    for source in sorted(grouped):
        group = sorted(grouped[source], key=lambda item: int(item.get("chunk_index") or 0))
        policy = catalog_of(source)
        cards.append(DocumentCard(
            source=source,
            department=str(group[0].get("department") or policy["department"]),
            sensitivity=str(group[0].get("sensitivity") or policy["sensitivity"]),
            acl=str(group[0].get("acl") or policy["acl"]),
            chunk_count=len(group),
            preview=_preview_of(item.get("text") or "" for item in group[:2]),
            trust=str(group[0].get("trust") or "internal"),
        ))
    hidden = len({str(item.get("source")) for item in raw}) - len(cards)
    return CatalogSnapshot(
        actor={
            "user_id": actor.user_id,
            "name": actor.display_name,
            "role": actor.role,
            "department": actor.department,
        },
        documents=cards,
        hidden_count=max(hidden, 0),
    )


def get_chunk(
    source: str,
    chunk_index: int,
    user_id: str | Actor | None,
    chunks: list[dict] | None = None,
) -> ChunkPreview | None:
    """按 文件名#切块号 取一块。看不见就当这块不存在，不报『权限拒绝』细节。

    ``source`` 是文件名，``chunk_index`` 是块序号，``user_id`` 是工牌（``Actor`` / id /
    None），``chunks`` 可选传语料、不传现场读。返回 ``ChunkPreview``；看不见或不存在
    都返回 None。

    这里**故意不区分**"没有这块"和"你没权限看这块"：两者返回同一个 None，前端都显示
    "找不到该片段"。区分开就等于告诉低权限用户"这里有个文件叫财务薪酬密级.md"，
    权限门禁变成了文档名探测器。
    """
    for chunk in visible_chunks(user_id, chunks):
        if str(chunk.get("source")) == source and int(chunk.get("chunk_index") or 0) == int(chunk_index):
            return ChunkPreview(
                source=source,
                chunk_index=int(chunk_index),
                text=str(chunk.get("text") or ""),
                department=str(chunk.get("department") or ""),
                sensitivity=str(chunk.get("sensitivity") or ""),
                acl=str(chunk.get("acl") or ""),
            )
    return None


def parse_doc_id(doc_id: str) -> tuple[str, int] | None:
    """把 ``员工差旅管理制度.md#2`` 拆成 (文件名, 切块号)。拆不开返回 None。

    ``doc_id`` 是引用角标回映射出来的 id。用 ``rpartition`` 从右往左找最后一个 ``#``：
    文件名里本身可能带 ``#``，从左切会把文件名截断，切块号反而是确定在末尾的。

    返回 ``(文件名, 块序号)``；没有 ``#``、``#`` 前为空、或后半段不是整数时返回 None——
    这类 id 来自模型或前端，形状不可信，宁可判为无效也不猜。
    """
    text = (doc_id or "").strip()
    if "#" not in text:
        return None
    source, _, index = text.rpartition("#")
    if not source:
        return None
    try:
        return source, int(index)
    except ValueError:
        return None


def get_chunk_by_doc_id(
    doc_id: str,
    user_id: str | Actor | None,
    chunks: list[dict] | None = None,
) -> ChunkPreview | None:
    """按 ``文件名#切块号`` 取一块原文，是 ``get_chunk`` 的字符串版入口。

    ``doc_id`` 是前端传来的复合 id（``parse_doc_id`` 拆不开就当无效返回 None）；
    ``user_id`` 是工牌（``Actor`` / id / None）；``chunks`` 可选传语料。

    返回 ``ChunkPreview`` 或 None（不存在与无权限都归为 None）。做成独立函数而不是让
    前端自己拆 id，是为了让"点角标跳原文"这条路径只有一处解析逻辑：拆错了就会去查
    另一篇文档的同一块，跳过去还能正常显示，没人会发现跳错了。
    """
    parsed = parse_doc_id(doc_id)
    if parsed is None:
        return None
    source, index = parsed
    return get_chunk(source, index, user_id, chunks)


def list_chunks_of(
    source: str,
    user_id: str | Actor | None,
    chunks: list[dict] | None = None,
) -> list[ChunkPreview]:
    """某篇文档在这张工牌下的全部切块，按 chunk_index 排序。

    ``source`` 是文件名，``user_id`` 是工牌（``Actor`` / id / None），``chunks`` 可选传
    语料、不传现场读。返回 ``ChunkPreview`` 列表，看不见这篇就返回空列表。

    先过滤再排序：排序只保证同一篇内部的阅读顺序，不负责"哪些该出现"。
    目录侧展开长文档时用它逐块渲染，所以这里也必须过 ``visible_chunks``——
    密级文档只挡检索、不挡逐块读取的话，前端换个接口就能把整篇刷出来。
    """
    previews = []
    for chunk in visible_chunks(user_id, chunks):
        if str(chunk.get("source")) != source:
            continue
        previews.append(ChunkPreview(
            source=source,
            chunk_index=int(chunk.get("chunk_index") or 0),
            text=str(chunk.get("text") or ""),
            department=str(chunk.get("department") or ""),
            sensitivity=str(chunk.get("sensitivity") or ""),
            acl=str(chunk.get("acl") or ""),
        ))
    previews.sort(key=lambda item: item.chunk_index)
    return previews


def highlight_span(text: str, needle: str, radius: int = 40) -> dict[str, str]:
    """给证据抽屉做『命中句前后各留一点』。找不到就返回原文开头。

    ``text`` 是整块原文，``needle`` 是要高亮的片段（一般是用户问句或关键词），
    ``radius`` 是命中处前后各留多少字符，默认 40——够看半句话的上下文，又不至于
    把抽屉撑成整篇。

    返回 ``{"before", "hit", "after", "index"}``：前三段拼起来就是高亮显示的内容，
    ``index`` 是命中位置（字符串形式的整数，没命中记 ``"-1"``，便于前端判断要不要
    显示"未找到命中位置"）。先精确匹配、再小写匹配：大小写不同也不该判成"没命中"。
    """
    body = text or ""
    query = (needle or "").strip()
    if not query:
        return {"before": "", "hit": "", "after": body[: radius * 2], "index": "-1"}
    index = body.find(query)
    if index < 0:
        lowered = body.lower()
        index = lowered.find(query.lower())
    if index < 0:
        return {"before": "", "hit": "", "after": body[: radius * 2], "index": "-1"}
    start = max(0, index - radius)
    end = min(len(body), index + len(query) + radius)
    return {
        "before": body[start:index],
        "hit": body[index:index + len(query)],
        "after": body[index + len(query):end],
        "index": str(index),
    }
