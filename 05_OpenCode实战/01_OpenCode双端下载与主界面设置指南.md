# 5.1 OpenCode 双端下载与主界面设置指南

> **本节导读**：工欲善其事，必先利其器！OpenCode 作为当前最火热的开源 AI 编程智能体平台，同时提供了**轻功水上漂的极速终端 CLI 版**与**直观优雅的图形化桌面 Desktop 版**。本节将带你完成双端全平台安装，逐一拆解主界面功能分区，并手把手带你调优通用设置与模型提供商接入！

***

## 💡 一、生活化大比喻：什么是 OpenCode 的双端体验？

如果把传统的编程比作“在工地上徒手搬砖”，那么使用 OpenCode 就相当于给你配备了一套**高科技外骨骼装甲与智能副驾**：

- 🖥️ **OpenCode CLI（终端命令行版）**：就像是**特种兵随身携带的战术多功能瑞士军刀**。无需打开庞大的窗口，在任何终端或远程服务器里敲一行命令，就能让 AI 像闪电一样快速检索代码、定位 Bug、批量修改文件并自动运行测试；
- 🖼️ **OpenCode Desktop（桌面图形化客户端）**：就像是**现代飞机的全景玻璃驾驶舱**。所有会话历史、项目工作区、代码实时变动（Diff 对比）、AI 思考推理链和终端沙箱执行一目了然，特别适合需要精细审查代码和享受视觉心流的开发者！

最爽的是，**CLI 版与 Desktop 版共享完全相同的底层架构与全局配置文件（`~/.config/opencode/`）**！你在桌面端配置好的模型和密钥，在命令行终端里敲回车就能直接复用，真正做到“双端合一，无缝切换”。

```mermaid
graph TD
    subgraph Core ["OpenCode 统一底层核心 (OpenCode Core)"]
        Config["全局配置文件<br/>(~/.config/opencode/opencode.jsonc)"]
        Engine["智能体调度引擎 & 沙箱执行器"]
        Router["多模型中转路由 & MCP/Skills 外挂"]
    end

    subgraph Client ["双端协同交互形态"]
        CLI["OpenCode CLI<br/>(命令行极速黑客模式 / 远程 SSH 友好)"]
        Desktop["OpenCode Desktop<br/>(图形化驾驶舱 / 可视化 Diff / 沉浸式交互)"]
    end

    Config --> Engine
    Router --> Engine
    Engine --> CLI
    Engine --> Desktop
```

***

## 📥 二、全平台双端下载与安装指南

### 1. 终端命令行版（CLI）极速安装

OpenCode CLI 支持全平台一键安装，你可以根据自己的操作系统选择最便捷的方式：

#### 🍏 macOS & Linux

你可以使用官方一键脚本或 Node.js 全局包管理器安装：

```bash
# 方式一：官方一键 Shell 脚本安装（推荐）
curl -fsSL https://opencode.ai/install.sh | bash

# 方式二：使用 Homebrew 安装 (macOS)
brew install sst/tap/opencode

# 方式三：使用 npm / pnpm 全局安装
npm install -g opencode-ai
# 或者
pnpm add -g opencode-ai
```

#### 🪟 Windows

Windows 用户可以在 PowerShell（建议以管理员身份打开）中运行：

```powershell
# 方式一：官方 PowerShell 一键安装
irm https://opencode.ai/install.ps1 | iex

# 方式二：使用 npm 全局安装
npm install -g opencode-ai

# 方式三：使用 Scoop 包管理器
scoop bucket add opencode https://github.com/sst/opencode-scoop.git
scoop install opencode
```

#### ✅ 验证 CLI 安装

在终端输入以下命令，输出版本号即代表安装成功：

```bash
opencode --version
# 输出示例: opencode v1.18.x
```

在任何项目目录下输入 `opencode`，即可直接唤醒终端交互式智能体！

***

### 2. 桌面图形化版（Desktop）下载与安装

OpenCode Desktop 提供了开箱即用的跨平台安装包，教程也主要采用desktop版本：

- **官方下载中心**：<https://opencode.ai/download>
- **学习社区镜像与指南**：<https://learnopencode.com/>

| 操作系统        | 安装包格式                | 适用架构                                      | 安装与配置注意事项                                                                    |
| :---------- | :------------------- | :---------------------------------------- | :--------------------------------------------------------------------------- |
| **macOS**   | `.dmg`               | Apple Silicon (M1/M2/M3/M4) / Intel (x64) | 下载后拖拽至 `Applications`；首次打开如遇安全提示，在“系统设置 ⮕ 隐私与安全性”中点击“仍要打开”。                  |
| **Windows** | `.exe` / `.msi`      | x64 / ARM64                               | 双击安装向导，一路点击“下一步”即可完成安装并自动创建桌面快捷方式。                                           |
| **Linux**   | `.AppImage` / `.deb` | x64 / ARM64                               | Ubuntu/Debian 可执行 `sudo dpkg -i opencode-desktop.deb`；AppImage 赋予执行权限即可直接运行。 |

***

## 🖥️ 三、OpenCode Desktop 主界面全景拆解

首次启动 OpenCode Desktop 时，你将看到一个极简、清爽且专注于代码创造的现代化界面：

![OpenCode Desktop 主界面](./img/opencode_main_interface.png)

### 🔍 主界面核心功能分区：

1. **左上角新建与控制区**：
   - 🔴🟡🟢 **窗口控制红黄绿灯**（macOS 原生风格）；
   - 📑 **侧边栏与分栏切换按钮**：快速收起或展开左侧会话面板，最大化代码与对话可视区域；
   - ➕ **新建会话按钮（`+`）**：随时开启一段全新上下文的 AI 协作任务，避免历史对话过长导致注意力漂移。
