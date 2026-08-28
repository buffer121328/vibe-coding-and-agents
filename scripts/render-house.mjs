// render-house.mjs —— 将 .mmd 图源渲染为全库统一的 House 风格 SVG
// 用法: node scripts/render-house.mjs <in.mmd> <out.svg>
// 模板与配色对齐既有章节产物: Latte 浅色 (--bg:#eff1f5), Inter/PingFang 字体,
// 直角节点 (fill=--_node-fill, stroke=--_node-stroke), 28px 子图标题栏, 正交折线连线。
import puppeteer from 'puppeteer'
import fs from 'node:fs'

const PALETTE = '--bg:#eff1f5;--fg:#4c4f69;--line:#9ca0b0;--accent:#8839ef;--muted:#9ca0b0'
const FONT = `'Inter, PingFang SC, Microsoft YaHei, sans-serif', system-ui, sans-serif`
const STYLE_BLOCK = `
  @import url('https://fonts.googleapis.com/css2?family=Inter%2C%20PingFang%20SC%2C%20Microsoft%20YaHei%2C%20sans-serif:wght@400;500;600;700&amp;display=swap');
  text { font-family: ${FONT}; }
  svg {
    /* Derived from --bg and --fg (overridable via --line, --accent, etc.) */
    --_text:          var(--fg);
    --_text-sec:      var(--muted, color-mix(in srgb, var(--fg) 60%, var(--bg)));
    --_text-muted:    var(--muted, color-mix(in srgb, var(--fg) 40%, var(--bg)));
    --_text-faint:    color-mix(in srgb, var(--fg) 25%, var(--bg));
    --_line:          var(--line, color-mix(in srgb, var(--fg) 50%, var(--bg)));
    --_arrow:         var(--accent, color-mix(in srgb, var(--fg) 85%, var(--bg)));
    --_node-fill:     var(--surface, color-mix(in srgb, var(--fg) 3%, var(--bg)));
    --_node-stroke:   var(--border, color-mix(in srgb, var(--fg) 20%, var(--bg)));
    --_group-fill:    var(--bg);
    --_group-hdr:     color-mix(in srgb, var(--fg) 5%, var(--bg));
    --_inner-stroke:  color-mix(in srgb, var(--fg) 12%, var(--bg));
    --_key-badge:     color-mix(in srgb, var(--fg) 10%, var(--bg));
  }
`
const DEFS = `
  <marker id="arrowhead" markerWidth="8" markerHeight="5" refX="7" refY="2.5" orient="auto">
    <polygon points="0 0, 8 2.5, 0 5" fill="var(--_arrow)" stroke="var(--_arrow)" stroke-width="0.75" stroke-linejoin="round" />
  </marker>
  <marker id="arrowhead-start" markerWidth="8" markerHeight="5" refX="1" refY="2.5" orient="auto-start-reverse">
    <polygon points="8 0, 0 2.5, 8 5" fill="var(--_arrow)" stroke="var(--_arrow)" stroke-width="0.75" stroke-linejoin="round" />
  </marker>
`

