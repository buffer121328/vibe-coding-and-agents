# 📦 第十一章配套代码（问题驱动 · 随讲随练）

本章代码与 `11.2 - 11.9`、`11.11 - 11.15` 对应，均围绕真实业务痛点展开。分节脚本可独立运行，综合项目负责把链路总装起来。

> 🎯 **统一真实语料**：除 s02 的清洗管道演示外，所有分节脚本的检索/评估/引用/安全演示都跑在 `testdata/` 的 8 份真实文档（约 28 个页级 Chunk）上，不再使用硬编码的内存假文档。公共语料加载器与模型工厂见 [`shared_corpus.py`](shared_corpus.py)——`demo_pages()`/`all_pages()` 返回带 `doc_id`/`page`/`title` 元数据的页级 Chunk，`make_embeddings()`/`make_llm()` 读取 `.env` 的 OpenAI 兼容端点（含方舟「单次最多 10 条 input」的分批兼容）。每个脚本的检索结果都能用页 ID 追溯到原文。

> 🌟 **质量控制台与可视化工作台**：[`rag_workbench/`](rag_workbench/README.md) 首页可离线检查四份测试语料、版本冲突、引用完整性与提示注入；其余页面把 12 个脚本搬上交互台，需要模型的实验读取本目录 `.env`。

> 📌 说明：综合实战位于 `KnowledgeForge_lite/`；分节脚本负责看清单个机制，总装项目负责验证组件接缝。

## 目录一览

| 目录 / 文件 | 是什么 | 是否入库 |
| :--- | :--- | :--- |
| `s02 ~ s14` 共 12 个脚本 | 与 11.2~11.9、11.11~11.14 各小节一一对应的随堂练（见下方脚本索引） | ✅ 手写源码 |
| [`rag_workbench/`](rag_workbench/README.md) | 🌟 Gradio 质量控制台：离线门禁首页 + 12 个真实脚本实验 + 选型速查 | ✅ 手写源码 |
| [`KnowledgeForge_lite/`](KnowledgeForge_lite/README.md) | 🏭 11.15 端到端综合实战：把本章零件总装成完整 RAG 系统（独立 venv） | ✅ 手写源码 |
| [`skills/`](skills/README.md) | 给 AI 编码助手看的操作手册：工作台接线方式、模型切换改造、版本兼容坑、新增关卡检查单 | ✅ 手写文档 |
| `img/` | 多模态演示素材（`s14_multimodal_rag.py` 用）；缺图时脚本会用 matplotlib 自动生成 `demo_chart.png` | ⚙️ 可自动生成 |
| `indexes/` | 运行产物：跑 `s11_colbert_sparse.py` 时 PyLate/PLAID 写入的检索索引，删掉重跑即重建 | ⚙️ 运行时产物（已 gitignore） |
| `rag_quality.py` | 无模型依赖的质量底座：检索指标、引用门禁、去重、预算、缓存作用域、蓝绿索引 | ✅ 手写源码 |
| `shared_corpus.py` | 公共语料加载器 + 模型工厂：把 testdata 8 份文档切成页级 Chunk 供各脚本共享，读取 `.env` 生成 Embedding/Chat 客户端 | ✅ 手写源码 |
| `testdata/` | 现行/废止制度、故障手册、含注入网页、真实RAG演示文档（协作手册/差旅/设备/HR）共 8 份多页语料 | ✅ 测试语料 |
| `tests/` | 无 API Key 单元测试，验证理论与代码没有走样 | ✅ 测试源码 |

## 环境准备

```bash
cd code
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
pip install -r requirements.txt
# 在根目录创建 .env 并填入至少一个 LLM / Embedding 的 API Key

# 先跑不需要 API Key 的离线门禁
python -m unittest discover -s tests -v
```

## 脚本索引

