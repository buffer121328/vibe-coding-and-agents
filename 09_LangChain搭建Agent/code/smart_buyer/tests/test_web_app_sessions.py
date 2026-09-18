from smart_buyer import web_app


class FakeAgent:
    def chat_recommend(self, message, session_id, user_id):
        return {
            "output": f"已收到：{message}",
            "intermediate_steps": [],
            "total_tokens": 12,
            "cost_usd": 0.00001,
        }


def setup_function():
    web_app._WEB_SESSION_HISTORY.clear()
    web_app._WEB_SESSION_PROCESS.clear()
    web_app._WEB_SESSION_REPORTS.clear()
    web_app._SESSION_CHOICES[:] = web_app._DEFAULT_SESSION_CHOICES
    web_app.seed_demo_sessions()


def _final(result):
    if not hasattr(result, "__iter__") or isinstance(result, (str, dict, tuple, list)):
        values = result
    else:
        values = None
        for values in result:
            pass
        result = values
    return result


def test_session_switch_restores_its_own_history(monkeypatch):
    monkeypatch.setattr(web_app, "get_agent", lambda use_mcp: FakeAgent())

    history, _, _, _, session_id = _final(
        web_app.ask_agent("推荐轻薄本", [], "tester", "laptop-compare", False)
    )
    restored, process, _, _, restored_id, title, meta, *_ = web_app.select_session("laptop-compare")

    assert session_id == restored_id == "laptop-compare"
    assert restored == history
    assert "轻薄本对比" in title
    assert "laptop-compare" in meta
    assert restored[-1]["role"] == "assistant"


def test_empty_send_keeps_current_session_id():
    result = _final(web_app.ask_agent("", [], "tester", "custom-session", False))

    assert result[-1] == "custom-session"


def test_new_session_has_unique_id_and_radio_choice():
    first = web_app.start_new_session()
    second = web_app.start_new_session()
    first_id, second_id = first[6], second[6]

    assert first_id != second_id
    assert first[4]["value"] == first_id
    assert first_id in web_app._WEB_SESSION_HISTORY
    assert any(value == first_id for _, value in second[4]["choices"])


def test_ask_agent_shows_user_message_before_reply(monkeypatch):
    monkeypatch.setattr(web_app, "get_agent", lambda use_mcp: FakeAgent())
    events = web_app.ask_agent("推荐轻薄本", [], "tester", "web-shopper", False)

    first = next(events)
    assert first[0][-1] == {"role": "user", "content": "推荐轻薄本"}
    assert first[3] == ""

    last = _final(events)
    assert last[0][-2] == {"role": "user", "content": "推荐轻薄本"}
    assert last[0][-1]["role"] == "assistant"
    assert "推荐轻薄本" in last[0][-1]["content"]


def test_settings_and_help_switch_right_panel():
    workspace, settings, help_view, tabs = web_app.show_right_view("settings")
    assert workspace["visible"] is False
    assert settings["visible"] is True
    assert help_view["visible"] is False
    assert tabs["selected"] == "trace"

    workspace, settings, help_view, tabs = web_app.show_right_view("help")
    assert help_view["visible"] is True
    assert settings["visible"] is False


def test_runtime_trace_uses_chinese_and_hides_raw_dump():
    from types import SimpleNamespace

    long_obs = "【社区评测汇总】键盘偏软，风扇噪音明显。" + ("额外吐槽。" * 40)
    html = web_app.format_steps(
        {
            "intermediate_steps": [
                (
                    SimpleNamespace(
                        tool="search_product_reviews_and_complaints",
                        tool_input={"query_keyword": "小新 Pro16"},
                    ),
                    long_obs,
                ),
                (
                    SimpleNamespace(tool="query_price_history", tool_input='{"product": "ThinkBook14"}'),
                    "当前处于低位，是好价",
                ),
            ]
        },
        "done",
    )

    assert "search_product_reviews_and_complaints" not in html
    assert "query_price_history" not in html
    assert "query_keyword" not in html
    assert "全网差评搜索" in html
    assert "历史价格" in html
    assert "关键词 小新 Pro16" in html
    assert "产品 ThinkBook14" in html
    assert "{" not in html
    assert "额外吐槽" not in html
    assert "输入参数" not in html
    assert web_app.zh_tool_query('{"category_or_term": "低色域屏幕"}{"category_or_term": "低色域屏幕"}') == "品类 低色域屏幕"


def test_laptop_compare_restores_demo_archive():
    history, process, status, _, session_id, title, _, report_html, report_json, report_status, demand = (
        web_app.select_session("laptop-compare")
    )

    assert session_id == "laptop-compare"
    assert "轻薄本对比" in title
    assert sum(1 for message in history if message["role"] == "user") == 2
    assert "ThinkBook" in "".join(item["content"] for item in history)
    assert "避坑宝典" in process
    assert "全网差评搜索" in process
    assert "查了 4 步" in process
    assert "研究过程一并恢复" in status
    assert "ThinkBook 14+" in report_html
    assert report_json["overall_value_score"] == 84
    assert "决策报告" in report_status or "昨天" in report_status
    assert "预算 5000" in demand


def test_switching_sessions_keeps_each_report_and_trace(monkeypatch):
    monkeypatch.setattr(web_app, "get_agent", lambda use_mcp: FakeAgent())
    _final(web_app.ask_agent("推荐降噪耳机", [], "tester", "web-shopper", False))
    web_app._remember_report(
        "web-shopper",
        web_app.report_to_html({"category_summary": "通勤降噪耳机", "budget_evaluation": "千元够用", "overall_value_score": 80, "recommended_products": [], "trap_warnings": ["先试戴"], "final_verdict": "先听再买"}),
        {"category_summary": "通勤降噪耳机"},
        "已生成耳机报告",
        "推荐降噪耳机",
    )

    other = web_app.select_session("laptop-compare")
    back = web_app.select_session("web-shopper")

    assert "ThinkBook" in "".join(item["content"] for item in other[0])
    assert "避坑宝典" in other[1]
    assert "通勤降噪耳机" in back[7]
    assert back[9] == "已生成耳机报告"
