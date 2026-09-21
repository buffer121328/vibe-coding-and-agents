# 第十一章：现代 RAG 系统 —— 从完整生命周期到问题驱动实战

> **“如果说大模型微调是让学生脱产读研三年，那么 RAG（检索增强生成）就是给学生发一套随身携带、随查随翻的百科全书。”**
> 在本章中，我们不再像传统教程那样按“Naive → Advanced → Agentic”的版本号叙事，而是**先把 RAG 这台机器的完整生命周期（数据准备 → 检索 → 生成 → 评估运维）整体拆开给你看**，然后**用一个接一个的真实业务痛点驱动我们去动手实现**：数据太脏怎么办？机器不懂语义怎么办？海量数据查不快怎么办？搜不准、搜不全怎么办？……

---

## 本章学习路径：三种视角

### 视角一：先看全局 —— RAG 完整生命周期（11.1）

一张图把 RAG 系统的四大层次串起来，让你先建立“整机”概念，再逐层深入：

<!-- 图表源文件：img/diagrams/overview-diagram-01.mmd；视觉风格：Linear 紫色科技感 -->
<p align="center">
  <a href="img/diagrams/overview-diagram-01.svg">
    <img src="img/diagrams/overview-diagram-01.svg" alt="视角一：先看全局 —— RAG 完整生命周期（11.1）" width="760">
  </a>
</p>

### 视角二：再看局部 —— 问题驱动（11.2 - 11.9）

围绕企业在落地 RAG 时**最常碰到的 8 个真实痛点**，每个小节用「痛点 → 思路 → 代码实现 → 拓展」四段式带你动手解决：

| 序号 | 你会遇到的痛点 | 对应解法 | 技术关键词 |
| :--- | :--- | :--- | :--- |
| 11.2 | 文档数据源又脏又乱 | 解析、清洗与切块 | PDF/Word/HTML/Markdown 解析、语义切块、父子切块、迟切块/上下文检索、RAPTOR |
| 11.3 | 机器怎样比较文本语义 | 向量嵌入 | Embedding、余弦相似度、多模态、MRL 降维、领域 Embedding 微调 |
| 11.4 | 数据上千万条查得太慢 | 向量数据库与索引 | HNSW、IVF-PQ、Qdrant/Chroma/Pgvector |
| 11.5 | 搜不准、搜不全 | 混合检索与重排 | BM25+Dense、RRF、Cross-Encoder 选型/微调、上下文编排、可解释检索 |
| 11.6 | 用户问得太含糊 | 查询重写与意图路由 | HyDE、Multi-Query、Step-Back、结构化路由、前沿检索（Search-R1） |
| 11.7 | 宏观总结问题答不了 | 知识图谱与 GraphRAG | 实体关系抽取、Leiden 社区、Global/Local Search、LightRAG/HippoRAG |
| 11.8 | 答非所问、还一本正经胡说 | Agentic RAG | Self-RAG、CRAG、LangGraph 自省闭环、长期记忆式 RAG、Deep Research |
| 11.9 | 说不清系统到底变好没有 | 评估与可观测性 | RAG 三元组、Ragas、细粒度归因（RAGChecker）、中文基准、RAFT/AutoRAG |

### 视角三：最后进阶 —— 选型与生产实践（11.10 - 11.14）

主干打通之后，再讨论方案选型、生产环境和端到端总装：

| 序号 | 生产里的拦路虎 | 对应解法 | 技术关键词 |
| :--- | :--- | :--- | :--- |
| 11.10 | 零件很多，不知道买、改还是自研 | 平台与框架选型 | 约束清单、PoC、退出成本、总拥有成本 |
| 11.11 | 词级细节被一句话一向量抹平 | 迟交互与稀疏检索 | ColBERT MaxSim、SPLADE、ColPali、多库调度 |
| 11.12 | 答案没出处，没人敢用 | 生成层防幻觉与引用溯源 | 接地生成、引用标注、忠实度复检、拒答、流式 |
| 11.13 | Notebook 跑通但上不了生产 | 工程化部署与安全 | FastAPI 流式、语义缓存、多租户 ACL、增量更新、注入防护、知识投毒/隐私泄露防御 |
| 11.14 | 知识不止是文字 | 多模态与垂直场景 | 图片描述/VLM 直读、跨语言 BGE-M3、音视频转写、结构化数据（CSV/JSON/SQL）、端侧 |
| 11.15 | 零件都会装，就是缺总装图 | 端到端综合实战 KnowledgeForge Lite | 工牌 ACL、三路 RRF、四道闸门、拒答、回归门禁、SSE 服务化 |