| 脚本 | 对应章节 | 解决痛点 | 运行方式 |
| :--- | :--- | :--- | :--- |
| `s02_data_pipeline.py` | 11.2 | 数据源又脏又乱 | `python s02_data_pipeline.py` |
| `s03_embedding.py` | 11.3 | 机器不懂语义 | `python s03_embedding.py` |
| `s04_vector_db.py` | 11.4 | 海量数据查不快 | `python s04_vector_db.py` |
| `s05_hybrid_retrieval.py` | 11.5 | 搜不准搜不全 | `python s05_hybrid_retrieval.py` |
| `s06_query_rewrite.py` | 11.6 | 提问含糊 | `python s06_query_rewrite.py` |
| `s07_graphrag.py` | 11.7 | 宏观问题答不了 | `python s07_graphrag.py` |
| `s08_agentic_rag.py` | 11.8 | 幻觉与答非所问 | `python s08_agentic_rag.py` |
| `s09_evaluation.py` | 11.9 | 无法度量系统好坏 | `python s09_evaluation.py` |
| `s11_colbert_sparse.py` | 11.11 | 词级细节被抹平、多库路由靠 if-else | `python s11_colbert_sparse.py` |
| `s12_citation_grounded_gen.py` | 11.12 | 答案没出处、没人敢用 | `python s12_citation_grounded_gen.py` |
| `s13_serving_security.py` | 11.13 | Notebook 跑通但上不了生产 | `python s13_serving_security.py` |
| `s14_multimodal_rag.py` | 11.14 | 知识不止是文字 | `python s14_multimodal_rag.py` |
| `KnowledgeForge_lite/` | 11.15 | 零件都会装，缺总装图 | 见其 README（独立 venv） |

## 各脚本说明

### s02_data_pipeline.py —— 文档解析、清洗与切块
按文件后缀自动选解析器 → 正则去噪（页眉页脚/水印）→ 中文分隔符递归切块 → 注入稳定 Chunk ID、内容哈希、状态与信任级别；输出语料体检报告，并演示 ParentDocumentRetriever 父子切块。

### s03_embedding.py —— 向量嵌入
把 testdata 真实语料变成高维坐标；手写余弦/欧氏/点积三种度量；手写 Top-K 最近邻检索并用标准答案页算 Hit@3；同义改写鲁棒性（中英混排/跨语言）；在真实语料上验证 MRL 截断降维的检索质量。

### s04_vector_db.py —— 向量库与 ANN 索引
用 numpy 复现“暴力检索 vs 近似检索”并计算 Recall@k；用 Qdrant 建集合、配置 HNSW 索引参数、把 testdata 全部真实页入库（payload 带分类/年份/信任级别），演示「政策问题 + 2026 年 + 内部可信」元数据过滤如何挡住废止版与外部网页。

### s05_hybrid_retrieval.py —— 混合检索与重排
手写 RRF 融合算法（真实页 ID 榜单）；在 testdata 真实语料上用 BM25 + Chroma 双路召回；Cross-Encoder 重排取 Top-K；MMR 多样性选择与近重复上下文装箱。

### s06_query_rewrite.py —— 查询重写与意图路由
HyDE：生成假想制度文档 → 用其向量检索真实制度库并对照直接检索；Multi-Query：原问题保底 + 多路并发检索真实语料（含清理模型输出的 markdown 噪声）；结构化意图路由到 ops/policy/hr 三张真实知识库（附判定边界的分诊提示词），并增加多跳检测与改写护栏。

### s07_graphrag.py —— 知识图谱与 GraphRAG
LLMGraphTransformer 在真实《VibeCoding 协作手册》上抽取实体/关系；用 networkx 在真实手册实体图上做社区发现并生成“研报”；全局问答基于真实手册内容；增加 Basic/Local/Global/DRIFT 路由基线与实体规范化；展示 Neo4j 入库与 Cypher 查询。

### s08_agentic_rag.py —— Agentic RAG 自省自校正
基于 LangGraph 构建工程闭环：检索 testdata 真实制度库（打印页 ID）→ 借鉴 CRAG 的文档分级 → 受控兜底 → 生成 → 幻觉复检；明确它不是论文训练方法的等价复现，并加入硬停止预算。

