# 01 初识 LangGraph 与状态机

## 1. 为什么需要 LangGraph？（传统 Agent 的痛点）

在用 LangChain（或其他框架）做 Agent 的时候，你可能遇到过这样的场景：Agent 在执行任务时像一头“脱缰的野马”。只要给它分配了任务，它就在后台狂奔，你既不知道它跑到哪了，也没法中途叫停。如果它不小心用错了工具，或者陷入了“死循环”（比如反复搜索同一个关键词却找不到结果），你只能眼睁睁看着它把 Token 烧光然后报错退出。

**生活化比喻：**
传统的 Agent 就像一个“一根筋的快递员”。你给了他一个地址，他骑着车就跑了。如果路上遇到修路（报错），他不知道绕路，只会在修路的地方一直撞墙；如果他送错小区的楼号了，你也没法中途打电话叫他回来，只能等他彻底失败或者超时。

为了解决这个问题，[LangGraph 1.x](https://langchain-ai.github.io/langgraph/) 诞生了。它并不是一个全新的大模型框架，而是 LangChain 官方推出的**意图流（Workflow）与图编排框架**。

## 2. 什么是状态机 (State Machine) 与图 (Graph)？

LangGraph 的核心思想是将 Agent 的运行过程变成一个**“状态图” (State Graph)**。

你可以把 LangGraph 想象成一张“飞行棋的棋盘”：
1. **State（状态）**：棋子当前走到哪一格，以及你手里现在有多少筹码（当前的对话上下文、提取到的实体变量等）。
2. **Nodes（节点）**：棋盘上的格子。比如“调用大模型”是一个格子，“执行工具”是另一个格子。
3. **Edges（边）**：格子之间的连线，决定了下一步该往哪里走。
4. **Conditional Edges（条件边）**：走到十字路口时的“指路牌”。比如大模型说“我需要查天气”，路牌就指引你走到“天气工具”格子；如果大模型说“我已经知道答案了”，路牌就指引你走到“结束”格子。

<!-- 图表源文件：img/diagrams/01-diagram-01.mmd；视觉风格：Linear 紫色科技感 -->
<p align="center">
  <a href="img/diagrams/01-diagram-01.svg">
    <img src="img/diagrams/01-diagram-01.svg" alt="2. 什么是状态机 (State Machine) 与图 (Graph)？" width="760">
  </a>
</p>

> **注意：** 在 LangGraph 中，数据是在这些节点中循环流动的。这使得我们可以构建非常复杂的**循环逻辑（Cyclic Graphs）**，这也是 LangGraph 相比于普通 LangChain Expression Language (LCEL) 最大的优势。LCEL 只能做单向流水线（DAG，有向无环图），而 LangGraph 可以做死循环和复杂的“反复推敲”。

## 3. LangGraph 1.x 的三大杀器

LangGraph 1.x 引入了许多强大的特性，核心解决的是“可控性”：

1. **State（全局状态共享）**：就像大家共同维护的一张“黑板”。无论流程怎么绕，所有的中间结果、对话记录都保存在这个状态字典里。
2. **Persistence（记忆与持久化）**：自带的 Checkpointer（检查点机制）。就像单机游戏里的“自动存档”。如果跑到一半出错了，下次可以从存档点继续跑，而不是从头再来。
3. **Human-in-the-loop（人类介入 / 拦截）**：可以在执行某个危险动作（比如“确认转账”或“预订不可退款酒店”）之前，自动暂停运行，把控制权交给人类。人类点击“同意”或修改参数后，再继续执行。

## 4. 多智能体框架怎么选？LangGraph vs AutoGen vs CrewAI

能做 Multi-Agent 的框架不止 LangGraph 一家。用开公司来比喻三家定位：

| 框架 | 定位（一句话） | 生活化比喻 | 适合谁 |
| :--- | :--- | :--- | :--- |
| [LangGraph](https://langchain-ai.github.io/langgraph/) | 把智能体系统建模为**有状态图**，节点、边、循环、并行全部显式可控 | **自建厂房 + 流水线**：轨道自己画，闸门自己装 | 要精确控制状态、路由、循环、并行、HITL 的生产级系统 |
| [AutoGen](https://microsoft.github.io/autogen/stable/)（微软） | 多个 Agent **对话协作**完成任务，团队内置轮转/选主等聊天编队 | **圆桌会议**：一群专家围着桌子聊，聊着聊着任务就办了 | 研究、原型验证、以对话为主的协作场景 |
| [CrewAI](https://github.com/crewAIInc/crewAI) | 角色分工的**班组（Crew）** + 事件驱动的**流程（Flow）** | **剧组制**：导演定角色（CEO 助理、研究员、写手），各演各的再合戏 | 快速搭建“角色扮演式”团队，上手门槛最低 |

**怎么选**：如果你的系统是“几个 Agent 自由讨论、角色扮演、协作完成”，CrewAI / AutoGen 往往上手更直接；但如果流程长这样——Agent A 判断 → B/C 并行 → Reviewer 评审 → 不合格重试 → 人工审批 → 收尾——那本质已经不是一个“聊天群”，而是一台**需要状态机的 Agent 工作流**，LangGraph 的图编排、持久化与人工介入闸门就值回票价。

> 💡 三者的边界也在打通：LangChain 生态官方提供多智能体模式总览与选型矩阵（[Multi-Agent 文档](https://docs.langchain.com/oss/python/langchain/multi-agent)），并配套 [langgraph-supervisor](https://github.com/langchain-ai/langgraph-supervisor)、[langgraph-swarm](https://github.com/langchain-ai/langgraph-swarm) 等现成编队库，12 节会逐一亮相。

---

**下一节：** 我们将通过代码真正构建一个简单的 LangGraph 状态图，看看状态（State）是如何在图中流动的。
