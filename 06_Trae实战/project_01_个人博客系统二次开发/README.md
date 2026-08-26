# 📝 个人博客系统（Trae 二次开发实战版）

基于 **FastAPI + SQLite + SQLAlchemy 2.0 + 单文件 HTML 前端** 的极简全栈博客系统。它诞生于第五章 OpenCode 实战，并在第六章 Trae 实战中完成了一路「生产级二次开发」：从基础文章 CRUD 演进到 **JWT 角色权限隔离 → 评论点赞社交系统 → 接口分页重构 → AI 原生赋能（智能摘要提炼与自动打标）**。

> 本 README 面向「拿到源码就能跑」的开发者；各阶段完整实施方案见 [docs/](./docs/)。

***

## ✨ 功能特性

| 演进阶段 | 核心能力 |
| :--- | :--- |
| 基础能力 | 文章 CRUD、分类统计、Markdown 实时渲染、阅读量统计、关键词搜索、分页浏览 |
| 阶段一 · 身份与安全（6.3） | 用户注册登录、**JWT 角色权限**（admin 可写 / reader 只读）、bcrypt 密码哈希、种子管理员 |
| 阶段二 · 社交互动（6.4） | 评论**楼层**渲染、点赞**幂等防刷**、接口 `Page & PageSize` 分页重构 |
| 阶段三 · AI 原生赋能（6.5） | **100 字导读摘要**、**内容感知自动打标**、编辑器**「AI 灵感副驾」**、存量**批量回填**、无 Key **优雅降级** |

***

## 🛠 技术栈

| 层 | 技术 |
| :--- | :--- |
| 后端 | FastAPI + Uvicorn + SQLAlchemy 2.0（Mapped 语法）+ Pydantic V2 |
| 数据库 | SQLite（单文件 `blog.db`，零配置） |
| 前端 | 单文件 `index.html`：TailwindCSS（CDN）+ Marked.js + Lucide + 原生现代 JS，**零 npm 构建链** |
| AI 能力 | openai SDK + OpenAI 兼容接口（默认 DeepSeek），`base_url` 一行切换厂商 |
| 工程 | uv 依赖管理 + pytest（TestClient）ATDD 验收测试 |

***

## 📂 项目结构

```
project_01_个人博客系统二次开发/
├── .traerules        # Trae 项目专属规则大脑（技术栈 + 二次开发守则）
├── .trae/            # OpenSpec 为 Trae 生成的智能体配置（skills + commands + rules）
├── openspec/         # 规格演进制品：specs 主规格 + changes 变更归档
├── reference/        # 已验收历史规格归档区（区分历史资产与新迭代规格）
├── docs/             # 各阶段实施方案（phase05 鉴权 / phase06 社交分页 / phase07 AI 赋能）
├── .env.example      # 环境变量模板（复制为 .env 填入 LLM_API_KEY 启用 AI）
├── pyproject.toml    # uv 依赖声明
├── uv.lock           # 锁定的确定性依赖版本
├── database.py       # SQLite 引擎、Session 与 get_db 依赖
├── models.py         # ORM 模型：User / Post(含 summary 导读) / Comment / Like
├── schemas.py        # Pydantic V2 请求/响应 DTO（含分页/评论/点赞/AI DTO）
├── security.py       # bcrypt 哈希、JWT 编解码、get_current_user/get_optional_user/require_admin
├── ai_service.py     # OpenAI 兼容客户端 + 摘要/标签/标题/分类生成 + JSON 解析兜底
├── main.py           # FastAPI 路由、鉴权守卫挂载、静态托管、CORS、AI 后台自动生成
├── index.html        # 单文件前端（玻璃拟态，分页/点赞/评论楼层/AI 灵感副驾/导读展示）
└── test_main.py      # pytest 回归测试套件（95 用例全绿，AI 用例 stub LLM，含草稿隐私隔离）
```

***

## 🚀 快速开始

依赖一律 `uv` 管理（禁止手写 pip/venv）：

```bash
# 1. 进入项目目录
cd 06_Trae实战/project_01_个人博客系统二次开发

# 2. 首次：创建虚拟环境并安装依赖（后续无需重复）
uv sync

# 3. 启动开发服务器
uv run uvicorn main:app --reload --port 8000
```

打开浏览器访问 <http://127.0.0.1:8000>。

