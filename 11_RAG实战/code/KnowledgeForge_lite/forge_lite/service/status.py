"""status.py —— 运行时体检：装对了没有、索引新不新、会话柜里有什么。

蒸馏来源：完整版 health / ready 探针与运维面板。
对应教程：11.13。排障顺序应当是先看体检再问模型：

1. **索引层**：docstore 的 schema 和当前 ``INDEX_SCHEMA`` 一致吗？切块账本有没有？
   两套向量空间错配不报错，只会「悄悄变差」（11.13 的静默降级）。
2. **图谱层**：图存储里有几条边？种子在不在？第三路是不是一直靠垫底在跑？
3. **会话层**：各工牌各有多少会话——课上演越权时，能看出「谁真的问过」。
4. **账本层**：审计和缓存的条目数、schema 分布。

本模块只读不写：不重建索引、不清缓存、不碰会话柜正文。
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .. import config
from ..store.audit import AuditLog
from ..data.catalog import load_chunks
from ..store.conversations import ConversationStore
from ..core.identity import USERS, resolve_actor
from ..data.knowledge_graph import _triples_from_store, load_seed_triples
from ..store.query_cache import QueryCache


@dataclass
class DocumentRow:
    """索引层里的一行文档：账本键、它记的 schema、内容哈希前 8 位。

    ``source`` 是来源文件名（账本键）；``schema`` 是入库时写下的索引 schema，
    和当前 ``INDEX_SCHEMA`` 对不上就说明两套向量空间错配了；``hash_prefix``
    只取前 8 位——体检单上用来比对"这篇变没变"，不需要完整摘要。
    """

    source: str
    schema: str
    hash_prefix: str

    def as_dict(self) -> dict[str, Any]:
        """摊成扁平字典，字段与页面表格一一对应。"""
        return asdict(self)


@dataclass
class IndexSection:
    """索引层体检结果：账本有几条、schema 怎么分布、切块有多少。

    ``docstore_entries`` 是内容哈希账本的条目数；``schema_counts`` 是
    ``schema → 条目数`` 的分布（老格式条目单列成"（旧格式）"）；``chunks_total``
    是切块总数；``chunks_by_source`` 是 ``文件名 → 块数``；``documents`` 是逐篇明细；
    ``schema_stale`` 表示出现了当前 ``INDEX_SCHEMA`` 之外的 schema（静默降级的信号）；
    ``empty`` 表示账本和切块两边都空——这时问答只可能拒答。
    """

    docstore_entries: int = 0
    schema_counts: dict[str, int] = field(default_factory=dict)
    chunks_total: int = 0
    chunks_by_source: dict[str, int] = field(default_factory=dict)
    documents: list[DocumentRow] = field(default_factory=list)
    schema_stale: bool = False
    empty: bool = False

    def as_dict(self) -> dict[str, Any]:
        """摊成嵌套字典（``documents`` 逐行展开），供接口直接序列化。"""
        return {
            "docstore_entries": self.docstore_entries,
            "schema_counts": dict(self.schema_counts),
            "chunks_total": self.chunks_total,
            "chunks_by_source": dict(self.chunks_by_source),
            "documents": [row.as_dict() for row in self.documents],
            "schema_stale": self.schema_stale,
            "empty": self.empty,
        }


@dataclass
class GraphSection:
    """图谱层体检结果：第三路召回的那张图有多少边、种子占多少。

    ``total_triples`` 是图存储里的总边数（含种子）；``seed_triples`` 是种子事实条数；
    ``sources`` 是 ``文件名 → 边数``。``total_triples`` 一直等于 ``seed_triples``
    就说明图只靠垫底在跑，抽取那一步其实没产出。
    """

    total_triples: int = 0
    seed_triples: int = 0
    sources: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """摊成扁平字典；``sources`` 拷一份，免得调用方改到体检用的原对象。"""
        return {
            "total_triples": self.total_triples,
            "seed_triples": self.seed_triples,
            "sources": dict(self.sources),
        }


@dataclass
class ConversationSection:
    """会话层体检结果：每张工牌各开了几格柜子。

    ``per_badge`` 是 ``工牌 id → 柜子数``；``total`` 是合计数。课上演越权时，
    这张表就是"谁真的问过"的底账。
    """

    per_badge: dict[str, int] = field(default_factory=dict)
    total: int = 0

    def as_dict(self) -> dict[str, Any]:
        """摊成扁平字典；``per_badge`` 拷一份，避免外部改动影响后续渲染。"""
        return {"per_badge": dict(self.per_badge), "total": self.total}


@dataclass
class LedgerSection:
    """账本层体检结果：审计事件与精确缓存各有多少条目。

    ``audit_events`` 是审计事件条数（只读最近一批）；``audit_actions`` 是
    ``动作 → 次数`` 分布；``cache_entries`` 是缓存条目数；``cache_schemas`` 是
    ``schema → 条目数``——缓存不带 schema 口径的话，重建索引后会继续吐旧切块号。
    """

    audit_events: int = 0
    audit_actions: dict[str, int] = field(default_factory=dict)
    cache_entries: int = 0
    cache_schemas: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """摊成扁平字典，两个分布各拷一份。"""
        return {
            "audit_events": self.audit_events,
            "audit_actions": dict(self.audit_actions),
            "cache_entries": self.cache_entries,
            "cache_schemas": dict(self.cache_schemas),
        }


@dataclass
class RuntimeReport:
    """一次完整体检的结果：四层分节 + 给人看的建议 + 一句结论。

    ``index`` / ``graph`` / ``conversations`` / ``ledger`` 四节各自缺省为空节，
    所以没跑到的层会以"零"呈现而不是缺失；``notes`` 是排障建议（中文，能照着做）；
    ``healthy`` 只看索引层——索引空或 schema 漂移才算不健康，别的都属于"能跑但可以更好"。
    """

    index: IndexSection = field(default_factory=IndexSection)
    graph: GraphSection = field(default_factory=GraphSection)
    conversations: ConversationSection = field(default_factory=ConversationSection)
    ledger: LedgerSection = field(default_factory=LedgerSection)
    notes: list[str] = field(default_factory=list)
    healthy: bool = True

    def as_dict(self) -> dict[str, Any]:
        """摊成嵌套字典：四节各自 ``as_dict``，``notes`` 拷成列表供接口序列化。"""
        return {
            "index": self.index.as_dict(),
            "graph": self.graph.as_dict(),
            "conversations": self.conversations.as_dict(),
            "ledger": self.ledger.as_dict(),
            "notes": list(self.notes),
            "healthy": self.healthy,
        }


def _load_docstore(path: Path | None = None) -> dict:
    """读内容哈希账本；``path`` 为空时走 ``config.DOCSTORE_JSON``。

    与 ``ingest.load_docstore`` 的区别是这里**不抛异常**：体检是排障用的，
    账本文件缺失或写坏了正好是要报告的现象，不该让体检自己先崩掉，所以一律退回空字典。
    """
    target = Path(path) if path else config.DOCSTORE_JSON
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def inspect_index(chunks_path: Path | None = None, docstore_path: Path | None = None) -> IndexSection:
    """跑一次索引层体检，返回 ``IndexSection``。

    ``chunks_path`` 是切块账本路径（BM25 语料），``docstore_path`` 是内容哈希账本路径，
    两个都缺省走 ``config`` 里的正式路径；传参是为了让测试和文档区能指向别的目录，
    两边口径必须一致，否则"文档数"会各说各话。
    """
    section = IndexSection()
    docstore = _load_docstore(docstore_path)
    section.docstore_entries = len(docstore)
    schemas: Counter[str] = Counter()
    for source, entry in docstore.items():
        if isinstance(entry, dict):
            schemas[str(entry.get("schema") or "（未标注）")] += 1
            digest = str(entry.get("hash") or "")
        else:
            schemas["（旧格式）"] += 1
            digest = str(entry or "")
        section.documents.append(DocumentRow(source, str((entry or {}).get("schema") if isinstance(entry, dict) else ""), digest[:8]))
    section.schema_counts = dict(schemas)
    chunks = load_chunks(chunks_path)
    section.chunks_total = len(chunks)
    section.chunks_by_source = dict(Counter(str(chunk.get("source")) for chunk in chunks))
    section.schema_stale = any(name not in {config.INDEX_SCHEMA, "（未标注）", "（旧格式）"} for name in schemas)
    section.empty = not chunks and not docstore
    return section


def inspect_graph() -> GraphSection:
    """跑一次图谱层体检，返回 ``GraphSection``（总边数、种子条数、逐来源分布）。

    读的是"图存储 + 种子垫底"的合并结果：问答时看到的就是这一份，
    体检不该去看另一份更干净的图。
    """
    triples = _triples_from_store()
    section = GraphSection(total_triples=len(triples), seed_triples=len(load_seed_triples()))
    section.sources = dict(Counter(str(item.get("source") or "（未标注）") for item in triples))
    return section


def inspect_conversations(store: ConversationStore | None = None) -> ConversationSection:
    """按工牌数柜子。只调 ``count_for``，不读正文。

    ``store`` 是会话柜；不传就现开一个，用完全在 ``finally`` 里关掉——
    体检不该在服务器进程里留下一堆没关的连接。传进来的柜子由调用方负责关闭。
    """
    owns = store is None
    active = store or ConversationStore()
    section = ConversationSection()
    try:
        for actor in USERS.values():
            count = active.count_for(actor.user_id)
            section.per_badge[actor.user_id] = count
            section.total += count
    finally:
        if owns:
            active.close()
    return section


def inspect_ledger(audit: AuditLog | None = None, cache: QueryCache | None = None) -> LedgerSection:
    """跑一次账本层体检，返回 ``LedgerSection``。

    ``audit`` 是审计日志（不传就现开一个，只读最近 1000 条——体检看的是分布，
    不是全量对账）；``cache`` 是精确缓存，**不传就干脆不统计缓存**（报告里留 0），
    而不是替调用方开一个可能有副作用的缓存实例。
    """
    section = LedgerSection()
    log = audit or AuditLog()
    events = log.read(limit=1000)
    section.audit_events = len(events)
    section.audit_actions = dict(Counter(str(item.get("action") or "?") for item in events))
    if cache is not None:
        hits = cache.read_all()
        section.cache_entries = len(hits)
        section.cache_schemas = dict(Counter(hit.schema or "（未标注）" for hit in hits))
    return section


def build_report(
    *,
    chunks_path: Path | None = None,
    docstore_path: Path | None = None,
    store: ConversationStore | None = None,
    audit: AuditLog | None = None,
    cache: QueryCache | None = None,
) -> RuntimeReport:
    """跑一次全量体检，附上给人看的建议。

    ``chunks_path`` / ``docstore_path`` 是切块账本与内容哈希账本路径（缺省走 config）；
    ``store`` 是会话柜（不传就现开一个现关）；``audit`` 是审计日志；``cache`` 是精确缓存
    （不传就跳过缓存统计）。全部关键字传参，免得六个参数靠位置去记。

    返回 ``RuntimeReport``：四节体检结果 + ``notes`` 建议列表 + ``healthy`` 结论。
    """
    report = RuntimeReport()
    report.index = inspect_index(chunks_path, docstore_path)
    report.graph = inspect_graph()
    report.conversations = inspect_conversations(store)
    report.ledger = inspect_ledger(audit, cache)

    if report.index.empty:
        report.notes.append("索引是空的：先跑 `python scripts/01_ingest.py`，否则问答只有拒答。")
    if report.index.schema_stale:
        report.notes.append(
            f"docstore 里有旧 schema 的条目（当前 {config.INDEX_SCHEMA}）：重建索引，别让两套向量空间错配。"
        )
    if report.index.chunks_total and report.index.docstore_entries == 0:
        report.notes.append("有切块账本却没有内容哈希账本：确认入库脚本是否跑到写入那一步。")
    if report.graph.total_triples == 0:
        report.notes.append("图存储是空的：第三路召回想跑起来，入库时会垫种子三元组。")
    elif report.graph.seed_triples and report.graph.total_triples <= report.graph.seed_triples:
        report.notes.append("图谱目前只有种子垫底事实：想更丰富可以跑 `python scripts/05_build_graph.py`。")
    if report.conversations.total == 0:
        report.notes.append("会话柜还是空的：在页面上问一句，或跑 `python scripts/06_demo.py` 看离线走查。")
    report.healthy = report.index.empty is False and report.index.schema_stale is False
    return report


def render_report(report: RuntimeReport) -> str:
    """给人看的中文体检单。控制台和文档都读这一份，返回多行文本。

    ``report`` 是 ``build_report`` 的产物。建议段只在 ``notes`` 非空时逐条列出，
    空的时候写一句"一切正常"，让"没建议"和"忘了跑建议"看起来不一样。
    """
    lines: list[str] = []
    lines.append("KnowledgeForge Lite 运行时体检")
    lines.append("=" * 56)
    lines.append(f"[索引] 内容哈希账本 {report.index.docstore_entries} 条，"
                 f"切块 {report.index.chunks_total} 块")
    if report.index.schema_counts:
        pairs = "、".join(f"{name} × {count}" for name, count in sorted(report.index.schema_counts.items()))
        lines.append(f"       schema 分布：{pairs}（当前 {config.INDEX_SCHEMA}）")
    if report.index.chunks_by_source:
        for source, count in sorted(report.index.chunks_by_source.items()):
            lines.append(f"       · {source}：{count} 块")
    lines.append(f"[图谱] 三元组 {report.graph.total_triples} 条"
                 f"（其中种子垫底 {report.graph.seed_triples} 条）")
    for source, count in sorted(report.graph.sources.items()):
        lines.append(f"       · {source}：{count} 条边")
    lines.append(f"[会话] 柜子合计 {report.conversations.total} 格")
    for user_id, count in sorted(report.conversations.per_badge.items()):
        actor = resolve_actor(user_id)
        lines.append(f"       · {actor.display_name}（{user_id}）：{count} 格")
    lines.append(f"[账本] 审计 {report.ledger.audit_events} 条事件，"
                 f"精确缓存 {report.ledger.cache_entries} 条")
    if report.ledger.audit_actions:
        pairs = "、".join(f"{name}×{count}" for name, count in sorted(report.ledger.audit_actions.items()))
        lines.append(f"       动作分布：{pairs}")
    if report.ledger.cache_schemas:
        pairs = "、".join(f"{name}×{count}" for name, count in sorted(report.ledger.cache_schemas.items()))
        lines.append(f"       缓存 schema：{pairs}")
    lines.append("-" * 56)
    if report.notes:
        lines.append("建议：")
        for note in report.notes:
            lines.append(f"  ! {note}")
    else:
        lines.append("建议：一切正常，可以起服务答题了。")
    lines.append(f"结论：{'体检通过 ✅' if report.healthy else '需要处理 ⚠️'}")
    return "\n".join(lines)
