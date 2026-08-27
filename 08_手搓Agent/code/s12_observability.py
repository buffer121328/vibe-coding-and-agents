"""s12_observability.py - 8.12 可观测性与性能评估 (EventBus 事件总线 + TokenCostAudit 费用审计 + EvalSuite 评估套件)"""
import json, random, time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
try:
    import tiktoken  # 可选依赖：未安装时自动降级为字符数估算
except ImportError:
    tiktoken = None
from s01_env_setup import ZhipuGLMClient

# ========== 1️⃣ AgentEvent 可观测事件：运行过程中的一次瞬时动作 ==========
@dataclass
class AgentEvent:
    """🚀 一条可观测事件（Pi 风格事件联合体）：记录 Agent 运行中的一次瞬时动作"""
    event_type: str      # agent_start / llm_call / tool_call / tool_result / compact / error / finish
    tool_name: str = ""  # 涉及的工具名（非工具事件为空）
    content: str = ""    # 事件附带文本（工具结果 / 回复 / 错误信息）
    tokens: int = 0      # 本次 LLM 调用消耗的总 token 数
    latency_ms: float = 0.0   # 本次动作耗时（毫秒）
    timestamp: float = field(default_factory=time.time)  # 事件发生时间戳

    def to_dict(self) -> Dict[str, Any]:
        """将事件序列化为字典，便于 JSON 展示与持久化"""
        return {"event_type": self.event_type, "tool_name": self.tool_name, "content": self.content,
                "tokens": self.tokens, "latency_ms": round(self.latency_ms, 2), "timestamp": round(self.timestamp, 3)}

# ========== 2️⃣ EventBus 事件总线：subscribe 订阅 / emit 广播（参考 Pi 事件驱动设计） ==========
class EventBus:
    """📡 事件总线：让外部模块实时感知 Agent 的完整运行过程"""
    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[[AgentEvent], None]]] = {}
        self.history: List[AgentEvent] = []   # 📼 完整事件历史（审计 / 回放用）

    def subscribe(self, event_type: str, callback: Callable[[AgentEvent], None]) -> None:
        """订阅某类事件；传 '*' 表示通配订阅所有事件（Pi 风格）"""
        self._subscribers.setdefault(event_type, []).append(callback)

    def emit(self, event: AgentEvent) -> None:
        """广播一条事件：分发给精确匹配者 + 通配订阅者，并写入历史"""
        self.history.append(event)
        for cb in list(self._subscribers.get(event.event_type, [])) + self._subscribers.get("*", []):
            cb(event)

# ========== 3️⃣ TokenCostAudit 费用审计员：tiktoken 估算 + 账单输出 ==========
class TokenCostAudit:
    """💰 费用审计员：用 tiktoken 估算 token，并按定价表换算人民币账单"""
    # 💡 简易定价表（元 / 每百万 token）—— 教学用假想价格，真实价格以 GLM 官方为准
    PRICES = {"deepseek-v3": {"input": 2.0, "output": 8.0},   # 输入 2 元 / 输出 8 元（假想）
              "deepseek-r1": {"input": 4.0, "output": 16.0}}  # 输入 4 元 / 输出 16 元（假想）；均为教学假想价，真实以官方为准

    def __init__(self) -> None:
        self._records: List[Dict[str, Any]] = []
        self._enc = None
        if tiktoken is not None:
            try:
                self._enc = tiktoken.get_encoding("cl100k_base")   # 🧮 中文友好编码器
            except Exception:
                self._enc = None

    def estimate_tokens(self, text: str) -> int:
        """用 tiktoken 估算文本 token 数（失败则按 1 token ≈ 1.5 字符兜底）"""
        try:
            return len(self._enc.encode(text)) if self._enc else max(1, int(len(text) / 1.5))
        except Exception:
            return max(1, int(len(text) / 1.5))

    def record_usage(self, model_name: str, input_tokens: int, output_tokens: int,
                     latency_ms: float = 0.0) -> None:
        """记录一次 LLM 调用用量：输入/输出 token 与耗时，并累计成本"""
        price = self.PRICES.get(model_name, self.PRICES["deepseek-v3"])
        cost = (input_tokens / 1e6) * price["input"] + (output_tokens / 1e6) * price["output"]
        self._records.append({"model": model_name, "input_tokens": input_tokens, "output_tokens": output_tokens,
                              "cost": cost, "latency_ms": latency_ms})

    def summary(self) -> str:
        """输出人类可读的费用审计账单文本"""
        n = len(self._records)
        recs = self._records
        total_in = sum(r["input_tokens"] for r in recs); total_out = sum(r["output_tokens"] for r in recs)
        cost = sum(r["cost"] for r in recs); avg = sum(r["latency_ms"] for r in recs) / n if n else 0.0
        return (f"📊 ====== Token 费用审计账单 ======\n"
                f"🔢 调用次数      : {n}\n"
                f"📥 输入 Tokens   : {total_in:,}\n"
                f"📤 输出 Tokens   : {total_out:,}\n"
                f"🧮 总 Tokens     : {total_in + total_out:,}\n"
                f"💴 预估成本      : ¥ {cost:.4f}\n"
                f"⏱️ 平均时延      : {avg:.1f} ms")

