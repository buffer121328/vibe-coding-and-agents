"""
s02_data_pipeline.py
====================
11.2 配套代码：文档解析、清洗与切块
痛点：数据源又脏又乱 → 三步走「解析 → 清洗 → 切块」产出干净 Chunk 与元数据。
教学管道覆盖 md/txt/html/docx/文字层 PDF；扫描件/双栏/公式走可选的 MinerU 4.x（RAG_USE_MINERU=1）。
"""

import hashlib
import os
import re
import time
from pathlib import Path
from typing import Iterable, List

import numpy as np
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

TESTDATA_DIR = Path(__file__).with_name("testdata")
PDF_FIXTURE = TESTDATA_DIR / "差旅管理制度_2026.pdf"
SUPPORTED_SUFFIXES = {".md", ".txt", ".html", ".pdf", ".docx"}
# 写 PDF 时的兜底短页：真正检索用的是 testdata 里那份 14 页现行制度 PDF
PDF_FIXTURE_PAGES = [
    (
        "第 1 页\n"
        "星河科技差旅管理制度（2026 年 7 月版）\n"
        "文档编号：TRAVEL-2026-07  状态：现行  生效日期：2026-07-01\n"
        "一线城市包括北京、上海、广州、深圳。\n"
        "一线城市住宿费上限为每人每天 500 元。\n"
        "其他省会及计划单列市上限为 400 元。\n"
        "其他城市上限为 320 元。\n"
        "员工乘坐高铁原则上选择二等座。"
    ),
    (
        "第 2 页\n"
        "出差期间餐饮补贴为每人每天 150 元，无需另附餐饮发票。\n"
        "由客户统一提供全天餐食的日期不再发放餐饮补贴。\n"
        "差旅报销单须在返回常驻工作地后 5 个工作日内提交 OA。\n"
        "财务在材料齐全后 7 个工作日内完成审核。\n"
        "机密文件，严禁外传"
    ),
]


