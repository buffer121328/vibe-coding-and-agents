"""shared_corpus.py
==================
第十一章公共语料与模型工厂。

为什么需要它：之前各小节脚本各自在内存里硬编码两三句"假文档"，案例文档
（testdata/）躺在旁边没人用。本模块把 testdata 里的真实文档统一解析成
「页级 Chunk」（复用 s02 的清洗与切块思想，与工作台 real_demo_pages 对齐），
并让各脚本共享同一份语料和同一套模型工厂，检索结果可互相对照。

设计约束：
- 导入本模块不触发任何网络请求与模型下载（离线测试依赖这一条）；
- 全部模型/Embedding 通过工厂函数延迟创建，配置读 code/.env；
- 每个页级 Chunk 的 metadata 带 doc_id/page/title/source/trust，
  供 s04 过滤检索、s09 评估、s12 引用溯源直接使用。
"""

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.documents import Document

import s02_data_pipeline as s02

CODE_DIR = Path(__file__).resolve().parent
TESTDATA_DIR = CODE_DIR / "testdata"
DEMO_DIR = TESTDATA_DIR / "真实RAG演示文档"

load_dotenv(CODE_DIR / ".env")


@dataclass(frozen=True)
class CorpusPage:
    """一页真实文档 = 一个可解释的检索单元。"""

    doc_id: str
    page: str
    title: str
    source: str
    text: str

    @property
    def chunk_id(self) -> str:
        return f"{self.doc_id}#p{self.page}"


def _split_markdown_pages(path: Path) -> list[CorpusPage]:
    """把「## 第 N 页：标题」结构的 Markdown 拆成页级 Chunk。"""
    raw = path.read_text(encoding="utf-8")
    doc_id_match = re.search(r"文档编号：([^\s　]+)", raw)
    doc_id = doc_id_match.group(1).strip() if doc_id_match else path.stem
    parts = re.split(r"(?m)^## 第 (\d+) 页：?([^\n]*)\n", raw)
    pages: list[CorpusPage] = []
    if len(parts) == 1:
        pages.append(CorpusPage(doc_id, "full", path.stem, path.name, s02.clean_text(raw)))
        return pages
    for i in range(1, len(parts), 3):
        page_no = parts[i].strip()
        title = parts[i + 1].strip() or f"第 {page_no} 页"
        body = s02.clean_text(parts[i + 2])
        pages.append(CorpusPage(doc_id, page_no, title, path.name, body))
    return pages


@lru_cache(maxsize=1)
def demo_pages() -> tuple[CorpusPage, ...]:
    """testdata/真实RAG演示文档 的 4 份案例文档，按「页」切成 16 个 Chunk。"""
    pages: list[CorpusPage] = []
    for path in sorted(DEMO_DIR.glob("*.md")):
        pages.extend(_split_markdown_pages(path))
    return tuple(pages)


@lru_cache(maxsize=1)
def regression_pages() -> tuple[CorpusPage, ...]:
    """testdata 根目录的 4 份回归语料（现行/废止制度、故障手册、注入网页）。"""
    names = ["差旅管理制度_2026.md", "差旅管理制度_2025_已废止.md", "办公设备故障手册.md", "外部网页快照_含注入样本.md"]
    pages: list[CorpusPage] = []
    for name in names:
        path = TESTDATA_DIR / name
        pages.extend(_split_markdown_pages(path))
    return tuple(pages)


def all_pages() -> tuple[CorpusPage, ...]:
    """全部 8 份真实文档的页级语料：演示文档 + 回归语料。"""
    return demo_pages() + regression_pages()


def page_documents(pages: tuple[CorpusPage, ...] = demo_pages()) -> list[Document]:
    """页级语料转成 LangChain Document，metadata 与工作台/评估口径一致。"""
    return [
        Document(
            page_content=p.text,
            metadata={"id": p.chunk_id, "doc_id": p.doc_id, "page": p.page, "title": p.title, "source": p.source},
        )
        for p in pages
    ]


def page_texts(pages: tuple[CorpusPage, ...] = demo_pages()) -> list[str]:
    return [p.text for p in pages]


def page_ids(pages: tuple[CorpusPage, ...] = demo_pages()) -> list[str]:
    return [p.chunk_id for p in pages]


def find_page(chunk_id: str, pages: tuple[CorpusPage, ...]) -> CorpusPage:
    for p in pages:
        if p.chunk_id == chunk_id:
            return p
    raise KeyError(f"语料中不存在该页：{chunk_id}")


# ===================== 模型工厂 =====================
def make_embeddings():
    """OpenAI 兼容 Embedding 端点。

    方舟等国产端点只接受字符串输入且自定 base_url：必须关掉 tiktoken
    预分词（check_embedding_ctx_length=False, tiktoken_enabled=False），
    并显式传入 base_url——否则 LangChain 会去请求 api.openai.com。
    """
    from langchain_openai import OpenAIEmbeddings

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ARK_API_KEY", "")
    base_url = os.getenv("OPENAI_API_BASE") or os.getenv("OPENAI_BASE_URL", "")
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    return OpenAIEmbeddings(
        api_key=api_key or "sk-dummy",
        base_url=base_url or None,
        model=model,
        check_embedding_ctx_length=False,
        tiktoken_enabled=False,
    )


def embed_texts_batched(embedder, texts: list[str], batch_size: int = 10) -> list[list[float]]:
    """部分兼容端点（如方舟）一次最多接收 10 条 input，这里显式分批。"""
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        vectors.extend(embedder.embed_documents(texts[start:start + batch_size]))
    return vectors


def embed_pages_batched(pages: tuple["CorpusPage", ...] | None = None, embedder=None):
    """真实语料整批向量化：返回 (pages, texts, vectors)。"""
    import numpy as np

    pages = pages or all_pages()
    embedder = embedder or make_embeddings()
    texts = [p.text for p in pages]
    vectors = np.array(embed_texts_batched(embedder, texts))
    return pages, texts, vectors


def make_llm(temperature: float = 0.3, max_tokens: int | None = None):
    """OpenAI 兼容 Chat 端点：MIMO 首选 → ARK 备选 → CHAT_MODEL/gpt-4o-mini 兜底。"""
    from langchain_openai import ChatOpenAI

    candidates = [
        ("MIMO_API_KEY", "MIMO_BASE_URL", "MIMO_MODEL"),
        ("ARK_API_KEY", "ARK_BASE_URL", "ARK_MODEL_ENDPOINT"),
    ]
    api_key = base_url = model = ""
    for key_var, url_var, model_var in candidates:
        api_key = os.getenv(key_var, "")
        base_url = os.getenv(url_var, "")
        model = os.getenv(model_var, "")
        if api_key and model:
            break
    if not (api_key and model):
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_API_BASE") or os.getenv("OPENAI_BASE_URL", "")
        model = os.getenv("CHAT_MODEL", "gpt-4o-mini")
    return ChatOpenAI(
        model=model,
        api_key=api_key or "sk-dummy",
        base_url=base_url or None,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=60,
        max_retries=1,
    )
