# RAG 质量控制台与工作台（第十一章配套可视化演示）

> 默认首页是无需密钥的质量控制台：直接读取 `../testdata/` 的回归文档，检查检索指标、新旧版本、引用完整性和提示注入。其后是十二个分节实验与选型页；能真实走模型的按钮会读取 `../.env`，并在左侧展示实际检索命中和喂给模型的上下文。
> 页面采用左侧章节导航和高密度工程控制台布局。桌面端左右对照结果与过程，两张结果卡固定等高，超长内容在卡片内部滚动；窄屏自动改为单列。每个模型实验都保留「痛点横幅 + 过程透视终端」。
> 11.2–11.14 每页都会在运行前列出真实输入、关键参数和中间工序；11.2 的脏原文可直接编辑，结果按解析、清洗、切块三个阶段展开。

## 运行

```bash
cd code
# 1) 环境（首次）：Python 3.13 + 依赖（gradio 已含在 rag_workbench 开发依赖里，见下）
uv venv --python 3.13 && uv pip install --python .venv/bin/python -r requirements.txt
# gradio 与 matplotlib 已写入 requirements.txt，无需另装

# 2) 模型配置：code/.env 至少提供 OpenAI 兼容端点（可从 09 章 .env 复制）：
#    OPENAI_API_KEY / OPENAI_BASE_URL（或 ARK_API_KEY + ARK_BASE_URL 自动推导）
#    CHAT_MODEL（对话模型，如 deepseek-v4-flash）/ EMBEDDING_MODEL（嵌入模型，如 doubao-embedding-vision-250615）

# 3) 起台
.venv/bin/python rag_workbench/app.py    # 浏览器打开 http://127.0.0.1:7861
# 端口被占用时：GRADIO_SERVER_PORT=7862 .venv/bin/python rag_workbench/app.py
```

## 质量首页 + 12 关 + 选型页

| 关卡 | 对应脚本 | 痛点 | 看点 |
| :--- | :--- | :--- | :--- |
| ⌂ 质量控制台 | rag_quality + testdata | 改完系统不敢发布 | 四份语料盘点、离线质量门禁、版本冲突与引用攻击演练 |
| 📄 11.2 数据管道 | s02 | 数据源又脏又乱 | 解析→清洗→切块产物预览、父子切块 |
| 🧭 11.3 向量嵌入 | s03 | 机器不懂语义 | 三种度量手写、Top-K、MRL 截断降维 |
| 🗄 11.4 ANN 索引 | s04 | 海量查不快 | 暴力 vs 近似 Recall@10、Qdrant 过滤检索（内存模式） |
| 🔀 11.5 混合检索 | s05 | 搜不准搜不全 | 手写 RRF、BM25+Dense 双路、Cross-Encoder 重排 |
| 🪄 11.6 查询重写 | s06 | 提问含糊 | HyDE 假想文档、Multi-Query 三路并发、结构化意图路由 |
| 🕸 11.7 GraphRAG | s07 | 宏观问题答不了 | LLM 抽实体建图、社区研报、全局问答 |
| 🔄 11.8 Agentic RAG | s08 | 幻觉与答非所问 | LangGraph 五节点闭环：分级→兜底→生成→复检（配章节图） |
| 📏 11.9 评估 | s09 | 无法度量好坏 | 检索五指标、引用/延迟门禁、Ragas、链路追踪 |
| 🎯 11.11 迟交互稀疏 | s11 | 词级细节被抹平 | 标准 MaxSim 求和、ColBERT/SPLADE（首跑下载模型）、分诊台 |
| 🔗 11.12 引用溯源 | s12 | 答案没出处 | 编号引用协议、幽灵引用攻击演示、流式生成 |
| 🏭 11.13 部署安全 | s13 | 上不了生产 | 隔离缓存、多租户 ACL、投毒扫描、蓝绿索引、指令/数据隔离 |
| 🖼 11.14 多模态 | s14 | 知识不止文字 | 图片素材自动生成、跨语言相似度、表格问答 |
| 🧭 11.10 选型页 | （纯展示） | 框架怎么挑 | 复用章节 overview 两张 House 图 |

## 文件结构

```
rag_workbench/
├── app.py            # Gradio 6 单文件主程序（工程控制台布局，含离线质量首页）
└── smoke_test.py     # 冒烟：直调各关 Gradio 回调，确认非空 JSON 与过程日志
```

## 设计约定（与 10 章图工作台的差异）

- **本地门禁先行**：首页的检索、版本、引用与注入检查完全离线，换索引或改切块后可立即回归；
- **Gradio 真实调用优先**：有 `.env` 时，11.3/11.5/11.6/11.8/11.12 等按钮会真实调用 Embedding/Chat；左侧说明输入、候选资料、中间判断、发送给模型的上下文和输出含义；
- **模型可切换**：所有脚本已改造为 `CHAT_MODEL` / `EMBEDDING_MODEL` 环境变量优先（默认回落 gpt-4o-mini / text-embedding-3-small），换供应商只改 `.env`；
- **测试不依赖外部服务**：`smoke_test.py` 使用 `RAG_WORKBENCH_TEST_MODE=1` 验证 UI 不空白；正常 Gradio 启动不设置该变量，会按 `.env` 尝试真实调用；
- **痛点横幅**：每关顶部一句「本章痛点」——本章教材是问题驱动的，工作台保持同一叙事；
- 版式/视觉/交互规范见 [`10_LangGraph搭建工作流/code/skills/gradio-frontend-skill.md`](../../../10_LangGraph搭建工作流/code/skills/gradio-frontend-skill.md)（10 章沉淀，两章共用）。

## 参考

- [LangChain 官方文档](https://python.langchain.com/docs/)
- [Ragas 评估框架](https://docs.ragas.io/)
- [Qdrant 文档](https://qdrant.tech/documentation/)
- 第十章图工作台（版式先例）：`../../10_LangGraph搭建工作流/code/workbench/`


## 真实 RAG 演示文档

`../testdata/真实RAG演示文档/` 内置 4 份 Markdown 文档，每份 3–4 页：Vibe Coding 协作手册、差旅报销制度、RX-9000 故障手册、HR 年假与体检制度。Gradio 的真实检索按钮会按页读取这些文档，调用 Embedding 生成向量并把 Top-K 编号上下文交给 Chat 模型生成答案。
