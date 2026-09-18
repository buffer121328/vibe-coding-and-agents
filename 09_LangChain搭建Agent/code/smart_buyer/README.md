# 🛍️ SmartBuyer —— AI 智能数码选购与避坑决策参谋

第九章 9.13 综合实战的**独立项目版**：基于 **LangChain 1.4** 的生产架构导向 Agent，把课程 9.1~9.12 的全部零件一次总装——护栏挡在门外、中间件守住流水线、上下文工程千人千面、RAG 让参谋有据可依、Pydantic 报表让决策可交付。

> 📖 **课堂版教学解析**（每个零件为什么这么装、对应哪一节课）：[`../../13_综合实战_AI智能数码选购与避坑决策Agent.md`](../../13_综合实战_AI智能数码选购与避坑决策Agent.md)

## 快速启动

```bash
cd 09_LangChain搭建Agent/code        # 复用第九章的 uv 环境（LangChain 1.4 + deepagents 已就位）

# 1. 配置环境变量（任一 OpenAI 兼容端点 + Embedding 端点）
cp ../.env.example .env              # 或直接复用 code/.env
# 编辑 .env 填入 MIMO_API_KEY 或 OPENAI_API_KEY，以及 EMBEDDING_MODEL

# 2. 终端体验：课程版整机点火试车（8 把工具：3 本地 + 5 MCP 行情，多轮问诊 + 一键报表）
uv run python -m smart_buyer.main
#    关闭 MCP（纯本地 3 工具，课程最小配置）：SMARTBUYER_USE_MCP=false uv run python -m smart_buyer.main

# 3. 深度版（Phase 2）：四子代理协作（差评/测算/避坑/物流售后），报告写虚拟文件系统
uv run python -m smart_buyer.deep_agent

# 3. Web 工作台：问诊对话 + 工具调用链 + 结构化报告（默认 http://127.0.0.1:7861）
uv run python -m smart_buyer.web_app
# 可选：改端口 / 关闭 MCP
SMARTBUYER_PORT=8080 SMARTBUYER_USE_MCP=false uv run python -m smart_buyer.web_app

# 4. MCP 自检：内置服务器 5 把行情工具逐把真实调用（零 API、零外部依赖）
uv run python -m smart_buyer.mcp_server

# 5. 质量测试（Phase 1，19 项，零 API 依赖可进 CI）
uv run pytest smart_buyer/tests/ -v

# 6. 可选：接通 LangSmith 全链路观测
#    .env 里加 LANGSMITH_TRACING=true 与 LANGSMITH_API_KEY=...
# 可选：接入外部 MCP 服务器（与内置服务器合并装配）
#    .env 里加 SMARTBUYER_MCP_URLS=https://mcp.example.com/mcp
```

## 目录结构

```
smart_buyer/
├── main.py              # 课程交付版核心（自包含，可独立运行）：
│                        #   模型工厂 / Callback 账单 / 重试·日志·限流中间件 / 黑名单护栏
│                        #   Pydantic 报表 Schema / 内置避坑 RAG / 三大本地 @tool
│                        #   @dynamic_prompt 三数据源注入 / SmartBuyerAgent 总装 / CLI 入口
│                        #   Phase 1：db_path= → SqliteSaver 会话记忆落盘
│                        #   Phase 3：use_mcp= 自动装配 MCP 行情工具（默认开，SMARTBUYER_USE_MCP=false 关）
├── web_app.py           # 独立 Gradio 工作台：问诊 / 过程透视 / 结构化报告
├── mcp_server.py        # Phase 3 数据源：内置 MCP 演示服务器（in-process FastMCP，零外部依赖）
│                        #   5 把电商行情工具：历史价格 / 官方参数 / 以旧换新估价 / 物流时效 / 售后政策
│                        #   内置离线行情数据集，查询走真实代码路径，CI 与离线环境可跑
├── mcp_tools.py         # Phase 3 接入层：1.4 langchain.mcp（beta）MCPAdapter
│                        #   两路数据源合并（内置服务器 + SMARTBUYER_MCP_URLS 外部服务器）
│                        #   async 工具同步包装（ToolNode 同步路径兼容）；list_tools 三档缓存
│                        #   ProviderToolSearch 延迟挂载 + LLMToolSelector 分诊（工具>12 把自动启用）
├── deep_agent.py        # Phase 2+4：deepagents 深度版
│                        #   create_deep_agent + 四专项子代理（差评侦察/参数测算/避坑审核/物流售后）
│                        #   子代理共享 MCP 工具层（按需各领所需）；报告写虚拟文件系统 /reports/*.md
│                        #   /memories/<user_id>/ 经 StoreBackend 跨会话沉淀；FilesystemPermission
│                        #   最小权限网；TracePolicy 链路打码 + LangSmith 观测开关
├── tests/               # Phase 1：质量加固（uv run pytest smart_buyer/tests/ -v）
│                        #   护栏黑名单断言（含大小写绕过/代码注入）+ 固定用例回归
│                        #   + SqliteSaver 跨实例持久化验证（Fake 模型零 API）
├── README.md            # 本文件：架构图解 + 演进路线
└── .env -> ../.env      # 复用 code/.env（软链）
```

