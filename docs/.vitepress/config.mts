// docs/.vitepress/config.mts —— VitePress 站点配置（侧边栏按章节自动生成）
import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

// docs/ 根目录（本文件位于 docs/.vitepress/config.mts）
const docsRoot = join(fileURLToPath(new URL('..', import.meta.url)))

function firstHeading(file: string): string {
  const m = readFileSync(file, 'utf-8').match(/^#\s+(.+)$/m)
  return m ? m[1].trim() : ''
}

// 自动扫描 docs/ 下已同步的章节，生成单个章节的侧边栏分组（新增章节/文章无需改配置）
const chapterDirs = readdirSync(docsRoot)
  .filter((d: string) => /^\d{2}_/.test(d) && statSync(join(docsRoot, d)).isDirectory())
  .sort()

function chapterGroup(dir: string) {
  const files = readdirSync(join(docsRoot, dir))
    .filter((f: string) => f.endsWith('.md'))
    .sort()
  const items = files.map((f: string) => {
    const isIndex = f === 'index.md'
    const link = isIndex ? `/${dir}/` : `/${dir}/${f.replace(/\.md$/, '')}`
    const title = firstHeading(join(docsRoot, dir, f)) || f.replace(/\.md$/, '')
    return { text: title, link }
  })
  return { text: dir.replace(/^\d{2}_/, ''), items }
}

// 学习路径六大类（与根 README「章节导览：按学习路径分类」保持一致）
const categories = [
  { text: '🧭 入门概念', full: '🧭 入门概念（打地基）', link: '/01_发展之路/', prefixes: ['01_', '02_', '03_'] },
  { text: '🛠️ 主流工具实战', full: '🛠️ 主流工具实战（多备几把趁手的刀）', link: '/04_Dify实战/', prefixes: ['04_', '05_', '06_', '07_'] },
  { text: '🤖 从底层理解 Agent', full: '🤖 从底层理解 Agent（开天眼）', link: '/08_手搓Agent/', prefixes: ['08_'] },
  { text: '🏭 主流 Agent 框架', full: '🏭 主流 Agent 框架（最成熟的生产方案）', link: '/09_LangChain搭建Agent/', prefixes: ['09_', '10_'] },
  { text: '📚 RAG 实战', full: '📚 RAG 实战（知识库长期工程）', link: '/11_RAG实战/', prefixes: ['11_'] },
  { text: '💆 对 Agent 与 AI 的思考', full: '💆 对 Agent 与 AI 的思考（认知碰撞）', link: '/12_如何做一个自己的项目/', prefixes: ['12_', '13_'] },
]

// 侧边栏：按六大学习路径分组，组内展示各章节（含子页面）
const sidebar = categories.map((cat) => ({
  text: cat.full,
  collapsed: false,
  items: cat.prefixes.flatMap((p) =>
    chapterDirs.filter((d: string) => d.startsWith(p)).map(chapterGroup),
  ),
}))

export default withMermaid(defineConfig({
  lang: 'zh-CN',
  title: 'Vibe Coding 知识库',
  description: 'AI 辅助编程与 Agent 智能体全景教学知识库',
  base: '/vibe_coding/',
  cleanUrls: true,
  lastUpdated: true,
  ignoreDeadLinks: true, // 书稿中存在指向项目子文件/未同步页面的交叉引用，跳过死链检查

  markdown: {
    math: true, // 支持 $..$ / $$..$$ 的 LaTeX 数学公式（VitePress 内置 markdown-it-mathjax3）
    config(md) {
      // 把行内文本与行内代码里的 {{ 和 }} 转义为 HTML 实体，避免 Vue 模板编译器
      // 把 Dify 模板变量（如 {{#sys.query#}}）误当作插值表达式导致构建失败
      const escapeMustache = (html: string) =>
        html.replace(/{{/g, '&#123;&#123;').replace(/}}/g, '&#125;&#125;')
      const codeInline = md.renderer.rules.code_inline!
      md.renderer.rules.code_inline = (tokens, idx, options, env, self) =>
        escapeMustache(codeInline(tokens, idx, options, env, self))
      const text = md.renderer.rules.text!
      md.renderer.rules.text = (tokens, idx, options, env, self) =>
        escapeMustache(text(tokens, idx, options, env, self))
    },
  },

  themeConfig: {
    nav: [
      { text: '首页', link: '/' },
      ...categories.map((c) => ({ text: c.text, link: c.link })),
      { text: 'GitHub', link: 'https://github.com/buffer121328/vibe_coding' },
    ],
    sidebar,
    outline: { label: '本页目录', level: [2, 3] },
    search: {
      provider: 'local',
      options: {
        translations: {
          button: { buttonText: '搜索', buttonAriaLabel: '搜索' },
          modal: {
            noResultsText: '未找到相关结果',
            resetButtonTitle: '清除查询',
            footer: { selectText: '选择', navigateText: '切换', closeText: '关闭' },
          },
        },
      },
    },
    lastUpdated: { text: '最后更新' },
    docFooter: { prev: '上一篇', next: '下一篇' },
    darkModeSwitchLabel: '主题',
    lightModeSwitchTitle: '切换到浅色模式',
    darkModeSwitchTitle: '切换到深色模式',
    sidebarMenuLabel: '章节目录',
    returnToTopLabel: '返回顶部',
    notFound: {
      title: '页面不存在',
      quote: '你访问的页面不存在或已被移动。',
      linkLabel: '回到首页',
    },
  },
})
)
