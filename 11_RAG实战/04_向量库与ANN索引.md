# 11.4 海量数据怎么秒级检索？—— 向量数据库与 ANN 索引

> **痛点场景**：你的知识库从 1 万条涨到 1000 万条。如果每次检索都拿查询向量和全部向量**暴力比一遍**（KNN），一次查询要几秒甚至几分钟——用户早等不及了。而企业要求的是**毫秒级返回**。这就需要一个专门的存储引擎：**向量数据库 + 近似最近邻（ANN）索引**。

---

## 🩹 痛点：为什么传统数据库搞不定“找相似”？

- MySQL/PostgreSQL 的 B+ 树索引擅长的是“一维大小比较”：`id > 100`、`name LIKE '张%'`；
- 但一个 1536 维的向量**没有“大小顺序”**，你无法回答 `[0.12, 0.85, ...]` 和 `[0.34, 0.11, ...]` 谁大谁小；
- 高维空间还有著名的**维度灾难**：维度越高，向量分布越稀疏，“最近邻”和“最远点”的差距越来越不明显，普通索引彻底失效。

所以需要专为高维向量设计的**近似最近邻（ANN）**索引：允许牺牲一点点精度，换取上千倍的检索速度。

---

## 💡 思路：用“近似”换“速度”，用“索引结构”换“全表扫描”

<!-- 图表源文件：img/diagrams/04-diagram-01.mmd；视觉风格：Linear 紫色科技感 -->
<p align="center">
  <a href="img/diagrams/04-diagram-01.svg">
    <img src="img/diagrams/04-diagram-01.svg" alt="💡 思路：用“近似”换“速度”，用“索引结构”换“全表扫描”" width="760">
  </a>
</p>

### HNSW：六度人脉 + 高速公路导航

把向量看成地图上的城市，HNSW 建起多层图：
- **顶层（高速公路）**：稀疏骨干网，从北京到深圳先瞬移到南方；
- **中层（省道）**：定位到广东省；
- **底层（街道）**：精准找到目标大楼。

查询时从顶层快速“下钻”到底层，越级跳跃，速度极快。它有两个核心参数：

| 参数 | 作用 | 调大后 |
| :--- | :--- | :--- |
| `M` | 每个节点的最大连接数 | 更准但更耗内存、建库更慢 |
| `ef_construction` | 建图时考虑的候选数 | 图更优但建库更慢 |
| `ef_search` | 查询时考虑的候选数 | **召回更准但更慢**（查询热调参用这个） |

### IVF-PQ：先分小区，再压缩图片

- **IVF（倒排）**：用 K-Means 把 1000 万个向量先分成 1000 个“小区”，查询只进最近几个小区找；
- **PQ（乘积量化）**：把高维向量压成短编码（类似“图片缩略图”），可显著降低内存——具体比例由原始维度、子空间数、编码位数和是否保留原向量决定；适合内存吃紧的大规模场景，但通常会损失召回率。

---

## 🧑‍💻 代码实现一：亲手做一个“暴力 vs 近似候选”小实验

> 我们先不看库，自己用 numpy 复现两种检索，直观感受“精确但慢”与“近似但快”的差距，以及召回率（Recall@k）怎么算。

> 📌 这里的随机投影分桶只是 ANN 思想演示，并不是手写 HNSW。真正的 HNSW 建图、搜索与过滤行为由后面的 Qdrant 示例承担。

```python
import time
import numpy as np

# 造 2 万个 128 维随机向量 + 100 条查询
rng = np.random.default_rng(42)
db = rng.normal(size=(20_000, 128)).astype(np.float32)
db /= np.linalg.norm(db, axis=1, keepdims=True)   # L2 归一化
queries = rng.normal(size=(100, 128)).astype(np.float32)
queries /= np.linalg.norm(queries, axis=1, keepdims=True)

# 暴力精确 Top-10（作为“标准答案”）
t0 = time.perf_counter()
true_topk = []
for q in queries:
    sims = db @ q
    true_topk.append(np.argsort(-sims)[:10])
brute_time = time.perf_counter() - t0

# 随机投影生成 8 位签名，只精排汉明距离 <= 2 的候选
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

# 计算召回率：近似结果里有多少命中精确 Top-10
hits = sum(len(set(true_topk[i]) & set(approx_topk[i])) for i in range(100))
recall = hits / (100 * 10)

print(f"暴力检索: {brute_time*1000:.1f} ms/批, 精确度 100%")
print(f"近似检索: {approx_time*1000:.1f} ms/批, Recall@10 = {recall:.2%}")
print("=> 结论：候选越少通常越快，但 Recall 会掉；参数必须用真实数据评测。")
```

---

## 🧑‍💻 代码实现二：用 Qdrant 建库、配索引参数、做元数据过滤

> 生产环境直接用向量数据库。下面演示 Qdrant 的完整落地姿势：**建集合 → 配 HNSW 参数 → 插入带业务元数据的文档 → 带过滤检索**。

