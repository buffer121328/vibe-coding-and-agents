# 阶段二：后端工程与数据持久化 (Phase 2: Backend & SQLite)

> **阶段定位**：用最少、最清晰的代码实现 FastAPI 后端与 SQLite 数据库交互，完成文章的 CRUD 核心逻辑。

---

## 🛠️ 一、涉及的核心文件

```
project_03_个人博客系统/
├── database.py   # SQLite 引擎与 Session 获取
├── models.py     # Post 数据表模型
├── schemas.py    # Pydantic 校验与数据模式
└── main.py       # FastAPI 路由与 CRUD 业务逻辑
```

---

## ⚙️ 二、模块实现要点

### 1. `database.py`（极简数据库连接）
- 使用 SQLite 单文件数据库：`sqlite:///./blog.db`；
- 配置 `connect_args={"check_same_thread": False}`；
- 提供 `get_db()` 依赖注入函数。

### 2. `models.py`（ORM 模型）
- 定义 `Post` 表，包含字段：`id`, `title`, `content`, `category`, `tags`, `status`, `views`, `created_at`, `updated_at`。

### 3. `schemas.py`（数据校验）
- `PostCreate`：发布文章必填校验（标题限制 1~200 字，内容不能为空）；
- `PostUpdate`：修改文章可选字段；
- `PostResponse`：向前端返回的完整文章结构；
- `CategoryStat`：分类聚合统计。

### 4. `main.py`（路由与逻辑）
- 启动时自动建表：`Base.metadata.create_all(bind=engine)`；
- 开启 CORS 跨域：`CORSMiddleware`；
- 注册 6 个接口：
  - `GET /api/posts`（支持 `category`, `status`, `search` 过滤）
  - `GET /api/posts/{id}`（获取详情并自增 `views + 1`）
  - `POST /api/posts`（新增文章，返回 201）
  - `PUT /api/posts/{id}`（编辑修改文章）
  - `DELETE /api/posts/{id}`（删除文章，返回 204）
  - `GET /api/categories`（获取分类列表及统计）

---

## 📋 三、阶段推进核对清单

- [x] 1. 实现 `database.py` 数据库连接与会话；
- [x] 2. 实现 `models.py` 文章实体定义；
- [x] 3. 实现 `schemas.py` 请求与响应校验；
- [x] 4. 实现 `main.py` 路由与业务逻辑。
