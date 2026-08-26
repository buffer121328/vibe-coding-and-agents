## Why

博客系统目前**无任何鉴权**：任意访客都能增删改文章，写接口与读接口毫无区分。需要引入「用户 + JWT 权限隔离」体系，实现角色权限制（普通用户只读、管理员可写），并确保密码以 bcrypt 哈希安全存储。

## What Changes

- 新增 `users` 表（`username` 唯一 / `password_hash`(bcrypt) / `role`(admin|reader) / `created_at`）
- 新增认证接口：`POST /api/auth/login`（颁发 JWT）、`GET /api/auth/me`（当前用户）
- 新增用户管理接口：`POST /api/users`、`GET /api/users`（**仅 admin**）
- **BREAKING**：`POST/PUT/DELETE /api/posts` 由公开改为 **仅 admin**，未登录返回 `401`、非 admin 返回 `403`
- 新增 `security.py`（bcrypt 哈希 / JWT 颁发与校验 / `get_current_user`、`require_admin` 守卫依赖）
- 启动时自动种子化首个管理员（`admin`），默认密码可经环境变量覆盖
- 前端最小改造：登录弹窗、Token 持久化（localStorage）、按登录态显隐写/编辑/删除按钮、401 自动弹登录框
- 新增依赖：`pyjwt`、`bcrypt`

## Capabilities

### New Capabilities
- `user-auth-jwt`: 用户注册/登录、JWT 鉴权与角色权限隔离（管理员可写、读者只读）

### Modified Capabilities
- `blog-frontend`: 前端需支持登录态、按钮按角色显隐、Token 持久化与 401 处理

## Impact

- 修改文件：`models.py`（+User）、`schemas.py`（+认证 DTO）、`main.py`（+认证/用户接口 + 写接口守卫 + 种子管理员）、`index.html`（登录弹窗/按钮显隐/Token）、`test_main.py`（既有写接口测试改造 + 新增认证/权限用例）
- 新增文件：`security.py`
- 依赖：`uv add pyjwt bcrypt`
- 数据库：新增 `users` 表（首次启动自动建表 + 种子管理员）
