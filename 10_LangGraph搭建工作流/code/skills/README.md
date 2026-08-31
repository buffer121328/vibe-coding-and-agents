# Skill 索引：FastAPI + Air 改造工具箱

本目录是 `travel_agent_v2` Web 层改造（FastAPI 后端 + Air 前端）的配套 skills。**改造已于 2026-08-29 执行完毕**（三层测试全绿，详见 [../docs/refactor-plan-fastapi-air.md](../docs/refactor-plan-fastapi-air.md) 的状态头与实测偏差记录）；以下 skills 保留作为维护与后续升级参考：

| 文件 | 内容 | 何时读 |
| :--- | :--- | :--- |
| [air-frontend-skill.md](air-frontend-skill.md) | Air 框架版本卡（alpha、Python≥3.13）、核心 API、与 FastAPI 共存的两种模式、迁移对照表、风险与回滚 | **最先读**——含环境准备与同名项目陷阱 |
| [fastapi-graph-service-skill.md](fastapi-graph-service-skill.md) | 把编译后的 LangGraph 图包成 HTTP 服务的关键模式：stream 消费、interrupt 挂起判定、子图穿透、批准/驳回、并发边界 | 第二读——后端设计依据 |
| [web-testing-skill.md](web-testing-skill.md) | 假模型驱动三层测试（处理函数 / TestClient / 真实服务），剧本编写铁律与消耗清单 | 写测试前读 |
| [gradio-frontend-skill.md](gradio-frontend-skill.md) | 图工作台（../workbench）的前端操作手册：排版/美观/交互规范、SVG 点亮机制、示例工厂重构约定、新增关卡检查单 | 改版式 / 加关卡前读 |

配套改造计划：[../docs/refactor-plan-fastapi-air.md](../docs/refactor-plan-fastapi-air.md)

> 事实核验日期：2026-08-29。Air 处于 alpha（0.48.1），动手前建议重查 PyPI 版本与官方 llms.txt。
