"""
s02_data_pipeline.py
====================
11.2 配套代码：文档解析、清洗与切块
痛点：数据源又脏又乱 → 三步走「解析 → 清洗 → 切块」产出干净 Chunk 与元数据。
"""

import hashlib
import re
from pathlib import Path
from typing import Iterable, List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


# ============ 1. 解析：按文件后缀自动选择解析器 ============
def load_text_by_ext(path: Path) -> str:
    """返回统一格式的纯文本。生产环境可按需替换为 MinerU/Unstructured 等高保真解析器。"""
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8")
    if suffix == ".html":
        # 用正则粗略剥掉标签，严谨场景建议 BeautifulSoup + 白名单
        html = path.read_text(encoding="utf-8")
        return re.sub(r"<[^>]+>", "", html)
    # 生产环境：.pdf 用 pymupdf/MinerU，.docx 用 python-docx
    raise NotImplementedError(f"暂未实现 {suffix} 的解析器")


# ============ 2. 清洗：去噪 + 归一化 ============
NOISE_PATTERNS = [
    r"第\s*\d+\s*页",             # 页眉页脚："第 38 页"
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
        "差旅管理制度_2026.md": ("制度", "active", "internal"),
        "差旅管理制度_2025_已废止.md": ("制度", "deprecated", "internal"),
        "办公设备故障手册.md": ("运维", "active", "internal"),
        "外部网页快照_含注入样本.md": ("外部网页", "quarantine", "external"),
    }
    result: List[Document] = []
    for filename, (category, status, trust) in configs.items():
        chunks = build_chunks(root / filename, filename, category)
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


if __name__ == "__main__":
    # 构造一份“带病”演示文档
    demo_doc = Path("demo.md")
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

    corpus = build_test_corpus()
    print("\n=== 多页测试语料体检 ===")
    print(corpus_quality_report(corpus))

    demo_parent_document()