# ========== 4️⃣ EvalSuite 评估套件（参考 hello-agents 第12章） ==========
class EvalSuite:
    """🎯 评估套件：对一组任务各跑 trials 次，统计成功率 / 平均耗时 / 平均 token"""
    def __init__(self, client, tasks: List[str], trials: int = 3,
                 model_name: str = "deepseek-v3",
                 success_keywords: Optional[List[str]] = None,
                 fail_keywords: Optional[List[str]] = None) -> None:
        self.client = client          # 兼容 ZhipuGLMClient（真实评估时使用）
        self.tasks, self.trials = tasks, trials
        self.model_name = model_name
        self.success_keywords = success_keywords or ["成功", "完成", "✅", "OK"]
        self.fail_keywords = fail_keywords or ["失败", "错误", "异常", "❌"]
        self.audit = TokenCostAudit()

    def _on_llm_call(self, event: AgentEvent) -> None:
        """LLM 调用事件监听：把 token 用量与耗时记入费用审计"""
        out_t = self.audit.estimate_tokens(event.content)  # 📤 对回复文本精确估算
        self.audit.record_usage(self.model_name, max(1, event.tokens - out_t), out_t, event.latency_ms)

    def _is_success(self, output: str) -> bool:
        """用关键词子串匹配判断成功：先看失败词，再看成功词"""
        return not any(k in output for k in self.fail_keywords) \
            and any(k in output for k in self.success_keywords)

    def run_eval(self, agent_runner_callable: Callable[[EventBus, str], str]) -> Dict[str, Any]:
        """对每个任务跑 trials 次：用 EventBus 收集轨迹，统计成功率/平均耗时/平均 token"""
        self.audit = TokenCostAudit()
        report: Dict[str, Any] = {"summary": {}, "tasks": {}}
        all_ok, all_lat, all_tok = [], [], []
        for task in self.tasks:
            s_ok, lats, toks, trs = 0, [], [], []
            for _ in range(self.trials):
                bus = EventBus()
                bus.subscribe("llm_call", self._on_llm_call)      # 🪝 挂载费用审计监听
                t0 = time.perf_counter()
                out = agent_runner_callable(bus, task)            # 🏃 运行一次 Agent
                lat = (time.perf_counter() - t0) * 1000           # ⏱️ 统计总耗时
                lats.append(lat)
                toks.append(sum(e.tokens for e in bus.history))   # 🧮 累加本次运行的 token
                ok = self._is_success(out)
                s_ok += ok
                trs.append({"output": out, "success": ok,
                            "events": [e.to_dict() for e in bus.history]})

            all_ok.append(s_ok); all_lat += lats; all_tok += toks
            report["tasks"][task] = {"success_rate": round(s_ok / self.trials, 3),
                                     "avg_latency_ms": round(sum(lats) / self.trials, 1),
                                     "avg_tokens": round(sum(toks) / self.trials, 1), "traces": trs}
        runs = len(self.tasks) * self.trials
        report["summary"] = {"total_tasks": len(self.tasks), "total_runs": runs,
                             "overall_success_rate": round(sum(all_ok) / runs, 3),
                             "avg_latency_ms": round(sum(all_lat) / len(all_lat), 1),
                             "avg_tokens": round(sum(all_tok) / len(all_tok), 1),
                             "cost_audit": self.audit.summary()}
        return report

def run_mock_eval(tasks: Optional[List[str]] = None, trials: int = 3) -> Dict[str, Any]:
    """� 本地 Mock 评估演示：不依赖网络与 API Key，直接返回评估报告 dict（供 Gradio 工作台复用）"""
    class MockResponse:
        """模拟 OpenAI 返回体，兼容 .choices[0].message.content 访问"""
        def __init__(self, content: str) -> None:
            self.content = content
            self.message = self   # 📎 message 指向自身，即可用 .choices[0].message.content
        @property
        def choices(self) -> List[Any]:
            return [self]

    class MockLLM:
        """🤖 假应答函数：输入含"失败/错误/异常"则返回失败标记，否则返回成功"""
        def chat(self, messages):
            text = messages[-1]["content"]
            reply = ("❌ 任务执行失败：遇到了未知异常，无法完成。" if any(w in text for w in ["失败", "错误", "异常"])
                     else "✅ 任务执行成功，已顺利完成全部步骤！")
            return MockResponse(reply)

    def agent_runner(bus: EventBus, task: str) -> str:
        """🧭 本地模拟的 Agent 运行器：把一次任务的完整过程广播到事件总线"""
        audit = TokenCostAudit()
        bus.emit(AgentEvent("agent_start", content=f"🎬 开始任务：{task}"))
        time.sleep(random.uniform(0.01, 0.05))          # 模拟规划耗时
        prompt_text = f"用户任务：{task}，请规划并执行。"
        reply = MockLLM().chat([{"role": "user", "content": prompt_text}]).choices[0].message.content
        time.sleep(random.uniform(0.02, 0.06))          # 模拟推理耗时
        bus.emit(AgentEvent("llm_call", content=reply,
                            tokens=audit.estimate_tokens(prompt_text) + audit.estimate_tokens(reply),
                            latency_ms=random.uniform(300, 900)))
        if "失败" in reply:                              # 出错时额外广播 error 事件
            bus.emit(AgentEvent("error", content="捕获到模型报错，正在记录。"))
        bus.emit(AgentEvent("finish", content=reply))
        return reply

    suite = EvalSuite(client=MockLLM(), tasks=tasks or ["写一个计算器程序", "修复 404 页面错误"], trials=trials)
    return suite.run_eval(agent_runner)

