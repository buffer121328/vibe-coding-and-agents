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


def order_contexts(scored: list[tuple[str, float]]) -> list[str]:
    """上下文编排：把最相关的放首尾，对抗 lost-in-the-middle 的位置偏置。

    规则：先按分数降序排出名次 → 第 1 名放开头，第 2 名放结尾，
    其余按分数升序（越不相关越靠中间）填进中间。纯函数，不依赖任何模型。

    参见正文 `## 进阶：上下文编排 —— 顺序、位置偏置与 Token 预算`。
    """
    if not scored:
        return []
    ranked = sorted(scored, key=lambda item: item[1], reverse=True)
    if len(ranked) <= 1:
        return [doc_id for doc_id, _ in ranked]
    if len(ranked) == 2:
        return [doc_id for doc_id, _ in ranked]
    head = ranked[0][0]
    tail = ranked[1][0]
    middle = [doc_id for doc_id, _ in sorted(ranked[2:], key=lambda item: item[1])]
    return [head, *middle, tail]


def build_hard_negatives(query: str, ranked_ids: list[str], gold_ids, top_n: int = 3) -> list[str]:
    """重排微调的难负例构造：从粗排榜单里挑“排得靠前但不含答案”的文档 ID。

    难负例比随机负例更值钱，因为线上真正会误判的就是这种“看起来很像但不含答案”的块。

    按传入顺序保留 `ranked_ids` 的相对顺序，最多返回 `top_n` 个；输入缺失时返回 `[]`。
    这里只做**数据准备**这一半，训练入口与脚本见正文
    `## 进阶：Cross-Encoder 怎么选、怎么调、怎么微调`。
    """
    if not ranked_ids or top_n <= 0:
        return []
    gold = set(gold_ids or [])
    return [doc_id for doc_id in ranked_ids if doc_id not in gold][:top_n]


def explain_retrieval(hits: list[dict]) -> list[dict]:
    """可解释检索：给每条命中补上“为什么是它”，并提醒分数不可直接比大小。

    不修改入参，返回新的 dict 列表；缺字段时用 `"-"`/0 兜底，不抛异常。
    """
    explained: list[dict] = []
    for hit in hits or []:
        route = hit.get("route", "-") or "-"
        rank = hit.get("rank", 0) or 0
        fused_rank = hit.get("fused_rank")
        fused_text = fused_rank if fused_rank is not None else "-"
        record = dict(hit)
        record["why"] = f"被 {route} 召回（该路第 {rank} 名），融合后第 {fused_text} 名"
        # 检索分数不是概率，BM25/向量/图谱各路不可直接比大小（同 11.11 的 MaxSim 提醒）
        record["is_confidence_comparable"] = False
        explained.append(record)
    return explained


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

    # 官方封装是带权重的 RRF，和上面手写的纯名次公式不是同一把尺
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


def demo_ordering_and_negatives() -> None:
    """手工小数据演示：上下文编排顺序、难负例构造、可解释检索（可用真实页 ID 替换）。"""
    scored = [
        ("RX-9000设备手册#p12", 0.91),   # 最相关：直接给处理步骤
        ("安全规范#p3", 0.86),           # 次相关：必须遵守的条款
        ("散热结构设计说明#p4", 0.44),   # 次要背景
        ("历史维修记录#p1", 0.21),       # 最不相关
    ]
    print("\n=== 上下文编排：最相关放首尾（对抗 lost-in-the-middle）===")
    print("融合名次(降序):", [doc_id for doc_id, _ in sorted(scored, key=lambda x: x[1], reverse=True)])
    print("编排后顺序  :", order_contexts(scored))

    ranked_ids = ["RX-9000设备手册#p12", "散热结构设计说明#p4", "安全规范#p3", "历史维修记录#p1"]
    gold_ids = {"RX-9000设备手册#p12"}
    print("\n=== 难负例构造：粗排靠前但不含答案的块 ===")
    print("难负例:", build_hard_negatives("RX-9000 报 ERR-404-X9 怎么处理？", ranked_ids, gold_ids, top_n=2))

    hits = [
        {"id": "RX-9000设备手册#p12", "route": "bm25", "score": 12.4, "rank": 2, "fused_rank": 1},
        {"id": "安全规范#p3", "route": "dense", "score": 0.83, "rank": 1, "fused_rank": 2},
        {"id": "散热结构设计说明#p4", "route": "graph", "score": 0.57, "rank": 3, "fused_rank": 3},
    ]
    print("\n=== 可解释检索：告诉用户“为什么是它” ===")
    for record in explain_retrieval(hits):
        print(f"[{record['id']}] {record['why']}；分数可跨路比大小？{record['is_confidence_comparable']}")


if __name__ == "__main__":
    demo_rrf()
    demo_hybrid_rerank()
    demo_mmr_on_real_corpus()
    demo_ordering_and_negatives()
