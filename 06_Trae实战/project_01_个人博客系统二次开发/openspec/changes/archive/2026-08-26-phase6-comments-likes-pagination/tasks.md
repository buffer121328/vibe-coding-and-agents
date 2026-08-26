## 1. 数据模型与认证依赖

- [x] 1.1 `models.py` 新增 `Comment` 表（post_id/user_id 外键 + content + created_at）
- [x] 1.2 `models.py` 新增 `Like` 表（post_id/user_id 外键 + created_at + `(post_id,user_id)` 唯一约束）
- [x] 1.3 `security.py` 新增 `oauth2_scheme_optional`（auto_error=False）与 `get_optional_user`（未登录返回 None 不抛 401）

## 2. Schema DTO

- [x] 2.1 `schemas.py` 扩展 `PostResponse`：新增 `likes` / `comment_count` / `liked`（带默认值）
- [x] 2.2 `schemas.py` 新增 `CommentCreate` / `CommentResponse`（含 username）
- [x] 2.3 `schemas.py` 新增 `LikeResponse` / `PaginatedPosts` / `PaginatedComments`

## 3. 测试（ATDD 红灯）

- [x] 3.1 改造既有 `test_get_posts_empty/list/filter_category/filter_status/search` 断言适配分页结构（红灯）
- [x] 3.2 新增分页用例：page/page_size 正确切页、`page=0`/`page_size=0`/`page_size=100` 返回 422
- [x] 3.3 新增评论用例：发表（201/未登录 401/空内容 422/文章不存在 404）、列表（公开/空/分页/升序楼层/404）、删除（作者 204/admin 204/他人 403/未登录 401/不存在 404）
- [x] 3.4 新增点赞用例：点赞 200/重复点赞幂等/取消 200/未点赞时取消幂等/未登录 401/文章不存在 404
- [x] 3.5 新增社交计数用例：详情与列表响应含 likes/comment_count/liked（含已点赞回显）
- [x] 3.6 新增级联用例：删除文章后其点赞与评论一并清除
- [x] 3.7 运行 `uv run pytest -q` 确认新用例红灯（既有改造后全绿）

## 4. 后端接口实现

- [x] 4.1 `main.py` 辅助函数：`_post_counts`（IN+GROUP BY 批量统计）、`_liked_post_ids`、`_post_response`
- [x] 4.2 `main.py` `GET /api/posts` 分页改造（page/page_size + `PaginatedPosts`，保留过滤）
- [x] 4.3 `main.py` `GET /api/posts/{id}` 携带 likes/comment_count/liked
- [x] 4.4 `main.py` 评论接口：`GET/POST /api/posts/{id}/comments`、`DELETE /api/comments/{id}`（作者或 admin）
- [x] 4.5 `main.py` 点赞接口：`POST/DELETE /api/posts/{id}/like`（幂等）
- [x] 4.6 `main.py` `DELETE /api/posts/{id}` 级联清理点赞与评论
- [x] 4.7 `uv run pytest -q` 全绿

## 5. 前端改造

- [x] 5.1 `index.html` `loadPosts()` 解析分页响应，新增 `pageInfo` 状态；导航统计改用 `total`；切换分类/搜索重置 page=1
- [x] 5.2 首页网格下方新增「上一页 / 第 x 页 / 下一页」分页控件（首末页禁用）
- [x] 5.3 文章卡片元信息增加点赞数与评论数徽标
- [x] 5.4 阅读器新增点赞按钮（未登录弹登录框；点击切换点赞/取消并即时更新状态与计数）
- [x] 5.5 阅读器新增楼层评论区：评论列表（N楼/作者/时间/内容）、发表输入框（登录显隐）、删除按钮（作者或 admin）、加载更多
- [x] 5.6 保持玻璃拟态风格，无 JS 报错

## 6. 联调验收

- [x] 6.1 启动服务（8001）curl 验证：登录拿 Token、点赞两次计数仍 1（幂等）、未登录点赞 401、评论列表分页结构、他人评论删除 403
- [x] 6.2 浏览器实测：首页分页翻页、卡片社交徽标、阅读器点赞填充/取消、评论楼层渲染与发表/删除/未登录引导、刷新后登录态与已点赞态保持
- [x] 6.3 检查浏览器控制台无 JS 错误

## 7. 文档与归档

- [x] 7.1 更新 `agents.md` 与 `.trae/rules/backend.md`（项目目录/文件清单/契约）
- [x] 7.2 `openspec validate` + `openspec sync` + `openspec archive` 归档阶段六
