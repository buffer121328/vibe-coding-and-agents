## Why

博客系统需要后端 CRUD 接口支撑前端文章管理。Phase 1 已定义 API 契约与数据模型，Phase 2 需要将规格落地为可运行的 FastAPI 后端，为 Phase 3 前端联调提供真实接口。

## What Changes

- 新建 `database.py`：SQLite 引擎（`blog.db`）与会话管理
- 新建 `models.py`：SQLAlchemy `Post` ORM 模型（9 字段）
- 新建 `schemas.py`：Pydantic 请求/响应校验（`PostCreate`、`PostUpdate`、`PostResponse`、`CategoryStat`）
- 重写 `main.py`：FastAPI 路由 + CORS + 6 个 RESTful 接口

## Capabilities

### New Capabilities
- `backend-crud`: 文章 CRUD 核心能力——数据库连接、ORM 模型、Pydantic 校验、6 个 RESTful 接口（列表/详情/新增/编辑/删除/分类统计）

### Modified Capabilities

（无，首次后端实现）

## Impact

- 新增 4 个 Python 文件：`database.py`、`models.py`、`schemas.py`、`main.py`
- 依赖：FastAPI、SQLAlchemy、Pydantic（已在 `pyproject.toml` 中声明）
- 数据库：SQLite 单文件 `blog.db`，启动时自动建表
- API 端口：默认 8000，CORS 允许前端跨域
