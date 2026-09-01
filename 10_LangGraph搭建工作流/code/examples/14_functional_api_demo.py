"""14 Functional API：@entrypoint 与 @task —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/14_FunctionalAPI与两套API选型.md
运行：python 14_functional_api_demo.py   （无需任何 API Key）

给普通 Python 函数加持久化与 HITL：不画图，只用两个装饰器。

工作台入口：build_flow() 返回装配好的 entrypoint 函数（每次调用全新
Checkpointer，防串台），供 ../workbench 直接 import 复用。
"""
import time

from langgraph.func import entrypoint, task
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command


@task
def translate_topic(topic: str) -> str:
    """互不依赖的工序 A：模拟翻译。"""
    time.sleep(0.05)
    return f"{topic}（English brief）"


@task
def summarize_topic(topic: str) -> str:
    """互不依赖的工序 B：模拟摘要。"""
    time.sleep(0.05)
    return f"{topic}的三句话摘要"


@task
def write_essay(topic: str, materials: list[str]) -> str:
    """工序一：写初稿（每道工序的执行结果自动存档）"""
    return f"""# 《{topic}》

## 为什么需要讨论这个问题

机器人已经从实验室走进客服、仓储、医疗辅助和家庭设备。能力越强，出错时影响的人也越多。因此，安全不能等产品上线后再补，而要从需求、数据、工具权限到上线监控一路设计进去。

## 三道安全护栏

第一道是**权限边界**：机器人只能调用完成任务所需的工具，高风险动作必须经过人工确认。第二道是**过程可追踪**：每个节点读了什么状态、写了什么结果、为何走向下一条边，都应留下记录。第三道是**失败可恢复**：外部接口超时可以重试，流程崩溃可以从检查点继续，不能让一次故障把整条任务链推倒重来。

## 人应该站在哪里

LangGraph 的 `interrupt()` 适合把人放在真正关键的位置，例如付款、删除数据和发布内容。机器先准备材料，人只做需要判断的决定；批准后用 `Command(resume=...)` 续跑，驳回时把原因送回流程修改。

## 结语

安全的机器人系统不是“永远不犯错”，而是知道哪些事不能擅自做，出错后能解释、能停下、也能恢复。把状态、节点、边和人工审批都画清楚，团队才有机会在事故发生前发现问题。

---

**并行准备材料**：{'；'.join(materials)}"""


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
        # 先创建两个 future，再统一取结果：两个 task 会并行执行。
        # 如果在每一行末尾立刻 `.result()`，第二个 task 要等第一个结束，那仍是串行。
        translation_future = translate_topic(topic)
        summary_future = summarize_topic(topic)
        materials = [translation_future.result(), summary_future.result()]
        draft = write_essay(topic, materials).result()
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
