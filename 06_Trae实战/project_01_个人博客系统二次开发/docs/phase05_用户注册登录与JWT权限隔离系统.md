# 阶段五：用户注册登录与 JWT 权限隔离系统 — 实施方案

## 一、概述（Summary）

在现有「个人博客系统」（FastAPI + SQLite + SQLAlchemy 2.0 + 单文件 HTML 前端）基础上，新增**用户与鉴权体系**：
- 新增 `users` 表（用户名 / bcrypt 密码哈希 / 角色）
- 提供登录接口颁发 **JWT**，受保护接口用依赖守卫校验
- 采用**角色权限制**：普通用户（reader）只读，管理员（admin）可增删改
- **仅管理员可创建账号**，不开放公开注册；系统启动时自动种子化首个管理员
- 前端**最小改造**：登录弹窗 + 按登录态显隐写/编辑/删除按钮 + Token 持久化

遵循项目红线：bcrypt 哈希、JWT 闭环、ATDD（先写测试再编码）、`uv` 管理依赖、分层清晰。

---

## 二、现状分析（Current State Analysis）

| 文件 | 现状 | 与本阶段关系 |
| :--- | :--- | :--- |
| `models.py` | 仅 `Post` 单表（title/content/category/tags/status/views/created_at/updated_at） | 需新增 `User` 表 |
| `schemas.py` | `PostCreate/PostUpdate/PostResponse/CategoryStat` | 需新增认证 DTO |
| `database.py` | SQLite 引擎 + `SessionLocal` + `get_db` | 无需改动（复用） |
| `main.py` | 6 个 REST 接口 + `/` 托管 index.html + CORS；lifespan 只建表 | 需加鉴权路由 + 保护写接口 + 种子管理员 |
| `index.html` | 写文章/编辑/删除按钮**无登录限制**，`apiFetch` 不带 Authorization | 需登录弹窗 + 按钮显隐 + Token |
| `test_main.py` | 全部接口测试（创建/更新/删除**未鉴权**） | 需改造既有测试 + 新增认证/权限测试 |
| `pyproject.toml` | 无 bcrypt / jwt 依赖 | 需 `uv add pyjwt bcrypt` |
| `.trae/rules/*`、`agents.md` | 已声明「bcrypt + JWT」红线 | 阶段完成后按惯例同步文档 |

**关键破坏性点**：现有 `test_create_post_*`、`test_update_*`、`test_delete_*` 均未携带 Token；一旦写接口加 `require_admin` 守卫，这些测试将全部变 401，**必须同步改造**（登录管理员后带 `Authorization` 头）。

---

## 三、目标与决策（Goals & Decisions）

用户已确认的决策：
1. **权限模型 = 角色权限制**：`reader` 只读，`admin` 可写；不做作者归属（`posts` 表**不新增** `author_id`）。
2. **账号来源 = 仅管理员创建**：不提供公开 `/api/auth/register`；管理员通过 `POST /api/users` 创建账号；首个管理员由启动种子化生成。
3. **前端范围 = 最小改造**：仅登录弹窗 + 按钮显隐 + Token 持久化；不展示作者信息、不做注册表单、不做用户管理 UI（用户管理仅 API，UI 留待后续阶段）。

补充合理假设（已记录，如不合意可调整）：
- 种子管理员：`admin` / `admin123`（本地教学项目默认值，注释提示上线前修改；密码可通过环境变量 `BLOG_ADMIN_PASSWORD` 覆盖）。
- JWT 有效期：**7 天**（`ACCESS_TOKEN_EXPIRE_MINUTES = 7*24*60`），采用 HS256。
- JWT 密钥：优先读环境变量 `BLOG_SECRET_KEY`，未设置时用开发默认值并注释警告。
- 密码强度：`password` 至少 6 位（Pydantic `min_length=6`）。
- 角色取值：`admin` / `reader`，非法角色 422 拒绝。
- 本期**不做**：refresh token、邮箱/验证码、找回密码、登录限流、审计日志、作者字段、用户管理前端页面。

---

## 四、方案设计（Design）

