# api-pagination Specification

## Purpose
为列表类接口（文章列表、评论列表）建立统一的 Page & PageSize 参数化分页契约，返回 `{items, total, page, page_size}` 元信息，避免全量返回导致的数据量与响应体积问题。
## Requirements
### Requirement: 文章列表分页
系统 SHALL 将 `GET /api/posts` 改造为分页接口：支持 `page`（≥1，默认 1）与 `page_size`（1~50，默认 10）Query 参数，响应结构为 `{items, total, page, page_size}`；`total` 为满足过滤条件的总文章数。既有 `category` / `status` / `search` 过滤保持不变。

#### Scenario: 默认返回第一页
- **WHEN** 不指定分页参数请求文章列表
- **THEN** 返回 200 与 `{items, total, page: 1, page_size: 10}`，`items` 为最新文章按创建时间倒序的前 10 条

#### Scenario: 指定页码与每页条数
- **WHEN** 指定 `page=2&page_size=5` 请求文章列表
- **THEN** 返回第 2 页的 5 条文章，`page`/`page_size` 回显请求值，`total` 为总数

#### Scenario: 分页与过滤组合
- **WHEN** 带分类/状态/搜索过滤并指定分页参数
- **THEN** 过滤结果同样按分页返回，`total` 为过滤后的总数

#### Scenario: 空数据分页
- **WHEN** 没有任何文章（或过滤后无结果）
- **THEN** 返回 200，`items` 为空数组，`total` 为 0

#### Scenario: 非法分页参数
- **WHEN** 提交 `page=0`、`page_size=0` 或 `page_size>50`
- **THEN** 接口返回 422

### Requirement: 删除文章级联清理社交数据
系统 SHALL 在删除文章（`DELETE /api/posts/{post_id}`）时同步删除该文章的全部点赞与评论，避免产生孤儿社交数据。

#### Scenario: 删除文章后点赞评论清零
- **WHEN** admin 删除一篇含点赞与评论的文章
- **THEN** 接口返回 204，且该文章的点赞与评论记录一并被删除

