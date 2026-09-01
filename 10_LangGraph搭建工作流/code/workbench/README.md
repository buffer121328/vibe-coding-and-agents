# LangGraph 图工作台（第十章配套可视化演示）

> 把 `../examples/` 里 14 个分节演示搬上台面：**课本示例的真实 LangGraph 图在跑，工作台把执行过程逐帧点亮。**
> 左边是图（House 风格 SVG），START / END 会像入口和出口一样显式点亮；普通节点先显示琥珀色“执行中”，完成后变为绿色。图下方先给一句 State 摘要，右侧 JSON 展示完整公共交接本，下面的「过程透视」终端逐节点打印状态增量。全部演示**零 API Key**（假模型 / 规则驱动）。

## 运行

```bash
cd workbench
uv venv --python 3.13 && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python app.py        # 浏览器打开 http://127.0.0.1:7860
```

浏览器演示默认每个节点停留约 0.55 秒，便于观察“执行中 → 已完成”的变化。想加快或关闭动画可设置 `WORKBENCH_ANIMATION_DELAY`（单位：秒）：

```bash
WORKBENCH_ANIMATION_DELAY=0 .venv/bin/python app.py
```

## 新手读图法

- **START / END 不是你写的业务函数**：它们是 LangGraph 自动加的图边界。START 点亮表示流程进入图，END 点亮表示流程离开图。工作台故意把它们也点亮，是为了让初学者看清“从哪里开始、在哪里结束”。
- **颜色表示当前进度**：灰色表示还没走到，琥珀色呼吸表示正在执行，绿色表示已经完成。普通节点变成琥珀色时，才代表对应 Python 节点函数正在运行。
- **State 有四层展示**：状态机透视用「节点卡片 + State 徽标」画出本次实际路径——每个节点下方挂一枚提交后交接本的摘要徽标（执行中显示「读取 State…」，未提交显示「待提交」），State 如何沿边一站站生长一目了然，且只在路径/增量变化时更新、不随逐帧文案闪烁；State 摘要负责快速扫一眼；右侧 JSON 是完整公共交接本；终端里的“状态更新”告诉你每个节点刚刚写入了哪些字段。循环图会保留重复节点，因此能看到 `writer → evaluator → writer` 的卡片链，不会只剩一排最终绿灯。

## 14 道关卡（对应 10.2~10.14 节，12 节含两个关卡）

| 关卡 | 图机制 | 交互看点 |
| :--- | :--- | :--- |
| 🧱 10.2 State 图 | StateGraph / add_edge / stream | greeter → echo 接力，徽章逐个点亮 |
| 🚦 10.3 条件路由 | add_conditional_edges / Literal | 换输入文本，只点亮命中的支路 |
| 🕸 10.4 Send 并行 | Send / operator.add / 隐式屏障 | 城市清单决定并行路数（虚线 Send 边） |
| 📡 10.5 流式调试 | stream_mode=updates vs values | 两种流对照，观察增量与全量的差别 |
| 🧠 10.6 记忆与 HITL | MemorySaver / interrupt_before / update_state | 同一检查点批准续跑；驳回补 ToolMessage 并跳过敏感工具 |
| 🏨 10.7 状态栈 | dialog_state 自定义 reducer | 压栈/弹栈全过程，栈条实时回显 |
| 🛠 10.8 工具循环 | ToolNode / tools_condition | ReAct 闭环：assistant ⇄ tools |
| 🧩 10.9 设计模式 | Routing / Orchestrator-Worker / Evaluator-Optimizer | 三张图三个 Tab，改稿循环带保险丝 |
| 🗄 10.10 记忆与 Time Travel | Store / Replay / update_state | 跨会话档案 + 回放真实重跑下游节点 + 回到 A 点改道 |
| 🛡 10.11 持久执行 | RetryPolicy / Checkpointer | 三次真实调用逐帧展开；崩溃点与恢复点分图显示 |
| 🪆 10.12 子图嵌套 | 子图.compile() / xray | 共享键透传，透视子图内部 |
| 🎭 10.12b 多智能体重点实现 | Router / Subagents（Supervisor）/ Custom workflow | 对照当前官方分类：分诊路由、主管调用专家、自定义规划-执行-评审流 |
| ✋ 10.13 HITL 进阶 | interrupt() / Command(resume) | 金额滑杆切换两级审批；按钮先弹确认框，Checkpoint / interrupt / resume 历史同屏变化 |
| 🧪 10.14 Functional API | @entrypoint / @task future | 两个 future 同时点亮；review 工序弹出人工审阅弹窗卡片（初稿 + 驳回意见 + 批准/打回同屏），批准后弹窗关闭 |

## 文件结构

```
workbench/
├── app.py            # Gradio 6 单文件主程序（版式沿用 09 章实验台 indigo 体系）
├── assets/           # 20 组 {节号}-diagram.mmd + .svg（House 风格，scripts/render-house.mjs 渲染；
│                     #   12-diagram-02/03/04 与章级 img/diagrams 同源，用于 10.12b 三种重点实现）
├── gen_assets.py     # 从示例图对象导出 mermaid 源码（改图后重跑 + 重渲染）
├── smoke_test.py     # 无 Key 冒烟：直调各关运行逻辑（.venv/bin/python smoke_test.py）
└── requirements.txt  # gradio>=6.26 + langgraph>=1.2
```

## 改动示例后如何同步

1. `examples/xx_demo.py` 里改图结构 → `workbench/.venv/bin/python gen_assets.py`
2. 重渲染 SVG：`cd assets && for f in *.mmd; do node ../../../../scripts/render-house.mjs "$f" "${f%.mmd}.svg"; done`
3. 跑冒烟：`.venv/bin/python smoke_test.py` 全绿即收工

## 设计约定

- **点亮五层同步**：节点徽章行（chip）、SVG 内节点高亮（data-lit）、状态机透视卡片（mnode/marrow 逐站点亮）、State 摘要、过程透视终端逐条增量，统一由节点事件驱动；当前节点以琥珀色静态描边显示（呼吸动画只保留在徽章行与 SVG 内），完成节点以绿色落定；
- **示例原码零拷贝**：app.py 只 import `examples/` 的 `build_graph()` 工厂，示例即课本、课本即演示；
- **两阶段审批关**（06/13/14）：06 展示静态断点的批准续跑与 `update_state` 正式驳回；13/14 展示 `interrupt()` + `Command(resume)`；
- 版式/视觉/交互规范见 [`../skills/gradio-frontend-skill.md`](../skills/gradio-frontend-skill.md)。

## 参考

- [LangGraph 官方文档](https://docs.langchain.com/oss/python/langgraph/overview)
- [Gradio 官方文档](https://www.gradio.app/docs)
- 第九章实验台（版式先例）：`../../09_LangChain搭建Agent/code/app.py`
