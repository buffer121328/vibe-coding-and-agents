# Git 提交规范（教学技能包）

把这个文件扔进 `skills/`，Agent 做版本管理时才把它挂进 System Prompt。平时不挂，省 Token。

## 什么时候用

用户提到提交、分支、回滚、冲突、`.gitignore`、PR 说明时启用。

## 必须遵守

1. **先看再改**：提交前先 `git status` 和 `git diff`，不要凭记忆写说明。
2. **一条提交只做一件事**：修登录和改 README 拆开，别揉成「一堆改动」。
3. **说明写人话**：`fix: 登录失败时返回同一个 401，避免枚举账号`，不要写 `update` / `misc`。
4. **不替人提交**：没有明确「帮我提交 / git commit」就只给命令和建议，不要自己跑 `git commit`。
5. **密钥不进库**：`.env`、密钥、证书一律进 `.gitignore`；发现误加先停手告诉用户。

## 常用命令（只读优先）

```bash
git status --short
git diff
git log --oneline -n 12
```

需要改历史（`reset --hard` / `push --force`）时先说明后果，等人点头。
