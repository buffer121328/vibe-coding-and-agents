## 1. 依赖与配置

- [x] 1.1 `uv add openai python-dotenv`
- [x] 1.2 新增 `.env.example`（LLM_API_KEY / LLM_BASE_URL / LLM_MODEL），确认 `.gitignore` 含 `.env`

## 2. 数据模型

- [x] 2.1 `models.py` 为 `Post` 增加 `summary` 列（Text，默认空串）
- [x] 2.2 对既有 `blog.db` 执行 `ALTER TABLE posts ADD COLUMN summary TEXT DEFAULT ''`（新库自动建列）

## 3. AI 服务模块

- [x] 3.1 新增 `ai_service.py`：环境变量动态读取、`ai_enabled()`、`get_client()`、`provider_name()`
- [x] 3.2 `_chat_json`：强制 `response_format=json_object` + `json.loads` 解析兜底
- [x] 3.3 `generate_all(title, content, category)`：一次性产出 摘要/标签/标题/分类

## 4. Schema DTO

- [x] 4.1 `PostCreate` / `PostUpdate` / `PostResponse` 增加 `summary`（默认空串/可选）
- [x] 4.2 新增 `AIGenerateRequest` / `AIGenerateResponse` / `AIStatusResponse` / `BackfillResponse`

## 5. 测试（ATDD）

- [x] 5.1 `setup_db` autouse 增加 `monkeypatch.delenv("LLM_API_KEY")` 保证默认 AI 禁用、既有用例隔离
- [x] 5.2 新增 `_enable_ai` 辅助：setenv + stub `ai_service._chat_json` 返回确定性 JSON
- [x] 5.3 状态用例：有 key `enabled=true` / 无 key `enabled=false`
- [x] 5.4 generate 用例：admin 200 四件套 / 未登录 401 / reader 403 / 缺字段 422 / 无 key 503 / LLM 失败 502
- [x] 5.5 发布自动生成用例：空 summary 发布后后台补齐摘要与标签；人工预填不覆盖；无 key 优雅降级；更新触发补齐
- [x] 5.6 回填用例：只处理无摘要文章 / limit 截断 / 幂等 / 无 key 503 / 未登录 401
- [x] 5.7 运行 `uv run pytest -q`：既有 71 + 新增 17 = 88 全绿

## 6. 后端接口实现

- [x] 6.1 `main.py` 顶部 `load_dotenv()`
- [x] 6.2 `_post_response` 携带 `summary`；`create_post` / `update_post` 挂 `_maybe_auto_enrich` 后台任务
- [x] 6.3 `_auto_enrich_post`：自行开 Session，按字段独立回填，try/except 仅记日志
- [x] 6.4 `GET /api/ai/status`（公开）
- [x] 6.5 `POST /api/ai/generate`（仅 admin，无 key 503，失败 502）
- [x] 6.6 `POST /api/ai/backfill`（仅 admin，limit 1~200，幂等，失败计数）
- [x] 6.7 `uv run pytest -q` 全绿

## 7. 前端改造

- [x] 7.1 编辑器新增「导读摘要」输入框 `editorSummary`（发布/保存/编辑回填）
- [x] 7.2 编辑器新增「AI 灵感副驾」面板：`GET /api/ai/status` 探测显隐、一键生成填充摘要/标签、标题/分类建议条一键采用
- [x] 7.3 文章卡片优先展示 `summary` 导读（无导读回退正文截取）；阅读器顶部导读条（escapeHtml）
- [x] 7.4 admin 导航「AI 回填」按钮（`aiEnabled && isAdmin()` 显隐）→ `POST /api/ai/backfill` → Toast 结果
- [x] 7.5 保持玻璃拟态风格，无 JS 报错

## 8. 联调验收

- [x] 8.1 启动服务实测：无 key 时 status=false / generate/backfill 503 / 发布正常（优雅降级）
- [x] 8.2 配 key 实测：status=true / generate 真实打到上游（无效 key 返回 502 优雅报错）/ 回填 200 逐篇失败计数 / 发布后台生成失败仅记日志不崩
- [x] 8.3 浏览器实测：登录 admin 见「AI 回填」、编辑器 AI 面板与摘要框、一键生成按钮交互、无 JS 报错

## 9. 文档与归档

- [x] 9.1 更新 `agents.md`、`.trae/rules/backend.md`、`.trae/rules/frontend.md`、`.traerules`、项目 `README.md`、`docs/phase07_AI智能摘要提炼与自动打标.md`
- [x] 9.2 `openspec validate` + `openspec sync` + `openspec archive` 归档阶段七
