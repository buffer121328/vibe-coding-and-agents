# LangGraph 图工作台（第十章配套可视化演示）

> 把 `../examples/` 里 13 个分节示例搬上台面：**课本示例的真实 LangGraph 图在跑，工作台只是把它点亮。**
> 左边是图（House 风格 SVG），跑完一个节点点亮一个；下面是「过程透视」终端，逐节点打印状态增量。全部演示**零 API Key**（假模型 / 规则驱动）。

## 运行

```bash
cd workbench
uv venv --python 3.13 && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python app.py        # 浏览器打开 http://127.0.0.1:7860
```

## 13 道关卡（对应 10.2~10.14 节）

| 关卡 | 图机制 | 交互看点 |
| :--- | :--- | :--- |
| 🧱 10.2 State 图 | StateGraph / add_edge / stream | greeter → echo 接力，徽章逐个点亮 |
| 🚦 10.3 条件路由 | add_conditional_edges / Literal | 换输入文本，只点亮命中的支路 |
| 🕸 10.4 Send 并行 | Send / operator.add / 隐式屏障 | 城市清单决定并行路数（虚线 Send 边） |
| 📡 10.5 流式调试 | stream_mode=updates vs values | 两种流对照，观察增量与全量的差别 |
| 🧠 10.6 记忆与 HITL | MemorySaver / interrupt_before | 敏感操作被「刹车」拦停 → 批准/驳回 |
| 🏨 10.7 状态栈 | dialog_state 自定义 reducer | 压栈/弹栈全过程，栈条实时回显 |
| 🛠 10.8 工具循环 | ToolNode / tools_condition | ReAct 闭环：assistant ⇄ tools |
| 🧩 10.9 设计模式 | Routing / Orchestrator-Worker / Evaluator-Optimizer | 三张图三个 Tab，改稿循环带保险丝 |
| 🗄 10.10 记忆与 Time Travel | Store / get_state_history / update_state | 跨会话档案 + 回到 A 点改道 |
| 🛡 10.11 持久执行 | RetryPolicy / Checkpointer | 重试自愈 + 崩溃后从快照复活 |
| 🪆 10.12 子图嵌套 | 子图.compile() / xray | 共享键透传，透视子图内部 |
| 🎭 10.12b 多智能体三范式 | Router / Supervisor / Planner-Executor-Reviewer | 三张图三个 Tab：分诊台分流、循环派单（supervisor 被点亮 3 次）、改稿拉锯战带 3 版保险丝 |
| ✋ 10.13 HITL 进阶 | interrupt() / Command(resume) | 金额滑杆切换组长/老板两级审批 |
| 🧪 10.14 Functional API | @entrypoint / @task | 不画图也有持久化与人工审阅 |

## 文件结构

```
workbench/
├── app.py            # Gradio 6 单文件主程序（版式沿用 09 章实验台 indigo 体系）
├── assets/           # 18 组 {节号}-diagram.mmd + .svg（House 风格，scripts/render-house.mjs 渲染；
│                     #   12-diagram-02/03/04 与章级 img/diagrams 同源，用于 10.12b 三范式）
├── gen_assets.py     # 从示例图对象导出 mermaid 源码（改图后重跑 + 重渲染）
├── smoke_test.py     # 无 Key 冒烟：21 个用例直调各关运行逻辑（.venv/bin/python smoke_test.py）
└── requirements.txt  # gradio>=6.26 + langgraph>=1.2
```

## 改动示例后如何同步

1. `examples/xx_demo.py` 里改图结构 → `workbench/.venv/bin/python gen_assets.py`
2. 重渲染 SVG：`cd assets && for f in *.mmd; do node ../../../scripts/render-house.mjs "$f" "${f%.mmd}.svg"; done`
3. 跑冒烟：`.venv/bin/python smoke_test.py` 全绿即收工

## 设计约定

- **点亮三层同步**：节点徽章行（chip）、SVG 内节点高亮（data-lit）、过程透视终端逐条增量，三处由同一份 `stream_mode="updates"` 事件驱动；
- **示例原码零拷贝**：app.py 只 import `examples/` 的 `build_graph()` 工厂，示例即课本、课本即演示；
- **两阶段审批关**（06/13/14）：先跑到挂起 → 琥珀审批条 + 批准/驳回按钮出现 → resume 续跑；
- 版式/视觉/交互规范见 [`../skills/gradio-frontend-skill.md`](../skills/gradio-frontend-skill.md)。

## 参考

- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [Gradio 官方文档](https://www.gradio.app/docs)
- 第九章实验台（版式先例）：`../../09_LangChain搭建Agent/code/app.py`
