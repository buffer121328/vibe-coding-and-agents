# 🏁 9.13 综合实战：AI 智能数码选购与避坑决策 Agent（全链路融会贯通）

> **“学了十二节零件课，今天整机下线——真正的工程能力，不是认得每个零件，而是把它们装配成一台能跑、能扛、能卖的机器。”**  
> 本节是第九章的收官之战：我们把 9.1~9.12 装进工具箱的全部零件——统一模型 I/O、LCEL 管道、结构化输出、自定义工具、记忆管理、Callbacks 审计、RAG 检索、`create_agent` 架构、上下文工程、自定义中间件、生产级护栏——**一次性总装**成一个完整的生产级项目：**SmartBuyer（AI 智能数码选购与避坑决策参谋）**。

---

## 💡 概念大白话：装机佬的整机组装

### 1. 为什么最后一定要有综合实战？

学会零件 ≠ 会装机。前面十二节里，每一节都单独点亮了一块技能：可你会不会有种感觉——“每块都懂，但拼在一起就手忙脚乱”？这太正常了：**单点知识是零件，工程能力是总装**。真实企业项目从来不是“只用一个中间件”，而是**十几个零件协同运转**：护栏挡在门口、中间件盯着流水线、上下文工程递剧本、记忆管着抽屉、Callbacks 记着账——任何一环掉链子，整机就是废铁。

### 2. 生活比喻：攒一台旗舰整机

把 SmartBuyer 想成一位装机佬攒出来的旗舰主机，每个硬件都对应前面学过的一节：

| 电脑硬件 | 对应章节 | 在 SmartBuyer 里是什么 |
| :--- | :--- | :--- |
| 🧠 CPU（大脑） | 9.1 统一模型 I/O | `get_chat_model_primary()` 一行换模型，业务代码零改动 |
| 🔌 主板（总装骨架） | 9.9 `create_agent` | 所有零件插在它上面，1.x 标准架构 |
| ⚙️ 散热与供电（稳压器） | 9.11 自定义中间件 | 日志、调用限流、自动重试三件套 |
| 🛡️ 机箱侧板（防尘防静电） | 9.12 生产级护栏 | 黑名单拦截 + PII 脱敏，纵深防御 |
| 🗂️ 内存与硬盘（记忆） | 9.6 记忆管理 | Checkpointer 线程记忆 + Store 长期顾客画像 |
| 💽 固态硬盘里的资料库 | 9.8 RAG | 内置数码避坑宝典（Chroma 向量知识库） |
| 🖱️ 外设（手脚） | 9.5 自定义工具 | 差评搜索 / 性价比测算 / 避坑检索三大 `@tool` |
| 📺 机箱灯效与仪表 | 9.7 Callbacks | Token 成本审计回调，黑匣子账单 |
| 🎛️ 开机前的 BIOS 设置 | 9.10 上下文工程 | `@dynamic_prompt` 按人、按场景动态定稿"剧本" |
| 📋 出厂质检报告 | 9.4 结构化输出 | Pydantic《选购决策与避坑报告》 |
| 🔗 机箱内部排线 | 9.3 LCEL | `prompt \| structured_llm` 管道符编排 |

<!-- 图表源文件：img/diagrams/13-diagram-01.mmd；视觉风格：Notion 简洁 -->
<p align="center">
  <a href="img/diagrams/13-diagram-01.svg">
    <img src="img/diagrams/13-diagram-01.svg" alt="SmartBuyer 全链路架构：护栏层 → 上下文工程层 → 智能体中枢 → 工具生态 → 双模输出" width="760">
  </a>
</p>

---

## 🧩 融会贯通全景图：12 节知识点的落点对照

先看总装清单——**每一节学的东西，在整机里都有明确的位置**，一个都不浪费：

| 章节 | 零件名称 | 在 SmartBuyer 中的落点 |
| :--- | :--- | :--- |
| 9.1 统一模型 I/O | 万能转换插头 | `get_chat_model_primary()` 工厂接入，换模型不改业务 |
| 9.3 LCEL 管道 | 自动化传送带 | `prompt \| structured_llm` 一根管道生成报表 |
| 9.4 结构化输出 | 海关标准报关单 | `ShoppingDecisionReport` 强类型选购决策矩阵 |
| 9.5 自定义工具 | 瑞士军刀卡槽 | 3 个 `@tool`：差评搜索、性价比测算、避坑宝典 |
| 9.6 记忆管理 | 抽屉 + 剪报员 | Checkpointer（thread_id 短期）+ Store（跨会话画像） |
| 9.7 Callbacks | 航班黑匣子 | `PerformanceAndCostCallback` Token 成本自动审计 |
| 9.8 RAG 检索 | 智能图书索引员 | `langchain-chroma` 内置避坑知识库，零配置开箱即用 |
| 9.9 create_agent | 高级私人秘书 | 整机总装骨架，Tool Calling 自主推理 |
| 9.10 上下文工程 | 导演的剧本调度 | `@dynamic_prompt` 三数据源动态注入系统提示 |
| 9.11 自定义中间件 | 流水线质检员 | 日志 + 调用限流 + 自动重试，三钩子协同 |
| 9.12 生产级护栏 | 安检门与安检员 | 黑名单 `before_agent` 拦截 + PII 输入脱敏 |

