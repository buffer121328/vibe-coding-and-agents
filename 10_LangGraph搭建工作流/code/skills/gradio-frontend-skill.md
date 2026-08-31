# Gradio 图工作台前端 Skill（第十章 workbench）

> **何时读**：要改 `../workbench/app.py` 的版式、配色、交互，或给 13 关之外新增关卡时，先读本文再动手。
> 活样板：本文件与 `../workbench/app.py` 互为对照；更大的先例是 09 章实验台 `../../09_LangChain搭建Agent/code/app.py`（约 1560 行，本 skill 的规范源头）。

## 1. 排版规范

### 1.1 单文件 app.py 的分区顺序（雷打不动）

```
docstring（启动方式 + 设计原则一句话）
→ import：标准库 / gradio / sys.path 插入 examples / 各示例工厂 import
→ 通用工具：now() / load_svg() / chips_html() / highlight_svg() / fmt_update() / run_stream_updates()
→ 模块级会话状态：_rescue_state / _t13 / _t14（跨回调共享的挂起句柄，dict 包裹防闭包陷阱）
→ custom_css 大字符串（设计令牌在最前）
→ THEME = gr.themes.Soft(primary_hue="indigo", ...)
→ with gr.Blocks：侧边栏 → Hero → head() 工厂 → 各关 gr.Group → 导航切换 → 页脚
→ if __name__ == "__main__": demo.launch(...)
```

### 1.2 关卡页面统一版式

每关一个 `gr.Group(visible=False)`（首关 visible=True），内部自上而下：

1. `gr.HTML(head(编号, emoji, 标题, 公式芯片, 一句话解说))`——编号徽章 + 标题 + `.pipe-line` 公式芯片；
2. **图结构区**：`gr.HTML(load_svg("XX-diagram"))` + 节点徽章行 `gr.HTML(chips_html(...))`；
3. **控制区**：`gr.Column(elem_classes=["input-unit"])` 外壳包输入件，按钮行 `btn-row tail` 悬浮框内右下角；
4. **结果双栏**：`gr.Row(equal_height=True)` 左「📦 State 快照 `gr.Code(language="json")`」右「🔍 过程透视终端」。

### 1.3 导航切换

左侧 `gr.Sidebar` 内放 `gr.Radio(choices=PAGES, elem_id="nav-radio")`，`page_selector.change` 一次性返回 `[gr.update(visible=(selected==name)) for name in PAGES]` 到 13 个 Group。新增关卡 = 追加 PAGES 项 + 追加 page_groups 项，两处顺序必须一致。

## 2. 美观规范

### 2.1 设计令牌（custom_css 顶部的 .gradio-container 变量）

| 令牌 | 值 | 用途 |
| :--- | :--- | :--- |
| `--paper` | `#f3f4fb` | 页面纸面底 |
| `--card` | `#ffffff` | 卡片底 |
| `--ink` | `#1b1850` | 正文墨蓝 |
| `--chain` / `--spark` | `#4f46e5` / `#7c3aed` | indigo 主色 / violet 辅色（渐变按钮、徽章） |
| `--amber` | `#f59e0b` | **当前节点点亮色**（琥珀辉光） |
| `--mint` | `#10b981` | 已完成节点绿 |
| `--mono` | `"SF Mono","JetBrains Mono",...` | 终端/徽章/公式芯片一律等宽 |

### 2.2 三处点亮样式（本工作台的灵魂）

- **徽章行** `.chip / .chip.done / .chip.cur`：灰 → 绿（✓）→ 琥珀（●，带 `box-shadow: 0 0 0 3px` 辉光圈）；
- **SVG 内高亮**：House 渲染器输出的节点是 `<g class="node" data-id="节点名">`，用 CSS 属性选择器直接染色——`g.node[data-lit="cur"] rect { fill:#fef3c7; stroke:#f59e0b; stroke-width:2.4; filter:drop-shadow(...) }`。**前提**：图源码的节点 id 必须与 LangGraph 真实节点名一致（`gen_assets.py` 的约定）；
- **过程透视终端** `.console`：墨蓝暗底（`#0d1428→#0a0f1f`）+ 浅绿文字 + 等宽字体；label 前缀 `▍` 用 `.console .label-wrap span::before` 注入。注意 Gradio 6 的 CSS dedupe 会合并同属性规则，终端底色要用**双前缀 + 重复类名**的高特异性写法（见 app.py 里 `.gradio-container.gradio-container-6-26-0 ...` 三连选择器，09 章踩坑结论原样沿用）。

