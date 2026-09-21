# 11.8 答非所问与幻觉怎么自愈？—— Agentic RAG

> **痛点场景**：单向 RAG 流水线有三大硬伤——
> ① **假召回**：检索回 3 篇文档但通篇跑题，系统也硬着头皮编答案；
> ② **知识缺失**：库里根本没收录，系统只能回一句冷冰冰的“不知道”；
> ③ **幻觉**：生成完后没人核对，答案里“赔偿 1000 元”而原文明明是“100 元”。
> **Agentic RAG 就是给这条流水线装上“分诊台 + 化验室 + 药师”**：标本溶血了退回重抽（重检索）、本院查不到就按规定转外院（联网兜底）、发药前药师再核一次剂量（幻觉检测）。

---

## 思路：三种“会思考”的 RAG 范式

<!-- 图表源文件：img/diagrams/08-diagram-01.mmd；视觉风格：Linear 紫色科技感 -->
<p align="center">
  <a href="img/diagrams/08-diagram-01.svg">
    <img src="img/diagrams/08-diagram-01.svg" alt="💡 思路：三种“会思考”的 RAG 范式" width="760">
  </a>
</p>

| 范式 | 一句话 | 核心机制 |
| :--- | :--- | :--- |
| **Self-RAG** | 生成过程中自我反思 | 反思 Token：`[Retrieve]`（要不要查）、`[ISREL]`（相关吗）、`[ISSUP]`（有依据吗） |
| **CRAG** | 检索后先“分级再决策” | 裁判给文档打分：Correct→提炼去噪、Incorrect→联网兜底、Ambiguous→多源融合 |
| **Adaptive RAG** | 先判断难度再选路线 | 简单→直接答（省钱）、中等→单次检索、困难→多轮/多工具 |

