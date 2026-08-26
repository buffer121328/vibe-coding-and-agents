# ai-enrichment Specification

## Purpose
为博客系统注入 AI 原生能力：通过 OpenAI 兼容接口自动生成文章 100 字导读摘要与内容感知标签，提供编辑器灵感副驾（摘要/标签/标题/分类建议）与存量批量回填；未配置 API Key 时优雅降级，博客主流程完全不受影响。
## Requirements
### Requirement: AI 能力状态探测
系统 SHALL 提供 `GET /api/ai/status` 公开接口，返回 AI 能力是否启用及当前模型与供应商信息，供前端决定是否展示 AI 面板。

#### Scenario: 已配置 API Key
- **WHEN** 后端已配置 `LLM_API_KEY`
- **THEN** 接口返回 200 与 `{enabled: true, model, provider}`

#### Scenario: 未配置 API Key
- **WHEN** 后端未配置 `LLM_API_KEY`
- **THEN** 接口返回 200 与 `{enabled: false, model, provider}`

### Requirement: 编辑器灵感生成
系统 SHALL 提供 `POST /api/ai/generate` 接口（仅 admin），根据文章标题与正文一次性生成 摘要 / 标签 / 标题 / 分类 建议，返回 `AIGenerateResponse`。

#### Scenario: 管理员生成灵感
- **WHEN** admin 提交合法 `{title, content, category?}`
- **THEN** 接口返回 200 与 `{summary, tags[], title_suggestion, category_suggestion}`
- **AND** `summary` 为约 100 字中文导读，`tags` 为 3~5 个标签

#### Scenario: 未登录或非 admin
- **WHEN** 未携带 Token 或由 reader 调用
- **THEN** 接口分别返回 401 或 403

#### Scenario: 未配置 API Key
- **WHEN** 后端未配置 `LLM_API_KEY`
- **THEN** 接口返回 503，提示未配置

#### Scenario: 大模型调用失败
- **WHEN** 上游 LLM 调用或 JSON 解析失败
- **THEN** 接口返回 502 并携带失败原因

### Requirement: 文章导读字段
系统 SHALL 在 `posts` 表新增 `summary` 列存储 AI 100 字导读（空串表示未生成），并在文章详情 `GET /api/posts/{id}` 与列表 `GET /api/posts` 的 `PostResponse` 中携带 `summary` 字段；`POST /api/posts` 与 `PUT /api/posts/{id}` 允许人工预填 `summary`。

#### Scenario: 响应携带摘要
- **WHEN** 访客请求文章详情或列表
- **THEN** 每条文章响应均包含 `summary` 字段（未生成为空串）

#### Scenario: 人工预填不被覆盖
- **WHEN** 创建/更新文章时显式提供 `summary` / `tags`
- **THEN** 自动生成绝不覆盖该人工输入

### Requirement: 发布/更新后台自动生成
系统 SHALL 在创建或更新文章后，若 `summary` 为空且 AI 可用，通过后台任务异步生成摘要与标签并落库；生成规则为「按字段独立回填」——`summary` 为空才写摘要、`tags` 为空才写标签，标题/分类绝不自动修改。

#### Scenario: 发布空摘要文章
- **WHEN** admin 发布一篇未填 `summary` 的文章且 AI 可用
- **THEN** 后台自动为文章生成 100 字导读与内容感知标签并写入数据库

#### Scenario: 未配置 Key 时发布
- **WHEN** 未配置 `LLM_API_KEY` 时发布文章
- **THEN** 发布正常返回 201，`summary` 保持空串，不触发任何 AI 调用

#### Scenario: 自动生成失败不影响发布
- **WHEN** 后台自动生成过程中 LLM 调用失败
- **THEN** 仅记录日志，文章发布/更新结果不受影响

### Requirement: 存量批量回填
系统 SHALL 提供 `POST /api/ai/backfill` 接口（仅 admin，`limit` 1~200），对无摘要（`summary == ""`）的存量文章逐篇生成摘要与标签，返回 `{total, processed, updated, failed}`；操作幂等，单篇失败计入 `failed` 不中断。

#### Scenario: 回填无摘要文章
- **WHEN** admin 调用回填接口且存在无摘要文章
- **THEN** 逐篇生成并落库摘要与标签，返回成功数量；`total` 为本次扫描到的无摘要文章数

#### Scenario: 回填限流截断
- **WHEN** 指定 `limit` 小于无摘要文章总数
- **THEN** 仅处理前 `limit` 篇，`processed` 不超过 `limit`

#### Scenario: 幂等重复调用
- **WHEN** 所有无摘要文章已回填后再次调用
- **THEN** `total` 与 `updated` 均为 0，不重复扣费

#### Scenario: 未配置 Key 或未登录
- **WHEN** 未配置 `LLM_API_KEY` 或未携带 Token
- **THEN** 接口分别返回 503 或 401

### Requirement: 前端 AI 灵感副驾与导读展示
系统 SHALL 在编辑器提供「AI 灵感副驾」：一键生成后直接填充摘要/标签输入框，标题/分类以建议条展示供一键采用；文章卡片与阅读器展示 `summary` 导读（非空时，卡片最多 2 行截断）；admin 导航提供「AI 回填」按钮（仅 `enabled && admin` 时显示）。

#### Scenario: 灵感副驾可用性
- **WHEN** `GET /api/ai/status` 返回 `enabled=false`
- **THEN** 编辑器隐藏 AI 灵感面板并提示「未配置 LLM API Key」

#### Scenario: 一键生成与采用
- **WHEN** admin 在编辑器点击「✨ 一键生成」且 AI 可用
- **THEN** 摘要与标签自动填充输入框，标题/分类建议条渲染，点击「采用」即填入对应输入框

#### Scenario: 导读展示
- **WHEN** 文章存在非空 `summary`
- **THEN** 卡片标题下方展示导读摘要、阅读器内容顶部展示导读条；渲染内容经 HTML 转义防 XSS

