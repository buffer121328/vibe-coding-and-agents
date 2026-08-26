# 后端规则（Backend Rules）

> 适用：`project_01_个人博客系统二次开发/` FastAPI + uvicorn + SQLite（`blog.db`）+ SQLAlchemy 2.0（Mapped 语法）+ Pydantic V2，依赖一律 `uv` 管理。

## ✅ 遵循规范（Do）

- 分层清晰：`models.py`（ORM 表模型：User / Post / Comment / Like）/ `schemas.py`（Pydantic DTO）/ `database.py`（引擎与 `get_db`）/ `security.py`（bcrypt 哈希、JWT 编解码、`get_current_user` / `get_optional_user` / `require_admin` 守卫）/ `ai_service.py`（OpenAI 兼容客户端与生成能力）/ `main.py`（路由、鉴权守卫挂载、静态托管、CORS）；
- RESTful：资源复数名词（`/api/posts`、`/api/auth`、`/api/users`、`/api/comments`、`/api/ai`），语义化状态码，统一错误格式 `{"detail": "..."}`，Pydantic 校验请求体；
- 列表接口参数化分页（`Page` & `PageSize`），返回 `{items, total, page, page_size}` 元信息；`page≥1`、`1≤page_size≤50`，非法参数 422；
- 安全：密码一律 bcrypt 哈希存储；JWT（HS256）颁发与验证闭环；受保护接口（文章增删改、用户管理、AI 生成与回填）用 `Depends(security.require_admin)` 守卫校验 Token，未登录 401 / 非 admin 403；
- 认证接口契约：`POST /api/auth/login`（公开，颁发 Token）、`GET /api/auth/me`（登录态）、`POST /api/users` / `GET /api/users`（仅 admin，不开放公开注册）；`seed_admin` 在 lifespan 建表后与测试 setup 中调用，保证始终有可登录管理员；
- 评论接口契约：`GET /api/posts/{id}/comments`（公开，分页，按时间升序=楼层）、`POST /api/posts/{id}/comments`（登录，1~1000 字符）、`DELETE /api/comments/{id}`（评论作者或 admin 可删，否则 403）；
- 点赞接口契约：`POST/DELETE /api/posts/{id}/like`（登录，幂等）；`likes` 表对 `(post_id,user_id)` 建唯一约束兜底防刷，计数一律 `COUNT(*)` 实时统计，严禁无约束 `+1` 累加；
- 社交计数：文章详情/列表的 `PostResponse` 必须携带 `likes` / `comment_count` / `liked`（未登录 `liked=false`）；列表批量统计用 `IN + GROUP BY`（`_post_counts`）避免 N+1；
- 可选登录：读接口展示已点赞态用 `get_optional_user`（`auto_error=False`），未登录不得 401；
- 草稿隐私隔离：列表接口非 admin（含未登录）强制 `status='published'`，显式请求非发布状态直接返回空集；详情接口非 admin 访问非发布文章一律 404；admin 可通过 `status` 参数自由过滤草稿/全部；
- 级联清理：删除文章时同步删除其 `likes` 与 `comments`（SQLite 默认未启用外键级联）；
- AI 接口契约：`GET /api/ai/status`（公开，返回 `{enabled, model, provider}`）、`POST /api/ai/generate`（仅 admin，body `{title, content, category?}` → 摘要/标签/标题/分类建议）、`POST /api/ai/backfill`（仅 admin，`limit` 1~200，对无摘要文章逐篇回填，幂等返回 `{total, processed, updated, failed}`）；
- AI 触发：发布/更新文章后若 `summary` 为空且 AI 可用，用 `BackgroundTasks` 异步调 `_auto_enrich_post`（自行开 Session）补齐摘要与标签；**按字段独立回填**——`summary` 空才写摘要、`tags` 空才写标签，标题/分类绝不自动覆盖，仅编辑器建议；
- AI 配置：`LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` 一律 `os.getenv` 动态读取（默认 DeepSeek），仅存 `.env`（已忽略）；`main.py` 顶部 `load_dotenv()`；`ai_service` 强制 `response_format=json_object` 并做 JSON 解析兜底；
- AI 降级：未配置 `LLM_API_KEY` 时 `ai_enabled()` 返回 False——AI 接口 503、发布照常不报错、后台自动生成静默跳过；调用失败仅记日志/返回 502，绝不影响博客主流程；
- AI 测试：用例用 `monkeypatch.setenv("LLM_API_KEY", ...)` + stub `ai_service._chat_json` 返回确定性 JSON；`setup_db` 默认 `delenv` 使 AI 禁用，保证既有用例隔离；
- 新增或改造接口先写 `pytest` + TestClient 验收测试（正常 / 异常 / 未授权 / 越权状态码），红灯后再编码，`uv run pytest -q` 全绿后交付。

## 🚫 红线禁令（Don't）

- 禁止明文存储密码与 Token；
- 禁止绕过 JWT 校验暴露受保护接口；
- 禁止破坏既有 API 契约与分层职责（含分页响应结构 `{items,total,page,page_size}`）；
- 禁止点赞无唯一约束直接累加计数（防刷）；
- 禁止向非 admin 泄露草稿/非发布文章（列表默认必须过滤为 published，详情对非 admin 返回 404）；
- 禁止在 `get_optional_user` 上抛 401 破坏读接口公开性；
- 禁止 `LLM_API_KEY` 落库、进响应体或进前端（只能后端环境变量，`.env` 必须忽略）；
- 禁止自动生成覆盖人工输入的 `summary` / `tags`（严格按字段独立回填，标题/分类只建议不自动改）；
- 禁止未配 key / 调用失败时影响博客主流程（发布、浏览、评论、点赞必须保持可用）；
- 禁止跳过测试伪造绿灯。
