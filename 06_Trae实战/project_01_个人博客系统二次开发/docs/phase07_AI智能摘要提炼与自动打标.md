# 阶段七：AI 原生赋能（智能摘要提炼与自动打标）— 实施方案

> 对应第六章 6.5 · 阶段三实战。

## 一、概述（Summary）

在「个人博客系统」（FastAPI + SQLite + SQLAlchemy 2.0 + 单文件 HTML 前端 + JWT 角色权限隔离 + 评论/点赞/分页）基础上，注入 **AI 原生能力**：

- 后端接入 **OpenAI 兼容 API**（openai SDK + `base_url` 一行切换 DeepSeek / 通义 / Kimi 等）
- **100 字导读摘要**：根据正文自动生成导读，落库到 `posts.summary`
- **内容感知自动打标**：根据正文提取 3~5 个标签，填充 `posts.tags`（复用既有字段，不新增表）
- **编辑器灵感副驾**：编辑器内「✨ AI 生成」一键产出 摘要 / 标签 / 标题 / 分类 建议，供一键采用
- **发布自动生成**：发布/更新文章时**后台异步**自动补齐摘要与标签（按字段独立回填，尊重人工输入）
- **存量批量回填**：提供 `/api/ai/backfill` 对无摘要旧文章逐篇回填（限速、幂等、可设上限）
- **优雅降级**：未配置 `LLM_API_KEY` 时博客功能完全不受影响，AI 能力可用性通过 `/api/ai/status` 可见

遵循项目红线：API Key 100% 环境变量注入（绝不落库、绝不进前端）、分层清晰、ATDD、`uv` 管理依赖、`uv run pytest -q` 全绿交付、OpenSpec 闭环。

---

## 二、现状分析（Current State Analysis）

| 文件 | 现状 | 与本阶段关系 |
| :--- | :--- | :--- |
| `models.py` | `Post`：title/content/category/tags/status/views/...，**无摘要字段** | 需给 `Post` 增加 `summary` 列 |
| `schemas.py` | `PostResponse` 无 `summary`；无 AI 相关 DTO | 需扩展 + 新增 AI DTO |
| `main.py` | 文章 CRUD / 评论 / 点赞 / 分类；无 AI 路由与后台任务 | 需新增 AI 路由 + 发布时挂异步生成 |
| `index.html` | 编辑器模态框：标题/分类/标签/Markdown+预览；无摘要输入、无 AI 面板 | 需新增摘要输入框 + AI 灵感副驾 + 卡片/阅读器导读展示 |
| `test_main.py` | 71 用例全绿；未覆盖 AI | 需新增 AI 能力用例（stub LLM） |
| `pyproject.toml` | 无 `openai` / `python-dotenv` 依赖 | 需 `uv add openai python-dotenv` |
| `.env.example` / `.gitignore` | 无环境变量模板 | 需新增 `.env.example` 并确保 `.env` 被忽略 |
| `.trae/rules/backend.md`、`agents.md` | 无 AI 相关红线 | 阶段完成后按惯例同步文档 |

**关键点**：
- `posts` 表新增列对**既有本地库**需一次性 `ALTER TABLE`（测试库每用例重建不受影响）。
- 发布接口**无破坏性风险**：自动生成在后台异步执行，不阻塞发布响应；未配置 key 时静默跳过。
- 标签字段 `tags` 本身已存在（逗号分隔字符串），自动打标复用该字段，不新增表。

---

## 三、目标与决策（Goals & Decisions）

已与用户确认的决策：

1. **LLM 选型 = OpenAI 兼容 API + openai SDK**：统一 `openai` 客户端，`base_url` 一行切换厂商（默认 DeepSeek：`https://api.deepseek.com` / `deepseek-chat`）。
2. **触发方式 = 发布自动 + 编辑器手动**：发布/更新时后台异步自动补齐摘要与标签；编辑器内可手动「✨ AI 生成」即时拿到 摘要/标签/标题/分类 建议。
3. **灵感副驾范围 = 摘要 + 标签 + 标题/分类建议**（不含续写/扩写正文）。
4. **存量回填 = 提供批量回填接口**（限速、幂等、可设上限）。

补充合理假设（已记录，如不合意可调整）：

