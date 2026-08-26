# AGENTS.md（Trae 章节 · 纪律红线）

> 本文件**只收录严格禁止做的事（红线清单）**与项目目录速览。正向开发规范见项目 [.trae/rules/](./project_01_个人博客系统二次开发/.trae/rules/)（frontend / backend / general）与项目 [.traerules](./project_01_个人博客系统二次开发/.traerules)。
> 撰写教学文档（章节 .md、README）按根目录 [agents.md](../agents.md) 执行。
> 📌 阶段开发完成后须同步更新 agents.md 与 `.trae/rules/`（frontend / backend / general，含项目目录、文件清单与红线）——每个阶段开始前都站在已开发好的基础上推进。

---

## 一、项目目录与文件速览（一行注释）

```
project_01_个人博客系统二次开发/
├── .traerules          # Trae 项目专属规则大脑（技术栈 + 二次开发守则）
├── .trae/              # OpenSpec 为 Trae 生成的智能体配置（skills + commands）
├── openspec/           # 规格演进制品：specs 主规格 + changes 变更
├── reference/          # 已验收历史规格归档区（区分历史资产与新迭代规格）
├── docs/               # 各阶段实施方案文档（阶段五起，含 phase06 评论点赞/分页）
├── pyproject.toml      # uv 依赖声明文件（含 openai / python-dotenv）
├── uv.lock             # 锁定的确定性依赖版本
├── .env.example        # 环境变量模板（LLM_API_KEY / LLM_BASE_URL / LLM_MODEL），复制为 .env 使用
├── database.py         # SQLite 引擎、Session 与 get_db 依赖
├── models.py           # SQLAlchemy ORM 数据模型（User + Post(含 summary 导读) + Comment + Like）
├── schemas.py          # Pydantic V2 请求/响应 DTO（含分页/评论/点赞/AI 能力 DTO）
├── security.py         # bcrypt 哈希、JWT 编解码、get_current_user/get_optional_user/require_admin 守卫
├── ai_service.py       # OpenAI 兼容客户端（DeepSeek 默认）、generate_all 摘要/标签/标题/分类生成、JSON 兜底
├── main.py             # FastAPI 路由、鉴权守卫挂载、静态托管、CORS、分页/评论/点赞/AI 接口、后台自动生成
├── index.html          # 单文件前端（TailwindCSS + Marked.js，玻璃拟态，分页/点赞/评论楼层/AI 灵感副驾/导读展示）
└── test_main.py        # pytest 自动化回归测试套件（95 用例全绿，AI 用例 stub LLM，含草稿隐私隔离）
```

---

## 二、严格禁止清单（红线）

1. 🛑 **严禁私自提交**：未经用户明确指令，绝不执行 `git commit` / `git push`；
2. 🛡️ **严禁明文密码**：用户密码必须 bcrypt 哈希，严禁明文存储；鉴权接口严禁绕过 JWT Token 校验；
3. 🧪 **严禁伪造绿灯**：所有接口必须真实跑通 `uv run pytest -q`，禁止跳过验证、伪造测试结果；
4. ⛔ **严禁跳阶段 / 跳 OpenSpec 闭环**：禁止跨阶段一次性混杂开发；每个阶段必须按 `propose → apply → sync/archive` 闭环推进，propose 四件套评审通过前禁止直接编码，实现后必须 `openspec archive` 合并主规格并归档；
5. ⛔ **严禁手操依赖**：禁止手动 pip / venv，依赖一律 `uv` 管理；
6. ⛔ **严禁混淆归档**：禁止擅动 `reference/` 已验收资产与既有 API 契约；
7. ⛔ **严禁破层开发**：禁止混淆 models / schemas / database / main / index.html 的分层职责；
8. ⛔ **严禁泄露密钥**：API Key / 密钥 / 私有域名 100% 脱敏，`*.db` 等产物必须加入 `.gitignore`；
9. ⛔ **严禁虚构信息**：禁止虚构官方链接、技术细节与测试结论；
10. ⛔ **严禁越权写码**：propose / 规划阶段禁止写业务代码，explore 阶段只读不写；
11. 🛡️ **严禁刷量点赞**：点赞必须基于 `likes` 表 `(post_id,user_id)` 唯一约束幂等实现，严禁直接 `post.likes += 1` 无约束累加；
12. 🧪 **严禁破坏分页契约**：列表接口（`/api/posts`、评论列表）必须返回 `{items,total,page,page_size}`，严禁退回裸数组破坏契约；
13. 🔑 **严禁泄露 LLM API Key**：`LLM_API_KEY` 只能存后端 `.env`（已入 `.gitignore`），严禁落库、进响应体、进 `index.html` 或任何前端可读位置；
14. ✍️ **严禁 AI 覆盖人工输入**：自动生成必须「按字段独立回填」——`summary` / `tags` 非空即跳过，标题/分类只做编辑器建议，严禁自动改库；
15. 🛡️ **严禁破坏优雅降级**：未配置 key / LLM 调用失败时，发布、浏览、评论、点赞等博客主流程必须保持可用，AI 接口按约定返回 503/502，严禁抛异常拖垮主流程；
16. 🧪 **严禁 AI 无兜底**：AI 输出必须强制 `json_object` + 解析兜底，严禁裸信任模型输出拼接进响应。