```python
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

# 1. 连接（生产用 url="http://localhost:6333"，演示用内存）
client = QdrantClient(location=":memory:")

# 2. 创建集合：指定向量维度、度量、以及 HNSW 索引参数
client.create_collection(
    collection_name="enterprise_kb",
    vectors_config=qm.VectorParams(size=128, distance=qm.Distance.COSINE),
    hnsw_config=qm.HnswConfigDiff(m=32, ef_construct=200),  # 建图参数：更密的图
)
# 生产服务查询时可传 qm.SearchParams(hnsw_ef=128) 热调参。
# 本地内存模式执行精确搜索，hnsw_ef 不生效，因此演示时不传。

# 3. 插入带业务元数据（payload）的向量与文本
payloads = [
    {"text": "研发部年终奖评定标准与发放时间表", "dept": "rd", "year": 2025},
    {"text": "市场部差旅报销与宴请额度细则", "dept": "marketing", "year": 2025},
    {"text": "研发部服务器故障应急操作手册", "dept": "rd", "year": 2024},
]
vectors = [[0.1] * 128, [0.2] * 128, [0.3] * 128]  # 演示用占位向量
client.upsert(
    collection_name="enterprise_kb",
    points=[qm.PointStruct(id=i, vector=vectors[i], payload=payloads[i]) for i in range(3)],
)

# 4. 带过滤检索：只看研发部(dept=rd) 且 2025 年的文档
results = client.query_points(
    collection_name="enterprise_kb",
    query=[0.15] * 128,
    limit=2,
    query_filter=qm.Filter(
        must=[
            qm.FieldCondition(key="dept", match=qm.MatchValue(value="rd")),
            qm.FieldCondition(key="year", match=qm.MatchValue(value=2025)),
        ]
    ),
).points
for hit in results:
    print(f"score={hit.score:.4f}  text={hit.payload['text']}")
```

> 💡 **元数据过滤的意义**：企业知识库往往要按部门、年份、文档类型做隔离。带过滤的 ANN 检索（filter + vector search）比“先全库搜再筛”更高效，也是向量库相比“自己用 numpy 检索”的核心价值之一。

---

## 🏆 主流向量库选型矩阵

| 向量库 | 架构/语言 | 部署方式 | 核心亮点 | 适用场景 |
| :--- | :--- | :--- | :--- | :--- |
| **[Chroma](https://github.com/chroma-core/chroma)** | Python/C++ | 进程内/单机 Docker | 零配置、与 LangChain 深度集成 | 原型验证、轻量单机 |
| **[Qdrant](https://qdrant.tech/documentation/)** | Rust | 单机/分布式 | Payload 过滤、多租户分区、混合检索 | 中大型企业知识库 |
| **[Milvus](https://milvus.io/docs)** | Go/C++ | 云原生分布式 | 十亿级向量、存储计算分离 | 互联网级海量检索 |
| **[Pgvector](https://github.com/pgvector/pgvector)** | PostgreSQL 插件 | 原生扩展 | 与业务表 Join、支持 ACID | 已有 PG 系统的平滑升级 |
| **[Pinecone](https://www.pinecone.io/)** | 闭源 SaaS | 全托管云 | 托管运维、按服务能力使用 | 出海/不自建向量基础设施的团队 |

### 选型决策树

<!-- 图表源文件：img/diagrams/04-diagram-02.mmd；视觉风格：Stripe 紫蓝 -->
<p align="center">
  <a href="img/diagrams/04-diagram-02.svg">
    <img src="img/diagrams/04-diagram-02.svg" alt="选型决策树" width="760">
  </a>
</p>

---

## 🚀 拓展：关于“Recall@k 与延迟”的取舍

| 优化方向 | 手段 | 代价 |
| :--- | :--- | :--- |
| 提高召回率 | 调大 `ef_search` / 减少 PQ 量化压缩 | 延迟上升、内存上升 |
| 降低延迟 | 调小 `ef_search`、开启量化（Binary/Int8） | 召回率下降 |
| 降低内存 | PQ / 量化、删减 `M` | 精度下降 |

**工程口诀**：先离线用你的真实数据跑一组 Recall@k 与延迟的“成本-收益曲线”，再选一个折中参数，而不是照抄网上默认值。

## 🧭 索引调优不能只看一条平均耗时

ANN 的参数像高速公路的车道数：车多时扩车道能提速，但建路、占地和维护成本也会上升。可靠压测应同时记录：

| 阶段 | 指标 | 回答的问题 |
| :--- | :--- | :--- |
| 建库 | 吞吐、峰值内存、索引大小、构建时长 | 数据每天更新时能否按时建完 |
| 查询 | Recall@K、P50/P95/P99、QPS | 普通请求和最慢请求分别怎样 |
| 过滤 | 不同租户/标签选择率下的 Recall 与延迟 | 过滤后候选很少时索引是否退化 |
| 更新 | 写入可见延迟、删除滞留、重建影响 | 新制度多久能搜到，旧制度多久消失 |
| 故障 | 节点失效、恢复时间、备份恢复 | 服务挂一台是否仍可查、能否恢复 |

### 过滤检索有“先筛还是先搜”的坑

假设全库有一千万条，用户只允许查看财务部的一千条。若先在全库搜 Top-10 再做权限过滤，很可能十条全部被删光；若数据库能把过滤条件带入 ANN 搜索，才有机会在那一千条里找真正的 Top-10。

因此元数据字段要提前建索引，并按真实过滤组合压测。权限字段还必须由服务端根据身份注入，不能相信前端传来的 `tenant=xxx`。

### 选择向量库前先问约束，不先看“性能冠军”

1. 已有 PostgreSQL，规模中等且要频繁 Join 业务表：优先评估 pgvector；
2. 大量复杂 Payload 过滤、多租户向量服务：评估 Qdrant 等专用库；
3. 十亿级、分布式与冷热分层要求明确：评估 Milvus 等分布式系统；
4. 团队不想运维：评估托管服务，但把数据驻留、退出成本和备份导出写进 PoC；
5. 无论选谁，都用自己的向量、过滤比例、并发和硬件复现基准。

---

## 🔗 权威官方参考

- [Qdrant 官方文档（索引与过滤）](https://qdrant.tech/documentation/)
- [Milvus 官方架构文档](https://milvus.io/docs)
- [Pgvector 开源仓库](https://github.com/pgvector/pgvector)
- [Chroma 官方指南](https://docs.trychroma.com/)
- [HNSW 原始论文（Y. Malkov & D. Yashunin, 2016）](https://arxiv.org/abs/1603.09320)
