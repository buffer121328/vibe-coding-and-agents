"""
s07_graphrag.py
===============
11.7 配套代码：知识图谱与 GraphRAG
痛点：宏观问题答不了 → 在 testdata 真实文档上抽取实体关系、轻量社区发现、
基于社区研报的全局问答、Neo4j 落地。
"""

import os

import networkx as nx
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_experimental.graph_transformers import LLMGraphTransformer

from shared_corpus import demo_pages, find_page, make_llm as _make_llm


def make_llm():
    return _make_llm(temperature=0)


def choose_graph_search(question: str) -> str:
    """按问题形态选择检索法；这是可解释基线，不是微软 GraphRAG 的完整路由器。"""
    global_markers = ("整体", "全局", "主要主题", "演进脉络", "分成哪几部分")
    local_markers = ("谁", "哪个系统", "依赖", "关系", "负责")
    multi_hop_markers = ("为什么", "如何影响", "沿着", "间接")
    if any(marker in question for marker in global_markers):
        return "global"
    if any(marker in question for marker in multi_hop_markers) and any(marker in question for marker in local_markers):
        return "drift"
    if any(marker in question for marker in local_markers):
        return "local"
    return "basic"


def canonicalize_entity(name: str, aliases: dict[str, str]) -> str:
    """最小实体消歧：统一大小写与空白后查别名表；生产中还需人工审计和置信度。"""
    normalized = " ".join(name.lower().split())
    return aliases.get(normalized, normalized)


def demo_extract_graph() -> None:
    """用 LLMGraphTransformer 在真实《VibeCoding 协作手册》上抽取实体与关系。"""
    llm = make_llm()
    transformer = LLMGraphTransformer(
        llm=llm,
        allowed_nodes=["人物", "角色", "文档", "工作方式", "质量要求"],   # 白名单控制抽取范围
        allowed_relationships=["负责", "协作", "规定", "要求", "包含"],
    )

    # 真实文档：testdata/真实RAG演示文档/01_VibeCoding_Agent协作手册 第 1、3 页
    pages = demo_pages()
    content = "\n\n".join(find_page(pid, pages).text for pid in
                          ["REAL-RAG-AGENT-2026#p1", "REAL-RAG-AGENT-2026#p3"])
    doc = Document(page_content=content, metadata={"source": "01_VibeCoding_Agent协作手册.md"})

    graph_docs = transformer.convert_to_graph_documents([doc])
    print("=== 从《VibeCoding 协作手册》抽取到的节点 ===")
    for node in graph_docs[0].nodes:
        print(f"[{node.type}] {node.id}")
    print("\n=== 抽取到的关系 ===")
    for rel in graph_docs[0].relationships:
        print(f"{rel.source.id} --({rel.type})--> {rel.target.id}")
    return graph_docs


def demo_community_global() -> None:
    """轻量社区发现 + 社区研报 + 全局问答（体会 GraphRAG 的 Global Search 思路）。

    图的边来自真实协作手册的实体关系（人工整理成固定边表，
    让离线环境也能跑；LLM 自动抽取见 demo_extract_graph）。
    """
    llm = make_llm()

    G = nx.Graph()
    # 与真实手册内容对应的实体关系边表：人类角色 / Agent 职责 / 质量要求
    edges = [
        ("人类负责人", "业务目标"), ("人类负责人", "红线边界"), ("人类负责人", "验收方式"),
        ("Agent", "读代码"), ("Agent", "改代码"), ("Agent", "跑测试"), ("Agent", "报告风险"),
        ("跑测试", "单元测试"), ("跑测试", "浏览器冒烟"),
        ("任务描述", "目标"), ("任务描述", "现状"), ("任务描述", "重点文件"), ("任务描述", "验证方式"),
        ("交付说明", "改了什么"), ("交付说明", "怎么测"),
        ("工程红线", "禁止删测试过关"), ("工程红线", "禁止私自commit"),
    ]
    G.add_edges_from(edges)

    communities = list(nx.community.label_propagation_communities(G))
    print("\n=== 在真实手册实体图上发现的社区 ===")
    for idx, comm in enumerate(communities):
        print(f"社区{idx}: {sorted(comm)}")

    summarize = ChatPromptTemplate.from_template(
        "下面是一组来自《Vibe Coding 协作手册》的相互关联概念，请用一句话总结这一组概念的共同主题：\n{members}\n"
    )
    reports = []
    for comm in communities:
        summary = (summarize | llm).invoke({"members": ", ".join(sorted(comm))}).content
        reports.append(f"[社区] {sorted(comm)}\n{summary}")
        print(f"\n--- 社区研报 ---\n{summary}")

    final_qa = ChatPromptTemplate.from_template(
        "请基于以下各社区的研报，回答用户的全局性问题：\n{reports}\n\n问题：{question}\n回答："
    )
    answer = (final_qa | llm).invoke(
        {"reports": "\n\n".join(reports), "question": "这份协作手册整体把人与 Agent 的分工讲成了哪几个部分，各自职责是什么？"}
    ).content
    print(f"\n=== 全局回答（真实手册内容）===\n{answer}")
    print("\n=== 查询方法路由 ===")
    for question in ["这份手册分成哪几个部分？", "谁负责跑测试？", "住宿标准是多少？"]:
        print(f"{choose_graph_search(question):>6} ← {question}")