// ---------- 解析 .mmd ----------
function parseMMD(text) {
  const dir = /(?:graph|flowchart)\s+(TD|LR|TB|RL)/.exec(text)?.[1] === 'LR' ? 'LR' : 'TD'
  const nodes = new Map()    // id -> {id, label, lines, shape, cluster}
  const clusters = new Map() // id -> {id, label, members: []}
  const edges = []           // {from, to, style, label, bidir}
  const stack = []
  const memberOf = (id) => stack.length ? stack[stack.length - 1] : null
  function addNode(id, label, shape) {
    if (!nodes.has(id)) {
      const lines = label ? label.split('\\n') : ['']
      nodes.set(id, { id, label: label || id, lines, shape: shape || 'rectangle', cluster: memberOf(id) })
      const cid = nodes.get(id).cluster
      if (cid) clusters.get(cid).members.push(id)
    } else if (label) {
      const n = nodes.get(id)
      n.label = label
      n.lines = label.split('\\n')
      n.shape = shape || n.shape
    }
  }
  function endpoint(tok) {
    const m = /^(\w+)[\[{]"([^"]*)"[}\]]$/.exec(tok)
    if (m) { addNode(m[1], m[2], tok.includes('{') ? 'diamond' : 'rectangle'); return m[1] }
    const plain = /^(\w+)$/.exec(tok)
    if (plain) {
      if (clusters.has(plain[1])) return plain[1] // 子图 ID：不注册为节点
      addNode(plain[1], null); return plain[1]
    }
    return null
  }
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    if (!line || line.startsWith('%%') || /^(graph|flowchart)\b/.test(line)) continue
    const sg = /^subgraph\s+([\w-]+)(?:\s*\["([^"]*)"\])?/.exec(line)
    if (sg) { clusters.set(sg[1], { id: sg[1], label: sg[2] || sg[1], members: [] }); stack.push(sg[1]); continue }
    if (line === 'end') { stack.pop(); continue }
    // 连线语句（支持链式 A --> B --> C, ==>、<==>、-.label.->、-.->、-->|label|）
    const tokenRe = /(<==>|==>|-\.([^.]*)\.->|-\.->|-->)(\|"([^"]*)"\||\|([^|]*)\|)?/g
    const parts = []
    let m, last = 0
    while ((m = tokenRe.exec(line))) {
      parts.push({ tok: line.slice(last, m.index).trim(), op: m[1], label: (m[4] || m[5] || m[2] || '').trim() })
      last = tokenRe.lastIndex
    }
    parts.push({ tok: line.slice(last).trim(), op: null, label: '' })
    if (parts.length > 1) {
      const ids = parts.map(p => endpoint(p.tok))
      for (let i = 0; i < parts.length - 1; i++) {
        if (!ids[i] || !ids[i + 1]) continue
        let style = 'normal', bidir = false
        if (parts[i].op === '==>') style = 'thick'
        else if (parts[i].op === '<==>') { style = 'thick'; bidir = true }
        else if (parts[i].op.startsWith('-.')) style = 'dotted'
        edges.push({ from: ids[i], to: ids[i + 1], style, label: parts[i].label, bidir })
      }
    } else {
      const d = /^(\w+)[\[{]"([^"]*)"[}\]]$/.exec(line)
      if (d) addNode(d[1], d[2], line.includes('{') ? 'diamond' : 'rectangle')
    }
  }
  return { dir, nodes: [...nodes.values()], clusters: [...clusters.values()], edges }
}

