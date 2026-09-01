# RAG 工作台前端与真实调用 Skill（第十一章 rag_workbench）

> **何时读**：要改 `../rag_workbench/app.py`、加新关卡，或把新脚本接进工作台时，先读本文再动手。
> 基础排版/美观/交互规范**与第十章共用**：先读 [10_LangGraph搭建工作流/code/skills/gradio-frontend-skill.md](../../../10_LangGraph搭建工作流/code/skills/gradio-frontend-skill.md)，本文只讲第十一章的增量。

## 1. 与第十章工作台的三点差异

| 维度 | 10 章图工作台 | 11 章 RAG 工作台 |
| :--- | :--- | :--- |
| 调用模式 | 零 Key（假模型/规则） | **真实调用**（读 `../.env`，每次点击消耗 Token） |
| 可视化主角 | 图结构 SVG + 节点点亮 | 管道产物 + 章节配图（`../../img/diagrams/`） |
| 每关版式增量 | 无 | 顶部**痛点横幅** `.pain-bar`（本章问题驱动叙事） |

## 2. 真实调用的接线规范

### 2.1 模型配置链（app.py 顶部，顺序固定）

```
load_dotenv(../.env)
→ CHAT_MODEL / EMBEDDING_MODEL（缺失时从 ARK_MODEL_ENDPOINT 推导，默认 gpt-4o-mini）
→ OPENAI_BASE_URL / OPENAI_API_KEY（缺失时从 ARK_BASE_URL / ARK_API_KEY 推导）
```

所有脚本已改造为环境变量优先：`ChatOpenAI(model=os.getenv("CHAT_MODEL", "gpt-4o-mini"))`、
`OpenAIEmbeddings(model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"), check_embedding_ctx_length=False)`。
**新脚本接进工作台前先做同样改造**，换供应商只动 `.env`。

### 2.2 doubao/ARK 嵌入端点的坑（实测踩过）

- `OpenAIEmbeddings` 必须加 **`check_embedding_ctx_length=False`**：langchain 默认用 tiktoken 把输入切成 token 数组再发，doubao 端点只吃字符串，否则报 `input[0] expected a string, but got [30624 99849 ...]`；
- `CHAT_MODEL` 与 `EMBEDDING_MODEL` 是**两个端点能力**：deepseek 不吃图片，doubao-embedding 不聊天——别共用一个模型名。

### 2.3 依赖版本兼容（2026-08 实测，重装环境前先查）

| 症状 | 原因 | 修法 |
| :--- | :--- | :--- |
| `No module named 'langchain.retrievers'` | langchain 1.x 经典层搬进 `langchain_classic` | `from langchain_classic.retrievers import ...`（storage 同理） |
| `QdrantClient has no attribute 'search'` | qdrant-client 新版移除 `.search` | `query_points(query=..., search_params=SearchParams(hnsw_ef=...)).points`；`HnswConfigDiff` 已无 `ef` 字段 |
| ragas 导入报 vertexai | ragas 0.2.6 硬 import 已被 langchain-community 0.4 移除的模块 | 给 site-packages 里 `ragas/llms/base.py` 的该 import 打 try/except 补丁（见 rag_workbench README 环境段） |
| ragas 结果取列 KeyError | 0.2.x 结果列名 v2 化 | `question→user_input / contexts→retrieved_contexts / answer→response` |

## 3. 关卡回调规范（run_captured 模式）

每关回调不重写教材逻辑，只做三件事：

1. **捕获 stdout**：`run_captured(fn, *args)` 跑脚本里的 `demo_xxx()`，抓 print 为「过程透视」文本并附耗时——脚本本身就是课本，工作台不复制逻辑；
2. **结构化快照**：需要 JSON 卡的关（路由结果、引用校验）在 runner 里用正则/返回值抓关键产物，`json.dumps` 前确认无不可序列化对象；
3. **优雅跳过**：依赖本地模型/外部资源的演示（ColBERT 首跑下载、VLM 图片、本地音频）必须 try/except 后打印「跳过原因 + 生产做法」，绝不让页面弹「错误」。

## 4. 新增关卡检查单

- [ ] 脚本完成模型环境变量化改造（CHAT/EMBEDDING 两个 getenv）
- [ ] 回调用 `run_captured` 包 demo 函数，outputs 长度严格对齐（(snap, console) 两元组）
- [ ] 资源缺失路径实测过（断网/无模型/无文件时页面不报错）
- [ ] `smoke_test.py` 加对应用例并全绿（真实调用用例注明消耗 Token）
- [ ] PAGES 与 page_groups 同步追加
