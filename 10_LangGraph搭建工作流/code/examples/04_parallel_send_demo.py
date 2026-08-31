"""04 并行执行与 Send 动态分发 —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/04_并行执行与Send动态分发.md
运行：python 04_parallel_send_demo.py   （无需任何 API Key）

工作台入口：build_graph() 返回编译后的图，供 ../workbench 直接 import 复用。
"""
import operator
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send


class State(TypedDict):
    user_input: str
    cities: list                            # 规划节点算出的任务清单
    quotes: Annotated[list, operator.add]   # 用加法 reducer 合并各城市报价
    final_answer: str


# ---- 两个模拟依赖：真实项目中分别换成 LLM 抽取与航司查询 API ----
def parse_cities(user_input: str) -> list[str]:
    """极简版城市解析：词典匹配演示用。真实项目用 with_structured_output 抽取更稳"""
    known_cities = ["北京", "上海", "广州", "深圳", "杭州", "成都"]
    return [c for c in known_cities if c in user_input]


def query_flight_api(city: str, date: str) -> int:
    """模拟航司报价接口：返回一个编造的价格"""
    return 600 + 120 * (len(city.encode()) % 5)


def plan(state: State):
    """规划节点（Map）：解析城市写进状态"""
    return {"cities": parse_cities(state["user_input"])}


def fan_out(state: State):
    """Send 路由函数（不是节点！）：按城市数量动态派发 N 个并行实例"""
    return [Send("search_one_city", {"city": c}) for c in state["cities"]]


def search_one_city(state: dict):
    city = state["city"]                     # 每个实例只看到自己的私有状态
    quote = query_flight_api(city, "2026-09-01")
    return {"quotes": [{"city": city, "price": quote}]}


def aggregate(state: State):
    cheapest = min(state["quotes"], key=lambda q: q["price"])
    return {"final_answer": f"最低价是 {cheapest['city']}，仅需 {cheapest['price']} 元"}


def build_graph():
    """装配并编译本节演示图（命令行与工作台共用同一份）"""
    builder = StateGraph(State)
    builder.add_node("plan", plan)
    builder.add_node("search_one_city", search_one_city)
    builder.add_node("aggregate", aggregate)
    builder.add_edge(START, "plan")
    builder.add_conditional_edges("plan", fan_out)       # 动态分发
    builder.add_edge("search_one_city", "aggregate")     # 隐式屏障：等所有实例完成
    builder.add_edge("aggregate", END)
    return builder.compile()


graph = build_graph()


def main():
    result = graph.invoke({"user_input": "帮我同时查一下北京、上海和成都的机票"})
    print(result["final_answer"])


if __name__ == "__main__":
    main()
