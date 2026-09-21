# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

既有技术栈（非绿地，无需选型）：`air.Air`（FastAPI 子类）出页面结构，原生 HTML/CSS/JS 零构建，
静态资源在 `forge_lite/web/static/`。这条选择由项目"教学代码必须一眼看懂、不许 npm/vite"的约束决定，
不在本轮重新讨论。

## Users

- **主要用户**：跟着《第十一章 RAG》学习的学生 / 转行工程师。他们在课堂上刚学完解析、嵌入、混合检索、
  改写、图谱、自省闭环、评估、工程化九个零件，需要看见它们在一台真机器里怎么咬合。
- **使用场景**：一台笔记本电脑、一间教室或自习室；可能还没配好 API Key；老师会现场切工牌演示越权对照。
- **要完成的任务**：问一句制度问题 → 看见带角标的答案 → 点角标读原文 → 换工牌看权限差异 →
  理解"为什么拒答"和"为什么这句话有出处"。

## Purpose

把"能不能搜到"和"能不能看见"这两件事同时演示清楚。产品让"权限先于检索"这条纪律**可见**：
同一句问题在不同工牌下，不是答案被涂掉，而是资料根本不在候选池里。

## Differentiating mechanism

- **检索前裁库**：`visible_department_ids` 决定候选池，权限不是生成后的过滤器；
- **三路召回进同一套 RRF**：向量 + BM25 + 图谱，图谱命中也必须指回源切块；
- **生成前的证据资格**：够答 / 部分 / 背景 / 冲突 / 不足，不够就不进生成；
- **四道闸门**：证据资格 → 分级 → 引用格式 → 忠实度复检，每关只许重试一次，不过就拒答；
- **会话服务端权威**：会话在 SQLite 里，刷新不丢；浏览器只记工牌和当前会话号。

## Durable constraints

- 不许 npm / 构建步骤；任何组件都必须能在"纯 Python + 静态文件"里读懂；
- 离线可跑：无 API Key 时也要能演示权限矩阵、证据资格、会话柜（`scripts/06_demo.py`）；
- 术语沿用课堂（工牌、会话、出处、轨迹、证据资格），不引入新的黑话；
- 运行产物一律落 `runtime/`，且不入库；
- 密钥只走 `.env`，任何页面/接口都不得回显。

## Terminology

工牌（actor/badge）· 会话柜（conversation cabinet）· 出处（citation chunk）·
检索轨迹（run trace）· 证据资格（evidence qualification）· 原问题（original query）

## Accessibility

键盘可用（Tab / Enter 提交、角标可聚焦）、`:focus-visible` 有主题化焦点环、
尊重 `prefers-reduced-motion`、正文对比度 ≥ 4.5:1、答案区行宽 ≤ 75ch。

## Open decisions

- 学生自己的知识库文件替换成什么行业场景（当前是公司制度 + 一份投毒 HTML 样本）；
- 是否补 3D 图谱（完整版有，Lite 明确不做）。
