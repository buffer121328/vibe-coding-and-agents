"""图工作台冒烟测试：无 API Key，逐关调用 app.py 的核心运行逻辑。

运行：.venv/bin/python smoke_test.py   （在 workbench 目录内执行）

GUI 组件（gradio）无法脱离浏览器断言，本测试聚焦每关回调背后的「真图运行」：
导入 app 模块后直接复用其运行函数 / 示例工厂，断言点亮徽章、State 快照、终端文本
的关键内容，保证「课本示例在工作台里真实跑通」。
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import os
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
os.environ["WORKBENCH_ANIMATION_DELAY"] = "0"

import app  # noqa: E402  （导入即装配 Blocks，但不 launch）

ok_count = 0
fail_count = 0


def check(name, fn):
    global ok_count, fail_count
    try:
        fn()
        ok_count += 1
        print(f"✅ {name}")
    except AssertionError as e:
        fail_count += 1
        print(f"❌ {name}: {e}")
    except Exception as e:
        fail_count += 1
        print(f"❌ {name}（异常）: {type(e).__name__}: {e}")


def run_all(gen, n_expected_last=1):
    """消费一个生成器到 yield 尽头，返回最后一次的输出 tuple"""
    last = None
    n = 0
    for out in gen:
        last = out
        n += 1
    assert last is not None, "生成器没有产出任何输出"
    return last, n


def chips_done(html: str) -> set:
    """从徽章 HTML 中解析已点亮（done/cur）的节点集合，忽略 START/END 边界标记。"""
    import re
    return {n for n in re.findall(r'class="chip (?:done|cur)">(?:✓|●) ([^<]+)</span>', html)
            if n not in {"START", "END"}}


def main():
    # ---------- 10.2 ----------
    def t02():
        frames = list(app.t02_run("你好，今天天气怎么样？"))
        assert any("START" in frame[0] and "正在执行" in frame[0] for frame in frames), "缺少 START 入口帧"
        assert any("END" in frame[0] and "状态已更新" in frame[0] for frame in frames), "缺少 END 出口帧"
        assert any("State 摘要" in frame[0] for frame in frames), "图下方缺少 State 摘要"
        assert any("状态速览" in frame[3] for frame in frames), "终端缺少状态速览摘要"
        chips, svg, snap, console = frames[-1]
        assert chips_done(chips) == {"greeter", "echo"}, f"点亮不全：{chips_done(chips)}"
        assert "greeter" in svg and "data-lit" in svg, "SVG 未注入点亮标记"
        assert chips.count('class="mstate"') >= 3, "状态机透视缺 State 徽标（每节点一枚）"
        assert "读取 State" not in chips, "结束帧不应再有「读取 State」徽标"
        snap_obj = json.loads(snap)
        assert any("打招呼节点" in str(m) for m in snap_obj["messages"]), "State 缺 greeter 产物"
        assert "节点 greeter 完成" in console, "终端缺 greeter 记录"
    check("10.2 State 图：运行 + 点亮 + 快照", t02)

    # ---------- 10.3 ----------
    def t03():
        (chips, svg, snap, console), _ = run_all(app.t03_run("帮我把这段话翻译成英文"))
        done = chips_done(chips)
        assert "translate_node" in done and "summarize_node" not in done, f"路由点错支路：{done}"
        assert json.loads(snap)["category"] == "translate"
    check("10.3 条件路由：只点亮命中的支路", t03)

    # ---------- 10.4 ----------
    def t04():
        (chips, svg, snap, console), _ = run_all(app.t04_run("帮我同时查一下北京、上海和成都的机票"))
        done = chips_done(chips)
        assert {"plan", "search_one_city", "aggregate"} <= done, f"点亮不全：{done}"
        snap_obj = json.loads(snap)
        assert len(snap_obj["quotes"]) == 3, f"Send 应有 3 路报价：{snap_obj['quotes']}"
        assert "最低价" in snap_obj["final_answer"]
    check("10.4 Send 并行：3 路报价合并", t04)

    # ---------- 10.5 ----------
    def t05u():
        (chips, svg, snap, console), _ = run_all(app.t05_run_updates("LangGraph 是什么"))
        assert chips_done(chips) == {"search", "reply"}
        assert "updates" in console
    check("10.5 流式调试：updates 模式", t05u)

    def t05v():
        (chips, svg, snap, console), _ = run_all(app.t05_run_values("LangGraph 是什么"))
        assert "最终回答" in json.loads(snap)["answer"]
    check("10.5 流式调试：values 模式", t05v)

    # ---------- 10.6（两阶段：拦截 → 批准/驳回） ----------
    def t06():
        outs = list(app.t06_run("帮我清空购物车"))
        chips, svg, snap, console, pending, ok, no = outs[-1]
        assert "propose" in chips_done(chips), "拦截前 propose 应已点亮"
        assert pending["visible"], "挂起审批条未出现"
        assert ok["visible"] and no["visible"], "批准/驳回按钮未出现"
        # 批准后续跑
        outs = list(app.t06_resume())
        chips2, _, snap2, console2, p2, o2, n2 = outs[-1]
        assert "sensitive_tool" in chips_done(chips2)
        assert "已批准" in console2
        # 重新发起一条请求验证正式驳回：sensitive_tool 不应点亮，拒绝回执应进入 State
        list(app.t06_run("帮我清空购物车"))
        chips3, _, snap3, console3, p3, o3, n3 = app.t06_reject()
        assert "sensitive_tool" not in chips_done(chips3)
        assert "update_state" in console3 and "工具调用被用户拒绝" in snap3
    check("10.6 HITL：拦截 → 批准续跑", t06)

    # ---------- 10.7（状态栈） ----------
    def t07():
        (chips, svg, snap, console), _ = run_all(app.t07_run("帮我订一张去东京的机票"))
        snap_obj = json.loads(snap)
        assert snap_obj.get("dialog_state", []) == [], f"栈应弹空：{snap_obj.get('dialog_state')}"
        assert "空栈" in console, "终端应含栈条回空展示"
        assert "航班助理" in console
    check("10.7 状态栈：压栈弹栈回空", t07)

    # ---------- 10.8（ReAct） ----------
    def t08():
        (chips, svg, snap, console), _ = run_all(app.t08_run("帮我查一下去东京的航班"))
        assert "ToolMessage" in console or "工具" in console, f"终端缺工具回执：{console[-200:]}"
        assert "为您查到东京的 3 个航班" in console
    check("10.8 ReAct：工具回执进闭环", t08)

    # ---------- 10.9（三模式） ----------
    def t09a():
        (chips, svg, snap, console), frames = run_all(app.t09a_run("这个东西多少钱？"))
        assert frames >= 6, f"Routing 应逐节点流式展示，实际只有 {frames} 帧"
        assert "pricing" in chips_done(chips)
        assert "99 元" in json.loads(snap)["answer"]
    check("10.9 Routing：价格支路点亮", t09a)

    def t09b():
        (chips, svg, snap, console), _ = run_all(app.t09b_run("英 日 法"))
        assert len(json.loads(snap)["results"]) == 4  # 3 工人 + 1 汇总
    check("10.9 Orchestrator-Worker：3 工人汇聚", t09b)

    def t09c():
        (chips, svg, snap, console), _ = run_all(app.t09c_run())
        snap_obj = json.loads(snap)
        assert snap_obj["revision"] == 2 and snap_obj["score"] == 120, f"保险丝逻辑：{snap_obj}"
    check("10.9 Evaluator-Optimizer：2 版过线", t09c)

    # ---------- 10.10（Store + TimeTravel） ----------
    def t10_store():
        (chips, svg, snap, console), frames = run_all(app.t10_store_demo())
        obj = json.loads(snap)
        assert frames >= 4, "Store assistant 图应展示 START、节点和 END 流转"
        assert "allergy" in obj["长期_Store"][0][0] or any(
            k == "allergy" for k, _ in obj["长期_Store"]), f"抽屉缺卡片：{obj}"
        assert "花生" in obj["短期_State"]["reply"] or "allergy" in obj["短期_State"]["reply"]
    check("10.10 Store：跨会话档案", t10_store)

    def t10_fork():
        chips, svg, snap, console = app.t10_fork()
        obj = json.loads(snap)
        assert "被人类改写" in obj["text"] and obj["text"].endswith("-> B"), f"改道结果：{obj}"
        assert "新历史" in console
    check("10.10 Time Travel：改道长出新历史", t10_fork)

    def t10_replay():
        chips, svg, snap, console = app.t10_replay()
        obj = json.loads(snap)
        assert obj["第一次"]["step_b_runs"] == 1
        assert obj["回放后"]["step_b_runs"] == 2
        assert "B 真实重跑" in console
    check("10.10 Time Travel：Replay 重新执行下游节点", t10_replay)

    # ---------- 10.11（重试 + 崩溃复活） ----------
    def t11():
        (chips, svg, snap, console), retry_frames = run_all(app.t11_retry())
        assert retry_frames >= 5 and "第 3 次成功" in console
        assert len(json.loads(snap)["RetryPolicy 调用轨迹"]) == 3
        (chips, svg, snap, console), boom_frames = run_all(app.t11_boom())
        assert boom_frames >= 3
        assert "崩溃" in console and "step_1" in snap
        (chips, svg, snap, console), rescue_frames = run_all(app.t11_rescue())
        obj = json.loads(snap)
        assert obj["steps"] == ["step_1", "boom"], f"复活结果：{obj}"
        assert "没有被重新执行" in console
    check("10.11 容错：重试自愈 + 断点复活", t11)

    # ---------- 10.12（子图） ----------
    def t12():
        outs = list(app.t12_run())
        chips, svg, snap, console = outs[-1]
        obj = json.loads(snap)
        assert obj["ticket"] == "CA-1801", f"共享键透传失败：{obj.get('ticket')}"
        assert "xray=True（透视）" in console
    check("10.12 子图：共享键透传 + xray", t12)

    # ---------- 10.12b（当前分类下的三种重点实现） ----------
    def t12b_router():
        (chips, svg, snap, console), frames = run_all(app.t12b_a_run("帮我查一下上个月的数据库订单量"))
        done = chips_done(chips)
        assert frames >= 6 and 'data-id="sql_agent" data-lit="done"' in svg, "Router SVG 未按真实节点名流转"
        assert "sql_agent" in done and "rag_agent" not in done, f"Router 路由点错支路：{done}"
        assert "SQL 专员" in json.loads(snap)["answer"]
    check("10.12b Router：SQL 支路点亮", t12b_router)

    def t12b_supervisor():
        (chips, svg, snap, console), _ = run_all(app.t12b_b_run())
        done = chips_done(chips)
        assert {"researcher", "writer", "aggregator"} <= done, f"派活不全：{done}"
        assert "最终报告" in json.loads(snap)["final"]
    check("10.12b Subagents（Supervisor）：循环派活 + 汇总", t12b_supervisor)

    def t12b_per():
        (chips, svg, snap, console), _ = run_all(app.t12b_c_run())
        obj = json.loads(snap)
        assert obj["revision"] == 2 and obj["verdict"] == "pass", f"评审保险丝：{obj}"
        assert "executor" in chips_done(chips) and "reviewer" in chips_done(chips)
    check("10.12b PER：2 版过审", t12b_per)

    # ---------- 10.13（多级审批：小额 1 层，大额 2 层） ----------
    def t13_small():
        outs = list(app.t13_start(5000))
        chips, svg, snap, console, pending, ok, no = outs[-1]
        assert pending["visible"] and "组长审批" in pending["value"]
        chips, svg, snap, console, pending, ok, no = app.t13_approve()
        assert not pending["visible"], "小额通过后不应再挂起"
        assert "已转账 5000 元" in console
    check("10.13 小额：组长一级审批", t13_small)

    def t13_big():
        outs = list(app.t13_start(200000))
        _, _, _, _, pending, ok, no = outs[-1]
        assert "组长审批" in pending["value"]
        chips, svg, snap, console, pending, ok, no = app.t13_approve()
        assert pending["visible"] and "老板审批" in pending["value"], "大额应进入老板二审"
        chips, svg, snap, console, pending, ok, no = app.t13_reject()
        assert "流程终止" in console, f"老板驳回应终止：{console}"
    check("10.13 大额：两级审批 + 驳回终止", t13_big)

    # ---------- 10.14（Functional API 两阶段） ----------
    def t14():
        outs = list(app.t14_start("机器人安全"))
        assert len(outs) >= 4, "Functional API 应展示 START、并行、汇合、审阅四个阶段"
        assert "START" in outs[0][0] and "正在执行" in outs[0][0], "缺少 START 入口帧"
        assert "translate" in outs[1][0] and "summarize" in outs[1][0], "两个 Future 未同时进入执行中状态"
        assert "write_essay" in outs[2][0] and "translate" in outs[2][0], "Future 汇合阶段未点亮"
        assert "State 摘要" in outs[2][0], "Functional API 图下方缺少 State 摘要"
        _, _, document, snap, console, modal = outs[-1]
        assert modal["visible"], "人工审阅弹窗未弹出"
        assert "三道安全护栏" in document, "弹窗中应能看到完整初稿"
        _, _, document, snap, console, modal = app.t14_approve("")
        assert not modal["visible"], "批准后弹窗应关闭"
        assert "最终产出" in console and "《机器人安全》" in console
        assert "三道安全护栏" in document and len(document) > 300, "批准后应展示完整文稿"
    check("10.14 Functional API：interrupt → resume", t14)

    print(f"\n{'全部通过' if fail_count == 0 else f'{fail_count} 个用例失败'}（{ok_count} 通过 / {fail_count} 失败）")
    sys.exit(1 if fail_count else 0)


if __name__ == "__main__":
    main()
