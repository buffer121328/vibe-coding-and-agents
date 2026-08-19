# 📖 第二章：核心概念扫盲 —— 从软件基建到 AI Agent 底层全解

欢迎来到 **《Vibe Coding 极速通关》第二章：概念扫盲**！

如果说第一章《发展之路》帮你建立了宏观的时代视野，那么本章将为你彻底扫清所有**技术专有名词与底层原理**的认知障碍。

不管是前端、后端、数据库、Git，还是大模型底层、Transformer、Agent 闭环、上下文工程、MCP 协议、RAG 向量库、Multi-Agent 多智能体五大范式、微调量化、Harness/Loop 工程、主流开发框架，乃至**AI 时代最值得读的神级论文、前沿神级项目（DeerFlow/DeepAgents）、Skills 市场与 MCP 教程**，我们**一律用大白话和生活化比喻拆解**，即使你是零基础小白，也能轻松通读无压力！

---

## 🧭 第二章全景知识图谱

```mermaid
graph TD
    subgraph Part1 ["第一部分：传统软件工程基建"]
        A1["01 软件架构基础<br/>(前端/后端/数据库/中间件/微服务/同步异步)"]
        A2["02 Git 与 GitHub 极速入门<br/>(版本控制/注册流程/代理网络配置)"]
    end

    subgraph Part2 ["第二部分：大模型底层与认知进化"]
        B1["03 大模型本质与 Transformer<br/>(概率接龙/本质压缩/注意力机制)"]
        B2["05 提示词与上下文工程<br/>(Prompt Engineering vs Context Engineering)"]
        B3["10 模型微调与量化技术<br/>(SFT/LoRA 专项深造 vs GGUF 轻量化压缩)"]
    end

    subgraph Part3 ["第三部分：AI Agent 智能体与前沿范式"]
        C1["04 Agent 机制与运行原理<br/>(大模型大脑 + 工具手脚 + ReAct 闭环)"]
        C2["06 记忆管理与 Agent Skills<br/>(短期窗口/长期记忆/技能包封装)"]
        C3["07 工具调用、MCP 与 A2A 协议<br/>(Function Calling / 万能 Type-C 接口 / 智能体协作)"]
        C4["08 RAG 知识库与向量存储<br/>(开卷考试/Embedding 相似度检索)"]
        C5["09 Multi-Agent 多智能体范式<br/>(团队作战：监工/流水线/层级/辩论/蜂群五大范式)"]
        C6["11 Harness 工程与 Loop 工程<br/>(沙箱评测底盘 / 自主迭代与熔断防护)"]
    end

    subgraph Part4 ["第四部分：实战框架、前沿开源项目与生态大市场"]
        D1["12 主流开发框架全景<br/>(LangChain / LangGraph / AutoGen / CrewAI / LlamaIndex)"]
        D2["13 论文/项目/Skills市场/MCP教程<br/>(8 篇里程碑论文 + DeerFlow/DeepAgents + Skills 市场 + MCP 实战)"]
    end

    Part1 --> Part2
    Part2 --> Part3
    Part3 --> Part4
```

---

## 📑 章节目录导航

点击下方链接逐一阅读各小节的通俗精讲与权威官方链接：

1. **[2.1 软件架构基础：前端、后端、数据库、中间件、微服务、同步与异步](./01_软件架构基础.md)**
   - 饭店前厅与后厨的比喻，彻底搞懂现代互联网软件的骨架与协作方式。

2. **[2.2 Git 与 GitHub 极速入门：时光机、代码云盘、注册与代理配置](./02_Git与GitHub极速入门.md)**
   - 什么是 Git 存盘点？什么是 GitHub 社交广场？国内如何配置代理流畅拉取代码？

3. **[2.3 大模型本质与工作原理：超级文字接龙、高维压缩与 Transformer](./03_大模型本质与Transformer.md)**
   - 大模型到底是怎么学会说话的？它的本质是什么？Transformer 注意力机制在解决什么？

4. **[2.4 Agent 机制与运行原理：给大模型装上眼睛、双手与规划大脑](./04_Agent机制与运行原理.md)**
   - 为什么普通聊天模型不是 Agent？ReAct（思考-行动-观察-自愈）闭环与做大餐大比喻。

5. **[2.5 提示词与上下文工程：从写好 Prompt 到喂饱 Context](./05_提示词与上下文工程.md)**
   - 提示词工程 vs 上下文工程的区别；KV Cache 预制菜与避免“迷失在中间”。

6. **[2.6 记忆管理与 Agent Skills：短期遗忘、长期记忆与技能包扩展](./06_记忆管理与AgentSkills.md)**
   - 人类三大记忆映射、滑动窗口截断、向量记忆库持久化；可复用技能安装包体系。

7. **[2.7 工具调用、MCP 协议与 A2A 协作：打通软硬件万能插头](./07_工具调用_MCP与A2A协议.md)**
   - Function Calling 递小票原理；Anthropic MCP 万能协议；A2A 三大协作拓扑。

8. **[2.8 RAG 知识库与向量存储：给 AI 备一本开卷考试参考书](./08_RAG知识库与向量存储.md)**
   - 相亲角红娘打分雷达图（Embedding）、千层饼分块重叠、海选+决赛混合检索与重排。

9. **[2.9 Multi-Agent（多智能体）：团队作战与五大核心协作范式](./09_MultiAgent多智能体范式.md)**
   - 告别单兵作战瓶颈；深入监工调度、线性流水线、树状层级、法庭辩论对抗与自组织蜂群五大范式！

10. **[2.10 模型微调与量化技术：专科深造与轻量化瘦身秘籍](./10_模型微调与量化技术.md)**
    - SFT/LoRA 专科深造 vs RAG 选型黄金口诀，GGUF/AWQ 4-bit 极限瘦身。

11. **[2.11 Harness 工程与 Loop 工程：从单次问答到自主工业级闭环](./11_Harness工程与Loop工程.md)**
    - 运行与评测支架（Agent/Eval Harness 与 SWE-bench）；自主循环控制与死循环熔断。

12. **[2.12 主流开发框架全景：LangChain、LangGraph、AutoGen 与 CrewAI](./12_主流开发框架全景.md)**
    - 工业级落地框架盘点！三大单 Agent 与三大多 Agent 主流框架横向对比与官方选型指南。

13. **[2.13 AI 时代最值得读的论文、神级项目、Skills 市场与 MCP 教程](./13_AI时代最值得读的论文和项目.md)**
    - 8 篇里程碑论文（Transformer、ReAct、Reflexion、SWE-bench 等）+ 前沿必学神级项目（Hello-Agents、Learn-Claude-Code、DeerFlow、DeepAgents）+ Agent Skills 大市场 + MCP 极速实战教程！
