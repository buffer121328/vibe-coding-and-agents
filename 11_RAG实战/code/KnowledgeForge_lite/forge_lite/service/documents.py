"""documents.py —— 文档区服务层：目录总览、上传入库、删除级联。

蒸馏来源：完整版 ``api/routers/documents`` + ``workflows/ingest_document.py``。
对应教程：11.2 / 11.4 / 11.13（解析切块 → 入库 → 增量同步与级联清理）。

这一层只做三件事，都要求"可解释"：

1. **总览**：每篇文档的部门/密级、切块数、内容哈希、索引状态、隔离原因；
   状态不是猜的——`docstore.json` 里记着 hash / schema / status / signals；
2. **上传**：扩展名与体积先卡一道，文件名只取 basename（挡住路径穿越），
   写入 `data/docs/` 后**只对这一篇**做嵌入与写入，其余文档不动；
3. **删除**：先删源文件，再让入库管道级联清掉向量与账本——不是手动删库，
   让"源文件是唯一事实来源"这条规矩在代码里成立。

隔离（投毒扫描命中）的文档仍然保留在账本里，状态记 ``quarantined`` 并附原因：
课堂上要看得见"它被挡下了"，而不是凭空消失。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .. import config
from ..data.catalog import load_chunks
from ..core.identity import DOC_POLICY, catalog_of
from ..data.ingest import accessions_of, content_hash, ingest, load_docstore

# 入库认这几种后缀；扫描件 PDF 会读出空文本并在上传时被挡下（提示走 MinerU）
ALLOWED_SUFFIXES = (".md", ".txt", ".html", ".docx", ".pdf")
MAX_UPLOAD_BYTES = 8 * 1024 * 1024          # 课堂体量：单篇 8MB
MAX_FILENAME_LENGTH = 80


class DocumentError(ValueError):
    """上传/删除的入参问题：后缀不许、体积超限、文件名非法。"""


class DocumentNotFound(LookupError):
    """文档不存在（或已被隔离/删除）。"""


@dataclass
class DocumentRow:
    """文档登记簿的一行，供文档区表格直接渲染。status 只有两种：indexed（进了检索）/ quarantined（被隔离）。

    ``source`` 是文件名（同时也是账本键、切块来源键）；``department`` 与
    ``department_label`` 是部门代号与其中文文案（如 ``it`` / "IT"），``sensitivity``
    与 ``sensitivity_label`` 同理（``restricted`` / "密级"）；``acl`` 是访问标签；
    ``accession`` 是登记号，入库时烙上、之后不动——它**不是行号**：删掉一篇不会让
    后面的号往前挪。"第几行"会随排序和增删变，登记号不会，这正是登记簿的意思。

    ``chunks`` 是这篇当前的切块数（隔离文档为 0）；``hash_prefix`` 是内容哈希前 8 位，
    够页面上比对"这篇变没变"；``schema`` 是入库时的索引 schema；``status`` 只有两种：
    ``indexed``（进了检索）/ ``quarantined``（被隔离）；``signals`` 是投毒
    扫描命中的原因；``bytes`` 是源文件体积（文件已不在就是 0）；``in_index`` 表示
    它的切块确实在 BM25 语料里——隔离文档为 False，这正是课堂上要看的那条分界。
    """

    source: str
    department: str
    department_label: str
    sensitivity: str
    sensitivity_label: str
    acl: str
    accession: int = 0
    chunks: int = 0
    hash_prefix: str = ""
    schema: str = ""
    status: str = "indexed"
    signals: list[str] = field(default_factory=list)
    bytes: int = 0
    in_index: bool = False

    def as_dict(self) -> dict[str, Any]:
        """摊成扁平字典交给页面/接口；字段多但不嵌套，前端不必再拆一层。"""
        return asdict(self)


def safe_filename(name: str) -> str:
    """把用户给的文件名削成可用名，返回清洗后的文件名；不合规抛 ``DocumentError``。

    ``name`` 是上传接口收到的原始文件名（不可信）。削平的顺序是：先取最后一段
    （``../../etc/passwd`` 到这里只剩 ``passwd``）、去掉空字节与两种斜杠、按长度砍一刀，
    最后卡后缀白名单。

    上传是唯一的写入口，文件名就是攻击面：取 basename 之后路径穿越这类输入在进入
    文件系统之前就已经不成立了——所以这里削的不只是"难看的字符"，是路径语义本身。
    """
    raw = Path(str(name or "")).name.strip()
    cleaned = raw.replace("\x00", "").replace("/", "").replace("\\", "")
    if not cleaned or cleaned in {".", ".."}:
        raise DocumentError("文件名不合法")
    if len(cleaned) > MAX_FILENAME_LENGTH:
        stem, dot, suffix = cleaned.rpartition(".")
        keep = MAX_FILENAME_LENGTH - len(suffix) - 1 if dot else MAX_FILENAME_LENGTH
        cleaned = f"{stem[:keep]}.{suffix}" if dot else cleaned[:MAX_FILENAME_LENGTH]
    if not cleaned.lower().endswith(ALLOWED_SUFFIXES):
        raise DocumentError(f"只收 {' / '.join(ALLOWED_SUFFIXES)}，收到 {cleaned}")
    return cleaned


def _label_maps() -> tuple[dict[str, str], dict[str, str]]:
    """取部门/密级两份中文文案表，返回 ``(部门文案, 密级文案)``。

    函数内 import 是为了不把 ``labels`` 拖进模块导入期，页面文案与这层解耦。
    """
    from ..core.labels import DEPARTMENT_LABELS, SENSITIVITY_LABELS
    return DEPARTMENT_LABELS, SENSITIVITY_LABELS


def _docstore_entry(docstore: dict, source: str) -> dict:
    """取 ``source`` 在账本 ``docstore`` 里的条目；缺条目或老格式一律回空字典。

    回空字典而不是 None，是为了让调用方写 ``entry.get(...)`` 时不必先判空——
    这里把"没有"和"字段没写"统一成同一件事。
    """
    entry = docstore.get(source)
    return entry if isinstance(entry, dict) else {}


def list_documents_admin(
    chunks_path: Path | None = None,
    docstore_path: Path | None = None,
    docs_dir: Path | None = None,
) -> list[DocumentRow]:
    """文档总览：账本 + 切块账 + 目录元数据三方对齐，缺一方就如实标出来。

    ``chunks_path`` 是切块账本路径（BM25 语料），``docstore_path`` 是内容哈希账本路径，
    两个都缺省走 ``config`` 里的正式路径——传参只为了测试能指向临时目录。
    ``docs_dir`` 是源文件目录，用来数每篇的实际体积、也用来把"目录里有、账本里没有"
    的文件捞出来显示（缺省 ``config.DOCS_DIR``）。

    ``in_index`` 表示这篇的切块确实在 BM25 语料里；隔离文档为 False——
    它在账本里，但不在检索索引里，这正是课堂上要看到的那条分界。
    """
    docs_dir = docs_dir or config.DOCS_DIR
    docstore = load_docstore() if docstore_path is None else (
        json.loads(Path(docstore_path).read_text(encoding="utf-8")) if Path(docstore_path).exists() else {}
    )
    chunks = load_chunks(chunks_path)
    per_source: dict[str, int] = {}
    for chunk in chunks:
        per_source[str(chunk.get("source"))] = per_source.get(str(chunk.get("source")), 0) + 1

    dept_labels, sens_labels = _label_maps()
    accessions = accessions_of(docstore)
    rows: list[DocumentRow] = []
    names = sorted(set(docstore) | set(per_source) | {
        path.name for path in docs_dir.iterdir() if path.is_file() and path.suffix.lower() in ALLOWED_SUFFIXES
    } if docs_dir.exists() else set(docstore) | set(per_source))
    for source in names:
        entry = _docstore_entry(docstore, source)
        policy = catalog_of(source)
        path = docs_dir / source
        # 状态以账本为准；账本没写（旧格式或还没入库）时按可观察事实推断：
        # 有信号就是被隔离，有切块就是已索引，其余老实标 unknown——不硬说"已索引"。
        recorded = str(entry.get("status") or "")
        if recorded:
            status = recorded
        elif entry.get("signals"):
            status = "quarantined"
        elif per_source.get(source):
            status = "indexed"
        else:
            status = "unknown"
        rows.append(DocumentRow(
            source=source,
            department=policy["department"],
            department_label=dept_labels.get(policy["department"], policy["department"]),
            sensitivity=policy["sensitivity"],
            sensitivity_label=sens_labels.get(policy["sensitivity"], policy["sensitivity"]),
            acl=policy["acl"],
            accession=accessions.get(source, 0),
            chunks=per_source.get(source, 0),
            hash_prefix=str(entry.get("hash") or "")[:8],
            schema=str(entry.get("schema") or ""),
            status=status,
            signals=[str(item) for item in (entry.get("signals") or [])],
            bytes=path.stat().st_size if path.exists() else 0,
            in_index=per_source.get(source, 0) > 0,
        ))
    # 隔离的排前面：课堂第一眼要看的就是「挡下了什么」。
    # 组内按登记号倒序——登记簿是新条目加在后面，读起来自然是倒着翻最近的那几页。
    rows.sort(key=lambda row: (row.status != "quarantined", -row.accession, row.source))
    return rows


def index_summary(
    chunks_path: Path | None = None,
    docstore_path: Path | None = None,
    docs_dir: Path | None = None,
) -> dict[str, Any]:
    """文档区顶部的体检条：可见文档数、切块总数、隔离数、schema 是否漂移。

    ``chunks_path`` / ``docstore_path`` 是切块账本与内容哈希账本的路径（缺省走 config），
    只为了测试能指向临时目录。

    ``docs_dir`` 必须一路往下传：不传就会落到 ``config.DOCS_DIR``，
    测试与多目录场景下会把别的目录的文档算进来（口径不一致比数字错更麻烦）。

    返回给页面直接显示的字典：``documents`` / ``indexed`` / ``quarantined`` /
    ``chunks`` / ``schema`` / ``schema_stale`` / ``empty`` / ``policies``。
    """
    from ..service.status import inspect_index
    section = inspect_index(chunks_path, docstore_path)
    rows = list_documents_admin(chunks_path, docstore_path, docs_dir)
    quarantined = [row for row in rows if row.status == "quarantined"]
    return {
        "documents": len(rows),
        "indexed": len([row for row in rows if row.in_index]),
        "quarantined": len(quarantined),
        "chunks": section.chunks_total,
        "schema": config.INDEX_SCHEMA,
        "schema_stale": section.schema_stale,
        "empty": section.empty,
        "policies": len(DOC_POLICY),
    }


def upload_document(filename: str, data: bytes, docs_dir: Path | None = None) -> dict[str, Any]:
    """写入一篇文档并只对它做入库。返回这一篇的入库结果。

    ``filename`` 是客户端给的原始文件名，先过 ``safe_filename`` 才碰文件系统；
    ``data`` 是文件字节（空文件直接拒），体积过 ``MAX_UPLOAD_BYTES`` 抛 ``DocumentError``；
    ``docs_dir`` 是落盘目录，缺省 ``config.DOCS_DIR``。文件名不合法或后缀不在白名单
    同样抛 ``DocumentError``。

    规矩：文件名清洗 → 体积校验 → 落盘 → ``ingest(only=[name])``。
    其它文档一律不重嵌入——课堂上传一篇不该等整个库重算。

    返回 ``source`` / ``replaced``（是否覆盖了同名文件）/ ``status`` / ``chunks`` /
    ``signals``，以及这一步的计数 ``stats``。
    """
    name = safe_filename(filename)
    if not data:
        raise DocumentError("空文件不入库")
    if len(data) > MAX_UPLOAD_BYTES:
        raise DocumentError(f"单篇最大 {MAX_UPLOAD_BYTES // 1024 // 1024}MB，收到 {len(data) / 1024 / 1024:.1f}MB")
    docs_dir = docs_dir or config.DOCS_DIR
    docs_dir.mkdir(parents=True, exist_ok=True)
    target = docs_dir / name
    existed = target.exists()
    target.write_bytes(data)

    stats = ingest(docs_dir=docs_dir, only=[name])
    files = {item["source"]: item for item in stats.get("files", [])}
    outcome = files.get(name, {})
    return {
        "source": name,
        "replaced": existed,
        "status": outcome.get("status", "unknown"),
        "chunks": outcome.get("chunks", 0),
        "signals": outcome.get("signals", []),
        "stats": {key: stats.get(key) for key in ("added", "updated", "skipped", "deleted", "quarantined")},
    }


def delete_document(source: str, docs_dir: Path | None = None) -> dict[str, Any]:
    """删源文件 → 入库管道级联清向量与账本。返回删除结果。

    ``source`` 是文件名（只取最后一段，挡住 ``../`` 这类写法）；``docs_dir`` 是源文件
    目录，缺省 ``config.DOCS_DIR``。文件不在目录里抛 ``DocumentNotFound``——
    先确认"要删的东西真的在"，再动手。

    删完立刻跑一次全量 ``ingest``：向量、账本、BM25 语料都由它级联清理，而不是在这里
    手动删库——这样"源文件是唯一事实来源"这条规矩在代码里始终成立。
    返回被删的文件名、级联清掉的条数与这一步的计数 ``stats``。
    """
    name = Path(str(source or "")).name
    docs_dir = docs_dir or config.DOCS_DIR
    target = docs_dir / name
    if not target.exists():
        raise DocumentNotFound(f"{name} 不在 data/docs 里")
    target.unlink()
    stats = ingest(docs_dir=docs_dir)
    return {
        "source": name,
        "deleted": stats.get("deleted", 0),
        "stats": {key: stats.get(key) for key in ("added", "updated", "skipped", "deleted", "quarantined")},
    }


def document_chunks(source: str, chunks_path: Path | None = None) -> list[dict[str, Any]]:
    """一篇文档在 BM25 语料里的全部切块，按 ``chunk_index`` 升序返回。

    ``source`` 是文件名（同样只取最后一段）；``chunks_path`` 是切块账本路径，
    缺省走 ``config`` 里的正式路径，传参只为了测试能指向临时目录。
    隔离文档返回空列表，因为它不在索引里——空列表本身就是"它被挡下了"的证据，
    不必再回一句"查不到"。

    每条带 ``heading``（这块属于哪一节），前端拿它标在块号旁边——学生看切块预览时
    最想问的就是"这块是从哪一段切下来的"，而那个信息切完就只存在这里了。
    """
    name = Path(str(source or "")).name
    return [
        {
            "chunk_index": int(chunk.get("chunk_index") or 0),
            "text": str(chunk.get("text") or ""),
            "heading": str(chunk.get("heading") or ""),
            "department": str(chunk.get("department") or ""),
            "sensitivity": str(chunk.get("sensitivity") or ""),
        }
        for chunk in sorted(
            (item for item in load_chunks(chunks_path) if str(item.get("source")) == name),
            key=lambda item: int(item.get("chunk_index") or 0),
        )
    ]


def preview_chunk_plan(text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[dict[str, Any]]:
    """切块预演：不落盘、不调模型，只按当前旋钮把一段文本切一遍。

    ``text`` 是待切文本（空串也没关系，会返回空列表）；``chunk_size`` 与 ``overlap``
    是两个旋钮，都不传就走 ``config`` 里的当前值，传了就用传的——``overlap`` 显式传 0
    也算"传了"，所以判据是 ``is not None`` 而不是真假。

    返回 ``[{chunk_index, chars, text}]``：段落原文照给，方便课堂上一眼看出切面。

    课堂上最有用的一个动作：把旋钮调小，让学生看见"同一篇文档被切成什么样"，
    再理解为什么 CHUNK_SIZE 属于**索引时旋钮**（改完必须重建，11.13）。
    """
    from ..data.ingest import make_splitter
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    if chunk_size or overlap:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size or config.CHUNK_SIZE,
            chunk_overlap=overlap if overlap is not None else config.CHUNK_OVERLAP,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
        )
    else:
        splitter = make_splitter()
    parts = splitter.split_text(text or "")
    return [
        {"chunk_index": index, "chars": len(part), "text": part}
        for index, part in enumerate(parts)
    ]


def summarize_upload_results(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """把多篇上传的结果收成一句人话，给页面顶部显示。

    ``results`` 是若干次 ``upload_document`` 的返回值（可迭代即可，这里会先落成列表）。
    返回 ``summary``（人话）、``indexed`` / ``quarantined`` 两个计数、``chunks``
    （只数入库成功那几篇的块数——被隔离的没有块，算进去会让数字虚高），
    以及原样的 ``items``。
    """
    items = list(results)
    ok = [item for item in items if item.get("status") == "indexed"]
    quarantined = [item for item in items if item.get("status") == "quarantined"]
    total_chunks = sum(int(item.get("chunks") or 0) for item in ok)
    parts = [f"入库 {len(ok)} 篇（{total_chunks} 块）"]
    if quarantined:
        parts.append(f"隔离 {len(quarantined)} 篇：{'、'.join(item['source'] for item in quarantined)}")
    return {"summary": "；".join(parts), "indexed": len(ok), "quarantined": len(quarantined),
            "chunks": total_chunks, "items": items}


def store_snapshot() -> dict[str, Any]:
    """账本原样快照，排障用：谁在里面、什么状态、源码页缺了谁。

    返回 ``entries``（按文件名排序的账本条目，**不做脱敏也不裁剪**）、当前
    ``schema``，以及 ``docs_dir`` / ``chunks_json`` 两个路径——排障时看不到路径，
    就没法判断刚才看的是不是同一个库。
    """
    docstore = load_docstore()
    return {
        "entries": {name: entry for name, entry in sorted(docstore.items())},
        "schema": config.INDEX_SCHEMA,
        "docs_dir": str(config.DOCS_DIR),
        "chunks_json": str(config.CHUNKS_JSON),
    }