// ---------- 布局 ----------
function layout(graph, measure) {
  const { nodes, clusters, edges } = graph
  const NW = new Map(), NH = new Map()
  for (const n of nodes) {
    const widths = n.lines.map(l => measure(l, 13, 500))
    NW.set(n.id, Math.max(90, Math.round(Math.max(...widths) * 1.06 + 30)))
    NH.set(n.id, 36.9 + 16.9 * (n.lines.length - 1))
  }
  const members = id => clusters.find(c => c.id === id)?.members || []
  const isCluster = id => clusters.some(c => c.id === id)

  const bandOfSafe = n => n.cluster || `__free_${n.id}`
  // 行(rank)分配：先用 DFS 找出回流边(成环)，再按最长路径松弛
  const backEdges = new Set()
  {
    const adj = new Map(edges.map((e, i) => [i, []]))
    const byFrom = new Map()
    edges.forEach((e, i) => { if (!e.bidir) { if (!byFrom.has(e.from)) byFrom.set(e.from, []); byFrom.get(e.from).push(i) } })
    const state = new Map() // 0=未访问 1=在栈 2=完成
    const dfs = (u) => {
      state.set(u, 1)
      for (const i of byFrom.get(u) || []) {
        const v = edges[i].to
        if (!state.get(v)) dfs(v)
        else if (state.get(v) === 1) backEdges.add(i)
      }
      state.set(u, 2)
    }
    for (const n of nodes) if (!state.get(n.id)) dfs(n.id)
  }
  const active = edges.filter((e, i) => !backEdges.has(i))
  // 参与定向流（存在非双向边）的簇：其双向簇边的目标参与纵向排序；纯并列分组则保持并排
  const flowClusters = new Set()
  for (const e of active) if (!e.bidir) { flowClusters.add(e.from); flowClusters.add(e.to) }
  const rank = new Map(nodes.map(n => [n.id, 0]))
  const bottomOf = id => isCluster(id) ? Math.max(...members(id).map(m => rank.get(m))) : rank.get(id)
  for (let iter = 0; iter < nodes.length + clusters.length + 2; iter++) {
    let changed = false
    for (const e of active) {
      if (e.bidir && !flowClusters.has(e.from)) continue // 纯并列分组：不加行约束，保持并排
      const need = bottomOf(e.from) + 1
      if (isCluster(e.to)) {
        for (const mm of members(e.to)) if (rank.get(mm) < need) { rank.set(mm, need); changed = true }
      } else if (rank.get(e.to) < need) { rank.set(e.to, need); changed = true }
    }
    if (!changed) break
  }
  // 簇内浮动节点（无边）：放到受约束节点的最深行的上一行
  for (const c of clusters) {
    const constrained = c.members.filter(mm => active.some(e => (e.from === mm || e.to === mm) && !e.bidir))
    const floaters = c.members.filter(mm => !constrained.includes(mm))
    if (floaters.length && constrained.length) {
      const deepest = Math.max(...constrained.map(mm => rank.get(mm)))
      for (const f of floaters) rank.set(f, Math.max(0, deepest - 1))
    }
  }
  const maxRank = Math.max(...nodes.map(n => rank.get(n.id)))
  const LR = graph.dir === 'LR'
  // flow = 流向轴长度, cross = 横向轴长度（LR 时节点框保持文字横向，尺寸不换轴）
  const flowSize = n => LR ? NW.get(n.id) : NH.get(n.id)
  const crossSize = n => LR ? NH.get(n.id) : NW.get(n.id)
  const VGAP = 48, CGAP = 24
  const rows = Array.from({ length: maxRank + 1 }, () => [])
  for (const n of nodes) rows[rank.get(n.id)].push(n)
  const rowBands = rows.map(r => new Set(r.map(n => n.cluster || `__free_${n.id}`)))
  const rowU = []
  let uc = 36
  for (let r = 0; r <= maxRank; r++) {
    const h = rows[r].length ? Math.max(...rows[r].map(flowSize)) : 0
    rowU[r] = uc
    const crossCluster = r + 1 <= maxRank && rows[r + 1].length && rows[r].length &&
      [...rowBands[r]].some(b => !rowBands[r + 1].has(b))
    uc += h + VGAP + (crossCluster ? 44 : 0)
  }

  // 列(band)装箱：flow 区间不重叠的 band 共用一条流向通道（纵向堆叠），重叠的沿 cross 轴并排
  const bandOf = n => n.cluster || `__free_${n.id}`
  const bandIds = new Set(nodes.map(bandOf))
  const bandNext = new Map([...bandIds].map(b => [b, new Set()]))
  const bandOfEntity = id => isCluster(id) ? id : (nodes.find(n => n.id === id) ? bandOf(nodes.find(n => n.id === id)) : null)
  for (const e of active) {
    const ba = bandOfEntity(e.from), bb = bandOfEntity(e.to)
    if (ba && bb && ba !== bb) bandNext.get(ba).add(bb)
  }
  const bandLevel = new Map([...bandIds].map(b => [b, 0]))
  for (let i = 0; i < bandIds.size + 1; i++)
    for (const b of bandIds)
      for (const nx of bandNext.get(b))
        if (bandLevel.get(nx) < bandLevel.get(b) + 1) bandLevel.set(nx, bandLevel.get(b) + 1)
  const bandOrder = [...bandIds].sort((a, b) => bandLevel.get(a) - bandLevel.get(b) ||
    (clusters.findIndex(c => c.id === a) + 1 || 999) - (clusters.findIndex(c => c.id === b) + 1 || 999))
  const GAPX = 56
  const bandV = new Map(), bandC = new Map()
  const columns = [] // { occupied: [{min,max,end}] }
  for (const b of bandOrder) {
    const bNodes = nodes.filter(n => bandOf(n) === b)
    const ranks = [...new Set(bNodes.map(n => rank.get(n.id)))]
    let w = 0
    for (const r of ranks) {
      const rn = bNodes.filter(n => rank.get(n.id) === r)
      w = Math.max(w, rn.reduce((s2, n) => s2 + crossSize(n), 0) + CGAP * (rn.length - 1))
    }
    const hdr = clusters.find(c => c.id === b)
    if (hdr) w = Math.max(w, measure(hdr.label, 12, 600) + 36)
    bandC.set(b, w)
    const span = { min: Math.min(...ranks), max: Math.max(...ranks) }
    let col = columns.find(c => !c.occupied.some(o => span.min <= o.max && o.min <= span.max))
    if (!col) {
      col = { occupied: [], v: columns.length ? Math.max(...columns.flatMap(c => c.occupied.map(o => o.end))) + GAPX : 36 }
      columns.push(col)
    }
    bandV.set(b, col.v)
    col.occupied.push({ ...span, end: col.v + w })
  }
  // 节点坐标：band 内按 rank 居中排布（u=流向, v=横向）
  const pos = new Map()
  for (const b of bandOrder) {
    const bNodes = nodes.filter(n => bandOf(n) === b)
    const ranks = [...new Set(bNodes.map(n => rank.get(n.id)))].sort((a, b2) => a - b2)
    for (const r of ranks) {
      const rn = bNodes.filter(n => rank.get(n.id) === r).sort((a, b2) => nodes.indexOf(a) - nodes.indexOf(b2))
      const total = rn.reduce((s2, n) => s2 + crossSize(n), 0) + CGAP * (rn.length - 1)
      let v = bandV.get(b) + (bandC.get(b) - total) / 2
      for (const n of rn) {
        pos.set(n.id, { u: rowU[r], v, fs: flowSize(n), cs: crossSize(n), w: NW.get(n.id), h: NH.get(n.id) })
        v += crossSize(n) + CGAP
      }
    }
  }
  for (const p of pos.values()) { p.uMax = p.u + p.fs; p.vMax = p.v + p.cs; p.uC = p.u + p.fs / 2; p.vC = p.v + p.cs / 2 }
  // 簇外框（头部条永远在 flow 较小一侧的顶端）
  const box = new Map()
  for (const c of clusters) {
    const ps = c.members.map(mm => pos.get(mm))
    const u1 = Math.min(...ps.map(p => p.u)), v1 = Math.min(...ps.map(p => p.v))
    const u2 = Math.max(...ps.map(p => p.uMax)), v2 = Math.max(...ps.map(p => p.vMax))
      const hdrW = measure(c.label, 12, 600) + 36
    // 头部条(28) 永远在真实 y 轴顶端：TD 时占 flow 轴，LR 时占 cross 轴
    const b = {}
    if (LR) {
      b.u = u1 - 16; b.v = v1 - 44
      b.fs = Math.max(u2 - u1 + 32, hdrW); b.cs = v2 - v1 + 60
    } else {
      b.u = u1 - 44; b.v = v1 - 16
      b.fs = u2 - u1 + 60; b.cs = Math.max(v2 - v1 + 32, hdrW)
    }
    b.uMax = b.u + b.fs; b.vMax = b.v + b.cs; b.uC = b.u + b.fs / 2; b.vC = b.v + b.cs / 2
    box.set(c.id, b)
  }
  // 映射到 x/y：节点框 w/h 始终为文字尺寸；簇头部条永远在真实 y 轴顶端
  // （抽象簇框只含 16px 内边距供连线锚定；绘制时 TD 在 flow 轴、LR 在 cross 轴额外加 28px 头部空间）
  for (const p of pos.values()) {
    if (LR) { p.x = p.u; p.y = p.v } else { p.x = p.v; p.y = p.u }
    p.cx = p.x + p.w / 2; p.cy = p.y + p.h / 2
  }
  for (const b of box.values()) {
    if (LR) { b.x = b.u; b.y = b.v; b.w = b.fs; b.h = b.cs }
    else { b.x = b.v; b.y = b.u; b.w = b.cs; b.h = b.fs }
  }
  return { pos, box, active, backEdges, nodes, clusters }
}

