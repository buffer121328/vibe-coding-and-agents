"""13 HITL 进阶：interrupt() 动态中断与 Command 恢复 —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/13_HITL进阶.md
运行：python 13_hitl_interrupt_demo.py   （无需任何 API Key）

工作台入口：build_graph() 返回编译后的图（每次调用全新 Checkpointer，防串台），
供 ../workbench 直接 import 复用。

小额（≤ 100000）只走组长审批；大额再加老板一关。
注意：interrupt() 发生时节点还没有 return，log 要等整个 transfer 跑完才写回 State。
"""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command


class State(TypedDict):
    amount: int
    log: list


def transfer(state: State):
    """多级审批：先组长，大额再老板。interrupt() 抛出的是待审批数据包。"""
    log = list(state["log"])
    amount = state["amount"]

    ok1 = interrupt({
        "level": "组长审批",
        "amount": amount,
        "action": f"向供应商账户转账 ￥{amount}",
        "hint": "金额 ≤ 100000 时组长通过即可落地",
    })
    log.append(f"组长审批 -> {'通过' if ok1['approved'] else '驳回'}")
    if not ok1["approved"]:
        return {"log": log + [f"流程终止：组长驳回 ￥{amount} 转账"]}

    if amount > 100000:
        ok2 = interrupt({
            "level": "老板审批",
            "amount": amount,
            "action": f"大额转账 ￥{amount}，需第二人确认",
            "hint": "等待期间不要在 interrupt() 之前执行真正的扣款",
        })
        log.append(f"老板审批 -> {'通过' if ok2['approved'] else '驳回'}")
        if not ok2["approved"]:
            return {"log": log + [f"流程终止：老板驳回 ￥{amount} 转账"]}

    log.append(f"已转账 ￥{amount}（幂等键 demo-transfer-{amount}）")
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
    print("== 场景一：小额转账，组长通过即完成 ==")
    g1 = build_graph()
    config1 = {"configurable": {"thread_id": "case-1"}}
    result = g1.invoke({"amount": 5000, "log": []}, config1)
    print("第一次运行（挂起）：", result["__interrupt__"][0].value)
    result = g1.invoke(Command(resume={"approved": True}), config1)
    print("恢复后：", result["log"])

    print("\n== 场景二：大额转账，组长通过后老板驳回 ==")
    g2 = build_graph()
    config2 = {"configurable": {"thread_id": "case-2"}}
    result = g2.invoke({"amount": 200000, "log": []}, config2)
    print("第一次挂起：", result["__interrupt__"][0].value)
    result = g2.invoke(Command(resume={"approved": True}), config2)
    print("第二次挂起：", result["__interrupt__"][0].value)
    result = g2.invoke(Command(resume={"approved": False}), config2)
    print("最终：", result["log"])


if __name__ == "__main__":
    main()