def run_real_agent_eval(tasks: Optional[List[str]] = None, trials: int = 1,
                        client: Optional[ZhipuGLMClient] = None) -> Dict[str, Any]:
    """🚀 真实引擎联动评估：用 s01 客户端驱动 s02 ReActAgent，经 EvalSuite 采集可观测指标

    懒加载 s02，Mock 场景不强依赖；未配置 ZHIPU_API_KEY 时抛出异常由调用方处理。
    """
    from s02_react_loop import ReActAgent      # 懒加载，避免纯 Mock 场景硬依赖
    client = client or ZhipuGLMClient()
    if not client.api_key:
        raise RuntimeError("未配置 ZHIPU_API_KEY")

    def real_agent_runner(bus: EventBus, task: str) -> str:
        """🏃 真实 ReActAgent 运行器：把工具动作与最终回答实时广播到事件总线"""
        audit = TokenCostAudit()
        bus.emit(AgentEvent("agent_start", content=f"🎬 开始任务：{task}"))
        ans, logs = ReActAgent(client).run(task)
        for log in logs:                          # 回放每步 Thought/Action/Observation
            if log.get("action") and log["action"] != "完成":
                bus.emit(AgentEvent("tool_call", tool_name=log["action"],
                                    content=log.get("observation", "")))
        bus.emit(AgentEvent("llm_call", content=ans,
                            tokens=audit.estimate_tokens(task) + audit.estimate_tokens(ans),
                            latency_ms=random.uniform(400, 1500)))
        bus.emit(AgentEvent("finish", content=ans))
        return ans

    suite = EvalSuite(client=client, tasks=tasks or ["计算 25 * 4 + 10 等于多少？"], trials=trials)
    return suite.run_eval(real_agent_runner)

if __name__ == "__main__":
    print("🧪 开始本地可观测性自测（全程 Mock，不联网）...\n")

    print("--- 1. EventBus 订阅/广播/通配自测 ---")
    bus = EventBus()
    seen = []
    bus.subscribe("tool_call", lambda e: seen.append(("tool_call", e.tool_name)))
    bus.subscribe("*", lambda e: seen.append(("*", e.event_type)))
    bus.emit(AgentEvent("llm_call", content="hi", tokens=10))
    bus.emit(AgentEvent("tool_call", tool_name="run_bash", content="ls"))
    print("收到事件数:", len(seen), "| 事件历史条数:", len(bus.history))

    print("\n--- 2. TokenCostAudit 记账与账单自测 ---")
    audit = TokenCostAudit()
    audit.record_usage("deepseek-v3", input_tokens=1000, output_tokens=500, latency_ms=120.0)
    audit.record_usage("deepseek-r1", input_tokens=2000, output_tokens=1000, latency_ms=300.0)
    print(audit.summary())

    print("\n--- 3. EvalSuite 成功率判定自测 ---")
    suite = EvalSuite(client=None, tasks=[], trials=1)
    print("'✅ 成功完成' 判定:", suite._is_success("✅ 成功完成，一切正常"))
    print("'❌ 任务失败' 判定:", suite._is_success("❌ 任务失败，遇到异常"))

    print("\n--- 4. 完整 Mock 评估报告 ---")
    report = run_mock_eval()
    print("📋 ====== 评估报告 (JSON) ======\n" + json.dumps(report, ensure_ascii=False, indent=2))
    print("\n📜 ====== 单次运行轨迹回放 (trace) ======")
    for ev in report["tasks"]["写一个计算器程序"]["traces"][0]["events"]:
        print(f"  [{ev['event_type']:>10}] {ev['content'][:36]}  (tokens={ev['tokens']}, {ev['latency_ms']:.0f}ms)")

    print("\n--- 5. 真实引擎联动小案例 (s01 客户端 + s02 ReActAgent + 可观测采集) ---")
    try:
        report = run_real_agent_eval()
        task_name = list(report["tasks"])[0]
        tr = report["tasks"][task_name]["traces"][0]
        print(f"🤖 模型最终回答: {tr['output'][:120]}")
        print(f"🎯 判定: {'✅ 成功' if tr['success'] else '❌ 失败'} (按通用成功词: 成功/完成/✅/OK)")
        print("📜 轨迹回放:")
        for ev in tr["events"]:
            print(f"  [{ev['event_type']:>10}] {ev['content'][:36]}  (tokens={ev['tokens']}, {ev['latency_ms']:.0f}ms)")
        print("\n" + report["summary"]["cost_audit"])
    except Exception as e:
        print("⚠️ 真实引擎联动自测跳过 (若未配置 API Key 属正常):", e)
