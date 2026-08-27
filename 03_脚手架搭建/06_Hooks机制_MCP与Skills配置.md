# 3.6 Hooks 机制、MCP 万能插件与 Skills 技能

> Hooks（钩子）就像“进门自动感应换鞋的门禁保安”，在关键操作前后自动拦截把关；MCP 是连接外部世界的“万能 Type-C 拓展坞”；而 Skills 则是给 Agent 一键安装的“专家作业技能包”！

***

## 🪝 一、先搞懂什么是 Hooks（钩子机制）？

很多新手听到“Hooks”觉得很高深，其实用日常生活场景一秒就能理解：

- **日常生活比喻**：
  - **汽车安全带蜂鸣器**：当你坐上驾驶位发动引擎的一瞬间（触发事件），系统自动检查你有没有系安全带（Pre-Hook 拦截）。没系好就疯狂报警甚至无法挂挡！
  - **自动洗手机**：把手伸到水龙头下（事件），自动感应出水并在离开后自动关闭（Post-Hook 收尾）。

<!-- 图表源文件：img/diagrams/06-diagram-01.mmd；视觉风格：Vercel 黑白 -->
<p align="center">
  <a href="img/diagrams/06-diagram-01.svg">
    <img src="img/diagrams/06-diagram-01.svg" alt="🪝 一、先搞懂什么是 Hooks（钩子机制）？" width="860">
  </a>
</p>

### 编程与 Agent 中最常见的两大 Hooks

1. **Git Hooks (如** **[Husky](https://typicode.github.io/husky/))**：在执行 `git commit` 时，自动运行 Pre-commit Hook，如果代码有报错红字，直接拒绝提交，保证推送到 GitHub 的永远是健康代码；
2. **Agent 安全 Hooks**：在 Agent 执行 `rm`、`drop table` 或向外发送网络请求前，自动弹出危险拦截提示，必须人类授权才可放行。

***

## 🔌 二、手把手配置 MCP（Model Context Protocol）万能插头

- **官方网站**: <https://modelcontextprotocol.io>

### 在 Cursor / Claude Desktop 中配置 MCP

在你的项目根目录 `.cursor/mcp.json` 或 Claude Desktop 配置文件中加入以下配置：

```json
{
  "mcpServers": {
    "local-filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/cheng/Desktop/vibe_coding"]
    },
    "postgres-database": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://user:password@localhost:5432/mydb"]
    },
    "github-tools": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_your_token_here"
      }
    }
  }
}
```

保存后重启编辑器，你的 Agent 瞬间拥有了**直接读写本地指定目录、查询数据库表、以及在 GitHub 上自动提 PR 的物理手脚！**

***

## 🧰 三、如何下载与挂载 Agent Skills 技能包？

**Agent Skill** 是一套封装了专家规程的 `SKILL.md` 标准包。

<!-- 图表源文件：img/diagrams/06-diagram-02.mmd；视觉风格：Notion 简洁 -->
<p align="center">
  <a href="img/diagrams/06-diagram-02.svg">
    <img src="img/diagrams/06-diagram-02.svg" alt="🧰 三、如何下载与挂载 Agent Skills 技能包？" width="760">
  </a>
</p>

### 实战步骤（以安全审计技能为例）：

1. **访问技能大市场**：打开 [Agent Skills Hub (GitHub)](https://github.com/legendaryabhi/agent-skills-hub)；
2. **下载标准技能文件**：找到 `security-audit/SKILL.md`；
3. **放入项目规范目录**：在项目中创建 `.skills/security-audit/SKILL.md`；
4. **对 Agent 说一句话触发**：“请调用 security-audit 技能，对当前项目的所有 API 接口进行漏洞排查”。
   Agent 就会完全按照专家的 SOP 步骤，逐一排查 SQL 注入、跨站脚本和权限漏洞！

***

## 🔗 相关开源工具与官方平台

- [Model Context Protocol 官方极速入门](https://modelcontextprotocol.io/quickstart)
- [Awesome MCP Servers 社区精选资源库](https://github.com/punkpeye/awesome-mcp-servers)
- [Agent Skills Hub 官方开源仓库](https://github.com/legendaryabhi/agent-skills-hub)
- [Husky 现代 Git Hooks 官方文档](https://typicode.github.io/husky/)

