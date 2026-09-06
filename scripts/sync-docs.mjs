// scripts/sync-docs.mjs —— 把各章节顶层 Markdown 同步进 docs/ 供 VitePress 渲染
// 原则：仓库根目录各章节 md = 唯一内容源；docs 下章节内容为生成物（已在 .gitignore 忽略）
import { readdirSync, copyFileSync, mkdirSync, rmSync, statSync, cpSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const repoRoot = join(fileURLToPath(new URL('..', import.meta.url)))
const docsRoot = join(repoRoot, 'docs')

// 1. 清空 docs 下旧的生成章节目录，保证与仓库现状完全一致
for (const entry of readdirSync(docsRoot)) {
  if (/^\d{2}_/.test(entry)) {
    rmSync(join(docsRoot, entry), { recursive: true, force: true })
  }
}

// 把 HTML <img src="img/..."> / 图片 Markdown ![](img/...) 改写为 ./img/...，
// 使 Vue 模板编译器能按「相对当前文件」正确解析图片资源（不改动仓库源文件）
function fixImageRefs(content) {
  return content
    .replace(/src="img\//g, 'src="./img/')
    .replace(/src='img\//g, "src='./img/")
    .replace(/\]\(img\/([^) \n]+)\)/g, '](./img/$1)')
}

// 从正文提取用于 SEO 的纯文本摘要：优先取开头的第一段正文；若前部只有标题/引用/表格，
// 则退而取引用块导语。目标 ~160 字符（搜索引擎摘要的常见截断长度）。
function extractDescription(content) {
  const clean = (s) =>
    s
      .replace(/!\[[^\]]*\]\([^)]*\)/g, '') // 行内图片
      .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1') // 链接只留文字
      .replace(/[*_`~]/g, '') // Markdown 强调/代码标记
      .replace(/"/g, '＂') // 直引号会截断 HTML meta 属性，换成全角引号
      .replace(/\s+/g, ' ')
      .trim()
  // 预处理：跳过 fenced 代码块（``` 围栏行与围栏内代码都不适合做摘要）
  const lines = []
  let inFence = false
  for (const line of content.split('\n')) {
    if (/^\s*(```|~~~)/.test(line)) {
      inFence = !inFence
      continue
    }
    if (!inFence) lines.push(line)
  }
  const isDivider = (t) => /^(\*\s*){3,}$|^(-\s*){3,}$|^(_\s*){3,}$/.test(t) // *** / --- / ___ 分隔线
  const pick = (pred) => {
    for (const line of lines) {
      const t = line.trim()
      if (!t || isDivider(t)) continue
      if (pred(t)) return clean(t.replace(/^>\s*/, ''))
    }
    return ''
  }
  const isBody = (t) =>
    !t.startsWith('#') && !t.startsWith('>') && !t.startsWith('|')
    && !t.startsWith('![') && !t.startsWith('<')
    && !/^([-*+]|\d+\.)\s/.test(t)
  // 第一优先：第一段「够长」的正文（≥40 字符，避免摘到孤立短句）；不够则接着找下一段，
  // 全文都没有长段时退回第一个引用块导语（本书各章开篇常是金句式导语）
  const firstBody = pick(isBody)
  const longBody = pick((t) => isBody(t) && clean(t).length >= 40)
  const desc = longBody || firstBody || pick((t) => t.startsWith('>'))
  if (!desc) return ''
  return desc.length > 160 ? desc.slice(0, 160).replace(/[，、；,;]\s*[^，、；,;]*$/, '') + '……' : desc
}

// 已生成过 frontmatter 的内容集合（幂等：重复执行不叠加）
const frontmatterCache = new Set()

function injectFrontmatter(filePath) {
  if (frontmatterCache.has(filePath)) return
  frontmatterCache.add(filePath)
  const raw = readFileSync(filePath, 'utf-8')
  if (raw.startsWith('---\n')) return // 已有 frontmatter，尊重现状
  const heading = raw.match(/^#\s+(.+)$/m)?.[1]?.trim() ?? ''
  const description = extractDescription(raw) || heading
  if (!description) return
  const fm = `---\ntitle: ${heading || '文档'}\ndescription: ${JSON.stringify(description)}\n---\n\n`
  writeFileSync(filePath, fm + raw)
}

// 2. 扫描仓库根目录所有 "NN_*" 章节文件夹，复制顶层 .md 与 img/ 目录（跳过 code/项目子目录等）
let synced = 0
for (const dir of readdirSync(repoRoot).sort()) {
  if (!/^\d{2}_/.test(dir)) continue
  const srcDir = join(repoRoot, dir)
  if (!statSync(srcDir).isDirectory()) continue
  const dstDir = join(docsRoot, dir)
  mkdirSync(dstDir, { recursive: true })
  for (const f of readdirSync(srcDir).sort()) {
    if (!f.endsWith('.md')) continue
    const dstName = f === 'README.md' ? 'index.md' : f // 章节 README -> 章节首页
    const content = fixImageRefs(readFileSync(join(srcDir, f), 'utf-8'))
    writeFileSync(join(dstDir, dstName), content)
    injectFrontmatter(join(dstDir, dstName)) // 注入 SEO frontmatter（title/description）
    synced += 1
  }
  // 章节图片目录（md 中多以相对路径 img/xxx.png 引用）
  const srcImg = join(srcDir, 'img')
  if (statSync(srcImg, { throwIfNoEntry: false })?.isDirectory()) {
    cpSync(srcImg, join(dstDir, 'img'), { recursive: true })
  }
}

console.log(`✅ 章节 Markdown 已同步到 docs/（共 ${synced} 个文件）`)
