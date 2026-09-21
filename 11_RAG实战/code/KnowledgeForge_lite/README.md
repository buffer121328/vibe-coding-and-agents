# 🏭 KnowledgeForge Lite —— 端到端综合实战（11.15 配套）

这是第十一章的“总装项目”：把 11.2~11.14 学到的零件**总装成一台能跑的机器**。它是完整版 [KnowledgeForge](https://github.com/buffer121328/KnowledgeForge) 的蒸馏教学版——主干与完整版同构（**工牌先裁可见范围 → 三路召回进 RRF → 证据不够就拒答**），实现保持课堂体量。砍掉的是 JWT/Celery/Kafka/React 3D，不是检索思想、权限纪律和审计账。一个下午可以读完并跑通，读完整版时这份地图就是翻译词典。

## 目录分层：六层，单向依赖

`forge_lite/` 按**依赖方向**分六层——上层可以 import 下层，反之绝对不行。
这条规矩是机械可查的（`tests/test_layering.py` 会跑一遍依赖图，发现回边就报错）：

```
┌──────────────────────────────────────────────────────────────┐
│ web/         HTTP 层：路由、页面结构、静态资源                  │
│              app.py · pages.py · static/                      │
├──────────────────────────────────────────────────────────────┤
│ service/     面向页面的服务：被 web 调用，也能被脚本单独调用      │
│              documents · status · export · graph_view · demo   │
├──────────────────────────────────────────────────────────────┤
│ answer/      编排与评测：把零件串成一次完整回答                  │
│              agent · evaluate · evaluation · scenarios · classroom │
├──────────────────────────────────────────────────────────────┤
│ retrieve/    检索：把证据找出来                                 │
│              search · citation · trace                         │
├──────────────────────────────────────────────────────────────┤
│ data/        数据：语料的进出                                   │
│              ingest · catalog · acl_matrix · knowledge_graph   │
├──────────────────────────────────────────────────────────────┤
│ store/       持久化：会话、账号、审计、缓存                      │
│              conversations · accounts · audit · query_cache    │
├──────────────────────────────────────────────────────────────┤
│ core/        零件：不依赖任何内部模块，谁都能用                   │
│              identity · quality · chunking · rewrite ·         │
│              evidence · labels · sseutil                       │
└──────────────────────────────────────────────────────────────┘
   顶层公共件：config.py（旋钮）· contracts.py（页面契约）· llm.py（模型客户端）
   server.py 只是 web.app:app 的兼容导出，里面不加路由
```

**为什么 `llm.py` 单独拎出来**：模型客户端本该只有一处定义，而需要它的分处两层——
编排层要用它生成与复检，数据层要用它抽图谱三元组。客户端建在编排层，数据层就得反过来
依赖它，于是 `agent → retrieve → knowledge_graph → agent` 成了一个环。挪到叶子模块后，
两层各自向 `llm` 取实例、互相不认识——**这是"解耦"最常见的收益：不是把代码拆小，
是把不该碰面的东西隔开。**

## 模块 ↔ 教程 ↔ 完整版对照地图

| 层 | 本项目文件 | 对应教程 | 蒸馏自完整版 / 装了什么 |
| :--- | :--- | :--- | :--- |
| 公共 | `config.py` | 11.13 | `shared/config`：索引时旋钮 vs 检索时旋钮；索引形状版本由零件拼出 |
| 公共 | `llm.py` | 11.4 | 模型工厂：一个延迟创建的共用 Chat 客户端（解环用） |
| 公共 | `contracts.py` | 11.13 | 页面 DOM id 与前端字段契约 |
| core | `core/identity.py` | 11.13 | 检索层 ACL：四张演示工牌，**打分前**按部门/密级裁库 |
| core | `core/quality.py` | 11.5 / 11.8 / 11.9 / 11.13 | 纯函数零件：RRF、装箱、去重、引用门禁、RunBudget、投毒扫描、PII 脱敏 |
| core | `core/chunking.py` | 11.2 / 11.4 | 结构感知切块：按标题分节 + 标题路径 + 表格整段不切 |
| core | `core/rewrite.py` | 11.6 | `services/qa/query.py`：本地改写（原问题必须保留 + 顿号拆主题），模型扩写可选 |
| core | `core/evidence.py` | 11.8 / 11.12 | `EvidenceQualifier`：生成前的证据资格（直接 / 部分 / 背景 / 冲突 / 不足） |
| core | `core/labels.py` · `core/sseutil.py` | 11.13 | 文案表；SSE 帧协议与事件白名单 |
| store | `store/conversations.py` | 11.13 | `PostgreSQLQAHistoryRepository`：SQLite 会话柜，工牌隔离、软删除、游标分页 |
| store | `store/accounts.py` | 11.13 | 注册 / 登录 / 会话（pbkdf2 + 服务端会话表，登出即删一行） |
| store | `store/audit.py` | 11.13 | 审计账 JSONL：谁问过什么，员工读不到管理员的账 |
| store | `store/query_cache.py` | 11.13 | 精确缓存：工牌 + 问句 + 索引 schema 才许命中 |
| data | `data/ingest.py` | 11.2 / 11.4 / 11.13 | `ingest_document`：解析切块 + 部门/密级元数据 + 投毒隔离 + 三路写入 |
| data | `data/catalog.py` | 11.13 | documents catalog + `docApi.chunks`：点角标看原文，与检索同一把 ACL |
| data | `data/acl_matrix.py` | 11.13 | 权限矩阵：四张工牌 × 全部文档的可见性，工牌卡的计数从这来 |
| data | `data/knowledge_graph.py` | 11.7 | `knowledge_extractor`：图谱作为**第三路召回**，命中映射回源切块 |
| retrieve | `retrieve/search.py` | 11.4 / 11.5 / 11.7 | `retrievers` + `hybrid_rerank`：授权后向量 + BM25 + 图谱，加权 RRF |
| retrieve | `retrieve/citation.py` | 11.12 | `qa_grounding`：编号协议 + 幽灵引用校验 |
| retrieve | `retrieve/trace.py` | 11.5 / 11.12 | QA run 详情：查询、路由、证据资格、预算 |
| answer | `answer/agent.py` | 11.6 / 11.8 / 11.12 | `qa_agent`：改写→三路检索→资格→分级→生成→校验→复检 |
| answer | `answer/evaluate.py` | 11.9 | Ragas 0.4 官方 collections：Faithfulness / ContextRecall / AnswerRelevancy |
| answer | `answer/evaluation.py` | 11.9 | `evaluation/` 的 runner：逐条跑黄金集、行为与命中判定、报告留档 |
| answer | `answer/classroom.py` · `scenarios.py` | 11.15 | 空状态剧本与越权对照题；页面与测试共用一份 |
| service | `service/documents.py` | 11.2 / 11.4 / 11.13 | `documents` 路由：总览（含隔离原因）/ 上传只嵌单篇 / 删除级联 / 切块预演 |
| service | `service/status.py` | 11.13 | 运行时体检：索引 schema 漂移、图谱、会话、账本 |
| service | `service/export.py` | 11.13 | 会话导出 Markdown / JSON（脱敏、只导自己的会话） |
| service | `service/graph_view.py` | 11.7 | `frontend/` 3D 图谱的课堂平面版：按工牌裁邻接，点开原文 |
| service | `service/demo.py` | 11.15 | 无 API Key 的离线走查：权限矩阵 / 证据资格 / 会话 / 图谱 |
| web | `web/app.py` | 11.13 | `api/`：`air.Air` + SSE（先验证再分片）+ 全部路由 |
| web | `web/pages.py` + `web/static/` | 11.13 | `frontend/`：登录页 + 控制台三视图（问答 · 文档 · 评测），零构建 |

## 快速开始

```bash
cd code/KnowledgeForge_lite
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 在本目录创建 .env（或放在仓库根目录），填入 OpenAI 兼容端点：
#   OPENAI_API_KEY=sk-xxx
#   OPENAI_BASE_URL=https://api.xxx.com/v1   # 可选，DeepSeek/智谱等兼容端点

python -m unittest discover -s tests -v                  # ⓪ 离线门禁（无需 API Key，450 个用例）
python scripts/06_demo.py                                # ① 离线走查：工牌矩阵 / 证据资格 / 会话柜 / 图谱
python scripts/01_ingest.py                              # ② 入库（幂等；投毒 HTML 隔离；种子图谱垫底）
python scripts/02_ask.py "去上海出差住一晚能报多少？"       # ③ 命令行问答（默认 IT 员工工牌）
python scripts/02_ask.py "出差回来晚了一天，钱最晚啥时候能到手？"  # 口语题：11.6 改写后仍应命中报销时限
python scripts/02_ask.py "公司年终奖一般发几个月？"         #    试拒答：库里没有就老实说
python scripts/02_ask.py "P6 薪酬带宽是多少？" it_staff    #    越权拒答：员工看不见财务密级
python scripts/02_ask.py "P6 薪酬带宽是多少？" finance_head #    财务负责人应能引用密级文档
python scripts/03_evaluate.py                            # ④ 门禁层（行为 + 期望文档召回，不调裁判；改完代码先跑这个）
python scripts/04_ragas_eval.py                          #    体检层：Ragas 0.4 三指标（要裁判模型，八条可能要几十分钟）
python scripts/05_build_graph.py                         # ⑤ 可选：LLM 补抽三元组写入 Neo4j（入库已有种子）
python scripts/07_status.py                               # ⑥ 运行时体检：索引 schema 漂移 / 图谱 / 会话柜 / 账本
uvicorn forge_lite.web.app:app --port 8800                # ⑦ 起服务：http://127.0.0.1:8800/ 控制台三视图
#    旧命令 uvicorn forge_lite.server:app 仍可用（server.py 只是兼容层，路由仍在 web/app.py）
#    控制台里：问答区（问一句、点角标、看轨迹）/ 文档区（上传、切块、隔离原因）/
#    评测区（逐条跑黄金集、Ragas 三指标、历史报告）——文档区与评测区按角色只对管理员开放
```

## Docker 方式运行（推荐）

不想配本地 Python 环境的话，一条命令起全套（Neo4j + 应用）：

```bash
echo "OPENAI_API_KEY=sk-你的key" > .env    # 密钥只放 .env，绝不进镜像（.dockerignore 已排除）
docker compose up -d --build               # Neo4j 健康检查通过后才启动应用
# 聊天页 http://localhost:8800 ，Neo4j 控制台 http://localhost:7474
docker compose down -v                     # 全部停掉并清理（连数据卷）
```

为什么坚持 Docker 化：①RAG 系统天然多服务（图数据库/向量库/应用各一个"集装箱"）；②`Dockerfile` 先拷依赖再拷代码，改代码重建不重装依赖（层缓存）；③容器互访用服务名（`bolt://neo4j:7687`），不用管 IP。Docker/镜像/容器/Dockerfile/Compose 概念速成见教程 [11.15 的 Docker 小节](../../15_端到端综合实战_KnowledgeForge_lite.md)。

## Web 界面：为什么选 Air 而不是 React？

完整版的 `frontend/` 是 React 19 + Ant Design + Three.js 的管理后台（含 3D 知识图谱可视化），约百余个 TS 文件——那是 Lite 砍掉的第一刀。但"完全没界面"又会让读者错过最能建立信心的一幕：**通过质量门禁后的答案分片出现、每个 `[n]` 角标可对应出处**。Lite 采用先验证再分片发送的安全流式，所以我们选了 [Air](https://github.com/feldroy/air)：

1. **Air 是 FastAPI 的子类**：`web/app.py` 把 `FastAPI()` 换成 `air.Air()`，接口一行不改，页面与 API 同进程，不需要第二个服务；
2. **页面结构就是 Python**：`web/pages.py` 用 Air 标签树写 HTML（`air.Div(...)` 即 `<div>`），读者不需要会 React；样式与交互放在 `static/console.css`、`static/workbench.js` 和 `static/console.js`，都带中文注释；
3. **零构建**：没有 npm/vite/打包器，浏览器直接吃静态文件；JS 只做三件事——拉会话柜、消费 SSE（`EventSource` 不支持 POST，所以用 `fetch + ReadableStream`）、点角标开证据抽屉；
4. **一个诚实的取舍**：Air 还没到 1.0，API 迭代快，所以 requirements 里锁了版本；追求 3D 图谱、权限管理台这类复杂交互时，该回到完整版的 React 形态。

> 一句话：**Air 负责"看得见的演示"，React 完整版负责"用得多的产品"**——和 11.10 选型地图里"买车/焊车"是同一个决策逻辑。

## 控制台：和完整版同一套界面语言

Lite 的前端不是另立门户，而是**完整版 KnowledgeForge 的课堂版**：同一个深藏青侧边栏、
同一顶白栏、同一块灰蓝画布、同一个主色 `#155eef`。
学生在 Lite 上学会的动作，搬到完整版上认得出位置。设计规则写在
[`DESIGN.md`](./DESIGN.md)——token 逐条对齐完整版 `frontend/src/main.tsx` 的 antd 主题
与 `frontend/src/index.css`。

### 身份有两层：账号 + 工牌

**账号**决定"你是谁"。`/login` 是登录/注册页（居中卡片，结构对着完整版 `pages/Login.tsx`）；
未登录访问控制台会被 303 过去。实现上和完整版同一条链，只是把 JWT 换成了**服务端会话表**：

| | 完整版 | Lite |
| :--- | :--- | :--- |
| 口令 | bcrypt | `pbkdf2_hmac` 加盐迭代 20 万轮（标准库，不引依赖），等时比较 |
| 会话 | JWT + 令牌黑名单 | 库里一行随机 token；**登出 = 删那一行**，立刻失效 |
| Cookie | `access_token` + `refresh_token` | 一个 `HttpOnly` + `SameSite=Lax` 的会话 cookie |

**库建出来是空的，谁用谁注册。** 不预置账号是刻意的：一个默认口令的账号，
哪怕只在文档里写着，也等于给系统留一把人人都知道的钥匙。注册时**从四张工牌里挑一张**
（公司管理员 / 财务负责人 / IT 员工 / 人事员工），想看"换个身份就换可见范围"就多注册一个。
不想注册就点「以访客身份看看」。

> 为什么表单是"挑身份"而不是分开选"角色 + 部门"：权限由 (角色, 部门) 这一对决定，
> 而工牌空间里只有四种组合。让用户自由拼 3×4 = 12 种，其中 8 种查不到、只能回落——
> 我们真踩过：选「公司管理员 + IT」（IT 还是部门下拉的默认值）回落到 IT 员工的工牌，
> 于是这个"管理员"进不去知识文档和评测治理。**与其在回落处打补丁，不如让表单拼不出
> 不存在的组合。**

**工牌**是**演示身份切换器**，只出现在 Lite 里（完整版没有这一块）。
课堂上老师要当场切四张牌做越权对照，这个开关就是为那个动作留的，
所以它待在**问答区顶部那条对照条**里，不占顶栏——顶栏只回答"你是谁"。

四张牌各写着「可见 N 篇 / 裁掉 M 篇」：**这就是"权限先于检索"的可视化**。
同一个语料库，公司管理员看得见 6 篇制度、IT 员工 5 篇（裁掉财务密级）、人事员工 4 篇
（裁掉财务密级和 IT 故障单）——被裁的文档根本不进候选池，不是搜出来再过滤。
投毒 HTML 走隔离，不进这张可见表；办公用品是人人可见的诱饵，漏登就会让工牌卡和目录页数出两个数字。
卡片上只给条数不给名字：**列出被裁文档的名字本身就是泄露**。

登录时初始选中项由账号的角色决定——**身份来自账号，不是页面上的开关**。
切工牌也会切权限：切到 IT 员工，知识文档和评测治理会一起锁上，这是同一条纪律的自然结果。

| 视图 | 装了什么 | 对应完整版 |
| :--- | :--- | :--- |
| **智能问答** | 左历史会话卡（与右栏**等高**）· 右对话卡：头像 + 气泡（用户靠右蓝底、助手靠左白底）· `[N]` 角标 · 状态标签 · 推理步骤与引用来源折叠 · 反馈 · 连体输入框 · 证据抽屉（目录 / 出处 / 轨迹） | `pages/QAChat.tsx` + `components/ChatHistory.tsx` |
| **知识文档** | 上传（拖拽或选择，逐篇入库）、统计卡、文档表（两行首列 / 状态标签 / 文字链操作）、隔离原因可展开、查看分块抽屉、**切块实验台** | `pages/DocList.tsx` + `components/DocumentTable.tsx` |
| **评测治理** | 说明条、统计卡、用例表（点行开详情抽屉）、Ragas 0.4 三指标、历史报告 | `pages/EvaluationGovernance.tsx` |

界面语言上，这几处和完整版是同一套语法：

- **两行首列**：主名 + 一行灰色副信息（登记号 / 工牌 / 来源），扫读时先看名字再看注脚；
- **状态用描边小标签**（`.tag`），不是实心色块，也不是圆角胶囊；
- **操作是蓝色文字链**（查看分块 / 删除 / 打开文档），不是一排按钮；
- **详情开抽屉**：分块、用例详情、评测报告都在右侧抽屉里，`Escape` 可关；
- **图标**是一套手写的 24 栅格描边 SVG，定义在 `web/pages.py` 一处，服务端和 JS 共用；
- **受控响应不渲染成散文**：证据不足 / 冲突 / 需人工时，气泡里给一条警示——
  这几种情况下"答案"本身就不该被当成答案读。

窄屏（≤991px，与完整版 `lg` 断点一致）侧边栏收成抽屉 + 遮罩；工牌横排可滑、不折行。

三条与完整版一致的纪律：

1. **知识文档与评测治理按角色开放**：接口返回 403 并说清"切到公司管理员工牌再试"，
   页面给出同样的提示和一个切换按钮——权限在服务端生效，前端只把话说明白；
2. **上传只嵌单篇**：`ingest(only=[文件名])` 只对上传的文件做嵌入，其余文档不重算
   （BM25 语料始终全量重建——切块是本地计算，嵌入才花钱）；
3. **删除走级联**：先删源文件，再让入库管道清掉向量与账本。"源文件是唯一事实来源"这条规矩，
   在删除路径上同样成立。

界面之外，问答这一段最该带走的是**会话的纪律**：

1. **服务端才是历史的权威来源**：会话写进 `runtime/conversations.sqlite`，刷新、换浏览器、重启进程都不丢；浏览器 `localStorage` 只记当前工牌和当前会话号；
2. **指针不是权限**：会话号指向的会话必须属于当前工牌，拿别人的 id 硬调接口按 404 处理——不是"拒绝访问"，是"不存在"；
3. **预览原文走同一把 ACL**：点角标打开的切块和检索一样先过 `authorize_chunks`；
4. **可复盘**：每次问答落一条 run（状态、路由、引用、各路名次、证据资格摘要）和一条审计事件，
   会话可一键导出成带引用与轨迹摘要的 Markdown。

### 登记号不是行号

文档表里那行灰色小字（`登记号 04`）是**入库那一刻烙上的号**，它和"第几行"是两件事：

| | 行号（`index + 1`） | 登记号（`accession`） |
| :--- | :--- | :--- |
| 删掉一篇 | 后面的全往前挪 | 别的号一个不动，留一个空号 |
| 重传一篇 | 位置随排序变 | 还是原来那个号 |
| 换个排序 | 全乱 | 全不变 |

空号不是 bug，是登记簿本来的样子（现实的档案号也不复用）。实现上索引里存 `accession`，
读路径用 `accessions_of` 按同一套规则算缺号——所以"还没 build 过"和"刚 build 完"
看到的号一致，不会闪。如果它只是个行号，就该被删掉：那是会随排序乱跳的装饰，
而结构装置有权存在的前提是它承载了信息。

### 切块实验台：把"切块"从只读变成可调的旋钮

文档区底部那块面板是 11.13 那个结论的实物：**CHUNK_SIZE 属于索引时旋钮**。
所以它不写库、不调模型，纯粹按你给的数字把一段文本切一遍给你看——

| 你能动的 | 你会看到的 |
| :--- | :--- |
| 正文（粘一段，或点表里某行的「查看分块」把正文带过来） | 块数 / 平均字数 / 最长块，五个读数一排 |
| 每块字数（50–2000） | 每块一张卡片，标题写块号与字数 |
| 重叠字数（0–400） | **块头重复的部分标黄**，并注明"头 N 字是上一块的重叠" |

最后一条是这块面板最值得看的地方：重叠不是个抽象参数，它是"同一句话被两块都装了进去"，
而检索时这句话就有两次机会被命中——代价是索引变大。把数字从 400 调到 120，
看着块数从 2 变成 5，这件事就不用再解释了。

旋钮只在这里生效；要真改索引的切块方式，得改 `.env` 里的 `FORGE_LITE_CHUNK_SIZE` 再重建索引。

### 解析与切块（11.2 / 11.4）：先读懂结构，再下刀

管道的前两段比"剥标签然后按字数切"多做几件事，每一件都对应一个真实会踩的坑：

| 环节 | 做了什么 | 不做会怎样 |
| :--- | :--- | :--- |
| **编码** | UTF-8 → GB18030 两档试 | 一份 GBK 老制度直接抛异常，整篇进不了库 |
| **表格**（docx） | 按**文档原顺序**遍历段落和表格，表格转成 `表格行: A \| B \| C` | 表格整块消失——正文读起来还通顺，只是"500 元"永远查不到 |
| **表格**（HTML） | 单元格之间换成 `\|`，和 docx 同一个形状 | 表格被压成一串没有列界的字 |
| **脚本** | `script/style/svg/head` 整块删掉 | 变量名会被 BM25 当关键词召回 |
| **控制字符** | 清洗第一步就删 | 隐含字符夹在词中间，同一句话的哈希对不上，重传一次就"内容变了" |
| **占位符** | 识别 `×××公司` / `待定` 并**标记**（不删） | 一份没填的模板混进索引，谁问都召回它，而它什么信息都没有 |
| **切块** | 按标题分节，每块带上「《文件名》 › 第 X 条」 | 块脱离了原文，"这块讲哪一条"就丢了 |
| **表格切块** | 表格行是**不可分割的最小单位**，超长表格只在行间切且每块补表头 | 一行被劈成两半，「500」和它的城市名分家 |

标题识别认两套写法：Markdown 的 `#`，和中文制度文件那套「第X章 / 第X条 / 一、 / （一）」——
真实文档大多不是 Markdown，Word 转出来就长这样。

### 一个只有跑评测才能发现的 bug：装箱与编排的顺序

这轮改切块之后，评测从 8/8 掉到 **6/8**。查下去发现两件事叠在一起：

1. 切块变结构化了，块的**数量变多、单块变短**，还各自带了上下文头 → 上下文总长度变大，
   1800 字的预算覆盖不到那么多了；
2. 而 `order_contexts`（对抗 lost-in-the-middle 的那步）**故意把第二名放到列表最末**，
   紧接着的装箱步骤却**按预算从尾部截断**——预算一紧，第一个被砍掉的正是那个被特意
   安排到结尾、最该给模型看的第二名。

两块单独看都对，凑在一起就成了"越重要的越先被丢"。修法是调换顺序：**先按相关度装箱
（决定谁进得来），再对装进来的做首尾编排（决定怎么摆）**。修完复跑 8/8。

`tests/test_retrieval_slice.py::PackThenOrderTests` 把这两种顺序摆在一起对比，
错序那条会明确地丢掉榜眼——回归测试记的就是这个。

### 文件名的攻击面

上传是唯一的写入口，所以 `documents.safe_filename` 在进文件系统之前先削平：
只取 basename（挡 `../../etc/passwd`）、去空字节、卡扩展名白名单、限长 80 字。
测试里专门有一条"穿越文件名落不进 docs 目录外"。

### 评测区分两层，和完整版一致

| 层 | 看什么 | 要不要裁判模型 |
| :--- | :--- | :--- |
| **门禁层** | 期望行为对不对（该答就答、该拒就拒）+ 期望文档有没有召回 | **不要**——所以快，每次改动都能跑 |
| **体检层** | Ragas 0.4 三指标（faithfulness / context_recall / answer_relevancy） | 要，且慢（每条 3 次裁判调用） |

拒答题在门禁层不看 Hit/Recall——它本来就该空手而归；硬套检索指标会把"两种病"混成一种。
报告落 `runtime/evaluations/eval-*.json`，评测区的历史列表点开就能回看。

> 🔍 **这套评测区抓到过什么**：第一次跑，`travel-cap` 用例（"去上海出差住一晚住宿费上限是多少？"）
> 被判**证据冲突**——同一篇《员工差旅管理制度》里一线 500、二线 350 是正常分档，却被当成两份资料打架。
> 修的时候又发现更深一层：`_on_topic` 拿「元」这种通用量词当住宿的**特征词**，
> 于是 FAQ 里的 999 元和办公用品制度的 200 元都被算成"住宿资料"。
> 现在主题归因只用名词性特征词，数值冲突只在**不同来源**之间判。
> 修完复跑：**8/8 全过**（修复前 7/8，挂掉的正是 `travel-cap`）。
> 这就是评测区存在的意义：闸门误杀的代价是"该答的题拒答"，肉眼看不出，跑一遍才知道。

## 工牌 ACL：和完整版同一条纪律

完整版用 JWT + 部门可见范围在打分前过滤。Lite 用四张写死的工牌演示同一件事——**先裁库，再检索，绝不先搜再丢**：

| 工牌 | 角色 | 能看见什么 |
| :--- | :--- | :--- |
| `it_staff`（默认） | IT 员工 | 公司公开文档 + IT 部门文档 |
| `hr_staff` | 人事员工 | 公司公开文档，看不见 IT 故障单和财务密级 |
| `finance_head` | 财务负责人 | 公司公开 + 财务部（含 `restricted` 薪酬带宽） |
| `admin` | 公司管理员 | 不过滤部门（`visible_department_ids is None`） |

试法：同一句「P6 薪酬带宽是多少？」换工牌，员工拒答、财务负责人才引用《财务薪酬密级》。这就是读完整版 `visible_department_ids` 时要认的课堂版。

> 🐛 **控制台上线后抓到的一个真 bug**：管理员刷新页面，头部明明写着「公司管理员」，
> 切到文档区却说「当前工牌：IT 员工」并锁着——两个管理区都进不去，除非换张牌再换回来。
>
> 原因是"工牌是谁"这件事被两个独立闭包各存了一份：`workbench.js` 会从 `localStorage`
> 读回上次用的牌，`console.js` 却自己写死 `it_staff`，而它只在**切换**工牌时才收到通知——
> 刷新时没人通知它。修法不是让控制台也去读一遍 `localStorage`（那样就有了两份真相），
> 而是让工作台在 `/whoami` 校验完、工牌真正定下来之后**广播一次最终身份**，
> 控制台收到就对齐。顺带把两个视图的请求加了序号：换牌会连发两次请求，
> 过期的那次结果要丢掉，否则旧牌的 403 可能盖掉新牌的数据。
>
> 同一个坑还有第二层：静态资源只有 `ETag` 没有 `Cache-Control`，浏览器按启发式缓存
> 直接拿旧 JS，于是**改完前端刷新页面看到的还是上一版**。现在 `/static/` 显式
> `Cache-Control: no-cache`——是"用之前先问一句"，不是"不许存"，命中 ETag 就是便宜的 304。

## 图谱：第三路召回，不再是事后加餐

- 入库时就把 `data/seed_triples.json` 垫进图存储，问答默认就能走向量 + BM25 + 图谱三路 RRF（图谱权重 1.05，与完整版 `hybrid_rerank` 同构）；
- 图谱命中必须映射回源文档切块（`文件名#切块号`），不另造「知识图谱」幽灵块——RRF 才能和另外两路用同一把身份钥匙；
- `05_build_graph.py`：可选地用 LLM 再抽一批三元组写入 Neo4j；没起 Neo4j 时自动读种子 JSON，不拖死主链路；
- **默认后端 Neo4j**（完整版同款）：写入用 `MERGE` 去重、查询走 Cypher，节点带属性可加索引。起一个容器即可：
  ```bash
  docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/forge12345 neo4j:5
  # .env / 环境变量：FORGE_LITE_NEO4J_URI=bolt://localhost:7687
  #                 FORGE_LITE_NEO4J_USER=neo4j  FORGE_LITE_NEO4J_PASSWORD=forge12345
  ```
  建图后打开 http://localhost:7474 可视化浏览；Cypher 抽查：`MATCH (a)-[r:RELATES]->(b) RETURN a,r,b LIMIT 25`；
- **兜底后端 NetworkX**：没起 Neo4j 时自动降级（落盘 `runtime/graph.json`）。它是内存对象序列化——没有 Cypher、没有索引、没有事务，只配课堂演示不配生产；
- 为什么坚持默认真图数据库：图谱数据的价值在"关系查询"（多跳、反向、按关系类型过滤），这些正是 Cypher 的主场；NetworkX 兜底只为"还没装 Docker 就先看看效果"。

## 这台机器的质量关卡（从外到内）

0. **入库扫描**（ingest.py）：投毒 HTML 隔离，不进检索索引；切块打上部门/密级（11.13）；
1. **工牌裁剪**（identity.py）：提问人可见范围在打分前决定，越权材料进不了候选池；
2. **查询改写**（rewrite.py）：原问题必须保留，本地拆主题，模型扩写失败就回退（11.6）；
3. **三路检索**（retrieve/search.py）：向量 + BM25 + 图谱，加权 RRF，最相关放首尾，按预算装箱（11.5 / 11.7）；
4. **证据资格**（evidence.py）：生成前先判「够不够答」——背景/冲突/不足直接拦截（11.8 / 11.12）；
5. **相关性分级**（agent.py `n_grade`）：资格不够直接拒答；资格已经放行时不再让模型一票否决（11.8 CRAG 的模型分级只当兜底）；
6. **接地生成 + 引用标注**（citation.py）：编号协议，每个关键句带 `[n]` 出处（11.12）；
7. **程序校验**（agent.py `n_check`）：幽灵引用直接打回；`RunBudget` 只许重试 1 次（11.8 / 11.12）；
8. **忠实度复检**（agent.py `n_verify`）：裁判 LLM 返回前逐句验真，仍不过就拒答，绝不带病交付。

## 评测按 Ragas 0.4 官方入口，只留三个指标

[Ragas](https://docs.ragas.io/en/stable/) 现在的主线是 0.4.x，写法与 0.2 不同：新代码用 `ragas.metrics.collections` 里的类 + `llm_factory` / `embedding_factory` 组装，再 `ascore(...)`；旧的 `from ragas.metrics import faithfulness` 单例已被标记弃用。Lite 按官方入口重写，样本字段用 `user_input / retrieved_contexts / response / reference`：

- **Faithfulness**：答案每个陈述能否在资料里找到依据（生成有没有编）；
- **ContextRecall**：标准答案里的要点，检索有没有召回来（检索漏没漏）；
- **AnswerRelevancy**：答案是不是在回答这个问题（答非所问）。

为什么只留三个：课堂要的是**定位**而不是打分表。faithfulness 低先修生成，context_recall 低先修检索，answer_relevancy 低说明答非所问——三条各自指向一层，正好覆盖 11.9 的三元组定位法。评测默认 `persist=False`，黄金题不往会话柜写。

评测分两层，别绑在一个脚本上：

| 层 | 入口 | 看什么 | 要不要裁判 |
| :--- | :--- | :--- | :--- |
| **门禁层** | `scripts/03_evaluate.py` | 该答的答了没有、该拒的拒了没有、期望文档召回了没有 | 不要——改完代码先跑这个 |
| **体检层** | `scripts/04_ragas_eval.py` | Faithfulness / ContextRecall / AnswerRelevancy | 要裁判。课堂默认关掉 MiMo 隐性思考（`FORGE_LITE_THINKING_MODE=disabled`），否则一条用例可能要几分钟 |

`AnswerRelevancy` 官方默认 `strictness=3`（连问三次「这个问题还能怎么问」）。课堂默认 `FORGE_LITE_JUDGE_RELEVANCY_STRICTNESS=1`，要更稳的分数再调回 3。作答路径 0.66–0.85 是这一档的预期。拒答题的低分是裁判在给拒答话术打分（越权题的 context_recall 还经常是 0，因为 ACL 没让文档进上下文），先看门禁层行为，别把八条分数直接平均。

### 跑起来的三件非默认配置

用法与官方文档逐字一致，但下面这几样都不是默认值，缺哪件都跑不起来（都实测踩过）：

| 配置 | 不做会怎样 | 怎么做 |
| :--- | :--- | :--- |
| VertexAI 垫片 | ragas 0.4.3 的 `ragas/llms/base.py` 顶层 import 了 `langchain_community.chat_models.vertexai`，而该类在 langchain-community 0.4 已被移除 → `import ragas` 直接 ImportError（ragas 声明依赖时不带上界，pip 拦不住） | `evaluate.py` 的 `_patch_vertexai()` 补个占位类。ragas 只在"把 langchain 模型对象包成 ragas LLM"的分支里用它，我们走 `llm_factory`，用不到真货 |
| 裁判分两个客户端 | 拿 `CHAT_MODEL`（MiMo）去请求 `OPENAI_API_BASE`（方舟）→ 404 `UnsupportedModel`，而报错只说模型不支持，不说是端点配错了 | `_judge_clients()`：对话裁判认 `CHAT_*`，嵌入裁判认 `OPENAI_*`——正是 `config.resolve_chat_endpoint` 要拦的那条纪律（见 11.13） |
| `max_tokens` 要给足 | `llm_factory` 默认 1024，裁判的结构化输出被截断 → `IncompleteOutputException` | `config.JUDGE_MAX_TOKENS`（默认 8192）。关思考之后额度主要给 JSON；真要开思考再加大 |
| 关掉隐性思考 | MiMo `mimo-v2.5-pro` 默认开思考，`reasoning_tokens` 计入 completion。开着时单条 Ragas 可能要几分钟，八条黄金集要几十分钟 | 课堂默认 `FORGE_LITE_THINKING_MODE=disabled`（也认完整版的 `LLM_THINKING_MODE`）。问答客户端和 Ragas `llm_factory` 都传 `extra_body={"thinking":{"type":"disabled"}}`。要看推理链再改成 `default` |

一句话：`import ragas` 能用之后，裁判跑在**你自己 `.env` 里那一套端点**上——这正是 11.9 强调的"阅卷老师得是你自己请来的"。

## 目录约定

- `data/docs/`：种子知识库（差旅 / FAQ / 故障 / 安全 / 财务密级 / 办公用品 + 1 篇投毒 HTML），可增删 `.md` / `.txt` / `.html` / `.docx` / 文字层 `.pdf`；
- `tests/`：**450 个离线用例**，不需要 API Key——RRF 加权、工牌 ACL 矩阵、证据资格、图谱映射回切块、改写护栏、投毒扫描、会话柜隔离与游标分页、SSE 帧顺序、轨迹与导出、评测契约、工作台资产；
- `runtime/`：一切运行产物（Chroma 持久库、BM25 语料、内容哈希账本、会话柜 sqlite、审计 jsonl、精确缓存），已 gitignore——**运行产物不入库**；
- 改完任何模块，先跑 `python -m unittest discover -s tests -v`，再跑 `03_evaluate.py`（门禁层）。通过率下降就说明改坏了；Ragas 留给上线前或评测区第二个按钮；
- 排障顺序：`07_status.py` 看索引 schema 有没有漂移、图谱在不在、柜子里有什么——先体检，再怀疑模型；
- 改界面前先读 `PRODUCT.md`（产品事实）与 `DESIGN.md`（视觉规则）：它们是这份 UI 的说明书，
  改完跑一次 `impeccable detect` 看有没有踩到设计雷区。
