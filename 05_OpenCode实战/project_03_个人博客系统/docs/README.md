# 极客个人博客系统：实施推进总览

本项目是一个**轻量、现代、开箱即用**的个人全栈博客系统（FastAPI + SQLite + TailwindCSS + Markdown），按照 OpenSpec 理念划分为 4 个推进阶段。

---

## 📁 项目目录结构

```
project_03_个人博客系统/
├── docs/                         # 📚 实施推进阶段文档
│   ├── README.md                 # 实施阶段总览与路线图 (当前)
│   ├── phase_01_规格定义与API契约.md  # 阶段一：目录结构、数据模型与API契约
│   ├── phase_02_后端工程与数据持久化.md # 阶段二：FastAPI 与 SQLite CRUD 实现
│   ├── phase_03_响应式前端与Markdown引擎.md # 阶段三：TailwindCSS 与 Markdown 单页交互
│   └── phase_04_全链路联调与验收交付.md # 阶段四：前后端联调与自测交付
├── database.py                   # 🗄️ SQLite 数据库连接与会话
├── models.py                     # 🧱 SQLAlchemy ORM 数据模型 (Post 表)
├── schemas.py                    # 🔍 Pydantic 请求与响应校验
├── main.py                       # 🚀 FastAPI 主服务入口与 CRUD 路由
├── index.html                    # 🎨 现代响应式单页前端 (TailwindCSS + Marked.js)
├── pyproject.toml                # ⚡ uv 依赖配置
└── README.md                     # 📖 项目快速启动说明
```

---

## 🗺️ 4 大推进阶段与目标

| 阶段 | 文档 | 核心任务 |
| :--- | :--- | :--- |
| **阶段一** | [phase_01_规格定义与API契约.md](./phase_01_规格定义与API契约.md) | 确定极简目录结构、SQLite 单表字段与 RESTful API 契约 |
| **阶段二** | [phase_02_后端工程与数据持久化.md](./phase_02_后端工程与数据持久化.md) | 实现 `database.py`、`models.py`、`schemas.py` 与 `main.py` 核心 CRUD 接口 |
| **阶段三** | [phase_03_响应式前端与Markdown引擎.md](./phase_03_响应式前端与Markdown引擎.md) | 实现单文件 `index.html`，支持卡片流、分类过滤、Markdown 双栏编辑与阅读器 |
| **阶段四** | [phase_04_全链路联调与验收交付.md](./phase_04_全链路联调与验收交付.md) | 前后端联调自测、跨域配置、异常防御与一键启动运行 |

---

## ⚡ 常用命令

```bash
# 同步依赖
uv sync

# 启动全栈服务 (前后端一体化)
uv run uvicorn main:app --reload --port 8000
```
- 前端页面：`http://127.0.0.1:8000`
- 接口文档：`http://127.0.0.1:8000/docs`
