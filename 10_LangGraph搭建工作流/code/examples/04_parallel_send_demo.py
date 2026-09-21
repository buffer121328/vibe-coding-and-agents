"""04 并行执行与 Send 动态分发 —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/04_并行执行与Send动态分发.md
运行：python 04_parallel_send_demo.py   （无需任何 API Key）

工作台入口：build_graph() 返回编译后的图，供 ../workbench 直接 import 复用。

演示闭环：plan 写出城市清单 → 条件边返回 Send 列表 → 每座城市一个私有实例
→ quotes 经 operator.add 拼接 → aggregate 等全部完成后给出最低价。
"""
import operator
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send


class State(TypedDict):
    user_input: str
    cities: list                            # 规划节点算出的任务清单
    quotes: Annotated[list, operator.add]   # 各城市报价，并行写入时靠 reducer 拼接
    final_answer: str


# 模拟航司报价表。真实项目换成接口返回；这里把数字写死，方便对照 reducer 合并结果。
FLIGHT_QUOTES = {
    "北京": {"flight": "CA-1501", "price": 720, "depart": "08:15"},
    "上海": {"flight": "MU-5137", "price": 880, "depart": "09:40"},
    "广州": {"flight": "CZ-3102", "price": 640, "depart": "07:55"},
    "深圳": {"flight": "ZH-9881", "price": 710, "depart": "11:20"},
    "杭州": {"flight": "JD-5156", "price": 690, "depart": "13:05"},
    "成都": {"flight": "3U-8692", "price": 760, "depart": "10:30"},
}


def parse_cities(user_input: str) -> list[str]:
    """词典匹配演示用。真实项目用 with_structured_output 抽取城市列表更稳。"""
    known_cities = list(FLIGHT_QUOTES)
    found = [c for c in known_cities if c in user_input]
    # 去重但保持出现顺序，避免同一城市被派两路。
    seen: set[str] = set()
    ordered = []
    for city in found:
        if city not in seen:
            seen.add(city)
            ordered.append(city)
    return ordered


def query_flight_api(city: str, date: str) -> dict:
    """模拟航司查询。查不到的城市给一个明显偏高的兜底价，避免 aggregate 因空列表崩溃。"""
    row = FLIGHT_QUOTES.get(city, {"flight": "N/A", "price": 9999, "depart": "--"})
    return {"city": city, "date": date, **row}


def plan(state: State):
    """规划节点（Map）：只负责拆任务，把城市清单写进 State。"""
    cities = parse_cities(state["user_input"])
    print(f">>> plan 解析出 {len(cities)} 座城市：{cities}")
    return {"cities": cities}


def fan_out(state: State):
    """Send 路由函数（不是节点！）：按城市数量动态派发 N 个并行实例。"""
    return [Send("search_one_city", {"city": city, "date": "2026-09-01"}) for city in state["cities"]]


def search_one_city(state: dict):
    """每个 Send 实例只看到自己的 city / date，互不干扰。"""
    quote = query_flight_api(state["city"], state.get("date", "2026-09-01"))
    print(f">>> search_one_city({quote['city']}) -> {quote['flight']} ￥{quote['price']}")
    return {"quotes": [quote]}


def aggregate(state: State):
    """隐式屏障：所有 search_one_city 实例完成后才会进入这里。"""
    if not state["quotes"]:
        return {"final_answer": "没有解析到任何城市，无法比价。"}
    cheapest = min(state["quotes"], key=lambda q: q["price"])
    lines = [f"{q['city']} {q['flight']} ￥{q['price']}" for q in state["quotes"]]
    return {
        "final_answer": (
            "比价结果：" + "；".join(lines)
            + f"。最低价是 {cheapest['city']} {cheapest['flight']}，￥{cheapest['price']}。"
        )
    }


def build_graph():
    """装配并编译本节演示图（命令行与工作台共用同一份）"""
    builder = StateGraph(State)
    builder.add_node("plan", plan)
    builder.add_node("search_one_city", search_one_city)
    builder.add_node("aggregate", aggregate)
    builder.add_edge(START, "plan")
    builder.add_conditional_edges("plan", fan_out)
    builder.add_edge("search_one_city", "aggregate")
    builder.add_edge("aggregate", END)
    return builder.compile()


graph = build_graph()


def main():
    result = graph.invoke({"user_input": "帮我同时查一下北京、上海和成都的机票"})
    print("\n最终回答：", result["final_answer"])
    print("quotes 字段（reducer 合并后）：")
    for row in result["quotes"]:
        print("  ", row)


if __name__ == "__main__":
    main()
