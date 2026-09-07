# 2.7 工具调用、MCP 协议与 A2A 协作：打通软硬件通用连接

餐厅的小票约定了菜名、数量和口味，外卖平台约定了商家如何接单，不同门店之间还可能需要协调履约。模型工具调用、MCP 和 A2A 也处于不同层次：分别涉及调用表达、工具连接和智能体之间的通信。

---

## 函数调用（Function Calling）：大模型递出“点单小票”

很多新手以为大模型自己可以直接操作电脑硬件，**其实完全不是**。这里讨论的工具调用中，模型输出的是调用请求，实际操作由宿主程序执行。

- - 你去高档餐厅对服务员说：“给我来一份微辣的宫保鸡丁，顺便打包带走”。
  - 服务员（大模型）不会亲自去炒菜，而是立刻打印出一张**格式严谨的标准点单小票（JSON 数据）**：
    ```json
    {
      "dish_name": "宫保鸡丁",
      "spiciness": "微辣",
      "takeout": true
    }
    ```
  - 后厨大厨（真实 Python/Node 程序）接过小票，照着参数开火爆炒，炒好后把成品端给服务员，服务员再笑脸相迎地端给你。

<!-- 图表源文件：img/diagrams/07-diagram-01.mmd；视觉风格：GitHub Dark -->
<p align="center">
  <a href="img/diagrams/07-diagram-01.svg">
    <img src="img/diagrams/07-diagram-01.svg" alt="概念与流程示意图" width="960">
  </a>
</p>

### Function Calling 的标准工程流程（5 步）

1. **声明工具清单**：开发者在系统里注册好“有哪些工具可用、参数长什么样”（Tool Schema）；
2. **模型读到清单**：模型根据用户需求，判断“该不该调、调哪个、传什么参数”；
3. **模型输出调用指令**：模型**不亲自执行**，只输出一段 JSON（工具名 + 参数）；
4. **宿主程序执行**：程序代替模型真正去调函数、查数据库、跑命令；
5. **结果回传再思考**：把真实结果作为“观察”传回模型，模型继续回答或发起下一次调用。

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
# name": "get_weather", "arguments": {"city": "上海"}}

# 3. 宿主程序拿着参数去执行真实函数，再把结果回传给模型
def get_weather(city: str) -> str:
    # 演示返回值，不连接真实天气服务
    return f"演示数据：{city}，晴，28℃"
