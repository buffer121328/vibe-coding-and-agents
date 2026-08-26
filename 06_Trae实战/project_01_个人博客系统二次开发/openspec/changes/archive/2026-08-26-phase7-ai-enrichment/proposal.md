## Why

博客系统已具备文章 CRUD、用户/JWT 权限隔离、评论点赞社交与分页重构，但内容仍完全依赖人工填写：文章缺少导读摘要与内容感知标签，读者浏览首页/阅读器只能看正文截断，作者写作时也没有任何 AI 辅助。需要接入大模型为文章注入「AI 原生能力」：自动提炼 100 字导读、内容感知提取标签、编辑器灵感副驾，并对存量文章提供批量回填。

## What Changes

- `posts` 表新增 `summary` 列（AI 100 字导读，空串表示未生成）；既有本地库执行一次 `ALTER TABLE`，新库由 `create_all` 自动建列
- 新增 `ai_service.py`：OpenAI 兼容客户端（`base_url` 一行切换厂商，默认 DeepSeek），`generate_all` 一次性产出 摘要/标签/标题/分类 建议，强制 `response_format=json_object` + JSON 解析兜底
- 新增 AI 接口：`GET /api/ai/status`（公开，返回 `{enabled, model, provider}`）、`POST /api/ai/generate`（仅 admin）、`POST /api/ai/backfill`（仅 admin，`limit` 1~200，幂等返回 `{total, processed, updated, failed}`）
- **变更**：`POST /api/posts` 与 `PUT /api/posts/{id}` 在 `summary` 为空且 AI 可用时，用 `BackgroundTasks` 后台异步补齐摘要与标签——**按字段独立回填**（`summary` 空才写摘要、`tags` 空才写标签），绝不覆盖人工输入；标题/分类仅编辑器建议，绝不自动改库
- `PostResponse` / `PostCreate` / `PostUpdate` 增加 `summary` 字段（默认空串，兼容旧调用）
- 优雅降级：未配置 `LLM_API_KEY` 时 AI 接口返回 503、发布/浏览照常、后台生成静默跳过、前端 AI 面板自动隐藏
- 前端：编辑器新增「导读摘要」输入框与「AI 灵感副驾」（一键生成直接填充摘要/标签、标题/分类建议条一键采用）、文章卡片与阅读器导读展示、admin 导航「AI 回填」按钮
- 依赖：`uv add openai python-dotenv`；新增 `.env.example`（`LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`），`.env` 已入 `.gitignore`

## Capabilities

### New Capabilities
- `ai-enrichment`: AI 智能摘要提炼与自动打标——100 字导读生成、内容感知标签提取、编辑器灵感副驾、发布/更新后台自动补齐、存量批量回填、未配置 Key 优雅降级

## Impact

- 修改文件：`models.py`（+summary）、`schemas.py`（+AI DTO）、`main.py`（AI 路由 + 后台任务 + load_dotenv）、`index.html`（摘要框/AI 面板/导读/回填）、`test_main.py`（+17 用例）、`pyproject.toml`（+openai/python-dotenv）
- 新增文件：`ai_service.py`、`.env.example`
- 数据库：`posts` 表新增 `summary` 列（既有库需一次 `ALTER TABLE`）
- 兼容性：`PostResponse` 新增 `summary` 默认空串，既有调用与测试不受影响；未配置 Key 时行为与阶段六完全一致