// ---------- 连线路由（flow/cross 抽象坐标，渲染时映射为 x/y） ----------
function route(e, lay) {
  const { pos, box, backEdges, edges, nodes } = lay
  const anchor = id => box.has(id) ? box.get(id) : pos.get(id)
  const clusterOf = id => nodes.find(n => n.id === id)?.cluster
  const a = anchor(e.from), b = anchor(e.to)
  const pts = []
  if (backEdges.has(edges.indexOf(e))) {
    // 回流边：从源节点侧面出，绕簇 cross 正外侧向上，进入目标节点侧面，避免与主链重叠
    const aC = box.get(clusterOf(e.from)), bC = box.get(clusterOf(e.to))
    const Xc = Math.max(a.vMax, b.vMax, aC?.vMax ?? -Infinity, bC?.vMax ?? -Infinity) + 16
    pts.push([a.uC, a.vMax], [a.uC, Xc], [b.uC, Xc], [b.uC, b.vMax])
    return pts.map(([u, v]) => lay.graph.dir === 'LR' ? [u, v] : [v, u])
  }
  const A = box.get(e.from), B = box.get(e.to)
  if (A && B && e.bidir && Math.abs(a.u - b.u) < 10 && a.vMax < b.v) {
    // 并排簇横向连线
    const y = Math.max(a.u, b.u) + 48
    pts.push([y, a.vMax], [y, b.v])
  } else if (A && B && a.uMax < b.u + 2) {
    // 纯前后簇间：前面簇的出发面 → 后面簇的顶端
    let m = (a.uMax + b.u) / 2
    if (Math.abs(a.vC - b.vC) < 2) pts.push([a.uMax, a.vC], [b.u, b.vC])
    else pts.push([a.uMax, a.vC], [m, a.vC], [m, b.vC], [b.u, b.vC])
  } else {
    let m = (a.uMax + b.u) / 2
    if (box.has(e.to)) m = Math.min(m, b.u - 10)
    // 目标是簇首行节点且从上方进入：绕簇 cross 外侧进入其侧面，避免连线穿过头部条文字
    const C = box.get(clusterOf(e.to))
    const firstRow = C && b.u - C.u <= 46
    const fromAbove = !C || a.uMax < C.u + 30
    if (C && firstRow && fromAbove) {
      const Xc = C.vMax + 16
      pts.push([a.uMax, a.vC], [m, a.vC], [m, Xc], [b.uC, Xc], [b.uC, b.vMax])
    } else if (Math.abs(a.vC - b.vC) < 2) {
      pts.push([a.uMax, a.vC], [b.u, b.vC])
    } else {
      pts.push([a.uMax, a.vC], [m, a.vC], [m, b.vC], [b.u, b.vC])
    }
  }
  // flow/cross -> x/y
  return pts.map(([u, v]) => lay.graph.dir === 'LR' ? [u, v] : [v, u])
}