```

---

## 说明 MCP（Model Context Protocol）协议的三大支柱

- **官方网站**: [https://modelcontextprotocol.io](https://modelcontextprotocol.io)
- **发起方**: Anthropic（已被 Claude、Cursor、Cline、Windsurf 全面采纳）

<!-- 图表源文件：img/diagrams/07-diagram-02.mmd；视觉风格：GitHub Dark -->
<p align="center">
  <a href="img/diagrams/07-diagram-02.svg">
    <img src="img/diagrams/07-diagram-02.svg" alt="概念与流程示意图" width="860">
  </a>
</p>

### 为什么 MCP 是 AI 界的“通用连接 接口”？
- 没有统一连接协议时，同一工具经常需要为不同客户端编写适配代码；
- MCP 制定了全世界通用的协议标准，现在**符合相应协议的 Server 可以被兼容客户端复用；认证方式、协议版本和具体能力仍需要匹配。**

### MCP 的三角色：Host、Client、Server

| 角色 | 生活比喻 | 职责 |
| :--- | :--- | :--- |
| **MCP Host** | 插座所在的房间（AI 应用本体） | Claude Desktop、Cursor、Claude Code 等 AI 客户端 |
| **MCP Client** | 房间墙上的插座孔 | Host 内部的连接器，负责与每个 Server 建立一对一连接 |
| **MCP Server** | 插进去的电器（外部能力） | 对外提供 Prompts / Resources / Tools 的中介程序 |

> 🧩 一个 Host 可以同时连很多个 Server（就像墙上一排插座孔，插满各种电器）。MCP 的“万能”就在于：**插头规格全球统一，即插即用**。

**配置应以客户端和服务端的现行文档为准。** 本节先理解连接关系，第三章再用本地文件服务演示。早期示例中的 GitHub 与 PostgreSQL 参考服务器已经归档，不应继续作为默认安装方案。参见 [MCP 参考服务器维护列表](https://github.com/modelcontextprotocol/servers)。

---

## A2A（Agent-to-Agent）三大团队协作拓扑

多智能体可以采用下面几种组织方式，但这些并不是 A2A 协议规定的三种拓扑。A2A 关注跨系统的能力描述、任务与消息交换：

<!-- 图表源文件：img/diagrams/07-diagram-03.mmd；视觉风格：Pastel 多巴胺 -->
<p align="center">
  <a href="img/diagrams/07-diagram-03.svg">
    <img src="img/diagrams/07-diagram-03.svg" alt="概念与流程示意图" width="760">
  </a>
</p>

1. **主从监工模式（Supervisor）**：类似项目经理派单给各小组长，各小组长搞定后向经理汇总；
2. **扁平互评模式（Peer-to-Peer）**：类似辩论赛或双人结对编程，一个负责快速起草，另一个专职找茬挑刺；
3. **树状层级模式（Hierarchical）**：大型企业化运营，高层定战略，中层拆解任务，底层执行。

### MCP 与 A2A：到底各管哪一段？

很多人把两者搞混，其实分工非常清晰：

| | MCP（Model Context Protocol） | A2A（Agent-to-Agent） |
| :--- | :--- | :--- |
| **连接对象** | 大模型 ↔ 外部工具 / 数据 | AI 智能体 ↔ AI 智能体 |
| **生活比喻** | 通用连接 接口（人机工具） | 会议室开会（智能体与智能体） |
| **解决什么问题** | “AI 怎么调外部工具” | “多个 AI 怎么协作分工” |
| **发起方** | Anthropic | Google |

> 🧩 一句话：**MCP 打通“AI 与工具”，A2A 打通“AI 与 AI”**——一个管能力，一个管协作。

---

## 从 Function Calling → MCP → A2A：一条清晰的演进脉络

| 层级 | 解决的问题 | 生活比喻 | 代表 |
| :--- | :--- | :--- | :--- |
| **Function Calling** | 单个模型怎么“递小票”调用函数 | 服务员写点单小票 | OpenAI / 各家 SDK |
| **MCP** | 工具接口怎么标准化、即插即用 | 通用连接 接口 | Anthropic |
| **A2A** | 多个智能体怎么组队协作 | 会议室分工开会 | Google |

> 💡 三者可以配合使用，但并非必须逐层采用：**先学会“单点调用工具” → 再统一“工具接口标准” → 最后实现“智能体之间的团队协作”**。单个应用内部的多智能体也可以通过函数和共享状态协作，不一定需要 A2A。

---

## 工具定义不仅要写“能做什么”

假设一个工具叫 `search_notes`，只写“搜索笔记”还不足以让模型稳定使用。还需要说明关键词能否为空、一次最多返回多少条、结果字段是什么，以及搜索失败怎样表示。

宿主程序收到调用后，应验证工具是否允许使用、参数是否符合结构、当前用户是否有权访问数据，再执行实际操作。结构正确只说明参数形式合法，不代表业务行为合理。

| 检查层次 | 示例 | 由谁负责 |
| :--- | :--- | :--- |
| 参数结构 | `limit` 必须是整数 | 参数验证程序 |
| 业务范围 | `limit` 不得超过允许上限 | 业务代码 |
| 访问权限 | 只能搜索当前用户的笔记 | 服务端权限检查 |
| 返回结果 | 区分空结果与服务故障 | 工具实现与调用方 |

把“没有找到”与“服务不可用”都返回空列表，会让模型作出错误判断。工具应保留必要的状态信息，同时避免在错误里暴露密钥或完整敏感记录。

## MCP 的工具、资源和提示模板有何区别

可以把工具理解为办理业务的窗口，把资源理解为可阅读的材料，把提示模板理解为填写任务时可复用的表单。三者分别对应 Tools、Resources 和 Prompts。客户端支持哪些能力，必须查看具体实现，而不是看到“MCP”就默认全部可用。

本地标准输入输出连接通常由客户端启动一个进程；远程 HTTP 连接则访问已经运行的服务。连接失败时，前者先检查程序是否安装与启动，后者先检查地址、认证和网络。

## A2A 解决的是跨系统交接

两个由同一程序管理的智能体，可以直接调用彼此或共享状态。不同团队、不同部署环境中的智能体则需要约定怎样描述能力、提交任务、报告进度以及返回成果。[A2A 官方项目](https://github.com/a2aproject/A2A)提供这类互操作协议。

通信协议不能替代任务设计。即使两端成功连接，仍要约定超时、取消、失败和重复请求的处理。一个智能体回复“已经收到”，只代表任务被接收，不代表已经完成。

## 官方文档与权威开源链接

- [Model Context Protocol (MCP) 官方标准文档](https://modelcontextprotocol.io)
- [官方开源 MCP Servers 仓库 (GitHub)](https://github.com/modelcontextprotocol/servers)
- [OpenAI 官方 Function Calling 开发手册](https://platform.openai.com/docs/guides/function-calling)
