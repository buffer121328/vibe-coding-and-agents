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
    synced += 1
  }
  // 章节图片目录（md 中多以相对路径 img/xxx.png 引用）
  const srcImg = join(srcDir, 'img')
  if (statSync(srcImg, { throwIfNoEntry: false })?.isDirectory()) {
    cpSync(srcImg, join(dstDir, 'img'), { recursive: true })
  }
}

console.log(`✅ 章节 Markdown 已同步到 docs/（共 ${synced} 个文件）`)
