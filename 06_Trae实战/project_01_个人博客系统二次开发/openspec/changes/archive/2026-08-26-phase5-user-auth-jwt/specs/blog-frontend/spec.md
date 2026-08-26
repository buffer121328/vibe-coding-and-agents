## MODIFIED Requirements

### Requirement: 顶部导航栏
系统 SHALL 提供固定的顶部导航栏，包含博客标题、文章/浏览统计、搜索输入框、登录区（登录按钮或用户名+退出）和「写文章」按钮。

#### Scenario: 页面加载后显示统计信息
- **WHEN** 用户打开博客首页
- **THEN** 导航栏显示文章总数和总浏览量

#### Scenario: 实时搜索文章
- **WHEN** 用户在搜索框输入关键词
- **THEN** 文章列表即时过滤，仅显示标题或内容包含该关键词的文章

#### Scenario: 未登录时显示登录按钮
- **WHEN** 用户未登录
- **THEN** 导航栏显示「登录」按钮，隐藏「写文章」按钮

#### Scenario: 管理员登录后显示写文章
- **WHEN** admin 用户登录后
- **THEN** 导航栏显示用户名与「退出」按钮，并显示「写文章」按钮

#### Scenario: 点击写文章按钮
- **WHEN** 管理员点击「✍️ 写文章」按钮
- **THEN** 弹出 Markdown 双栏编辑器模态框

### Requirement: 文章卡片网格展示
系统 SHALL 以网格布局展示文章卡片，每张卡片包含标题、分类、纯文本摘要、标签、浏览量和日期；编辑/删除按钮仅管理员可见。

#### Scenario: 正常展示文章列表
- **WHEN** 存在已发布的文章
- **THEN** 以卡片网格形式展示，每张卡片显示标题、分类徽章、内容摘要（前100字符）、标签、浏览量和相对时间

#### Scenario: 未登录不显示管理按钮
- **WHEN** 用户未登录浏览文章卡片
- **THEN** 卡片不显示编辑与删除按钮

#### Scenario: 管理员显示管理按钮
- **WHEN** admin 用户浏览文章卡片
- **THEN** 每张卡片显示编辑与删除按钮

#### Scenario: 空状态展示
- **WHEN** 没有任何文章
- **THEN** 显示友好的空状态提示；「写第一篇文章」按钮仅管理员可见

#### Scenario: 卡片悬浮效果
- **WHEN** 用户鼠标悬浮在文章卡片上
- **THEN** 卡片上浮并显示发光阴影效果

## ADDED Requirements

### Requirement: 登录与退出
系统 SHALL 提供登录模态框（用户名/密码），登录成功后将 Token 与用户信息持久化到 localStorage，并支持退出清除登录态。

#### Scenario: 打开登录弹窗
- **WHEN** 用户点击「登录」按钮
- **THEN** 弹出登录模态框，用户名输入框自动聚焦

#### Scenario: 登录成功
- **WHEN** 用户输入正确凭据并提交
- **THEN** 关闭登录弹窗，导航栏切换为用户名+退出，并显示成功提示

#### Scenario: 登录失败
- **WHEN** 用户输入错误凭据并提交
- **THEN** 保持登录弹窗并显示红色错误提示

#### Scenario: 退出登录
- **WHEN** 用户点击「退出」
- **THEN** 清除本地 Token 与用户信息，界面恢复只读态并提示已退出

#### Scenario: 刷新后保持登录态
- **WHEN** 页面刷新且本地存在 Token
- **THEN** 通过 `GET /api/auth/me` 校验并恢复登录态，管理按钮继续显示

### Requirement: 请求自动携带 Token 与 401 处理
系统 SHALL 在 API 请求中自动附带 `Authorization: Bearer <token>`；收到 401 时清除本地登录态并弹出登录框。

#### Scenario: 请求附带 Token
- **WHEN** 页面发起 API 请求且本地存在 Token
- **THEN** 请求头自动携带 `Authorization: Bearer <token>`

#### Scenario: 401 时弹出登录框
- **WHEN** 任一 API 请求返回 401
- **THEN** 清除本地登录态并弹出登录模态框
