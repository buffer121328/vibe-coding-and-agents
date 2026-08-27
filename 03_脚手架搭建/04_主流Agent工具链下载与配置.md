# 3.4 主流 Agent 工具

> 有了前几节准备好的 Python 环境与 API Key，现在是时候给你的数字工位装上最趁手的“神兵利器”了！本节介绍 Trae、Claude Code CLI、Cursor 与 Cline！后面也会给大家带来opencode、trae和codex的实战！

***

## 🛠️ 主流 Agent 工具链四大门派盘点

<!-- 图表源文件：img/diagrams/04-diagram-01.mmd；视觉风格：Vercel 黑白 -->
<p align="center">
  <a href="img/diagrams/04-diagram-01.svg">
    <img src="img/diagrams/04-diagram-01.svg" alt="🛠️ 主流 Agent 工具链四大门派盘点" width="760">
  </a>
</p>

***

## 🚀 核心工具下载与配置保姆级教程

### 1. [Trae](https://www.trae.ai) —— 字节跳动出品的免费自适应 AI IDE

- **官网下载**: <https://www.trae.ai>
- **核心特色**：国内直连极速，无需配置复杂的 API 密钥，直接免费内置顶尖大模型；
- **极速上手**：
  1. 下载安装后打开项目文件夹；
  2. 点击右上角的 **“Builder”** 模式图标；
  3. 输入自然语言需求：“为当前项目搭建一个简单的用户登录页面”，Agent 会自动拆解任务、多文件生成并实时预览！

***

### 2. [Claude Code (Anthropic 官方 CLI)](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code) —— 终端自主智能体

- **官方文档**: <https://docs.anthropic.com/en/docs/agents-and-tools/claude-code>
- **安装前置要求**：电脑已安装 Node.js (v18+)；
- **一键安装与启动命令**：

```bash
# 1. 使用 npm 全局安装 Claude Code CLI
npm install -g @anthropic-ai/claude-code

# 2. 进入你的项目文件夹并启动 Claude Code
cd /Users/cheng/Desktop/vibe_coding
claude

# 3. 首次启动时，终端会弹出一个网页授权链接，登录 Anthropic 账号即可完成认证！
```

***

### 3. [Cursor](https://www.cursor.com) —— 全球最主流的 AI-First IDE

- **官网下载**: <https://www.cursor.com>
- **关键配置技巧**：
  1. **开启 Codebase 向量索引**：进入 `Settings` ➔ `Features` ➔ `Codebase Indexing`，确保项目索引状态为已完成，这样 AI 就能秒级检索整个项目的所有函数；
  2. **唤醒 Composer Agent 模式**：按下快捷键 `Cmd + I`（Windows 为 `Ctrl + I`），切换为 **Agent 模式**，直接下达跨文件重构指令。

***

### 4. [Cline (VS Code 扩展插件)](https://github.com/cline/cline)

- **安装方式**：在 VS Code 插件市场搜索 `Cline` 点击安装；
- **配置自定义 API**：
  1. 打开 Cline 侧边栏，点击右上角 ⚙️ 设置齿轮；
  2. 在 **API Provider** 中选择 `DeepSeek` 或 `OpenAI Compatible`；
  3. 填入你的 `API Key` 与 `Base URL`；
  4. 点击保存，即可在 VS Code 侧边栏拥有一个完全自主操控终端与文件的开源 Agent！

***

## 📊 主流 Agent 工具横向选型建议

| 工具名称            | 上手门槛             | 硬件与网络要求                | 最佳适用场景                   |
| :-------------- | :--------------- | :--------------------- | :----------------------- |
| **Trae**        | 🟢 极低 (点开就用)     | 国内直连顺畅，免配置 API         | 新手入门、快速体验 AI 辅助建站        |
| **Cursor**      | 🟢 低 (类 VS Code) | 需账号订阅或自带 Key           | 日常全天候主力写代码、重构中大型项目       |
| **Claude Code** | 🟡 中等 (命令行操作)    | 需 Anthropic API / 海外网络 | 终端重度用户、自动化批量任务、服务器无桌面环境  |
| **Cline**       | 🟡 中等 (需配置 Key)  | 支持本地 Ollama / 私有模型     | 追求隐私合规、重度使用自定义 MCP 插件的极客 |

