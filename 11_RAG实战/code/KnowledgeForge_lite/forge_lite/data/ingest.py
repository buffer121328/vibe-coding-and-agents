"""ingest.py —— 数据管道：解析 → 清洗 → 切块 → 投毒扫描 → 三路写入。

蒸馏来源：完整版 agents/document_parser + workflows/ingest_document.py。
对应教程：11.2（解析切块 / 零成本上下文头）、11.4（Chroma 入库）、
11.13（内容哈希幂等同步 + 入库侧投毒扫描 + 部门/密级元数据）。
教学版吃 Markdown/文本/HTML/Word/文字层 PDF；扫描件、双栏、表格、公式走教程 11.2 的 MinerU 4.x 分流。
"""

import hashlib
import json
import re
from pathlib import Path

from .. import config
from ..core.chunking import chunk_document
from ..core.identity import catalog_of
from ..core.quality import scan_poisoning

# 与 s02 对齐：只删单独成行的页码，不要误伤「## 第 N 页」标题
NOISE_PATTERNS = [
    r"(?m)^第\s*\d+\s*页\s*$",
    r"机密文件[，,]?严禁外传",
    r"\bPage\s+\d+\b",
    r"^\s*[-–—]\s*\d+\s*[-–—]\s*$",
]

# 控制字符（换行和制表符除外）：Word 复制、PDF 抽取常带进来，肉眼看不见但会
# 让「同一句话」的哈希对不上，也会污染分词。
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# 横向空白：半角空格、制表符、全角空格（U+3000）、不换行空格（U+00A0）
HORIZONTAL_SPACE = re.compile(r"[\t \u3000\u00a0]+")

# 未填模板的占位符。企业文档库里真实存在的坑：一份「×××公司」的模板混进索引，
# 谁问都被它召回，而它什么信息都没有。识别出来是为了**标记**而不是删除——
# 删掉就没人知道库里有一份没填的模板；标记出来，文档区能看见，评测也能拿它当反例。
PLACEHOLDER_PATTERNS = {
    "叉号占位": re.compile(r"[×xX]{2,}(?:公司|集团|有限责任公司|有限公司)?"),
    "下划线占位": re.compile(r"_{3,}"),
    "待填写": re.compile(r"待定|待填写|待补充|另行通知|暂无"),
}


