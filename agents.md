# 🤖 AGENTS.md —— Vibe Coding 项目智能体协作规范与上下文指南

> **本文件用途**：本文件是专为参与本项目开发与维护的 **AI Coding Agent（如 Cursor、Claude Code、Windsurf、Cline、Devin 等）** 提供的专属规则文件（类似于 `CLAUDE.md` / `.cursorrules`）。所有协助本项目的 AI 必须在理解本文件设定的定位与规则后，严格按规范执行任务。

---

## 🎯 一、项目核心定位与愿景 (Project Identity)

- **项目名称**：`vibe_coding`
- **项目性质**：**开源 AI 辅助编程与 Agent 概念理论教学知识库**
- **开源协议**：MIT License
- **受众画像**：从零基础初学者、产品经理、转行开发者，到想要掌握 AI 意图编排与 Vibe Coding 心智模型的资深工程师。
- **项目目标**：打破技术黑话壁垒，通过通俗生动的语言和严谨的理论结构，带领读者完整建立从“传统手写编程”到“大模型与 Agent 智能体”，最终迈入“Vibe Coding 意图流开发”的认知与实践体系。

---

## 📜 二、智能体必须严格遵守的核心写作规则 (Core Rules for AI)

所有 AI 在为本项目生成、修改或扩展文档时，必须**无条件遵守以下五大原则**：

### 1. 🗣️ 通俗大白话原则（禁止晦涩黑话）
- **核心要求**：严禁堆砌晦涩难懂的学术词汇（如将“认知负荷”改为“让人秃头/大脑超载”，将“FIM 中间填充”改为“中间缺哪补哪”）；
- **生活化比喻优先**：讲解任何抽象的技术概念（如微服务、数据库、异步、注意力机制、Agent 闭环、向量检索、Harness/Loop），必须先引入**非编程的日常生活场景比喻**（如餐厅前厅与后厨、快递打包、嘈杂派对、做大餐试错、相亲角打分雷达图等）；
- **生动幽默、条理清晰**：多使用表格、对比矩阵、步骤清单，做到小白零门槛一眼看懂。

