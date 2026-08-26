## Context

博客系统为 FastAPI + SQLite + SQLAlchemy 2.0 + 单文件 HTML 前端，已有用户/JWT 权限隔离（`get_current_user` / `require_admin`）。当前 `GET /api/posts` 返回全量裸数组，无任何社交能力。本项目约定列表接口使用 `Page & PageSize` 分页并返回 `{items,total,page,page_size}`。见 proposal.md - Why 与 specs 的行为契约。

## Goals / Non-Goals

**Goals:**
- 新增 `comments` / `likes` 表，文章删除时级联清理
- 评论：发表（需登录）、分页列表（公开、时间升序楼层）、删除（作者或 admin）
- 点赞：幂等点赞/取消，`(post_id,user_id)` 唯一约束防刷，计数实时统计
- `/api/posts` 与评论列表统一分页契约
- 前端：分页导航、卡片社交徽标、阅读器点赞按钮、楼层评论区

**Non-Goals:**
- 不做评论回复（楼中楼）、@提及、富文本编辑器、评论审核
- 不做点赞用户列表、不展示「谁赞了」
- 不做 WebSocket/SSE 实时评论推送
- 不改动 `User` / `Post` 表结构与既有认证契约

## Decisions

### 社交计数采用「实时统计」而非「冗余计数字段」
用 `likes` / `comments` 表 `COUNT(*)` 实时统计，而非在 `Post` 上加 `like_count` / `comment_count` 冗余列。理由：唯一约束保证计数精确，杜绝冗余字段的读写漂移；文章量级在个人博客场景下 `GROUP BY` 统计开销可忽略。列表接口用 `IN + GROUP BY` 批量统计（`_post_counts`）避免逐篇 N+1 查询。`liked` 态通过 `get_optional_user`（`auto_error=False` 的 OAuth2 依赖）在未登录时返回 `None`，从而读接口保持公开。

### 评论列表按 `created_at + id` 双键升序
楼层语义要求最早评论为 1 楼；同一秒内的评论用 `id` 二次排序保证顺序稳定。分页时前端楼层号 = `(page-1)*page_size + 索引 + 1`。

### 点赞防刷 = 数据库唯一约束 + 接口幂等
`UniqueConstraint("post_id","user_id")` 在数据库层兜底重复点赞；接口侧「存在则跳过、不存在则新增」，重复调用不报错、不叠加。删除文章时手动级联 `DELETE` 点赞与评论（SQLite 默认未启用外键级联）。

### 分页参数校验统一放在 Query 层
`page: int = Query(1, ge=1)`、`page_size: int = Query(10, ge=1, le=50)`，由 FastAPI 返回 422，规避手写校验。

### 前端分页状态管理
首页 `page_size=9`（3×3 网格）。`loadPosts()` 从分页响应取 `items` 渲染、`total` 更新统计；切换分类/搜索时重置 `page=1`。评论区分页（`page_size=20`）用「加载更多」追加，楼层号按偏移累计。

## Risks / Trade-offs

- **分页契约破坏性变更** → 同步改造既有 5 个 `test_get_posts_*` 用例与前端 `loadPosts()`，保持测试先行（红灯→绿灯）
- **SQLite 外键默认不启用** → 删除文章手动级联清理点赞/评论，配套测试断言无孤儿数据
- **列表 N+1** → 统一用 `IN + GROUP BY` 批量统计，禁止逐篇 `COUNT`
- **401 vs 422 顺序** → 新接口「缺字段」断言用登录态请求，规避框架校验顺序依赖
- **`get_optional_user` 误抛 401** → 使用 `auto_error=False` 的 OAuth2 依赖，未登录返回 `None`，保证读接口公开

## Migration Plan

- 首次启动 `Base.metadata.create_all` 自动建 `comments` / `likes` 表；既有 `blog.db` 无需手工迁移（新表增量创建）
- 前端与后端同步发布（单文件工程，无灰度诉求）；若需回滚，`GET /api/posts` 恢复裸数组并还原前端即可
- 测试用内存 SQLite（StaticPool）每用例重建表，天然覆盖新表结构与级联逻辑

## Open Questions

无。
