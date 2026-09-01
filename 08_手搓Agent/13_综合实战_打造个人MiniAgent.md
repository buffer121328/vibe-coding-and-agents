# 8.13 综合实战：打造个人 Mini-Agent —— 会联网搜索、会深度思考的对话助手

> **“从 8.1 的一颗 CPU，到如今这台有眼睛（联网搜索）、有大脑（深度思考）、有手（工具调用）、有记性（记忆/技能）、有档案（会话存档）、有仪表盘（可观测）的完整智能体——就像组装一台电脑：零件我们一个个搓好了，今天把它们装成你的专属工作站！”**

***

## 🏗️ 收官整合：一台属于你的「个人 Mini-Agent」

经过前面 12 节的逐个攻坚，我们已经把 Agent 的全部器官逐一搓好：

| 章节 | 搓好的"器官" | 在本节的角色 |
| :--- | :--- | :--- |
| 8.1 | `ZhipuGLMClient` 模型客户端 | 大脑与神经 |
| 8.2 - 8.3 | ReAct / Plan & Execute / Reflection 思考范式 | 思维模式 |
| 8.4 - 8.5 | 工具注册分发 + 终端 + `str_replace` | 手与脚 |
| 8.6 - 8.7 | 权限门禁 + Hooks 切面 | 安全带与监控 |
| 8.8 - 8.9 | 上下文压缩 + 记忆 + 技能挂载 | 内存与经验 |
| 8.10 | Subagents 子代理协作 | 团队分工 |
| 8.11 | 会话持久化与多分支 | 存档读档 |
| 8.12 | 可观测性与评估 | 仪表盘 |

本节是 **收官实战**：我们把所有器官组装成一台 **个人 Mini-Agent**——一个能陪你长期对话的 AI 助手，并新装上两大"王牌能力"：

1. **🌐 联网搜索（Web Search）**：不再局限于模型训练时的旧知识，随时检索最新资讯、数据、文档；
2. **🧠 深度思考（Deep Thinking）**：面对复杂问题时，先"想清楚再回答"，可选用 GLM-R1 深度推理端点。

<!-- 图表源文件：img/diagrams/13-diagram-01.mmd；视觉风格：Pastel 多巴胺 -->
<p align="center">
  <a href="img/diagrams/13-diagram-01.svg">
    <img src="img/diagrams/13-diagram-01.svg" alt="🏗️ 收官整合：一台属于你的「个人 Mini-Agent」" width="760">
  </a>
</p>

***

## 🌐 新能力一：手写会诚实报错的 `web_search`

大模型的训练数据有截止日期，天然无法回答"今天发生了什么"。"联网搜索"就是把 Agent 的眼睛接到真实世界。我们选用 **DuckDuckGo 的 HTML 接口**（无需申请任何 API Key），用标准库 `urllib` 直接抓取、正则解析，完美契合"手搓"精神：

```python
class WebSearch:
    """🔍 联网搜索：DuckDuckGo HTML 接口（免 API Key），返回 标题+链接+摘要"""
    BASE_URL = "https://html.duckduckgo.com/html/?q={query}"
    HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    def search(self, query: str, max_results: int = 5) -> str:
        try:
            url = self.BASE_URL.format(query=urllib.parse.quote(query))
            req = urllib.request.Request(url, headers=self.HEADERS)
            html = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", "ignore")

            # 分别抓取「标题+跳转链接」与「摘要」
            titles = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S)
            snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.S)

            results = []
            for i, (href, title) in enumerate(titles[:max_results]):
                # DuckDuckGo 的链接是 uddg= 重定向参数，需解码还原真实 URL
                real_url = urllib.parse.unquote(re.sub(r".*uddg=([^&]+).*", r"\1", href))
                clean_title = re.sub(r"<.*?>", "", title).strip()
                snippet = re.sub(r"<.*?>", "", snippets[i]).strip() if i < len(snippets) else ""
                results.append(f"### {i + 1}. {clean_title}\n{real_url}\n{snippet[:150]}")
            return "\n\n".join(results) if results else "未检索到结果，请换个关键词再试。"
        except Exception as e:
            # 报错即观测：把错误转成文本喂回给模型，让它换思路
            return f"❌ [web_search 报错] {e}。若在当前网络下无法访问，可更换搜索源或改走本地知识。"
```

