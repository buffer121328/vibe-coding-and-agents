## Purpose

提供博客系统文章的完整 CRUD 能力：数据库连接、ORM 模型定义、Pydantic 请求/响应校验、6 个 RESTful 接口，为前端提供可靠的文章管理后端。

## ADDED Requirements

### Requirement: 数据库连接与会话管理
系统 SHALL 使用 SQLite 单文件数据库（`blog.db`），提供依赖注入的数据库会话。

#### Scenario: 正常获取数据库会话
- **WHEN** 应用启动并调用 `get_db()` 依赖
- **THEN** 返回可用的 SQLAlchemy Session 对象

#### Scenario: 数据库文件自动创建
- **WHEN** 应用首次启动且 `blog.db` 不存在
- **THEN** 自动创建数据库文件并建立 `posts` 表

### Requirement: 文章 ORM 模型
系统 SHALL 定义 `Post` 表，包含 9 个字段，支持完整的文章数据存储。

#### Scenario: Post 表结构完整
- **WHEN** 应用启动并执行 `Base.metadata.create_all`
- **THEN** 创建包含字段 `id`、`title`、`content`、`category`、`tags`、`status`、`views`、`created_at`、`updated_at` 的 `posts` 表

#### Scenario: 字段默认值正确
- **WHEN** 创建新文章时未指定 `category`、`tags`、`status`、`views`
- **THEN** `category` 默认为 `'默认分类'`，`tags` 默认为 `''`，`status` 默认为 `'published'`，`views` 默认为 `0`

### Requirement: Pydantic 请求/响应校验
系统 SHALL 使用 Pydantic 校验所有 API 请求与响应，确保数据合法性。

#### Scenario: 创建文章校验通过
- **WHEN** 请求体包含 `title`（1~200 字）和 `content`（非空）
- **THEN** 返回 201 Created 及完整文章对象

#### Scenario: 创建文章缺少标题
- **WHEN** 请求体缺少 `title` 字段
- **THEN** 返回 422 Unprocessable Entity 及详细错误信息

#### Scenario: 创建文章标题超长
- **WHEN** `title` 字段超过 200 字符
- **THEN** 返回 422 Unprocessable Entity 及详细错误信息

#### Scenario: 创建文章内容为空
- **WHEN** `content` 字段为空字符串
- **THEN** 返回 422 Unprocessable Entity 及详细错误信息

### Requirement: 获取文章列表
系统 SHALL 支持按分类、状态、关键词过滤获取文章列表。

#### Scenario: 获取全部文章
- **WHEN** 请求 `GET /api/posts` 不带任何查询参数
- **THEN** 返回 200 OK 及所有文章列表（按创建时间倒序）

#### Scenario: 按分类过滤
- **WHEN** 请求 `GET /api/posts?category=Python`
- **THEN** 返回 200 OK 及仅包含 `category='Python'` 的文章

#### Scenario: 按状态过滤
- **WHEN** 请求 `GET /api/posts?status=draft`
- **THEN** 返回 200 OK 及仅包含 `status='draft'` 的文章

#### Scenario: 关键词搜索
- **WHEN** 请求 `GET /api/posts?search=FastAPI`
- **THEN** 返回 200 OK 及标题或内容包含 `FastAPI` 的文章

### Requirement: 获取文章详情并自增阅读量
系统 SHALL 返回文章详情，并在指定时自增阅读量。

#### Scenario: 获取详情且自增阅读量
- **WHEN** 请求 `GET /api/posts/1?increment_views=true`
- **THEN** 返回 200 OK 及文章详情，`views` 字段自增 1

#### Scenario: 获取详情不自增
- **WHEN** 请求 `GET /api/posts/1` 不带 `increment_views` 参数
- **THEN** 返回 200 OK 及文章详情，`views` 不变

#### Scenario: 文章不存在
- **WHEN** 请求 `GET /api/posts/9999`
- **THEN** 返回 404 Not Found

### Requirement: 发布新文章
系统 SHALL 支持创建新文章，返回 201 状态码。

#### Scenario: 成功发布文章
- **WHEN** 请求 `POST /api/posts` 且请求体合法
- **THEN** 返回 201 Created 及新文章完整信息（含自增 `id` 和时间戳）

### Requirement: 修改编辑文章
系统 SHALL 支持部分字段更新文章内容。

#### Scenario: 成功修改文章
- **WHEN** 请求 `PUT /api/posts/1` 且文章存在
- **THEN** 返回 200 OK 及更新后的文章信息

#### Scenario: 修改不存在的文章
- **WHEN** 请求 `PUT /api/posts/9999`
- **THEN** 返回 404 Not Found

### Requirement: 删除文章
系统 SHALL 支持删除文章，返回 204 无内容状态码。

#### Scenario: 成功删除文章
- **WHEN** 请求 `DELETE /api/posts/1` 且文章存在
- **THEN** 返回 204 No Content

#### Scenario: 删除不存在的文章
- **WHEN** 请求 `DELETE /api/posts/9999`
- **THEN** 返回 404 Not Found

### Requirement: 获取分类列表及统计
系统 SHALL 返回所有分类名称及对应的文章数量。

#### Scenario: 获取分类统计
- **WHEN** 请求 `GET /api/categories`
- **THEN** 返回 200 OK 及分类列表，每项包含 `category` 名称和 `count` 文章数
