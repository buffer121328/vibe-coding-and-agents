"""14 Functional API：@entrypoint 与 @task —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/14_FunctionalAPI与两套API选型.md
运行：python 14_functional_api_demo.py   （无需任何 API Key）

给普通 Python 函数加持久化与 HITL：不画图，只用两个装饰器。

工作台入口：build_flow() 返回装配好的 entrypoint 函数（每次调用全新
Checkpointer，防串台），供 ../workbench 直接 import 复用。
"""
from langgraph.func import entrypoint, task
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command


@task
def write_essay(topic: str) -> str:
    """工序一：写初稿（每道工序的执行结果自动存档）"""
    return f"《{topic}》初稿：机器人应当……"


@task
def review(essay: str) -> str:
    """工序二：人工审阅——复用 13 节的 interrupt()"""
    decision = interrupt({"essay": essay, "ask": "这篇可以发布吗？"})
    return essay if decision["approved"] else f"需修改：{decision['reason']}"


def build_flow():
    """装配 entrypoint 流程（每次调用全新 Checkpointer，命令行与工作台共用）"""

    @entrypoint(checkpointer=MemorySaver())
    def essay_flow(topic: str) -> str:
        """总入口：普通 Python 控制流（if/for 随便用），持久化由框架接管"""
        draft = write_essay(topic).result()   # @task 返回 future，.result() 取值
        final = review(draft).result()
        return final

    return essay_flow


flow = build_flow()


def main():
    config = {"configurable": {"thread_id": "user-42"}}

    # 第一次运行：执行到 review 的 interrupt() 处挂起
    result = flow.invoke("机器人安全", config)
    print("第一次运行（挂起，待审批数据包）：", result["__interrupt__"][0].value)

    # 人工批准后恢复
    final = flow.invoke(Command(resume={"approved": True}), config)
    print("恢复后的最终产出：", final)


if __name__ == "__main__":
    main()
