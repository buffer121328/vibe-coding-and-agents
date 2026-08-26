## Context

博客系统当前无鉴权：写接口（POST/PUT/DELETE `/api/posts`）与读接口同为公开，任何访客均可增删改。技术栈为 FastAPI + SQLite + SQLAlchemy 2.0 + 单文件 HTML 前端，依赖由 uv 管理，测试采用 pytest + TestClient（内存 SQLite，StaticPool）。详见 proposal.md 的 Why。

## Goals / Non-Goals

**Goals:**
- 建立 `users` 表 + bcrypt 密码哈希 + JWT 鉴权闭环
- 角色权限制：reader 只读，admin 可写、可管理用户
- 前端最小改造：登录弹窗 + 按钮显隐 + Token 持久化 + 401 处理
- 既有测试全量改造适配，新增认证/权限用例，`uv run pytest -q` 全绿

**Non-Goals:**
- 不开放公开注册（仅管理员创建账号）
- 不做 refresh token、邮箱验证、找回密码、登录限流、审计日志
- `posts` 表不加 `author_id`（角色制而非作者归属）
- 不做用户管理前端页面（仅提供 API）

## Decisions

### 数据模型：新增 `User` 表
- `models.py` 增加 `User`（id/username 唯一索引/password_hash/role(默认 reader)/created_at）
- 密码只存 bcrypt 哈希；任何响应 DTO 都不序列化 `password_hash`

### 认证原语独立分层：新增 `security.py`
- 将 bcrypt 哈希、JWT 编解码、`get_current_user` / `require_admin` 守卫从 `main.py` 拆出，保持 `main.py` 只管路由
- JWT：HS256，7 天有效期；`SECRET_KEY` 优先环境变量 `BLOG_SECRET_KEY`，未设置用开发默认值（注释提醒上线前修改）

### 守卫依赖
- `get_current_user`：`OAuth2PasswordBearer(tokenUrl="/api/auth/login")` 解析 Bearer → `jwt.decode` → 查库取 User；失败一律 401
- `require_admin`：在 `get_current_user` 之上校验 `role == "admin"`，否则 403
- 写文章接口（POST/PUT/DELETE）与用户管理接口挂 `require_admin`

### 种子管理员
- `seed_admin(db)`：`users` 为空时创建 `admin`（默认密码 `admin123`，可经 `BLOG_ADMIN_PASSWORD` 环境变量覆盖）
- `lifespan` 中建表后调用；测试侧 `setup_db` 每个用例重建表后也调用，保证可登录

### 前端（index.html）最小改造
- 登录模态框复用既有 `.modal-overlay`/`.modal-panel` 玻璃拟态样式
- `apiFetch` 自动附带 `Authorization: Bearer <token>`；401 时清除本地登录态并弹登录框
- 按 `role === 'admin'` 显隐：写文章按钮、卡片编辑/删除按钮、空状态按钮
- 登录态持久化于 localStorage（`blog_token` / `blog_user`），初始化经 `/api/auth/me` 校验恢复

### 测试（ATDD）
- 既有写接口测试全部携带管理员 Token（`admin_headers` 辅助函数），保留原 422/404/201/200/204 断言
- 新增登录/me/权限矩阵（401/403/200）/用户管理用例

## Risks / Trade-offs

- **既有测试破坏**：写接口加守卫后旧测试必红，须先改测试（红灯）再改接口（绿灯）
- **测试种子确定性**：`setup_db` 每用例重建表，须每用例重新 `seed_admin`，否则后续用例无管理员可登录
- **401 vs 422 顺序**：依赖框架校验顺序不可靠，缺字段断言一律用 admin 登录态请求规避
- **默认凭据风险**：`admin/admin123` 仅限本地教学，代码注释明确提醒通过环境变量修改
- **JWT 无吊销机制**：Token 7 天内有效，本期不做服务端注销（可接受的最小范围）