# ============ 1. 解析：按文件后缀自动选择解析器 ============
def _cjk_fontfile() -> str | None:
    """写 PDF 夹具时找一款系统里现成的中文字体，避免抽出来变成方框。"""
    candidates = [
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def _wrap_pdf_lines(text: str, max_chars: int = 36) -> list[str]:
    """按中文标点折行。页标题整行保留；数字和「元」不拆开。"""
    wrapped: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line or raw_line.startswith("## 第") or len(raw_line) <= max_chars:
            wrapped.append(raw_line)
            continue
        buf = raw_line
        while buf:
            if len(buf) <= max_chars:
                wrapped.append(buf)
                break
            cut = max_chars
            window = buf[:max_chars]
            for sep in "。；！？，、 ":
                idx = window.rfind(sep)
                if idx >= 12:
                    cut = idx + 1
                    break
            if cut < len(buf) and buf[cut:cut + 1] == "元" and cut > 0 and buf[cut - 1].isdigit():
                cut += 1
            wrapped.append(buf[:cut].rstrip())
            buf = buf[cut:].lstrip()
    return wrapped


def write_digital_pdf(path: Path, pages: list[str] | None = None) -> Path:
    """生成能选中复制的文字层 PDF。每一项从新页起写，超长自动续页。"""
    import pymupdf

    pages = pages or PDF_FIXTURE_PAGES
    path.parent.mkdir(parents=True, exist_ok=True)
    fontfile = _cjk_fontfile()
    tmp = path.with_suffix(".pdf.tmp")
    doc = pymupdf.open()
    fontsize = 11
    line_height = 16
    try:
        for body in pages:
            page = doc.new_page(width=595, height=842)
            fontname = "helv"
            if fontfile:
                page.insert_font(fontname="cjk", fontfile=fontfile)
                fontname = "cjk"
            y = 52
            for line in _wrap_pdf_lines(body):
                if y > 790:
                    page = doc.new_page(width=595, height=842)
                    if fontfile:
                        page.insert_font(fontname="cjk", fontfile=fontfile)
                    y = 52
                page.insert_text((48, y), line or " ", fontsize=fontsize, fontname=fontname)
                y += line_height
        try:
            doc.subset_fonts()
        except Exception:
            pass
        doc.save(tmp, deflate=True, garbage=4)
        tmp.replace(path)
    finally:
        doc.close()
        if tmp.exists() and tmp != path:
            tmp.unlink(missing_ok=True)
    return path


def write_text_pdf(path: Path, text: str) -> Path:
    """把带「## 第 N 页」的全文写入文字层 PDF；抽文本后仍按页标题切块。"""
    return write_digital_pdf(path, [text])


def write_docx(path: Path, text: str) -> Path:
    """每行一个段落，方便 round-trip 后还能看到「## 第 N 页」。"""
    try:
        from docx import Document as DocxDocument
    except ImportError as exc:
        raise NotImplementedError("写 Word 需要 python-docx，请先 pip install python-docx") from exc
    doc = DocxDocument()
    for line in text.splitlines():
        doc.add_paragraph(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    return path


def write_simple_html(path: Path, text: str, title: str = "") -> Path:
    """教学用的网页快照：带一点导航噪声，正文标题仍写成「## 第 N 页」。"""
    import html as html_lib

    chunks = [
        "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><title>",
        html_lib.escape(title or path.stem),
        "</title></head><body><nav>广告 | 登录 | 帮助中心</nav><article>",
    ]
    for line in text.splitlines():
        escaped = html_lib.escape(line)
        if line.startswith("## "):
            chunks.append(f"<h2>{escaped}</h2>\n")
        elif line.startswith("# "):
            chunks.append(f"<h1>{escaped}</h1>\n")
        elif not line.strip():
            chunks.append("<br/>\n")
        else:
            chunks.append(f"<p>{escaped}</p>\n")
    chunks.append("</article></body></html>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(chunks), encoding="utf-8")
    return path


def convert_text_to(path: Path, text: str) -> Path:
    """按目标后缀把同一份带页标题的文本写成 md/pdf/docx/html。"""
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path
    if suffix == ".pdf":
        return write_text_pdf(path, text)
    if suffix == ".docx":
        return write_docx(path, text)
    if suffix == ".html":
        return write_simple_html(path, text)
    raise ValueError(f"不支持写成 {suffix}")


def ensure_pdf_fixture() -> Path:
    """testdata 里那份差旅 PDF 就是现行 14 页检索原文。体积异常时不要用两页短夹具覆盖它。"""
    if PDF_FIXTURE.exists() and 200 < PDF_FIXTURE.stat().st_size < 2_000_000:
        return PDF_FIXTURE
    raise FileNotFoundError(
        f"缺少检索用 PDF：{PDF_FIXTURE}。请用 write_text_pdf() 从制度原文重建，不要回退成两页短夹具。"
    )


def try_mineru_markdown(path: Path, timeout_s: float = 8.0) -> str | None:
    """MinerU 4.x 可选路径。没装包、没起本地服务、超时，都返回 None。

    MinerU 4 不是「import 之后当场把 PDF 变成字符串」：库模式要先
    `mineru server start`，再用 DoclibClient 提交 ParseRequest。
    教学默认关掉，避免离线测试去连一个并不存在的本地服务。
    """
    try:
        from mineru import DoclibClient
        from mineru.doclib import ParseRequest
    except ImportError:
        return None
    try:
        client = DoclibClient()
        job = client.ensure_parse(ParseRequest(path=str(path), tier="standard"))
        deadline = time.time() + timeout_s
        wait_ids = list(getattr(job, "wait_parse_ids", None) or [])
        for pid in wait_ids:
            parse = client.get_parse(pid)
            while getattr(parse, "status", "") in ("pending", "parsing"):
                if time.time() > deadline:
                    return None
                time.sleep(0.4)
                parse = client.get_parse(pid)
        short_id = getattr(job, "short_id", None)
        if not short_id:
            return None
        content = client.read_content(f"doc:{short_id}/tier:standard/page:1")
        text = getattr(content, "content", None) or str(content)
        text = (text or "").strip()
        return text or None
    except Exception:
        return None


def extract_pdf_with_pymupdf(path: Path) -> str:
    """抽文字层 PDF。扫描件会得到空字符串，这时该换 MinerU，而不是硬切空块。"""
    try:
        import pymupdf
    except ImportError as exc:
        raise NotImplementedError("解析 PDF 需要 pymupdf，请先 pip install pymupdf") from exc
    with pymupdf.open(path) as doc:
        text = "\n".join(page.get_text("text") for page in doc).strip()
    if not text:
        raise ValueError(
            f"{path.name} 抽出来是空的：多半是扫描件或图片型 PDF。"
            "请改用 MinerU 4.x（见 11.2），不要把空文本切块入库。"
        )
    # 排版折行可能把「500」和「元」拆开，先拼回来再交给切块器
    text = re.sub(r"(\d)\s*\n\s*(元)", r"\1 \2", text)
    return text


def load_docx(path: Path) -> str:
    """Word 按段落拼回纯文本。教学语料把「## 第 N 页」写成普通段落，方便和 Markdown 共用切页规则。"""
    try:
        from docx import Document as DocxDocument
    except ImportError as exc:
        raise NotImplementedError("解析 Word 需要 python-docx，请先 pip install python-docx") from exc
    doc = DocxDocument(str(path))
    return "\n".join(paragraph.text for paragraph in doc.paragraphs)


def load_html(path: Path) -> str:
    """剥标签时在块级标签后补换行，避免「第 N 页」标题和正文粘成一行。"""
    import html as html_lib

    raw = path.read_text(encoding="utf-8")
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</(p|h1|h2|h3|h4|div|li|tr|article|section)>", "\n", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    return html_lib.unescape(raw)


def load_pdf(path: Path, prefer_mineru: bool | None = None) -> str:
    """PDF 双通道：环境变量打开时先试 MinerU，失败再退回 pymupdf。"""
    if prefer_mineru is None:
        prefer_mineru = os.getenv("RAG_USE_MINERU", "").strip().lower() in {"1", "true", "yes"}
    if prefer_mineru:
        mined = try_mineru_markdown(path)
        if mined:
            return mined
    return extract_pdf_with_pymupdf(path)


def load_text_by_ext(path: Path) -> str:
    """按后缀把文件变成统一纯文本。PDF 默认走 pymupdf；扫描件请开 MinerU。"""
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8")
    if suffix == ".html":
        return load_html(path)
    if suffix == ".pdf":
        return load_pdf(path)
    if suffix == ".docx":
        return load_docx(path)
    raise NotImplementedError(
        f"暂未实现 {suffix} 的解析器，教学管道目前覆盖 md/txt/html/docx/pdf"
    )


def resolve_corpus_file(root: Path, stem: str) -> Path:
    """按文件名（不含后缀）找 testdata 里的那一份，md/pdf/docx/html 均可。"""
    for suffix in (".md", ".pdf", ".docx", ".html", ".txt"):
        candidate = root / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"{root} 下找不到 {stem}.（md/pdf/docx/html）")


# ============ 2. 清洗：去噪 + 归一化 ============
NOISE_PATTERNS = [
    r"(?m)^第\s*\d+\s*页\s*$",     # 只删单独成行的页眉，例如「第 38 页」
    r"机密文件[，,]?严禁外传",      # 水印/免责声明
    r"\bPage\s+\d+\b",            # 英文分页
    r"^\s*[-–—]\s*\d+\s*[-–—]\s*$",  # 单独成行的页码
]


def clean_text(raw: str) -> str:
    text = raw
    for pat in NOISE_PATTERNS:
        text = re.sub(pat, "", text)
    text = re.sub(r"[ \t]+", " ", text)      # 多个空格/制表符压成一个空格
    text = re.sub(r"\n{3,}", "\n\n", text)   # 多余空行折叠
    text = text.replace("\u3000", " ")       # 全角空格归一
    return text.strip()


# ============ 3. 切块：递归字符切块（中文场景） ============
def make_splitter(chunk_size: int = 400, overlap: int = 60) -> RecursiveCharacterTextSplitter:
    """中文文档建议把 '。！？；' 加进分隔符，优先在句边界下刀，避免腰斩句子。"""
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
        length_function=len,
    )


# ============ 4. 组装完整管道 ============
def build_chunks(path: Path, source_name: str, category: str) -> List[Document]:
    raw = load_text_by_ext(path)
    cleaned = clean_text(raw)
    splitter = make_splitter()
    chunks = splitter.split_text(cleaned)
    source_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:16]
    return [
        Document(
            page_content=chunk,
            metadata={
                "source": source_name,
                "category": category,
                "source_hash": source_hash,
                "chunk_id": f"{source_hash}:{i}",
                "chunk_index": i,
                "total": len(chunks),
            },
        )
        for i, chunk in enumerate(chunks)
    ]