要点拆解：
- **免 Key 免依赖**：纯 `urllib + re`，无需申请搜索 API，适合教学与本地跑通；
- **报错即观测**：联网失败时把错误转成结构化文本返回，模型会自动反思、换个思路；
- **可插拔**：若 DuckDuckGo 不可达，只需替换 `search()` 内部抓取逻辑，`MiniAgent` 无需改动；当前实现会明确返回失败，绝不会拿固定文字冒充实时搜索结果。

### 🤔 生产环境一般用什么搜索 API？DuckDuckGo 只是兜底

真实项目里，Agent 的联网搜索通常接入**专为 LLM 优化的搜索 API**，而不是自己去爬 HTML。下表是主流方案：

| 方案 | 特点 | 是否需要 Key | 适用场景 |
| :--- | :--- | :--- | :--- |
| **Tavily** | 专为 LLM 设计的搜索 API，直接返回结构化摘要 | 需要（有免费额度） | 最常见的 Agent 搜索标配 |
| **SerpAPI / Serper** | 封装 Google / 必应搜索结果 | 需要 | 想复用搜索引擎结果 |
| **Bing Web Search API** | 微软官方，国内可达性较好 | 需要 | 国内环境更友好 |
| **Brave Search API** | 隐私友好，有免费额度 | 需要 | 轻量替代方案 |
| **国内搜索 API**（如百度/腾讯云等） | 合规、低延迟 | 需要 | 国内生产部署 |
| **DuckDuckGo HTML（本项目）** | 零成本、免 Key、纯标准库，但页面结构易变 | **不需要** | 教学 / 本地链路演示 |

> 本项目选择 DuckDuckGo HTML 是零成本教学方案。网络失败或解析不到结果时，它只返回可识别错误，不生成看似可信的“实时摘要”。生产环境应换成带 SLA 和结构化响应的搜索 API。

***

## 🧠 新能力二：`deep_think` 深度思考前置规划（参考 deepagents 规划 + ReAct）

普通的对话是"拿到问题 → 直接回答"，容易凭直觉、抓不住重点。工业界两条成熟思路恰好能补上这一环：

