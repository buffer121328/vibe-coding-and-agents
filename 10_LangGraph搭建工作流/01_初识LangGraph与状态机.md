# 10.1 初识 LangGraph 与状态机

> **“模型负责在路口做判断，轨道必须由人来铺。”**  
> 第九章已经能用 `create_agent` 跑通一轮工具循环。这一节先回答一个更扎心的问题：为什么很多“看起来很聪明”的 Agent，一进真实业务就脱缰？

---

## 为什么单体 Agent 会变成脱缰野马

用 LangChain 或其他框架写 Agent 时，最常见的体验是：你把任务一丢，它就在后台狂奔。你既看不到它走到哪一步，也没法中途叫停。一旦用错工具，或者反复搜索同一个关键词，你只能看着 Token 烧光，然后报错退出。

这就像把一份出差任务交给一个只带手机、不带行程单的同事：

- 你让他“去一趟北京把合同签了”，他可能在机场反复改签，始终不上飞机；
- 路上遇到闸机故障（接口报错），他不会绕路，只会在同一道闸前连续刷卡；
- 真要动用公司账户订不可退票，他也没人签字，直接刷卡走人。

传统“一个大 Prompt + 一堆工具 + 一个 while 循环”的单体 Agent，本质就是这位同事。循环在代码里，决策在模型里，出了问题你只能看最终答案，中间过程像黑盒。

[LangGraph 1.x](https://docs.langchain.com/oss/python/langgraph/overview) 要解决的，不是“让模型更聪明”，而是**让过程可见、可打断、可续跑**。官方把它定位成：**低层编排框架 + 有状态运行时**。你先画出轨道，再让模型在需要理解自然语言的路口做路由。

---

## 先建立一个最小心智模型：飞行棋棋盘

LangGraph 的核心不是又一套 Chain，而是把一次运行变成**状态图（State Graph）**。四个零件对上日常直觉：

| 零件 | 在图里是什么 | 可以怎么记 |
| :--- | :--- | :--- |
| **State（状态）** | 所有节点共享的一份快照 | 棋子走到哪一格，背包里现在有什么 |
| **Nodes（节点）** | 真正干活的 Python 函数 | 棋盘上的格子：调模型、查接口、写摘要 |
| **Edges（边）** | 格子之间的固定连线 | “这一格走完，下一格一定是它” |
| **Conditional Edges（条件边）** | 看状态再决定去哪 | 十字路口的指路牌 |

<!-- 图表源文件：img/diagrams/01-diagram-01.mmd；视觉风格：Linear 紫色科技感 -->
<p align="center">
  <a href="img/diagrams/01-diagram-01.svg">
    <img src="img/diagrams/01-diagram-01.svg" alt="状态图：节点干活，边决定下一步" width="760">
  </a>
</p>

数据在这些节点之间循环流动。这也是它相对第九章 LCEL 最大的差别：LCEL 擅长单向管道（有向无环图），LangGraph 允许**循环**——模型调用工具，看结果，再决定要不要再调一次。没有循环，就没有真正的 Agent。

官方底层跑法借鉴了 Google 的 **Pregel** 消息传递：图按离散的**超步（super-step）**往前走。同一个超步里可以并行跑多个节点；这个超步全部结束后，才进入下一超步。你暂时不必记这个名字，只要知道一件事：**并行不是“线程随便抢”，而是同一拍里一起动。**

---

## LangGraph 真正值钱的三件事

很多教程一上来堆 API。更值得先记住的是它解决的三类工程问题：

1. **共享状态，而不是靠 Prompt 口头交接。**  
   目的地、订单号、已经查过的航班，都写在 State 里。节点读的是同一份快照，不会靠“请模型回忆一下刚才说了什么”。

2. **每一步都能存档。**  
   Checkpointer 在每个超步结束时拍快照。会话要续聊、审批要暂停、进程要崩溃重启，靠的都是这份存档，而不是把历史重新塞进 Prompt。

3. **人可以插进回路。**  
   转账、订不可退票、清库之前，图可以停住，把“准备做什么”交给人类看一眼。同意或改参数后，从原地继续，而不是重开一轮聊天。

这三件事加在一起，Agent 才从“会说话的脚本”变成“能跑长流程的程序”。

---

## 它在生态里站哪一层？

LangChain 负责零件：模型、工具、提示词、中间件。LangGraph 负责运行时：状态怎么走、循环怎么停、失败怎么续。第九章的 `create_agent`，底层就是一张 LangGraph 图。你可以先走高层快车道；等需要自定义路由、子图、审批闸门时，再把同一张图摊开改。

和另外两家常见的多智能体框架比，差别不在“谁更新鲜”，而在**控制权放在哪**：

| 框架 | 一句话定位 | 更像什么 | 适合谁 |
| :--- | :--- | :--- | :--- |
| [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview) | 把系统建成**有状态的图**，节点、边、循环、并行全部显式 | 自己铺轨道、自己装闸门 | 要精确控制状态、路由、HITL、续跑的生产流程 |
| [AutoGen](https://microsoft.github.io/autogen/stable/)（微软） | 多个 Agent **对话协作**，内置轮转 / 选主 | 圆桌讨论，聊着聊着把事办了 | 研究、原型、以对话为主的协作 |
| [CrewAI](https://docs.crewai.com/) | 角色班组 + 事件驱动流程 | 剧组分工：导演定角色，各演各的再合戏 | 快速搭“角色扮演式”团队 |

怎么选可以更直白一点：如果系统长这样——先判断意图，再让 B、C 并行，Reviewer 不过就打回，人签字后才落库——那已经不是聊天群，而是一台需要状态机的工作流。LangGraph 的图、存档和中断，就是为这种结构准备的。

LangChain 当前用五种模式帮你选型（[Multi-Agent 文档](https://docs.langchain.com/oss/python/langchain/multi-agent)）：Subagents、Handoffs、Skills、Router、Custom workflow。生态里还有 [langgraph-supervisor-py](https://github.com/langchain-ai/langgraph-supervisor-py) 与 [langgraph-swarm-py](https://github.com/langchain-ai/langgraph-swarm-py)，但新项目应先按官方模式和上下文需求选，细节放在 12 节。

---

## 先用一条最小路径理解状态图

刚接触时，不必先画十几个节点。可以从“读取问题 → 判断要不要查询 → 返回结果”开始，状态里只留 `messages` 和一个业务字段。跑完后逐项回答：哪个节点读了什么、返回了什么、下一条边为何被选中。

状态图的价值不是“节点越多越专业”，而是让关键决策有明确位置：

- 固定规则能判断的事，优先用普通函数；
- 只有需要理解自然语言时，才让模型上场；
- 每条循环都要有结束条件、最大步数或人工出口，画成图也不会自动避免死循环。

完成这个最小例子后，再加入检查点和工具调用。一次只加一个机制，出了问题才能判断是状态更新、路由判断，还是外部工具造成的。

---

## 扩展阅读

- LangGraph 总览（官方定位：低层编排 + 有状态运行时）：[docs.langchain.com/oss/python/langgraph/overview](https://docs.langchain.com/oss/python/langgraph/overview)
- 图 API 概念（节点、边、状态、超步）：[docs.langchain.com/oss/python/langgraph/graph-api](https://docs.langchain.com/oss/python/langgraph/graph-api)
- Workflows and agents（工作流与 Agent 的分界）：[docs.langchain.com/oss/python/langgraph/workflows-agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)

---

**下一节：** 交接本到底长什么样？节点返回的字典如何合并进状态？以及 1.x 里经常被漏讲的 Runtime 上下文、输入输出 Schema。