**停止运行**：在运行 uvicorn 的终端按 `Ctrl + C` 即可停止（`--reload` 模式会同时退出热重载进程）。若终端已关闭、进程残留导致端口被占用，可用以下命令找到并结束占用 8000 端口的进程：

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN   # 查看占用 8000 的 PID
kill <PID>                          # 结束该进程后即可重新启动
```

**默认种子管理员账号**：`admin` / `admin123`（仅限本地教学，上线前请通过环境变量修改密码）。

> 💡 切换 AI 厂商：只需改 `.env` 里的 `LLM_BASE_URL` / `LLM_MODEL`，代码零改动。

***

## 🔑 AI 能力配置（可选）

AI 功能（智能摘要 / 自动打标 / 灵感副驾 / 批量回填）**默认关闭**，未配置时博客完全可用，AI 面板自动隐藏。

```bash
# 复制模板 → 填入真实 Key
cp .env.example .env
```

`.env` 说明：

| 变量 | 必填 | 说明 |
| :--- | :--- | :--- |
| `LLM_API_KEY` | ✅ | 大模型 API Key，**只存后端 `.env`**（已入 `.gitignore`），绝不进前端 |
| `LLM_BASE_URL` | 否 | OpenAI 兼容接口地址，默认 `https://api.deepseek.com` |
| `LLM_MODEL` | 否 | 模型名，默认 `deepseek-chat` |

**触发方式**：
- 编辑器「✨ 一键生成」→ 手动生成 摘要/标签/标题/分类 建议；
- 发布/更新文章时（摘要为空）→ 后台自动补齐摘要与标签；
- 顶部「AI 回填」→ 对无摘要的存量旧文章批量回填。

**数据红线**：AI 生成**绝不覆盖人工输入**——`summary` / `tags` 非空即跳过，标题/分类只给建议不自动改。

***

## 📡 API 一览

统一错误格式 `{"detail": "..."}`；受保护接口未登录 `401`、非 admin `403`。

### 认证 / 用户

| 方法 | 路径 | 权限 | 说明 |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/auth/login` | 公开 | 登录颁发 JWT |
| `GET` | `/api/auth/me` | 登录 | 当前用户信息 |
| `POST` | `/api/users` | admin | 创建账号（不开放公开注册） |
| `GET` | `/api/users` | admin | 用户列表 |

### 文章 / 分类

| 方法 | 路径 | 权限 | 说明 |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/posts` | 公开 | 列表（分页 + 分类/状态/搜索过滤） |
| `GET` | `/api/posts/{id}` | 公开 | 详情（`increment_views` 可选自增阅读量） |
| `POST` | `/api/posts` | admin | 发布（摘要为空且 AI 可用时后台自动生成） |
| `PUT` | `/api/posts/{id}` | admin | 更新 |
| `DELETE` | `/api/posts/{id}` | admin | 删除（级联清理评论/点赞） |
| `GET` | `/api/categories` | 公开 | 分类及文章数统计 |

### 评论 / 点赞

| 方法 | 路径 | 权限 | 说明 |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/posts/{id}/comments` | 公开 | 评论列表（分页，升序楼层） |
| `POST` | `/api/posts/{id}/comments` | 登录 | 发表评论（1~1000 字符） |
| `DELETE` | `/api/comments/{id}` | 作者/admin | 删除评论 |
| `POST` | `/api/posts/{id}/like` | 登录 | 点赞（幂等防刷） |
| `DELETE` | `/api/posts/{id}/like` | 登录 | 取消点赞（幂等） |

### AI 能力

| 方法 | 路径 | 权限 | 说明 |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/ai/status` | 公开 | AI 可用状态 `{enabled, model, provider}` |
| `POST` | `/api/ai/generate` | admin | 生成 摘要/标签/标题/分类 建议（无 Key 返回 503） |
| `POST` | `/api/ai/backfill` | admin | 批量回填无摘要文章（`limit` 1~200，幂等） |

> 分页契约：列表接口返回 `{items, total, page, page_size}`；`page ≥ 1`、`1 ≤ page_size ≤ 50`，非法参数 422。

***

## 🧪 测试

```bash
uv run pytest -q        # 95 个用例全绿（既有 71 + AI 17 + 草稿隐私隔离 7）
```

- 覆盖：认证/权限/越权、文章 CRUD、分页契约、评论楼层与删除权限、点赞幂等、社交计数、级联清理、AI 全链路；
- AI 用例通过 stub `ai_service._chat_json` 返回确定性 JSON，**不消耗真实 token**，测试完全离线可跑。

***

## 🧭 关联文档

- [docs/phase05_用户注册登录与JWT权限隔离系统.md](./docs/phase05_用户注册登录与JWT权限隔离系统.md) — 阶段一实施方案
- [docs/phase06_评论点赞系统与接口分页重构.md](./docs/phase06_评论点赞系统与接口分页重构.md) — 阶段二实施方案
- [docs/phase07_AI智能摘要提炼与自动打标.md](./docs/phase07_AI智能摘要提炼与自动打标.md) — 阶段三实施方案（AI 原生赋能）
- `reference/` — OpenCode 时代已验收的历史规格归档