function esc(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;') }

async function render(inPath, outPath) {
  const graph = parseMMD(fs.readFileSync(inPath, 'utf-8'))
  const browser = await puppeteer.launch({ args: ['--no-sandbox', '--font-render-hinting=none'] })
  const page = await browser.newPage()
  await page.setContent('<html><body></body></html>')
  // 预先批量测量所有节点/子图/边标签的像素宽度（evaluate 无法直接返回函数）
  const texts = new Set()
  for (const n of graph.nodes) for (const l of n.lines) texts.add(l)
  for (const c of graph.clusters) texts.add(c.label)
  for (const e of graph.edges) if (e.label) texts.add(e.label)
  const widthCache = await page.evaluate((list) => {
    const cv = document.createElement('canvas').getContext('2d')
    const out = {}
    for (const [text, size, weight] of list) {
      cv.font = `${weight} ${size}px 'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif`
      out[`${size}|${weight}|${text}`] = cv.measureText(text).width
    }
    return out
  }, [...texts].flatMap(t => [[t, 13, 500], [t, 12, 600], [t, 11, 400]]))
  const measure = (text, size, weight) => widthCache[`${size}|${weight}|${text}`] ?? text.length * size
  await browser.close()
  const lay = layout(graph, measure)
  lay.graph = graph
  const { pos, box } = lay
  const labelW = (t) => measure(t, 11, 400) + 14

  // 先在 TD 空间完成布线
  const routes = new Map()
  for (const e of graph.edges) routes.set(e, route(e, { ...lay, edges: graph.edges }))

  const out = []
  for (const c of graph.clusters) {
    const b = box.get(c.id)
    out.push(`<g class="subgraph" data-id="${c.id}" data-label="${esc(c.label)}">`)
    out.push(`  <rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="0" ry="0" fill="var(--_group-fill)" stroke="var(--_node-stroke)" stroke-width="1" />`)
    out.push(`  <rect x="${b.x}" y="${b.y}" width="${b.w}" height="28" rx="0" ry="0" fill="var(--_group-hdr)" stroke="var(--_node-stroke)" stroke-width="1" />`)
    out.push(`  <text x="${b.x + 12}" y="${b.y + 14}" font-size="12" font-weight="600" fill="var(--_text-sec)" dy="4.2">${esc(c.label)}</text>`)
    out.push(`</g>`)
  }
  for (const e of graph.edges) {
    const pts = routes.get(e)
    const dash = e.style === 'dotted' ? ' stroke-dasharray="4 3"' : ''
    const sw = e.style === 'thick' ? 2 : 1
    const ms = e.bidir ? ' marker-start="url(#arrowhead-start)"' : ''
    out.push(`<polyline class="edge" data-from="${e.from}" data-to="${e.to}" data-style="${e.style}" data-arrow-start="${e.bidir}" data-arrow-end="true" points="${pts.map(p => `${p[0]},${p[1]}`).join(' ')}" fill="none" stroke="var(--_line)" stroke-width="${sw}"${dash}${ms} marker-end="url(#arrowhead)" />`)
    if (e.label) {
      const m1 = pts[Math.max(0, pts.length - 3)], m2 = pts[Math.max(1, pts.length - 2)]
      const mx = (m1[0] + m2[0]) / 2, my = (m1[1] + m2[1]) / 2
      const w = labelW(e.label)
      out.push(`<g class="edge-label" data-from="${e.from}" data-to="${e.to}" data-label="${esc(e.label)}">`)
      out.push(`  <rect x="${mx - w / 2}" y="${my - 11}" width="${w}" height="22" rx="2" ry="2" fill="var(--bg)" stroke="var(--_inner-stroke)" stroke-width="1" />`)
      out.push(`  <text x="${mx}" y="${my}" text-anchor="middle" font-size="11" font-weight="400" fill="var(--_text-sec)" dy="3.85">${esc(e.label)}</text>`)
      out.push(`</g>`)
    }
  }
  for (const n of graph.nodes) {
    const p = pos.get(n.id)
    out.push(`<g class="node" data-id="${n.id}" data-label="${esc(n.label)}" data-shape="${n.shape}">`)
    if (n.shape === 'diamond') {
      const cx = p.x + p.w / 2, cy = p.y + p.h / 2
      out.push(`  <polygon points="${cx},${p.y - 12} ${p.x + p.w / 2 + 36},${cy} ${cx},${p.y + p.h + 12} ${p.x + p.w / 2 - 36},${cy}" fill="var(--_node-fill)" stroke="var(--_node-stroke)" stroke-width="0.75" />`)
    } else {
      out.push(`  <rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="0" ry="0" fill="var(--_node-fill)" stroke="var(--_node-stroke)" stroke-width="0.75" />`)
    }
    const lines = n.lines, cy = p.y + p.h / 2
    const firstDy = 4.55 - (lines.length - 1) * 8.45
    const tspans = lines.map((l, i) => `<tspan x="${p.cx}" dy="${i === 0 ? firstDy : 16.9}">${esc(l)}</tspan>`).join('')
    out.push(`  <text x="${p.cx}" y="${cy}" text-anchor="middle" font-size="13" font-weight="500" fill="var(--_text)">${tspans}</text>`)
    out.push(`</g>`)
  }
  const xs = [], ys = []
  for (const p of pos.values()) { xs.push(p.x, p.x + p.w); ys.push(p.y, p.y + p.h) }
  for (const b of box.values()) { xs.push(b.x, b.x + b.w); ys.push(b.y, b.y + b.h) }
  for (const pts of routes.values()) for (const pt of pts) { xs.push(pt[0]); ys.push(pt[1]) }
  for (const e of graph.edges) {
    if (!e.label) continue
    const pts = routes.get(e)
    const m1 = pts[Math.max(0, pts.length - 3)], m2 = pts[Math.max(1, pts.length - 2)]
    const w = labelW(e.label)
    xs.push((m1[0] + m2[0]) / 2 - w / 2, (m1[0] + m2[0]) / 2 + w / 2)
    ys.push((m1[1] + m2[1]) / 2 - 11, (m1[1] + m2[1]) / 2 + 11)
  }
  const W = Math.max(...xs) + 24, H = Math.max(...ys) + 24
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" style="${PALETTE};background:var(--bg)">
<style>${STYLE_BLOCK}</style>
<defs>${DEFS}</defs>
${out.join('\n')}
</svg>
`
  fs.writeFileSync(outPath, svg)
  console.log(`rendered ${outPath} (${Math.round(W)}x${Math.round(H)})`)
}

const [, , inPath, outPath] = process.argv
render(inPath, outPath).catch(e => { console.error(e); process.exit(1) })
