## Why

后端 CRUD API 和数据库层已完成（阶段一二），但用户没有界面可以操作。需要一个现代化、响应式的单页前端，让用户能通过浏览器完成文章的创建、阅读、编辑、删除和分类筛选，同时支持 Markdown 实时渲染和代码高亮。

## What Changes

- 新增单文件 `index.html`，零 npm 依赖，通过 CDN 引入所有库
- 实现文章列表卡片流展示（网格布局、分类标签、摘要、浏览量）
- 实现分类药丸筛选栏（从 API 动态拉取）
- 实现顶部导航栏（搜索、统计、写文章入口）
- 实现 Markdown 沉浸式阅读器（模态框 + 代码高亮）
- 实现 Markdown 双栏编辑器（左侧源码 + 右侧实时预览）
- 实现删除二次确认弹窗
- 实现 Toast 通知、骨架屏加载、模态框过渡动画
- 深色主题 + 玻璃拟态 UI 风格

## Capabilities

### New Capabilities

- `blog-frontend`: 博客单页前端界面，包含导航、文章列表、分类筛选、Markdown 阅读器、双栏编辑器、删除确认等完整交互功能

### Modified Capabilities

（无，后端 API 契约不变）

## Impact

- 新增文件：`index.html`（单文件前端）
- 依赖：TailwindCSS CDN、Marked.js CDN、Highlight.js CDN、Lucide Icons CDN
- 不修改后端代码
- 不新增 Python 依赖
