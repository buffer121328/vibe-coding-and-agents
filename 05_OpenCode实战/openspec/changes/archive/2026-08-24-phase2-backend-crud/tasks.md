## 1. 数据库层

- [x] 1.1 实现 `database.py`：SQLite 引擎（`blog.db`）+ `get_db()` 依赖注入
- [x] 1.2 实现 `models.py`：`Post` ORM 模型（9 字段，含默认值）

## 2. 数据校验层

- [x] 2.1 实现 `schemas.py`：`PostCreate`（标题 1~200 字 + 内容非空）、`PostUpdate`（可选字段）、`PostResponse`、`CategoryStat`

## 3. 路由与业务逻辑

- [x] 3.1 重写 `main.py`：FastAPI 实例 + CORS 中间件 + 启动自动建表
- [x] 3.2 实现 `GET /api/posts`（支持 category/status/search 过滤）
- [x] 3.3 实现 `GET /api/posts/{id}`（含 increment_views 自增阅读量）
- [x] 3.4 实现 `POST /api/posts`（返回 201）
- [x] 3.5 实现 `PUT /api/posts/{id}`（部分更新）
- [x] 3.6 实现 `DELETE /api/posts/{id}`（返回 204）
- [x] 3.7 实现 `GET /api/categories`（分类聚合统计）

## 4. 验收测试

- [x] 4.1 编写 pytest 测试：文章 CRUD 全流程（创建/列表/详情/编辑/删除）
- [x] 4.2 编写 pytest 测试：异常场景（404/422）
- [x] 4.3 编写 pytest 测试：分类统计接口
- [x] 4.4 运行 `pytest -q` 确认全部通过
