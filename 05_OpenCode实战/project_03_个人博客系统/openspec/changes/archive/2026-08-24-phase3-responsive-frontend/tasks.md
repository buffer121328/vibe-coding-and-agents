## 1. 基础结构与样式

- [x] 1.1 创建 `index.html` 文件，搭建 HTML 骨架（DOCTYPE、head、body）
- [x] 1.2 引入所有 CDN 依赖（TailwindCSS、Lucide、Marked.js、Highlight.js、Google Fonts）
- [x] 1.3 配置 TailwindCSS 暗黑模式和自定义主题
- [x] 1.4 编写基础 CSS 样式（背景网格、光晕、滚动条、模态框过渡、骨架屏动画）

## 2. 导航栏与搜索

- [x] 2.1 实现顶部导航栏 HTML 结构（标题、统计、搜索框、写文章按钮）
- [x] 2.2 实现移动端搜索框（响应式）
- [x] 2.3 实现搜索防抖逻辑（350ms 延迟）

## 3. 分类筛选

- [x] 3.1 实现分类药丸栏 HTML 结构
- [x] 3.2 实现 `loadCategories()` 从 API 获取分类
- [x] 3.3 实现 `renderCategories()` 渲染药丸标签
- [x] 3.4 实现分类点击筛选逻辑

## 4. 文章卡片网格

- [x] 4.1 实现 `loadPosts()` 从 API 获取文章列表（支持分类和搜索过滤）
- [x] 4.2 实现 `renderPosts()` 渲染文章卡片（标题、分类、摘要、标签、浏览量、日期）
- [x] 4.3 实现空状态展示
- [x] 4.4 实现卡片入场动画（fade-up + stagger）

## 5. Markdown 阅读器

- [x] 5.1 实现阅读器模态框 HTML 结构
- [x] 5.2 实现 `openReader()` 获取文章详情并渲染 Markdown
- [x] 5.3 实现代码高亮（highlight.js）
- [x] 5.4 实现阅读量自增（`increment_views=true`）
- [x] 5.5 实现关闭逻辑（ESC、遮罩层点击）

## 6. 双栏编辑器

- [x] 6.1 实现编辑器模态框 HTML 结构（标题/分类/标签输入、左右分栏）
- [x] 6.2 实现 `openEditor()` 支持新建和编辑模式
- [x] 6.3 实现实时预览（textarea input 事件 → marked.parse）
- [x] 6.4 实现 `publishPost()` 发布/更新文章
- [x] 6.5 实现 `saveDraft()` 保存草稿

## 7. 删除确认

- [x] 7.1 实现删除确认模态框 HTML 结构
- [x] 7.2 实现 `openDeleteModal()` 和 `closeDeleteModal()`
- [x] 7.3 实现 `confirmDelete()` 调用 DELETE API

## 8. 通用 UX

- [x] 8.1 实现 Toast 通知系统（success/error/info）
- [x] 8.2 实现 `apiFetch()` 统一错误处理
- [x] 8.3 实现导航栏统计更新（文章数、浏览量）
- [x] 8.4 初始化流程（lucide.createIcons + 并行加载分类和文章）
