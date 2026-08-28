# 1.7 Vibe Coding 思维方式：从“苦力码农”到“交响乐指挥官”

> **“There's a new kind of coding I call 'vibe coding', where you entirely give in to the vibes, embrace every AI, and forget that the code even exists... I just see stuff, say stuff, run stuff, and copy paste stuff, and it mostly works.”**
> —— *Andrej Karpathy (前 OpenAI 联合创始人、前 Tesla AI 总监)*

---

## 🌊 什么是 Vibe Coding？（大白话版）

在 2025 年，“Vibe Coding” 成为了整个科技界最火爆的词汇，甚至被柯林斯词典评选为年度词汇。**2025 年 2 月，Andrej Karpathy 给这种全新的开发方式起了“Vibe Coding”这个名字**：你主要用自然语言描述你想要什么，让 AI 生成实现，再通过看结果、继续说、继续改来推进。

要注意：**Vibe Coding 并不是在 Agent 之后“又冒出来的新一代技术”**。它更像是建立在大模型、AI 补全、AI 原生 IDE、Coding Agent 等所有前面能力之上的**一种开发方式 / 思维方式**——前面几代解决了“AI 越来越能干”，这一代解决的是“**你该用什么姿势和 AI 协作**”。

用大白话来说，**Vibe Coding 就是“氛围感编程 / 意图流编程”**：
- **过去写代码**：你必须像个泥瓦匠，在大脑里紧绷着每一块砖（语法、分号、内存、类型），稍不留神就被红字报错搞到心力交瘁；
- **现在 Vibe Coding**：你彻底从琐碎的代码细节中解脱出来，化身为**产品总监 / 架构设计师**。你喝着咖啡，看着屏幕，用人话向 AI 描述你的灵感与想法，AI 负责在底下疯狂搬砖，你只需要看效果、提反馈、享受创造的纯粹快乐！

<!-- 图表源文件：img/diagrams/07-diagram-01.mmd；视觉风格：Macaron 马卡龙 -->
<p align="center">
  <a href="img/diagrams/07-diagram-01.svg">
    <img src="img/diagrams/07-diagram-01.svg" alt="🌊 什么是 Vibe Coding？（大白话版）" width="960">
  </a>
</p>

---

## 📊 编程进化主线：六阶段大白话对比表

> 说明：这是按时间演进的主线（传统手写 → AI 代码补全 → 对话式 AI → AI 原生 IDE → Coding Agent → Vibe Coding）。1.6 的低代码/工作流属于**并行支线**，不占主线代数。

| 维度 | 1. 传统手写 | 2. AI 代码补全 | 3. 对话式 AI | 4. AI 原生 IDE | 5. Coding Agent | 6. 🌊 Vibe Coding |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **代表工具** | VS Code, Vim, IDEA | Copilot, Continue | ChatGPT, Claude, DeepSeek | Cursor, Windsurf, Trae | Claude Code, Devin, Aider | 以上全部 + Bolt.new + MCP |
| **你干的最多的事** | 一个字母一个符号手打 | 紧盯屏幕不停按 Tab 键 | 网页和代码间疯狂复制粘贴 | 在 IDE 里跟 AI 对话改代码 | 给实习生下指令并点批准 | **动动嘴皮子提需求、看成品验收** |
| **遇到报错怎么办** | 百度/Google 到处搜帖子 | 人工粘贴报错，代码搜不到答案 | 复制报错发回网页问 AI | 选中代码让 IDE 就地改 | Agent 自己看报错并自我修复 | **测试全自动跑，哪里不对改哪里** |
| **你的真实身份** | 苦力打字员 (Coder) | 结对副驾驶 (Driver) | 人肉中转站 (Router) | 对话督导员 (Director) | 领航督导员 (Supervisor) | **交响乐总指挥 (Director)** |
| **搞定产品的速度** | 几个月起步 | 几周 | 几天 | 几天~几小时 | 几小时 | **一杯咖啡的功夫出原型！** |

**人的角色变化**（贯穿整条主线，非常漂亮）：
> 自己写每一行 → AI 猜你的下一行 → 你开始告诉 AI 怎么写 → AI 开始理解整个项目 → AI 可以自己动手执行 → 你主要负责说清目标、给上下文、看结果。

---

## 🔺 Vibe Coding 爽快又不翻车的“黄金三角”

要想真正玩转 Vibe Coding，而不是陷入“代码越跑越乱”的泥潭，只需要掌握这三点：

<!-- 图表源文件：img/diagrams/07-diagram-02.mmd；视觉风格：Cyberpunk -->
<p align="center">
  <a href="img/diagrams/07-diagram-02.svg">
    <img src="img/diagrams/07-diagram-02.svg" alt="🔺 Vibe Coding 爽快又不翻车的“黄金三角”" width="760">
  </a>
</p>

### 1. 意图讲清楚（Intent）：别让 AI 当算命先生
- ❌ **糟糕的提问**：“帮我写个网站”。（AI 根本不知道你要什么，只能瞎猜）；
- ✅ **优秀的提问**：“用 Next.js 和 Tailwind CSS 做一个待办事项网站，左侧是分类菜单，右侧是任务列表，支持本地保存，界面要现代简约风格”。

### 2. 上下文喂饱（Context）：给 AI 充足的参考资料
- AI 之所以写错，通常是因为你没给它足够的信息。
- 善用 `.cursorrules` 文件告诉 AI 你的规矩（例如：“本项目一律使用 TypeScript”、“中文注释必须清晰”），或者直接把设计图和参考文档 `@` 引用给它看。

### 3. 验证自动化（Verification）：别用肉眼看代码，直接看运行效果
- 既然是 Vibe Coding，你就**不需要逐行审阅 AI 写了几千行什么代码**；
- 只要让测试跑起来，或者在浏览器/预览窗口里亲手点一点、测一测功能是否符合预期。

---

## 🛡️ 新手防翻车指南

1. **多用 Git 存盘打点**：
   - 每当 AI 做好一个满意的功能，随手做一次 Git 提交。万一下一步 AI 把代码改乱了，一键就能回滚重来！
2. **每次只做一个小功能，小步快跑**：
   - 不要一口气让 AI “帮我把整个淘宝做出来”；
   - 先做“商品列表展示”，确认没问题了，再做“加入购物车”，然后做“结算下单”，循序渐进体验极佳。
3. **守住核心数据大门**：
   - 涉及到用户密码、真实支付接口、核心数据库配置，人类要保持基本的安全意识。

---

## 🚀 准备开启你的 Vibe Coding 之旅

恭喜你！读到这里，你已经对现代 AI 编程的核心发展了然于胸。

接下来让我们进入脚手架的搭架！