## 业务闭环：一个咨询请求的完整旅程

```
用户："预算 4000 考虑 MagicBook14，有一台 iPhone15 想以旧换新，现在值得入手吗？"
  │
  ├─ 🔒 黑名单护栏（9.12）检查通过
  ├─ 🔌 MCP【query_price_history】→ MagicBook14 当前 ¥4,499，比双 11 低点贵 ¥400
  ├─ 🔌 MCP【estimate_trade_in】→ iPhone15（99新）抵扣 ≈ ¥3,040
  ├─ 🔌 MCP【query_official_specs】→ 官方参数核对：内存板载焊死、无 HDMI
  ├─ 🔧 本地【避坑宝典 RAG】→ 屏幕色域 / 内存陷阱要点（9.8）
  ├─ 🔧 本地【全网差评搜索】→ 真实用户吐槽（ddgs 联网，9.5）
  ├─ 🔧 本地【性价比测算器】→ 4499 - 3040 = 实际入手 ¥1,459（9.5）
  ▼
最终答复：是否好价 + 抵扣后真实成本 + 避坑警告 + 一锤定音
```

> 🔁 **闭环要点**：8 把工具（3 本地 + 5 MCP）对模型完全同层——模型按需自主调度，
> MCP 工具经 mcp_tools.py 的同步包装后与本地 `@tool` 无差别；深度版（deep_agent.py）
> 的四个子代理再按职责各领所需，形成"主参谋派单 → 子代理取证 → 汇总决策"的两级闭环。

## 架构一图流

```
用户咨询
   │
   ▼
┌─ 第 1 层【9.12】护栏 ────────────── ContentFilterMiddleware 黑名单（零 Token 拦截）
│        ▼
├─ 第 2 层【9.11】治理 ────────────── LoggingMiddleware → CallCounterMiddleware(超10次熔断) → retry_model(重试3次)
│        ▼
├─ 第 3 层【9.10】上下文工程 ──────── @dynamic_prompt：基础人设 + Store 画像 + 会话长度自适应
│        ▼
├─ 智能体中枢【9.9】create_agent ──── Tool Calling 自主推理
│        ├─ 🔧 差评搜索【9.5】（ddgs 联网，失败优雅降级）
│        ├─ 🔧 性价比测算【9.5】（严禁心算）
│        └─ 🔧 避坑宝典【9.8】（Chroma 向量检索，零配置内置）
│        ▼
└─ 双模输出
   ├─ 多轮问诊：Checkpointer 会话记忆【9.6】+ Callback Token 账单【9.7】
   └─ 一键报表：prompt | structured_llm【9.3+9.4】Pydantic《选购决策与避坑报告》
```

**千人千面**：Store 预置 `user-veteran`（极简直接）与 `user-rookie`（手把手科普）两套画像——同一个问题，参谋对老手甩参数表、对新手讲避坑故事。

## 演进路线（"长大"计划）

