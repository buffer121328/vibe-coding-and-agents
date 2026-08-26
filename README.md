# 🌊 Vibe Coding 极速通关与现代 AI Agent 知识库

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![AI Era: 2026](https://img.shields.io/badge/AI_Era-2026_Frontier-blue.svg)](https://github.com)
[![Status: Actively Developing](https://img.shields.io/badge/Status-Actively_Updating-orange.svg)](https://github.com)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com)

> **“There's a new kind of coding I call 'vibe coding', where you entirely give in to the vibes, embrace every AI, and forget that the code even exists... I just see stuff, say stuff, run stuff, and copy paste stuff, and it mostly works.”**
> —— *Andrej Karpathy (前 OpenAI 联合创始人、前 Tesla AI 总监)*

***

## 📖 项目简介 (About The Project)

欢迎来到 **`vibe_coding`** 开源知识库！

本项目是一个**完全开源、面向零基础到进阶开发者的现代 AI 辅助编程与 Agent 智能体全景指南**。

在 2026 年，软件开发的范式正在经历半个世纪以来最深刻的重塑：

- **从“苦力搬砖码农”跃迁为“交响乐指挥官”**：开发者不再需要死记硬背繁琐的语法、分号和死板配置，而是以架构师与产品总监的视角，用自然语言意图（Intent）驱动 AI 进行软件工程创造；
- **AI 智能体自治闭环**：AI 负责跨文件读写代码、安装依赖、在沙箱中运行测试、自我反思排错；人类负责享受纯粹的创造乐趣！

本项目旨在打破技术黑话壁垒，用**生动通俗的大白话、日常生活比喻、严谨架构图与全套权威官方资料**，带你从底层原理到工程落地彻底通关！

***

## 🗂️ 知识库完整目录体系 (Table of Contents)

```
vibe_coding/
├── LICENSE                                            # MIT 开源许可证
├── README.md                                          # 项目介绍与全景目录总纲
├── agents.md                                          # 智能体协作规则指南 (AI Rules 类似 CLAUDE.md)
├── 01_发展之路/                                       # 第一章：发展之路（编程进化五代史）
│   ├── README.md                                      # 第一章导读与五代演进脉络
│   ├── 01_传统手写代码时代.md                         # 1.1 纯手工打铁与让人秃头的规则
│   ├── 02_AI网页对话时代.md                           # 1.2 人肉搬运工与上下文割裂 
│   ├── 03_AI插件辅助时代.md                           # 1.3 住在编辑器里的超级联想输入法 
│   ├── 04_Agent自主编程时代.md                        # 1.4 自带手脚能跑腿排错的实习生
│   ├── 05_低代码与工作流平台.md                       # 1.5 搭积木与动动嘴出 App
│   └── 06_VibeCoding心智模型与终极演进.md              # 1.6 从苦力码农到交响乐指挥官 
├── 02_概念扫盲/                                       # 第二章：核心概念扫盲
│   ├── README.md                                      # 第二章导读与全景图谱
│   ├── 01_软件架构基础.md                             # 2.1 前端/后端/数据库/中间件/微服务/同步与异步
│   ├── 02_Git与GitHub极速入门.md                      # 2.2 时光机存盘、GitHub 注册与国内代理配置指南
│   ├── 03_大模型本质与Transformer.md                  # 2.3 超级文字接龙、高维压缩与自注意力机制
│   ├── 04_Agent机制与运行原理.md                      # 2.4 Agent 四大支柱与 ReAct 闭环
│   ├── 05_提示词与上下文工程.md                       # 2.5 Prompt vs Context Engineering，KV Cache 
│   ├── 06_记忆管理与AgentSkills.md                    # 2.6 人类三大记忆映射、短期滑动窗口与技能安装包
│   ├── 07_工具调用_MCP与A2A协议.md                    # 2.7 Function Calling 与 MCP 万能接口
│   ├── 08_RAG知识库与向量存储.md                      # 2.8 开卷参考书模式
│   ├── 09_MultiAgent多智能体范式.md                   # 2.9 团队作战！监工/流水线/层级/辩论/蜂群五大范式
│   ├── 10_模型微调与量化技术.md                       # 2.10 SFT/LoRA 深造 vs RAG 选型与量化
│   ├── 11_Harness工程与Loop工程.md                    # 2.11 赛车底盘与标准化考场 (SWE-bench) + 死循环熔断防护
│   ├── 12_主流开发框架全景.md                         # 2.12 LangChain、LangGraph、AutoGen、CrewAI 盘点
│   └── 13_AI时代最值得读的论文和项目.md               # 2.13 8 篇神级论文 + DeerFlow/DeepAgents + Skills + MCP
├── 03_脚手架搭建/                                     # 第三章：脚手架搭建
│   ├── README.md                                      # 第三章导读与全景知识图谱
│   ├── 01_Python编程核心内功.md                       # 3.1 告别 YES 工程师！Python 核心语法与免费名校宝库
│   ├── 02_APIKey原理申请与安全防泄露.md               # 3.2 VIP 门禁卡、主流平台申请与 .env 防盗刷铁律
│   ├── 03_IDE开发环境配置_VSCode与PyCharm.md          # 3.3 VS Code 必备插件天梯榜与 Python 虚拟环境 (venv/uv)
│   ├── 04_主流Agent工具链下载与配置.md                # 3.4 Trae、Claude Code CLI、Cursor、Cline 安装与调优
│   ├── 05_Spec驱动开发与OpenSpec实战.md               # 3.5 终结 AI 瞎猜！
│   ├── 06_Hooks机制_MCP与Skills配置.md                # 3.6 门禁保安 Hooks 机制、mcp.json 配置与技能包挂载
│   ├── 07_中转上游与代理配置_以Codex为例.md           # 3.7 CC-Switch 极速中转网关、.codex 与环境变量
│   └── 08_如何选择AI.md                               # 3.8 主流大模型全景评测、6大业务场景与黄金选型矩阵
├── 04_Dify实战/                                       # 第四章：Dify 实战（低代码与可视化工作流编排）
│   ├── README.md                                      # 第四章导读与全景知识图谱
│   ├── 01_Dify核心概念与平台全貌.md                   # 4.1 控制台功能拆解、四大应用形态与核心节点体系
│   ├── 02_创建工作流与工作室实操.md                   # 4.2 探索工作室、三大创建应用姿势与形态选型指南
│   ├── 03_模型供应商与工具插件生态.md                 # 4.3 全球模型矩阵、多Key密钥池、5大能力与MCP插件
│   ├── 04_面必过Chatbot全景架构与状态机设计.md        # 4.4 业务痛点、游乐园手环状态锁、7大会话变量与插件生态
│   ├── 05_状态锁路由与意图识别分流.md                 # 4.5 JD提取、状态锁If-Else、意图识别Prompt与动态加锁
│   ├── 06_模拟面试流与多专家技术复盘.md               # 4.6 简历懒加载、Python问答记忆拼接、面试引擎与HTML报告导出
│   ├── 07_多专家圆桌式简历优化流水线.md               # 4.7 JD匹配+HR审核+内容优化师、圆桌收敛与精修简历HTML
│   └── 08_工作流调试发布与端到端自测.md               # 4.8 单节点调试、高频避坑清单、发布API集成与Agent节点局限性反思
├── 05_OpenCode实战/                                   # 第五章：OpenCode 实战（开源终端与多智能体意图编排）
│   ├── README.md                                      # 第五章导读与全景知识图谱
│   ├── 01_OpenCode双端下载与主界面设置指南.md         # 5.1 CLI/Desktop 双端安装、主界面拆解与通用提供商设置
│   ├── 02_高级配置_MCP与Skills及omo_slim实战.md       # 5.2 opencode.jsonc 核心拆解、MCP/Skills 挂载与 omo-slim 实战
│   ├── 03_极速破冰_意图驱动单文件小工具实战.md        # 5.3 5分钟破冰、单文件免依赖应用规范与赛博木鱼实战
│   ├── 04_进阶实战_动态交互网页与AI灵感卡片生成器.md  # 5.4 omo-slim 专家协同、高审美 UI 与灵感卡片工坊
│   ├── 05_极简全栈_FastAPI与SQLite个人博客实战(上).md # 5.5 极简全栈：基建准备与阶段拆分规划
│   └── 06_极简全栈_FastAPI与SQLite个人博客实战(下).md # 5.6 极简全栈：前后端编码落地与全链路交付
├── 06_Trae实战/                                       # 第六章：Trae 实战（原生双模驱动与已有项目生产级二次开发）
│   ├── README.md                                      # 第六章导读与全景知识图谱
│   ├── 01_初识Trae：双模驱动、新人福利与生产级IDE新范式.md # 6.1 生态优势、新人首月2.5折、Work/Code双模、单文件精准撤销与Solo模式
│   ├── 02_环境基建与项目导入：在Trae中建立上下文与依赖安装.md # 6.2 工程迁移、uv秒级依赖同步、CodeGraph上下文、IDE神级扩展与探索大作业
│   ├── 03_阶段一实战：用户认证与JWT权限隔离系统.md    # 6.3 指挥官心智、Plan交互模式、Bcrypt哈希与JWT角色权限守卫
│   ├── 04_阶段二实战：评论点赞系统与接口分页重构.md    # 6.4 Solo自主闭环、点赞防刷幂等、楼层评论与Page&PageSize分页重构
│   ├── 05_阶段三实战：AI原生赋能智能摘要与自动打标.md # 6.5 计划先行心智、OpenAI客户端接入、100字导读提炼与AI批量回填
│   └── 06_架构演进与目录治理：从SpringBoot三层架构到现代化全栈解耦.md # 6.6 SpringBoot三层思想、AI上帝文件防腐、生产级目录治理蓝图与进阶宝典
├── 07_Codex实战/                                      # 第七章：Codex 实战
├── 08_手搓Agent/                                      # 第八章：手搓 Agent（基于火山方舟 DeepSeek 从零构建）
│   ├── README.md                                      # 第八章导读、11步演进全景路线图与技术雷达
│   ├── 01_环境基建与模型接入.md                        # 8.1 火山方舟 DeepSeek API 接入与客户端封装
│   ├── 02_ReAct思考范式.md                            # 8.2 极简 Thought-Action-Observation 闭环
│   ├── 03_Plan_and_Execute规划范式.md                 # 8.3 任务清单拆解、Todo 状态机与动态重排
│   ├── 04_工具注册与分发机制.md                        # 8.4 @tool 装饰器、JSON Schema 生成与分发机
│   ├── 05_终端执行与代码编辑.md                        # 8.5 Bash 命令执行与 str_replace 精准行替换
│   ├── 06_权限控制与人类在环.md                        # 8.6 危险指令拦截与 Human-in-the-Loop 交互确认
│   ├── 07_Hooks生命周期机制.md                        # 8.7 Pre/Post 切面拦截、参数脱敏与审计日志
│   ├── 08_上下文工程与压缩.md                          # 8.8 Token 预算、结果截断与 /compact 深度摘要
│   ├── 09_记忆系统与技能挂载.md                        # 8.9 长期记忆提取持久化与 SKILL.md 动态挂载
│   ├── 10_Subagents子代理协作.md                      # 8.10 上下文隔离、子任务派发与 DeepResearch
│   └── 11_综合实战_打造MiniAgent.md                   # 8.11 Rich 高亮终端、LoopGuard 熔断与整机交付
├── 09_LangChain搭建Agent/                             # 第九章：LangChain 搭建 Agent（LCEL 管道流与工业级智能体编排）
│   ├── README.md                                      # 第九章导读、10步进阶全景路线图与技术雷达
│   ├── 01_初识LangChain与生态架构.md                  # 9.1 langchain-core 拆分、统一模型工厂与流式/批量调用
│   ├── 02_Prompt模板与上下文消息流.md                 # 9.2 四大消息模型、ChatPromptTemplate 与 MessagesPlaceholder
│   ├── 03_LCEL表达式语言与流式调度.md                 # 9.3 管道符 '|'、Runnable 协议族、并行流与 Fallbacks 容灾
│   ├── 04_结构化输出与容错解析.md                     # 9.4 with_structured_output、Pydantic 强类型与 JSON 修复
│   ├── 05_自定义工具生态与参数校验.md                 # 9.5 @tool 装饰器、Pydantic 参数防御与 bind_tools 底层机制
│   ├── 06_记忆管理与会话状态持久化.md                 # 9.6 RunnableWithMessageHistory、会话隔离与 trim_messages 裁剪
│   ├── 07_Callbacks回调与可观测性中间件.md            # 9.7 BaseCallbackHandler、Token 账单审计与敏感信息脱敏
│   ├── 08_RAG核心链路与向量检索增强.md                # 9.8 语义切块、Chroma 向量入库与 LCEL 标准 RAG 检索问答
│   ├── 09_Agent现代架构与create_agent.md              # 9.9 现代 Tool Calling Agent、Scratchpad 推理与中间步骤审计
│   └── 10_综合实战_AI智能数码选购与避坑决策Agent.md # 9.10 综合实战：SmartBuyer 数码选购参谋与 10-Tab Gradio 工作台
├── 10_LangGraph搭建工作流/                            # 第十章：LangGraph 搭建工作流（意图图编排与多智能体实战）
│   ├── README.md                                      # 第十章导读与核心概念
│   ├── 01_初识LangGraph与状态机.md                    # 10.1 解决传统Agent不可控痛点，图与状态流转
│   ├── 02_State图的构建与运行.md                      # 10.2 定义交接本State与节点的连线流转
│   ├── 03_条件路由与动态决策.md                       # 10.3 十字路口路由裁判、意图分流与决策树
│   ├── 04_并行执行与Send动态分发.md                   # 10.4 Fan-out/Fan-in 并行与 Send 动态批量并行
│   ├── 05_图的可视化与流式调试.md                     # 10.5 Mermaid/PNG 可视化与 stream 逐节点状态流转
│   ├── 06_Memory与Human-in-the-loop.md                # 10.6 Checkpointer存档与危险动作人类签字拦截
│   ├── 07_MultiAgent分层架构.md                       # 10.7 大堂经理与后厨专家的路由转交状态栈
│   └── 08_综合实战_旅行助手项目.md                    # 10.8 综合实战：企业级全能旅行助手项目重构剖析
├── 11_如何做一个自己的项目/                           # 第十一章：如何做一个自己的项目（个人与应届生 AI 落地实战）
│   ├── README.md                                      # 第十一章导读与全景知识图谱
│   ├── 01_开源选型与二次开发_协议避坑与架构借力.md    # 11.1 站在巨人肩膀、开源许可证(MIT/Apache/GPL/AGPL)避坑与二次开发
│   ├── 02_传统业务AI赋能_从Web小程序到智能体应用.md   # 11.2 电商/CRM/教育/本地生活系统 AI 赋能改造与架构嫁接手术
│   ├── 03_数据困境与业务深耕_拒绝玩具Demo与出彩功能设计.md # 11.3 真实数据破局4招、拒绝代码堆叠、Three.js 3D旅行助手惊艳案例
│   └── 04_求职与能力进阶_垂直微调_小模型降本与开源贡献.md # 11.4 垂直微调(SFT/LoRA)、后训练SLM小模型端侧极致降本与开源PR贡献
└── 12_如何看待AI对时代的意义/                         # 第十二章：如何看待 AI 对时代的意义（认知破局与心理按摩）
    ├── README.md                                      # 第十二章导读与全景认知图谱
    ├── 01_生产力跃迁与超级个体红利.md                 # 12.1 机械打字员到指挥官、创造力平民化与独立开发者十倍杠杆
    ├── 02_结构性阵痛与传统岗位洗牌.md                 # 12.2 机械搬砖岗位挤压、任务消亡vs总需求爆发与拒绝执行末端
    ├── 03_从马夫到司机的历史回响_新职业浪潮与进化.md  # 12.3 百年汽车大博弈、照相机/Excel/ATM历史镜像与5大AI新职业浪潮
    ├── 04_拒绝焦虑割韭菜_构建AI时代不可替代的护城河.md # 12.4 扒开焦虑营销遮羞布、底层技术硬功/思想架构/第一性原理/对抗性思考
    └── 05_AI绝不能碰的红线.md                          # 12.5 AI六大红线：安防攻击/伦理道德/暴力违法/造谣造假/数据隐私/学术诚信
```

***

## 🚧 后续章节火热更新中 (Roadmap & WIP)

> 📢 **提示**：本项目是一个**长期演进、持续更新的活体开源项目**！

当前已完成全套十二个核心章节的目录体系规划与全景知识图谱构建，各章节实战小节文档正在紧锣密鼓地持续打磨中！

***

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

***

## 📄 开源许可证 (License)

本项目采用 **[MIT License](LICENSE)** 开源许可证。

你可以自由地阅读、学习、分享、修改甚至商业化使用本项目的全部内容，只需保留原作者版权与许可声明即可。

***

**🌊 Happy Vibe Coding! 愿每个人都能在 AI 时代享受创造软件的纯粹心流与快乐！**
