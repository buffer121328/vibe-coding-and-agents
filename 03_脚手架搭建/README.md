# 🛠️ 第三章：脚手架搭建 —— 从内功修炼到 Agent 工具链实战

欢迎来到 **《Vibe Coding 极速通关》第三章：脚手架搭建**！

在第一章《发展之路》和第二章《概念扫盲》中，我们建立了宏观视野并扫清了所有底层概念。现在，我们正式进入**动手前的脚手架搭建**阶段！

工欲善其事，必先利其器。本章将带你打造一套坚不可摧的现代化 AI 辅助开发工作流：从 Python 核心语法内功、API Key 申请与安全防泄露、IDE 黄金配置，到 Agent 工具链（Trae/Claude Code/Codex）、Spec 规范驱动开发（OpenSpec/Qoder）、Hooks/MCP/Skills 配置，以及中转上游（CC-Switch）的实战调优！

---

## 🧭 第三章全景知识图谱

```mermaid
graph TD
    subgraph Step1 ["第一步：修炼核心内功 (严防 YES 工程师)"]
        A1["01 Python 编程核心内功<br/>(拒绝盲目点接受 / 核心语法 / 免费名校教程)"]
        A2["02 API Key 原理申请与安全防泄露<br/>(VIP 门禁卡 / 供应商平台 / .env 铁律)"]
    end

    subgraph Step2 ["第二步：打造现代化开发工位"]
        B1["03 IDE 环境配置：VS Code 与 PyCharm<br/>(插件天梯榜 / 虚拟环境 venv 与 uv)"]
        B2["04 主流 Agent 工具链下载与配置<br/>(Trae / Claude Code / Codex / OpenCode)"]
    end

    subgraph Step3 ["第三步：规范驱动与进阶外挂"]
        C1["05 Spec 驱动开发与 OpenSpec 实战<br/>(终结 AI 瞎猜 / OpenSpec 规范 / Qoder 编译器)"]
        C2["06 Hooks 机制、MCP 与 Skills 配置<br/>(自动化拦截门禁 / MCP.json / 技能大市场)"]
        C3["07 中转上游与代理配置：以 Codex 为例<br/>(CC-Switch 工具 / .codex 配置 / 极速网关)"]
    end

    subgraph Step4 ["第四步：调兵遣将心法"]
        D1["08 如何选择 AI：主流大模型全景评测<br/>(6大业务场景 / 国内外全家桶 / 黄金组合矩阵)"]
    end

    Step1 --> Step2
    Step2 --> Step3
    Step3 --> Step4
```

---

## 📑 章节目录导航

点击下方链接逐一阅读各小节的保姆级实操指南与官方链接：

1. **[3.1 Python 编程核心内功：告别“YES 工程师”，打牢第一性原理语法](./01_Python编程核心内功.md)**
   - 没有内功是万万不能的！变量、字典、函数、try-except 极速过，附官方文档与菜鸟教程等免费宝库。

2. **[3.2 API Key 原理、主流申请与安全防泄露指南](./02_APIKey原理申请与安全防泄露.md)**
   - 什么是 VIP 门禁卡？OpenAI/Anthropic/DeepSeek/硅基流动申请步骤，`.env` 防盗号核心铁律。

3. **[3.3 IDE 黄金开发环境配置：VS Code 与 PyCharm](./03_IDE开发环境配置_VSCode与PyCharm.md)**
   - 必备插件天梯榜（Pylance/Error Lens/GitLens）、虚拟环境（venv/uv/conda）极速初始化。

4. **[3.4 主流 Agent 工具链下载与实战配置](./04_主流Agent工具链下载与配置.md)**
   - Trae、Claude Code CLI、OpenCode、Codex 等新一代智能体的安装与调优。

5. **[3.5 Spec 驱动开发与 OpenSpec 实战：终结 AI 的瞎编乱猜](./05_Spec驱动开发与OpenSpec实战.md)**
   - 什么是 Spec-Driven Development？主推 OpenSpec 开源规范，以及 Spec 驱动 Agent 编译器 Qoder 实战。

6. **[3.6 Hooks 机制、MCP 万能插件与 Skills 技能配置](./06_Hooks机制_MCP与Skills配置.md)**
   - 先搞懂什么是 Hooks 门禁挂钩，手把手在编辑器中配置 `mcp.json` 与挂载 Agent Skills 技能包。

7. **[3.7 中转上游与代理配置：以 Codex / CC-Switch 为例](./07_中转上游与代理配置_以Codex为例.md)**
   - 国内网络加速方案，使用 CC-Switch 一键管理多供应商与 MCP，`.codex` 配置文件详解。

8. **[3.8 如何选择 AI：主流大模型全景评测与多场景选型指南](./08_如何选择AI.md)**
   - 不迷信单点屠榜！覆盖编程、工作、创作、办公、对话与 Agent 6 大场景，深度评测 DeepSeek、GLM、Kimi、Qwen、MIMO、MiniMax、豆包、GPT、Claude、Gemini、Grok 并奉上实战黄金组合。
