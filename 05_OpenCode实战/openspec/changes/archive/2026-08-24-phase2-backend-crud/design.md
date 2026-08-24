## Context

Phase 1 已定义完整的 API 契约与数据模型。当前项目仅有一个占位 `main.py`，需要从零实现后端。技术栈锁定：FastAPI + SQLAlchemy + SQLite + Pydantic，所有依赖已在 `pyproject.toml` 中声明。

## Goals / Non-Goals

**Goals:**
- 实现 4 个核心文件的完整后端 CRUD 逻辑
- 启动时自动建表，零配置开箱即用
- 6 个 RESTful 接口全部可用，返回正确状态码
- CORS 跨域已配置，为 Phase 3 前端联调做准备

**Non-Goals:**
- 不做身份认证/授权（个人博客单用户）
- 不做分页（数据量小，前端可一次性加载）
- 不做数据库迁移工具（SQLite 单文件足够简单）
- 不做 Docker 部署

## Decisions

### 1. 数据库：SQLite 单文件
- **选择**：`sqlite:///./blog.db`
- **理由**：个人博客场景，单用户、低并发，SQLite 零配置、单文件便于部署
- **替代方案**：PostgreSQL（需要额外服务，过度设计）

### 2. ORM：SQLAlchemy 2.0 风格
- **选择**：使用 `DeclarativeBase` + `Mapped` 类型注解风格
- **理由**：类型安全，与 Pydantic 天然配合，社区主流
- **替代方案**：SQLModel（多一层抽象，本项目不需要）

### 3. 会话管理：依赖注入
- **选择**：`get_db()` 作为 FastAPI `Depends`，使用 `yield` 确保会话关闭
- **理由**：FastAPI 标准实践，自动管理会话生命周期

### 4. 建表时机：应用启动时
- **选择**：`Base.metadata.create_all(bind=engine)` 在模块加载时执行
- **理由**：简单直接，适合开发阶段。生产环境可迁移至 Alembic

### 5. CORS：显式允许前端来源
- **选择**：`CORSMiddleware` 允许 `*` 来源（开发阶段）
- **理由**：前后端同机开发，避免跨域问题。生产环境应限制具体域名

## Risks / Trade-offs

- **SQLite 并发限制** → 个人博客单用户场景无影响；未来多用户需迁移
- **无数据库迁移** → 结构变更需手动处理；当前阶段可接受
- **CORS 允许全部来源** → 开发便利，上线前必须收紧
- **启动时建表** → 多实例并发启动可能冲突；单实例部署无影响