> 📄 对应论文：[Self-RAG (Asai et al., 2023)](https://arxiv.org/abs/2310.11511)、[CRAG (Yan et al., 2024)](https://arxiv.org/abs/2401.15884)。

> ⚠️ **先划清边界**：Self-RAG 原论文训练模型学习反思 Token；CRAG 原论文也有特定的检索评估与知识精炼方法。下面的 LangGraph 代码是**借鉴这些决策思想的工程工作流**，不是对论文训练过程的等价复现。把几个 LLM 裁判节点串起来，不能直接宣称“实现了 Self-RAG”。

---

## 代码实现：基于 LangGraph 的「检索 + 分级 + 幻觉自检」闭环

> 三种范式里，本节动手做的是 **CRAG 那一刀：检索完先分级，再决定生成、兜底还是闭嘴**。Self-RAG 的反思 Token、Adaptive RAG 的“先判断难不难”，思想都对，但教学脚本没有单独做一个“难度路由器”——简单题省一次检索，靠的是预算和拒答，不是再套一层分类模型。

完整脚本见 [`code/s08_agentic_rag.py`](./code/s08_agentic_rag.py)，检索的是 `testdata/` 里的真实制度页。这里只把**最容易装反的两段路**拎出来：分级之后往哪走，复检失败之后往哪走。

把一次问答想成医院开处方：抽血化验（检索）→ 化验单质检（分级）→ 医生开方（生成）→ 药师审方（复检）。化验单写着“标本溶血”，你不会按这份单子开药；药师说“剂量对不上病历原文”，你最多让医生改一次处方，不会让他改到天亮。代码里的条件边就是这两条院规。

```python
from typing import List, TypedDict

from langgraph.graph import END, START, StateGraph
from rag_quality import RunBudget

class GraphState(TypedDict):
    question: str
    documents: List[str]
    generation: str
    needs_web_search: bool
    status: str            # ok / regen / refuse；缺这个键，LangGraph 不会替你填默认值
    budget: RunBudget

def decide_after_verification(faithful: bool, answered: bool, budget: RunBudget) -> str:
    """药师复核通过就发药；没过只许改一次处方，再不行就停方转专科。"""
    if faithful and answered:
        return "deliver"
    if budget.consume("rewrite"):
        return "retry"
    return "refuse"

def after_grade(state: GraphState) -> str:
    if state.get("status") == "refuse":
        return "end"          # 预算没了或库里没有，别再走进生成
    return "web_search" if state.get("needs_web_search") else "generate"

def after_verify(state: GraphState) -> str:
    return "generate" if state.get("status") == "regen" else "end"

workflow = StateGraph(GraphState)
# retrieve → grade_documents → (web_search | generate | end)
# generate → check_hallucination → (generate | end)
workflow.add_conditional_edges(
    "grade_documents", after_grade,
    {"web_search": "web_search", "generate": "generate", "end": END},
)
workflow.add_conditional_edges(
    "check_hallucination", after_verify,
    {"generate": "generate", "end": END},
)
```

跑两个场景就够体会闭环：

| 用户怎么问 | 诊室里实际发生什么 |
| :--- | :--- |
| “RX-9000 报 ERR-404-X9 怎么办？” | 制度库里有故障页，分级会放行，生成后再复检是否胡编步骤 |
| “公司年终奖发几个月？” | 库里没有。教学版不会真去搜公网编一个数，只会附一条“外部占位、不可当内部制度”的纸条；预算用尽就拒答、转人工 |

教学版的 `web_search` **不发起真实联网**。外院能查到公开的临床指南，查不到你们公司年终奖标准——私有问题靠公网补，补来的多半是幻觉。

**这段代码比“玩具版”强在哪？**
1. **真实检索**，命中哪一页能用页 ID 对上 testdata，不是内存里两句假文档；
2. **分级是独立节点**：相关就生成，全跑题才走兜底，库里没有就停；
3. **复检有刹车**：`RunBudget` 把“最多再写一次”写成可测试的数字，而不是注释里的“注意别死循环”；
4. **拒答是一等公民**：复检失败、预算耗尽，答案必须换成转人工，不能把半成品端上桌。

总装项目 Lite 还多了一刀确定性资格（`EvidenceQualifier`）：资料已经够答时，**不再让分级模型一票否决**。课堂黄金集里「打印机 E3」曾经同一题两次跑、一次过一次挂，就是模型分级把已经放行的证据又否了。CRAG 的模型分级只在资格没结论时当兜底。完整闭环见 [`code/KnowledgeForge_lite/forge_lite/answer/agent.py`](code/KnowledgeForge_lite/forge_lite/answer/agent.py)。

---

## 拓展：工程化时要注意什么？

| 关注点 | 建议 |
| :--- | :--- |
| **成本与延迟** | 每次多轮重试都烧 token，务必设置最大重试次数（如 2 次）并记录耗时 |
| **安全边界** | 联网兜底只应把“检索结果”拼入上下文，不要让 LLM 自由执行代码/访问内网 |
| **可观测** | 每个节点的判定结果要落日志，方便 11.9 做 Badcase 归因 |
| **阈值校准** | “相关/忠实/已作答”的判定标准要先在离线评测集上校准，再上线 |

## 自省模型也会一本正经地判断错

让 LLM 检查 LLM，好比让同一个学生既答题又批卷：确实能抓住一部分错误，但也可能偏爱自己的表达、漏掉隐蔽矛盾，或把“没证据”误判成“有证据”。尤其当生成模型、相关性裁判和忠实度裁判来自同一模型家族时，错误可能一起发生。

因此裁判输出不能只有 `yes/no`：

| 应记录的字段 | 用途 |
| :--- | :--- |
| 判定、置信度、理由 | 低置信度时转人工或走保守路线 |
| 被判相关的证据片段 | 检查裁判是否真的看到了依据 |
| 裁判模型与 Prompt 版本 | 模型升级后可回放比较 |
| 节点耗时、Token 和费用 | 判断这次自省是否值得 |
| 最终动作 | 交付、重检索、改写、拒答或转人工 |

裁判上线前要与人工标注集比较，并单独覆盖数字、否定、时间冲突、无答案和提示注入样本。

## 每个循环都必须有“刹车”和预算

一个健壮的闭环至少设定：最大检索次数、最大改写次数、最大验证次数、总 Token、总费用和墙钟时间。任意上限触发后，系统进入明确终态：交付已有可靠部分、拒答，或转人工。不能用“再试一次”掩盖没有退出条件的死循环。

```text
相关证据充足 + 验证通过  → 交付
证据不足 + 仍有检索预算  → 改写或换数据源
答案不忠实 + 仍有重写预算 → 重新生成
预算耗尽 / 裁判低置信      → 拒答或转人工
```

配套 `RunBudget` 把这条纪律写成了可测试代码。脚本演示里 `max_rewrites=1`：第一次复检不过，允许再生成一轮；第二轮还不过，直接拒答。你可以把它想成门诊的“免费复诊一次”——剂量对不上可以改一次方，不会让医生通宵试药。

## 联网兜底不是默认答案

私有库查不到“公司年终奖标准”，去公网搜索也不可能得到公司内部政策。只有公开、时效性问题且业务允许时才联网，并且必须：

1. 使用允许的数据源和域名；
2. 保留网页 URL、抓取时间与可信级别；
3. 把网页视为不可信数据，继续执行注入扫描与引用校验；
4. 绝不把私有问题、租户资料或访问令牌泄露给搜索服务；
5. 公网结果与内部制度冲突时，按来源等级处理并明确提示。

## 什么时候简单 RAG 更好？

事实明确、知识库小、低延迟要求高的场景，固定“检索→重排→接地生成→引用”通常更便宜、更容易测试。只有评测证明错误主要来自动态决策、多跳检索或证据不足时，才增加 Agentic 节点。衡量收益时必须把正确率提升与 P95 延迟、模型调用次数和拒答率放在一张表里。

---

<!-- CH10-14_EXPANSION -->

## 自省节点也要接受外部检查

模型评价“证据充分”只是一项判断，不能当作事实证明。可以让程序检查引用是否存在、检索分数是否达标，再用独立样本评估自省模型的误判率。高风险答案仍需要人工复核。

循环必须设置次数、时间和费用上限，并记录每次为何重新检索。连续两次查询和候选结果没有明显变化时，应停止或转人工，避免用更多调用重复同一种错误。

---

## 进阶：长期记忆式 RAG —— 把“记忆”也当成一个知识库

> 💡 **比喻**：本节前面的自省闭环，像一位尽职但“没记性”的办事员——每次你来办事，他都要重新翻一遍档案柜；而记忆式 RAG 像一位老同事，记得你上次聊到哪、习惯看表格还是看条款，开口就能接上。

### 做法：给系统开一本“独立小账本”

把跨会话的稳定信息——用户偏好（“喜欢看我给表格”）、已确认结论（“已经排除了 MySQL 方案”）、任务进展（“报告写到第三章”）——写进一个**独立的记忆库**。问答时，记忆库与知识库**一起召回**，拼进同一个上下文。记忆库用向量库也能跑，但如果记忆之间有明显的时间与因果关系（“先确认了 A，才决定做 B”），用图数据库存更合适：因为你要查的往往是“这条记忆是从哪条推出来的”。

| 维度 | 知识库 | 记忆库 |
| :--- | :--- | :--- |
| **内容** | 客观资料、文档、制度 | 用户偏好、已确认结论、任务进展 |
| **更新频率** | 低（按版本批量更新） | 高（每轮对话都可能写入） |
| **召回方式** | 语义 / 关键词检索 | 按用户 + 时效检索，常配时间衰减 |
| **失效策略** | 版本替换、过期标记 | 时间戳 + 来源，可单条撤销或删除 |

### 三条工程红线

1. **写入门槛**——只写稳定的偏好与结论，不要把每轮噪声都当记忆写进去。否则记忆库很快变成垃圾场，召回来的全是“用户说了句你好”这类废话；
2. **时间与来源**——每条记忆必须带时间戳与出处，过期要能失效（呼应 11.7 的图谱保鲜、11.12 的引用溯源）；
3. **删除权**——用户要求删除时**必须能真删**，不是标记一下还留着（隐私合规，呼应 11.13 的数据治理）。

> 📄 参考实现：[MemoRAG（记忆增强检索）思路的 notebook 演示](https://github.com/NirDiamant/RAG_Techniques/blob/main/all_rag_techniques/memorag.ipynb)、[mem0](https://github.com/mem0ai/mem0)、[Graphiti（时序知识图谱记忆）](https://github.com/getzep/graphiti)、[Agent Memory Techniques](https://github.com/NirDiamant/Agent_Memory_Techniques)。

> 🧩 **配套脚本**：`code/s08_agentic_rag.py` 的 `MemoryStore` 实现了写入门槛 / TTL / 真删除。

---

## 拓展：Deep Research —— Agentic RAG 的“超集”

一句话定位：**把本节的自省闭环，从“答一个问题”放大到“产出一份带引用的研究报告”**。

| 角色 | 干什么 | 对应本节的哪个环节 |
| :--- | :--- | :--- |
| **规划者** | 把大问题拆成若干可检索的子问题 | 先判断值不值得兴师动众（教学脚本用预算卡住轮数，不另做分类器） |
| **搜索者** | 多轮外部检索，每轮根据上一轮结论换关键词 | 检索 → 分级 |
| **写作者** | 阶段性成文，并显式标注“哪一段还没有证据” | 生成 |
| **审校者** | 回头补检没答上的部分，决定是否再来一轮 | 幻觉复检 + 有限重试 |

和本节的关系：内核是**同一套“检索—评估—再检索”思想**，差别只在三处——循环次数更多（从一两轮变成几轮到几十轮）、检索源从本地库扩到全网、输出从一段短答变成一篇长文。

代价与红线：

- **Token 与延迟是普通问答的几十倍**，所以**必须设总预算与最大轮数**（呼应上文“每个循环都必须有‘刹车’和预算”），否则一次研究就能烧掉一整天的额度；
- 外部网页是**不可信输入**，同样要过 11.13 的注入防护与引用校验，不能因为它“看着权威”就直接当事实。

> 💡 **极简流程**（伪代码，只讲骨架）：

```text
budget = {"max_rounds": 5, "max_tokens": ..., "max_seconds": ...}  # 先上刹车
outline = plan(question)             # 规划者：拆子问题
notes, todo = {}, outline            # 每个子问题 → 已找到的证据

while todo and 预算未耗尽:
    q = 挑一个未答子问题
    docs = search(q)                 # 搜索者：外部多轮检索
    if 证据不足:
        重写查询并把 q 标为“缺口”; continue   # 不硬编，缺就承认缺
    notes[q] = docs
    draft = write(outline, notes)    # 写作者：阶段性成文
    todo = review(draft, outline)    # 审校者：指出还缺哪一段

输出 draft（每个结论后带引用来源；缺口处明确标注“未找到依据”）
```

> 📄 参考实现：[assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher)、[langchain-ai/open_deep_research](https://github.com/langchain-ai/open_deep_research)。

---

## 权威官方参考

- [Self-RAG 论文（Asai et al., 2023, arXiv:2310.11511）](https://arxiv.org/abs/2310.11511)
- [CRAG 论文（Yan et al., 2024, arXiv:2401.15884）](https://arxiv.org/abs/2401.15884)
- [LangChain Adaptive RAG 官方教程](https://github.com/langchain-ai/langgraph/blob/main/examples/rag/langgraph_adaptive_rag.ipynb)
- [LangGraph CRAG 官方实战](https://github.com/langchain-ai/langgraph/blob/main/examples/rag/langgraph_crag.ipynb)
- [MemoRAG（记忆增强检索）notebook（NirDiamant/RAG_Techniques）](https://github.com/NirDiamant/RAG_Techniques/blob/main/all_rag_techniques/memorag.ipynb)
- [mem0 官方仓库（mem0ai/mem0）](https://github.com/mem0ai/mem0)
- [Graphiti 时序知识图谱记忆仓库（getzep/graphiti）](https://github.com/getzep/graphiti)
- [Agent Memory Techniques（NirDiamant/Agent_Memory_Techniques）](https://github.com/NirDiamant/Agent_Memory_Techniques)
- [GPT Researcher 官方仓库（assafelovic/gpt-researcher）](https://github.com/assafelovic/gpt-researcher)
- [Open Deep Research 官方仓库（langchain-ai/open_deep_research）](https://github.com/langchain-ai/open_deep_research)
