# 🌊 Vibe Coding 极速通关与现代 AI Agent 知识库

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![AI Era: 2026](https://img.shields.io/badge/AI_Era-2026_Frontier-blue.svg)](https://github.com)
[![Status: Actively Developing](https://img.shields.io/badge/Status-Actively_Updating-orange.svg)](https://github.com)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com)

> **“There's a new kind of coding I call 'vibe coding', where you entirely give in to the vibes, embrace every AI, and forget that the code even exists... I just see stuff, say stuff, run stuff, and copy paste stuff, and it mostly works.”**
> —— *Andrej Karpathy (前 OpenAI 联合创始人、前 Tesla AI 总监)*

---

## 📖 项目简介 (About The Project)

欢迎来到 **`vibe_coding`** 开源知识库！

本项目是一个**完全开源、面向零基础到进阶开发者的现代 AI 辅助编程与 Agent 智能体全景指南**。

在 2026 年，软件开发的范式正在经历半个世纪以来最深刻的重塑：
- **从“苦力搬砖码农”跃迁为“交响乐指挥官”**：开发者不再需要死记硬背繁琐的语法、分号和死板配置，而是以架构师与产品总监的视角，用自然语言意图（Intent）驱动 AI 进行软件工程创造；
- **AI 智能体自治闭环**：AI 负责跨文件读写代码、安装依赖、在沙箱中运行测试、自我反思排错；人类负责享受纯粹的创造乐趣！

本项目旨在打破技术黑话壁垒，用**生动通俗的大白话、日常生活比喻、严谨架构图与全套权威官方资料**，带你从底层原理到工程落地彻底通关！

---

## 🌟 项目核心特色 (Key Highlights)

1. **💡 零门槛大白话精讲**：拒绝晦涩黑话，用“餐厅大厨”、“快递打包”、“嘈杂派对注意力”、“做大餐自愈试错”等生活化比喻，小白一读就懂；
2. **🚀 2026 顶尖前沿生态**：全面涵盖 **DeerFlow**（字节开源）、**DeepAgents**（LangChain 官方）、**Claude Code CLI**、**Cursor Composer**、**Bolt.new**、**Dify** 等最新生产力利器；
3. **🏛️ 理论 + 手搓实战 + 工业级 Harness**：从 Transformer 与 ReAct 论文第一性原理，到 **Hello-Agents** 与 **Learn-Claude-Code** 手搓架构，再到工业级评测体系 **SWE-bench**；
4. **🔗 100% 真实权威引用**：所有提到的前沿大模型、开源代码仓库、学术论文与技术标准（MCP / Agent Skills）均配有可直达的官方链接。

---

## 🗂️ 知识库完整目录体系 (Table of Contents)

```
vibe_coding/
├── LICENSE                                            # MIT 开源许可证
├── README.md                                          # 项目介绍与全景目录总纲
├── agents.md                                          # 智能体协作规则指南 (AI Rules 类似 CLAUDE.md)
├── 01_发展之路/                                       # 第一章：发展之路（编程进化五代史）
│   ├── README.md                                      # 第一章导读与五代演进脉络
│   ├── 01_传统手写代码时代.md                         # 1.1 纯手工打铁与让人秃头的规则
│   ├── 02_AI网页对话时代.md                           # 1.2 人肉搬运工与上下文割裂 (Claude 5/GPT-5.6/DeepSeek V4)
│   ├── 03_AI插件辅助时代.md                           # 1.3 住在编辑器里的超级联想输入法 (Copilot/Continue)
│   ├── 04_Agent自主编程时代.md                        # 1.4 自带手脚能跑腿排错的实习生 (Cursor/Devin/Claude Code)
│   ├── 05_低代码与工作流平台.md                       # 1.5 搭积木与动动嘴出 App (Dify/Coze & Bolt.new/Lovable)
│   └── 06_VibeCoding心智模型与终极演进.md              # 1.6 从苦力码农到交响乐指挥官 (Karpathy 核心心法)
├── 02_概念扫盲/                                       # 第二章：核心概念扫盲（基建到智能体）
│   ├── README.md                                      # 第二章导读与全景图谱
│   ├── 01_软件架构基础.md                             # 2.1 前端/后端/数据库/中间件/微服务/同步与异步 (餐厅大比喻)
│   ├── 02_Git与GitHub极速入门.md                      # 2.2 时光机存盘、GitHub 注册与国内代理配置指南
│   ├── 03_大模型本质与Transformer.md                  # 2.3 超级文字接龙、高维压缩与自注意力机制
│   ├── 04_Agent机制与运行原理.md                      # 2.4 Agent 四大支柱、做大餐比喻与 ReAct 闭环
│   ├── 05_提示词与上下文工程.md                       # 2.5 Prompt vs Context Engineering，KV Cache 预制菜心法
│   ├── 06_记忆管理与AgentSkills.md                    # 2.6 人类三大记忆映射、短期滑动窗口与技能安装包
│   ├── 07_工具调用_MCP与A2A协议.md                    # 2.7 Function Calling 递小票原理与 MCP 万能接口
│   ├── 08_RAG知识库与向量存储.md                      # 2.8 开卷参考书模式、相亲角打分与海选决赛重排
│   ├── 09_MultiAgent多智能体范式.md                   # 2.9 团队作战！监工/流水线/层级/辩论/蜂群五大范式
│   ├── 10_模型微调与量化技术.md                       # 2.10 SFT/LoRA 专科深造 vs RAG 选型与 4-bit 量化
│   ├── 11_Harness工程与Loop工程.md                    # 2.11 赛车底盘与标准化考场 (SWE-bench) + 死循环熔断防护
│   ├── 12_主流开发框架全景.md                         # 2.12 LangChain、LangGraph、AutoGen、CrewAI 压轴盘点
│   └── 13_AI时代最值得读的论文和项目.md               # 2.13 8 篇神级论文 + DeerFlow/DeepAgents + Skills + MCP
└── 03_脚手架搭建/                                     # 第三章：脚手架搭建（从内功修炼到工具链实战）
    ├── README.md                                      # 第三章导读与全景知识图谱
    ├── 01_Python编程核心内功.md                       # 3.1 告别 YES 工程师！Python 核心语法与免费名校宝库
    ├── 02_APIKey原理申请与安全防泄露.md               # 3.2 VIP 门禁卡、主流平台申请与 .env 防盗刷铁律
    ├── 03_IDE开发环境配置_VSCode与PyCharm.md          # 3.3 VS Code 必备插件天梯榜与 Python 虚拟环境 (venv/uv)
    ├── 04_主流Agent工具链下载与配置.md                # 3.4 Trae、Claude Code CLI、Cursor、Cline 安装与调优
    ├── 05_Spec驱动开发与OpenSpec实战.md               # 3.5 终结 AI 瞎猜！OpenSpec 规范与 Qoder 编译器实战
    ├── 06_Hooks机制_MCP与Skills配置.md                # 3.6 门禁保安 Hooks 机制、mcp.json 配置与技能包挂载
    └── 07_中转上游与代理配置_以Codex为例.md           # 3.7 CC-Switch 极速中转网关、.codex 与环境变量配置
```

---

## 🚧 后续章节火热更新中 (Roadmap & WIP)

> 📢 **提示**：本项目是一个**长期演进、持续更新的活体开源项目**！

当前已完成前三章的演进史、底层概念扫盲与开发脚手架搭建，后续章节正在紧锣密鼓地打磨中：
- **第四章：提示词与规则工程实战规范**（团队专属 `.cursorrules` 与 `AGENTS.md` 模板库、System Prompt 防翻车秘籍）；
- **第五章：Vibe Coding 从 0 到 1 实战项目演练**（全栈应用极速开发：Bolt.new 极速打样 ➔ Dify 搭建 RAG 后端 ➔ Cursor 落地交付上线）；
- **第六章：进阶 Agent Harness 架构手搓实战**（参考 DeerFlow / DeepAgents，动手开发属于你自己的轻量级软件工程师 Agent）。

---

## 🤝 共同学习，欢迎贡献！(Join Us & Contributing)

一个人可以走得很快，但一群人可以走得更远！**我们非常欢迎大家共同学习、一起进步！**

- **💡 提交你的金点子（Ideas）**：如果你有更精彩、更有趣的生活化比喻，或者发现了前沿的重磅论文与工具，欢迎随时提 **Issue** 或 **PR**；
- **📐 完善开发规范与规则（Rules）**：如果你对不同开发语言（Python / TypeScript / Go / Rust）的 Vibe Coding 规范或 `.cursorrules` 沉淀有独到见解，期待你的分享；
- **🐛 纠错与优化**：发现任何错别字、链接失效或描述不准确之处，欢迎一键发起 Pull Request！

```bash
# 参与贡献极简三步走：
1. Fork 本仓库到你的个人 GitHub
2. 新建你的分支：git checkout -b feature/awesome-idea
3. 提交 PR 并描述你的贡献，我们会在第一时间审核合并！
```

---

## 📄 开源许可证 (License)

本项目采用 **[MIT License](LICENSE)** 开源许可证。

你可以自由地阅读、学习、分享、修改甚至商业化使用本项目的全部内容，只需保留原作者版权与许可声明即可。

---

**🌊 Happy Vibe Coding! 愿每个人都能在 AI 时代享受创造软件的纯粹心流与快乐！**
