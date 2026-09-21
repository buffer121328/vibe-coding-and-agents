"""10 长期记忆与 Time Travel —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/10_长期记忆与TimeTravel.md
运行：python 10_memory_timetravel_demo.py   （无需任何 API Key）

演示 Store 跨线程长期记忆 + get_state_history / update_state 回放与改道。

工作台入口：build_assistant_graph() / build_tt_graph() 返回编译后的图，
供 ../workbench 直接 import 复用；Store 与 Checkpointer 在工厂内创建，防串台。
"""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import MemorySaver


class State(TypedDict):
    user_id: str
    reply: str


def make_assistant_graph(store: InMemoryStore | None = None):
    """演示一：Store 长期记忆图（工厂可注入外部 Store，缺省自建）"""
    store = store or InMemoryStore()

    def assistant(state: State, *, store: BaseStore):
        """节点多收一个 store 参数即可访问长期记忆（编译时传入 store）。"""
        profile = store.search((state["user_id"],))
        if not profile:
            return {"reply": "档案是空的。你可以先记下过敏原或座位偏好。"}
        prefs = "；".join(f"{item.key}={item.value}" for item in profile)
        return {"reply": f"跨会话读到的会员档案：{prefs}"}

    builder = StateGraph(State)
    builder.add_node("assistant", assistant)
    builder.add_edge(START, "assistant")
    builder.add_edge("assistant", END)
    return builder.compile(store=store, checkpointer=MemorySaver()), store


def build_assistant_graph():
    """工作台入口：全新 Store + 编译图（命令行 main() 用种子档案预填）"""
    return make_assistant_graph()[0]


def seed_store(store: InMemoryStore):
    """预填演示档案：namespace 是抽屉，key 是卡片编号。"""
    store.put(("user_123",), "allergy", {"food": "花生", "note": "过敏性休克风险，餐食必须标明"})
    store.put(("user_123",), "preference", {"seat": "靠窗", "meal": "素食"})
    store.put(("user_123",), "recent_trip", {"city": "大阪", "date": "2026-08-12"})


# ============ 演示二：Time Travel 回放与改道 ============
class SimpleState(TypedDict, total=False):
    text: str
    step_b_runs: int


_STEP_B_COUNTER = {"count": 0}


def step_a(state: SimpleState):
    return {"text": state["text"] + " -> A"}


def step_b(state: SimpleState):
    # 用计数器模拟“每次调用结果都可能不同”的 LLM / 外部 API。
    _STEP_B_COUNTER["count"] += 1
    return {
        "text": state["text"] + " -> B",
        "step_b_runs": _STEP_B_COUNTER["count"],
    }


def reset_step_b_counter():
    _STEP_B_COUNTER["count"] = 0


def build_tt_graph():
    """工作台入口：全新 Checkpointer 的 Time Travel 图，防多次运行串台"""
    return (
        StateGraph(SimpleState)
        .add_node("step_a", step_a)
        .add_node("step_b", step_b)
        .add_edge(START, "step_a")
        .add_edge("step_a", "step_b")
        .add_edge("step_b", END)
        .compile(checkpointer=MemorySaver())
    )


def main():
    print("== Store 长期记忆（换 thread_id 也能翻到同一份档案）==")
    store = InMemoryStore()
    seed_store(store)

    card = store.get(("user_123",), "allergy")
    all_cards = store.search(("user_123",))
    print("精确取 allergy：", card.value)
    print("翻整个抽屉：", [(item.key, item.value) for item in all_cards])

    graph, _ = make_assistant_graph(store)
    print(
        graph.invoke(
            {"user_id": "user_123", "reply": ""},
            config={"configurable": {"thread_id": "brand_new_session"}},
        )["reply"]
    )

    print("\n== Time Travel：回放会让下游节点真的再跑一次 ==")
    reset_step_b_counter()
    tt_graph = build_tt_graph()
    config = {"configurable": {"thread_id": "tt-1"}}
    tt_graph.invoke({"text": "起点"}, config)

    history = list(tt_graph.get_state_history(config))
    print("历史快照数（含起点）：", len(history))

    replay_config = next(s.config for s in history if s.values.get("text", "").endswith("-> A"))
    replayed = tt_graph.invoke(None, replay_config)
    print("回放后 step_b 的执行次数：", replayed["step_b_runs"], "（第一次是 1，回放后应变成 2）")

    fork_config = next(s.config for s in history if s.values.get("text", "").endswith("-> A"))
    new_config = tt_graph.update_state(
        fork_config,
        {"text": "起点 -> A（被人类改写）"},
        as_node="step_a",
    )
    new_result = tt_graph.invoke(None, new_config)
    print("改道后的新历史：", new_result["text"])


if __name__ == "__main__":
    main()
