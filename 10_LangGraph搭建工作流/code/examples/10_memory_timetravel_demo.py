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
        """节点多收一个 store 参数即可访问长期记忆（编译时传入 store）"""
        profile = store.search((state["user_id"],))
        prefs = "；".join(f"{i.key}={i.value}" for i in profile)
        return {"reply": f"我记得你的偏好：{prefs or '（暂无档案）'}"}

    builder = StateGraph(State)
    builder.add_node("assistant", assistant)
    builder.add_edge(START, "assistant")
    builder.add_edge("assistant", END)
    return builder.compile(store=store, checkpointer=MemorySaver()), store


def build_assistant_graph():
    """工作台入口：全新 Store + 编译图（命令行 main() 用种子档案预填）"""
    return make_assistant_graph()[0]


def seed_store(store: InMemoryStore):
    """预填演示档案：namespace 相当于抽屉，key 是卡片编号（真实项目由模型决定写入）"""
    store.put(("user_123",), "allergy", {"food": "花生"})
    store.put(("user_123",), "preference", {"seat": "靠窗"})


# ============ 演示二：Time Travel 回放与改道 ============
class SimpleState(TypedDict):
    text: str


def step_a(state: SimpleState):
    return {"text": state["text"] + " -> A"}


def step_b(state: SimpleState):
    return {"text": state["text"] + " -> B"}


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
    # ============ 演示一：Store 长期记忆（跨线程的“会员档案”） ============
    store = InMemoryStore()
    seed_store(store)

    # 取 / 搜：换个会话（新 thread_id）也能翻到这份档案
    card = store.get(("user_123",), "allergy")
    all_cards = store.search(("user_123",))
    print("== Store 长期记忆 ==")
    print("精确取卡片：", card.value)
    print("翻整个抽屉：", [(i.key, i.value) for i in all_cards])

    graph, _ = make_assistant_graph(store)

    print("\n换一个全新会话（新 thread_id），档案依然在：")
    print(graph.invoke({"user_id": "user_123", "reply": ""},
                       config={"configurable": {"thread_id": "brand_new_session"}})["reply"])

    # ============ 演示二：Time Travel 回放与改道 ============
    tt_graph = build_tt_graph()
    config = {"configurable": {"thread_id": "tt-1"}}
    tt_graph.invoke({"text": "起点"}, config)

    print("\n== Time Travel ==")
    history = list(tt_graph.get_state_history(config))
    print("历史快照数（含起点）：", len(history))

    # 改道（Fork）：回到 step_a 之后那一刻，替换 text，长出一条新历史
    fork_config = next(s.config for s in history if s.values.get("text", "").endswith("-> A"))
    tt_graph.update_state(fork_config, {"text": "起点 -> A（被人类改写）"}, as_node="step_a")
    new_result = tt_graph.invoke(None, fork_config)   # 从改写后的快照继续
    print("改道后的新历史：", new_result["text"])


if __name__ == "__main__":
    main()
