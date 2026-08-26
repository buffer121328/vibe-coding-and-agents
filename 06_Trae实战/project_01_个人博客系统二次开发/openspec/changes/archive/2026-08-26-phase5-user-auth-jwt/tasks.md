## 1. 依赖与数据模型

- [x] 1.1 `uv add pyjwt bcrypt`
- [x] 1.2 `models.py` 新增 `User` 表（username 唯一 / password_hash / role / created_at）

## 2. 认证模块与 DTO

- [x] 2.1 新增 `security.py`：bcrypt 哈希、JWT 编解码（HS256/7天）、`get_current_user`、`require_admin` 守卫
- [x] 2.2 `schemas.py` 新增 `LoginRequest` / `TokenResponse` / `UserCreate` / `UserResponse` / `UserBrief`

## 3. 后端接口与守卫（ATDD）

- [x] 3.1 `test_main.py` 改造 `setup_db`（每用例 `seed_admin`）+ 新增 `admin_headers` / `reader_headers` 辅助
- [x] 3.2 改造既有写接口测试携带管理员 Token，先红灯后绿灯
- [x] 3.3 新增登录/me/权限隔离/用户管理测试用例，`uv run pytest -q` 全绿
- [x] 3.4 `main.py`：`seed_admin` + lifespan 种子化管理员
- [x] 3.5 `main.py`：新增 `POST /api/auth/login`、`GET /api/auth/me`
- [x] 3.6 `main.py`：新增 `POST /api/users`、`GET /api/users`（仅 admin）
- [x] 3.7 `main.py`：`POST/PUT/DELETE /api/posts` 挂 `require_admin` 守卫

## 4. 前端改造

- [x] 4.1 新增登录模态框（玻璃拟态样式 + 自动聚焦 + Enter 提交）
- [x] 4.2 `apiFetch` 自动附带 `Authorization: Bearer <token>`，401 清除登录态并弹登录框
- [x] 4.3 登录态 localStorage 持久化（`blog_token` / `blog_user`），初始化经 `/api/auth/me` 恢复
- [x] 4.4 按 `role === 'admin'` 显隐写文章/编辑/删除/空状态按钮；导航登录区切换
- [x] 4.5 ESC 与遮罩点击关闭登录框

## 5. 联调验收

- [x] 5.1 启动服务（8001）curl 验证登录颁发 Token、401/403 权限矩阵、用户管理
- [x] 5.2 浏览器实测：未登录只读 → 登录 admin 后可写（发布成功）→ 刷新保持登录态 → 退出恢复只读
- [x] 5.3 检查浏览器控制台无 JS 错误
