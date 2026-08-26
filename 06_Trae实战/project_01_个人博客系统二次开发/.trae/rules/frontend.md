# 前端规则（Frontend Rules）

> 适用：`project_01_个人博客系统二次开发/` 单文件 HTML5 + TailwindCSS（CDN）+ Marked.js + 原生现代 JS，零 npm 构建链。

## ✅ 遵循规范（Do）

- 单文件 `index.html`，公共 CDN 引入 TailwindCSS / Marked.js / Lucide，双击/静态服务即跑；
- 保持深色玻璃拟态质感（`bg-white/5 backdrop-blur-md border-white/10`）+ 渐变强调色 + 悬浮微交互 + 移动优先响应式；
- 对接后端统一 `fetch` + `baseURL` 封装（相对 `/api`）；
- 认证：登录模态框 + `apiFetch` 自动附带 `Authorization: Bearer <token>`；Token 与用户信息持久化到 localStorage（`blog_token` / `blog_user`），初始化经 `GET /api/auth/me` 校验恢复；收到 401 自动清除登录态并弹登录框；
- 权限显隐：写文章 / 编辑 / 删除 / 空状态创建按钮按 `role === 'admin'` 显隐，退出恢复只读态；
- 分页：文章列表解析分页响应 `{items,total,page,page_size}`，网格下方渲染「上一页 / 第 x 页 / 下一页」控件（首末页禁用）；导航统计用 `total`；切换分类/搜索时重置 `page=1`；
- 社交徽标：文章卡片元信息展示点赞数与评论数；
- 点赞：阅读器提供「♥ 点赞」按钮，未登录点击弹登录框；登录后点击切换点赞/取消并即时更新按钮态与计数（`liked=true` 填充红色心形），重新打开文章回显已点赞态；
- 评论：阅读器内容下方渲染楼层评论区（`N楼`/作者/时间/内容，按升序）；登录显示输入框、未登录显示「登录后参与评论」引导；评论作者或 admin 可见删除按钮；评论超过一页用「加载更多」追加；渲染用户生成内容一律 `escapeHtml` 防 XSS；
- AI 灵感副驾：编辑器提供「✨ 一键生成」调 `POST /api/ai/generate`（仅 admin），摘要/标签直接填充输入框、标题/分类以「建议条 + 采用」呈现；打开编辑器/页面加载时 `GET /api/ai/status` 探测，`enabled=false` 时隐藏 AI 面板并提示「未配置 LLM API Key」；
- AI 导读展示：文章卡片与阅读器顶部展示 `summary` 导读（非空时，卡片最多 2 行截断），渲染一律 `escapeHtml` 防 XSS；
- AI 批量回填：admin 导航提供「AI 回填」按钮（`aiEnabled && isAdmin()` 才显示）调 `POST /api/ai/backfill`，完成后 Toast 展示 `processed/updated/failed`；
- 用 `localStorage` 持久化前端状态（Token、偏好设置等）；
- 新增页面/组件前，先查 `.trae/skills/` 技能包按需加载，再读对应 `SKILL.md` 执行：

| 技能                 | 用途                     | 触发场景      |
| ------------------ | ---------------------- | --------- |
| tailwind-ui-master | UI 规范（暗黑 / 玻璃拟态 / 微交互） | 前端样式      |
| single-file-app    | 单文件 HTML 骨架（CDN + 内联 JS） | 页面/弹窗搭建   |
| simplify           | 代码精简 / 去死代码             | 重构        |

- 完成后必须真实实测（点击 / 输入 / 查 console / 截图），并结合后端 `pytest` 联调。

## 🚫 红线禁令（Don't）

- 禁止 npm install 与任何前端构建链；
- 禁止破坏既有玻璃拟态视觉风格与既有交互习惯；
- 禁止硬编码后端地址、绕过 CORS 排查；
- 禁止未转义直接 `innerHTML` 渲染评论等用户生成内容（防 XSS）；同样适用于 AI 生成的 `summary` / 标签 / 建议文案；
- 禁止把 `LLM_API_KEY` 写进前端代码或 localStorage（密钥只存在于后端 `.env`）；
- 禁止忽略分页元信息直接用 `items.length` 当文章总数；
- 禁止「写完即交付」——未真实实测不得交付。
