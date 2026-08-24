## Context

后端已完成 CRUD API（`/api/posts`、`/api/categories`），需要实现单文件前端 `index.html`。约束：零 npm 依赖，所有库通过 CDN 引入，单文件包含全部 HTML/CSS/JS。

## 架构决策

### 单文件结构
- 所有代码写在一个 `index.html` 中
- CSS 通过 `<style>` 标签内联
- JS 通过 `<script>` 标签内联
- 外部库全部 CDN 引入

### 状态管理
- 使用 JS 全局变量管理状态（`allPosts`、`categories`、`currentCategory`、`currentSearch`、`editingPostId`、`deleteTargetId`）
- 不使用 localStorage（后端是数据源）
- 模态框开关通过 CSS class `active` 控制

### API 通信
- 统一 `apiFetch()` 封装，处理 JSON 序列化、错误处理、204 响应
- `API_BASE = ''`（同源，无需前缀）
- 搜索使用 350ms 防抖

### UI 框架
- TailwindCSS CDN + 自定义 `<script>` 配置暗黑模式
- 玻璃拟态风格：`bg-white/5 backdrop-blur-md border border-white/10`
- 渐变强调色：`from-indigo-500 via-purple-500 to-pink-500`
- 字体：Noto Serif SC（标题）+ Noto Sans SC（正文）

### Markdown 渲染
- `marked.parse()` 渲染 Markdown
- `hljs.highlightElement()` 代码高亮
- 编辑器左侧 textarea 输入，右侧 div 实时预览

### 模态框系统
- 三个模态框：阅读器、编辑器、删除确认
- 统一 CSS 过渡动画（fade + scale）
- ESC 键 / 遮罩层点击关闭

## 关键文件

- `index.html`（新增）：单文件前端
- `main.py`（已存在）：后端 API，无需修改

## CDN 依赖

| 库 | 用途 | CDN |
|---|---|---|
| TailwindCSS | CSS 框架 | `cdn.tailwindcss.com` |
| Lucide Icons | 图标 | `unpkg.com/lucide@latest` |
| Marked.js | Markdown 解析 | `cdn.jsdelivr.net/npm/marked` |
| Highlight.js | 代码高亮 | `cdnjs.cloudflare.com/ajax/libs/highlight.js` |
| Google Fonts | 中文字体 | `fonts.googleapis.com` |
