# 11.7 宏观问题答不了怎么办？—— 知识图谱与 GraphRAG

> **痛点场景**：用户问“把过去三年公司技术架构的演进脉络总结一下”，或者“这本书的核心价值观是什么”。你把它喂给向量 RAG，它只会从库底捞几个带“架构”“技术”的碎片，以偏概全、断章取义。**因为向量检索本质是“局部相似度”，而这类问题是“全局总结题”——需要把所有相关概念的关系网串起来看。**

---

## 🩹 痛点：向量 RAG 的“一叶障目”

- **点状检索**：向量检索每次只能捞出“碎片”，就像抽屉里翻便签——你抽到“张三主导支付重构”，抽不到它和“弃用 Oracle”“引入 TiDB”之间的关系；
- **关系丢失**：知识以“张三 →(主导)→ 支付系统 →(迁移至)→ TiDB”这样的**关系链**存在，但切块把这条链切断了；
- **全局问题**：“总结全书主旨”“梳理架构演进”没有任何一个单独切块能回答。

<!-- 图表源文件：img/diagrams/07-diagram-01.mmd；视觉风格：Linear 紫色科技感 -->
<p align="center">
  <a href="img/diagrams/07-diagram-01.svg">
    <img src="img/diagrams/07-diagram-01.svg" alt="🩹 痛点：向量 RAG 的“一叶障目”" width="760">
  </a>
</p>

> 💡 **比喻**：向量 RAG 是散落一桌的便签纸；GraphRAG 是刑警队墙上钉着红线、把嫌疑人与资金流向串起来的“案件线索图”——哪怕两个实体从未出现在同一份文档里，顺着关系也能推理出全貌。

---

## 💡 思路：微软 GraphRAG 的四步流水线

微软开源了 [GraphRAG](https://github.com/microsoft/graphrag)（论文 [arXiv:2404.16130](https://arxiv.org/abs/2404.16130)），核心流程：

<!-- 图表源文件：img/diagrams/07-diagram-02.mmd；视觉风格：GitHub Dark -->
<p align="center">
  <a href="img/diagrams/07-diagram-02.svg">
    <img src="img/diagrams/07-diagram-02.svg" alt="💡 思路：微软 GraphRAG 的四步流水线" width="760">
  </a>
</p>

1. **抽取**：用 LLM 从每个切块里抽出实体（人/系统/概念）、关系（“负责”“依赖”“弃用”）、协变量（事实主张）；
2. **建图**：实体对齐去重后，形成“节点 + 边”的知识图谱；
3. **Leiden 社区发现**：把关系紧密的实体自动聚成“朋友圈”（社区），例如【交易与资金社区】【身份认证社区】；
4. **社区摘要**：让 LLM 给每个社区写一份浓缩“研报”，全局问题就直接在这些研报上做 Map-Reduce 汇总。

---

## 🧑‍💻 代码实现一：LLM 抽取实体与关系（LangChain LLMGraphTransformer）

```python
from langchain_core.documents import Document
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o", temperature=0)
transformer = LLMGraphTransformer(
    llm=llm,
    allowed_nodes=["人物", "系统", "技术组件", "组织"],          # 白名单：控制抽取范围
    allowed_relationships=["负责", "依赖", "重构成", "部署于"],   # 关系白名单
)

doc = Document(page_content="""
张三领导基础架构部，2025 年主导将老旧的 MySQL 订单库重构为 TiDB 分布式集群。
该 TiDB 集群部署于阿里云上海可用区，被结算系统和风控系统直接依赖。
李四负责监控该集群的实时告警。
""")

graph_docs = transformer.convert_to_graph_documents([doc])
print("=== 抽取到的节点 ===")
for node in graph_docs[0].nodes:
    print(f"[{node.type}] {node.id}")
print("\n=== 抽取到的关系 ===")
for rel in graph_docs[0].relationships:
    print(f"{rel.source.id} --({rel.type})--> {rel.target.id}")
```

> 💡 **白名单的意义**：不限制的话 LLM 可能抽出几百种五花八门的关系类型，导致图不可控。先白名单约束，是工程化的关键一步。

---

## 🧑‍💻 代码实现二：轻量社区发现 + 全局问答（自己体会“全局视野”）

> 微软 GraphRAG 内部用 Leiden 算法。这里我们用同样思路做一次最小演示：**把关系图聚成社区 → 给社区写摘要 → 全局问题基于摘要汇总**。

```python
import networkx as nx
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# 1. 构造一个小图谱（节点=系统，边=依赖关系）
G = nx.Graph()
edges = [
    ("订单服务", "支付网关"), ("订单服务", "库存服务"), ("支付网关", "结算系统"),
    ("结算系统", "风控系统"), ("用户中心", "OAuth2"), ("用户中心", "JWT认证"),
]
G.add_edges_from(edges)

# 2. 用标签传播做社区发现（轻量版“朋友圈”聚类；生产用 Leiden）
communities = list(nx.community.label_propagation_communities(G))
print("=== 发现的社区 ===")
for idx, comm in enumerate(communities):
    print(f"社区{idx}: {sorted(comm)}")

# 3. 每个社区生成“研报摘要”
summarize = ChatPromptTemplate.from_template(
    "下面是一组相互依赖的系统，请用一句话总结这一组系统的共同业务定位：\n{members}\n"
)
reports = []
for comm in communities:
    summary = (summarize | llm).invoke({"members": ", ".join(sorted(comm))}).content
    reports.append(f"[社区] {sorted(comm)}\n{summary}")
    print(f"\n--- 社区研报 ---\n{summary}")

# 4. 全局问题：直接基于所有社区研报汇总（这就是 Global Search 的核心）
global_question = "这个系统的整体架构分成了哪几个部分，各自职责是什么？"
final_qa = ChatPromptTemplate.from_template(
    "请基于以下各子系统的社区研报，回答用户的全局性问题：\n{reports}\n\n问题：{question}\n回答："
)
answer = (final_qa | llm).invoke({"reports": "\n\n".join(reports), "question": global_question}).content
print(f"\n=== 全局回答 ===\n{answer}")
```

---

## 🧑‍💻 代码实现三：入库 Neo4j 并用 Cypher 查询

```python
# 前置：docker run -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5
from langchain_community.graphs import Neo4jGraph

graph = Neo4jGraph(url="bolt://localhost:7687", username="neo4j", password="password")
# graph.add_graph_documents(graph_docs)  # 把上面抽取的图文档写入

# Cypher 查询示例：找“谁依赖了 TiDB 集群”
cypher = """
MATCH (target {id: 'TiDB 分布式集群'})<-[:依赖]-(upstream)
RETURN upstream.id AS upstream_component
"""
# result = graph.query(cypher)
# print(result)
print("（在 Neo4j Desktop / Browser 中执行上面的 Cypher 即可可视化图谱）")
```

> 💡 **工程选型提示**：如果只是几十万条以内的“中等图谱”，完全可以用 networkx + 社区摘要自己搭轻量版；只有图谱达到百万级节点、需要复杂图查询时，才值得引入 Neo4j 这类专业图数据库。

---

## 🔗 权威官方参考

- [微软 GraphRAG 官方仓库（microsoft/graphrag）](https://github.com/microsoft/graphrag)
- [GraphRAG 官方文档与案例](https://microsoft.github.io/graphrag/)
- [GraphRAG 核心论文：From Local to Global（arXiv:2404.16130）](https://arxiv.org/abs/2404.16130)
- [Neo4j LangChain 集成指南](https://python.langchain.com/docs/integrations/graphs/neo4j_cypher/)