- **按字段独立回填**：`summary` 为空才生成摘要、`tags` 为空才生成标签；`title/category` 建议仅编辑器手动采用，**绝不自动覆盖**。
- **生成结果约定**：摘要约 100 字中文导读；标签 3~5 个（以英文逗号 `,` 拼接写入 `tags`，与既有前端 placeholder 一致）；标题建议 1 条；分类建议 1 条。
- **超时与失败**：LLM 调用失败只记日志不抛错（自动生成场景）；手动按钮场景以 Toast 提示「生成失败，请重试」。
- **安全**：`LLM_API_KEY` 仅后端 `os.getenv` 读取；前端永远不接触 Key；`AIGenerateRequest` 仅含 title/content/category。
- **限流**：批量回填默认 `limit=50`、逐篇生成失败计入 `failed` 不中断（幂等，重复调用不会重复扣费）；不设人为 sleep，避免阻塞，靠失败计数与上游限流错误兜底。
- **本期不做**：AI 续写/扩写正文、对话式助手、摘要缓存/去重、多轮重试与降级到其他模型。

---

## 四、方案设计（Design）

### 4.1 数据模型 — `models.py` 为 `Post` 增加 `summary`

```python
# Post 新增字段（放在 content 之后）
summary: Mapped[str] = mapped_column(Text, default="")  # AI 生成的 100 字导读，空串表示未生成
```

> 既有本地库迁移（新库由 `create_all` 自动包含该列）：
> `sqlite3 blog.db "ALTER TABLE posts ADD COLUMN summary TEXT DEFAULT ''"`

### 4.2 AI 服务模块 — 新增 `ai_service.py`

职责：环境变量配置 + OpenAI 兼容客户端 + 生成能力 + 纯 JSON 输出解析。独立分层，保持 `main.py` 只管路由。

```python
import json
import os

from openai import OpenAI

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

_client: OpenAI | None = None


def ai_enabled() -> bool:
    return bool(LLM_API_KEY)


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    return _client


def _chat_json(system: str, user: str) -> dict:
    """要求模型返回纯 JSON 对象；解析失败抛 ValueError，由上层兜底"""
    resp = get_client().chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.4,
    )
    return json.loads(resp.choices[0].message.content)


def generate_all(title: str, content: str, category: str = "") -> dict:
    """一次性产出 {summary, tags, title_suggestion, category_suggestion}"""
    system = (
        "你是中文技术博客的编辑助手。严格只输出 JSON 对象，不要输出任何解释或 Markdown。"
        "字段说明："
        "summary：根据正文提炼约 100 字的中文导读（吸引读者、点明主旨，不含 HTML）；"
        "tags：根据正文内容提取 3~5 个标签，放入字符串数组；"
        "title_suggestion：一个更吸引人的标题；"
        "category_suggestion：一个合适的分类名。"
    )
    user = f"标题：{title}\n现有分类：{category}\n正文：\n{content[:4000]}"
    return _chat_json(system, user)
```

> 测试注入点：用例用 `monkeypatch` 替换 `ai_service._chat_json` 或 `ai_service.get_client`，返回确定性 JSON，保证 ATDD 稳定。

### 4.3 Schema — `schemas.py` 新增 / 扩展

```python
# PostResponse 增加摘要字段（默认空串，保证旧调用兼容）
class PostResponse(BaseModel):
    ...
    summary: str = ""
    ...

# PostCreate / PostUpdate 增加可选 summary（允许人工预填 / 编辑）
class PostCreate(BaseModel):
    ...
    summary: str = ""


class PostUpdate(BaseModel):
    ...
    summary: Optional[str] = None


# ────────────────── AI ──────────────────

class AIGenerateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    category: str = ""


class AIGenerateResponse(BaseModel):
    summary: str
    tags: list[str]
    title_suggestion: str
    category_suggestion: str


class AIStatusResponse(BaseModel):
    enabled: bool
    model: str
    provider: str


class BackfillResponse(BaseModel):
    total: int      # 扫描到的无摘要文章数
    processed: int  # 本次实际尝试生成数（受 limit 截断）
    updated: int    # 成功落库数
    failed: int     # 失败数（仅记日志，不中断）
```

### 4.4 API 契约（新增 / 变更）