### 2. 🔗 100% 真实权威引用原则（严禁虚构链接）
- **官方权威直达**：所有提到的大模型、开源代码库、技术框架、协议标准必须附带真实有效的官方网站、GitHub 代码仓或 arXiv 论文链接；
- **核心参考锚点**：
  - **实战教学项目**：[Hello-Agents (Datawhale)](https://github.com/datawhalechina/hello-agents)、[Learn-Claude-Code](https://github.com/shareAI-lab/learn-claude-code)；
  - **前沿 Harness 架构**：[DeerFlow (ByteDance)](https://github.com/bytedance/deer-flow)、[DeepAgents (LangChain)](https://github.com/langchain-ai/deepagents)；
  - **生态标准与市场**：[Model Context Protocol (MCP)](https://modelcontextprotocol.io)、[Agent Skills Hub](https://github.com/legendaryabhi/agent-skills-hub)、[Awesome MCP Servers](https://github.com/punkpeye/awesome-mcp-servers)。

### 3. 📊 Mermaid 图表语法合规原则（零容错）
- 为了避免各平台 Markdown 预览器发生 `Parse error` 解析崩溃：
  - 子图定义必须使用安全格式：`subgraph ID ["标题名称"]`；
  - 节点标签内部若包含括号、冒号或特殊字符，必须使用双引号包裹：`NodeID["节点说明 (包含括号)"]`；
  - 严禁在图表标签内滥用原生 HTML 标签。

### 4. 🧭 理论体系为主，前沿实操为辅
- 本项目的重点在于**概念扫盲、架构演进与第一性原理**；
- 避免冗长无趣的重复代码堆砌，重点讲清“为什么需要这个技术”、“解决了什么痛点”、“底层如何运转”、“与其他技术的对比选型”。

### 5. 🛑 Git 操作红线纪律（严禁私自提交）
- 除非人类用户在对话中给出了**明确的提交指令（例如：“帮我提交”、“git commit”）**，否则 AI 在日常创建或修改文件时，**绝对严禁擅自执行 `git commit`**，必须保持工作区修改处于就绪未提交状态！

---

## 🗂️ 三、项目目录结构与知识地图 (Repository Map)

```
vibe_coding/
├── LICENSE                                            # MIT 开源许可证
├── README.md                                          # 项目面向读者的总介绍与全景目录
├── agents.md                                          # 本文件：面向 AI Agent 的专属规则指南
├── 01_发展之路/                                       # 第一章：编程进化五代史（从纯手写到 Vibe Coding）
│   ├── README.md                                      # 第一章导读与脉络图
│   ├── 01_传统手写代码时代.md                         # 1.1 纯手工搬砖时代
│   ├── 02_AI网页对话时代.md                           # 1.2 人肉搬运工时代
│   ├── 03_AI插件辅助时代.md                           # 1.3 智能联想输入法时代
│   ├── 04_Agent自主编程时代.md                        # 1.4 自带手脚的实习生时代
│   ├── 05_低代码与工作流平台.md                       # 1.5 搭积木与动动嘴出 App
│   └── 06_VibeCoding心智模型与终极演进.md              # 1.6 从苦力码农到交响乐指挥官
├── 02_概念扫盲/                                       # 第二章：核心概念扫盲（基建到智能体）
│   ├── README.md                                      # 第二章导读与全景图谱
│   ├── 01_软件架构基础.md                             # 2.1 前端/后端/数据库/中间件/微服务/同步异步
│   ├── 02_Git与GitHub极速入门.md                      # 2.2 时光机存盘、注册与代理配置
│   ├── 03_大模型本质与Transformer.md                  # 2.3 文字接龙、高维压缩与自注意力机制
│   ├── 04_Agent机制与运行原理.md                      # 2.4 Agent 四大支柱与 ReAct 闭环
│   ├── 05_提示词与上下文工程.md                       # 2.5 Prompt vs Context Engineering
│   ├── 06_记忆管理与AgentSkills.md                    # 2.6 人类三大记忆映射与标准化技能包
│   ├── 07_工具调用_MCP与A2A协议.md                    # 2.7 Function Calling 与万能插头标准
│   ├── 08_RAG知识库与向量存储.md                      # 2.8 开卷参考书模式与向量数据库
│   ├── 09_MultiAgent多智能体范式.md                   # 2.9 监工/流水线/层级/辩论/蜂群五大范式
│   ├── 10_模型微调与量化技术.md                       # 2.10 SFT 专科深造 vs RAG 选型与 4-bit 量化
│   ├── 11_Harness工程与Loop工程.md                    # 2.11 运行评测支架 (SWE-bench) 与死循环熔断
│   ├── 12_主流开发框架全景.md                         # 2.12 LangChain、LangGraph、AutoGen、CrewAI 盘点
│   └── 13_AI时代最值得读的论文和项目.md               # 2.13 8 篇神级论文 + 4 大前沿项目 + Skills + MCP
├── 03_脚手架搭建/                                     # 第三章：脚手架搭建（从内功修炼到工具链实战）
│   ├── README.md                                      # 第三章导读与全景知识图谱
│   ├── 01_Python编程核心内功.md                       # 3.1 告别 YES 工程师！Python 核心语法与免费名校宝库
│   ├── 02_APIKey原理申请与安全防泄露.md               # 3.2 VIP 门禁卡、主流平台申请与 .env 防盗刷铁律
│   ├── 03_IDE开发环境配置_VSCode与PyCharm.md          # 3.3 VS Code 必备插件天梯榜与 Python 虚拟环境 (venv/uv)
│   ├── 04_主流Agent工具链下载与配置.md                # 3.4 Trae、Claude Code CLI、Cursor、Cline 安装与调优
│   ├── 05_Spec驱动开发与OpenSpec实战.md               # 3.5 终结 AI 瞎猜！OpenSpec 规范与 Qoder 编译器实战
│   ├── 06_Hooks机制_MCP与Skills配置.md                # 3.6 门禁保安 Hooks 机制、mcp.json 配置与技能包挂载
│   └── 07_中转上游与代理配置_以Codex为例.md           # 3.7 CC-Switch 极速中转网关、.codex 与环境变量配置
├── 04_Dify实战/                                       # 第四章：Dify 实战（低代码与可视化工作流编排）
├── 05_OpenCode实战/                                   # 第五章：OpenCode 实战（开源与开放式 AI 编程智能体）
├── 06_Trae实战/                                       # 第六章：Trae 实战（自适应原生 AI IDE 与全自主编程）
├── 07_Codex实战/                                      # 第七章：Codex 实战（OpenAI 编程大脑与代码生成工程）
├── 08_手搓Agent/                                      # 第八章：手搓 Agent（从零手写 ReAct 最小闭环智能体）
├── 09_LangChain搭建Agent/                             # 第九章：LangChain 搭建 Agent（工业级框架与生态实战）
└── 10_LangGraph搭建工作流/                            # 第十章：LangGraph 搭建工作流（图状态机与多智能体编排）
```

---

## ✅ 四、AI 协助编写后续章节的标准作业流程 (AI SOP)

当用户要求 AI 编写后续章节（如第三章实战环境搭建、第四章 0-1 全栈项目等）时，AI 应当遵循以下验收检查清单：

1. [ ] **大白话检查**：是否每个专有名词都有贴切的生活化比喻？
2. [ ] **架构图检查**：Mermaid 代码是否符合 `subgraph ID ["标题"]` 规范？
3. [ ] **官方链接检查**：涉及到的开源库、工具或大模型是否都有可点击的官方真实超链接？
4. [ ] **目录同步检查**：新生成的文件是否已同步更新至对应章节的 `README.md` 与根目录 `README.md`？
5. [ ] **Git 纪律检查**：是否严格保持本地文件改动未提交，静待用户指令？
