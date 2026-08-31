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


def reset_flaky():
    """重置 flaky 计数器（工作台每次运行前调用，防串台）"""
    flaky_attempts["n"] = 0


def flaky_api(state: State):
    """前两次调用抛超时，第三次成功——模拟不稳定的第三方接口"""
    flaky_attempts["n"] += 1
    print(f"    flaky_api 第 {flaky_attempts['n']} 次被调用")
    if flaky_attempts["n"] < 3:
        raise TimeoutError("模拟接口超时")
    return {"steps": ["flaky_api 成功"]}


def build_retry_graph():
    """演示一：RetryPolicy 重试图（命令行与工作台共用）"""
    builder = StateGraph(State)
    builder.add_node(
        "flaky_api", flaky_api,
        retry_policy=RetryPolicy(
            max_attempts=3,              # 最多试 3 次（含第一次）
            initial_interval=0.1,        # 演示用短间隔
            backoff_factor=2.0,          # 指数退避
            retry_on=(TimeoutError,),    # 只对超时重试
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
    print("    step_1 执行")
    return {"steps": state["steps"] + ["step_1"]}


def boom(state: State):
    """第一次运行在这里崩掉；恢复后引爆开关已被拆除，顺利通过"""
    if boom_flag["armed"]:
        raise RuntimeError("模拟进程崩溃！")
    print("    boom 执行（这次没崩）")
    return {"steps": state["steps"] + ["boom"]}


def build_rescue_graph():
    """演示二：断点恢复图（每次调用全新 MemorySaver，命令行与工作台共用）"""
    builder2 = StateGraph(State)
    builder2.add_node("step_1", step_1)
    builder2.add_node("boom", boom)
    builder2.add_edge(START, "step_1")
    builder2.add_edge("step_1", "boom")
    builder2.add_edge("boom", END)
    return builder2.compile(checkpointer=MemorySaver())   # 生产换 SqliteSaver/PostgresSaver


def main():
    print("== 演示一：RetryPolicy ==")
    print(build_retry_graph().invoke({"steps": [], "done": False}))
    print(f"（接口共被调用了 {flaky_attempts['n']} 次，前两次的报错被自动消化）")

    config = {"configurable": {"thread_id": "job-1001"}}
    print("\n== 演示二：断点恢复 ==")
    rescue_graph = build_rescue_graph()
    try:
        rescue_graph.invoke({"steps": [], "done": False}, config)
    except RuntimeError as e:
        print("程序崩溃：", e)

    # 程序恢复后：同一 thread_id 再次 invoke，从最近快照继续，已完成的 step_1 不会重跑
    disarm_boom()
    rescue_graph.invoke(None, config)
    print("恢复后的最终状态：", rescue_graph.get_state(config).values["steps"])
    print("（注意输出：step_1 没有被重新执行）")


if __name__ == "__main__":
    main()
