# 3.5 Spec 驱动开发与 OpenSpec 实战：终结 AI 的瞎编乱猜

> 盖摩天大楼绝对不能靠包工头“凭感觉盲目砌砖”，必须先画一张严谨的“建筑施工蓝图（Spec）”！Spec 驱动开发就是让 AI 动笔写代码之前，先锁定需求规格与技术契约，彻底消灭 AI 随心所欲的瞎编乱造！

***

## 🏗️ 为什么说 Spec（规格说明书）是 Vibe Coding 的定海神针？

在早期使用 AI 写代码时，很多人遇到过这种痛点：

- 你对 AI 说：“帮我加个点赞功能”；
- AI 第一次写用了前端本地状态，第二次写用了 Redis，第三次又在数据库新建了一张表；
- **口头模糊需求（Ad-hoc Prompting）会导致系统架构迅速腐烂！**

**Spec-Driven Development（SDD / 规范驱动开发）** 的核心思想就是：

> **“Spec 是代码仓库唯一的真实之源（Source of Truth）。先出蓝图，后写代码；改代码必先改 Spec！”**

<!-- 图表源文件：img/diagrams/05-diagram-01.mmd；视觉风格：Notion 简洁 -->
<p align="center">
  <a href="img/diagrams/05-diagram-01.svg">
    <img src="img/diagrams/05-diagram-01.svg" alt="🏗️ 为什么说 Spec（规格说明书）是 Vibe Coding 的定海神针？" width="960">
  </a>
</p>

***

## 🌟 核心开源标准主推：OpenSpec架构详解

**OpenSpec** 是目前开源社区专为 AI Coding Agent 打造的最轻量、最标准的规范驱动框架。

### OpenSpec 标准目录骨架

在项目根目录下维护一个 `openspec/` 目录：

```
my-project/
├── openspec/
│   ├── AGENTS.md               # 告诉 Agent 如何阅读和执行本规范的指南
│   ├── specs/                  # 【主规范库】：系统的全局架构、数据模型与永久约定
│   │   ├── auth-system.md      # 用户认证系统的权威标准规范
│   │   └── database-schema.md  # 数据库表的永久权威设计
│   └── changes/                # 【增量变更提案 (Delta Specs)】
│       └── 2026-08-add-wechat-pay/  # 本次新增微信支付的具体任务提案与验收清单
└── src/                        # 实际业务源代码
```

### OpenSpec 标准流转五步法

<!-- 图表源文件：img/diagrams/05-diagram-02.mmd；视觉风格：Macaron 马卡龙 -->
<p align="center">
  <a href="img/diagrams/05-diagram-02.svg">
    <img src="img/diagrams/05-diagram-02.svg" alt="OpenSpec 标准流转五步法" width="760">
  </a>
</p>

***

## 🤖 Spec 驱动的 Agent 编译器推荐：Qoder(Alibaba)

- **核心定位**: 阿里巴巴通义实验室推出的 **Spec-First AI 开发者平台与 IDE 编译器**。
- **杀手锏特性**：
  1. **Quest 异步任务模式**：开发者只要在后台提交一份格式清晰的 Spec 说明书，Qoder 的 Agent 就会在后台自主进行代码分析、跨模块编码、自动化测试，完成后生成一份详尽的交付报告；
  2. **Action Flow 实时追踪**：全透明展示 Agent 思考、读文件、改代码的决策树链条；
  3. **Repo Wiki 自动沉淀**：自动提炼项目的架构设计，让团队新人或 AI 随时能查阅最新项目规范。

***

## 📝 编写一份高质量 Spec 的标准模版案例

```markdown
# 功能规格说明书：用户邮箱验证码注册 (Email Auth Spec)

## 1. 业务目标
为新用户提供通过邮箱获取 6 位数字验证码并完成注册的功能。

## 2. 接口设计契约
- **请求路由**: `POST /api/v1/auth/send-code`
- **请求体 (JSON)**: `{"email": "user@example.com"}`
- **响应体 (JSON)**: `{"code": 200, "message": "验证码已发送，5分钟内有效"}`

## 3. 技术约束与安全规则
- 验证码有效期：严格限制为 300 秒（存入 Redis 缓存并设置 TTL）；
- 频率限制：同一个邮箱 IP 60 秒内只能请求一次（防刷接口）；
- 密码存储：必须使用 bcrypt 加密加盐后存入 User 表。

## 4. 自动化验收标准 (Acceptance Criteria)
- [ ] 单元测试：发送验证码接口测试用例 100% 绿灯；
- [ ] 边界测试：输入非法邮箱格式时返回 400 Bad Request；
- [ ] 压力测试：连续点击两次只发送一封邮件。
```

把这份 Spec 丢给 Agent，AI 就会**分毫不差地严格实现你的全部意图**，彻底终结架构跑偏！
