# 3.7 中转上游与代理配置：以 Codex / CC-Switch 为例

> 中转上游就像一个“超高速跨国中转快递站”，国内直接连海外大模型容易网络卡顿或超时，通过中转网关转发，不仅速度飞快，还能用 **CC-Switch** 这样的神器一键在几十个不同的大模型之间随心切换！

***

## 🌐 为什么需要中转上游与代理？（国际中转仓比喻）

在实际使用 OpenAI Codex、Claude Code 或本地 Agent 时，许多开发者会遇到 `Connection Timeout (连接超时)` 或 `SSL Error` 报错。或者有的同学不会挂梯子，没有visa实体卡无法购买订阅。

<!-- 图表源文件：img/diagrams/07-diagram-01.mmd；视觉风格：Notion 简洁 -->
<p align="center">
  <a href="img/diagrams/07-diagram-01.svg">
    <img src="img/diagrams/07-diagram-01.svg" alt="🌐 为什么需要中转上游与代理？（国际中转仓比喻）" width="960">
  </a>
</p>

***

## 🎛️ 终极利器：CC-swtich统一中转与多模型管理神器

**CC-Switch** 是一款专为 AI 命令行与 Agent 开发者打造的跨平台桌面工具，彻底终结了“每次换模型都要手动改一大堆代码和配置文件”的折磨！这个后面也会带大家进行使用！

<!-- 图表源文件：img/diagrams/07-diagram-02.mmd；视觉风格：Notion 简洁 -->
<p align="center">
  <a href="img/diagrams/07-diagram-02.svg">
    <img src="img/diagrams/07-diagram-02.svg" alt="🎛️ 终极利器：CC-swtich统一中转与多模型管理神器" width="760">
  </a>
</p>

### CC-Switch 的三大杀手锏

1. **一键切换 50+ 供应商**：在图形界面上点一下，即可在 DeepSeek、OpenAI、Claude、SiliconFlow、OpenRouter 之间秒级切换；
2. **本地集中代理端口（`http://127.0.0.1:15721`）**：你的所有 Agent 工具只需将 `base_url` 指向这个本地端口，底层到底走哪个模型、用哪个 Key，全部在 CC-Switch 里鼠标点击搞定；
3. **MCP 统一管理中心**：无需在每个工具的 json 文件里重复复制粘贴 MCP 配置，在一个地方集中启用与停用。

***

## 📝 配置文件实战：以 Codex（.codex 配置）为例

如果你使用的是 OpenAI Codex、OpenCode 或兼容 OpenAI 接口的命令行 Agent，可以通过修改配置文件或设置环境变量来接入中转网关。下面是两个简单的式例，不等于最终的配置。

### 方式 A：通过本地配置文件 `.codex` 或 `config.toml`

在项目根目录或用户主目录下创建 `.codex` 配置文件：

```toml
# .codex 配置文件示例

[model]
# 指定使用的模型名称
name = "gpt-5.6"
# 也可以配置为 deepseek-reasoner 或 claude-3-7-sonnet

[api]
# 配置中转上游接口地址 (以中转服务商或本地 CC-Switch 为例)
base_url = "http://127.0.0.1:15721/v1"
# 或者填写服务商提供的中转地址：base_url = "https://api.your-relay-service.com/v1"

# 填入对应的 API Key
api_key = "sk-your-relay-api-key-here"

[options]
temperature = 0.2
timeout = 60
```

***

### 方式 B：通过终端全局环境变量一键生效

在终端命令行中直接设置环境变量（可以写入你的 `~/.zshrc` 或 `~/.bashrc` 文件永久生效）：

```bash
# 1. 设置中转上游的基础 URL 地址
export OPENAI_BASE_URL="http://127.0.0.1:15721/v1"

# 2. 设置对应的 API Key
export OPENAI_API_KEY="sk-your-relay-api-key-here"

# 3. 运行你的 Agent 工具（如 codex 或 opencode），所有请求将自动秒级走中转网关！
codex
```

***

## 🔧 常见网络排错排查指南

| 报错现象                                | 根本原因                   | 快速化解方案                                              |
| :---------------------------------- | :--------------------- | :-------------------------------------------------- |
| **`Connection Refused`**            | 本地代理软件或 CC-Switch 没有启动 | 检查 CC-Switch 是否正在运行，确认本地端口号是否为 `15721`              |
| **`401 Unauthorized`**              | API Key 填错、已过期或账户余额不足  | 登录供应商控制台核对 Key 是否完整复制，检查账户是否有可用余额                   |
| **`SSL Certificate Verify Failed`** | 本地开启了全局抓包软件导致证书拦截      | 在工具配置中暂时开启 `insecure_skip_verify = true` 或关闭多余的抓包软件 |

