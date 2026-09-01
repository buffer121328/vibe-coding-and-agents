"""RAG 工作台冒烟测试：逐关调用 Gradio 回调，确认按钮不会黑盒或空白。

运行：在 ``11_RAG实战/code`` 目录执行 ``./.venv/bin/python rag_workbench/smoke_test.py``。

本测试不依赖外部 LLM、Embedding 服务或首次下载本地模型；它验证课堂 UI 的稳定教学层：
左侧必须返回可解析、非空的中文 JSON，且能看见输入、候选资料、中间过程或输出解释。
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(CODE))
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
os.environ["RAG_WORKBENCH_TEST_MODE"] = "1"

import app  # noqa: E402

ok_count = 0
fail_count = 0


def check(name, fn):
    global ok_count, fail_count
    try:
        fn()
        ok_count += 1
        print(f"✅ {name}")
    except Exception as e:
        fail_count += 1
        print(f"❌ {name}: {type(e).__name__}: {e}")


def snap_obj(snap: str):
    obj = json.loads(snap)
    assert isinstance(obj, dict) and obj, "左侧 JSON 不能为空"
    assert snap.strip() != "{}", "左侧不能返回空对象 {}"
    return obj


def assert_has_input(obj: dict):
    keys = set(obj)
    assert any(
        key.startswith("本次按钮输入") or key.startswith("本次输入") or key in {"被检索的文档", "编号来源_真正喂给模型的资料"}
        for key in keys
    ), f"缺少输入说明，当前字段：{sorted(keys)}"


def assert_callback(name: str, fn):
    snap, console = fn()
    obj = snap_obj(snap)
    assert_has_input(obj)
    assert console and len(console) > 20, f"{name} 右侧过程日志为空"
    return obj, console


def main():
    def quality_home():
        payload, report = app.run_quality_gate()
        assert payload["release_gate"] == "PASS" and "门禁通过" in report
        payload, _ = app.run_version_drill()
        assert payload["差旅制度"] == "TRAVEL-2026-07"
        payload, _ = app.run_citation_drill("住宿上限为 500 元[3]。")
        assert payload["release_gate"] == "BLOCK" and payload["invalid_source_ids"] == [3]
        assert len(app.corpus_inventory()) >= 8
    check("质量控制台：语料 + 版本 + 引用 + 注入门禁", quality_home)

    def t02():
        raw = getattr(app.t02_raw, "value", None) or "# 退款制度\n退货成功后 48 小时内原路退款。"
        snap, console = app.t02_main(raw)
        obj = snap_obj(snap)
        assert "阶段2_清洗" in obj and "机密文件" not in obj["阶段2_清洗"]["清洗后文本"]
        snap, console = app.t02_parent(raw)
        obj = snap_obj(snap)
        assert "父块" in snap and "命中的子块" in snap and "父块" in console
    check("11.2 数据管道：切块 + 父子切块", t02)

    def t03():
        obj, console = assert_callback("11.3 度量", app.t03_main)
        assert "命中TopK" in obj and "真实调用状态" in obj
        obj, console = assert_callback("11.3 MRL", app.t03_mrl)
        assert "截断后向量" in obj and "真实调用状态" in obj
    check("11.3 嵌入：三种度量 + MRL", t03)

    def t04():
        obj, console = assert_callback("11.4 暴力", app.t04_brute)
        assert "这节在检索什么" in obj and "Recall@10" in console
        obj, console = assert_callback("11.4 Qdrant", app.t04_qdrant)
        assert "候选文档" in obj and "过滤后命中" in obj
    check("11.4 ANN + Qdrant 过滤检索", t04)

    def t05():
        obj, console = assert_callback("11.5 RRF", app.t05_rrf)
        assert "被检索的文档" in obj and "融合结果" in obj
        obj, console = assert_callback("11.5 Hybrid", app.t05_hybrid)
        assert "BM25召回" in obj and "Dense召回" in obj and "RRF融合Top4" in obj
    check("11.5 混合检索：RRF + 重排", t05)

    def t06():
        obj, _ = assert_callback("11.6 HyDE", app.t06_hyde)
        assert "被检索的文档" in obj and "中间产物_HyDE先喂进去的假想文档" in obj and "真实调用状态" in obj
        obj, _ = assert_callback("11.6 Multi", app.t06_multi)
        assert "改写出来的3路查询" in obj and "去重后命中" in obj
        obj, _ = assert_callback("11.6 Route", app.t06_route)
        assert obj["路由结果"]["destination"] == "finance"
    check("11.6 查询重写：HyDE + Multi-Query + 路由", t06)

    def t07():
        obj, _ = assert_callback("11.7 建图", app.t07_extract)
        assert "抽到的节点" in obj and "抽到的关系" in obj
        obj, _ = assert_callback("11.7 全局", app.t07_global)
        assert "每个社区先写的小研报" in obj and "最终全局回答" in obj
    check("11.7 GraphRAG：建图 + 社区", t07)

    def t08():
        obj, _ = assert_callback("11.8 场景一", lambda: app.t08_run(1))
        assert obj["模型答案"] and "检索后逐篇打分" in obj
        obj, _ = assert_callback("11.8 场景二", lambda: app.t08_run(2))
        assert obj["模型答案"] and "检索后逐篇打分" in obj
    check("11.8 Agentic RAG：命中 + 联网兜底", t08)

    def t09():
        obj, _ = assert_callback("11.9 手写", app.t09_manual)
        assert "实际检索排名" in obj and "忠实度样例" in obj
        obj, _ = assert_callback("11.9 Ragas", app.t09_ragas)
        assert "本次输入_黄金三元组" in obj and "Ragas会检查什么" in obj
        obj, _ = assert_callback("11.9 Trace", app.t09_trace)
        assert "追踪的阶段" in obj
    check("11.9 评估：指标 + Ragas + 追踪", t09)

    def t11():
        obj, _ = assert_callback("11.11 MaxSim", app.t11_maxsim)
        assert "喂进去的向量" in obj and "得分" in obj
        obj, _ = assert_callback("11.11 ColBERT", app.t11_pylate)
        assert "被检索的文档" in obj and "TopK" in obj
        obj, _ = assert_callback("11.11 Triage", app.t11_triage)
        assert "分诊结果" in obj
    check("11.11 MaxSim + ColBERT + 语义分诊台", t11)

    def t12():
        obj, _ = assert_callback("11.12 Citation", app.t12_citation)
        assert "真正喂给模型的上下文" in obj and "程序校验" in obj
        obj, _ = assert_callback("11.12 Verify", app.t12_verify)
        assert "拦截原因" in obj and "[3] 不存在，是幽灵引用" in obj["拦截原因"]
        obj, _ = assert_callback("11.12 Stream", app.t12_stream)
        assert "流式输出片段" in obj
    check("11.12 引用溯源：标注 + 校验 + 流式", t12)

    def t13():
        obj, _ = assert_callback("11.13 Cache", app.t13_cache)
        assert "缓存隔离字段" in obj and "隔离后的key前16位" in obj
        obj, _ = assert_callback("11.13 ACL", app.t13_acl)
        assert "被检索的文档" in obj and "本次输入_两次查询" in obj
        obj, _ = assert_callback("11.13 Scan", app.t13_scan)
        assert "投毒扫描结果" in obj and "蓝绿索引" in obj
        obj, _ = assert_callback("11.13 Prompt", app.t13_prompt)
        assert "检索到的资料" in obj and "系统规则" in obj
    check("11.13 安全：缓存 + ACL + 扫描 + 隔离", t13)

    def t14():
        obj, _ = assert_callback("11.14 Image", app.t14_caption)
        assert "入库替身文本" in obj and "原图位置" in obj
        obj, _ = assert_callback("11.14 Cross", app.t14_cross)
        assert "被检索的中文文档" in obj
        obj, _ = assert_callback("11.14 Table", app.t14_table)
        assert "表格数据" in obj and "代码计算结果" in obj
    check("11.14 多模态：图片 + 跨语言 + 表格", t14)

    print(f"\n{'全部通过' if fail_count == 0 else f'{fail_count} 个用例失败'}（{ok_count} 通过 / {fail_count} 失败）")
    sys.exit(1 if fail_count else 0)


if __name__ == "__main__":
    main()