---

## 章节目录导航

01. **[11.1 RAG 完整生命周期分层](./01_RAG完整生命周期分层.md)**
    - **核心内容**：不按“版本号”讲故事，而是把 RAG 当成一台流水线机器拆成四大层次解剖；每个层次回答什么问题、包含哪些组件、层与层之间如何流转；RAG 与微调/长上下文/Agent/LLM Wiki（知识编译）的边界怎么划。
02. **[11.2 数据源又脏又乱怎么办？—— 文档解析、清洗与切块](./02_文档解析清洗与切块.md)**
    - **核心内容**：输入文档的质量如何影响后续结果；Markdown/HTML/Word/文字层 PDF 的解析与去噪；从固定长度切块到递归字符、标题层级、语义切块与父子切块；手写一条“文件 → 干净 Chunk → 元数据”的完整管道；再用 MinerU 4.x、Docling 处理扫描件、表格、公式和图文混排文档；最后补上两条“给块补上下文”的现代做法（迟切块、上下文检索）与让长文档长出“摘要树”的 RAPTOR。
      - **可跑的落地版**：`code/KnowledgeForge_lite/` 里这套是**真跑通**的——`decode_bytes` 两档编码兜底、Word 表格按文档原顺序抽取、未填模板标记、`chunking.py` 的标题层级切块（同时认 Markdown `#` 与中文「第X条」编号）与表格整段保护。附带一个只有跑评测才会发现的坑：**装箱与编排的顺序**写反会静默丢掉第二名。详见该章「把上面两条落成代码」一节。
03. **[11.3 机器怎么读懂语义？—— 向量嵌入与多模态](./03_向量嵌入与多模态.md)**
    - **核心内容**：Embedding 把文字变成高维坐标；余弦/欧氏/内积三种度量的适用边界；主流模型天梯榜与 MRL 降维；多模态嵌入（CLIP/ColPali）解决“图文混杂”场景；再用“正例 + 难负例”三元组把通用模型微调成懂行业黑话的检索器。
04. **[11.4 海量数据怎么秒级检索？—— 向量数据库与 ANN 索引](./04_向量库与ANN索引.md)**
    - **核心内容**：为什么 B+ 树搞不定高维向量；HNSW 与 IVF-PQ 两种索引的“快”与“省”；主流向量库选型矩阵；动手用 Qdrant 建库、调索引参数、做元数据过滤。
05. **[11.5 搜不准、搜不全怎么办？—— 混合检索与重排](./05_混合检索与重排.md)**
    - **核心内容**：向量检索的“意会”与 BM25 的“抠字眼”如何互补；手写 RRF 融合算法；Cross-Encoder 重排为什么能优于双塔；上下文压缩防止“上下文污染”；再讲重排模型的选型/微调/蒸馏、上下文编排（位置偏置与 Token 预算）以及可解释检索。
06. **[11.6 用户问得太含糊怎么办？—— 查询重写与意图路由](./06_查询重写与意图路由.md)**
    - **核心内容**：把“它怎么又崩了”翻译成技术文档语言；HyDE 以答搜答、Multi-Query 多路并发、Step-Back 抽象回退、指代消解；用结构化输出把问题路由到正确的知识库；末尾看一眼“让模型自己学会何时检索”的前沿路线（Search-R1、生成式检索）。
07. **[11.7 宏观问题答不了怎么办？—— 知识图谱与 GraphRAG](./07_知识图谱与GraphRAG.md)**
    - **核心内容**：向量 RAG 为什么只能“一叶障目”；实体/关系/协变量抽取；Leiden 社区发现与社区摘要；微软 GraphRAG 的 Global/Local 双模检索；轻量级图谱落地；并对比两条“便宜版 GraphRAG”——LightRAG 与 HippoRAG。
08. **[11.8 答非所问与幻觉怎么自愈？—— Agentic RAG](./08_Agentic_RAG自省自校正.md)**
    - **核心内容**：单向管线的三大硬伤；Self-RAG 的反思 Token、CRAG 的置信度分级、Adaptive RAG 的难度路由；用 LangGraph 把 RAG 升级成会自我纠错的智能体闭环；再把“跨会话记忆”接成独立记忆库，并看 Deep Research 如何把这套闭环放大成研究报告。
09. **[11.9 怎么证明系统真的变好了？—— 评估与可观测性](./09_评估与可观测性.md)**
    - **核心内容**：没有指标等于闭眼开车；RAG 三个主要指标；用 Ragas 自动化打分；再用手写指标看穿每个分数背后的含义；线上链路可观测；上线后的持续治理——A/B 实验、LLM-as-Judge 的裁判偏差校准、回归集治理与 RAG×微调组合拳；此外补上细粒度归因（RAGChecker）、中文基准（CRUD-RAG/RGB）与检索侧微调/自动调参（RAFT/AutoRAG）。
