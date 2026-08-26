# 通用规则（Common Rules：CodeGraph + OpenSpec + uv）

> 适用：`project_01_个人博客系统二次开发/` 全链路二次开发通用流程。

## ✅ 遵循规范（Do）

- **CodeGraph 查询先行**：动手改代码前先调用 `mcp_codegraph` 的 `codegraph_explore`（`query` 传符号/文件名/问题，`projectPath` 传项目绝对路径）；命中符号即视为已读；大型重构前先建立图谱索引；
- **OpenSpec 规格驱动**：按阶段开发，一个阶段一个完整闭环：`/opsx-explore` 探索 → `/opsx-propose` 生成四件套（proposal / spec / design / tasks）→ `/opsx-apply` 实现+验收 → `/opsx-sync` 合并 delta 规格 → `/opsx-archive` 归档（先 `openspec validate`）；
- **文档同步**：每个阶段开发完成后，同步更新 agents.md 与 `.trae/rules/`（frontend / backend / general，含项目目录、文件清单与红线）——每个阶段开始前都是站在已开发好的基础上推进；
- **uv 管理依赖**：`uv sync` / `uv run uvicorn main:app --reload --port 8000` / `uv run pytest -q` / `uv add <pkg>`；
- **Trae 工作流**：利用可视 Diff 审查与单文件精准撤销；复杂调试与自动化测试阶段可切换 Solo 模式自主闭环。

## 🚫 红线禁令（Don't）

- 禁止跳阶段、跨阶段一次性混杂开发；
- 禁止手写 pip / venv 管理依赖；
- 禁止混淆 `reference/` 已验收资产与当前 `openspec/specs` 新迭代规格；
- 禁止盲目全库搜索与重复 Read；
- 禁止在 propose / 规划阶段写业务代码，explore 阶段只读不写。
