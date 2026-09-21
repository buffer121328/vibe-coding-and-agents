"""11 持久执行与容错 —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/11_持久执行与容错.md
运行：python 11_durable_execution_demo.py   （无需任何 API Key）

演示 RetryPolicy 自动重试 + Checkpointer 断点恢复（崩溃复活）。

工作台入口：build_retry_graph() / build_rescue_graph() 返回编译后的图；
flaky 计数与 boom 引爆开关由模块级函数 reset/reset_boom 管理，防多次运行串台。
"""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import RetryPolicy


class State(TypedDict):
    steps: list
    done: bool


# ---------- 演示一：RetryPolicy 自动重试（瞬时故障自愈） ----------
flaky_attempts = {"n": 0}
flaky_trace = []


def reset_flaky():
    """重置 flaky 计数器（工作台每次运行前调用，防串台）"""
    flaky_attempts["n"] = 0
    flaky_trace.clear()


def flaky_api(state: State):
    """模拟不稳定的航司查询接口：前两次超时，第三次成功。"""
    flaky_attempts["n"] += 1
    attempt = flaky_attempts["n"]
    flaky_trace.append({"attempt": attempt, "result": "调用 query_flight_api"})
    print(f"    flaky_api 第 {attempt} 次被调用")
    if attempt < 3:
        flaky_trace[-1]["result"] = f"第 {attempt} 次 TimeoutError，交给 RetryPolicy"
        raise TimeoutError(f"模拟接口超时（第 {attempt} 次）")
    flaky_trace[-1]["result"] = "第 3 次成功，返回 CA-1801 ￥1280"
    return {"steps": ["flaky_api 成功：CA-1801 ￥1280"], "done": True}


def build_retry_graph():
    """演示一：RetryPolicy 重试图（命令行与工作台共用）"""
    builder = StateGraph(State)
    builder.add_node(
        "flaky_api",
        flaky_api,
        retry_policy=RetryPolicy(
            max_attempts=3,
            initial_interval=0.1,
            backoff_factor=2.0,
            retry_on=(TimeoutError,),
        ),
    )
    builder.add_edge(START, "flaky_api")
    builder.add_edge("flaky_api", END)
    return builder.compile()


# ---------- 演示二：断点恢复（崩了从最近快照复活） ----------
boom_flag = {"armed": True}


def reset_boom():
    """重新装上引爆开关（工作台每次运行前调用，防串台）"""
    boom_flag["armed"] = True


def disarm_boom():
    """拆除引爆开关（模拟修复完成后的恢复运行）"""
    boom_flag["armed"] = False


def step_1(state: State):
    print("    step_1 执行：写入订单草稿 order_1001")
    return {"steps": state["steps"] + ["step_1 已写入订单草稿 order_1001"]}


def boom(state: State):
    """第一次运行在这里崩掉；恢复后引爆开关已被拆除，顺利通过。"""
    if boom_flag["armed"]:
        raise RuntimeError("模拟进程崩溃：支付网关超时，订单草稿已在 step_1 落盘")
    print("    boom 执行（这次没崩）：支付成功")
    return {"steps": state["steps"] + ["boom 支付成功"], "done": True}


def build_rescue_graph():
    """演示二：断点恢复图（每次调用全新 MemorySaver，命令行与工作台共用）"""
    builder2 = StateGraph(State)
    builder2.add_node("step_1", step_1)
    builder2.add_node("boom", boom)
    builder2.add_edge(START, "step_1")
    builder2.add_edge("step_1", "boom")
    builder2.add_edge("boom", END)
    return builder2.compile(checkpointer=MemorySaver())


def main():
    reset_flaky()
    print("== 演示一：RetryPolicy ==")
    print(build_retry_graph().invoke({"steps": [], "done": False}))
    print(f"（接口共被调用了 {flaky_attempts['n']} 次，前两次超时被自动消化）")
    print("调用轨迹：", flaky_trace)

    config = {"configurable": {"thread_id": "job-1001"}}
    print("\n== 演示二：断点恢复 ==")
    rescue_graph = build_rescue_graph()
    try:
        rescue_graph.invoke({"steps": [], "done": False}, config)
    except RuntimeError as exc:
        print("程序崩溃：", exc)
        print("崩溃时已保存的 steps：", rescue_graph.get_state(config).values["steps"])

    disarm_boom()
    rescue_graph.invoke(None, config)
    print("恢复后的最终状态：", rescue_graph.get_state(config).values["steps"])
    print("（注意：step_1 没有被重新执行，只重跑了 boom）")


if __name__ == "__main__":
    main()
