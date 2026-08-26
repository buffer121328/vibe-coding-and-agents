## Why

博客系统已具备文章 CRUD、用户/JWT 权限隔离，但缺少社交互动（读者无法评论、无法点赞），且文章/评论列表为全量裸数组返回，数据量增长后加载缓慢、无法翻页。需要引入「评论 + 点赞」社交能力，并对列表接口做 Page & PageSize 分页重构。

## What Changes

- 新增 `comments` 表（`post_id`/`user_id` 外键，文章 ↔ 评论一对多）与 `likes` 表（`(post_id, user_id)` 唯一约束，点赞去重防刷）
- 新增评论接口：`GET/POST /api/posts/{id}/comments`（列表分页 + 发表需登录）、`DELETE /api/comments/{id}`（作者或 admin 可删）
- 新增点赞接口：`POST/DELETE /api/posts/{id}/like`（幂等，未登录 401，计数实时 `COUNT(*)`）
- **BREAKING**：`GET /api/posts` 响应由裸数组改为分页对象 `{items, total, page, page_size}`，新增 `page`/`page_size` Query 参数
- **BREAKING**：`GET /api/posts/{id}` 与 `GET /api/posts` 的 `PostResponse` 新增 `likes` / `comment_count` / `liked` 字段（`liked` 表示当前登录用户是否已点赞，未登录为 `false`）
- 删除文章时级联清理其点赞与评论
- `security.py` 新增 `get_optional_user`（读接口展示已点赞态但不强制登录）
- 前端：首页分页导航、文章卡片点赞/评论数徽标、阅读器内点赞按钮与「楼层评论」渲染

## Capabilities

### New Capabilities
- `social-interactions`: 评论系统（发表/分页列表/删除权限）与点赞系统（幂等点赞/取消、去重防刷、社交计数）
- `api-pagination`: 列表接口统一 Page & PageSize 分页契约（`/api/posts` 与评论列表，返回 items/total/page/page_size）

### Modified Capabilities
- `blog-frontend`: 前端需支持分页导航、文章卡片社交徽标、阅读器内点赞与楼层评论渲染

## Impact

- 修改文件：`models.py`（+Comment/+Like）、`schemas.py`（PostResponse 扩展 + 评论/点赞/分页 DTO）、`security.py`（+get_optional_user）、`main.py`（分页改造 + 评论/点赞路由 + 删除级联）、`index.html`（分页/点赞/评论楼层）、`test_main.py`（既有列表断言改造 + 新增用例）
- 数据库：新增 `comments`、`likes` 表（首次启动自动建表）
- 兼容性：`GET /api/posts` 与 `GET /api/posts/{id}` 响应结构变化，前端与既有测试需同步适配
