# blog-frontend Specification

## Purpose

提供一个现代化、响应式的单页博客前端界面，让用户通过浏览器完成文章的创建、阅读、编辑、删除和分类筛选，支持 Markdown 实时渲染与代码高亮。

## Requirements

### Requirement: 顶部导航栏
系统 SHALL 提供固定的顶部导航栏，包含博客标题、文章/浏览统计、搜索输入框和「写文章」按钮。

#### Scenario: 页面加载后显示统计信息
- **WHEN** 用户打开博客首页
- **THEN** 导航栏显示文章总数和总浏览量

#### Scenario: 实时搜索文章
- **WHEN** 用户在搜索框输入关键词
- **THEN** 文章列表即时过滤，仅显示标题或内容包含该关键词的文章

#### Scenario: 点击写文章按钮
- **WHEN** 用户点击「✍️ 写文章」按钮
- **THEN** 弹出 Markdown 双栏编辑器模态框

### Requirement: 分类筛选药丸栏
系统 SHALL 在导航栏下方显示分类药丸标签栏，支持按分类快速筛选文章。

#### Scenario: 加载分类列表
- **WHEN** 页面加载完成
- **THEN** 从 `/api/categories` 获取分类列表，渲染为可点击的药丸标签

#### Scenario: 点击分类药丸筛选
- **WHEN** 用户点击某个分类药丸
- **THEN** 文章列表仅显示该分类下的文章，药丸显示激活态

#### Scenario: 点击全部药丸
- **WHEN** 用户点击「全部」药丸
- **THEN** 文章列表显示所有文章

### Requirement: 文章卡片网格展示
系统 SHALL 以网格布局展示文章卡片，每张卡片包含标题、分类、纯文本摘要、标签、浏览量和日期。

#### Scenario: 正常展示文章列表
- **WHEN** 存在已发布的文章
- **THEN** 以卡片网格形式展示，每张卡片显示标题、分类徽章、内容摘要（前100字符）、标签、浏览量和相对时间

#### Scenario: 空状态展示
- **WHEN** 没有任何文章
- **THEN** 显示友好的空状态提示和「写第一篇文章」按钮

#### Scenario: 卡片悬浮效果
- **WHEN** 用户鼠标悬浮在文章卡片上
- **THEN** 卡片上浮并显示发光阴影效果

### Requirement: Markdown 沉浸式阅读器
系统 SHALL 提供模态框形式的 Markdown 阅读器，点击文章标题即可打开。

#### Scenario: 打开文章详情
- **WHEN** 用户点击文章卡片标题
- **THEN** 弹出阅读器模态框，从 API 获取文章详情，使用 marked.js 渲染 Markdown 内容，代码块使用 highlight.js 高亮

#### Scenario: 阅读量自增
- **WHEN** 用户打开文章详情
- **THEN** 调用 `GET /api/posts/{id}?increment_views=true`，阅读量 +1

#### Scenario: 关闭阅读器
- **WHEN** 用户点击关闭按钮、按 ESC 键或点击遮罩层
- **THEN** 阅读器模态框关闭

### Requirement: Markdown 双栏编辑器
系统 SHALL 提供左右分栏的 Markdown 编辑器，支持新建和编辑文章。

#### Scenario: 新建文章
- **WHEN** 用户点击「写文章」按钮
- **THEN** 弹出编辑器模态框，左侧为空白 Markdown 输入区，右侧为实时预览区

#### Scenario: 实时预览
- **WHEN** 用户在左侧输入 Markdown 内容
- **THEN** 右侧毫秒级实时渲染预览效果

#### Scenario: 编辑已有文章
- **WHEN** 用户点击文章卡片的编辑按钮
- **THEN** 弹出编辑器模态框，预填充文章的标题、分类、标签和内容

#### Scenario: 发布文章
- **WHEN** 用户填写标题和内容后点击「发布」
- **THEN** 调用 `POST /api/posts` 或 `PUT /api/posts/{id}`，关闭编辑器，刷新文章列表

#### Scenario: 保存草稿
- **WHEN** 用户点击「保存草稿」
- **THEN** 以 `status: "draft"` 保存文章

### Requirement: 删除确认机制
系统 SHALL 在删除文章前显示二次确认弹窗，避免误操作。

#### Scenario: 触发删除确认
- **WHEN** 用户点击文章卡片的删除按钮
- **THEN** 弹出确认删除模态框，显示「确认删除」和「取消」按钮

#### Scenario: 确认删除
- **WHEN** 用户点击「确认删除」
- **THEN** 调用 `DELETE /api/posts/{id}`，移除卡片，刷新列表

#### Scenario: 取消删除
- **WHEN** 用户点击「取消」或关闭弹窗
- **THEN** 关闭确认弹窗，不执行删除

### Requirement: 通知与加载状态
系统 SHALL 提供操作反馈通知和数据加载状态指示。

#### Scenario: 操作成功通知
- **WHEN** 用户成功创建、编辑或删除文章
- **THEN** 显示绿色 Toast 通知，3秒后自动消失

#### Scenario: 操作失败通知
- **WHEN** API 请求失败
- **THEN** 显示红色 Toast 通知，包含错误信息

#### Scenario: 加载状态
- **WHEN** 页面正在加载数据
- **THEN** 显示骨架屏占位动画

### Requirement: 响应式布局
系统 SHALL 在不同屏幕尺寸下自适应布局。

#### Scenario: 移动端布局
- **WHEN** 屏幕宽度小于 640px
- **THEN** 文章卡片单列显示，搜索框移至导航栏下方，编辑器纵向分栏，模态框全屏

#### Scenario: 桌面端布局
- **WHEN** 屏幕宽度大于 1024px
- **THEN** 文章卡片三列显示，搜索框在导航栏中间