10. **[11.10 实际项目中的落地：低代码平台与主流框架整体选型](./10_工业级落地与主流框架选型.md)**
    - **核心内容**：三条落地路线（买车/改车/焊车）；Dify、飞书 Aily、FastGPT、MaxKB、扣子 Coze 等低代码平台整体；RAGFlow、LlamaIndex、Haystack、DSPy 等开源框架对比；一张选型地图与“不足/可扩充”清单。
11. **[11.11 检索的下一档功率：迟交互、稀疏学习与多库调度](./11_迟交互与稀疏检索.md)**
    - **核心内容**：双塔“一句话一向量”抹平词级细节的根因；手写 MaxSim 看穿 ColBERT 迟交互本质；SPLADE “会扩词的 BM25”；ColPali 把页面当图片直接检索；多知识库语义分诊、置信度兜底与路由治理。
12. **[11.12 答案对了却没人敢用？—— 生成层防幻觉与引用溯源](./12_生成层防幻觉与引用溯源.md)**
    - **核心内容**：可追责是企业级 RAG 的最后一公里；接地 Prompt、编号引用协议 + 程序校验杜绝幽灵引用、返回前忠实度复检、拒答兜底四道闸门；引用粒度选型与流式生成。
13. **[11.13 从 Notebook 到生产系统 —— RAG 工程化部署与安全](./13_工程化部署与安全.md)**
    - **核心内容**：FastAPI + SSE 服务化；嵌入/语义/响应三级缓存降本与失效红线；检索层多租户 ACL 权限隔离；内容哈希幂等增量更新；Prompt 注入四层纵深防护与上线验收清单；并补齐数据面攻击的防御——知识投毒与隐私泄露。
14. **[11.14 知识不止是文字 —— 多模态与垂直场景 RAG](./14_多模态与垂直场景RAG.md)**
    - **核心内容**：多模态三条路线（文本化/多模态嵌入/VLM 直读）怎么选；图文混排 PDF 组合拳；跨语言 RAG 三方案；音视频转写 + 时间戳元数据；结构化数据（表格/CSV/JSON）RAG 的三种路线与 Text-to-SQL 安全笼子；端侧 RAG。