- **[deepagents](https://github.com/langchain-ai/deepagents) 的"先规划、再执行"**：内置 `write_todos` 规划工具，先把复杂目标拆成可执行的步骤清单再逐项执行——**先有作战地图，再上战场**；
- **8.2 的 ReAct 范式**：Thought（想）→ Action（做）→ Observation（看），每一步行动前先想清楚"我要做什么、为什么"。

我们把两者融合成一次**深度思考前置规划**：先用深度模型（可指定 **GLM-R1** 端点）产出"问题本质 + 检索计划 + 思考路径"的结构化作战清单，注入上下文后，让后面的 ReAct 工具循环每一步都有明确依据：

```python
def deep_think(self, question: str) -> str:
    """🧠 深度思考前置规划器（参考 deepagents write_todos + 8.2 ReAct 先想后做）"""
    prompt = f"""请以"先规划、再执行"的方式对以下问题做深度思考，输出结构化规划（不超过 300 字）：
1. 📌【问题本质】这个问题的核心矛盾 / 关键点是什么？
2. 🗺️【检索计划】为严谨回答它，需要检索哪些最新或外部信息？（列出 2-3 个候选检索关键词）
3. 🧭【思考路径】可能的论证路径与结论预判。
问题：{question}"""
    res = self.client.chat(
        [{"role": "user", "content": prompt}],
        model_endpoint=self.thinking_endpoint,   # 可传 R1 端点，也可复用主端点
        temperature=0.4,
    )
    return res.choices[0].message.content.strip()
```

```python
# 在 chat() 主循环中，把"作战清单"以 system 角色注入，ReAct 循环据此行动
if deep_think:
    think = self.deep_think(user_input)
    self.bus.emit(AgentEvent("deep_think", content=think))   # 8.12：事件可观测
    self.messages.append({"role": "system", "content": f"【🧠 深度思考前置规划】\n{think}"})
```

> 一句话：**深度思考负责"想清楚仗怎么打"，ReAct 循环负责"一枪一弹地打"**——前者是 deepagents 的规划器思想，后者是 8.2 的行动循环，两者合体才是完整的作战体系。

***

## 💻 组装与运行：`MiniAgent` 对话主循环

完整代码见 `code/s13_mini_agent.py`。`MiniAgent` 把所有器官焊在一起，对外只暴露一个 **`chat(user_input, deep_think)`** 多轮对话接口：

```python
class MiniAgent:
    def __init__(self, client, memory_file="agent_memory.json", skills_dir="skills",
                 thinking_endpoint=None, session_store=None, session_id=None,
                 human_approval_callback=None):
        self.client = client
        self.thinking_endpoint = thinking_endpoint or client.default_model  # 🧠 深度思考端点（默认复用主力模型）
        self.registry = ToolRegistry()                      # 8.4 🧰 工具注册分发
        self.guard = PermissionGuard(...)                    # 8.6 🛡️ 权限门禁
        self.hooks = create_default_hook_manager()           # 8.7 🪝 Hooks 切面
        self.context_mgr = ContextManager(client, ...)       # 8.8 🗜️ 上下文压缩
        self.memory = MemoryStore(memory_file)               # 8.9 💾 长期记忆
        self.skill_loader = SkillLoader(skills_dir)          # 8.9 🎒 技能挂载
        self.web = WebSearch()                               # 🌐 联网搜索（兜底方案）
        self.bus = EventBus()                                # 8.12 📡 可观测事件总线
        self.session_store = session_store                   # 8.11 🗂️ 会话仓库（可选）
        self.session_id = session_id
        self.messages = []                                   # 💬 多轮对话上下文
        if self.session_id and self.session_store:
            node = self.session_store.load(self.session_id)
            if node and node.messages:
                self.messages = node.messages                # 📂 断点续跑
        self._register_default_tools()

    def chat(self, user_input, deep_think=False, active_skills=None):
        """💬 对话主循环：深度规划 → ReAct 工具循环 → 回答 + 可观测轨迹"""
        # 1. 首次对话注入记忆与技能（8.9）
        # 2. 深度思考前置规划（deepagents 思想，可选）
        # 3. while True: ReAct 主循环（8.2）
        #    模型决策(8.1) → 工具调用(8.4) → 门禁(8.6) → Hooks(8.7) → 截断(8.8)
        #    → 回填 → 事件广播(8.12)，结束时自动存档(8.11)
        ...
```

这套 `chat()` 其实就是 8.2 的**通用 Agent 主循环**的完整工业形态——所有前序能力以"插件"方式挂载在循环里，一个器官都没有浪费。

> ✨ **输出适配：Markdown 润色**：大模型的回答是"原生态" Markdown，常有 `##标题` 缺空格、连续空行、代码围栏未闭合等小毛病。`MiniAgent` 在给出最终回答前会经过 `polish_markdown()` 统一润色——自动补全标题空格、压缩多余空行（代码块内部空行**原样保留**）、配对闭合代码围栏并规整首尾空白，保证终端与网页都能得到干净规范的排版。

### 🧵 本章如何串起 1-12 章的全部知识点？

| 章节知识点 | 在个人 Mini-Agent 中的落点 |
| :--- | :--- |
| 8.1 模型客户端 | `ZhipuGLMClient` 统一对话 / 流式入口 |
| 8.2 ReAct 范式 | `chat()` 的 Thought-Action-Observation 主循环 |
| 8.3 规划范式 | `deep_think()` 深度思考前置规划器（融合 deepagents 思想） |
| 8.4 工具注册分发 | `ToolRegistry` + `@register` 五件套工具 |
| 8.5 终端与编辑 | `exec_bash` / `read_file` / `edit_file_replace` |
| 8.6 权限门禁 | `PermissionGuard` 高危拦截 + `[y/N]` 人类审批 |
| 8.7 Hooks 切面 | Pre/Post 钩子：计时 + 敏感信息脱敏 |
| 8.8 上下文压缩 | `ContextManager` 自动 `/compact` + 长结果截断 |
| 8.9 记忆与技能 | `MemoryStore` 偏好记忆 + `SkillLoader` 技能注入 |
| 8.10 子代理 | 深度调研时可接入 `DeepResearchPipeline`（可选） |
| 8.11 会话持久化 | `SessionStore` 自动存档 + 断点续跑 |
| 8.12 可观测性 | `EventBus` 全流程事件轨迹（trace 可直接回放） |

> 从 8.1 到 8.12，每一个器官都在这台个人 Mini-Agent 上真正"上岗"了——这正是本章取名**综合实战**的意义。

***

## 🕹️ 动手体验

### 方式一：命令行直接对话（推荐先试这个）

```bash
cd 08_手搓Agent/code
uv run python s13_mini_agent.py
```

```
🤖 个人 Mini-Agent 已启动！
  - 输入 普通问题：直接对话回答
  - 输入 /deep 问题：开启深度思考后回答
  - 输入 /search 问题：强制先联网搜索再回答

👤 You> 2026年最新的主流前端框架有哪些新趋势？
🧠 Agent 思考中…
🛠️ 调用了 web_search → ### 1. React 19 发布 ...
🤖 Agent> 根据最新资料，2026 年前端领域主要有三大趋势：……
```

### 方式二：Gradio 工作台

> 🧪 **这是真实模型对话，不是 Mock 聊天**：每次发送都会调用 `ZhipuGLMClient`；Agent 决定搜索或勾选“强制联网搜索”时，还会尝试访问真实 DuckDuckGo 搜索页面。请先配置 `ZHIPU_API_KEY`，并留意多轮对话、深度思考与工具回填都会增加 Token 消耗。

在 `code/app.py` 中切换到 **`8.13 Mini-Agent 综合实战`** 标签页：
1. 输入多轮连续问题，例如先告诉它自己的名字和偏好，再提问确认长期记忆；
2. 勾选 **🔍 强制联网搜索** 或 **🧠 深度思考** 开关，或挂载 `git_expert` / `python_cleaner` 技能插件；若要保存长期偏好，还需显式勾选“允许本轮保存偏好”，该授权不会放行终端或代码编辑；
3. 点击 **🚀 发送**，观察支持多轮气泡对话流的完整 Mini-Agent 实时作答，并可在底部展开决策流与权限门禁审计 Trace！

<div align="center">
  <img src="img/06_agent_mini_agent_workbench_ui.png" alt="8.13 Mini-Agent 多轮对话与全机制综合实战工作台" width="100%" style="border: 1px solid #d9d9d9; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); margin: 15px 0;">
  <p><em>▲ Gradio 工作台中 8.13 Mini-Agent 连续多轮上下文记忆、深度思考与联网搜索综合实战</em></p>
</div>

***

## 🧭 项目盘点：我们已经具备了什么？还不具备什么？

至此，第八章收官。是时候坦诚地给这个"手搓 Agent"做一次体检了。

### ✅ 本项目已经具备的（核心能力）

1. **完整的思考内核**：ReAct / Plan & Execute / Reflection 三大范式 + 通用 Agent 主循环；
2. **全链路工具生态**：`@tool` 自动 Schema、终端执行、`str_replace` 精准编辑、文件系统工具、联网搜索；
3. **安全与可控**：三级权限门禁 + Human-in-the-Loop + Hooks 脱敏/审计 + LoopGuard 熔断；
4. **长效运行**：上下文 `/compact` 压缩、长期记忆持久化、SKILL.md 技能挂载；
5. **工程化进阶**：Subagents 协作、会话持久化与多分支、可观测性与评估；
6. **可直接演练**：一台会联网搜索、会深度思考、能多轮对话的教学型 Mini-Agent，外加 13 个模块的 Gradio 可视化工作台。

### ⚠️ 本项目还不具备的（面向生产的差距）

| 差距 | 说明 | 进阶方向 |
| :--- | :--- | :--- |
| **沙箱隔离** | 我们的 Agent 直接跑在本机，危险命令靠规则拦截；生产环境应放进 Docker 无权限容器 | 容器化 + 远程沙箱 |
| **流式体验** | 回答是"等全部生成完再显示"，没有逐 Token 流式渲染 | 接入 8.1 的 `chat_stream` |
| **后台并发** | 长任务（编译/测试）会阻塞对话，多子代理只能串行 | 后台线程 + 任务看板 |
| **团队通信** | 子代理之间只能串行传参，没有异步消息/协议（A2A） | Agent 间消息协议 |
| **MCP 生态** | 工具都是手搓的，还没接入现成的 MCP 工具服务器 | 按 MCP 协议接工具 |
| **评测闭环** | 有 `EvalSuite` 雏形，但缺少生产级基准集与回归流水线 | 评估数据集 + CI |
| **Prompt 打磨** | 系统提示词偏朴素，未做系统化的 prompt 优化与 A/B | Prompt 工程方法论 |

### 📚 后续深入学习路线（强烈推荐）

- **learn-claude-code（shareAI-lab）**：本项目的灵感源泉，12 个阶段把 Claude Code 从 84 行搓到 694 行，值得逐阶段精读，尤其补上我们缺的"任务依赖 / 后台任务 / 团队通信协议 / 自治看板"；
- **DeerFlow（GLM 开源的深度研究框架）**：研究"规划 → 检索 → 反思"的深度研究工作流是如何在工业级工程里落地的，是我们 8.10 DeepResearch 流水线的完整版参考；
- **hello-agents（Datawhale）**：第 8-12 章的记忆/RAG、上下文工程、通信协议、Agentic-RL、性能评估，补齐理论纵深。

### 🔧 如果想做"属于自己的 Agent"，建议二次开发基座

不必从零再搓一遍——在以下开源基座上做二次开发效率最高：

1. **opencode（sst 团队）**：TypeScript 开源 Agent，CLI + TUI + 多模型，你在第 5 章已经玩过它——加自己的工具、Skills、命令都极其顺滑；
2. **Pi（earendil-works/pi）**：Mario Zechner 打造的最小核心 Agent 框架，只有 read/write/edit/bash 四个原子工具，MIT 协议，最适合"按自己口味长成任何形状"；
3. **GLM Harness（GLM 官方 Agent 脚手架）**：与本章同源的国产模型底座，适合在此基础上接入自家业务、私有模型与评测体系。

> 一句话收尾：**能手搓，就一定能魔改**。看懂原理之后，无论用哪个基座，你都能玩出自己的花样。

***

## 🏁 第八章完：从 API 使用者到 Agent 构建者

恭喜你走完全程！从 8.1 的第一次 API 调用，到 8.13 这台会搜索、会深思、会存档、可观测的个人 Mini-Agent，你已经完成了从**大模型 API 使用者**到**智能体架构构建者**的质变：

1. **看透黑盒**：你亲手写过每一行请求报文、每一个工具 Schema、每一处循环调度；
2. **掌握范式**：ReAct / Plan&Execute / Reflection 的取舍了然于心；
3. **具备工程观**：权限、切面、压缩、记忆、并发、观测——工业级 Agent 的骨架你都搭过一遍。

掌握了最纯粹的第一性原理之后，再去学任何上层框架（LangChain、LangGraph、CrewAI…）都将势如破竹。下一站，让我们用成熟框架把这些原理"省力地"复用起来——请前往 **[第九章：LangChain 搭建 Agent](../09_LangChain搭建Agent/README.md)**！