def corpus_quality_report(documents: Iterable[Document]) -> dict[str, float]:
    """给入库结果做基础体检；它只能发现格式异常，不能替代检索评测。"""
    docs = list(documents)
    lengths = [len(doc.page_content) for doc in docs]
    unique_ids = {doc.metadata.get("chunk_id") for doc in docs}
    sentence_ended = sum(doc.page_content.rstrip().endswith(tuple("。！？!?")) for doc in docs)
    return {
        "chunks": float(len(docs)),
        "mean_chars": sum(lengths) / len(lengths) if lengths else 0.0,
        "max_chars": float(max(lengths, default=0)),
        "sentence_end_rate": sentence_ended / len(docs) if docs else 0.0,
        "duplicate_id_rate": 1 - len(unique_ids) / len(docs) if docs else 0.0,
    }


def build_test_corpus(root: Path | None = None) -> List[Document]:
    """加载教程自带的多页测试语料，保留状态与来源级别供后续过滤。"""
    root = root or Path(__file__).with_name("testdata")
    configs = {
        "差旅管理制度_2026": ("制度", "active", "internal"),
        "差旅管理制度_2025_已废止": ("制度", "deprecated", "internal"),
        "办公设备故障手册": ("运维", "active", "internal"),
        "外部网页快照_含注入样本": ("外部网页", "quarantine", "external"),
    }
    result: List[Document] = []
    for stem, (category, status, trust) in configs.items():
        path = resolve_corpus_file(root, stem)
        chunks = build_chunks(path, path.name, category)
        for chunk in chunks:
            chunk.metadata.update({"status": status, "trust": trust})
        result.extend(chunks)
    return result