| Phase | 目标 | 涉及课程零件 | 状态 |
| :--- | :--- | :--- | :--- |
| **Phase 0 · 课程交付版** | 9.1~9.12 全零件总装，终端 CLI | 全部 | ✅ 完成 |
| **Phase 1 · 质量加固** | `tests/` 19 项测试全绿：护栏黑名单断言（含大小写绕过 / 代码注入拦截）、固定用例回归、**SqliteSaver 会话记忆落盘**（`SmartBuyerAgent(db_path="buyer.db")`，跨进程重启记忆仍在，测试用 Fake 模型零 API 验证） | 9.12 测试纪律 / 9.6 Checkpointer | ✅ 完成 |
| **Phase 2 · deepagents 深度版** | [`deep_agent.py`](deep_agent.py)：`create_deep_agent` 装配，三个专项子代理（review-scout 差评侦察 / spec-analyst 参数测算 / trap-auditor 避坑审核）经 `task()` 派单在隔离上下文干活，报告写入虚拟文件系统 `/reports/*.md`；真实 API 试跑通过（四份报告完整产出） | 9.9 deepagents 五件套 | ✅ 完成 |
| **Phase 3 · MCP 工具生态** | [`mcp_tools.py`](mcp_tools.py)：1.4 `langchain.mcp`（beta）`MCPAdapter` 一键接入 MCP 服务器，`list_tools` 三档缓存（use/refresh/bypass）；`ProviderToolSearchMiddleware` 延迟挂载低频工具 + `LLMToolSelectorMiddleware` 分诊（工具 >12 把自动启用）；in-process FastMCP 端到端验证通过；未配置 URL 时优雅降级 | 9.1 MCP / 9.7 中间件 | ✅ 完成 |
| **Phase 4 · 多用户生产化** | `/memories/<user_id>/` 经 `StoreBackend(namespace=("smart-buyer", user_id))` 按用户隔离沉淀顾客档案；`FilesystemPermission` 最小权限网（只许写 /reports/ 与 /memories/，其余拒绝）；`TracePolicy` 链路打码 + `LANGSMITH_TRACING=true` 零代码接通全链路观测 | 9.6 Store / 9.11 TracePolicy / deepagents backends | ✅ 完成（LangSmith 需自配 Key） |

## 设计约定

- **零件可溯源**：每个类 / 函数 / 工具都标注了【9.x】章节编号，学习时可在课程文档与代码间双向跳转；
- **失败优雅降级**：联网搜索挂了给模拟数据、Embedding 端点 401 时退化为内置文本宝典——整机不因单点故障熄火；
- **护栏最外层原则**：中间件列表由外到内执行，安检门永远在导演（动态提示词）之前。

## Web 工作台说明

`web_app.py` 是独立项目的前端入口，和章节总工作台 `code/app.py` 分开运行，默认监听
`7861`，不会占用教学工作台的 `7860`。

前端基于 [Gradio Blocks 官方文档](https://www.gradio.app/docs/gradio/blocks)，流式输出走
[LangChain Streaming](https://docs.langchain.com/oss/python/langchain/streaming)，Agent 能力继续
使用 [LangChain Agents 官方文档](https://docs.langchain.com/oss/python/langchain/agents)。

| 区域 | 用途 |
| :--- | :--- |
| **中间对话** | 主界面。发送后立刻显示用户消息，回复按 token 往外冒；快捷问题只负责填输入框 |
| **左栏 · 最近会话** | 「轻薄本对比」是带档案的示例会话：点进去能看到昨天的对话、研究过程和决策报告。你自己聊过的会话也会按会话号记住这三样 |
| **右栏 · 研究过程** | 看参谋调了哪些工具，不是拿来填表的后台表单；切换会话时会跟着恢复 |
| **右栏 · 决策报告** | 每个会话各留一份建议卡片。默认沿用刚才的对话需求 |
| **左栏 · 设置 / 帮助** | 点开后切到右栏对应页面：用户画像、MCP 开关，以及怎么问更有效 |

前端只负责展示和输入，不复制 Agent 规则：护栏、动态画像、RAG、MCP、成本回调仍统一由
`main.py` 提供。页面打开时不会创建模型，首次发送咨询或生成报告时才初始化 Agent；即使还没
填 API Key，也可以先检查布局。调用失败时会在对话和过程透视中给出 `.env` 配置提示。

### 环境变量与验收

最少需要一组 OpenAI 兼容端点配置（例如 `MIMO_API_KEY` + `MIMO_BASE_URL` + `MIMO_MODEL`，
或 `OPENAI_API_KEY` + `OPENAI_API_BASE` + `MODEL_NAME`）。RAG 还可配置 `EMBEDDING_MODEL`。
`SMARTBUYER_USE_MCP=false` 会关闭内置行情工具，适合只演示三把本地工具。

- `uv run python -m smart_buyer.web_app` 能启动并打开 Web 页面；
- 发送咨询后能看到回答、Token / 成本状态和工具调用卡片；
- 点击“生成结构化决策报告”能同时得到卡片视图和 JSON；
- `uv run pytest smart_buyer/tests/ -v` 通过零 API 测试；
- 没有配置模型 Key 时，页面仍能启动，并在实际调用处明确提示配置问题。
