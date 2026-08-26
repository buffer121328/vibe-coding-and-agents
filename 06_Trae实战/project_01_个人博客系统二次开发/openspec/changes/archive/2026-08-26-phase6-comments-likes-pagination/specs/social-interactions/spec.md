## Purpose

为博客系统提供评论与点赞社交能力：读者可在文章下发表/浏览/删除评论，并可对文章点赞/取消点赞；点赞通过唯一约束去重防刷，计数实时统计；文章与评论列表携带社交计数。

## ADDED Requirements

### Requirement: 发表评论
系统 SHALL 提供 `POST /api/posts/{post_id}/comments` 接口，登录用户提交 `{content}` 后为指定文章创建评论，返回 201 与评论信息（含作者用户名与创建时间）。

#### Scenario: 登录用户发表评论
- **WHEN** 登录用户向存在的文章提交合法内容（1~1000 字符）
- **THEN** 接口返回 201 与评论信息，包含 `id/post_id/user_id/username/content/created_at`

#### Scenario: 未登录发表评论
- **WHEN** 未携带有效 Token 调用发表评论接口
- **THEN** 接口返回 401

#### Scenario: 评论内容为空或超长
- **WHEN** 提交空内容或超过 1000 字符
- **THEN** 接口返回 422

#### Scenario: 文章不存在
- **WHEN** 对不存在的文章发表评论
- **THEN** 接口返回 404

### Requirement: 评论列表（分页 + 楼层升序）
系统 SHALL 提供 `GET /api/posts/{post_id}/comments` 接口，公开返回该文章的分页评论列表，按创建时间升序排列（最早评论为 1 楼），响应结构为 `{items, total, page, page_size}`。

#### Scenario: 查看文章评论
- **WHEN** 任意访客请求存在的文章的评论列表
- **THEN** 接口返回 200 与分页结构，评论按时间升序排列，每条含作者用户名

#### Scenario: 无评论
- **WHEN** 文章尚无评论
- **THEN** 接口返回 200，`items` 为空数组且 `total` 为 0

#### Scenario: 评论分页
- **WHEN** 指定 `page` / `page_size` 参数请求评论列表
- **THEN** 返回对应页码的评论子集与 `total` 元信息；非法分页参数（如 `page=0`、`page_size=0` 或大于 50）返回 422

#### Scenario: 文章不存在
- **WHEN** 请求不存在文章的评论列表
- **THEN** 接口返回 404

### Requirement: 删除评论
系统 SHALL 提供 `DELETE /api/comments/{comment_id}` 接口，仅评论作者本人或 admin 可删除；删除成功后返回 204。

#### Scenario: 评论作者删除
- **WHEN** 评论作者本人携带有效 Token 删除自己的评论
- **THEN** 接口返回 204，评论被删除

#### Scenario: 管理员删除任意评论
- **WHEN** admin 角色用户删除任意评论
- **THEN** 接口返回 204

#### Scenario: 非作者非管理员删除
- **WHEN** 既非评论作者也非 admin 的用户删除他人评论
- **THEN** 接口返回 403

#### Scenario: 未登录删除
- **WHEN** 未携带有效 Token 调用删除评论接口
- **THEN** 接口返回 401

#### Scenario: 评论不存在
- **WHEN** 删除不存在的评论
- **THEN** 接口返回 404

### Requirement: 点赞与取消点赞（幂等防刷）
系统 SHALL 提供 `POST /api/posts/{post_id}/like` 与 `DELETE /api/posts/{post_id}/like` 接口，登录用户对文章点赞/取消点赞；同一用户对同一文章最多一条点赞记录（数据库唯一约束兜底），重复点赞不叠加计数，接口幂等。点赞数实时统计。

#### Scenario: 登录用户点赞
- **WHEN** 登录用户对存在的文章调用点赞接口
- **THEN** 接口返回 200 与 `{liked: true, likes: N}`，点赞数加 1

#### Scenario: 重复点赞不叠加
- **WHEN** 同一用户对同一文章重复调用点赞接口
- **THEN** 接口仍返回 200 `{liked: true, likes: N}`，但点赞数不重复累加

#### Scenario: 取消点赞
- **WHEN** 已点赞的用户调用取消点赞接口
- **THEN** 接口返回 200 与 `{liked: false, likes: N}`，点赞数减 1

#### Scenario: 未点赞时取消点赞
- **WHEN** 尚未点赞的用户调用取消点赞接口
- **THEN** 接口返回 200 `{liked: false, likes: N}`，幂等不报错

#### Scenario: 未登录点赞
- **WHEN** 未携带有效 Token 调用点赞或取消点赞接口
- **THEN** 接口返回 401

#### Scenario: 文章不存在
- **WHEN** 对不存在的文章点赞或取消点赞
- **THEN** 接口返回 404

### Requirement: 文章社交计数
系统 SHALL 在文章详情 `GET /api/posts/{post_id}` 与文章列表 `GET /api/posts` 的响应中携带社交字段：`likes`（点赞数）、`comment_count`（评论数）、`liked`（当前登录用户是否已点赞；未登录为 `false`）。

#### Scenario: 详情携带社交计数
- **WHEN** 访客请求文章详情
- **THEN** 响应包含 `likes`、`comment_count`、`liked` 字段

#### Scenario: 已点赞状态回显
- **WHEN** 已对该文章点赞的登录用户请求详情
- **THEN** 响应中 `liked` 为 `true`；未点赞或未登录时为 `false`

#### Scenario: 列表携带社交计数
- **WHEN** 请求文章列表
- **THEN** 每条文章均包含 `likes`、`comment_count`、`liked` 字段