### 4.1 数据模型 — `models.py` 新增 `User`

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="reader")  # admin | reader
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
```

> 说明：`username` 唯一约束 + 索引；`password_hash` 仅存 bcrypt 哈希，绝不存明文；`role` 默认 `reader`。

### 4.2 认证模块 — 新增 `security.py`（新文件，职责：哈希 / JWT / 守卫）

保持分层清晰，将认证原语从 `main.py` 拆出，`main.py` 只管路由：

- 常量：`SECRET_KEY`（环境变量优先）、`ALGORITHM="HS256"`、`ACCESS_TOKEN_EXPIRE_MINUTES`
- `hash_password(raw) -> str`：`bcrypt.hashpw(raw.encode(), bcrypt.gensalt())`
- `verify_password(raw, hashed) -> bool`：`bcrypt.checkpw`
- `create_access_token(user) -> str`：`jwt.encode({"sub": str(user.id), "role": user.role, "exp": ...}, ...)`
- `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")`
- `get_current_user`（依赖）：解析 `Authorization: Bearer` → 解码 JWT（失败抛 401）→ 查库取 `User`（不存在抛 401）
- `require_admin`（依赖）：`get_current_user` 之上校验 `role == "admin"`，否则 **403**

### 4.3 Schema — `schemas.py` 新增

```python
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)

class UserBrief(BaseModel):
    id: int; username: str; role: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserBrief

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)
    role: Literal["admin", "reader"] = "reader"

class UserResponse(BaseModel):
    id: int; username: str; role: str; created_at: datetime
    model_config = {"from_attributes": True}
```

### 4.4 API 契约（新增 / 变更）

| 方法 | 路径 | 权限 | 说明 |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/auth/login` | 公开 | body `{username,password}` → `200 TokenResponse`；用户名或密码错误 → `401`；参数缺失/超长 → `422` |
| `GET` | `/api/auth/me` | 登录 | 返回当前用户 `UserResponse`；无/无效 Token → `401` |
| `GET` | `/api/posts` | 公开 | **不变** |
| `GET` | `/api/posts/{id}` | 公开 | **不变** |
| `GET` | `/api/categories` | 公开 | **不变** |
| `POST` | `/api/posts` | **仅 admin** | 未登录 `401` / 非 admin `403` |
| `PUT` | `/api/posts/{id}` | **仅 admin** | 未登录 `401` / 非 admin `403` |
| `DELETE` | `/api/posts/{id}` | **仅 admin** | 未登录 `401` / 非 admin `403` |
| `POST` | `/api/users` | **仅 admin** | body `{username,password,role}` → `201 UserResponse`；用户名已存在 → `409` |
| `GET` | `/api/users` | **仅 admin** | 用户列表 |

错误格式沿用 `{"detail": "..."}`。

### 4.5 种子管理员 — `main.py`

- 抽 `seed_admin(db)` 独立函数：`users` 表为空时创建 `admin/admin123`（role=admin）。
- `lifespan` 中 `create_all` 后调用 `seed_admin`。
- 测试侧（见 4.7）在每个用例重建表后也调用 `seed_admin`，保证确定性。

### 4.6 前端 — `index.html` 最小改造

- 新增**登录模态框**（复用既有 `.modal-overlay`/`.modal-panel` 玻璃拟态样式），含用户名/密码输入 + 登录按钮；错误时红色 Toast。
- 顶部导航右侧：未登录显示「登录」按钮；已登录显示用户名 + 「退出」按钮（清除 localStorage 并刷新界面）。
- `apiFetch`：从 `localStorage` 读取 Token，自动附带 `Authorization: Bearer <token>`；收到 `401` 时清除本地登录态并弹出登录框。
- 初始化时若有 Token：调 `GET /api/auth/me` 校验并恢复登录态（`currentUser = {id, username, role}`）。
- 按 `currentUser?.role === 'admin'` 显隐：`#btnNewPost`（写文章）、文章卡片的编辑/删除按钮、空状态「写第一篇文章」按钮。
- 登录态存 `localStorage`（key：`blog_token` / `blog_user`）。

### 4.7 测试 — `test_main.py`（ATDD）

**改造既有测试**（写接口全部带管理员 Token）：
- 新增辅助函数 `admin_headers(client)`：以种子管理员登录拿 Token，返回 `{"Authorization": f"Bearer {token}"}`。
- `setup_db` fixture 在 `create_all` 后调用 `seed_admin(TestSessionLocal())`，确保每个用例都有管理员可登录。
- 既有 `test_create_post_*` / `test_update_*` / `test_delete_*` 在请求中带上 `admin_headers`，**保留原断言**（如 422、404、201、200、204），避免依赖「401 与 422 谁先返回」的实现细节。

