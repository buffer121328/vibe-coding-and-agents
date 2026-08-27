# 2.7 工具调用、MCP 协议与 A2A 协作：打通软硬件万能插头

> 函数调用（Function Calling）是大模型给真实世界程序递出的“标准格式小票”，MCP 是统一全世界所有 AI 工具的“万能 Type-C 接口”，而 A2A 则是让一群 AI 智能体聚在同一个会议室里分工开会、协同干活的通信协议！

---

## 🧾 函数调用（Function Calling）：大模型递出“点单小票”

很多新手以为大模型自己可以直接操作电脑硬件，**其实完全不是**！大模型本质只能输出文字。

- **日常生活比喻**：
  - 你去高档餐厅对服务员说：“给我来一份微辣的宫保鸡丁，顺便打包带走”。
  - 服务员（大模型）不会亲自去炒菜，而是立刻打印出一张**格式极其严谨的标准点单小票（JSON 数据）**：
    ```json
    {
      "dish_name": "宫保鸡丁",
      "spiciness": "微辣",
      "takeout": true
    }
    ```
  - 后厨大厨（真实 Python/Node 程序）接过小票，照着参数开火爆炒，炒好后把成品端给服务员，服务员再笑脸相迎地端给你！

<!-- 图表源文件：img/diagrams/07-diagram-01.mmd；视觉风格：GitHub Dark -->
<p align="center">
  <a href="img/diagrams/07-diagram-01.svg">
    <img src="img/diagrams/07-diagram-01.svg" alt="🧾 函数调用（Function Calling）：大模型递出“点单小票”" width="960">
  </a>
</p>

### Function Calling 的标准工程流程（5 步）

1. **声明工具清单**：开发者在系统里注册好“有哪些工具可用、参数长什么样”（Tool Schema）；
2. **模型读到清单**：模型根据用户需求，判断“该不该调、调哪个、传什么参数”；
3. **模型输出调用指令**：模型**不亲自执行**，只输出一段 JSON（工具名 + 参数）；
4. **宿主程序执行**：程序代替模型真正去调函数、查数据库、跑命令；
5. **结果回传再思考**：把真实结果作为“观察”喂回模型，模型继续回答或发起下一次调用。

> 💡 关键点：**模型只负责“决定”和“描述”，程序负责“执行”**——这就是 Function Calling 的本质。

**Python 代码最小示例**（以 OpenAI 兼容 SDK 为例）：

```python
# 1. 声明一个工具（这就是“工具清单 / Tool Schema”）
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的天气",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }
]

# 2. 模型看完后只会“输出调用指令”，并不真的执行：
#    {"name": "get_weather", "arguments": {"city": "上海"}}

# 3. 宿主程序拿着参数去执行真实函数，再把结果回传给模型
def get_weather(city: str) -> str:
    return f"{city} 今天晴，28℃，适合出行"
```

---

## 🔌 深度拆解 MCP（Model Context Protocol）协议的三大支柱

- **官方网站**: [https://modelcontextprotocol.io](https://modelcontextprotocol.io)
- **发起方**: Anthropic（已被 Claude、Cursor、Cline、Windsurf 全面采纳）

<!-- 图表源文件：img/diagrams/07-diagram-02.mmd；视觉风格：GitHub Dark -->
<p align="center">
  <a href="img/diagrams/07-diagram-02.svg">
    <img src="img/diagrams/07-diagram-02.svg" alt="🔌 深度拆解 MCP（Model Context Protocol）协议的三大支柱" width="860">
  </a>
</p>

### 为什么 MCP 是 AI 界的“万能 Type-C 接口”？
- 在 MCP 诞生前，为 Cursor 写的数据库工具，换到 Claude Desktop 里就必须重写一遍代码；
- MCP 制定了全世界通用的协议标准，现在**只需开发一次 MCP Server，全世界所有的 AI 编辑器和客户端都能即插即用！**

### MCP 的三角色：Host、Client、Server

| 角色 | 生活比喻 | 职责 |
| :--- | :--- | :--- |
| **MCP Host** | 插座所在的房间（AI 应用本体） | Claude Desktop、Cursor、Claude Code 等 AI 客户端 |
| **MCP Client** | 房间墙上的插座孔 | Host 内部的连接器，负责与每个 Server 建立一对一连接 |
| **MCP Server** | 插进去的电器（外部能力） | 对外提供 Prompts / Resources / Tools 的中介程序 |

> 🧩 一个 Host 可以同时连很多个 Server（就像墙上一排插座孔，插满各种电器）。MCP 的“万能”就在于：**插头规格全球统一，即插即用**。

**在配置文件里长什么样**（以 `mcp.json` 为例，详见 3.6 章）：

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxx" }
    }
  }
}
```

---

## 🤝 A2A（Agent-to-Agent）三大团队协作拓扑

当任务极其庞大时，单个 Agent 会出现注意力分散。通过 A2A 协议，可以组建不同形态的 AI 虚拟团队：

<!-- 图表源文件：img/diagrams/07-diagram-03.mmd；视觉风格：Pastel 多巴胺 -->
<p align="center">
  <a href="img/diagrams/07-diagram-03.svg">
    <img src="img/diagrams/07-diagram-03.svg" alt="🤝 A2A（Agent-to-Agent）三大团队协作拓扑" width="760">
  </a>
</p>

1. **主从监工模式（Supervisor）**：类似项目经理派单给各小组长，各小组长搞定后向经理汇总；
2. **扁平互评模式（Peer-to-Peer）**：类似辩论赛或双人结对编程，一个负责疯狂写，另一个专职找茬挑刺；
3. **树状层级模式（Hierarchical）**：大型企业化运营，高层定战略，中层拆解任务，底层执行。

### MCP 与 A2A：到底各管哪一段？

很多人把两者搞混，其实分工非常清晰：

| | MCP（Model Context Protocol） | A2A（Agent-to-Agent） |
| :--- | :--- | :--- |
| **连接对象** | 大模型 ↔ 外部工具 / 数据 | AI 智能体 ↔ AI 智能体 |
| **生活比喻** | 万能 Type-C 接口（人机工具） | 会议室开会（智能体与智能体） |
| **解决什么问题** | “AI 怎么调外部工具” | “多个 AI 怎么协作分工” |
| **发起方** | Anthropic | Google |

> 🧩 一句话：**MCP 打通“AI 与工具”，A2A 打通“AI 与 AI”**——一个管能力，一个管协作。

---

## 🧬 从 Function Calling → MCP → A2A：一条清晰的演进脉络

| 层级 | 解决的问题 | 生活比喻 | 代表 |
| :--- | :--- | :--- | :--- |
| **Function Calling** | 单个模型怎么“递小票”调用函数 | 服务员写点单小票 | OpenAI / 各家 SDK |
| **MCP** | 工具接口怎么标准化、即插即用 | 万能 Type-C 接口 | Anthropic |
| **A2A** | 多个智能体怎么组队协作 | 会议室分工开会 | Google |

> 💡 三者层层递进：**先学会“单点调用工具” → 再统一“工具接口标准” → 最后实现“智能体之间的团队协作”**——这也是从“会用 AI”走向“驾驭 AI 团队”的必经之路。

---

## 🔗 官方文档与权威开源链接

- [Model Context Protocol (MCP) 官方标准文档](https://modelcontextprotocol.io)
- [官方开源 MCP Servers 仓库 (GitHub)](https://github.com/modelcontextprotocol/servers)
- [OpenAI 官方 Function Calling 开发手册](https://platform.openai.com/docs/guides/function-calling)