### s09_evaluation.py —— 评估与可观测性
评估集锚定真实页 ID（事实题/版本冲突题/精确编号题/召回排序题/无答案题/安全题）；Hit Rate、Recall、Precision、MRR、nDCG、引用门禁与 P50/P95 等离线指标；手写忠实度用真实制度页做对照；Ragas 裁判模型指向 `.env` 端点（不再请求 OpenAI 官方模型名），样本取自真实制度内容；LangSmith 链路追踪。

### s11_colbert_sparse.py —— 迟交互、稀疏检索与多库调度
按标准公式手写 MaxSim（查询 Token 求和）看穿迟交互；PyLate 在真实制度页上建 PLAID 索引并检索（Top3 可追溯到现行/废止页；本地小模型约 0.6GB，迟交互暂无成熟 API 端点）；SPLADE 稀疏检索跑真实差旅制度页看扩词效果（约 0.8GB）；语义分诊台路由到真实语料子集并低置信全库兜底。

### s12_citation_grounded_gen.py —— 生成层防幻觉与引用溯源
编号引用资料来自真实制度页（REAL-RAG-TRAVEL-2026）；程序校验杜绝幽灵引用并检查逐主张引用完整性；返回前在线忠实度复检（第二句幻觉会被抓出）；高风险流式输出需分句缓冲。

### s13_serving_security.py —— 工程化部署与安全
完整作用域的语义缓存（缓存答案 = 真实制度页内容）；Qdrant tenant payload + ACL（真实文档 + 真实向量检索，rd 员工查管理层文档为空）；逐页扫描 testdata 语料捕获注入投毒；真实制度文档的内容哈希增量同步（改版/删旧版）；蓝绿索引发布/回滚；指令/数据隔离（资料 = 真实运维页 + 真实注入样本原句）。

### s14_multimodal_rag.py —— 多模态与垂直场景 RAG
图片描述文本化入库 + 命中原图 VLM 精读；跨语言检索走 `.env` 的多语言 Embedding API 端点（默认零下载，本地部署 BGE-M3 约 2.3GB 为可选项）；带置信度的 ASR 时间窗；表格计算下放与只读操作门禁。

## 🏭 总装项目：KnowledgeForge_lite/

`11.15 端到端综合实战` 的完整代码——开源项目 [KnowledgeForge](https://github.com/buffer121328/KnowledgeForge) 的蒸馏教学版（约 900 行）。含 4 篇种子文档、LangGraph 四道闸门问答闭环、知识图谱（LLM 抽三元组 → Neo4j Cypher 存储，NetworkX 兜底）、双层评估（手写门禁 + Ragas 全量三元组）、FastAPI/SSE 服务化、Air 纯 Python 聊天页（为什么选 Air 见其 README）与 docker compose 一键起全套（Neo4j + 应用）。独立依赖与启动方式见 [KnowledgeForge_lite/README.md](KnowledgeForge_lite/README.md)。

## 注意事项

- 涉及 LLM/Embedding 的脚本需要可用的 API Key（OpenAI 兼容端点即可，配置读 `.env`；`OPENAI_API_BASE`/`EMBEDDING_MODEL` 控制向量端点，`MIMO_*`/`ARK_*`/`CHAT_MODEL` 控制对话端点）；方舟等「单次最多 10 条 input」的端点已由 `shared_corpus.embed_texts_batched` 分批兼容；
- **模型下载分三档**：绝大多数演示（s03/s04/s06/s08/s09/s12/s13/s14）只调 `.env` 里的 API 端点，零模型下载；s14 跨语言的 BGE-M3 本地部署（约 2.3GB）是**可选项**，默认走 API；仅 s05 重排（约 1GB）和 s11 的 ColBERT/SPLADE（约 0.6–0.8GB）用本地小模型——迟交互/稀疏检索暂无成熟 API 端点，模型下载一次即可离线复用，各脚本头部与对应小节文档都写了 API 替代路线；
- `s07_graphrag.py` 的 Neo4j 段落需要先启动 Neo4j 容器，跳过不影响其余演示；`s13_serving_security.py` 的 ACL 段落用 Qdrant 内存模式即可，无需本地服务；
- 离线单元测试不调用模型；真实 LLM、Embedding 与本地重排/稀疏检索演示耗时取决于端点和模型下载，不承诺固定三分钟。
