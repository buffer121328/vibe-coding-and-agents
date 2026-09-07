# 2.9 Multi-Agent（多智能体）：团队作战与七大核心协作范式

编辑一本书时，可以由不同的人负责资料、写作和校对，但还需要有人协调版本与交稿标准。多智能体系统采用类似分工：把任务分给不同执行单元，再交换必要信息并汇总结果。

增加智能体会带来通信、等待和合并成本。只有当分工能减少单个任务的负担，或者形成有效的独立检查时，额外复杂度才值得。

***

## 为什么单兵 Agent 会“力不从心”？（痛点拆解）

很多人问：“既然大模型已经这么聪明了，为什么不直接让一个 Agent 把整个大项目写完？”

- **上下文窗口被塞爆**：单兵 Agent 又要读设计图、又要查数据库表、又要改代码、又要看报错日志，很快就会把有限的上下文塞满，导致“顾头不顾尾”；
- **角色混乱（Role Confusion）**：让同一个 AI “既当运动员（写代码），又当裁判员（找 Bug）”，它往往很难发现自己潜意识里的逻辑漏洞；
- **专业深度不够**：现实世界里没有人能同时是全栈、安全黑客和产品经理，**分工可能帮助收窄每个智能体的任务范围，但单智能体配合合适工具也能完成不少复杂任务。**

<!-- 图表源文件：img/diagrams/09-diagram-01.mmd；视觉风格：Linear 紫色科技感 -->
<p align="center">
  <a href="img/diagrams/09-diagram-01.svg">
    <img src="img/diagrams/09-diagram-01.svg" alt="概念与流程示意图" width="760">
  </a>
</p>

***

## Multi-Agent 七大核心协作范式介绍

在现代多智能体系统（如 MetaGPT、ChatDev、LangGraph、OpenAI Swarm）中，可以观察到下面七种组织方式；这是一种便于学习的分类，并非统一标准，也没有严格的先后代际：

***

### 1. 中心化监工 / 调度分发范式（Supervisor Pattern）

- **医院的“导医台”与“专家门诊”**。
  - 你去医院看病，先到导医台（Supervisor）；
  - 导医台听完你的症状，把骨折的你分流到**骨科诊室（骨科 Agent）**，把发烧的你分流到**发热门诊（内科 Agent）**；
  - 各科室医生看完了，把诊断报告交回给导医台汇总出院。

<!-- 图表源文件：img/diagrams/09-diagram-02.mmd；视觉风格：GitHub Dark -->
<p align="center">
  <a href="img/diagrams/09-diagram-02.svg">
    <img src="img/diagrams/09-diagram-02.svg" alt="概念与流程示意图" width="760">
  </a>
</p>

***

### 2. 顺序线性流水线范式（Sequential / Pipeline Pattern）

- **传统报社的“采写编排印”流水线**。
  - **记者（Agent 1）** 负责去现场采写初稿 ➔ 产出传递给 ➔ **主编（Agent 2）** 负责审查政治合规与错别字 ➔ 产出传递给 ➔ **美工排版师（Agent 3）** 负责插图版面 ➔ **印刷厂（Agent 4）** 出报纸。
- **特点**：前一个 Agent 的输出，作为后一个 Agent 的输入，环环相扣，极为严谨。

<!-- 图表源文件：img/diagrams/09-diagram-03.mmd；视觉风格：Linear 紫色科技感 -->
<p align="center">
  <a href="img/diagrams/09-diagram-03.svg">
    <img src="img/diagrams/09-diagram-03.svg" alt="概念与流程示意图" width="760">
  </a>
</p>

***

### 3. 树状层级分权范式（Hierarchical / Tree-based Pattern）

- **跨国大厂的管理金字塔**。
  - **集团 CEO Agent** 制定年度战略（如“进军东南亚电商市场”）；
  - **事业部 VP Agent** 拆解为季度 KPI（“开发多语言支付网关”）；
  - **技术组长 Agent** 细化为具体开发任务，指派给手底下的**一线搬砖 Agent** 执行。
- **特点**：适合规模庞大、跨学科、跨层级的超级复杂工程。

***

### 4. 辩论对抗与共识范式（Debate / Consensus / Red-Blue Teaming）

