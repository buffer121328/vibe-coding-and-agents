# 🛠️ 第九章：LangChain 搭建 Agent 配套代码库 (Code Base)

本目录包含了第九章从 9.1 到 9.13 的全部 LangChain 1.x 实现与一个 **侧边栏导航、全链路实时流式的现代化 Gradio 可视化交互工作台**。

***

## ⚡ 极速启动 (Quick Start)

我们推荐使用现代 Python 包管理工具 `uv`（也可使用原生 `pip`）：

```bash
# 1. 进入代码目录
cd 09_LangChain搭建Agent/code

# 2. 复制并配置环境变量
cp .env.example .env
# 编辑 .env 填入你的大模型 API Key（支持火山方舟、DeepSeek、OpenAI、硅基流动等任意 OpenAI 兼容端点）

# 3. 首次：创建虚拟环境 .venv 并安装全部依赖（后续无需重复）
uv sync

# 4. 运行单个功能演示脚本（例如 9.1 模型 I/O 或 9.13 综合实战参谋）
uv run python s01_model_io.py
uv run python s13_smart_buyer.py

# 5. 一键启动 13 关卡教学工作台（每页含「过程透视」终端 + Codex 式会话）
uv run python app.py
```

启动后在浏览器打开 `http://127.0.0.1:7860` 即可在可视化界面中体验 13 个功能模块与终极实战项目！

***

## 📂 代码文件结构索引

| 脚本文件 | 对应章节 | 核心功能说明 |
| :--- | :--- | :--- |
| **`s01_model_io.py`** | 9.1 初识生态与统一 I/O | 统一模型工厂接入、invoke / stream / batch 调用姿势、Token 元数据提取与 **模型能力档案 `.profile`** |
| **`s02_prompt_and_messages.py`** | 9.2 Prompt 模板与上下文流 | 四大消息类型 (System/Human/AI/Tool)、ChatPromptTemplate 与 MessagesPlaceholder 动态注入 |
| **`s03_lcel_chains.py`** | 9.3 LCEL 链式编排与调度 | Unix 管道符 `\|`、RunnableParallel 多分支并行与 with_fallbacks 高可用容灾 |
| **`s04_structured_output.py`** | 9.4 结构化输出与容错解析 | Pydantic 强类型约束、with_structured_output 提取与 JsonOutputParser 容错解析 |
| **`s05_custom_tools.py`** | 9.5 自定义工具生态与校验 | `@tool` 装饰器、Pydantic args_schema 参数校验、Docstring 意图契约、底层 bind_tools 与 **工具 `extras`** |
| **`s06_memory_and_trimming.py`** | 9.6 记忆管理与状态持久化 | create_agent + LangGraph Checkpointer 线程级记忆、RunnableWithMessageHistory 经典方案、trim_messages 滑动窗口裁剪与预算控制 |
| **`s07_callbacks_and_tracing.py`** | 9.7 Callbacks 与可观测性中间件 | BaseCallbackHandler 探针、Token 账单自动审计、耗时统计、敏感隐私数据拦截脱敏与 **官方预置中间件 (ModelRetry / PII)** |
| **`s08_rag_retrieval.py`** | 9.8 RAG 核心链路与向量检索 | 文本切块 (TextSplitter)、langchain-chroma 向量入库、LCEL 标准 RAG 检索问答管道 |
| **`s09_modern_agent.py`** | 9.9 Modern Agent 智能体闭环 | 1.x 标准 `create_agent`（SystemMessage 系统提示 + **ModelRetry 中间件**）、多模工具调用、messages 流水线审计、**response_format 结构化答复**与 **v3 流式协议** |
| **`s10_context_engineering.py`** | 9.10 上下文工程 | 动态 System Prompt（`@dynamic_prompt`）、动态工具选择（`wrap_model_call` + `request.override`）、Store + Runtime Context 画像注入 |
| **`s11_custom_middleware.py`** | 9.11 自定义中间件 | Node-style 钩子（`before_model`/`after_model`）+ Wrap-style 钩子（`wrap_model_call`）、类式中间件、`state_schema` 调用次数限流 |
| **`s12_guardrails_and_testing.py`** | 9.12 生产级防护 | 内置 `PIIMiddleware` 脱敏、`before_agent` 黑名单拦截、`after_agent` 安全复核、确定性护栏轻量自测（可进 CI） |
| **`s13_smart_buyer.py`** | 9.13 综合实战 SmartBuyer | 🌟 **终极实战（融会贯通版）**：9.1~9.12 全零件整机总装——护栏纵深防御 + 中间件治理栈 + 顾客画像动态注入 + 数码避坑 RAG + 差评搜索 + 参数测算 + Pydantic 选购报告 |
| **`app.py`** | 综合可视化界面 | 13 关卡侧边栏教学工作台：每页「过程透视」终端透明展示中间产物，Codex 式气泡会话，全链路实时流式 |