### 2.3 图资产纪律

- SVG 一律来自 `scripts/render-house.mjs`（全库统一 House 浅色风格），**不要手写 SVG**；
- House 渲染器只认矩形/菱形节点语法：起止节点写 `__start__["开始"]` 而不是 `(["开始"])`（stadium 语法会被当无标签矩形）；
- Send 等运行时动态边在静态图里不存在，`gen_assets.py` 用 `-.->|"Send"|` 虚线手工补画；
- SVG 嵌入前用 `load_svg()` 把固定 width/height 换成自适应（`width="100%"` + max-width）。

## 3. 交互规范

### 3.1 「跑一步、点亮一步」事件链

回调必须是**生成器**：内部消费 `run_stream_updates(graph, inputs, config)` 的每个 yield，立即输出（徽章 HTML、SVG HTML、快照 JSON、终端文本）四元组；循环结束后再 yield 一次收尾态（current=None）。Gradio 6 对生成器回调自动逐帧推送前端。

### 3.2 outputs 对齐铁律

`xxx.click(fn, inputs=[...], outputs=[组件...])` 的组件数必须与 fn 每次产出的元组长度**严格相等**——这是本工作台调试中最常见的翻车点（多一个 `{}` 尾项、包装函数误把 return 写成逐字 yield，都会变成前端「错误」）。冒烟测试 `smoke_test.py` 直调这些函数并按同样长度解包，就是给这条铁律上的保险。

### 3.3 两阶段审批（挂起 → 批准/驳回 → resume）

- 页面常备 `gr.HTML(visible=False)` 审批条 + 两枚 `visible=False` 按钮；
- 阶段一回调检测 `graph.get_state(config).next` 非空 → yield `gr.update(visible=True, value=审批条HTML)` 与按钮的 `gr.update(visible=True)`；
- 判定「还有下一层审批」要看 `snap.tasks` 里各 task 的 `interrupts`，**不能只看 `next`**（13 关大额二审：resume 后 `next=()` 但老板审批的 interrupts 已在 tasks 里）；
- 批准/驳回回调用 `Command(resume=...)` 续跑；`state` 里的 `__interrupt__` 键含不可序列化的 Interrupt 对象，入 JSON 前先 `pop`；
- 跨回调共享挂起句柄（graph/config）用**模块级 dict**（`_t13 = {"graph": None, ...}`），不要用闭包局部变量（Blocks 装配作用域下取不到值）。

### 3.4 状态可重置（防串台）

所有有状态的东西——假模型剧本（08）、重试计数器（11）、Checkpointer（06/10/13/14）——一律在每次点击时新建（工厂函数），或在回调开头 `reset_*()`。绝不能在模块顶层共享可变单例。

### 3.5 示例工厂重构约定（examples/ 侧）

- 每个示例暴露 `build_graph()`（多图时 `build_xxx_graph()`），`graph = build_graph()` 模块级实例仅作直跑兼容；
- 尾部运行代码包进 `main()` + `if __name__ == "__main__"` 保护；**直跑输出与重构前完全一致**是回归铁律；
- 带 Checkpointer 的示例（06 的 `build_graph`/`build_guarded`、13、14）工厂内部每次新建 MemorySaver，防止多次运行串档。

## 4. 新增关卡检查单

- [ ] `PAGES` 与 `page_groups` 同步追加
- [ ] 图资产：`gen_assets.py` 导出 + House 渲染（节点 id = 真实节点名）；文档已用的章级图可直接复制进 `assets/`（如 10.12b 的 12-diagram-02/03/04）
- [ ] 回调是生成器，outputs 长度严格对齐
- [ ] 有状态对象工厂化/可重置
- [ ] `smoke_test.py` 加对应用例并全绿
- [ ] 多 Tab 关卡（参照 10.9 / 10.12b）：每个 Tab 一套独立组件与按钮，Tab 内互不共享 outputs