> 🔑 **一句话读懂整机**：用户诉求先过**护栏安检**（9.12）→ 中间件**记录与限流**（9.11）→ 动态提示词**按画像定稿剧本**（9.10）→ `create_agent` 中枢**自主推理调用工具**（9.9 + 9.5 + 9.8）→ 输出**结构化决策报告**（9.4），全程 **Callbacks 记账、Checkpointer 记忆**（9.7 + 9.6）。

---

## 💻 核心实操：整机总装四步曲

完整可运行脚本见 [`code/s13_smart_buyer.py`](code/s13_smart_buyer.py)，全部零件均可单独溯源到对应章节。

### 第 1 步：备料——模型、工具与知识库（9.1 + 9.5 + 9.8）

```python
# code/s13_smart_buyer.py —— 备料三件套
from s01_model_io import get_chat_model_primary          # 【9.1】统一模型工厂
from s07_callbacks_and_tracing import PerformanceAndCostCallback  # 【9.7】Token 审计

@tool
def search_product_reviews_and_complaints(query_keyword: str) -> str:
    """全网实时搜索指定数码产品的真实用户评测、真实差评与翻车吐槽。"""   # 【9.5】Docstring = 工具说明书
    ...  # ddgs 联网搜索，失败时优雅降级为模拟数据

@tool
def calculate_specs_and_budget(formula: str) -> str:
    """精确计算价格优惠幅度、每元性能比与预算剩余额度（严禁心算）。"""
    ...

@tool
def query_hardware_traps(category_or_term: str) -> str:
    """查询内置数码硬件避坑宝典，识别偷工减料与营销话术陷阱。"""
    ...  # 【9.8】GLOBAL_BUYER_KB.as_retriever() Chroma 向量检索
```

### 第 2 步：装"大脑与剧本"——动态上下文工程（9.10）

这是本次总装的**灵魂升级**：老版实战写死 System Prompt，新版让系统提示**活起来**——每次模型调用前，从三数据源现场拼装：

```python
# code/s13_smart_buyer.py —— @dynamic_prompt 三数据源动态注入
@dynamic_prompt
def smart_buyer_dynamic_prompt(request: ModelRequest) -> str:
    # 1) Runtime Context：本次请求的固定配置（不传时优雅降级为游客画像）
    ctx = request.runtime.context
    user_id = getattr(ctx, "user_id", None) if ctx else None
    system = SMART_BUYER_BASE_PROMPT              # 基础人设：使命 + 三大工具 + 工作原则

    # 2) Store 长期画像：这位顾客"是谁"，决定参谋怎么说话
    if user_id and request.runtime.store is not None:
        prefs = request.runtime.store.get(("buyers",), user_id)
        if prefs:
            system += f"\n\n【顾客画像】沟通风格：{prefs.value['communication_style']}..."

    # 3) State 短期感知：聊了很久就自动"长话短说"
    if len(request.messages) > 10:
        system += "\n\n【会话提示】这是一段较长的咨询，请尽量简洁直接地给出结论。"
    return system
```

> 💡 **融会贯通点**：Store 里预置了两位顾客画像——`user-veteran`（极简直接）与 `user-rookie`（手把手科普）。同一个问题，参谋对老手甩参数表、对新手讲避坑故事——**这就是"同一个模型，千人千面"的上下文工程**。

### 第 3 步：插上"神经、韧带与安检门"——中间件与护栏（9.11 + 9.12）

```python
# code/s13_smart_buyer.py —— 整机总装：create_agent + 三层中间件纵深栈
self.agent = create_agent(
    model=self.llm,                                       # 【9.1】CPU
    tools=self.tools,                                     # 【9.5】外设
    middleware=[
        # 第 1 层【9.12】护栏：黑名单命中直接收尾，连模型都不调
        ContentFilterMiddleware(banned_keywords=["hack", "exploit", "malware", "刷单"]),
        # 第 2 层【9.11】治理：日志 / 调用超 10 次熔断 / 失败自动重试 3 次
        LoggingMiddleware(),
        CallCounterMiddleware(),
        retry_model,
        # 第 3 层【9.10】上下文工程：动态系统提示（放在最内层，最后定稿"剧本"）
        smart_buyer_dynamic_prompt,
    ],
    checkpointer=self.checkpointer,   # 【9.6】thread_id 自动隔离多轮会话记忆
    store=self.store,                 # 【9.6】跨会话长期顾客画像
    context_schema=BuyerContext,      # 【9.10】声明运行期上下文 Schema
)
```

> 🔑 **装配顺序有讲究**：中间件列表**由外到内**执行——护栏放最外层（把坏请求挡在一切开销之前），动态提示词放最内层（等日志、限流、重试都就绪后，最后定稿递给模型的剧本）。这个"**安检门在外、导演在内**"的排布，正是 9.12 纵深防御 + 9.10 上下文工程的组合拳。

### 第 4 步：点火试车——多轮问诊与结构化报表（9.6 + 9.7 + 9.3 + 9.4）

