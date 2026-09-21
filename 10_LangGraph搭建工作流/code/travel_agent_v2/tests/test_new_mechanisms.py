"""新机制冒烟测试：用 langchain-core 内置假模型驱动 travel_agent_v2（无需 API Key）。

运行：uv run python tests/test_new_mechanisms.py  （在 travel_agent_v2 目录内执行）

验证三件事：
1. 租车真子图：委派 -> 安全工具 -> 敏感工具前被子图 interrupt 拦截 -> 恢复 -> 弹栈回主助理
2. Store 长期记忆：recall_preferences 工具通过 InjectedStore 注入，能读到预置偏好
3. 多业务并行比价子图：Send 扇出四路查询 -> aggregate 汇总 -> 弹栈回主助理
"""
import sys

sys.path.insert(0, ".")

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langgraph.types import Command

import infra.llm as llm_cfg
from infra.biz_db import update_dates


def tc(name, args, id_):
    return {"name": name, "args": args, "id": id_, "type": "tool_call"}


class Fake(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self  # 主助理在 import 时会调用 bind_tools


llm_cfg.llm = Fake(responses=[
    # ---- 场景一：租车（真子图 + 子图内 interrupt）----
    AIMessage(content="", tool_calls=[tc("ToBookCarRental", {
        "location": "成都", "start_date": "2026-10-01", "end_date": "2026-10-03",
        "request": "SUV"}, "call_1")]),
    AIMessage(content="", tool_calls=[tc("search_car_rentals", {"location": "成都"}, "call_2")]),
    AIMessage(content="", tool_calls=[tc("book_car_rental", {"rental_id": 1}, "call_3")]),  # 敏感
    AIMessage(content="", tool_calls=[tc("CompleteOrEscalate", {"cancel": True, "reason": "任务完成"}, "call_4")]),
    AIMessage(content="您的租车已订好，还有什么可以帮您？"),
    # ---- 场景二：Store 偏好回忆 ----
    AIMessage(content="", tool_calls=[tc("recall_preferences", {}, "call_5")]),
    AIMessage(content="我记得您喜欢靠窗的座位。"),
    # ---- 场景三：多业务并行比价（Send）----
    AIMessage(content="", tool_calls=[tc("ToMultiQuote", {"request": "全部比价"}, "call_6")]),
    AIMessage(content="四类行情已汇总，需要深入了解哪一类？"),
])

from main import build_graph  # noqa: E402  (必须在打补丁后导入，主助理才会绑到假模型)

update_dates()
graph = build_graph()


def config_for(thread_id):
    return {"configurable": {"passenger_id": "3442 587242", "thread_id": thread_id}}


def last_text(state):
    return state["messages"][-1].content


print("\n========== 场景一：租车真子图（子图内 interrupt） ==========")
cfg1 = config_for("t-car")
result = graph.invoke({"messages": [("user", "帮我在成都订一辆SUV")]}, cfg1)
snap = graph.get_state(cfg1)
print("第一次运行后停在：", snap.next)
# 子图快照：用父图 task 携带的子图 checkpoint config 再取一次 state
child_state = graph.get_state(snap.tasks[0].state)
print("子图内部的待执行节点：", child_state.next)
assert snap.next == ("book_car_rental",), "父图未停在租车子图！"
assert child_state.next == ("book_car_rental_approval",), "子图内的动态审批节点未生效！"
assert child_state.tasks[0].interrupts, "审批节点没有抛出 interrupt 数据包！"
payload = child_state.tasks[0].interrupts[0].value
assert payload["kind"] == "tool_approval"
assert payload["tool_calls"][0]["name"] == "book_car_rental"

result = graph.invoke(Command(resume={"approved": True}), cfg1)  # 批准后才执行敏感工具
snap = graph.get_state(cfg1)
print("恢复后走完，最后回复：", last_text(snap.values))
assert "租车已订好" in last_text(snap.values)
assert not snap.next and not snap.tasks, "恢复后仍有未完成任务"

print("\n========== 场景二：Store 偏好回忆（InjectedStore） ==========")
cfg2 = config_for("t-store")
result = graph.invoke({"messages": [("user", "还记得我的偏好吗？")]}, cfg2)
tool_msgs = [m.content for m in result["messages"] if m.__class__.__name__ == "ToolMessage"]
print("工具回执：", tool_msgs)
assert any("seat_preference" in t and "靠窗" in t for t in tool_msgs), "Store 注入/读取失败！"
assert "靠窗" in last_text(result)

print("\n========== 场景三：多业务并行比价（Send） ==========")
cfg3 = config_for("t-quote")
result = graph.invoke({"messages": [("user", "帮我看看全部行情")]}, cfg3)
tool_msgs = [m.content for m in result["messages"] if m.__class__.__name__ == "ToolMessage"]
summary = [m.content for m in result["messages"]
           if m.__class__.__name__ == "AIMessage" and "已同时查完四类行情" in str(m.content)]
print("汇总消息：", summary)
assert summary, "并行比价汇总消息未生成！"
assert not graph.get_state(cfg3).next

print("\n✅ 三个新机制全部端到端验证通过")
