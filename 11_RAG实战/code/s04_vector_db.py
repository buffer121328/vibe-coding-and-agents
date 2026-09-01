"""
s04_vector_db.py
================
11.4 配套代码：向量库与 ANN 索引
痛点：海量数据查不快 → 亲手验证「暴力 vs 近似」，再用 Qdrant 把 testdata
真实制度文档建库、配 HNSW 索引参数、按元数据（部门/年份/信任级别）过滤检索。
"""

import time

import numpy as np

from shared_corpus import all_pages, embed_pages_batched, make_embeddings


def demo_brute_vs_approx() -> None:
    """用随机投影分桶演示 ANN 的取舍；这不是 HNSW 实现，HNSW 见 Qdrant 示例。"""
    rng = np.random.default_rng(42)
    db = rng.normal(size=(20_000, 128)).astype(np.float32)
    db /= np.linalg.norm(db, axis=1, keepdims=True)      # L2 归一化
    queries = rng.normal(size=(100, 128)).astype(np.float32)
    queries /= np.linalg.norm(queries, axis=1, keepdims=True)

    # 暴力精确 Top-10（作为标准答案）
    t0 = time.perf_counter()
    true_topk = []
    for q in queries:
        sims = db @ q
        true_topk.append(np.argsort(-sims)[:10])
    brute_time = time.perf_counter() - t0

    # 随机投影把向量变成 8 位签名；查询只精排汉明距离 <= 2 的桶。
    # 这只是教学用候选生成，避免把一个简单分桶实验误称为 HNSW。
    projections = rng.normal(size=(128, 8)).astype(np.float32)
    db_codes = (db @ projections) >= 0
    t0 = time.perf_counter()
    approx_topk = []
    for q in queries:
        query_code = (q @ projections) >= 0
        cand = np.where(np.count_nonzero(db_codes != query_code, axis=1) <= 2)[0]
        if len(cand) < 10:
            cand = np.where(np.count_nonzero(db_codes != query_code, axis=1) <= 3)[0]
        sims = db[cand] @ q
        approx_topk.append(cand[np.argsort(-sims)[:10]])
    approx_time = time.perf_counter() - t0

    hits = sum(len(set(true_topk[i]) & set(approx_topk[i])) for i in range(100))
    recall = hits / (100 * 10)
    print(f"暴力检索: {brute_time * 1000:.1f} ms/批, 精确度 100%")
    print(f"近似检索: {approx_time * 1000:.1f} ms/批, Recall@10 = {recall:.2%}")
    print("=> 结论：候选越少通常越快，但 Recall 会掉；真实 HNSW/IVF 应在真实语料上画曲线。")


def build_kb_points(pages=None, vectors=None):
    """把页级真实语料转成 Qdrant 点：向量来自真实 Embedding，payload 是真实元数据。"""
    from qdrant_client.http import models as qm

    pages = pages or all_pages()
    if vectors is None:
        _, _, vectors = embed_pages_batched(pages, make_embeddings())

    points = []
    for i, p in enumerate(pages):
        # 给真实文档打上业务过滤字段：来源分类、年份、信任级别
        category = "ops" if ("RX9000" in p.doc_id or "OPS-HELP" in p.doc_id) else "policy"
        year = 2025 if "2025" in p.doc_id else 2026
        trust = "external" if "外部网页" in p.source else "internal"
        payload = {
            "text": p.text,
            "doc_id": p.doc_id,
            "page": p.page,
            "title": p.title,
            "source": p.source,
            "category": category,
            "year": year,
            "trust": trust,
        }
        points.append(qm.PointStruct(id=i, vector=vectors[i].tolist(), payload=payload))
    return points


def demo_qdrant() -> None:
    """用 Qdrant 建集合、配置 HNSW 索引参数、插入真实文档并做元数据过滤检索。"""
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qm

    pages, _, vectors = embed_pages_batched(all_pages(), make_embeddings())
    dim = len(vectors[0])

    client = QdrantClient(location=":memory:")   # 生产用 url="http://localhost:6333"

    # 1. 创建集合：向量维度来自真实 Embedding、度量、HNSW 建图参数
    client.create_collection(
        collection_name="enterprise_kb",
        vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
        hnsw_config=qm.HnswConfigDiff(m=32, ef_construct=200),
    )
    # 生产服务查询时可传 search_params=qm.SearchParams(hnsw_ef=128) 热调参。
    # 本示例使用 Qdrant 本地内存模式，它执行精确搜索，因此不传 hnsw_ef，避免误导。

    # 2. 真实入库：testdata 全部页级语料，payload 带业务元数据
    client.upsert(collection_name="enterprise_kb", points=build_kb_points(pages, vectors))
    print(f"\n=== Qdrant 真实入库 {len(pages)} 页（向量维度 {dim}）===")

    # 3. 语义检索：真实问题，真实向量
    question = "打印机显示 E3 该怎么办？"
    q_vector = np.array(make_embeddings().embed_query(question))
    results = client.query_points(
        collection_name="enterprise_kb",
        query=q_vector.tolist(),
        limit=3,
    ).points
    print(f"\n=== 无过滤检索：「{question}」===")
    for hit in results:
        print(f"score={hit.score:.4f}  [{hit.payload['doc_id']}#p{hit.payload['page']}]《{hit.payload['title']}》")

    # 4. 带过滤的检索：换一个差旅问题，只看 2026 年、内部可信的政策文档
    question = "出差住宿报销上限是多少？"
    q_vector = np.array(make_embeddings().embed_query(question))
    results = client.query_points(
        collection_name="enterprise_kb",
        query=q_vector.tolist(),
        limit=3,
        query_filter=qm.Filter(
            must=[
                qm.FieldCondition(key="category", match=qm.MatchValue(value="policy")),
                qm.FieldCondition(key="year", match=qm.MatchValue(value=2026)),
                qm.FieldCondition(key="trust", match=qm.MatchValue(value="internal")),
            ]
        ),
    ).points
    print(f"\n=== 带过滤检索：「{question}」（category=policy, year=2026, trust=internal）===")
    for hit in results:
        print(f"score={hit.score:.4f}  [{hit.payload['doc_id']}#p{hit.payload['page']}]《{hit.payload['title']}》")
    print("=> 过滤的价值：废止旧版（2025）和不可信外部网页语义再近也进不来。")


if __name__ == "__main__":
    demo_brute_vs_approx()
    demo_qdrant()