**新增测试**：
- 登录：成功返回 token+role；密码错误 401；用户不存在 401；缺字段 422。
- `GET /api/auth/me`：有效 token 200；无 token 401；伪造 token 401。
- 写接口权限：未登录 401；reader 登录后 POST/PUT/DELETE 403；admin 成功。
- 用户管理：无 token 401；reader 403；admin 创建成功 201；重复用户名 409；非法 role 422。
- 读接口保持公开：无 token 仍可 GET 列表/详情/分类。

### 4.8 依赖

`uv add pyjwt bcrypt`（更新 `pyproject.toml` + `uv.lock`）。bcrypt 直接用 `bcrypt` 库（避免 passlib 与新版 bcrypt 的兼容坑）。

---

## 五、改动文件清单（Files & Why/How）

| 文件 | 改动 | 原因 / 方式 |
| :--- | :--- | :--- |
| `pyproject.toml` | 加依赖 | `uv add pyjwt bcrypt` |
| `models.py` | 新增 `User` 表 | bcrypt 哈希 + 角色 + 唯一用户名 |
| `security.py`（新增） | 哈希 / JWT / `get_current_user` / `require_admin` | 认证原语独立分层，保持 `main.py` 只管路由 |
| `schemas.py` | 新增 5 个认证/用户 DTO | Pydantic 校验请求与响应 |
| `main.py` | 种子管理员 + 4 个新接口 + 3 个写接口加守卫 | 鉴权闭环、权限隔离 |
| `index.html` | 登录弹窗 + 按钮显隐 + Token 持久化 + 401 处理 | 前端最小闭环 |
| `test_main.py` | 改造既有写接口测试 + 新增认证/权限测试 | ATDD，保证全绿 |
| 文档同步 | `agents.md`、`.trae/rules/backend.md`、本阶段文档 | 项目惯例「每阶段同步文档」 |

> `database.py` 与 `Post` 模型**不改动**；`posts` 表不加 `author_id`（角色制决策）。

---

## 六、实施步骤（Tasks）

1. `uv add pyjwt bcrypt`
2. `models.py` 新增 `User` 模型
3. 新增 `security.py`（常量、哈希、JWT、守卫依赖）
4. `schemas.py` 新增认证/用户 DTO
5. `test_main.py`：先改造 `setup_db` + `admin_headers`，再改造既有写接口测试（红灯→绿），再新增认证/权限用例（红灯→绿），`uv run pytest -q` 全绿
6. `main.py`：种子管理员 + `/api/auth/login`、`/api/auth/me`、`/api/users`（GET/POST）+ 写接口挂 `require_admin`
7. `uv run pytest -q` 回归确认
8. `index.html` 前端改造（登录弹窗 / 按钮显隐 / Token / 401）
9. 启动 `uv run uvicorn main:app --reload --port 8000`，浏览器实测：未登录只读、登录 admin 后可写、reader 被拒、退出恢复只读、刷新后登录态保持
10. 同步文档（`agents.md`、`.trae/rules/backend.md`）

---

## 七、验证步骤（Verification）

- 自动化：`uv run pytest -q` 全绿（既有 + 新增用例）。
- 手工（浏览器）：见任务 9 清单，覆盖正常 / 未授权 / 越权三态。
- API 层抽查：`curl` 验证登录颁发 Token、无 Token 写接口返回 401、reader Token 返回 403。

---

## 八、风险与注意事项

- **既有测试破坏**：写接口加守卫后旧测试必红，须先改测试（ATDD 顺序）再改接口，避免「红灯堆叠」。
- **测试种子确定性**：`setup_db` 每用例重建表，必须每用例重新 `seed_admin`，否则后续用例无管理员可登录。
- **401 vs 422 顺序**：新接口测试对「缺字段」断言用 admin 登录态请求，规避依赖框架校验顺序。
- **明文密码红线**：`UserResponse` 等任何响应模型**禁止**序列化 `password_hash`。
- **种子默认密码**：`admin/admin123` 仅限本地教学，代码注释明确提醒上线前通过环境变量修改。
