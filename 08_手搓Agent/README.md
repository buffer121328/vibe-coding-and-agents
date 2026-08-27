# 🛠️ 第八章：手搓 Agent —— 从 0 到 1 打造你的 AI 智能体内核

> **“What I cannot create, I do not understand.” —— 理查德·费曼 (Richard Feynman)**  
> 想要真正理解 Agent，最好的方法不是调用封装好的黑盒框架，而是**用原生 Python 一行一行把它手搓出来**！

***

## 📖 本章导读 (Chapter Overview)

在前面的章节中，我们学习了 Agent 的理论概念，也体验了 Dify、Trae、OpenCode 等现成工具的高效。但许多开发者常常有这样的困惑：
- *“大模型到底是怎么感知工具并在恰当时机调用它们的？”*
- *“遇到代码报错时，Agent 是如何一边反思一边自我修复的？”*
- *“动辄几万 Token 的长会话，Agent 是如何压缩记忆而不遗忘关键指令的？”*
- *“像 Claude Code 这样的顶尖工具，它的底层调度引擎究竟长什么样？”*

本章将带你彻底打破黑盒，**不依赖任何重型框架（如 LangChain / CrewAI）**，仅依靠 Python 原生机制与官方标准 SDK，参考业界顶尖项目 **[learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)** 与 **[hello-agents](https://github.com/datawhalechina/hello-agents)** 的精髓，使用**清华系智谱 AI（Zhipu AI）最新发布的 GLM-5.3-Flash / GLM-5.3 旗舰模型**（1M 超大上下文、全模态、限时半价超低成本），一步一个台阶，亲手打造出一个功能完备、高颜值、具备工业级韧性的 **Mini-Coding-Agent**！

***

## 🖥️ 教学演示可视化交互工作台 (Interactive Workbench)

为了彻底打破黑盒、降低纯命令行调试的学习门槛，本章特别配套了一个 **现代 IDE 风格的「左侧源码联动 + 右侧交互沙箱」Gradio 可视化全景工作台**。

> 💡 **核心定位说明**：  
> 该可视化前端（`app.py`）**纯粹是为了教学演练与直观调试服务，并非本章的核心业务逻辑**。  
> 我们的核心与灵魂永远是 `s01` 到 `s13` 这 13 个纯手工编写的原生 Python 模块！可视化前端就像是一个**随身携带的智能体“仪表盘与试车场”**——你无需把精力耗费在前端构建上，只需借助它一边看底层源码，一边实时观测智能体思考、工具调用与流式输出的运转细节。

<div align="center">
  <img src="img/04_agent_workbench_ui.png" alt="手搓 Agent 教学演示可视化交互工作台 - 8.1 基础模型接入" width="100%" style="border: 1px solid #d9d9d9; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); margin: 15px 0 8px 0;">
  <p><em>▲ 模块 8.1 演示：智谱 BigModel API 基础接入与极速 SSE Token 流式打字机响应</em></p>
</div>

<div align="center">
  <img src="img/05_agent_react_workbench_ui.png" alt="手搓 Agent 教学演示可视化交互工作台 - 8.2 ReAct 思考闭环推演" width="100%" style="border: 1px solid #d9d9d9; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); margin: 15px 0 8px 0;">
  <p><em>▲ 模块 8.2 演示：ReAct (Thought-Action-Observation) 思考闭环推演与结构化步骤追踪 (Trace)</em></p>
</div>

<div align="center">
  <img src="img/06_agent_mini_agent_workbench_ui.png" alt="手搓 Agent 教学演示可视化交互工作台 - 8.13 Mini-Agent 综合实战" width="100%" style="border: 1px solid #d9d9d9; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); margin: 15px 0 8px 0;">
  <p><em>▲ 模块 8.13 演示：Mini-Agent 综合实战（连续多轮上下文记忆、深度思考、联网搜索与技能插件挂载）</em></p>
</div>

### 🌟 可视化前端设计亮点

1. **📑 13 大模块垂直导航**：
   - 告别传统横向标签栏溢出拥挤的烦恼，采用现代 IDE 侧边栏导航布局；
   - 涵盖从 `8.1 环境基建`、`8.2 ReAct 范式`、`8.4 工具分发`、`8.6 权限门禁`、`8.8 上下文压缩`，直到 `8.13 Mini-Agent 综合实战` 全流程，学到哪一步即可一键点开哪一步。
2. **📜 左侧：Python 原生底层源码实时对照**：
   - 1:1 实时映射当前小节对应的 Python 底层源码文件（如 `s01_env_setup.py`、`s02_react_loop.py`），提供完整行号与语法高亮；
   - 读者无需在编辑器与浏览器之间来回频繁切屏，在页面内就能边看底层实现逻辑，边对照右侧运行表现。
3. **🧪 右侧：交互沙箱与流式打字机**：
   - **真实流式 Token 打字机**：直连智谱 BigModel API，基于 SSE 逐字吐出 Token 并配有呼吸光标动效，体验行云流水的推理响应；
   - **底层机制联动演练**：在沙箱中输入 Prompt 或触发按钮，直接调用左侧底层类的真实逻辑（如 `ReActAgent` 思考循环、`PermissionGuard` 四级风险门禁实时拦截审核等）；
   - **透明步骤追踪 (Trace)**：清晰结构化回放智能体的每一步思考（Thought）、工具动作（Action）与环境观测（Observation）；
   - **8.13 个人 Mini-Agent 对话流**：收官阶段可直接体验支持多轮记忆、联网搜索与深度思考的完整智能体对话。

***

## 🗺️ 13 步进阶全景路线图 (Roadmap)

<!-- 图表源文件：img/diagrams/overview-diagram-01.mmd；视觉风格：Notion 简洁 -->
<p align="center">
  <a href="img/diagrams/overview-diagram-01.svg">
    <img src="img/diagrams/overview-diagram-01.svg" alt="🗺️ 13 步进阶全景路线图 (Roadmap)" width="860">
  </a>
</p>

***

## 📑 章节目录与核心攻关目标

| 章节编号 | 文档名称 | 对应生活比喻 | 核心攻关目标与产出 |
| :--- | :--- | :--- | :--- |
| **8.1** | [环境基建与模型接入](01_环境基建与模型接入.md) | 给管家通电并接入中枢大脑 | 配置智谱 BigModel API Key，封装原生 `ZhipuGLMClient`（GLM-5.3-Flash） |
| **8.2** | [ReAct思考范式](02_ReAct思考范式.md) | 边尝咸淡边加盐的做菜试错 | 跑通 `Thought ➔ Action ➔ Observation` 极简单步试错循环 |
| **8.3** | [Plan and Execute规划范式](03_Plan_and_Execute规划范式.md) | 随身携带的待办便签白板 | 实现结构化任务清单与 `TodoItem` 状态机（Pending/Running/Done） |
| **8.4** | [工具注册与分发机制](04_工具注册与分发机制.md) | 给管家配备万能工具腰带 | 手写 `@tool` 装饰器、类型注解提取、JSON Schema 与分发路由器 |
| **8.5** | [终端执行与代码编辑](05_终端执行与代码编辑.md) | 配备安全手脚与精密手术刀 | 实现安全 `run_bash` 与 Claude Code 招牌 `str_replace` 精准行替换 |
| **8.6** | [权限控制与人类在环](06_权限控制与人类在环.md) | 门口把守的严格安全门禁 | 手写 `PermissionRule`，实现危险指令拦截与终端 `[y/N]` 交互授权 |
| **8.7** | [Hooks生命周期机制](07_Hooks生命周期机制.md) | 行动前后的隐形监控探针 | 实现 `PreToolUse`、`PostToolUse` 切面，完成敏感信息自动脱敏 |
| **8.8** | [上下文工程与压缩](08_上下文工程与压缩.md) | 撕掉杂乱便签，提炼精华小册 | 双轨体系：0ms 滑动窗口截断 + 工具首尾折叠 vs /compact 深度历史摘要 |
| **8.9** | [记忆系统与技能挂载](09_记忆系统与技能挂载.md) | 长期记忆档案与技能安装包 | 本地 JSON 偏好持久化存储，动态扫描并挂载外部 `SKILL.md` |
| **8.10** | [Subagents子代理协作](10_Subagents子代理协作.md) | 主厨派学徒分头去买菜做甜品 | 上下文完全隔离的子代理派发，手搓简易 DeepResearch 多角色管道 |
| **8.11** | [会话持久化与多分支管理](11_会话持久化与多分支管理.md) | 给工程存档并开出平行宇宙 | `SessionStore` 存档读档、树状 `fork` 分叉、断点续跑与 Markdown 导出 |
| **8.12** | [可观测性与性能评估](12_可观测性与性能评估.md) | 给赛车装仪表盘与体检报告 | `EventBus` 事件总线、`TokenCostAudit` 账单审计、`EvalSuite` 成功率/时延/Token 评估 |
| **8.13** | [综合实战：打造个人MiniAgent](13_综合实战_打造个人MiniAgent.md) | 组装出你的专属工作站 | 整合全机制，打造会联网搜索、会深度思考的个人对话 Mini-Agent |
| **8.14** | [常见问题与排查指南](14_常见问题与排查指南.md) | 智能体造物主随身急救包 | 覆盖大模型假死卡住、Gradio排版错乱、环境冲突、权限拦截等全套排障指南 |

***

## 🎓 学完本章你能收获什么？（已具备 vs 尚缺）

> 完整版"项目盘点"见 **[8.13 综合实战](13_综合实战_打造个人MiniAgent.md)** 末尾。速览如下：

- ✅ **已具备**：三大思考范式 + 通用 Agent 主循环；`@tool` 工具生态 / 终端 / `str_replace` / 联网搜索；三级权限门禁 + HITL + Hooks 脱敏 + LoopGuard 熔断；`/compact` 上下文压缩 + 长期记忆 + SKILL.md 技能挂载；Subagents 协作 + 会话持久化多分支 + 可观测性评估；以及一台开箱即用的**个人 Mini-Agent**（含 13 个 Tab 的 Gradio 工作台）。
- ⚠️ **尚不具备**：沙箱容器隔离（Docker）、后台并发守护、Agent 间通信协议（A2A）、复杂 MCP 生态接入、生产级大规模分布式评测。
- 📚 **深入学习**：[learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)（任务依赖/后台任务/团队协议/自治看板）、[hello-agents](https://github.com/datawhalechina/hello-agents)（记忆/RAG/通信协议/评估）。
- 🔧 **二次开发基座**：想自己做一个专属 Agent？推荐基于 **opencode**、**Pi（earendil-works/pi）** 或基于智谱 GLM API 做二次开发，效率远高于从零重写。

***

## 🚀 快速启动（Quick Start）

本章代码全部位于 [`code/`](code/) 目录，推荐使用现代 Python 包管理工具 **`uv`**：

```bash
# 1. 进入代码目录
cd 08_手搓Agent/code

# 2. 复制并配置环境变量（填入智谱 API Key，默认使用 glm-5.3-flash）
cp .env.example .env

# 3. 首次：创建虚拟环境 .venv 并安装全部依赖
uv sync

# 4. 一键启动 13-Tab Gradio 交互工作台
uv run python app.py
# 或运行单个章节脚本，例如：
uv run python s01_env_setup.py
```

浏览器打开 `http://127.0.0.1:7860` 即可在可视化界面中体验 8.1~8.13 全部核心特性。

> 💡 **IDE 提示**：在 VS Code / Trae 中打开 `08_手搓Agent/code` 后，请在右下角状态栏（或 `Cmd+Shift+P` → **Python: Select Interpreter**）选择解释器 `08_手搓Agent/code/.venv/bin/python`，即可消除“无法解析导入”标红并支持直接点 ▶ 运行。

### 依赖库说明

| 依赖库 | 用途 |
| :--- | :--- |
| **`openai`** | 官方 SDK，用于通过 OpenAI 兼容接口连接智谱 BigModel（`/chat/completions`） |
| **`rich`** | 终端彩色高亮、Markdown 渲染与打字机流式动效 |
| **`tiktoken`** | 精确计算与估算 Prompt 的 Token 消耗 |
| **`python-dotenv`** | 安全加载本地 `.env` 环境变量，防止密钥泄露 |

***

## 🔗 权威官方参考与致敬

- **智谱 BigModel 开放平台**：[https://open.bigmodel.cn/](https://open.bigmodel.cn/)
- **智谱 API 快速开始文档**：[https://docs.bigmodel.cn/cn/api/introduction](https://docs.bigmodel.cn/cn/api/introduction)
- **智谱结构化输出文档**：[https://docs.bigmodel.cn/cn/guide/capabilities/struct-output](https://docs.bigmodel.cn/cn/guide/capabilities/struct-output)
- **智谱充值中心**：[https://open.bigmodel.cn/finance-center/finance/pay](https://open.bigmodel.cn/finance-center/finance/pay)
- **learn-claude-code 开源项目**：[https://github.com/shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) —— Harness 工程圣经，8.2/8.5/8.8/8.9/8.13 反复致敬其 12 阶段递进
- **Deep Agents (LangChain)**：[https://github.com/langchain-ai/deepagents](https://github.com/langchain-ai/deepagents) —— 规划/文件系统/子代理/上下文管理即用型 Harness，8.3/8.8/8.10 参考
- **Pi Agent (earendil-works/pi)**：[https://github.com/earendil-works/pi](https://github.com/earendil-works/pi) —— 原子工具哲学、事件驱动、树状会话，8.4/8.7/8.11/8.12 参考
- **Hello-Agents 开源知识库**：[https://github.com/datawhalechina/hello-agents](https://github.com/datawhalechina/hello-agents) —— 经典范式与性能评估，8.2/8.3/8.12 参考

---

让我们从第一步开始，正式开启这场“手搓智能体”的热血之旅！👉 **[8.1 环境基建与模型接入](01_环境基建与模型接入.md)**
