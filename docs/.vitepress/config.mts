// docs/.vitepress/config.mts —— VitePress 站点配置（侧边栏按章节自动生成）
import { defineConfig } from 'vitepress'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

// docs/ 根目录（本文件位于 docs/.vitepress/config.mts）
const docsRoot = join(fileURLToPath(new URL('..', import.meta.url)))

function firstHeading(file: string): string {
  const m = readFileSync(file, 'utf-8').match(/^#\s+(.+)$/m)
  return m ? m[1].trim() : ''
}

// 自动扫描 docs/ 下已同步的章节，生成侧边栏（新增章节/文章无需改配置）
const sidebar = readdirSync(docsRoot)
  .filter((d) => /^\d{2}_/.test(d) && statSync(join(docsRoot, d)).isDirectory())
  .sort()
  .map((dir) => {
    const files = readdirSync(join(docsRoot, dir))
      .filter((f) => f.endsWith('.md'))
      .sort()
    const items = files.map((f) => {
      const isIndex = f === 'index.md'
      const link = isIndex ? `/${dir}/` : `/${dir}/${f.replace(/\.md$/, '')}`
      const title = firstHeading(join(docsRoot, dir, f)) || f.replace(/\.md$/, '')
      return { text: title, link }
    })
    return { text: dir.replace(/^\d{2}_/, ''), items }
  })

export default defineConfig({
  lang: 'zh-CN',
  title: 'Vibe Coding 知识库',
  description: 'AI 辅助编程与 Agent 智能体全景教学知识库',
  base: '/vibe_coding/',
  cleanUrls: true,
  lastUpdated: true,
  ignoreDeadLinks: true, // 书稿中存在指向项目子文件/未同步页面的交叉引用，跳过死链检查

  markdown: {
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
