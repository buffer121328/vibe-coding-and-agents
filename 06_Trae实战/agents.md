# AGENTS.md (Trae 专属规则与协作指南)

> **规则分工**：在 Trae 中进行**代码开发与重构**时严格按本文件及 `.traerules` 执行；**撰写教学文档**（章节 .md、README）按根目录 [agents.md](../agents.md) 执行。
> 本章节实战代码位于 [project_01_个人博客系统二次开发/](./project_01_个人博客系统二次开发/)（使用 `uv` 极速包管理，Python 3.12+）。

---

## 一、技术栈与运行环境

- **后端架构**：FastAPI + uvicorn + 原生 SQLite（`blog.db`），ORM 采用 SQLAlchemy 2.0+（Mapped 语法），数据校验使用 Pydantic V2。
- **前端架构**：单文件 HTML5 + TailwindCSS（CDN 引入）+ Marked.js + 原生现代 JS，零 npm 构建链，双击/静态服务即跑。
- **依赖管理**：坚决使用 `uv`（`uv sync` / `uv run uvicorn main:app --reload` / `uv add <pkg>`），严禁手动操作混乱的 pip/venv。
- **AI 赋能**：集成轻量高效 LLM API，实现自动摘要提炼与智能标签提取。

---

## 二、Trae 开发工作流（CodeGraph 索引 ➔ OpenSpec 阶段规划 ➔ Trae Code / Solo 闭环）

1. **项目上下文与图谱索引（CodeGraph）**：
   - 首次导入项目或进行大型重构前，使用 `CodeGraph` 建立代码语义图谱与符号索引，确保 AI 能够全局掌控路由、模型与接口依赖关系。
2. **阶段式递进开发（Phase 驱动）**：
   - 项目严禁一次性跨阶段混杂开发，必须按以下三大阶段逐步迭代：
     - **Phase 1**：用户注册、登录与 JWT 权限隔离系统；
     - **Phase 2**：评论楼层与点赞互动系统 + 后端分页重构；
     - **Phase 3**：AI 智能摘要提炼 + 智能打标赋能。
3. **ATDD 验收测试先行**：
   - 每一个新接口先编写 `pytest` 测试用例（正常/异常/未授权状态码），确认测试红灯后再进行业务编码，直到 `uv run pytest -q` 全绿交付。
4. **Trae Code 精细审查与单文件精准回滚**：
   - 充分利用 Trae Code 编译器的可视 Diff 审查机制，遇到不符合预期的局部改动直接在编辑器中单独撤销，保持工程干净整洁。
5. **Solo 模式自主闭环**：
   - 在复杂调试与自动化测试阶段，可切换至 Solo 模式，让 AI 自主执行任务清单、分析终端报错、自省修复直到闭环。

---

## 三、编码与安全纪律红线

- 🛑 **严禁私自提交**：未经用户明确指令，绝不擅自执行 `git commit`；
- 🛡️ **安全隔离**：用户密码必须使用安全的哈希算法（如 passlib/bcrypt），严禁明文存储；所有鉴权接口严格校验 JWT Token；
- 🧪 **真实验证**：所有接口与功能必须经 `pytest` 跑通测试，禁止跳过验证伪造测试结果。