# ============ 5. 父子切块（ParentDocumentRetriever） ============
def demo_parent_document() -> None:
    """小个子撞门、大个子进门的父子检索。需要可用的 Embedding API Key。"""
    from langchain_classic.retrievers import ParentDocumentRetriever
    from langchain_classic.storage import InMemoryStore
    from langchain_chroma import Chroma
    from langchain_openai import OpenAIEmbeddings

    parent_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=80)
    child_splitter = RecursiveCharacterTextSplitter(chunk_size=160, chunk_overlap=20)

    vectorstore = Chroma(collection_name="parent_demo", embedding_function=OpenAIEmbeddings())
    docstore = InMemoryStore()  # 生产可换 Redis/SQLite，避免重启丢数据

    retriever = ParentDocumentRetriever(
        vectorstore=vectorstore,
        docstore=docstore,
        child_splitter=child_splitter,
        parent_splitter=parent_splitter,
    )
    print("已构建 ParentDocumentRetriever，调用 retriever.add_documents(...) 即可入库")


# ============ 6. 上下文检索：给每块补“上下文头”（11.2 进阶） ============
def build_context_header(title: str, section: str = "") -> str:
    """零成本结构化块头，例如“《2026 差旅制度》> 第二章 住宿标准”。"""
    header = f"《{title}》"
    if section:
        header = f"{header}> {section}"
    return header


def contextualize_chunks(
    full_doc: str,
    chunks: list[str],
    llm=None,
    title: str = "",
) -> list[str]:
    """上下文检索：入库前为每块补上下文头。

    - llm 为 None：零成本退化路径，只补结构化块头（离线可测，不碰 API）；
    - llm 不为 None：让模型结合全文为每块写一句话上下文头。整篇文档放在
      <doc> 标签、当前块放在 <chunk> 标签里，生产环境可复用 prompt caching
      把整篇文档缓存起来，避免每块重复付费。
    """
    if llm is None:
        header = build_context_header(title)
        return [f"{header}\n\n{chunk}" for chunk in chunks]

    enriched: list[str] = []
    for chunk in chunks:
        prompt = (
            f"<doc>\n{full_doc}\n</doc>\n"
            f"<chunk>\n{chunk}\n</chunk>\n"
            "用一句话说明这一块在全文中的位置与背景，只输出这句话。"
        )
        header = llm.invoke(prompt).content
        enriched.append(f"{header}\n\n{chunk}")
    return enriched