```python
# code/s13_smart_buyer.py —— 双模输出：交互问诊 + 一键报表
def chat_recommend(self, user_query, session_id="default_shopper", user_id=None):
    callback = PerformanceAndCostCallback()                      # 【9.7】黑匣子账单
    invoke_kwargs = {"config": {"configurable": {"thread_id": session_id},   # 【9.6】会话记忆
                                "callbacks": [callback]}}
    if user_id:
        invoke_kwargs["context"] = BuyerContext(user_id=user_id) # 【9.10】运行期上下文
    response = self.agent.invoke({"messages": [("user", user_query)]}, **invoke_kwargs)
    ...  # 从 messages 流水线还原工具调用链（9.9 的审计姿势）

def generate_structured_report(self, user_demand):
    structured_llm = self.llm.with_structured_output(ShoppingDecisionReport)  # 【9.4】报关单
    chain = prompt | structured_llm                              # 【9.3】LCEL 管道
    return chain.invoke({"demand": user_demand})
```

---

## 🧪 出厂质检：整机的确定性自测

整机不是装完就走，出厂前要过质检（呼应 9.12 的测试纪律）：

1. **护栏断言（零 API 依赖，可进 CI）**：复用 9.12 的 `content_filter_check` / `pii_redact` 纯函数断言——黑名单命中即收尾、邮箱自动脱敏；
2. **端到端冒烟测试**：`uv run python s13_smart_buyer.py` 跑一次完整问诊 + 报表生成，核对 Token 账单与工具调用链是否完整；
3. **回归基线**：把"预算 5000 买轻薄本"等固定用例做成评估集，每次改 Prompt 都跑一遍回归；云端 Trace 与评估平台（LangSmith / Langfuse）暂不接入，如有需求后续单独成节介绍。

---

## 🖥️ 运行方式

```bash
cd 09_LangChain搭建Agent/code
uv sync                                          # 首次安装依赖
uv run python s13_smart_buyer.py                 # 终端体验：整机点火试车
uv run python app.py                             # 或打开 Gradio 工作台 → 侧边栏切到「🌟 9.13 SmartBuyer 实战」
```

Gradio 工作台的 9.13 页面是与其他 12 关完全不同的**专属「整机点验台」版式**（琥珀金暖色系，装机文化隐喻贯穿全页）：

- **点火 Hero · 数据屏**：横幅内嵌五格数据屏（12 零件总装 / 3 专业工具 / 2 记忆层级 / 3 纵深防御 / 100% 真实调用）+ 装配管线芯片；
- **三栏主舞台**：左栏三张「顾客身份卡」（老司机 / 新手小白 / 游客新客，点「以此身份咨询」即切换 Store 画像并联动刷新画像面板、装填同一对比问题）；中栏「侧透机箱」——Mac 窗式机箱头（红绿灯 + AGENT ONLINE 指示灯）包裹 Codex 式气泡会话；右栏「机箱侧透 · 装配流水线」——琥珀暗底终端实时滚动工具调用与画像注入明细 + Token 账单；
- **结构化决策报表台**：Pydantic 强类型 JSON 交付（零件 9.4）。

工具命中与差评检索实时推送、最终答复打字机输出、切换「会话 ID」即开启互不干扰的新咨询。

---

## 📚 权威官方资料直达

- 🔗 **create_agent 标准架构**：[LangChain Agents](https://docs.langchain.com/oss/python/langchain/agents)
- 🔗 **上下文工程官方指南**：[Context Engineering in Agents](https://docs.langchain.com/oss/python/langchain/context-engineering)
- 🔗 **中间件机制**：[LangChain Middleware](https://docs.langchain.com/oss/python/langchain/middleware)
- 🔗 **护栏官方指南**：[Guardrails](https://docs.langchain.com/oss/python/langchain/guardrails)
- 🔗 **向量检索**：[langchain-chroma](https://github.com/langchain-ai/langchain-chroma)
- 🔗 **联网搜索**：[ddgs (DuckDuckGo 官方库)](https://github.com/deedy5/ddgs)

---

## 🎯 全章收官：十三步，从管道到整机

1. **核心收获**：本节把 9.1~9.12 的全部零件**总装**成 SmartBuyer——护栏挡在门外、中间件守住流水线、上下文工程千人千面、工具与 RAG 让参谋有据可依、结构化报表让决策可交付、Callbacks 与测试让整机可审计、可回归。至此你完成的不是"又一个 Demo"，而是一个**零件可溯源、层级可解释、安全可验证**的生产级 Agent。
2. **全章回顾**：从 9.1 一次 `invoke()` 调用，到 LCEL 管道编排、工具生态、记忆裁剪、Callbacks 审计、RAG 增强，再到 `create_agent` 现代架构、上下文工程、自定义中间件与生产级护栏——十三步走完，你已经具备**用工业级框架交付智能体系统**的完整能力。
3. **下一站**：第九章之后，`LangGraph` 将带你在多智能体编排的维度上继续进阶——但请记住本章的整机思维：**零件易学，总装见真章**。愿你在下一次"攒机"中，装出属于自己的旗舰 Agent！🚀
