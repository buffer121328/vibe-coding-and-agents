# 🤖 AGENTS.md —— OpenCode 实战篇智能体协作与项目规则

> **本文件用途**：本文件是专为在 `05_OpenCode实战` 目录下协作开发的 **AI Coding Agent（如 OpenCode、Claude Code、Cursor、Trae 等）** 提供的专属项目级规则与上下文指南。

---

## 🎯 一、章节定位与实战目标 (Chapter Mission)

- **章节名称**：第五章：OpenCode 实战（新一代开源 AI 终端与多智能体意图编排）
- **核心哲学**：**轻量意图流、极致即时反馈、零后端繁杂配置、纯前端现代化动态交互**；
- **多智能体架构**：采用 `oh-my-opencode-slim`（omo-slim）六大专家角色（Orchestrator、Oracle、Librarian、Explorer、Designer、Fixer）进行协同分工；
- **技能库支持**：本地挂载 `.opencode/skills/` 中的 5 大神级技能（`tailwind-ui-master`、`agent-browser`、`single-file-app`、`html5-canvas-artist`、`simplify`）。

---

## 📜 二、智能体必须遵守的开发铁律 (Core Rules)

### 1. 📦 独立单文件与零依赖规范 (Single File & Zero Config)
- 在编写前端交互小工具与 Demo 时，优先采用**自包含单文件（Single File HTML）**架构；
- 通过官方公共 CDN 引入 TailwindCSS、Lucide 图标库、Canvas/音频工具库，严禁强制要求初学者在本地执行繁杂的 `npm install` 或配置复杂的构建流水线；
- 保证用户直接用浏览器双击打开 `.html` 文件即可获得 100% 完整功能！

### 2. 🎨 顶级 UI 审美注入 (Design Standards)
- 严禁生成未经样式美化的粗糙灰白默认 HTML 控件；
- 严格遵循 `tailwind-ui-master` 规范：默认采用深色暗黑模式（Dark Theme）、玻璃拟态（Glassmorphism）、微交互悬浮动效（Transitions/Hover Effects）与精致的排版对比度；
- 移动端与桌面端必须实现 100% 响应式自适应布局。

### 3. 🛡️ 技能分发与角色协同 (Skills & Roles)
- **UI 设计与样式生成**：优先交由 `designer` 专家，并加载 `tailwind-ui-master` 与 `html5-canvas-artist`；
- **代码重构与精简**：优先交由 `oracle` 专家，并加载 `simplify` 技能；
- **全流程验收与排错**：利用 `agent-browser` 与 `fixer` 角色进行自治审查与修复。

### 4. 🛑 纪律红线
- 严禁在未经用户明确授权的情况下执行 `git commit`；
- 示例代码中的 API Key、私有域名和敏感信息必须进行 100% 脱敏处理。
