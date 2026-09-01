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

## 🧭 GraphRAG 不是一个固定算法，也不是所有问题都走图

微软 GraphRAG 当前提供多种查询方式，像医院分诊不同科室：

| 方法 | 主要上下文 | 适合的问题 | 不适合的问题 |
| :--- | :--- | :--- | :--- |
| **Basic** | 普通 Top-K 文本单元 | 单点事实、直接条款 | 全局主题归纳 |
| **Local** | 目标实体、邻居、关系与关联文本 | “谁依赖谁”“某实体有什么关系” | 无明确实体的全局题 |
| **Global** | 分层社区报告 Map-Reduce | “主要主题是什么”“整体如何演进” | 简单事实题，成本不划算 |
| **DRIFT** | 社区起步，再沿局部证据迭代 | 既要广度又要追到细节的探索题 | 低延迟、低预算问答 |

生产系统应先做问题路由，普通事实题继续走混合检索。若所有问题都走 GraphRAG，建图与查询成本会吞掉收益。官方也提供 Standard 与更便宜但图更嘈杂的 FastGraphRAG 索引方法，应按实体保真需求选择。[GraphRAG 方法说明](https://microsoft.github.io/graphrag/index/methods/)

## 🧹 建图最难的不是画边，而是实体对齐

同一个系统可能写作“用户中心”“User Center”“IAM”；同名“支付服务”也可能属于不同地区。若不消歧，会出现两个相反问题：

- **没合并**：一个实体裂成多个节点，关系链断掉；
- **错合并**：两个不同实体被揉成一个，图上产生不存在的关系。

工程上要保存实体的规范名、别名、类型、来源 Chunk、抽取置信度与时间范围。低置信边不能直接进入关键决策；抽样人工审核发现的错误要回流到 Prompt、白名单与别名表。

## 🕰️ 图谱也有版本和保鲜期

“订单服务依赖 MySQL”在迁移 TiDB 后会过期。边应带 `valid_from`、`valid_to` 和来源，新索引完成后重新生成受影响的社区报告。不能只增不删，否则图会把历史关系当成当前事实。

更新成本通常包括：文本切块 → 实体关系抽取 → 实体对齐 → 社区发现 → 社区报告生成。GraphRAG 官方资料指出，标准流程的图抽取占索引成本的大头；因此应支持增量更新、受影响社区重算和索引版本回滚。

## 📏 GraphRAG 要单独评估“图有没有帮忙”

除了最终答案，还应测：实体识别准确率、别名合并错误率、关系正确率、证据来源覆盖、Global/Local 路由准确率，以及相对普通 RAG 的质量增益、索引费用和查询延迟。最有说服力的实验不是“GraphRAG 得了 90 分”，而是同一评测集上：Basic、混合检索、Global、Local、DRIFT 各自在哪类问题胜出。

配套脚本新增了可解释的 Basic/Local/Global/DRIFT 路由基线和实体规范化函数；它们用于讲清决策边界，不冒充完整 GraphRAG 实现。

---

## 🔗 权威官方参考

- [微软 GraphRAG 官方仓库（microsoft/graphrag）](https://github.com/microsoft/graphrag)
- [GraphRAG 官方文档与案例](https://microsoft.github.io/graphrag/)
- [GraphRAG 核心论文：From Local to Global（arXiv:2404.16130）](https://arxiv.org/abs/2404.16130)
- [GraphRAG DRIFT Search 官方说明](https://microsoft.github.io/graphrag/query/drift_search/)
- [Neo4j LangChain 集成指南](https://python.langchain.com/docs/integrations/graphs/neo4j_cypher/)