def personalized_pagerank_hits(
    graph: nx.Graph,
    seed_nodes: list[str],
    top_k: int = 5,
    alpha: float = 0.85,
) -> list[tuple[str, float]]:
    """HippoRAG 式多跳扩散检索：从入口实体出发用个性化 PageRank 激活全图。

    种子节点即“入口实体”，概率会顺着边一圈圈扩散，越靠前的节点表示
    多跳可达性越高。种子为空或都不在图里时返回空列表（不抛异常）。
    """
    seeds = [node for node in seed_nodes if node in graph]
    if not seeds:
        return []
    scores = nx.pagerank(graph, alpha=alpha, personalization={node: 1.0 for node in seeds})
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return ranked[:top_k]


def _char_ngram_overlap(query: str, keyword: str, n: int = 2) -> float:
    """按字符 n-gram 计算查询对关键词的覆盖度，可复现、无需模型。

    返回命中的 n-gram 占关键词 n-gram 的比例；关键词短于 n 时退化为单字集合。
    """
    def ngrams(text: str) -> set[str]:
        if len(text) < n:
            return set(text)
        return {text[i:i + n] for i in range(len(text) - n + 1)}

    kw_grams = ngrams(keyword)
    if not kw_grams:
        return 0.0
    return len(ngrams(query) & kw_grams) / len(kw_grams)


def dual_keyword_search(
    query: str,
    entity_keywords: dict[str, list[str]],
    topic_keywords: dict[str, list[str]],
    top_k: int = 3,
) -> list[tuple[str, float]]:
    """LightRAG 双层关键词检索简化版：实体层（0.6）+ 主题层（0.4）合并去重。

    entity_keywords / topic_keywords 形如 {关键词: [命中的节点ID, ...]}，
    用字符 n-gram 重合度给每个关键词打分，再按层权重把节点分数加权求和。
    """
    layer_weights = (("entity", entity_keywords, 0.6), ("topic", topic_keywords, 0.4))
    merged: dict[str, float] = {}
    for _, keywords, weight in layer_weights:
        for keyword, node_ids in keywords.items():
            score = _char_ngram_overlap(query, keyword) * weight
            if score <= 0:
                continue
            for node_id in node_ids:
                merged[node_id] = merged.get(node_id, 0.0) + score
    return sorted(merged.items(), key=lambda item: item[1], reverse=True)[:top_k]


def demo_ppr_and_dual_keyword() -> None:
    """演示多跳扩散检索（PPR）与双层关键词检索（LightRAG 简化版）。"""
    G = nx.Graph()
    G.add_edges_from([
        ("出差申请", "差旅标准"), ("差旅标准", "住宿标准"), ("住宿标准", "一线城市"),
        ("住宿标准", "二线城市"), ("差旅标准", "交通标准"), ("交通标准", "高铁"),
    ])
    print("\n=== 个性化 PageRank 多跳扩散（入口：出差申请）===")
    for node, score in personalized_pagerank_hits(G, ["出差申请"], top_k=5):
        print(f"  {score:.4f}  {node}")

    entity_keywords = {
        "住宿": ["TRAVEL-2026-07#p1"],
        "高铁": ["TRAVEL-2026-07#p2"],
        "差旅标准": ["TRAVEL-2026-07#p1"],
    }
    topic_keywords = {
        "报销": ["TRAVEL-2026-07#p1"],
        "审批": ["TRAVEL-2026-07#p3"],
        "出行": ["TRAVEL-2026-07#p2"],
    }
    print("\n=== 双层关键词检索（查询：住宿标准是多少）===")
    for node, score in dual_keyword_search("住宿标准是多少", entity_keywords, topic_keywords):
        print(f"  {score:.4f}  {node}")


def demo_neo4j() -> None:
    """入库 Neo4j 并用 Cypher 查询。需要先启动 Neo4j 容器，否则仅打印示例。"""
    from langchain_community.graphs import Neo4jGraph

    graph = Neo4jGraph(url="bolt://localhost:7687", username="neo4j", password="forge12345")
    # graph.add_graph_documents(graph_docs)  # 把抽取的图文档写入
    cypher = """
MATCH (target {id: 'Agent'})-[:负责]->(duty)
RETURN duty.id AS agent_duty
"""
    print("\n=== Neo4j Cypher 示例（请先在 Neo4j Browser 执行）===")
    print(cypher)


if __name__ == "__main__":
    demo_ppr_and_dual_keyword()   # 离线可跑：PPR 多跳扩散 + 双层关键词，不需要 API Key
    demo_extract_graph()
    demo_community_global()
    # demo_neo4j()  # 可选：先启动 Neo4j 再放开
