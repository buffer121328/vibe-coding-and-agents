# 5.2 模型配置、MCP、Skills 与 omo-slim

基础对话能正常工作后，再逐项增加配置会更容易排错。本节介绍模型配置、MCP 工具、技能说明和多角色插件的分工，帮助你判断哪些是当前任务需要的，哪些可以以后再加。

---

## OpenCode 的高级生态体系

我一般将opencode视作轻量级开发的主力，所以安装的配件和mcp不多，但都是真正好用的，同学们可以先看一下。\
配置扩展之前，需要先理解以下四个核心组件的分工与协作：

<!-- 图表源文件：img/diagrams/02-diagram-01.mmd；视觉风格：Pastel 多巴胺 -->
<p align="center">
  <a href="img/diagrams/02-diagram-01.svg">
    <img src="img/diagrams/02-diagram-01.svg" alt="💡 一、OpenCode 的高级生态体系" width="860">
  </a>
</p>

- 🖥️ **`opencode.jsonc`** **—— 赛车主板电脑**：决定了接入什么发动机（模型供应商）、加多少号汽油（API Key）、油门与刹车响应阈值（超时参数）；
- 🔌 **MCP（Model Context Protocol）—— 车顶万能扩展坞**：即插即用，给 AI 挂载代码图谱分析、实时联网搜索、数据库查询等外部超能力；
- 📜 **Skills —— 特战技能证书**：教 AI 如何按照特定标准执行复杂专业动作（如代码简化重构、浏览器完整流程测试）；
- 👥 **`oh-my-opencode-slim`（简称 omo-slim）—— 六个分工角色**：将任务分给统筹、架构、检索、探索、设计和修复等角色，适合边界清楚、可以独立交付的子任务。

***

## 配置文件的作用与存储路径

OpenCode 采用统一的全局配置文件管理所有模型、插件、MCP 与专家预设。

### 配置文件存储路径：

- **macOS / Linux**：`~/.config/opencode/opencode.jsonc`（或 `~/.config/opencode/opencode.json`）
- **Windows**：`%USERPROFILE%\.config\opencode\opencode.jsonc`

> 💡 **为什么推荐使用** **`.jsonc`** **而非** **`.json`？**
> 标准 `.json` 格式是严禁写注释的，只要多写一个 `//` 就会导致解析崩溃。而 `.jsonc`（JSON with Comments）原生支持双斜杠 `//` 注释。你可以随手记录某个模型参数的调整原因、超时配置的考量，适合长期维护与团队协作。

***

## `opencode.jsonc` 核心字段拆解

下面是一份已移除密钥和个人信息的配置模板，可以参考其结构进行修改：

```jsonc
{
  // 1. 语法约束与编辑器智能提示 Schema
  "$schema": "https://opencode.ai/config.json",

  // 2. 模型供应商与模型定义 (Providers & Models)
  "provider": {
    "deepseek": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "DeepSeek",
      "options": {
        "baseURL": "https://api.deepseek.com",
        "apiKey": "sk-your-deepseek-api-key-here",
        // 关键超时调优：推理大模型思考链首包较慢，防止被网关短超时过早掐断
        "timeout": 300000,        // 总请求超时 5 分钟
        "headerTimeout": 180000,  // 响应头等待超时 3 分钟
        "chunkTimeout": 120000    // 数据流分块超时 2 分钟
      },
      "models": {
        "deepseek-chat": {
          "name": "DeepSeek-V4-flash",
          "limit": {
            "context": 100000,
            "output": 128000
          }
        },
        "deepseek-reasoner": {
          "name": "DeepSeek-v4-pro",
          "limit": {
            "context": 100000,
            "output": 128000
          },
          "options": {
            "reasoningEffort": "max",
            "thinking": {
              "type": "enabled"
            }
          }
        }
      }
    },

  // 3. 智能体基础策略配置
  "agent": {
    "build": {
      "options": {
        "store": false            // 隐私保护：禁止数据被远端留存用于模型训练
      }
    },
    "plan": {
      "options": {
        "store": false
      }
    }
  },

  // 4. 插件生态加载
  "plugin": [
    "oh-my-opencode-slim"        // 载入轻量化多智能体专家调度器
  ],

  // 5. 开启 LSP 语言服务协议（为 AI 装上静态语法检查之眼）
  "lsp": true,

  // 6. MCP 外部工具扩展协议挂载
  "mcp": {
    "codegraph": {
      "type": "local",
      "command": [
        "codegraph",
        "serve",
        "--mcp"
      ],
      "enabled": true
    }
  }
}
```

