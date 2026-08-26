## Context

博客系统为 FastAPI + SQLite + SQLAlchemy 2.0 + 单文件 HTML 前端，已有用户/JWT 权限隔离、评论点赞社交与分页契约。本章节（第六章 6.5 · 阶段三）为文章注入 AI 原生能力：智能摘要提炼与自动打标。AI 采用 OpenAI 兼容接口（openai SDK + `base_url` 切换厂商，默认 DeepSeek）。密钥红线：`LLM_API_KEY` 只存后端 `.env`，绝不进前端。见 proposal.md - Why 与 specs 的行为契约。

## Goals / Non-Goals

**Goals:**
- `posts` 表新增 `summary` 列（AI 100 字导读），`PostResponse` 携带
- 新增 `ai_service.py`：OpenAI 兼容客户端 + `generate_all`（摘要/标签/标题/分类）+ JSON 解析兜底
- AI 接口：`GET /api/ai/status`、`POST /api/ai/generate`、`POST /api/ai/backfill`（均走既有 JWT 权限守卫）
- 发布/更新文章时后台异步自动补齐摘要与标签（`BackgroundTasks`，按字段独立回填）
- 前端：编辑器摘要输入框 + AI 灵感副驾、卡片/阅读器导读展示、admin 批量回填入口
- 优雅降级：未配置 Key / 调用失败不影响博客主流程

**Non-Goals:**
- 不做 AI 续写/扩写正文、对话式助手
- 不做摘要缓存/去重、多轮重试与降级到其他模型
- 不新增 tags 表（沿用既有逗号分隔字符串字段）
- 不改动 `User` / `Comment` / `Like` 表结构与既有认证契约

## Decisions

### LLM 选型 = OpenAI 兼容 API + openai SDK
统一 `openai` 客户端，`base_url` 一行切换 DeepSeek / 通义 / Kimi 等，教程普适性最强。默认 `https://api.deepseek.com` / `deepseek-chat`。环境变量（`LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`）在函数内动态 `os.getenv` 读取，便于测试注入与热切换。

### 触发方式 = 发布自动 + 编辑器手动
发布/更新文章时，若 `summary` 为空且 AI 可用，用 `BackgroundTasks` 后台异步调 `_auto_enrich_post`（自行开 `database.SessionLocal`）补齐摘要与标签，**不阻塞发布响应**。编辑器内「✨ 一键生成」同步调用 `POST /api/ai/generate`，即时拿到 摘要/标签/标题/分类 建议。

### 按字段独立回填（绝不覆盖人工输入）
自动生成严格逐字段判断：`summary` 为空才写摘要、`tags` 为空才写标签；标题/分类只以建议条形式给编辑器手动采用，绝不自动改库。这是数据红线，避免 AI 覆盖人工精心撰写的内容。

### 优雅降级 = `ai_enabled()` 开关
`ai_service.ai_enabled()` 读取 `LLM_API_KEY` 是否配置。未配置时：AI 接口 503、发布/更新不挂后台任务、`GET /api/ai/status` 返回 `enabled=false` 供前端隐藏 AI 面板。LLM 调用失败：自动生成场景仅记日志，手动生成场景返回 502 并 Toast 提示。

### JSON 输出可靠性兜底
强制 `response_format={"type":"json_object"}`（DeepSeek 等主流兼容接口均支持），`_chat_json` 用 `json.loads` 解析；解析失败抛 `ValueError`，由上层统一转 502 / 记日志，绝不裸信任模型输出拼接进响应。

### 存量回填 = 幂等 + 上限
`POST /api/ai/backfill` 只扫 `summary == ""` 的文章（`ORDER BY id` + `limit` 1~200），逐篇生成并**逐字段独立回填**；单篇失败计入 `failed` 不中断。幂等——二次调用 `total` 为 0、`updated` 为 0，不重复扣费。不设人为 sleep，靠失败计数与上游限流错误兜底。

### 测试 = stub LLM
用例用 `monkeypatch.setenv("LLM_API_KEY", ...)` 开启 AI + stub `ai_service._chat_json` 返回确定性 JSON；`setup_db` autouse 默认 `delenv("LLM_API_KEY")` 使 AI 禁用，保证既有 71 用例完全隔离、测试离线不消耗真实 token。

## Risks / Trade-offs

- **既有库新增列** → `create_all` 不会给既有 `posts` 表加列，须执行一次 `ALTER TABLE posts ADD COLUMN summary TEXT DEFAULT ''`（测试库每用例重建不受影响）
- **后台任务时序** → `BackgroundTasks` 在 TestClient 中同步执行；若环境时序不稳，测试改为直接调用 `_auto_enrich_post` 断言落库结果
- **密钥泄露** → `LLM_API_KEY` 只进后端环境变量与 `.env`；`AIGenerateRequest` 不含 key；响应与前端绝不携带 key；`.env` 必须入 `.gitignore`
- **LLM 输出不可靠** → 强制 `json_object` + 解析兜底 + 绝不信任输出执行任何逻辑
- **覆盖人工输入** → 严格「按字段独立回填」，`summary` / `tags` 非空即跳过，标题/分类仅建议
- **成本** → 自动生成只对「无摘要」文章触发；回填设 `limit` 上限且幂等，避免重复扣费

## Migration Plan

- 既有本地库执行一次 `sqlite3 blog.db "ALTER TABLE posts ADD COLUMN summary TEXT DEFAULT ''"`；新库由 `create_all` 自动建列
- 前端与后端同步发布（单文件工程）；未配置 Key 即回退阶段六行为，回滚成本为零
- 测试用内存 SQLite（StaticPool）每用例重建表，天然覆盖新列
- 文档：`docs/phase07_AI智能摘要提炼与自动打标.md` 为实施方案落盘，本次归档同步 openspec 制品

## Open Questions

无。
