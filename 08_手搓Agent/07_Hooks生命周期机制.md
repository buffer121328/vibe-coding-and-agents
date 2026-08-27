# 8.7 Hooks 生命周期机制：AOP 切面拦截、参数脱敏与审计日志

> **“银行运钞车出发前要核对押运清单（Pre-Hook），送达后要清点封条与盖章回执（Post-Hook）——所有操作必须透明、可审计且绝不泄密！”**

***

## 🪝 为什么成熟的 Agent 框架必须具备 Hooks 机制？

随着 Agent 接入的工具越来越多，如果我们在每个工具函数内部去写“计时代码”、“日志打印”、“密钥脱敏”、“异常捕获”，**代码很快就会变成一团乱麻（意大利面条式代码）**。

在软件工程中，**AOP（面向切面编程）** 是解耦横切关注点的终极杀招。在 Agent 架构中（参考 [learn-claude-code s04 Hooks](https://github.com/shareAI-lab/learn-claude-code/tree/main/s04_hooks)），我们通过 **Hooks（生命周期钩子）**，可以在不侵入任何工具业务逻辑的前提下，实现强大的扩展能力：
1. **安全脱敏**：防止工具执行后返回的敏感 API Key、数据库密码被直接喂进上下文；
2. **性能与耗时遥测**：精确记录每个工具的执行毫秒数；
3. **审计与合规**：完整记录所有调用的输入输出流水。

<!-- 图表源文件：img/diagrams/07-diagram-01.mmd；视觉风格：Linear 紫色科技感 -->
<p align="center">
  <a href="img/diagrams/07-diagram-01.svg">
    <img src="img/diagrams/07-diagram-01.svg" alt="🪝 为什么成熟的 Agent 框架必须具备 Hooks 机制？" width="760">
  </a>
</p>

***

## 💻 源码实现：`HookManager` 切面注册与调度

在 `code/s07_hooks_lifecycle.py` 中，我们设计了极简优雅的切面管理器：

```python
class HookManager:
    def __init__(self):
        self.pre_tool_hooks = []
        self.post_tool_hooks = []

    def register_pre_tool(self, hook: Callable):
        self.pre_tool_hooks.append(hook)

    def register_post_tool(self, hook: Callable):
        self.post_tool_hooks.append(hook)

    def run_pre_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """按注册顺序依次流水线处理参数"""
        for hook in self.pre_tool_hooks:
            args = hook(tool_name, args) or args
        return args

    def run_post_tool(self, tool_name: str, args: Dict[str, Any], result: Any) -> Any:
        """按注册顺序流水线加工执行结果"""
        for hook in self.post_tool_hooks:
            result = hook(tool_name, args, result)
        return result
```

### 生产级实用 Hook：敏感 Key 自动脱敏

```python
def sensitive_masking_post_hook(tool_name: str, args: Dict[str, Any], result: Any) -> Any:
    """自动屏蔽 sk-xxx / glm-xxx 密钥与密码"""
    if not isinstance(result, str):
        return result
    # 正则保留前8位，后续全部打码
    masked = re.sub(r"(sk-[a-zA-Z0-9]{8})[a-zA-Z0-9]+", r"\1****", result)
    masked = re.sub(r"(glm-[a-zA-Z0-9]{8})[a-zA-Z0-9-]+", r"\1****", masked)
    masked = re.sub(r"(password\s*[:=]\s*)\S+", r"\1******", masked, flags=re.IGNORECASE)
    return masked
```

***

## 🕹️ 在 Gradio 中动手体验

在 `code/app.py` 中切换到 **`8.7 Hooks 生命周期`** 标签页：

1. 在输入框填入一段模拟含有泄漏风险的日志：`数据库连接成功: host=127.0.0.1, key=sk-abcdef1234567890xyz, endpoint=glm-20250225123456-abcdef`；
2. 点击 **🧪 触发生命周期 Hooks 加工**；
3. 观察输出结果：敏感密钥被精准打码为 `sk-abcdef12****`，且末尾自动追加了高精度的 `⏱️ [耗时统计: 50.12ms]` 标记！

***

## 📡 进阶深化：从"钩子"升级到"事件总线"（参考 Pi 的事件驱动设计）

Hooks 本质上是"写死在 Agent 主流程里的切面回调"。当要接入的观察者越来越多（账单审计、轨迹回放、Web 进度条、评测统计）时，更优雅的姿势是 **事件总线（EventBus）**——Agent 只负责 `emit` 一条结构化事件，任何关心者通过 `subscribe` 订阅（这正是 [Pi Agent](https://github.com/earendil-works/pi) 的核心设计）：

```python
class EventBus:
    def __init__(self):
        self._subscribers = {}     # event_type -> [callback, ...]
        self.history = []          # 完整事件历史，可审计/回放

    def subscribe(self, event_type, cb):          # '*' 表示通配订阅所有事件
        self._subscribers.setdefault(event_type, []).append(cb)

    def emit(self, event):
        self.history.append(event)
        for cb in self._subscribers.get(event.event_type, []) + self._subscribers.get("*", []):
            cb(event)
```

两者关系：**Hooks 是"点对点"的切面，事件总线是"一对多"的广播**。Hooks 适合少数几个固定横切面（脱敏、计时），EventBus 适合面向未来的可扩展可观测体系——我们将在 **[8.12 可观测性与性能评估](12_可观测性与性能评估.md)** 完整实现它。

***

## 📝 本节小结

- **逻辑解耦**：业务工具只关心功能实现，日志、鉴权、脱敏、监控全部由 Hooks 切面统一接管；
- **防护屏障**：确保任何通过工具读到的敏感配置文件（如 `.env`）在喂回大模型前完成清洗，防止二次泄露；
- **新挑战**：当 Agent 运行了 20 轮对话，工具返回了大量日志，上下文即将把模型窗口塞爆时该怎么办？请进入——**[8.8 上下文工程与压缩](08_上下文工程与压缩.md)**！