| 方法 | 路径 | 权限 | 说明 |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/ai/status` | 公开 | 返回 `{enabled, model, provider}`，前端据此显隐 AI 面板 |
| `POST` | `/api/ai/generate` | 仅 admin | body `{title, content, category?}` → `AIGenerateResponse`；未配置 key → 503；未登录 401 / 非 admin 403 |
| `POST` | `/api/ai/backfill` | 仅 admin | 批量回填无摘要旧文章 → `BackfillResponse`；未配置 key → 503 |
| `POST` | `/api/posts` | 仅 admin | **变更**：发布成功后若 `summary` 为空且 AI 可用 → 挂后台任务自动生成 |
| `PUT` | `/api/posts/{id}` | 仅 admin | **变更**：同上，仅在 `summary` 为空时触发 |

错误格式沿用 `{"detail": "..."}`。

### 4.5 后端 — `main.py`

- 新增 `_auto_enrich_post(post_id: int)` 后台任务：自行 `database.SessionLocal()` 打开会话 → 查文章 → 调 `ai_service.generate_all` → **按字段独立回填**（`summary` 为空才写摘要、`tags` 为空才写标签）→ commit；全程 try/except 仅记日志。
- `create_post` / `update_post`：commit 后 `if ai_service.ai_enabled() and not post.summary: background_tasks.add_task(_auto_enrich_post, post.id)`。
- 新增 3 个 AI 路由（见 4.4）。`/api/ai/generate` 同步调用 `generate_all` 并校验返回键；`tags` 以 `",".join(...)` 写入。
- 环境变量：`main.py` 顶部 `load_dotenv()`（python-dotenv；无 `.env` 文件也不报错）。

### 4.6 前端 — `index.html`

- **编辑器新增「摘要」输入框** `editorSummary`（置于元信息区，占整行，2 行 textarea）。
- **编辑器新增「✨ AI 灵感」区域**（元信息下方）：
  - 「一键生成」按钮 → `POST /api/ai/generate` → loading 态 → 结果填充：`summary` → 摘要框、`tags` → 标签框、`title_suggestion` / `category_suggestion` → 以「建议条」展示，各带「采用」按钮；失败 Toast。
  - 打开编辑器时先 `GET /api/ai/status`，`enabled=false` 时隐藏 AI 区域并提示「未配置 LLM API Key」。
- **卡片导读**：文章卡片在标题下展示 `summary`（非空时，最多 2 行截断）。
- **阅读器导读**：阅读器内容顶部展示 `summary` 导读条（非空时）。
- **批量回填**：admin 可见「AI 批量回填」入口（顶部导航）→ `POST /api/ai/backfill` → 展示 `updated/failed` 结果 Toast。
- 保持玻璃拟态风格与既有交互习惯；`apiFetch` 自动带 Token；渲染 `summary` 一律 `escapeHtml` 防 XSS。

### 4.7 测试 — `test_main.py`（ATDD）

**stub 策略**：`monkeypatch.setattr(ai_service, "_chat_json", fake)` 返回确定性字典；`ai_enabled` 用 `monkeypatch.setenv("LLM_API_KEY", "test")` / `delenv` 控制。

**新增用例**：
- `/api/ai/status`：有 key → `enabled=true`；无 key → `enabled=false`。
- `/api/ai/generate`：admin 200 返回四件套；未登录 401；reader 403；无 key 503。
- 发布自动生成：admin 发布空 `summary` 文章 → 响应后查库 `summary`/`tags` 已被 stub 值填充（TestClient 同步执行后台任务；若时序不稳改用直接调用 `_auto_enrich_post` 断言）。
- 人工优先：发布时已手动填 `summary`/`tags` → 自动生成不覆盖。
- 按字段独立：有 `tags` 无 `summary` → 只补摘要、`tags` 保留。
- 无 key 降级：发布文章不报错、`summary` 保持空。
- `/api/ai/backfill`：只处理无摘要文章；`limit` 截断；幂等（二次调用 `updated=0`）；无 key 503。

**回归**：既有 71 用例全部保持绿灯（`PostResponse` 新增 `summary` 默认值不破坏既有断言）。

### 4.8 依赖与配置

- `uv add openai python-dotenv`
- 新增 `.env.example`：

  ```
  LLM_API_KEY=sk-xxx
  LLM_BASE_URL=https://api.deepseek.com
  LLM_MODEL=deepseek-chat
  ```

- 确保 `.gitignore` 忽略 `.env`；`LLM_API_KEY` 绝不进 `index.html` 与任何响应体。

---

## 五、改动文件清单（Files & Why/How）

| 文件 | 改动 | 原因 / 方式 |
| :--- | :--- | :--- |
| `pyproject.toml` | 加依赖 | `uv add openai python-dotenv` |
| `.env.example`（新增） | 环境变量模板 | 注入 Key / BaseURL / Model，脱敏红线 |
| `.gitignore` | 忽略 `.env` | 防密钥泄露 |
| `models.py` | `Post` 增加 `summary` 列 | 落库 AI 导读 |
| `ai_service.py`（新增） | OpenAI 客户端 + `generate_all` | AI 能力独立分层 |
| `schemas.py` | 三个文章 DTO 加 `summary`；新增 4 个 AI DTO | 契约与校验 |
| `main.py` | 3 个 AI 路由 + 发布/更新挂后台任务 + `load_dotenv` | AI 闭环与优雅降级 |
| `index.html` | 摘要输入框 + AI 灵感面板 + 卡片/阅读器导读 + 批量回填入口 | 前端闭环 |
| `test_main.py` | stub `ai_service` 新增 AI 用例 | ATDD |
| 文档同步 | `agents.md`、`.trae/rules/backend.md` | 项目惯例「每阶段同步文档」 |

> `database.py`、`security.py` 与既有 `User` / `Comment` / `Like` 表结构**不改动**。

---

## 六、实施步骤（Tasks）

1. `uv add openai python-dotenv`；新增 `.env.example` 并确认 `.gitignore` 含 `.env`
2. `models.py` 给 `Post` 增加 `summary`；对既有 `blog.db` 执行 `ALTER TABLE`（测试库重建即可）
3. 新增 `ai_service.py`（配置 + `generate_all` + JSON 解析兜底）
4. `schemas.py` 扩展 `summary` + 新增 AI DTO
5. `test_main.py`：先写 AI stub 与用例（红灯）→ 后编码（绿灯）；回归既有 71 用例
6. `main.py`：`load_dotenv` + 3 个 AI 路由 + `_auto_enrich_post` 后台任务挂载
7. `uv run pytest -q` 全绿
8. `index.html` 前端改造（摘要框 / AI 灵感面板 / 卡片与阅读器导读 / 批量回填入口）
9. 启动服务实测：配 key 与不配 key 两种形态、编辑器一键生成与采用、发布自动补齐、批量回填
10. OpenSpec `sync` + `archive` 归档 + 同步 `agents.md` / `.trae/rules/backend.md`

---

## 七、验证步骤（Verification）

- 自动化：`uv run pytest -q` 全绿（既有 71 + 新增 AI 用例）。
- API 层抽查（curl）：无 key 时 `/api/ai/generate` → 503、发布不报错；配 key 后 `/api/ai/status` `enabled=true`、`generate` 返回四件套、`backfill` 幂等。
- 手工（浏览器）：编辑器一键生成并采用摘要/标签/标题/分类；卡片与阅读器展示导读；批量回填结果提示；未配 key 时 AI 面板隐藏。

---

## 八、风险与注意事项

- **密钥红线**：`LLM_API_KEY` 只进后端环境变量；`AIGenerateRequest` 不含 key；响应与前端绝不携带 key；`.env` 必须入 `.gitignore`。
- **既有库迁移**：`create_all` 不会给既有表加列，须执行一次 `ALTER TABLE`，否则旧库查询 `summary` 报错。
- **异步时序**：`BackgroundTasks` 在 TestClient 中同步执行；若测试环境时序不稳，改为直接调用 `_auto_enrich_post` 断言落库结果。
- **LLM 输出不可靠**：强制 `response_format=json_object` + 解析失败抛错兜底；生成内容仅作辅助，绝不信任其执行任何逻辑。
- **绝不覆盖人工输入**：严格「按字段独立回填」，`summary` / `tags` 非空即跳过，标题/分类仅建议不自动改。
- **成本与限流**：回填默认 `limit=50` + 间隔限速；自动生成只对「无摘要」文章触发，避免重复扣费。
- **优雅降级**：未配 key / 调用失败均不得影响博客主流程（发布、浏览、评论、点赞）。
- **OpenSpec 闭环**：必须按 propose → apply → sync/archive 推进，规划阶段禁止写业务代码。