***

### 核心配置字段解析：

#### 1. `provider` 与底层驱动 (`npm`)

- **`npm: "@ai-sdk/openai-compatible"`**：OpenCode 采用 Vercel AI SDK 作为标准化驱动层。绝大多数主流大模型服务商（包括 DeepSeek、Moonshot、Qwen、硅基流动、OneAPI/NewAPI 等中转网关）均兼容 OpenAI 接口规范，可通过该驱动接入兼容服务；工具调用、结构化输出等参数仍需单独验证。

#### 2. 超时参数调优（高频避坑核心 ⚠️）

在连接思考型模型或经由国内反向代理/中转网关时，很多同学常遇到 `503 Service Unavailable` 或 `FetchError: Header Timeout` 报错。这是因为**模型在深度思考时，可能长达 30\~60 秒不吐出第一个 Token**。

- **`timeout`**（默认总超时）：建议设置为 `300000`（5 分钟），保证大任务长代码生成不被强制中断；
- **`headerTimeout`**（响应头等待超时）：内置默认值往往只有 10\~30 秒，极易误判为连接超时。强烈建议调大至 `180000`（3 分钟）；
- **`chunkTimeout`**（流式分块间隔超时）：建议设为 `120000`（2 分钟）。

#### 3. `models` 与 `limit`（窗口与输出上限）

- **`context`**：声明模型的最大上下文窗口（如 128,000 / 200,000 / 1,000,000）；
- **`output`**：单次请求的最大生成输出 Token 上限；
- **`variants`**：变体级别（如 `low` / `medium` / `high` / `max`），允许你在对话中随时一键调整推理思考深度。

#### 4. `lsp: true`（代码语言服务）

开启 LSP 后，OpenCode 会在后台自动调用项目语言的原生 Language Server（如 TypeScript LSP、Pyright、gopls 等），使 AI 在写完代码后能像人类 IDE 一样自动捕获语法错误和类型不匹配，极大提高生成代码的编译通过率。

#### 5. 环境变量与密钥安全要求

**切勿把真实 API Key 明文写进 `opencode.jsonc`。** 配置文件一旦分享或提交到代码仓，密钥即告泄露。OpenCode 支持在配置中通过 **`${环境变量名}`** 引用环境变量：

```jsonc
"options": {
  "baseURL": "https://api.deepseek.com",
  "apiKey": "${DEEPSEEK_API_KEY}"   // 从环境变量读取，避免明文
}
```

你可以在项目根目录放置 `.env` 文件（并加入 `.gitignore`），OpenCode 启动时会自动加载；也可以在终端 `export DEEPSEEK_API_KEY=sk-xxx` 后重启 OpenCode。这样既安全，多台设备复用时也无需改动配置。

> 💡 API Key 的申请与防泄露规范，可回顾 [3.2 API Key 原理申请与安全防泄露](../03_脚手架搭建/02_APIKey原理申请与安全防泄露.md)。

***

## MCP（Model Context Protocol）工具扩展实战

**MCP** 是 Anthropic 发起、如今已成为行业通用标准的外部工具协议。它就像是给 AI 插上的 **USB-C 拓展坞**。

### 1. 本地 MCP 挂载（Local Command）

本地 MCP 通过在宿主机执行可执行命令拉起。例如挂载代码图谱分析工具 `codegraph`：

```jsonc
"mcp": {
  "codegraph": {
    "type": "local",
    "command": ["codegraph", "serve", "--mcp"],
    "enabled": true
  }
}
```

> 💡 **CodeGraph 自动同步（Auto-Sync）**：挂载 MCP 前，请先在项目根目录执行一次 `codegraph init` 完成索引初始化（详见 [5.5 节](./05_极简全栈_FastAPI与SQLite个人博客实战%28上%29.md)）。初始化完成后，CodeGraph 会在后台启动守护进程（Daemon）并开启文件监听（File Watcher），每次代码保存都会**毫秒级增量同步**到 `.codegraph/codegraph.db`，全程无需手动重建索引。

### 2. 远程 MCP 挂载（Remote SSE / HTTP）

如果你部署了远程 MCP 代理服务，可以通过 URL 挂载：

```jsonc
"mcp": {
  "websearch": {
    "type": "remote",
    "url": "https://mcp.your-domain.com/sse",
    "enabled": true
  }
}
```

