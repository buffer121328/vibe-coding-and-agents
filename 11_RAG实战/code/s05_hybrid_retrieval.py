"""
s05_hybrid_retrieval.py
=======================
11.5 配套代码：混合检索与重排
痛点：搜不准、搜不全 → 在 testdata 真实制度语料上手写 RRF 融合 +
BM25/Dense 双路召回 + Cross-Encoder 重排 + 上下文压缩。
"""

import os

from typing import Dict, List

import numpy as np
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever
from langchain_classic.retrievers import EnsembleRetriever
from sentence_transformers import CrossEncoder

from rag_quality import deduplicate_contexts, reciprocal_rank_fusion
from shared_corpus import all_pages, embed_pages_batched, make_embeddings, page_documents


class BatchedEmbeddings:
    """包一层 make_embeddings()：Chroma 入库时分批调用，绕开端点 10 条 input 上限。"""

    def __init__(self):
        self._inner = make_embeddings()

    def embed_documents(self, texts):
        return embed_pages_batched_batch(texts, self._inner)

    def embed_query(self, text):
        return self._inner.embed_query(text)


def embed_pages_batched_batch(texts, embedder):
    from shared_corpus import embed_texts_batched
    return embed_texts_batched(embedder, list(texts))


def rrf_fuse(rankings: List[List[str]], k: int = 60) -> Dict[str, float]:
    """手写 RRF（倒数排名融合）：只看名次不看绝对分数。score(d) = Σ 1 / (k + rank_m(d))"""
    return dict(reciprocal_rank_fusion(rankings, rank_constant=k))


def mmr_select(query: np.ndarray, candidates: np.ndarray, top_k: int, diversity: float = 0.25) -> list[int]:
    """最大边际相关性：兼顾“像问题”和“别全说同一件事”。输入向量应先归一化。"""
    if not 0 <= diversity <= 1:
        raise ValueError("diversity 必须在 0 到 1 之间")
    if top_k <= 0 or len(candidates) == 0:
        return []
    relevance = candidates @ query
    selected: list[int] = []
    remaining = set(range(len(candidates)))
    while remaining and len(selected) < top_k:
        def score(index: int) -> float:
            redundancy = max((float(candidates[index] @ candidates[j]) for j in selected), default=0.0)
            return (1 - diversity) * float(relevance[index]) - diversity * redundancy
        winner = max(remaining, key=score)
        selected.append(winner)
        remaining.remove(winner)
    return selected


def pack_contexts(texts: List[str], max_chars: int = 1200) -> List[str]:
    """先去近重复，再按预算装箱；生产环境应使用模型 tokenizer 计算 token。"""
    packed, used = [], 0
    for text in deduplicate_contexts(texts):
        if used + len(text) > max_chars:
            continue
        packed.append(text)
        used += len(text)
    return packed


def demo_rrf() -> None:
    """拿真实页级 chunk 当牌桌：手工排dense/bm25两个榜单，看 RRF 怎么合议。"""
    dense_rank = ["TRAVEL-2026-07#p2", "REAL-RAG-TRAVEL-2026#p1", "OPS-HELP-2026#p1", "REAL-RAG-HR-2026#p1"]
    bm25_rank = ["REAL-RAG-TRAVEL-2026#p1", "TRAVEL-2025-01#p2", "OPS-HELP-2026#p1", "REAL-RAG-HR-2026#p1"]
    fused = rrf_fuse([dense_rank, bm25_rank])
    print("=== 手写 RRF 融合结果（真实页 ID）===")
    for doc_id, score in fused.items():
        print(f"{doc_id}: {score:.4f}")
    contexts = [
        "一线城市住宿费上限为每人每天 500 元。",
        "一线城市住宿标准为每人每天不超过 500 元。",   # 近重复：换了个说法
        "差旅报销单须在返回工作地后 5 个工作日内提交 OA。",
    ]
    print("上下文去重装箱:", pack_contexts(contexts, max_chars=40))


def demo_hybrid_rerank() -> None:
    """真实语料上 BM25 + Chroma 双路召回 → RRF 融合 → Cross-Encoder 重排。"""
    docs = page_documents(all_pages())
    query = "RX-9000 报 ERR-404-X9 故障怎么解决？"

    vectorstore = Chroma.from_documents(docs, BatchedEmbeddings())
    dense = vectorstore.as_retriever(search_kwargs={"k": 4})
    sparse = BM25Retriever.from_documents(docs)
    sparse.k = 4

    # 官方 RRF 封装（内部就是上面手写的算法）
    ensemble = EnsembleRetriever(retrievers=[dense, sparse], weights=[0.5, 0.5])

    candidates = ensemble.invoke(query)
    print(f"\n问题：{query}")
    print(f"粗排召回 {len(candidates)} 篇：")
    for d in candidates:
        print(f"  - [{d.metadata['id']}]《{d.metadata['title']}》")

    # 本地重排模型（首次运行下载约 1GB，缓存在 ~/.cache/huggingface）；
    # 不想下模型可用 API 重排：Jina/Cohere 重排接口或 LLM 分句打分（思路见 11.5 正文）。
    reranker = CrossEncoder("BAAI/bge-reranker-base")
    pairs = [[query, d.page_content] for d in candidates]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)

    print("=== 重排后 Top-2 ===")
    for doc, score in ranked[:2]:
        print(f"[{score:.4f}] [{doc.metadata['id']}]《{doc.metadata['title']}》")
        print(f"        {doc.page_content[:60]}……")


def demo_mmr_on_real_corpus() -> None:
    """MMR 在真实语料上的效果：差旅问题既要住宿标准页、也要报销流程页，别全说同一件事。"""
    pages, texts, vectors = embed_pages_batched(all_pages(), make_embeddings())
    normalized = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    query = "出差住宿报销的上限和提交时限？"
    embedder = make_embeddings()
    q_vector = np.array(embedder.embed_query(query))
    q_vector /= np.linalg.norm(q_vector)

    picked = mmr_select(q_vector, normalized, top_k=3, diversity=0.35)
    print(f"\n=== MMR 多样性选择（diversity=0.35）：{query} ===")
    for i in picked:
        print(f"[{pages[i].chunk_id}]《{pages[i].title}》")


if __name__ == "__main__":
    demo_rrf()
    demo_hybrid_rerank()
    demo_mmr_on_real_corpus()
