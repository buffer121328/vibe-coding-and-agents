"""forge_lite —— KnowledgeForge 蒸馏教学版包。

## 分层：六层，单向依赖

上层可以 import 下层，**反之绝对不行**。这条规矩不是写在文档里的一句愿望——
``tests/test_layering.py`` 会把整张依赖图跑一遍，出现回边、反向依赖或同层互赖就报错。

```
web/         HTTP 层：路由、页面结构、静态资源
service/     面向页面的服务：被 web 调用，也能被脚本单独调用
answer/      编排与评测：把零件串成一次完整回答
retrieve/    检索：把证据找出来
data/        数据：语料的进出
store/       持久化：会话、账号、审计、缓存
core/        零件：不依赖任何内部模块，谁都能用
```

顶层另有公共件，谁都能用：``config``（旋钮）、``contracts``（页面契约）、
``llm``（模型客户端）。``server.py`` 只是 ``web.app:app`` 的兼容导出，
给旧的 ``uvicorn forge_lite.server:app`` 留一条还能用的命令，里面不加路由。

``llm`` 单独拎出来是为了解环：模型客户端本该只有一处定义，而需要它的分处两层——
编排层要用它生成与复检，数据层要用它抽图谱三元组。客户端原本建在编排层，
数据层就得反过来依赖它，于是 ``agent → retrieve → knowledge_graph → agent`` 成了一个环。
挪到叶子模块后两层各自向它取实例、互相不认识。

## 模块 ↔ 教程对照

core/
- identity.py    11.13                演示工牌 RBAC，检索前先裁可见范围
- quality.py     11.5 / 11.8 / 11.9 / 11.13  纯函数零件（不调模型）
- chunking.py    11.2 / 11.4          结构感知切块：按标题分节 + 标题路径 + 表格整段不切
- rewrite.py     11.6                 本地改写护栏（原问题必须保留）
- evidence.py    11.8 / 11.12         生成前的证据资格（课堂版 EvidenceQualifier）
- labels.py / sseutil.py  11.13       文案表；SSE 帧协议与事件白名单

store/
- conversations.py 11.13              会话柜（SQLite，工牌隔离，刷新不丢）
- accounts.py    11.13                注册 / 登录 / 会话（pbkdf2；登出即删一行）
- audit.py / query_cache.py  11.13    审计账；精确缓存（带索引 schema 作用域）

data/
- ingest.py      11.2 / 11.4 / 11.13  解析切块 + 投毒扫描 + 哈希增量 + 三路写入
- catalog.py     11.13                目录与切块预览，和检索同一把 ACL
- acl_matrix.py  11.13                权限矩阵：四张工牌 × 全部文档的可见性
- knowledge_graph.py 11.7             图谱作为第三路召回（可降级）

retrieve/
- search.py      11.4 / 11.5 / 11.7   授权后三路召回 + 加权 RRF；BM25 切词（jieba + 二元组兜底）
- citation.py    11.12                编号引用协议
- trace.py       11.5 / 11.12         检索轨迹：查询、路由、证据资格、预算

answer/
- agent.py       11.8 / 11.12         LangGraph 自省闭环
- evaluate.py    11.9                 Ragas 0.4 collections：Faithfulness / ContextRecall / AnswerRelevancy
- evaluation.py  11.9                 评测区：逐条跑黄金集、行为与命中判定、报告留档
- classroom.py / scenarios.py 11.15   空状态剧本与越权对照题

service/
- documents.py   11.2 / 11.4 / 11.13  文档区：总览 / 上传只嵌单篇 / 删除级联 / 切块预演
- status.py      11.13                运行时体检
- export.py / graph_view.py / demo.py 11.13 / 11.7 / 11.15

web/
- app.py + pages.py + static/  11.13  登录页 + 控制台：问答 / 文档 / 评测（零构建三视图）
"""
