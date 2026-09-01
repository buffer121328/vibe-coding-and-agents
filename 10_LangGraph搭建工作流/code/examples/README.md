# 第十章分节示例代码（code/examples）

每个文件对应一个小节的最小可运行案例。**全部无需 API Key**——需要大模型的环节用 `langchain_core` 内置的假模型（按剧本返回）模拟，图的机制与真实模型完全一致。

> **双入口**：每个示例既能 `python xx_demo.py` 直跑，也暴露 `build_graph()` 等工厂函数供 [`../workbench`](../workbench/README.md)（图工作台）import——工作台跑的就是课本原码，只是把它点亮。

| 示例文件 | 对应小节 | 演示内容 |
| :--- | :--- | :--- |
| `02_state_graph_demo.py` | 02 State 图的构建与运行 | 定义 State、节点、边，stream 逐步观察 |
| `03_conditional_routing_demo.py` | 03 条件路由与动态决策 | 分诊台路由 + `Literal` 类型约束 |
| `04_parallel_send_demo.py` | 04 并行执行与 Send 动态分发 | reducer 合并 + Send Map-Reduce |
| `05_streaming_debug_demo.py` | 05 图的可视化与流式调试 | Mermaid 可视化 + `stream_mode="updates"` |
| `06_memory_hitl_demo.py` | 06 Memory 与 Human-in-the-loop | `interrupt_before` 教学断点 + 同检查点批准 + `update_state` 正式驳回 |
| `07_multiagent_stack_demo.py` | 07 MultiAgent 分层架构 | `dialog_state` 状态栈压栈/弹栈 |
| `08_tool_loop_demo.py` | 08 工具调用循环与预构建组件 | 完整 ReAct 闭环（假模型 + ToolNode + tools_condition） |
| `09_workflow_patterns_demo.py` | 09 工作流设计模式 | Routing / Orchestrator-Worker / Evaluator-Optimizer |
| `10_memory_timetravel_demo.py` | 10 长期记忆与 Time Travel | Store 跨线程档案 + 回放与改道 |
| `11_durable_execution_demo.py` | 11 持久执行与容错 | `RetryPolicy` 重试 + 断点恢复 |
| `12_subgraphs_demo.py` | 12 子图与多智能体全谱 | 父子图嵌套 + `xray` 透视 |
| `12b_multiagent_paradigms_demo.py` | 12 子图与多智能体全谱（分类节） | 当前分类下三种重点实现：Router / Subagents（Supervisor）/ Custom workflow（PER） |
| `13_hitl_interrupt_demo.py` | 13 HITL 进阶 | `interrupt()` + `Command(resume)` 多级审批 |
| `14_functional_api_demo.py` | 14 Functional API | `@entrypoint` / `@task` + 人工审阅 |

## 运行方式

```bash
pip install -U langgraph        # 唯一硬依赖（自带 langchain-core）
python 02_state_graph_demo.py   # 在本目录内逐个运行即可
```

> 15 节（部署）与 16 节（综合实战）没有独立示例：15 节的动手环节直接用 16 节 `travel_agent_v2` 的 `graph` 对象配合 `langgraph.json` 完成。
