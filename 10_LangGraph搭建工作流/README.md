# 第十章：LangGraph 搭建工作流 —— 把 Agent 画成一张能暂停、能回放的图

> 第九章把 LangChain 1.4 的零件装齐了：模型、提示词、工具、中间件、`create_agent`。  
> 本章换一个问题：当流程里出现**分支、循环、并行、人工审批、崩溃续跑**时，单靠“模型自己看着办”已经不够。我们需要一张能画出来、能打断、能存档的运行时。

***

## 📖 本章导读

把一个 Agent 交给真实业务，最先崩的往往不是模型本身，而是**过程失控**：

- 它在工具之间来回打转，Token 烧完了你才知道；
- 订票、退款、改库存这种动作，它说干就干，没有人签字；
- 跑到一半进程挂了，前面几步全部作废，只能从头来；
- 昨天用户说过“我对花生过敏”，今天换一条会话，它完全不记得。

[LangGraph](https://docs.langchain.com/oss/python/langgraph/overview) 不是又一个“把 Prompt 包一层”的框架。官方给它的定位很干脆：**低层编排框架 + 有状态运行时**。你把流程画成图：节点负责干活，边负责决定下一步去哪，整张图共享一份可存档的状态。大模型只在真正需要理解自然语言的路口上场，其余轨道由代码钉死。

可以把它想成一张**带存档点的游戏地图**：格子是节点，连线是边，玩家背包是 State，土地庙是 Checkpointer。模型负责在岔路口选路，你负责规定哪些路能走、哪些门必须等人开门。

和第九章的关系也很清楚：

| 你已经会的（第九章） | 本章要补上的 |
| :--- | :--- |
| `create_agent` 自动搭好“想一步、做一步”的小循环 | 把循环嵌进更大的图：分流、并行、子图、审批 |
| Checkpointer / Store 作为 Agent 的记忆接口 | 同一套机制如何驱动 HITL、Time Travel、断点续跑 |
| 中间件在模型调用前后插一脚 | 节点、边、`Command`、`interrupt()` 把控制权写进拓扑 |

全章基于 **LangGraph 1.x**（工作台实测基线 `langgraph>=1.2`）。老教程里的 `langgraph.prebuilt.create_react_agent` 已经弃用，高层 Agent 统一走 LangChain 的 `create_agent`。LangGraph 自己提供两套并列 API：

1. **Graph API**（`StateGraph`）：画轨道图，适合新建的复杂编排与多智能体，是 01～13 节的主线；
2. **Functional API**（`@entrypoint` / `@task`）：给现成 Python 函数加持久化与 HITL，14 节专门对照。

> 💡 官方选型说明：[Choosing between Graph and Functional APIs](https://docs.langchain.com/oss/python/langgraph/choosing-apis)。

***

## 🗺️ 16 节路线图

建议按四段读，不要一上来就啃旅行助手源码：

1. **01～05 把图画活**：状态、节点、边、条件路由、并行 `Send`、可视化与流式调试；
2. **06～08 加上记忆、刹车和心脏**：Checkpointer、静态断点、Handoffs 入门、工具调用循环；
3. **09～14 补齐工业零件**：设计模式、长期记忆、容错、子图与五种多智能体模式、动态 `interrupt()`、两套 API；
4. **15～16 看上线和整机**：部署选项、观测取舍，以及国内旅行助手如何把零件装到一起。

每学完一节，用一个最小例子回答四个问题：**状态里存了什么、这次走了哪条路、失败后从哪里继续、外部写操作会不会重复执行。**

***

## 📑 章节目录

| 章节 | 文档 | 这一节到底在解决什么 |
| :--- | :--- | :--- |
| **10.1** | [初识 LangGraph 与状态机](01_初识LangGraph与状态机.md) | 为什么单体 Agent 会脱缰，图、节点、边各自管什么 |
| **10.2** | [State 图的构建与运行](02_State图的构建与运行.md) | 交接本怎么定义，reducer / Runtime / 输入输出 Schema 怎么用 |
| **10.3** | [条件路由与动态决策](03_条件路由与动态决策.md) | 十字路口：路由函数、路径表、决策与路由分离、`Command` |
| **10.4** | [并行执行与 Send 动态分发](04_并行执行与Send动态分发.md) | Fan-out / Fan-in、reducer 合并、数量不定的 Map-Reduce |
| **10.5** | [图的可视化与流式调试](05_图的可视化与流式调试.md) | Mermaid、`stream_mode`、v2 统一事件、子图透视 |
| **10.6** | [Memory 与 Human-in-the-loop](06_Memory与Human-in-the-loop.md) | `thread_id` 存档，静态断点如何停住、如何正式驳回 |
| **10.7** | [Multi-Agent 分层架构](07_MultiAgent分层架构.md) | 主助理转交、状态栈、Handoffs 入门 |
| **10.8** | [工具调用循环与预构建组件](08_工具调用循环与预构建组件.md) | `bind_tools` / `ToolNode` / `tools_condition`，以及 `create_agent` |
| **10.9** | [工作流设计模式](09_工作流设计模式.md) | 官方五大模式 + Agent：先选型再画图 |
| **10.10** | [长期记忆与 Time Travel](10_长期记忆与TimeTravel.md) | Store 跨会话档案，回放不是放录像 |
| **10.11** | [持久执行与容错](11_持久执行与容错.md) | 断点续跑、RetryPolicy、超时、缓存、幂等 |
| **10.12** | [子图与多智能体全谱](12_子图与多智能体全谱.md) | 真子图；Subagents / Handoffs / Skills / Router / Custom workflow |
| **10.13** | [HITL 进阶](13_HITL进阶.md) | `interrupt()` + `Command(resume)`，条件拦截与多级审批 |
| **10.14** | [Functional API 与两套 API 选型](14_FunctionalAPI与两套API选型.md) | `@entrypoint` / `@task`，给旧代码加超能力 |
| **10.15** | [部署与可观测性](15_部署与可观测性.md) | 本地 Server / Studio / Platform，观测先练基本功 |
| **10.16** | [综合实战：旅行管家](16_综合实战_旅行助手项目.md) | 把全章零件装进国内旅行助手：登录认证、审批闸门、会话/订单/审计三本账 |

***

## 🚀 环境与示例

Python 3.10+。教学示例默认**零 API Key**，需要“模型出场”的地方用 `langchain-core` 的假模型按剧本说话，图的机制和真模型一致。只有 08 节带 `--real` 开关，可以换成 `.env` 里的真模型，看模型自己决定调不调工具。

```bash
# 分节示例（02～14）：本目录自带 pyproject.toml，零 API Key
cd 10_LangGraph搭建工作流/code/examples
uv sync
uv run python 02_state_graph_demo.py

# 08 专属：换真模型（读 .env 的 OPENAI_*，先按 .env.example 填好）
uv sync --extra real
uv run python 08_tool_loop_demo.py --real

# 图工作台：把同一份示例点亮（默认 http://127.0.0.1:7860）
cd ../workbench
uv venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python app.py
.venv/bin/python smoke_test.py   # 14 关零 Key 冒烟

# 16 节旅行管家（需 .env 真实模型；默认 http://127.0.0.1:7860）
# 依赖走 uv 原生清单（pyproject.toml + uv.lock），一条 uv sync 建环境装依赖
cd ../travel_agent_v2
uv sync
uv run uvicorn web.app:app --host 127.0.0.1 --port 7860
```

| 目录 | 做什么 |
| :--- | :--- |
| [code/examples/](code/examples/) | 02～14 每节一个最小可运行例子，工作台直接 import 同一份 `build_graph()` |
| [code/workbench/](code/workbench/README.md) | 14 关可视化：SVG 图结构、节点点亮、Replay、审批弹窗 |
| [code/travel_agent_v2/](code/travel_agent_v2/README.md) | 16 节收官整机：国内旅行助手，真实模型 + 假模型三层测试 + 一条分层守卫 |

两个版本注意点：

1. **不要再写 `create_react_agent`**。高层 Agent 用 [LangChain `create_agent`](https://docs.langchain.com/oss/python/langchain/agents)；
2. **生产存档不要用内存 Checkpointer**。`MemorySaver` / `InMemorySaver` 随进程消失，抗重启请换 `SqliteSaver` 或 `PostgresSaver`。

***

## 学习与验证建议

示例跑通不等于流程可靠。涉及写操作时，优先用教学数据，并专门验证：**驳回、超时、重复恢复、未知分类、部分并行失败**。章节代码展示机制，不代表身份、权限、事务和审计已经完成。16 节项目也应以它自己的 README 和测试结果为准。