- **法庭审判** 与 **网络攻防演练**。
  - **法官** 坐在台上，**原告律师 Agent** 和 **被告律师 Agent** 各自列举证据展开唇枪舌剑的多轮交锋；
  - **红队（黑客攻击 Agent）** 集中寻找系统漏洞，**蓝队（安全防御 Agent）** 见招拆招拼命打补丁。
- **效果与限制**：独立检查可能发现遗漏，但使用相近模型和同一份错误资料的智能体也可能共同犯错。辩论本身不能保证消除幻觉，最终仍需核对证据与测试结果。

<!-- 图表源文件：img/diagrams/09-diagram-04.mmd；视觉风格：GitHub Dark -->
<p align="center">
  <a href="img/diagrams/09-diagram-04.svg">
    <img src="img/diagrams/09-diagram-04.svg" alt="概念与流程示意图" width="860">
  </a>
</p>

***

### 5. 动态自组织蜂群范式（Swarm / Decentralized Handoff）

- **大自然里的蚂蚁搬家与蜜蜂采蜜**。
  - 蚁群里没有一个中央发号施令的“大统领”，每只蚂蚁在路上遇到食物，就会根据信息素动态把任务**转交（Handoff）**给最近的同伴。
- **代表项目**：[OpenAI Swarm](https://github.com/openai/swarm)
- **核心机制**：Agent 之间是扁平平等的。客服 Agent 聊到一半，发现用户要退款，直接一句 `handoff_to_refund_agent()` 把当前对话棒子交给退款专员，无需经过中间主管中转。

***

### 6. 嵌套递归范式（Nested / Recursive Pattern）

- **跨国集团层层分包**——区域分公司接到大单，再拆成小单分包给下面的项目组，项目组还能继续往下拆给小组。每个 Agent 都“上有老、下有小”。
- **核心机制**：主 Agent 把子任务委派给子 Agent，子 Agent 发现自己任务还是太复杂，**还能再开一层孙 Agent**，递归到底，直到每个最小任务都被一个专职 Agent 接手。
- **代表工具**：[LangGraph 子图](https://docs.langchain.com/oss/python/langgraph/use-subgraphs)；能否继续创建下级智能体取决于框架和权限设置。

***

### 7. 动态自编排 / 自我架构范式（Auto-Orchestration / Self-Architecting Pattern）

- **一位总导演拿到剧本后，当场根据剧情需要临时组建剧组**——需要爆破戏就临时请特技组，需要古装就临时雇造型师，全部即插即用，不需要人类预先排好岗位表。
- **核心机制**：主 Agent **自主决定**“要不要并行、创建多少个专业子 Agent、怎么分工委派、何时汇总”，**无需任何预定义角色或手工设计的工作流**——这和前面需要人类设计的 Supervisor、需要代码写死的 Handoff 完全不同。
- **代表工具**：由支持动态任务分派的运行系统实现，具体能力需要查对应版本。

> 🔥 第 7 种是目前最前沿的范式趋势：**把“谁干活、怎么分工”从“人设计”变成“模型自组织”**。

***

## 多智能体之间如何共享信息？（两大主流流派）

<!-- 图表源文件：img/diagrams/09-diagram-05.mmd；视觉风格：Linear 紫色科技感 -->
<p align="center">
  <a href="img/diagrams/09-diagram-05.svg">
    <img src="img/diagrams/09-diagram-05.svg" alt="概念与流程示意图" width="760">
  </a>
</p>

***

## Multi-Agent 的三大避坑指南

1. **防范“无限乒乓死循环”**：
   - 两个 Agent 互相客套（“你写得真棒，请您再过目” ➔ “您才是大师，您先请”），几分钟内烧光几十万 Token。必须给团队设定**硬性的最大轮数（Max Turns）**。
2. **通信开销膨胀**：
   - 如果所有智能体两两通信，潜在连接数会随数量呈平方量级增长。只把必要的信息传递给相关人员，禁止全员全量广播废话；
3. **幻觉放大效应**：
   - 如果第一个 Agent 的 PRD 假定了错误的前提，后续所有 Agent 可能会在这个错误的地基上“一本正经地越盖越高”。因此在关键交接节点必须引入**自动化测试或人类审核（HITL）**。

***

## 真实工具实战：七大范式 × 代表框架对照表

| 范式                          | 代表框架 / 真实工具                                                                                                           |
| :-------------------------- | :-------------------------------------------------------------------------------------------------------------------- |
| 1. 中心化监工 Supervisor         | [LangGraph](https://www.langchain.com/langgraph) 主管 Agent、[CrewAI](https://www.crewai.com)                            |
| 2. 顺序流水线 Pipeline           | LangChain LCEL、[Haystack](https://haystack.deepset.ai) 流水线                                                            |
| 3. 树状层级 Hierarchical        | [AutoGen](https://github.com/microsoft/autogen)、CrewAI 分层流程                                                           |
| 4. 辩论对抗 Debate              | [CAMEL](https://github.com/camel-ai/camel)、AutoGen GroupChat                                                          |
| 5. 蜂群转交 Swarm / Handoff     | [OpenAI Swarm](https://github.com/openai/swarm) / [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) |
| 6. 嵌套递归 Nested              | [Claude Code Subagents](https://docs.anthropic.com/en/docs/claude-code/sub-agents)、LangGraph 嵌套子图                     |
| 7. 动态自编排 Auto-Orchestration | 动态任务分派系统（依具体实现）                                                                                  |

***

## 动态分工还需要哪些约束

动态分工是根据当前任务决定是否创建子任务，而不是预先为每种角色都启动一个智能体。它仍需要可用工具、权限范围、最大并行数和费用限制，不能理解成完全没有预设边界。

例如整理十二份独立报告，可以把各报告摘要分开处理；但如果任务是修改同一个配置文件，同时让十二个智能体写入，反而容易互相覆盖。是否并行应由依赖关系决定，而不是由资料数量决定。

## 相关权威开源框架与经典论文

- [MetaGPT 官方开源仓库 (GitHub)](https://github.com/geekan/MetaGPT) —— 多智能体模拟软件公司的开山鼻祖
- [ChatDev 官方开源仓库 (GitHub)](https://github.com/OpenBMB/ChatDev) —— 虚拟软件开发团队多 Agent 协作平台
- [OpenAI Swarm 实验性蜂群多智能体框架](https://github.com/openai/swarm)
- [CAMEL: Communicative Agents for "Mind" Exploration (经典论文)](https://arxiv.org/abs/2303.17760)

## 怎样判断一个任务能不能拆开

先问三件事：每个子任务是否有独立输入，能否独立判断完成，以及结果能否按明确规则合并。三项都清楚时，分工比较容易产生收益。

| 任务 | 是否适合并行 | 原因 |
| :--- | :--- | :--- |
| 分别提取不同报告中的指标 | 通常适合 | 输入独立，可按统一字段汇总 |
| 接口规范确定后分别实现前后端 | 有条件适合 | 必须共享并遵守同一版接口约定 |
| 同时重写同一个文件 | 通常不适合 | 修改容易覆盖，合并难判断 |
| 根据上一步实验结果选择下一步 | 通常需顺序推进 | 后一步依赖真实反馈 |

角色名称不能替代任务边界。“你是数据库专家”不够，还要说明允许查看哪些表、要输出什么、哪些写入禁止执行，以及什么时候交回结果。

## 交接内容应该包含什么

把交接想成交班记录：下一位同事需要知道已经做到了哪里，不需要重复听全部聊天。可以包括目标、输入来源、关键发现、证据位置、未解决问题和可直接使用的成果。

主智能体收到结果后，应检查遗漏与冲突。两份结果对同一规则理解不同，不能简单拼在一起；需要回到原文或规范确认。汇总者承担的是整合与验收责任，不只是压缩文字。

## 共享文件与独立上下文的区别

独立上下文可以让各智能体集中处理自己的任务，但不一定意味着文件系统也隔离。如果它们使用同一个目录，仍可能同时修改文件。可以指定各自负责的文件范围，或使用独立工作区，再统一合并。

共享状态则要明确更新规则：哪些字段可以并行追加，哪些只能由协调者修改。例如每个研究员追加自己的来源记录较容易合并，而多人同时改“最终结论”就容易覆盖。

## 如何比较单智能体与多智能体

用同一组任务比较正确率、总耗时、调用费用和人工返工时间。不要只比较最早完成的一个子任务，也不要忽略最后汇总失败的情况。

如果单智能体已经稳定完成，增加分工未必值得。如果独立检查能明显减少遗漏，或多个耗时任务确实互不依赖，再引入多智能体更有依据。