2. **中间主工作区（项目加载区）**：
   - 📂 **“打开项目”按钮（Open Project）**：点击后选择你本地的工程文件夹（如 Git 仓库目录）。OpenCode 会自动建立本地文件树索引并加载环境配置。
3. **左下角配置与支持区**：
   - ⚙️ **设置齿轮图标（快捷键** **`⌘,`** **/** **`Ctrl+,`）**：进入系统级控制中枢（包含通用偏好、快捷键定义、模型提供商与服务器连接）；
   - ❓ **帮助与文档图标**：一键直达官方文档与社区支持通道。

***

## ⚙️ 四、设置中心手把手深度调优

点击左下角设置图标（或按下快捷键 `⌘,`），进入 OpenCode 设置面板。这里分为**通用偏好**与**提供商/模型连接**两大核心板块：

### 1. 通用设置（General Settings）

![OpenCode 通用设置](./img/opencode_settings_general.png)

#### 📝 核心配置项逐项解析：

| 设置项                           | 推荐状态           | 功能说明与生活化比喻                                                                                                                    |
| :---------------------------- | :------------- | :---------------------------------------------------------------------------------------------------------------------------- |
| **新布局 (New Layout)**          | 🔘 按需开启        | 开启后启用最新的标签页和主页分栏布局，适合喜欢在多文件和多任务间快速跳转的用户。                                                                                      |
| **语言 (Language)**             | 🇨🇳 **简体中文**  | 一键切换全中文界面，降低视觉疲劳与认知门槛。                                                                                                        |
| **自动接受权限 (Auto-approve)**     | ⚠️ **熟练后开启**   | **安全与效率的权衡**：开启后，AI 执行读写文件、运行 Shell 命令将不再弹窗等待你点击确认。- **小白期**：建议**关闭**（人工复核，看清 AI 想干嘛）；- **老手/信任沙箱期**：建议**开启**（彻底解放双手，享受丝滑心流）。 |
| **终端 Shell (Terminal Shell)** | 💻 **自动 (默认)** | 自动识别你当前系统的主 Shell（macOS 默认为 `zsh`，Linux 为 `bash`，Windows 为 `powershell`），作为智能体调用系统工具的基础底座。                                    |
| **显示推理摘要 (Reasoning)**        | ✅ **强烈建议开启**   | **透视 AI 的内心戏！** 针对具备思考能力的大模型（如 DeepSeek-R1、o1/o3、Claude 3.7 Extended Thinking），在时间线中完整展开其思维链（Chain of Thought），让你看清 AI 的推理逻辑。 |
| **展开 Shell 工具调用**             | ✅ **推荐开启**     | 默认在时间线中展开 AI 敲终端命令的完整细节与标准输出，避免黑盒盲盒操作。                                                                                        |
| **展开编辑工具调用**                  | ✅ **推荐开启**     | 默认在时间线中展开 `edit`、`write` 和 `patch` 等文件修改操作详情，方便随时肉眼 Review。                                                                   |

***

### 2. 提供商与模型接入（Providers & Models）

![OpenCode 提供商设置](./img/opencode_settings_providers.png)

OpenCode 拥有极度开放的模型生态，支持主流官方模型、订阅型服务与第三方中转网关：

#### 🌐 支持的常见模型类型：

1. **已连接的提供商（Connected Providers）**：
   - **DeepSeek**：性价比极高、推理与代码内功深厚的国产之光，支持通过官方 API 或硅基流动等中转极速接入；
   - **OpenAI**：这里显示自定义是因为用的中转；
   - **GitHub Copilot**：如果你拥有 Copilot 订阅，可以直接复用其模型通道；
2. **热门官方直连提供商（Featured Providers）**：
   - **OpenCode Zen / OpenCode Go**：官方推荐的即用型订阅与精选模型池（涵盖 Claude、GPT、Gemini 等），opencode go的套餐非常划算，是目前性价比最高的套餐之一；
   - **Anthropic**：Claude  系列，代码审美与架构能力天花板；
   - **Google**：Gemini 系列，拥有百万级超长上下文窗口；
3. **自定义提供商（Custom Provider）**：
   - 支持填写任意兼容 OpenAI 规范的第三方 Base URL 与 API Key，无论是本地部署的 Ollama / vLLM，还是公司内部的私有网关，都能一键接入！

***

## ⌨️ 五、高频快捷键与极速工作流

熟练掌握快捷键是开启“Vibe”的关键法宝：

| 快捷键 (macOS)             | 快捷键 (Windows/Linux) | 动作说明                 |
| :---------------------- | :------------------ | :------------------- |
| `⌘ ,`                   | `Ctrl + ,`          | 打开系统设置面板             |
| `⌘ N`                   | `Ctrl + N`          | 快速新建会话窗口             |
| `⌘ P`                   | `Ctrl + P`          | 快速文件模糊搜索与定位          |
| `⌘ K`                   | `Ctrl + K`          | 选中文本唤醒行内 AI 意图修改     |
| `⌘ B`                   | `Ctrl + B`          | 展开 / 折叠侧边栏           |
| `⌘ ↵` (Command + Enter) | `Ctrl + Enter`      | 发送当前指令并触发 Agent 自治执行 |

***

## 🔗 六、官方权威与拓展学习链接

- **OpenCode 官方主页**：<https://opencode.ai>
- **OpenCode 学习指南（推荐必读教程）**：<https://learnopencode.com/>
- **OpenCode 中文网配置文档**：<https://www.opencodecn.com/docs/config>
- **OpenCode 官方 GitHub 仓库**：<https://github.com/sst/opencode>

