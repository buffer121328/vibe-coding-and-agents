"""
s03_embedding.py
================
11.3 配套代码：向量嵌入与多模态
痛点：机器看不懂人话 → 把 testdata 里的真实制度/运维文档变成高维坐标，
手写三种度量与最近邻检索，再验证「问题打错一词，向量还会不会认」。
"""

import os

import numpy as np

from rag_quality import retrieval_metrics
from shared_corpus import all_pages, embed_pages_batched, make_embeddings


def cosine(v1, v2):
    denominator = np.linalg.norm(v1) * np.linalg.norm(v2)
    if denominator == 0:
        raise ValueError("零向量没有可定义的余弦相似度")
    return float(np.dot(v1, v2) / denominator)


def euclidean(v1, v2):
    return float(np.linalg.norm(v1 - v2))


def dot(v1, v2):
    return float(np.dot(v1, v2))


def embed_pages(pages=None, embed=None):
    """把页级真实语料转成向量矩阵；texts 向量与 pages 一一对应。"""
    return embed_pages_batched(pages, embed)


def demo_embedding_and_retrieval() -> None:
    """真实语料 → 三种度量 → 手写 Top-K 最近邻检索（需要可用的 Embedding API Key）。"""
    embed = make_embeddings()
    pages, texts, doc_vectors = embed_pages(embed=embed)

    query = "我下个月去上海出差，住一晚最多能报多少钱？"
    q_vector = np.array(embed.embed_query(query))

    print(f"=== 真实语料：{len(texts)} 页（testdata/ 8 份文档）===")
    print("=== 三种度量对比（对最相关的一页）===")
    sims = [cosine(q_vector, v) for v in doc_vectors]
    best = int(np.argmax(sims))
    print(f"命中页: {pages[best].chunk_id} 《{pages[best].title}》")
    print(f"余弦相似度 : {cosine(q_vector, doc_vectors[best]):.4f}  (越大越近)")
    print(f"欧氏距离   : {euclidean(q_vector, doc_vectors[best]):.4f}  (越小越近)")
    print(f"点积       : {dot(q_vector, doc_vectors[best]):.4f}  (越大越近)")

    top_idx = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)[:3]
    print("\n=== 手写最近邻 Top-3 ===")
    for i in top_idx:
        print(f"[{sims[i]:.4f}] {pages[i].chunk_id}《{pages[i].title}》")
        print(f"          {texts[i][:42]}……")

    # 用「标准答案页」算一下 Hit@3：真实评测的雏形
    gold = {"REAL-RAG-TRAVEL-2026#p1"}
    pred = {pages[i].chunk_id for i in top_idx}
    print(f"\nHit@3（命中标准答案住宿标准页）: {'✅' if gold & pred else '❌'}")


def demo_paraphrase_robustness() -> None:
    """换一种问法再查一次：语义检索的核心价值是「不用逐字匹配也能命中」。"""
    embed = make_embeddings()
    pages, texts, doc_vectors = embed_pages(embed=embed)

    variants = [
        "出差住一晚补贴上限是多少？",        # 与制度原文措辞不同
        " printer 显示 E3 是什么故障？",     # 中英混排 + 空格噪声
        "annual leave days",                 # 跨语言问题（英文问中文库）
    ]
    print("\n=== 同义改写鲁棒性 ===")
    for query in variants:
        q_vector = np.array(embed.embed_query(query))
        sims = [cosine(q_vector, v) for v in doc_vectors]
        top_idx = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)[:3]
        hits = [pages[i].chunk_id for i in top_idx]
        print(f"「{query}」→ Top1: {hits[0]}（score={sims[top_idx[0]]:.4f}）")
        print(f"          Top3 全部: {hits}")


def demo_mrl_dim_reduction() -> None:
    """Matryoshka（MRL）截断降维：省内存、省成本（需要模型支持 MRL）。"""
    embed = make_embeddings()
    embed.model = os.getenv("EMBEDDING_MODEL_LARGER", embed.model)
    pages, texts, full_vectors = embed_pages(embed=embed)
    query = "如何申请年假"
    q_full = np.array(embed.embed_query(query))

    dims_list = [256, 512, 1024, len(q_full)]
    gold = {"REAL-RAG-HR-2026#p1"}
    print("\n=== MRL 截断降维 vs 检索质量（真实语料）===")
    print(f"完整向量维度: {len(q_full)}")
    for dims in dims_list:
        if dims > len(q_full):
            continue
        small_vectors = full_vectors[:, :dims]
        q_small = q_full[:dims]
        scores = small_vectors @ q_small / (
            np.linalg.norm(small_vectors, axis=1) * np.linalg.norm(q_small)
        )
        top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:3]
        hit = "✅" if gold & {pages[i].chunk_id for i in top_idx} else "❌"
        ratio = dims / len(q_full)
        print(f"截断到 {dims:>4} 维（内存 {ratio:>5.0%}）: 年假页 Hit@3 = {hit}")

    print("提示：非 MRL 模型不支持直接截断，使用前请查阅模型说明并做离线评测")


def evaluate_dimension_recall(full_vectors: np.ndarray, small_vectors: np.ndarray, queries: np.ndarray, k: int = 5) -> float:
    """把完整维度的 Top-K 当参照，测截断维度保留了多少近邻；只用于相对比较。"""
    if full_vectors.shape[0] != small_vectors.shape[0]:
        raise ValueError("完整向量和截断向量必须对应同一批文档")
    if queries.shape[1] != full_vectors.shape[1]:
        raise ValueError("queries 应传完整维度，函数会按 small_vectors 的维度截断")
    recalls = []
    for query in queries:
        gold = np.argsort(-(full_vectors @ query))[:k]
        small_query = query[: small_vectors.shape[1]]
        candidate = np.argsort(-(small_vectors @ small_query))[:k]
        metrics = retrieval_metrics(candidate.astype(str).tolist(), gold.astype(str).tolist(), k)
        recalls.append(metrics["recall_at_k"])
    return float(np.mean(recalls)) if recalls else 0.0


if __name__ == "__main__":
    demo_embedding_and_retrieval()
    demo_paraphrase_robustness()
    demo_mrl_dim_reduction()
