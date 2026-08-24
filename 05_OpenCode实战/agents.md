# AGENTS.md 

> 规则分工：**开发代码**按本文件执行；**撰写教学文档**（章节 .md、README）按根目录 [agents.md](../agents.md) 执行。
> 项目代码位于 [project_03_个人博客系统](./project_03_个人博客系统/)（uv 管理，Python 3.12）。

## 一、技术栈

- 后端：FastAPI + uvicorn + SQLite（内置，单文件 .db），ORM 用 SQLAlchemy
- 前端：单文件 HTML5 + TailwindCSS（CDN）+ 原生 JS，无 npm/构建链
- 依赖管理：uv（`uv add` / `uv run`），禁止手写 venv/pip

## 二、开发工作流（阶段式：CodeGraph 查询 → OpenSpec 规划 → ATDD 实现）

0. **阶段式推进（先行）**：项目按 [docs/](./project_03_个人博客系统/docs/README.md) 阶段蓝图（phase_01~04）分阶段开发，**一个阶段一个完整闭环**：
   - 动手前先读 `docs/README.md` 确认当前阶段目标；
   - 每阶段严格走：`/opsx-explore` 探索本阶段 → `/opsx-propose` 生成该阶段四件套 → `/opsx-apply` 实现+验收 → `/opsx-sync` / `/opsx-archive` 收尾；
   - 阶段内每个功能仍遵守 ATDD（验收测试先行）；
   - 完成本阶段并勾选对应 `docs/phase_*.md` 核对清单后，才可进入下一阶段；**禁止跳阶段、禁止跨阶段一次性开发**。

1. **查询**：先调用 `mcp_codegraph` 的 `codegraph_explore`（`query` 传符号/文件名/问题，`projectPath` 传项目路径）。命中符号即视为已读，不再重复 Read。禁止盲目全库搜索。
2. **规划**：`/opsx-propose` 生成四件套：`proposal.md`（why）、`specs/*/spec.md`（what，含 WHEN/THEN 验收场景）、`design.md`（how）、`tasks.md`（任务清单）。此阶段**禁止写业务代码**。
3. **ATDD**：先把 specs 中的 Scenario 写成可执行验收测试（后端 `pytest`+TestClient，前端 `agent-browser`），再写实现。顺序：测试红 → 实现绿 → 重构。
4. **实现**：`/opsx-apply` 按 tasks.md 逐条实现，每完成一个任务跑通测试并勾选 `- [x]`。遇「任务不清/设计缺陷/报错」→ 暂停询问，禁止硬猜。
5. **收尾**：需求变更 → `/opsx-update`；完成 → `/opsx-sync` 合并 delta 规格 → `/opsx-archive` 归档（先 `openspec validate`）。

## 三、前端规则

- 单文件 `.html`，公共 CDN 引入 TailwindCSS/Lucide/Canvas，双击即用，禁止 npm install
- 默认深色 + 玻璃拟态（`bg-white/5 backdrop-blur-md border-white/10`）+ 渐变强调色 + 悬浮微交互 + 响应式
- 状态用 localStorage 持久化；动效 CSS transition / Canvas 60fps
- 对接后端统一 `fetch` + `baseURL` 封装；联调失败先查 CORS
- 完成必须用 `agent-browser` 实测（点击/输入/截图/查 console），禁止写完即交付

## 四、后端规则

- RESTful：资源复数名词（`/api/posts`），语义化状态码（200/201/204/400/404/409/500），统一错误格式 `{"detail": "..."}`，Pydantic 校验请求体
- 分层：router → service → repository
- CORS：`CORSMiddleware` 显式允许前端来源
- 测试先行：每接口先写 `pytest` + TestClient 验收测试（正常/异常/边界），`pytest -q` 全绿才交付
- 安全：API Key/密钥/私有域名 100% 脱敏；`*.db` 等产物加入 `.gitignore`

## 五、Skills 按需加载（`.opencode/skills/<名>/SKILL.md`）

先看下表决定加载哪些技能，再读对应 SKILL.md 执行，不无脑全读：

| 技能 | 用途 | 触发场景 |
|---|---|---|
| tailwind-ui-master | UI 规范（暗黑/玻璃拟态/微交互） | 前端样式 |
| single-file-app | 单文件 HTML 骨架 | 小工具/Demo |
| html5-canvas-artist | Canvas 动效 / Web Audio / 高清导出 | 动效音效 |
| agent-browser | 浏览器自测 | 前端验收 |
| simplify | 代码精简/去死代码 | 重构 |
| openspec-explore | 只读探索 | `/opsx-explore` |
| openspec-propose | 生成规划四件套 | `/opsx-propose` |
| openspec-update-change | 修订规划制品 | `/opsx-update` |
| openspec-apply-change | 逐任务实现 | `/opsx-apply` |
| openspec-sync-specs | delta 规格合并主规格 | `/opsx-sync` |
| openspec-archive-change | 变更归档 | `/opsx-archive` |

## 六、角色协同（omo-slim）

- UI 设计/样式 → `designer`（tailwind-ui-master + html5-canvas-artist）
- 重构/精简 → `oracle`（simplify）
- 验收/排错 → `agent-browser` + `fixer`
- 规格/验收测试 → 按第二节流程，`orchestrator` 统筹

## 七、纪律红线

- 禁止未经用户明确授权执行 `git commit`
- 禁止虚构官方链接与技术细节
- propose 阶段禁止写业务代码；explore 阶段只读不写
- 验收测试必须真实跑通（pytest / agent-browser），禁止假装通过