def clean_text(raw: str) -> str:
    """去噪点 + 归一化空白（教程 11.2 的清洗步骤），返回清洗后的正文。

    ``raw`` 是解析器刚吐出来的原文——PDF 的页眉页脚、HTML 的残留空行都在里面。

    四步，顺序有讲究：
    1. **去控制字符**要在归一化空白之前——否则那些不可见字符会卡在词中间，
       让「同一句话」的哈希对不上（同一份文档重传一次就变成"内容变了"）；
    2. 去页码噪点（``NOISE_PATTERNS``）只认「单独成行的页码」这类形态，
       不会误伤正文里恰好出现的数字；
    3. **横向空白归一**顺带把全角空格（U+3000）和不换行空格（U+00A0）也换成半角——
       中文文档里这两种空格遍地都是，不统一的话分词和检索都会把同一个词当两个；
    4. 最后把三个以上连续换行压成两个（段落间距），再 strip。
    """
    text = CONTROL_CHARS.sub("", raw)
    for pat in NOISE_PATTERNS:
        text = re.sub(pat, "", text)
    text = HORIZONTAL_SPACE.sub(" ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def find_placeholders(text: str) -> list[str]:
    """找出正文里还留着的未填模板痕迹，返回命中项的中文名（去重、按固定顺序）。

    ``text`` 是清洗后的正文。返回空列表表示这份文档看起来是填好的。

    只**标记**不删除：删掉就没人知道库里混进了一份没填的模板，而它会被
    任意问题召回、还答不出任何东西。标记出来之后，文档区能显示，评测也能拿它当反例。
    """
    return [name for name, pattern in PLACEHOLDER_PATTERNS.items() if pattern.search(text or "")]


def decode_bytes(data: bytes) -> str:
    """把文件字节解成文本，中文编码按「UTF-8 → GB18030」两档试。

    ``data`` 是文件原始字节。

    为什么不能只试 UTF-8：中文语料里 GBK/GB2312 的文件至今常见（老系统导出、
    Windows 记事本默认存的）。UTF-8 解码失败时直接抛 ``UnicodeDecodeError``，
    整篇文档进不了库——而它其实只是编码旧了点。

    为什么兜底是 GB18030 而不是 GBK：GB18030 是 GBK 的超集，能覆盖更全的汉字
    （含生僻字和部分少数民族文字），拿它兜底等于一次覆盖 GB2312/GBK/GB18030 三代。

    两档都失败才抛 ``ValueError``——这时候确实是编码不认识，该让人来看看。
    """
    for encoding in ("utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("这个文件的编码认不出来（试过 UTF-8 和 GB18030），请另存为 UTF-8 再入库")


def make_splitter():
    """按 config 的旋钮建一个递归切块器，中文优先在句边界下刀（教程 11.4）。

    切块的整体策略在 ``chunking.py``（先按标题分节、表格整段不切），这里只负责
    造那个"在句子边界上找落刀点"的零件——预演、实验台和真入库都从这一处拿旋钮，
    免得三处各写一份分隔符。
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    return RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
    )


def content_hash(text: str) -> str:
    """内容寻址：文档变了才重新入库（教程 11.13 增量更新），返回前 16 位十六进制摘要。

    ``text`` 是**清洗后**的正文。摘要只截 16 位：够课堂用，也短到能写进账本、
    显示在文档区那一列。

    注意哈希只覆盖正文，而真正送进向量库的文本前面还带着 ``《文件名》`` 上下文头——
    所以「改名不改内容」本该重算向量；账本又是按文件名索引的，改名后查不到旧条目，
    于是自然落到"新增"那条路上。两个判断恰好一致，不必额外写一条改名检测。
    """
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def load_docstore() -> dict:
    """读内容哈希账本：``来源文件名 → {hash, schema, status, signals, accession}``。

    账本不存在（还没入过库）就返回空字典，让调用方拿"空账本"直接跑通第一次入库，
    不必先判断文件在不在。解析失败不兜底——账本写坏是该修的问题，静默降级只会
    让后面看到一份"文档全没了"的假账。
    """
    if config.DOCSTORE_JSON.exists():
        return json.loads(config.DOCSTORE_JSON.read_text())
    return {}


def _entry_hash(entry) -> str:
    """取 ``entry`` 里的内容哈希；条目是老格式（纯字符串）时整串就是哈希。"""
    if isinstance(entry, dict):
        return str(entry.get("hash") or "")
    return str(entry or "")


def _entry_schema(entry) -> str:
    """取 ``entry`` 记的索引 schema；老格式条目没有这个字段，返回空串。"""
    if isinstance(entry, dict):
        return str(entry.get("schema") or "")
    return ""


def _stamp(digest: str, status: str = "indexed", signals: list[str] | None = None,
           accession: int = 0) -> dict:
    """账本记下内容哈希、索引 schema 和状态——schema 变了必须重建（11.13）。

    ``digest`` 是清洗后正文的内容哈希；``status`` 让"被投毒扫描隔离"成为账本里的
    一等状态：文档区要能显示「它在账本里、但不在检索索引里」，而不是让它凭空消失；
    ``signals`` 是扫描命中的原因列表，只在不为空时写入，免得账本里全是空数组。

    ``accession`` 是**登记号**：入库那一刻烙上，之后再不改动。它和"第几行"是两件事——
    删掉一篇不会让后面的号往前挪，留下的空号正是登记簿该有的样子。
    """
    entry = {"hash": digest, "schema": config.INDEX_SCHEMA, "status": status}
    if signals:
        entry["signals"] = list(signals)
    if accession:
        entry["accession"] = accession
    return entry


def _accession_of(entry) -> int:
    """取 ``entry`` 上的登记号；缺号、非数字或写坏一律返回 0。

    0 的意思是"还没号"（等 ``accessions_of`` 去补），不是"第 0 号"——
    真号从 1 起，所以 0 可以安全地当哨兵值用。
    """
    if not isinstance(entry, dict):
        return 0
    try:
        return max(0, int(entry.get("accession") or 0))
    except (TypeError, ValueError):
        return 0


def accessions_of(docstore: dict) -> dict[str, int]:
    """算出账本里每个来源的登记号：已有的沿用，缺号的接在最大号之后补。

    ``docstore`` 是内容哈希账本（``来源文件名 → 条目``），函数**只读不写**，
    返回 ``来源文件名 → 登记号`` 的映射。

    账本是保序的，所以补号的结果是确定的——读路径和入库路径用的是同一套规则，
    于是"还没入过库"和"刚入过库"看到的号完全一样。读路径不写账本，只算。
    """
    issued = {source: _accession_of(entry) for source, entry in docstore.items()}
    next_no = max(issued.values(), default=0) + 1
    for source in docstore:
        if not issued[source]:
            issued[source] = next_no
            next_no += 1
    return issued


def backfill_accessions(docstore: dict) -> int:
    """把补出来的号**写回**账本，返回下一个可用号。入库时调用一次，之后只读。

    ``docstore`` 是内容哈希账本，会被**就地改写**：只有缺号的条目会被补上
    ``accession``，已经有号的一个都不动，所以这个函数是幂等的——升级前入库的
    老文档在第一次入库时补号，之后每次跑读到的是同一个号。
    """
    issued = accessions_of(docstore)
    for source, entry in docstore.items():
        if isinstance(entry, dict) and not _accession_of(entry):
            entry["accession"] = issued[source]
    return max(issued.values(), default=0) + 1


def context_header(source_name: str) -> str:
    """零成本上下文头（教程 11.2 迟切块/上下文检索的退化路径），返回 ``《文件名》``。

    ``source_name`` 是来源文件名，只取主干（去掉 ``.md`` 这类后缀）再包上书名号。
    这行字会拼在每一块前面一起送进向量库：切块脱离原文之后，"这块属于哪篇"的线索
    就丢了，用文件名把这条线索零成本地补回去，比再调一次模型做摘要便宜得多。
    """
    stem = Path(source_name).stem
    return f"《{stem}》"


def embeddings():
    """OpenAI 兼容 Embedding。方舟等端点单次最多 10 条，外包一层分批。"""
    from langchain_openai import OpenAIEmbeddings

    inner = OpenAIEmbeddings(
        model=config.EMBED_MODEL,
        api_key=config.OPENAI_API_KEY or "sk-dummy",
        base_url=config.OPENAI_API_BASE or None,
        check_embedding_ctx_length=False,
        tiktoken_enabled=False,
    )
    return BatchedEmbeddings(inner, config.EMBED_BATCH_SIZE)


class BatchedEmbeddings:
    """绕开部分兼容端点「单次最多 10 条 input」上限（与 shared_corpus 同一纪律）。

    ``inner`` 是真正干活的 embedding 客户端（LangChain 的 Embeddings 接口）；
    ``batch_size`` 是单次请求最多塞几条文本。对外仍然只暴露标准的
    ``embed_documents`` / ``embed_query`` 两个方法，所以它可以原样当
    ``embedding_function`` 交给 Chroma，包装这件事对上游透明。
    """

    def __init__(self, inner, batch_size: int = 10):
        """``inner`` 是被包住的客户端，``batch_size`` 是每批条数（缺省 10，方舟的上限）。"""
        self._inner = inner
        self.batch_size = batch_size

    def embed_documents(self, texts):
        """``texts`` 是一批文本，返回与之一一对应的向量列表。

        分批只是为了绕开端点上限；返回值顺序必须与入参严格对齐——顺序错了会把
        A 文档的向量存到 B 文档名下，而且错得毫无报错。
        """
        texts = list(texts)
        vectors: list = []
        for start in range(0, len(texts), self.batch_size):
            vectors.extend(self._inner.embed_documents(texts[start:start + self.batch_size]))
        return vectors

    def embed_query(self, text):
        """``text`` 是单条查询文本，直接透传给底层客户端（查询不批量，没有上限问题）。"""
        return self._inner.embed_query(text)


def _iter_source_files(docs_dir: Path):
    """教学入库认 md/txt/html/docx/pdf；扫描件请先在 11.2 管道里走 MinerU。

    ``docs_dir`` 是待入库目录，只扫它**第一层**（不递归），产出按文件名排序——
    顺序稳定，账本条目与切块号才可复现。
    """
    for path in sorted(docs_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in {".md", ".txt", ".html", ".pdf", ".docx"}:
            yield path


def _read_pdf(path: Path) -> str:
    """文字层 PDF 用 pymupdf 抽文本。扫描件会得到空串，这时该换 MinerU，见教程 11.2。

    ``path`` 是 PDF 文件路径，返回全文。抽出来是空的会抛 ``ValueError``：
    空文本继续往下走只会变成"入库成功但零切块"的假象，不如当场叫停。
    """
    import pymupdf
    with pymupdf.open(path) as doc:
        text = "\n".join(page.get_text("text") for page in doc).strip()
    if not text:
        raise ValueError(f"{path.name} 抽出来是空的，多半是扫描件，请改用 MinerU 4.x")
    # PDF 换行常把"100 元"拆成两行，粘回去，免得切块正好从这里断开
    return re.sub(r"(\d)\s*\n\s*(元)", r"\1 \2", text)


def _docx_blocks(document):
    """按**文档原始顺序**产出段落与表格。

    ``document`` 是 python-docx 的 Document 对象。

    为什么不能只读 ``document.paragraphs``：那个属性只收集段落，表格整块消失——
    而制度文件里「一线城市 500 元 / 二线 350 元」这种关键信息十有八九在表格里。
    表格丢了，正文读起来还是通顺的，只是答案永远查不到，最难被发现的那种缺失。

    顺着 XML body 逐个孩子走，才能拿到「段落、表格、段落、表格」的真实顺序。
    产出 ``("p", Paragraph)`` 或 ``("t", Table)``。
    """
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield "p", Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield "t", Table(child, document)


def _table_line(table, marker: str = "表格行") -> str:
    """把一张表压成几行文本，一行一行读。

    ``table`` 是 python-docx 的 Table；``marker`` 是每行开头的前缀词。

    为什么按行而不是按单元格：一行表格本来就是一条完整记录（「一线城市 | 500 元」），
    打散成单元格会把「500 元」和它的城市名分开，检索命中「500」时看不到它属于谁。
    单元格之间用 ``|`` 分隔，是 Markdown 表格的写法，人读和模型读都熟。

    空单元格保留占位（否则列会错位，第三列的值看起来像第二列的），尾部连续空列去掉。
    返回多行文本，行与行之间用换行连接。
    """
    lines = []
    for row in table.rows:
        cells = [re.sub(r"\s+", " ", (cell.text or "")).strip() for cell in row.cells]
        while cells and not cells[-1]:
            cells.pop()
        if not any(cells):
            continue
        lines.append(f"{marker}: " + " | ".join(cells))
    return "\n".join(lines)


def _read_docx(path: Path) -> str:
    """``path`` 是 .docx 路径，返回段落与表格按原顺序拼好的文本。

    表格转成 ``表格行: A | B | C`` 的行，和段落混在同一个流里保持它们的先后关系——
    制度文件里「下面这张表说明标准」和表本身是连着的，拆开就断了。

    文本框（``word/document.xml`` 里独立于 body 的那种）仍然不抽，这是已知取舍：
    它要靠直读 XML 救，而教学版不想在这条路上再引一层解析。
    """
    from docx import Document as DocxDocument

    document = DocxDocument(str(path))
    parts: list[str] = []
    for kind, block in _docx_blocks(document):
        if kind == "p":
            text = (block.text or "").strip()
            if text:
                parts.append(text)
            continue
        table_text = _table_line(block)
        if table_text:
            parts.append(table_text)
    return "\n".join(parts)


# 整块丢掉的内容：脚本、样式、注释。它们不是"正文的一部分"，是页面的实现细节——
# 抽进索引只会给检索添噪声（脚本里的变量名还可能被当成关键词召回）。
_HTML_DROP = re.compile(r"(?is)<(script|style|noscript|svg|head)\b.*?</\1\s*>")
# 块级标签收尾时补换行，让段落/表格行/列表项各自成行
_HTML_BLOCK_END = re.compile(
    r"(?i)</(p|div|section|article|li|tr|h[1-6]|blockquote|pre|table|ul|ol|dl)\s*>"
)
_HTML_BR = re.compile(r"(?i)<br\s*/?>")
# 表格结构标记：换成 | 分隔符，让表格行和 docx 走同一个形状
_HTML_TD = re.compile(r"(?i)</t[dh]\s*>")


def _read_html(path: Path) -> str:
    """``path`` 是 HTML 路径，返回去标签、反转义后的纯文本。

    顺序不能反：先 unescape 的话，正文里写着的 ``&lt;p&gt;`` 会变成真标签，紧接着
    的剥标签步骤就把用户想看的字当标签吃掉了。

    比"剥掉所有标签"多做了两件事：

    1. **整块丢掉 script / style / svg / head**——只在剥标签前先按标签对删，
       否则脚本内容会变成一大段"正文"，变量名还会被 BM25 当关键词召回；
    2. **表格单元格之间换成 ``|``**——和 docx 的表格行保持同一个形状，让下游
       「表格行不切碎」的规则对两种来源一视同仁。
    """
    import html as html_lib

    raw = decode_bytes(path.read_bytes())
    raw = _HTML_DROP.sub("", raw)
    raw = _HTML_BR.sub("\n", raw)
    raw = _HTML_TD.sub(" | ", raw)
    raw = _HTML_BLOCK_END.sub("\n", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    text = html_lib.unescape(raw)
    # 每个 </td> 都换成了「| 」，行尾会剩一个孤零零的分隔符；逐行削掉它，
    # 免得下游把「| 」当成一个空单元格
    lines = [re.sub(r"(?:\s*\|\s*)+$", "", line).rstrip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line.strip())


def _read_source(path: Path) -> str:
    """``path`` 是待读文件，按后缀分流到 PDF / Word / HTML 解析器，其余当 UTF-8 文本读。"""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix == ".docx":
        return _read_docx(path)
    if suffix == ".html":
        return _read_html(path)
    # 其余按文本读，编码走 UTF-8 → GB18030 两档，别让一份 GBK 老文件整个进不了库
    return decode_bytes(path.read_bytes())


def _trust_of(path: Path) -> str:
    """``path`` 是来源文件，返回 ``external``（不可信）或 ``internal``（可信）。

    判据只有两条：后缀是 ``.html``，或文件名里带"外部"/"注入"。课堂上要造一篇
    不可信文档，在文件名里写上"外部"就行，不必真去接一个恶意站点。
    """
    name = path.name
    if path.suffix.lower() == ".html" or "外部" in name or "注入" in name:
        return "external"
    return "internal"


def ingest(docs_dir: Path | None = None, only: list[str] | None = None) -> dict:
    """把 data/docs 同步进向量库 + BM25（同源切块），并垫一份种子图谱。

    ``docs_dir`` 是待同步目录，缺省走 ``config.DOCS_DIR``；``only`` 是给
    "上传/重传一篇"用的：只对名单里的文件做嵌入与向量写入，
    其余文件只刷新 BM25 语料（切块是本地计算，不花钱）。**BM25 语料始终全量重建**，
    因为检索要看到所有文档；嵌入才是那个要花钱、要避免重算的步骤。
    级联删除只在全量同步（`only is None`）时进行。

    返回本轮统计：``added`` / ``updated`` / ``skipped`` / ``deleted`` / ``quarantined``
    五个计数，外加逐篇的 ``files`` 明细（状态、切块数、隔离原因）。
    完整版是「解析 → 抽取 → 三路并行写入」；Lite 同步走同一思想：
    一份切块同时喂 Chroma 和 BM25，种子三元组写入图存储，问答时三路一起召回。
    """
    from langchain_chroma import Chroma
    from langchain_core.documents import Document

    docs_dir = docs_dir or config.DOCS_DIR
    config.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    docstore = load_docstore()
    splitter = make_splitter()
    vectorstore = Chroma(
        collection_name="forge_lite", embedding_function=embeddings(),
        persist_directory=str(config.CHROMA_DIR),
    )

    stats = {"added": 0, "updated": 0, "skipped": 0, "deleted": 0, "quarantined": 0}
    files: list[dict] = []
    seen = set()
    indexed: list[dict] = []  # 通过扫描、真正进检索的切块（BM25 同源）

    def targeted(rel: str) -> bool:
        """``rel`` 是来源文件名；判断本轮该不该为它重算嵌入（``only`` 为空即全量，全都算）。"""
        return only is None or rel in only

    # 登记号：老条目先补号，之后新条目往后接。**改写已有的条目时必须沿用旧号**，
    # 否则重传一篇文档就会把它变成"最新入库"，登记簿的号就失去意义了。
    counters = {"next": backfill_accessions(docstore)}

    def stamp_for(previous, digest: str, **kwargs) -> dict:
        """记账：``previous`` 是账本里的旧条目，``digest`` 是本次算出的内容哈希，
        ``kwargs`` 是打包进 ``**kwargs`` 的其余关键字（``status`` / ``signals`` 等），
        原样透传给 ``_stamp``。

        旧条目已有登记号就沿用，没有才从计数器里取新号——**重传一篇文档不该把它
        变成"最新入库"**，否则登记号会随重传漂移，登记簿就白记了。
        """
        carry = _accession_of(previous)
        if carry:
            return _stamp(digest, accession=carry, **kwargs)
        counters["next"] += 1
        return _stamp(digest, accession=counters["next"] - 1, **kwargs)

    for path in _iter_source_files(docs_dir):
        rel = path.name
        seen.add(rel)
        text = clean_text(_read_source(path))
        digest = content_hash(text)
        trust = _trust_of(path)
        previous = docstore.get(rel)
        unchanged = _entry_hash(previous) == digest and _entry_schema(previous) == config.INDEX_SCHEMA
        signals = scan_poisoning(text, trust_level=trust)

        if signals:
            # 隔离：账本留名（含原因），但不进检索索引
            was_indexed = bool(previous) and str((previous or {}).get("status") or "") != "quarantined"
            docstore[rel] = stamp_for(previous, digest, status="quarantined", signals=signals)
            if unchanged and not was_indexed:
                stats["skipped"] += 1
            else:
                print(f"[投毒扫描] {rel} → 隔离，不进检索索引：{'；'.join(signals)}")
                if targeted(rel) or was_indexed:
                    try:
                        vectorstore.delete(where={"source": rel})
                    except Exception:
                        pass
                stats["quarantined"] += 1
            files.append({"source": rel, "status": "quarantined", "chunks": 0, "signals": signals})
            continue

        policy = catalog_of(rel)
        meta = {"source": rel, "acl": policy["acl"], "status": "active", "trust": trust,
                "department": policy["department"], "sensitivity": policy["sensitivity"],
                "schema": config.INDEX_SCHEMA}
        # 结构感知切块：先按标题分节、表格整段不切，再把「《文件名》 › 标题路径」
        # 拼在每块前面（教程 11.4）。切块策略在 chunking.py，这里只管接上旋钮。
        pieces = chunk_document(
            text, rel,
            chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP,
            splitter=splitter,
        )
        chunks = [piece["text"] for piece in pieces]
        for i, piece in enumerate(pieces):
            indexed.append({**meta, "chunk_index": i, "text": piece["text"],
                            "heading": piece["heading"]})

        if unchanged:
            # 内容没变就不重嵌入；但账本格式升级过（旧条目没有 status）时补写状态位——
            # 文档区要靠它区分「在索引里」和「被隔离」，不能让老条目含糊过去。
            entry = dict(previous or {})
            if entry.get("status") != "indexed":
                docstore[rel] = stamp_for(previous, digest, status="indexed")
            stats["skipped"] += 1
            files.append({"source": rel, "status": "indexed", "chunks": len(chunks), "signals": []})
            continue
        if not targeted(rel):
            # 全量同步里没点名、又被改过的文件：账本照记（下次会被处理），本轮不重嵌入
            stats["skipped"] += 1
            files.append({"source": rel, "status": "stale", "chunks": len(chunks), "signals": []})
            continue

        if previous:
            vectorstore.delete(where={"source": rel})
            stats["updated"] += 1
        else:
            stats["added"] += 1
        # chunks 里已经带着「《文件名》 › 标题路径」的上下文头（见 chunking.chunk_document），
        # 这里不再拼一次——拼两遍会让同一段路径在向量里出现两次，白占预算。
        docs = [Document(page_content=piece["text"],
                         metadata={**meta, "chunk_index": i, "heading": piece["heading"]})
                for i, piece in enumerate(pieces)]
        if docs:
            vectorstore.add_documents(docs)
        docstore[rel] = stamp_for(previous, digest, status="indexed")
        files.append({"source": rel, "status": "indexed", "chunks": len(chunks), "signals": []})

    if only is None:
        for gone in set(docstore) - seen:  # 源文件删除 → 级联清理（教程 11.13）
            try:
                vectorstore.delete(where={"source": gone})
            except Exception:
                pass
            del docstore[gone]
            stats["deleted"] += 1

    config.DOCSTORE_JSON.write_text(json.dumps(docstore, ensure_ascii=False, indent=2))
    _export_bm25_corpus(indexed)
    _seed_graph_store()
    stats["files"] = files
    return stats


def _seed_graph_store() -> None:
    """入库时把种子三元组垫进图存储，保证第三路召回不依赖另跑 05。"""
    seed = config.BASE_DIR / "data" / "seed_triples.json"
    if not seed.exists():
        return
    try:
        from .knowledge_graph import get_store
        get_store().save(json.loads(seed.read_text(encoding="utf-8")))
    except Exception as exc:
        print(f"[图谱降级] 种子三元组未写入图存储（问答仍可读 JSON 兜底）：{exc}")


def _export_bm25_corpus(chunks: list[dict]) -> None:
    """把同一批切块导出给 BM25 用：一份语料，三路索引共用（教程 11.5 / 11.7）。

    ``chunks`` 是本次通过投毒扫描、真正进检索的切块（已带权限元数据），整份覆写
    ``config.CHUNKS_JSON``。BM25 是本地计算，全量重写比增量对齐更不容易错——
    代价只是多写一点磁盘，换掉一整类"语料与索引对不上"的怪问题。
    """
    config.CHUNKS_JSON.write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    print(ingest())
