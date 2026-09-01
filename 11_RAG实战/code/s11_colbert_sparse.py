"""
s11_colbert_sparse.py
=====================
11.11 配套代码：迟交互、稀疏检索与多库调度
痛点：双塔一句话一向量抹平词级细节、BM25 不会扩词、多知识库路由全靠 if-else
→ 手写 MaxSim 看穿迟交互本质 + 在 testdata 真实制度页上跑 PyLate/SPLADE
+ 语义分诊台路由到真实知识库。
"""

import os

import numpy as np
from pydantic import BaseModel, Field

from shared_corpus import demo_pages, regression_pages


def colbert_maxsim(query_vecs: np.ndarray, doc_vecs: np.ndarray) -> float:
    """标准 ColBERT MaxSim：文档维度取最大值，查询 Token 维度求和。"""
    if query_vecs.ndim != 2 or doc_vecs.ndim != 2 or query_vecs.shape[1] != doc_vecs.shape[1]:
        raise ValueError("query_vecs 与 doc_vecs 必须是特征维度相同的二维数组")
    return float((query_vecs @ doc_vecs.T).max(axis=1).sum())


def demo_maxsim() -> None:
    """手写 MaxSim：迟交互（ColBERT）的灵魂就一行公式。"""
    q = np.random.RandomState(0).randn(3, 8)          # 查询 3 个 token 的向量
    doc_a = np.random.RandomState(1).randn(12, 8)     # 文档 A：12 个 token
    doc_b = doc_a.copy()
    doc_b[5] = q[0]   # 文档 B 某个 token 与查询“遥相呼应”
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    doc_a /= np.linalg.norm(doc_a, axis=1, keepdims=True)
    doc_b /= np.linalg.norm(doc_b, axis=1, keepdims=True)

    print("=== 手写 MaxSim（迟交互）===")
    print(f"文档 A 得分 = {colbert_maxsim(q, doc_a):.3f}   ← 泛泛之交")
    print(f"文档 B 得分 = {colbert_maxsim(q, doc_b):.3f}   ← 一个词的神呼应被捕捉")


def demo_pylate() -> None:
    """用 PyLate 在真实制度页上跑 ColBERT 迟交互检索（首次运行下载约 0.6GB 模型）。

    实现方式说明：迟交互/稀疏检索目前没有成熟的国产 API 端点，教学演示走本地
    小模型（GTE-ModernColBERT 约 0.6GB / SPLADE 约 0.8GB）；生产上可选
    Vespa / Qdrant 的稀疏向量支持或托管服务。参数量小、下载一次即可离线复用。
    """
    try:
        from pylate import indexes, models, retrieve
    except ImportError:
        print("\n[跳过 PyLate] pip install pylate")
        return

    pages = regression_pages()
    # 取现行/废止差旅制度 + 运维手册共 10 页真实语料，页 ID 可追溯
    docs = [p.text for p in pages if not p.source.startswith("外部网页")]
    ids = [p.chunk_id for p in pages if not p.source.startswith("外部网页")]

    colbert = models.ColBERT(model_name_or_path="lightonai/GTE-ModernColBERT-v1")
    # 新版 pylate：先建索引再检索（旧版 docs_embeddings= 直传已被移除）
    index = indexes.PLAID(index_folder="indexes", index_name="regression_kb", override=True)
    index.add_documents(
        documents_ids=ids,
        documents_texts=docs,
        documents_embeddings=list(colbert.encode(docs, is_query=False)),
    )
    retriever = retrieve.ColBERT(index=index)
    query = "住一线城市一晚补贴多少？"
    rankings = retriever.retrieve(colbert.encode(query, is_query=True), k=3)
    print(f"\n=== PyLate 迟交互检索（真实制度页）===\n问题：{query}")
    for rank, r in enumerate(rankings[0][:3], 1):
        # pylate 不同版本返回 dict 或对象，两种都兼容
        if isinstance(r, dict):
            print(f"Top{rank} = {r.get('id', r)}  score={r.get('score', float('nan')):.3f}")
        else:
            payload = getattr(r, "id", r)
            print(f"Top{rank} = {payload}  score={getattr(r, 'score', float('nan')):.3f}")


def demo_splade() -> None:
    """SPLADE：会自己“扩词”的稀疏检索，在真实制度页上看扩词效果（模型约 0.8GB）。"""
    try:
        from sentence_transformers import SparseEncoder
    except ImportError:
        print("\n[跳过 SPLADE] pip install sentence-transformers>=3.3")
        return

    pages = regression_pages()
    docs = [p.text for p in pages if "差旅" in p.source]
    splade = SparseEncoder("naver/splade-cocondenser-ensembledistil")
    doc_embeds = splade.encode(docs)
    query = "住一线城市一晚补贴多少？"
    query_embed = splade.encode_query(query)
    scores = splade.similarity(query_embed, doc_embeds)
    print(f"\n=== SPLADE 稀疏学习检索（真实差旅制度页）===\n问题：{query}")
    ranked = sorted(zip([p.chunk_id for p in pages if "差旅" in p.source], scores.tolist()[0]), key=lambda x: -x[1])
    for doc_id, score in ranked:
        print(f"[{score:.3f}] {doc_id}")


def demo_triage() -> None:
    """多知识库调度：语义分诊 + 置信度兜底，路由到 testdata 真实语料子集。"""
    from langchain_core.prompts import ChatPromptTemplate

    from shared_corpus import make_llm

    class Triage(BaseModel):
        kb: str = Field(description="目标知识库：product / policy / ticket / unknown")
        confidence: float = Field(description="0~1 的置信度")
        reason: str = Field(description="一句话理由")

    triage_llm = make_llm(temperature=0).with_structured_output(Triage)
    ROUTER_PROMPT = ChatPromptTemplate.from_template(
        "你是知识库分诊台。可用知识库：\n"
        "- product：产品功能、参数、价格\n"
        "- policy：公司制度、报销、考勤\n"
        "- ticket：历史工单、故障案例\n"
        "用户问题：{question}\n输出目标库与置信度。拿不准就输出 unknown。"
    )

    # 三张"知识库"对应真实语料的三个子集（页 ID）
    pages = demo_pages() + regression_pages()
    retrievers = {
        "product": [p.chunk_id for p in pages if "AGENT" in p.doc_id or "Vibe" in p.title],
        "policy": [p.chunk_id for p in pages if "TRAVEL" in p.doc_id or "HR" in p.doc_id],
        "ticket": [p.chunk_id for p in pages if "OPS" in p.doc_id or "RX9000" in p.doc_id],
    }

    def route(question: str, threshold: float = 0.7) -> list:
        r = triage_llm.invoke(ROUTER_PROMPT.format(question=question))
        print(f"分诊 → kb={r.kb} confidence={r.confidence:.2f} reason={r.reason}")
        if r.kb != "unknown" and r.confidence >= threshold:
            return retrievers.get(r.kb, [])[:3]
        all_hits = []
        for kb, hits in retrievers.items():
            all_hits.extend(hits[:2])
        return all_hits

    print("\n=== 多库分诊（真实语料页 ID）===")
    for q in ["差旅住宿一晚补贴多少？", "打印机显示 E3 是什么故障？"]:
        print(f"{q} → {route(q)}")


if __name__ == "__main__":
    demo_maxsim()
    demo_pylate()
    demo_splade()
    demo_triage()