15. **[11.15 端到端综合实战 —— KnowledgeForge Lite](./15_端到端综合实战_KnowledgeForge_lite.md)**
    - **核心内容**：把 11.2~11.14 的零件总装成一台能跑的机器——以开源项目 [KnowledgeForge](https://github.com/buffer121328/KnowledgeForge) 为蓝本蒸馏出的教学版（`code/KnowledgeForge_lite/`）。主干与完整版同构：工牌 ACL 打分前裁库（11.13）、本地改写护栏（11.6）、向量+BM25+图谱三路加权 RRF（11.5/11.7）、四道闸门（11.8/11.12）、双层评估（11.9）、Air 聊天页可切换工牌。JWT/Celery/HyDE/ColBERT 等外壳或进阶件故意不装。含离线测试、财务密级种子、投毒 HTML、Docker 五概念补课与越权/投毒破坏性实验。

---

## 第十一章整体路线图

<!-- 图表源文件：img/diagrams/overview-diagram-02.mmd；视觉风格：Macaron 马卡龙 -->
<p align="center">
  <a href="img/diagrams/overview-diagram-02.svg">
    <img src="img/diagrams/overview-diagram-02.svg" alt="🗺️ 第十一章整体路线图" width="860">
  </a>
</p>

---

## 关于本章代码

本章代码采用**问题驱动、随讲随练**的方式：

1. **正文内联代码**：每个小节内都包含聚焦该问题的、可直接复制运行的 Python 代码片段（基于 LangChain / LangGraph 生态，并逐行注释）；
2. **`code/` 目录脚本**：与 11.2 - 11.9、11.11 - 11.14 一一对应的 12 个完整可运行脚本（`s02_data_pipeline.py` … `s09_evaluation.py`、`s11_colbert_sparse.py` … `s14_multimodal_rag.py`）。所有检索/评估/引用演示都跑在 `testdata/` 的 8 份真实文档上，一共 **86 个页级 Chunk**（演示 4 份 45 页 + 回归 4 份 41 页，每份 8 到 14 页不等）。格式是 **md / pdf / docx / html 混排**，不是清一色 Markdown。HR 年假写的是入职满一年 **5 天**，不是“年假 15 天”。页 ID 可追溯到原文；公共语料加载器与模型工厂见 `code/shared_corpus.py`，详见 [code/README.md](code/README.md)；
3. **`code/rag_workbench/` RAG 质量控制台与工作台**：🌟 默认首页无需密钥，可直接检查 8 份测试语料、版本冲突、引用完整性和提示注入；其余页面把 12 个脚本搬上交互台，运行方式见 [code/rag_workbench/README.md](code/rag_workbench/README.md)；
4. **`code/KnowledgeForge_lite/` 总装项目**：11.15 端到端综合实战的完整代码——完整版 [KnowledgeForge](https://github.com/buffer121328/KnowledgeForge) 的蒸馏教学版。主干与完整版同构：工牌 ACL、三路检索进 RRF、证据资格与四道闸门、Ragas 0.4 三指标评测、三栏工作台（会话柜 · 转写 · 证据抽屉，刷新不丢）；含差旅/FAQ/故障/安全/财务密级/办公用品 + 投毒 HTML、450 个离线测试、七个入口脚本与独立依赖清单。

> 📌 注意：完整版“综合实战”大项目（含 Celery/Kafka/Neo4j/多租户的生产级形态）作者另有安排；11.15 的 KnowledgeForge Lite 是它的蒸馏教学版，动手从 [11.15](./15_端到端综合实战_KnowledgeForge_lite.md) 开始即可。11.10 是“选型地图”章节，不附带代码脚本；想动手的读者可跳回 11.2~11.9 对应脚本。

> 🧪 **新增离线质量门禁**：`code/rag_quality.py` 把检索指标、引用完整性、上下文去重、Agent 循环预算、缓存作用域和蓝绿索引变成可测试代码；`code/testdata/` 提供现行制度、废止旧版、故障手册、含注入网页与真实RAG演示文档（协作手册/差旅/设备/HR）共 8 组多页语料，格式覆盖 Markdown、文字层 PDF、Word 和 HTML。无需 API Key 即可在 `code/` 下运行 `python -m unittest discover -s tests -v`。总装项目另有一份 `code/KnowledgeForge_lite/tests/`（**450** 个用例），覆盖工牌 ACL、三路 RRF、图谱映射回切块、投毒隔离、改写护栏、资格不再被分级模型一票否决。

---

## 官方权威资源与论文直达

- **Dify 官方文档**：[docs.dify.ai/zh](https://docs.dify.ai/zh)（知识库专题：[docs.dify.ai/zh/use-dify/knowledge/readme](https://docs.dify.ai/zh/use-dify/knowledge/readme)）
- **RAGFlow 官方文档**：[ragflow.io/docs/dev](https://ragflow.io/docs/dev/)（中文：[ragflow.com.cn/docs/dev](https://ragflow.com.cn/docs/dev/)）
- **LlamaIndex 官方文档**：[docs.llamaindex.ai](https://docs.llamaindex.ai)
- **飞书 Aily 官方帮助中心**：[aily.feishu.cn/hc](https://aily.feishu.cn/hc/1u7kleqg/uwa9ehft)
- **LangChain RAG 官方概念文档**：[python.langchain.com/docs/concepts/rag/](https://python.langchain.com/docs/concepts/rag/)
- **LangGraph 官方文档**：[langchain-ai.github.io/langgraph/](https://langchain-ai.github.io/langgraph/)
- **微软 GraphRAG 官方开源库**：[microsoft/graphrag](https://github.com/microsoft/graphrag)
- **RAG 评估框架 Ragas**：[explodinggradients/ragas](https://github.com/explodinggradients/ragas)
- **FlagEmbedding 向量与重排模型库**：[FlagOpen/FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding)
- **ColBERT 官方仓库（迟交互检索）**：[stanford-futuredata/ColBERT](https://github.com/stanford-futuredata/ColBERT)
- **SPLADE 稀疏学习检索（Naver）**：[naver/splade](https://github.com/naver/splade)
- **ColPali 视觉文档检索**：[illuin-tech/colpali](https://github.com/illuin-tech/colpali)
- **MinerU 高保真文档解析器**：[opendatalab/MinerU](https://github.com/opendatalab/MinerU) · **Docling（IBM）**：[docling-project/docling](https://github.com/docling-project/docling)
- **Anthropic 上下文检索（Contextual Retrieval）**：[anthropic.com/news/contextual-retrieval](https://www.anthropic.com/news/contextual-retrieval) · **Jina 迟切块（Late Chunking）**：[jina.ai/news/late-chunking-in-long-context-embedding-models](https://jina.ai/news/late-chunking-in-long-context-embedding-models/)
- **RAPTOR 官方实现（摘要树检索）**：[parthsarthi03/raptor](https://github.com/parthsarthi03/raptor)
- **LightRAG（轻量图谱）**：[HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) · **HippoRAG（多跳图谱）**：[OSU-NLP-Group/HippoRAG](https://github.com/OSU-NLP-Group/HippoRAG)
- **RAGChecker（检索/生成细粒度归因）**：[amazon-science/RAGChecker](https://github.com/amazon-science/RAGChecker) · **CRUD-RAG（中文基准）**：[IAAR-Shanghai/CRUD_RAG](https://github.com/IAAR-Shanghai/CRUD_RAG)
- **AutoRAG（自动调参）**：[Marker-Inc-Korea/AutoRAG](https://github.com/Marker-Inc-Korea/AutoRAG)
- **嵌入/重排微调**：[UKPLab/sentence-transformers](https://github.com/UKPLab/sentence-transformers)
- **Deep Research 参考实现**：[assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher) · [langchain-ai/open_deep_research](https://github.com/langchain-ai/open_deep_research)
- **Agent 记忆**：[mem0ai/mem0](https://github.com/mem0ai/mem0) · [getzep/graphiti](https://github.com/getzep/graphiti) · [Agent Memory Techniques](https://github.com/NirDiamant/Agent_Memory_Techniques)
- **Search-R1（强化学习驱动检索）**：[PeterGriffinJin/Search-R1](https://github.com/PeterGriffinJin/Search-R1) · **NirDiamant/RAG_Techniques（42 个可跑 Notebook）**：[NirDiamant/RAG_Techniques](https://github.com/NirDiamant/RAG_Techniques)
- **OWASP LLM 应用十大风险**：[genai.owasp.org/llm-top-10](https://genai.owasp.org/llm-top-10/)
- **经典论文**：
  - *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*（Lewis et al., 2020）[arXiv:2005.11401](https://arxiv.org/abs/2005.11401)
  - *Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection*（Asai et al., 2023）[arXiv:2310.11511](https://arxiv.org/abs/2310.11511)
  - *Corrective Retrieval Augmented Generation (CRAG)*（Yan et al., 2024）[arXiv:2401.15884](https://arxiv.org/abs/2401.15884)
  - *From Local to Global: A Graph RAG Approach to Query-Focused Summarization*（Edge et al., 2024）[arXiv:2404.16130](https://arxiv.org/abs/2404.16130)
  - *ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction*（Khattab & Zaharia, 2020）[arXiv:2004.12832](https://arxiv.org/abs/2004.12832)
  - *ColPali: Efficient Document Retrieval with Vision Language Models*（Faysse et al., 2024）[arXiv:2407.01449](https://arxiv.org/abs/2407.01449)
  - *Lost in the Middle: How Language Models Use Long Contexts*（Liu et al., 2023）[arXiv:2307.03172](https://arxiv.org/abs/2307.03172)
  - *RGB: Benchmarking Large Language Models in Retrieval-Augmented Generation*（Chen et al., 2023）[arXiv:2309.01431](https://arxiv.org/abs/2309.01431)
  - *RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval*（Sarthi et al., 2024）[arXiv:2401.18059](https://arxiv.org/abs/2401.18059)
  - *RAFT: Adapting Language Model to Domain Specific RAG*（Zhang et al., 2024）[arXiv:2403.10131](https://arxiv.org/abs/2403.10131)
  - *Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models*（Günther et al., 2024）[arXiv:2409.04701](https://arxiv.org/abs/2409.04701)

准备好把 RAG 这台机器拆开再装回去了吗？从 **[11.1 RAG 完整生命周期分层](./01_RAG完整生命周期分层.md)** 开始。

---

<!-- CH10-14_README_EXPANSION -->

## 阅读与练习建议

学习 RAG 时，建议始终保留一条可观察的数据链：原始文档、切块、召回候选、重排结果、模型上下文、最终回答和引用。这样答案出错时，能找到具体环节，而不是立刻更换模型或叠加新组件。

可以先准备 20 条固定问题，其中包括能直接回答、需要跨段理解、资料中没有答案、文档版本冲突和用户无权限查看的情况。每次改动一个主要配置后重新运行，并记录检索指标、回答依据、耗时和调用成本。

第 11.15 节的 Lite 项目用于说明各模块怎样连接。多租户、可靠任务、正式监控和灾难恢复等能力，需要根据实际使用规模继续完善。