***

## Agent Skills 技能包加载指南

**Agent Skills** 是遵循标准化规范的“即插即用战术手册”。它以纯文本或脚本的形式告诉 AI 在面对特定场景时该遵循怎样的标准作业流程（SOP）。

### 1. 技能包存放路径：

- **全局生效**：`~/.config/opencode/skills/<skill-name>/`
- **生效**：`./.opencode/skills/<skill-name>/`

### 2. 经典技能包举例：

- **`simplify`**：代码精简与坏味道消除技能，专为重构和去冗余设计；
- **`agent-browser`**：为 AI 配备无头浏览器（Headless Browser），让 AI 能够自主打开网页、点击按钮、抓取截图并完成完整流程测试。

***

## 扩展配置：深入理解 `oh-my-opencode-slim`（omo-slim）

### 1. 本例为什么使用 `omo-slim`

本节使用 [`oh-my-opencode-slim`](https://github.com/code-any-way/oh-my-opencode-slim)演示角色分工。它是可选的第三方插件，并非完成后续项目的前提。选择插件前，应检查维护状态、安装说明、权限要求和自己所用模型的兼容情况。

没有统一测试条件，不能仅凭“轻量”名称就断言它比其他插件更快或更稳定。先用一个小任务验证角色是否实际参与、结果是否能合并，再决定是否用于较大的项目。

### 2. `oh-my-opencode-slim.jsonc` 字段说明

在 `~/.config/opencode/oh-my-opencode-slim.jsonc` 中，你可以为不同的使用场景定义多个模型预设（Preset），并为六大专家角色逐一指定模型、技能（Skills）与 MCP 权限。

**不用手写，让 AI 帮你生成即可**：omo-slim 提供官方交互式安装器，会按你订阅的模型套餐自动生成完整的预设配置，只需三步：

```bash
# 1. 运行官方安装器（交互式选择模型供应商，自动生成 oh-my-opencode-slim.jsonc）
bunx oh-my-opencode-slim@latest install

# 2. 登录你订阅的模型套餐（如火山引擎 Agent Plan / MiniMax Coding Plan / 腾讯云 Token Plan / OpenCode Go 等），按提示填入 API Key
opencode auth login

# 3. 拉取该账户下最新可用的模型列表
opencode models --refresh
```

- 配置文件顶部的 `"preset": "openai"` 字段决定**默认激活**哪个预设；
- 会话中想临时切换预设，直接输入 **`/preset <预设名>`** 即可热切换，无需重启 OpenCode。

以下是一个示例：

```json
{
  "$schema": "https://unpkg.com/oh-my-opencode-slim@latest/oh-my-opencode-slim.schema.json",
  // 当前激活的预设名称
  "preset": "openai",
  "presets": {
    "openai": {
      // 1. 统筹角色：负责拆解整体需求、安排任务
      "orchestrator": {
        "model": "deepseek/deepseek-v4-flash",
        "skills": ["*"],                    // 允许使用所有已挂载技能
        "mcps": ["*", "!context7"]          // 挂载所有 MCP 工具，但排除 context7
      },
      // 2. 智囊顾问：攻克疑难算法、架构设计与高难度推导
      "oracle": {
        "model": "deepseek/deepseek-v4-pro",
        "variant": "max",                   // 开启最高思考强度
        "skills": ["simplify"],             // 专门挂载代码精简技能
        "mcps": []
      },
      // 3. 图书管理员：专职查阅文档、全库检索、外部资料搜索
      "librarian": {
        "model": "deepseek/deepseek-v4-flash",
        "skills": [],
        "mcps": ["websearch", "grep_app"]   // 赋予联网搜索与全网代码检索权限
      },
      // 4. 代码探路者：极速扫描项目结构、定位文件与梳理依赖关系
      "explorer": {
        "model": "deepseek/deepseek-v4-flash",
        "skills": [],
        "mcps": []
      },
      // 5. 前端/UI 设计师：负责页面布局、交互设计与样式美化
      "designer": {
        "model": "deepseek/deepseek-v4-flash-vision-exp",
        "variant": "high",
        "skills": ["agent-browser"],        // 挂载浏览器端到端测试技能
        "mcps": []
      },
      // 6. Bug 修复专家：针对编译报错、单测失败精准打补丁
      "fixer": {
        "model": "deepseek/deepseek-deepseek-v4-pro",
        "variant": "high",
        "skills": [],
        "mcps": []
      }
    }
  }
}
```

***

### 3. 六大专家角色协作矩阵与权限分配：

<!-- 图表源文件：img/diagrams/02-diagram-02.mmd；视觉风格：Pastel 多巴胺 -->
<p align="center">
  <a href="img/diagrams/02-diagram-02.svg">
    <img src="img/diagrams/02-diagram-02.svg" alt="3. 六大专家角色协作矩阵与权限分配：" width="760">
  </a>
</p>

#### 技能与 MCP 白黑名单权限控制：

- **`"skills": ["*"]`**：全量授权，智能体可调用已加载的所有 Skills；
- **`"skills": ["simplify"]`**：白名单机制，仅允许使用指定的 `simplify` 技能；
- **`"mcps": ["*", "!context7"]`**：通配符与 `!` 排除语法结合，允许调用除 `context7` 外的所有 MCP，避免特定工具在大上下文中产生冲突或高额计费。

***

## 配置排错与常见问题

1. **修改配置文件后未生效？**
   - 检查 JSONC 语法是否有语法错误（如缺少闭合大括号 `}` 或漏掉逗号 `,`）；
   - 在 OpenCode 桌面端按下 `⌘R` 重载窗口，或重启 OpenCode 进程。
2. **多模型调用频繁报 503 / 504 错误？**
   - 检查 `opencode.jsonc` 中的 `headerTimeout` 是否已调整为 180000 毫秒（3分钟）以上；
   - 若使用中转 API，检查并发上限，在 options 中加入 `"maxConcurrency": 4` 或 `8` 进行削峰限流。
3. **插件加载失败？**
   - 确保系统已安装 Node.js 环境，在终端测试 `npm --version` 是否正常输出。

***

## 配置不生效时，沿着来源查

同一道菜用了两份配方，最后的味道取决于哪些步骤被覆盖。配置文件也可能同时来自全局设置、项目目录和环境变量；看到一个文件写对了，不等于它就是最终生效的值。

[OpenCode 的配置文档](https://opencode.ai/docs/config/)说明，各处配置会合并，冲突字段按优先顺序处理。因此，模型不符合预期时，应记录工作目录、配置来源和运行时选中的模型，再检查同名字段。

建议按“模型可用 → 一个工具可用 → 一份技能可读取 → 插件角色可调用”的顺序增加配置。每一步都单独验证，不要一次加入多个插件后才开始排查。

| 现象 | 首先确认 |
| --- | --- |
| 修改模型后没有变化 | 是否有更高优先级配置或会话选择 |
| MCP 已连接，但调用失败 | 工具参数、运行目录和服务端日志 |
| 技能存在却未使用 | 描述是否匹配任务、路径是否被发现 |
| 角色出现但没有工作 | 是否实际产生子任务和工具调用记录 |

技能说明提供做事方法，MCP 服务提供可调用能力，插件安排额外行为。三者都不能替代验收。多角色任务还会增加调用和沟通成本，只有能清楚分工的任务才值得拆开。

## 按配置来源逐层排查

配置问题可以按“全局配置—项目配置—环境变量—插件或扩展”逐层缩小范围。先在一个最小项目中验证全局模型，再进入目标项目观察是否被覆盖；随后只启用一个 MCP 或一份 Skill，确认调用记录符合预期后再增加下一项。

密钥也要区分保存位置和生效范围。配置文件里引用环境变量，只表示运行时会去读取，并不说明变量已经存在。排查时确认进程能否读取变量即可，不要把密钥值复制到截图、日志或对话中。项目需要共享配置时，只提交变量名和填写说明。

判断能力是否真正生效，要看证据：MCP 应出现具体工具调用及返回值，Skill 应让结果遵守其中的步骤或格式，多角色插件应产生清楚的分工和交付物。仅在列表中显示“已连接”或“已发现”，还不能说明目标任务已经用到了它。

---

## 参考资料

- **OpenCode 学习指南（推荐必读）**：<https://learnopencode.com/>
- **OpenCode 中文网配置文档**：<https://www.opencodecn.com/docs/config>
- **OpenCode 官方网站**：<https://opencode.ai>
- **Oh My OpenCode Slim 代码仓**：<https://github.com/code-any-way/oh-my-opencode-slim>
- **Model Context Protocol (MCP) 官方规范**：<https://modelcontextprotocol.io/>
- **Agent Skills 官方主页**：<https://agentskills.io>
