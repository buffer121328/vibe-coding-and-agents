"""13 HITL 进阶：interrupt() 动态中断与 Command 恢复 —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/13_HITL进阶.md
运行：python 13_hitl_interrupt_demo.py   （无需任何 API Key）

工作台入口：build_graph() 返回编译后的图（每次调用全新 Checkpointer，防串台），
供 ../workbench 直接 import 复用。
"""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command


class State(TypedDict):
    amount: int
    log: list


def transfer(state: State):
    """多级审批：先组长，大额再老板。interrupt() 抛出的是“待审批数据包”"""
    log = list(state["log"])
    amount = state["amount"]

    ok1 = interrupt({"level": "组长审批", "amount": amount})
    log.append(f"组长审批 -> {'通过' if ok1['approved'] else '驳回'}")
    if not ok1["approved"]:
        return {"log": log + ["流程终止"]}

    if amount > 100000:
        ok2 = interrupt({"level": "老板审批", "amount": amount})
        log.append(f"老板审批 -> {'通过' if ok2['approved'] else '驳回'}")
        if not ok2["approved"]:
            return {"log": log + ["流程终止"]}

    log.append(f"已转账 {amount} 元")
    return {"log": log}


def build_graph():
    """装配并编译本节演示图（interrupt 必须挂 Checkpointer）"""
    builder = StateGraph(State)
    builder.add_node("transfer", transfer)
    builder.add_edge(START, "transfer")
    builder.add_edge("transfer", END)
    return builder.compile(checkpointer=MemorySaver())


graph = build_graph()


def main():
    # ---------- 场景一：小额转账，组长通过即完成 ----------
    g1 = build_graph()
    config1 = {"configurable": {"thread_id": "case-1"}}
    result = g1.invoke({"amount": 5000, "log": []}, config1)
    print("== 场景一：小额 ==")
    print("第一次运行（挂起，interrupt 抛出的数据包）：", result["__interrupt__"][0].value)
    result = g1.invoke(Command(resume={"approved": True}), config1)   # resume 的值成为 interrupt() 的返回值
    print("恢复后：", result["log"])

    # ---------- 场景二：大额转账，组长通过后还需老板审批 ----------
    g2 = build_graph()
    config2 = {"configurable": {"thread_id": "case-2"}}
    result = g2.invoke({"amount": 200000, "log": []}, config2)
    print("\n== 场景二：大额多级审批 ==")
    print("第一次挂起：", result["__interrupt__"][0].value)
    result = g2.invoke(Command(resume={"approved": True}), config2)   # 组长通过
    print("第二次挂起：", result["__interrupt__"][0].value)              # 老板环节
    result = g2.invoke(Command(resume={"approved": False}), config2)  # 老板驳回
    print("最终：", result["log"])


if __name__ == "__main__":
    main()
