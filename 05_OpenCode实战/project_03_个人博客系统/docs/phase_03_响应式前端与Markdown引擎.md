# 阶段三：响应式前端与 Markdown 引擎 (Phase 3: Frontend & Markdown)

> **阶段定位**：编写单文件 `index.html`，无需打包工具，纯 CDN 引入 TailwindCSS + Marked.js，实现颜值高、体验好的现代化响应式博客界面。

---

## 🎨 一、前端技术栈与 CDN 依赖

- **HTML5 + 原生 JS**：单文件 `index.html`，双击或后端静态托管即跑；
- **TailwindCSS CDN**：`https://cdn.tailwindcss.com`（暗黑主题与玻璃拟态）；
- **Marked.js CDN**：`https://cdn.jsdelivr.net/npm/marked/marked.min.js`（Markdown 实时解析）；
- **Highlight.js CDN**：代码块语法高亮；
- **Lucide Icons CDN**：轻量级现代化图标。

---

## 🧩 二、核心交互功能实现

1. **顶部导航与搜索栏**：
   - 博客标题与文章/阅读量统计；
   - 实时搜索输入框；
   - 「✍️ 写文章」按钮。
2. **分类胶囊标签栏**：
   - 动态拉取分类，点击标签快速筛选文章。
3. **文章列表卡片流**：
   - 瀑布流/网格展示文章（标题、分类、纯文本摘要、阅读量、日期）；
   - 提供编辑与删除快捷按钮。
4. **Markdown 沉浸式阅读器（模态框）**：
   - 点击文章弹出，Marked.js 渲染正文并进行代码高亮；
   - 触发阅读量 `views + 1` 并同步前台。
5. **Markdown 双栏创作/编辑工坊（模态框）**：
   - 支持新建发布与修改编辑；
   - 左侧输入 Markdown 原文，右侧毫秒级实时预览渲染效果；
   - 支持一键发布或保存草稿。
6. **删除确认与提示**：
   - 二次弹窗确认删除，避免误操作。

---

## 📋 三、阶段推进核对清单

- [x] 1. 搭建 `index.html` 基础结构与 TailwindCSS 暗黑样式；
- [x] 2. 引入 Marked.js 与 Highlight.js 渲染管线；
- [x] 3. 实现文章列表卡片渲染与分类筛选；
- [x] 4. 实现 Markdown 阅读器与双栏编辑器交互。
