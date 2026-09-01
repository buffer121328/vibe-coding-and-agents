# 第 10 章：LangGraph 搭建工作流与 Multi-Agent 架构

在掌握了 LangChain 的基础与 Agent 概念后，我们将踏入当前大模型应用落地的深水区——**复杂工作流的编排**。

过去的一年里，开发者们普遍发现：单纯依赖大模型自行判断工具的“单体 Agent”在实际企业应用中不可控。它经常陷入死循环，或者在执行危险操作前不受控制。

为了解决这个问题，[LangGraph](https://docs.langchain.com/oss/python/langgraph/overview) 应运而生。它引入了图论（图、节点、边）和状态机概念，让开发者可以画出严谨的“轨道”，而让大模型仅仅负责在十字路口做路由决策。

> **本章核心目标**：从零理解状态图（StateGraph），掌握条件路由、并行分发、图的可视化与流式调试等基础基建，进阶到人工干预（Human-in-the-loop）机制，通过一个**生产架构导向的多智能体旅行助手教学项目**理解 AI 应用如何拆层、审批和测试；再以进阶专题补齐工具调用循环、设计模式、长期记忆、持久执行、子图、Functional API 与部署观测的知识地图。

## 📚 目录结构

* [01_初识LangGraph与状态机](01_初识LangGraph与状态机.md) - 解决传统Agent不可控痛点，学习“节点”、“边”与“条件路由”。
* [02_State图的构建与运行](02_State图的构建与运行.md) - 学习如何定义全局状态交接本，并编写代码让图跑起来。
* [03_条件路由与动态决策](03_条件路由与动态决策.md) - 学会让大模型在“十字路口”当路由裁判，构建意图分流与决策树。
* [04_并行执行与Send动态分发](04_并行执行与Send动态分发.md) - 多个节点同时开工（Fan-out/Fan-in），用 Send 做数量不定的动态批量并行。
* [05_图的可视化与流式调试](05_图的可视化与流式调试.md) - 把图画出来（Mermaid/PNG），用 stream 逐节点观察状态流转。
* [06_Memory与Human-in-the-loop](06_Memory与Human-in-the-loop.md) - 存档机制，以及如何在执行危险动作前暂停让“人类签字同意”。
* [07_MultiAgent分层架构](07_MultiAgent分层架构.md) - 用“大堂经理”与“专职助理”理解 Handoffs、状态栈交接和上下文传递。

**进阶专题**（对照 LangGraph 1.x 官方文档主线补全）：

* [08_工具调用循环与预构建组件](08_工具调用循环与预构建组件.md) - 补上 Agent 的心脏：bind_tools/ToolNode/tools_condition 循环闭环，及 create_agent + middleware 高层快车道。
* [09_工作流设计模式](09_工作流设计模式.md) - 官方五大模式速查（路由/编排者-工人/评估者-优化者等），建立“先选型再动手”的条件反射。
* [10_长期记忆与TimeTravel](10_长期记忆与TimeTravel.md) - Store 跨线程会员档案、语义检索，以及 get_state_history/update_state 回放与改道。
* [11_持久执行与容错](11_持久执行与容错.md) - 断点续跑、RetryPolicy 自动重试、超时与缓存，跑到一半崩了能复活。
* [12_子图与多智能体全谱](12_子图与多智能体全谱.md) - 真子图嵌套；按当前官方分类理解 Subagents、Handoffs、Skills、Router、Custom workflow，并用三张图跑通重点实现。
* [13_HITL进阶](13_HITL进阶.md) - 节点内动态中断 interrupt() + Command(resume)，条件拦截与多级审批。
* [14_FunctionalAPI与两套API选型](14_FunctionalAPI与两套API选型.md) - @entrypoint/@task 给现有 Python 函数加持久化，Graph API vs Functional API 选型对照。
* [15_部署与可观测性](15_部署与可观测性.md) - LangGraph Server/Studio/Platform 部署，可观测性取舍（暂不引入 LangSmith/Langfuse，用调试三板斧替代）与追踪生态认知。

**收官实战**：

* [16_综合实战_旅行助手项目](16_综合实战_旅行助手项目.md) - 用生产架构导向的旅行助手教学项目把全章零件装进一台整机，并明确它与真正生产系统之间的边界。

## 🛠️ 环境准备与两套 API 总览

开始学习前建议先装好环境（Python 3.10+）：

```bash
pip install -U langgraph langchain langchain-openai
```

两个版本注意点：

1. **LangGraph 1.x 已弃用 `create_react_agent`**，高层 Agent API 统一迁移到 LangChain 的 `create_agent` + middleware（见 08 节）；老教程里 `langgraph.prebuilt.create_react_agent` 的写法会遇到弃用警告。
2. **LangGraph 有两套并列 API**：Graph API（StateGraph 画轨道图，本第 01~07、08~12 节主线）与 Functional API（@entrypoint/@task 给现有 Python 代码加持久化，见 14 节）。前者适合新建的复杂编排与多智能体，后者适合给已有流程最小改动加记忆/HITL，详细选型见 [官方对比](https://docs.langchain.com/oss/python/langgraph/choosing-apis)。

> 💡 **参考资料**：本章基础小节主要依据 **LangGraph 1.x 官方文档**（图 API 概念、使用图 API、流式输出等），并参考了 PocketFlow、Matt Harrison 等社区教程进行扩展，各小节末尾均附有完整扩展阅读链接。

## 💻 本章示例与实战源码

- **[code/examples/](code/examples/)**：02~14 每节一个最小可运行示例，**全部无需 API Key**（用 langchain-core 内置假模型模拟大模型环节），装好 `langgraph` 后逐个 `python xxx.py` 即可跑通。
- **[code/workbench/](code/workbench/README.md)**：🌟 **图工作台**（本章配套可视化演示）——把 14 个关卡（含 10.12b 多智能体重点实现）的真实 LangGraph 图搬上交互台：House 风格 SVG 图结构 + 节点逐步点亮 + Replay 重执行对照 + 正式批准/驳回 + Functional API 真并行，同样零 API Key。
- **[code/travel_agent_v2/](code/travel_agent_v2/README.md)**：16 节收官实战的生产架构导向 Multi-Agent 教学项目；使用 LangGraph 1.x 动态 `interrupt()` 审批、子图、Store、Send 与测试，但仍采用 SQLite 和进程内存储，生产边界见项目 README。

准备好进入 Agent 工业流水线的时代了吗？让我们开始吧！