# ============ 7. 纯 numpy 的 k-means（RAPTOR 聚类用） ============
def kmeans_labels(vectors, k: int, iters: int = 20, seed: int = 0) -> list[int]:
    """教学版 k-means：够用于 RAPTOR 聚类，故不引入 sklearn。

    用 np.random.default_rng(seed) 初始化中心点以保证结果可复现；
    簇数多于样本数时直接返回全 0（退化成一个簇）。
    """
    points = np.asarray(vectors, dtype=float)
    if points.size == 0:
        return []
    if points.ndim == 1:
        points = points.reshape(-1, 1)
    n = points.shape[0]
    if k > n:
        return [0] * n
    k = max(1, k)
    if k == 1 or n == 1:
        return [0] * n

    rng = np.random.default_rng(seed)
    centers = points[rng.choice(n, size=k, replace=False)].copy()
    labels = np.zeros(n, dtype=int)
    previous = None
    for _ in range(iters):
        # 每个点到每个中心的欧氏距离，取最近的中心作为标签
        distances = np.linalg.norm(points[:, None, :] - centers[None, :, :], axis=2)
        labels = distances.argmin(axis=1)
        if previous is not None and np.array_equal(labels, previous):
            break
        previous = labels.copy()
        for cluster in range(k):
            members = points[labels == cluster]
            if len(members):            # 空簇保持原中心，避免除零
                centers[cluster] = members.mean(axis=0)
    return labels.tolist()


