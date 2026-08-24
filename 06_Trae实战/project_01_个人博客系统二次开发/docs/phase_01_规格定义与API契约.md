# 阶段一：目录结构定义与极简规格契约 (Phase 1: Structure & Specs)

> **阶段定位**：确定项目极简目录结构、SQLite 数据表设计与 RESTful API 契约，用最简单直接的方式指引后续开发。

---

## 📁 一、项目极简目录结构定义

为了保持极简、轻量、开箱即用，整个博客系统采用标准轻量分层结构，杜绝过度封装：

```
project_03_个人博客系统/
├── docs/                         # 📚 实施推进阶段文档
│   ├── README.md                 # 实施阶段总览与路线图
│   ├── phase_01_规格定义与API契约.md  # 阶段一：目录结构、数据模型与API契约 (当前)
│   ├── phase_02_后端工程与数据持久化.md # 阶段二：FastAPI 与 SQLite CRUD 实现
│   ├── phase_03_响应式前端与Markdown引擎.md # 阶段三：TailwindCSS 与 Markdown 单页交互
│   └── phase_04_全链路联调与验收交付.md # 阶段四：前后端联调与自测交付
├── database.py                   # 🗄️ SQLite 数据库连接配置与 Session 获取
├── models.py                     # 🧱 SQLAlchemy ORM 数据模型 (Post 文章表)
├── schemas.py                    # 🔍 Pydantic 数据校验 (创建/更新/返回结构)
├── main.py                       # 🚀 FastAPI 主入口、RESTful 路由与静态页面托管
├── index.html                    # 🎨 现代暗黑单页前端 (TailwindCSS CDN + Marked.js)
├── pyproject.toml                # ⚡ uv 项目依赖管理配置文件
└── README.md                     # 📖 项目快速启动与运行说明
```

### 核心文件职责一览：
1. **`database.py`**：仅负责创建 SQLite 引擎（`blog.db`）和提供数据库会话 `get_db`；
2. **`models.py`**：仅定义单张 `Post` 表结构，映射数据库字段；
3. **`schemas.py`**：定义文章新增（`PostCreate`）、修改（`PostUpdate`）和返回（`PostResponse`）的字段规范；
4. **`main.py`**：挂载 CORS 跨域、注册文章增删改查 6 个 API 接口，并托管 `index.html`；
5. **`index.html`**：纯单文件前端，引入 TailwindCSS 与 Marked.js，实现列表瀑布流、分类筛选、Markdown 双栏写文章与阅读器。

---

## 🗄️ 二、极简数据模型设计 (`posts` 表)

单文件 SQLite 数据库存储（`blog.db`），仅包含单张核心表 `posts`：

| 字段名 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | 主键自增 | 文章唯一 ID |
| `title` | `VARCHAR(200)` | 必填 | 文章标题 |
| `content` | `TEXT` | 必填 | 文章 Markdown 正文 |
| `category` | `VARCHAR(50)` | `'默认分类'` | 文章分类名称 |
| `tags` | `VARCHAR(200)` | `''` | 标签（逗号分隔，如 `"Python,FastAPI"`） |
| `status` | `VARCHAR(20)` | `'published'` | 状态：`published`（已发布）或 `draft`（草稿） |
| `views` | `INTEGER` | `0` | 文章总阅读量（打开详情自增 1） |
| `created_at` | `DATETIME` | 当前时间 | 创建时间 |
| `updated_at` | `DATETIME` | 当前时间 | 最近修改时间 |

---

## 🌐 三、极简 RESTful API 契约

全套 API 统一以 `/api` 开头，简洁明了：

| HTTP 方法 | 接口路径 | 功能说明 | 请求参数 / 请求体 | 响应状态码 |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/posts` | 获取文章列表 | Query: `category`, `status`, `search` | `200 OK` |
| `GET` | `/api/posts/{id}` | 获取文章详情（阅读量自增） | Query: `increment_views=true` | `200 OK` / `404` |
| `POST` | `/api/posts` | 发布新文章 | Body (JSON): `title`, `content`, `category`, `tags`, `status` | `201 Created` / `422` |
| `PUT` | `/api/posts/{id}` | 修改编辑文章 | Body (JSON): `title`, `content`, `category`, `tags`, `status` (可选) | `200 OK` / `404` |
| `DELETE` | `/api/posts/{id}` | 删除文章 | 无 | `204 No Content` / `404` |
| `GET` | `/api/categories` | 获取分类列表及文章数统计 | 无 | `200 OK` |

---

## 📋 四、阶段推进核对清单

- [x] 1. 明确极简扁平的 5 核心文件目录结构（`database.py`, `models.py`, `schemas.py`, `main.py`, `index.html`）；
- [x] 2. 锁定 SQLite 单表设计与字段定义；
- [x] 3. 规范标准清晰的 6 个 RESTful CRUD 接口。