# ============ 8. RAPTOR：递归摘要树骨架 ============
def build_raptor_tree(
    leaves: list[str],
    embed_fn,
    summarize_fn,
    branch: int = 4,
    max_depth: int = 2,
) -> list[dict]:
    """自底向上建树：嵌入 → 聚类 → 逐簇摘要 → 再聚类，返回所有层的节点。

    每个节点形如 {"text": str, "level": int, "children": list[int]}，
    level=0 是叶子；children 存上一层节点在返回列表中的下标。
    embed_fn(list[str]) -> list[list[float]]、summarize_fn(list[str]) -> str
    都是注入进来的，测试时可用本地假函数，不依赖任何模型。
    """
    nodes: list[dict] = [{"text": text, "level": 0, "children": []} for text in leaves]
    current_indices = list(range(len(leaves)))

    for level in range(1, max_depth + 1):
        if len(current_indices) <= 1:      # 只剩根节点，树长完了
            break
        current_texts = [nodes[i]["text"] for i in current_indices]
        vectors = embed_fn(current_texts)
        cluster_count = max(2, -(-len(current_texts) // branch))   # 向上取整
        labels = kmeans_labels(vectors, cluster_count)

        next_indices: list[int] = []
        for cluster in range(cluster_count):
            members = [current_indices[i] for i, label in enumerate(labels) if label == cluster]
            if not members:                # 空簇不生成节点
                continue
            summary = summarize_fn([nodes[i]["text"] for i in members])
            nodes.append({"text": summary, "level": level, "children": members})
            next_indices.append(len(nodes) - 1)
        current_indices = next_indices
    return nodes


# ============ 9. 命题切块：规则版自包含命题（不需要 LLM） ============
REFERENTIAL_STARTERS = ("它", "他", "该", "此", "这")
# 教学近似：只抓“<= 6 字的疑似主语 + 常见谓语标记”，生产环境应交给 LLM 改写
SUBJECT_PATTERN = re.compile(
    r"([\u4e00-\u9fa5]{2,6})(?:规定|要求|标准|制度|条款|办法|时限|上限|费用|补贴|须|应当|为)"
)


def split_propositions(text: str) -> list[str]:
    """按中文句末标点（。！？；）切句，并对指代句做基本“自包含化”。

    “自包含化”是教学近似：若句子以“它/他/该/此/这”开头，就把上一句用正则
    抓到的疑似主语短语补到句首。真正的指代消解生产环境应交给 LLM，这里只是
    让学生看清“命题切块”在做什么。
    """
    sentences = [s.strip() for s in re.split(r"[。！？；]", text)]
    sentences = [s for s in sentences if s]

    propositions: list[str] = []
    subject = ""
    for sentence in sentences:
        starts_with_reference = sentence[0] in REFERENTIAL_STARTERS
        if starts_with_reference and subject:
            sentence = f"{subject}，{sentence}"
        propositions.append(sentence)
        if not starts_with_reference:      # 只用自带主语的句子更新“最近主语”
            match = SUBJECT_PATTERN.search(sentence)
            if match:
                subject = match.group(1)
    return propositions


# ============ 10. 11.2 进阶演示：块头 + RAPTOR + 命题切块（全程离线） ============
def demo_contextual_and_raptor() -> None:
    """不需要 API Key、不下载模型：块头/假向量建树/命题切块三件事都能跑。"""
    doc_path = resolve_corpus_file(
        Path(__file__).with_name("testdata") / "真实RAG演示文档",
        "02_差旅报销与发票制度_2026",
    )
    full_doc = clean_text(load_text_by_ext(doc_path))
    # 演示用细一点的块，便于看清块头与树的分层
    chunks = make_splitter(chunk_size=150, overlap=20).split_text(full_doc)

    print("\n=== 上下文检索：补块头（llm=None 的零成本路径） ===")
    enriched = contextualize_chunks(full_doc, chunks[:3], llm=None, title="差旅报销与发票制度 2026")
    for index, block in enumerate(enriched, start=1):
        header, _, body = block.partition("\n\n")
        print(f"[chunk {index}] {header}  ← 块头；正文首行：{body.splitlines()[0][:16]}…")

    print("\n=== RAPTOR：零依赖摘要树骨架（假向量 + 假摘要） ===")

    def fake_embed(texts: list[str]) -> list[list[float]]:
        """用字符码之和构造假向量，本地可复现，不调用任何 Embedding 模型。"""
        return [[float(sum(map(ord, text)) % 97), float(len(text))] for text in texts]

    def fake_summarize(texts: list[str]) -> str:
        return texts[0][:20] + "…"

    leaves = chunks
    tree = build_raptor_tree(leaves, fake_embed, fake_summarize, branch=3, max_depth=2)
    level_counts: dict[int, int] = {}
    for node in tree:
        level_counts[node["level"]] = level_counts.get(node["level"], 0) + 1
    detail = "，".join(f"level {level} 有 {count} 个节点" for level, count in sorted(level_counts.items()))
    print(f"叶子 {len(leaves)} 个，摘要树共 {len(level_counts)} 层：{detail}")

    print("\n=== 命题切块：规则版自包含命题 ===")
    sample = next((line for line in full_doc.splitlines() if "住宿标准为" in line), full_doc.splitlines()[0])
    for proposition in split_propositions(sample):
        print(f"- {proposition}")


if __name__ == "__main__":
    demo_contextual_and_raptor()   # 离线可跑：块头 + RAPTOR 摘要树 + 命题切块，不需要 API Key

    # 构造一份“带病”演示文档
    demo_doc = Path(__file__).with_name("_demo_dirty.md")
    demo_doc.write_text(
        "第 1 页\n"
        "【员工差旅管理制度】\n"
        "第一条 本制度适用于全体正式员工。\n"
        "第二条 一线城市住宿标准为每人每天不超过 500 元；二线城市不超过 350 元。\n"
        "第三条 出差餐饮补贴为每人每天 150 元，无需发票。\n"
        "机密文件，严禁外传\n"
        "第 2 页\n"
        "第四条 差旅报销单须在返回工作地后 5 个工作日内提交 OA 系统。\n",
        encoding="utf-8",
    )

    docs = build_chunks(demo_doc, "差旅制度_2026.md", "行政")
    print(f"共生成 {len(docs)} 个 Chunk")
    for d in docs:
        print(f"\n[chunk {d.metadata['chunk_index']}/{d.metadata['total']}] source={d.metadata['source']}")
        print(d.page_content)

    pdf_path = ensure_pdf_fixture()
    pdf_raw = load_text_by_ext(pdf_path)
    pdf_docs = build_chunks(pdf_path, pdf_path.name, "行政")
    print(f"\n=== PDF 解析（{pdf_path.name}，文字层 / pymupdf）===")
    print(f"抽出 {len(pdf_raw)} 字，切成 {len(pdf_docs)} 块")
    print(pdf_docs[0].page_content[:80].replace("\n", " ") + "…")

    corpus = build_test_corpus()
    print("\n=== 多页测试语料体检 ===")
    print(corpus_quality_report(corpus))

    demo_parent_document()
    try:
        demo_doc.unlink(missing_ok=True)
    except TypeError:
        if demo_doc.exists():
            demo_doc.unlink()
