"""端点契约测试：SSE 分片顺序、导出下载头、轨迹接口、审计入账。生成模型被替身挡住。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from forge_lite.web import app as server  # noqa: E402
from forge_lite.web.pages import render_chat_page  # noqa: E402
from forge_lite.store.audit import AuditLog  # noqa: E402
from forge_lite.contracts import ASK_DONE_KEYS, TRACE_KEYS, missing_keys  # noqa: E402
from forge_lite.store.conversations import ConversationStore  # noqa: E402
from forge_lite.core.sseutil import format_delta, format_done, join_deltas, last_done, parse_stream  # noqa: E402


FAKE_ANSWER = {
    "question": "去上海出差住一晚能报多少？",
    "answer": "一线城市住宿上限 500 元 [1]。",
    "status": "ok",
    "warn": "",
    "routes": "bm25+dense+graph",
    "intent": "factoid",
    "queries": ["去上海出差住一晚能报多少？"],
    "citations": [{"marker": "[1]", "doc_id": "员工差旅管理制度.md#0"}],
    "contexts": ["一线城市住宿标准为每人每天不超过 500 元。"],
    "user_id": "it_staff",
    "evidence": {
        "response_status": "answered",
        "allows_generation": True,
        "reason_codes": ["direct_support"],
        "coverage": 0.8,
    },
    "response_status": "answered",
    "actor": {"user_id": "it_staff", "name": "IT 员工", "role": "employee", "department": "it"},
    "conversation_id": "",
    "run_id": "",
    "history_saved": False,
}


class FakeAsk:
    """替身：把答案写进真实会话柜，再原样交给 SSE 组装。"""

    def __init__(self, store: ConversationStore):
        self.store = store

    def __call__(self, question, user_id=None, conversation_id=None, persist=True):
        from forge_lite.store.conversations import ConversationError
        payload = dict(FAKE_ANSWER)
        payload["question"] = question
        # 与 forge_lite.answer.agent.ask 同纪律：不是自己的柜子就当没传指针
        owned = conversation_id or None
        if owned:
            try:
                self.store.get_conversation(owned, user_id)
            except ConversationError:
                owned = None
        conv_id, run_id = self.store.record_answer(user_id, question, payload, conversation_id=owned)
        payload["conversation_id"] = conv_id
        payload["run_id"] = run_id
        payload["history_saved"] = True
        return payload


class SseEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ConversationStore(Path(self.tmp.name) / "c.sqlite")
        self.audit = AuditLog(Path(self.tmp.name) / "audit.jsonl")
        self.patches = [
            patch.object(server, "get_store", lambda: self.store),
            patch.object(server, "get_audit", lambda: self.audit),
            patch.object(server, "ask_agent", FakeAsk(self.store)),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.store.close()
        self.tmp.cleanup()

    def _ask(self, client, question="去上海出差住一晚能报多少？", user_id="it_staff", conv=None):
        return client.post("/ask", json={"question": question, "user_id": user_id, "conversation_id": conv})

    def test_stream_order_and_done_payload(self):
        with TestClient(server.app) as client:
            resp = self._ask(client)
            self.assertEqual(resp.status_code, 200)
            frames = parse_stream(resp.text)
            events = [frame.event for frame in frames]
            self.assertEqual(events[0], "citations")
            self.assertEqual(events[-1], "done")
            self.assertEqual(join_deltas(frames), FAKE_ANSWER["answer"])
            done = last_done(frames)
            self.assertEqual(missing_keys(done, ASK_DONE_KEYS), [])
            self.assertTrue(done["history_saved"])
            self.assertTrue(done["conversation_id"].startswith("conv_"))
            self.assertEqual(done["route_chips"][0]["label"], "关键词")

    def test_answer_is_persisted_for_reload(self):
        with TestClient(server.app) as client:
            done = last_done(parse_stream(self._ask(client).text))
            conv_id = done["conversation_id"]
        detail = self.store.get_conversation(conv_id, "it_staff")
        self.assertEqual(len(detail.messages), 2)
        self.assertEqual(detail.messages[1].payload["run_id"], done["run_id"])

    def test_second_question_appends_to_same_cabinet(self):
        with TestClient(server.app) as client:
            first = last_done(parse_stream(self._ask(client).text))
            second = last_done(parse_stream(self._ask(client, question="那报销几号前交？", conv=first["conversation_id"]).text))
        self.assertEqual(first["conversation_id"], second["conversation_id"])
        detail = self.store.get_conversation(first["conversation_id"], "it_staff")
        self.assertEqual(len(detail.messages), 4)

    def test_foreign_conversation_id_starts_a_new_cabinet(self):
        with TestClient(server.app) as client:
            hr_conv, _ = self.store.record_answer("hr_staff", "人事的柜子", dict(FAKE_ANSWER))
            done = last_done(parse_stream(self._ask(client, conv=hr_conv).text))
        self.assertNotEqual(done["conversation_id"], hr_conv)

    def test_audit_ledger_records_the_ask(self):
        with TestClient(server.app) as client:
            self._ask(client)
        rows = self.audit.for_actor("it_staff")
        self.assertTrue(any(row["action"] == "ask" for row in rows))

    def test_trace_endpoint_returns_panel_fields(self):
        with TestClient(server.app) as client:
            done = last_done(parse_stream(self._ask(client).text))
            resp = client.get(f"/api/runs/{done['run_id']}/trace", params={"user_id": "it_staff"})
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(missing_keys(resp.json(), TRACE_KEYS), [])
            body = resp.json()
            self.assertEqual(body["response_status"], "answered")
            self.assertEqual(body["evidence_label"], "已回答")
            self.assertNotEqual(body["response_status"], "ok")
            foreign = client.get(f"/api/runs/{done['run_id']}/trace", params={"user_id": "hr_staff"})
            self.assertEqual(foreign.status_code, 404)

    def test_export_endpoint_sets_download_header(self):
        with TestClient(server.app) as client:
            done = last_done(parse_stream(self._ask(client).text))
            resp = client.get(f"/api/conversations/{done['conversation_id']}/export",
                              params={"user_id": "it_staff", "format": "md"})
            self.assertEqual(resp.status_code, 200)
            self.assertIn("attachment", resp.headers.get("content-disposition", ""))
            self.assertIn("住宿上限", resp.text)
            bad = client.get(f"/api/conversations/{done['conversation_id']}/export",
                             params={"user_id": "it_staff", "format": "pdf"})
            self.assertEqual(bad.status_code, 422)

    def test_export_of_foreign_cabinet_is_404(self):
        with TestClient(server.app) as client:
            done = last_done(parse_stream(self._ask(client).text))
            resp = client.get(f"/api/conversations/{done['conversation_id']}/export",
                              params={"user_id": "hr_staff"})
            self.assertEqual(resp.status_code, 404)


class SseFrameUnitTests(unittest.TestCase):
    def test_delta_and_done_frames_roundtrip(self):
        blob = format_delta("甲") + format_done({"status": "ok", "conversation_id": "conv_1"})
        frames = parse_stream(blob)
        self.assertEqual(join_deltas(frames), "甲")
        self.assertEqual(last_done(frames)["conversation_id"], "conv_1")

    def test_json_payload_is_utf8_not_escaped(self):
        self.assertIn("住宿", format_delta("住宿"))

    def test_done_payload_is_parseable_json(self):
        payload = json.loads(format_done({"status": "ok"}).split("data:", 1)[1].strip())
        self.assertEqual(payload["status"], "ok")


if __name__ == "__main__":
    unittest.main()


class AdminAreaTests(unittest.TestCase):
    """文档区与评测区按角色开放：接口挡住、页面说明原因。"""

    DOC_ROW = {"source": "制度.md", "department": "company", "department_label": "公司",
               "sensitivity": "public", "sensitivity_label": "公开", "acl": "employee",
               "chunks": 2, "hash_prefix": "abcd1234", "schema": "acl-v2", "status": "indexed",
               "signals": [], "bytes": 120, "in_index": True}
    SUMMARY = {"documents": 1, "indexed": 1, "quarantined": 0, "chunks": 2, "schema": "acl-v2",
               "schema_stale": False, "empty": False, "policies": 5}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.audit = AuditLog(Path(self.tmp.name) / "audit.jsonl")
        self.patches = [
            patch.object(server, "get_audit", lambda: self.audit),
            patch.object(server, "list_documents_admin", lambda *a, **k: [type("R", (), {
                **AdminAreaTests.DOC_ROW, "as_dict": lambda self: AdminAreaTests.DOC_ROW})()]),
            patch.object(server, "index_summary", lambda *a, **k: AdminAreaTests.SUMMARY),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def test_documents_requires_admin(self):
        with TestClient(server.app) as client:
            for badge in ("it_staff", "hr_staff", "finance_head"):
                with self.subTest(badge=badge):
                    resp = client.get("/api/documents", params={"user_id": badge})
                    self.assertEqual(resp.status_code, 403)
                    self.assertIn("公司管理员", resp.json()["detail"])
            ok = client.get("/api/documents", params={"user_id": "admin"})
            self.assertEqual(ok.status_code, 200)
            self.assertEqual(ok.json()["documents"][0]["source"], "制度.md")
            self.assertEqual(ok.json()["limits"]["max_bytes"] > 0, True)

    def test_documents_overview_exposes_chunk_knobs(self):
        """切块实验台要按当前 config 的旋钮起步，所以总览得把它带出来。"""
        from forge_lite import config
        with TestClient(server.app) as client:
            ok = client.get("/api/documents", params={"user_id": "admin"})
            chunk = ok.json()["limits"]["chunk"]
            self.assertEqual(chunk["size"], config.CHUNK_SIZE)
            self.assertEqual(chunk["overlap"], config.CHUNK_OVERLAP)

    def test_chunk_preview_honours_knobs(self):
        """预演模式的块数必须真的跟着 chunk_size 变——实验台的全部意义就在这。"""
        with TestClient(server.app) as client:
            body = "住宿标准每人每天不超过 500 元。" * 40
            coarse = client.get("/api/documents/制度.md/chunks",
                                params={"user_id": "admin", "text": body, "chunk_size": 800, "overlap": 0})
            fine = client.get("/api/documents/制度.md/chunks",
                              params={"user_id": "admin", "text": body, "chunk_size": 100, "overlap": 0})
            self.assertEqual(coarse.status_code, 200)
            self.assertEqual(coarse.json()["mode"], "preview")
            self.assertGreater(len(fine.json()["chunks"]), len(coarse.json()["chunks"]))
            self.assertEqual(coarse.json()["chunk_size"], 800)
            self.assertEqual(fine.json()["overlap"], 0)

    def test_chunk_preview_rejects_out_of_range_knobs(self):
        """旋钮有边界，越界由服务端拒绝，不靠前端拦。"""
        with TestClient(server.app) as client:
            low = client.get("/api/documents/制度.md/chunks",
                             params={"user_id": "admin", "text": "制度原文", "chunk_size": 10})
            high = client.get("/api/documents/制度.md/chunks",
                              params={"user_id": "admin", "text": "制度原文", "overlap": 9999})
            self.assertEqual(low.status_code, 422)
            self.assertEqual(high.status_code, 422)

    def test_chunk_preview_requires_admin(self):
        with TestClient(server.app) as client:
            resp = client.get("/api/documents/制度.md/chunks",
                              params={"user_id": "it_staff", "text": "住宿标准 500 元"})
            self.assertEqual(resp.status_code, 403)

    def test_evaluation_cases_requires_admin(self):
        with TestClient(server.app) as client:
            self.assertEqual(client.get("/api/evaluation/cases", params={"user_id": "it_staff"}).status_code, 403)
            ok = client.get("/api/evaluation/cases", params={"user_id": "admin"})
            self.assertEqual(ok.status_code, 200)
            self.assertTrue(ok.json()["cases"])

    def test_upload_calls_service_and_reports(self):
        captured = {}

        def fake_upload(filename, data, **kwargs):
            captured["filename"] = filename
            captured["size"] = len(data)
            return {"source": filename, "status": "indexed", "chunks": 3, "signals": [], "replaced": False}

        def fake_summarize(results):
            return {"summary": "入库 1 篇（3 块）", "indexed": 1, "quarantined": 0, "chunks": 3, "items": results}

        with patch.object(server, "upload_document", fake_upload), \
                patch.object(server, "summarize_upload_results", fake_summarize), \
                TestClient(server.app) as client:
            resp = client.post(
                "/api/documents/upload",
                params={"user_id": "admin"},
                files=[("files", ("新品说明.md", "住宿标准 500 元".encode(), "text/markdown"))],
            )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("入库 1 篇", resp.json()["summary"])
        self.assertEqual(captured["filename"], "新品说明.md")
        self.assertGreater(captured["size"], 0)

    def test_upload_rejected_suffix_is_reported_not_500(self):
        from forge_lite.service.documents import DocumentError

        def fake_upload(filename, data, **kwargs):
            raise DocumentError("只收 .md / .txt / .html / .docx / .pdf")

        with patch.object(server, "upload_document", fake_upload), \
                patch.object(server, "summarize_upload_results", lambda results: {
                    "summary": "入库 0 篇（0 块）", "indexed": 0, "quarantined": 0, "chunks": 0,
                    "items": results}), \
                TestClient(server.app) as client:
            resp = client.post("/api/documents/upload", params={"user_id": "admin"},
                               files=[("files", ("evil.exe", b"x", "application/octet-stream"))])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["items"][0]["status"], "rejected")
        self.assertIn("只收", resp.json()["items"][0]["error"])

    def test_delete_and_chunks_endpoints(self):
        calls = {}

        def fake_delete(source, **kwargs):
            calls["deleted"] = source
            return {"source": source, "deleted": 1, "stats": {}}

        def fake_chunks(source, *args, **kwargs):
            return [{"chunk_index": 0, "text": "住宿 500 元"}]

        with patch.object(server, "delete_document", fake_delete), \
                patch.object(server, "document_chunks", fake_chunks), \
                TestClient(server.app) as client:
            chunk_resp = client.get("/api/documents/制度.md/chunks", params={"user_id": "admin"})
            self.assertEqual(chunk_resp.status_code, 200)
            self.assertEqual(chunk_resp.json()["chunks"][0]["chunk_index"], 0)
            preview = client.get("/api/documents/制度.md/chunks",
                                 params={"user_id": "admin", "text": "住宿标准 500 元。" * 20,
                                         "chunk_size": 60, "overlap": 10})
            self.assertEqual(preview.json()["mode"], "preview")
            self.assertTrue(preview.json()["chunks"])
            deleted = client.delete("/api/documents/制度.md", params={"user_id": "admin"})
            self.assertEqual(deleted.status_code, 200)
            self.assertEqual(calls["deleted"], "制度.md")

    def test_evaluation_run_streams_cases_then_summary(self):
        from forge_lite.answer.evaluation import CaseResult

        def fake_iter(cases=None, ask_fn=None):
            yield CaseResult(case_id="a", question="住宿上限？", user_id="it_staff", actor_name="IT 员工",
                             expect="answer", expected_docs=["员工差旅管理制度.md"], status="ok",
                             behavior_ok=True, hit=1.0, passed=True, reason="符合预期", latency_ms=12)
            yield CaseResult(case_id="b", question="年终奖？", user_id="it_staff", actor_name="IT 员工",
                             expect="refuse", status="refuse", behavior_ok=True, passed=True,
                             reason="符合预期", latency_ms=8)

        with patch.object(server, "iter_cases", fake_iter), \
                patch.object(server, "save_report", lambda results, note="": {
                    "path": "eval-test.json", "created_at": "2026-01-01T00:00:00+00:00"}), \
                TestClient(server.app) as client:
            resp = client.post("/api/evaluation/run", params={"user_id": "admin"})
            self.assertEqual(resp.status_code, 200)
            frames = parse_stream(resp.text)
        events = [frame.event for frame in frames]
        self.assertEqual(events.count("case"), 2)
        self.assertEqual(events[-1], "summary")
        summary = frames[-1].data["summary"]
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["passed"], 2)
        self.assertEqual(frames[-1].data["report"], "eval-test.json")

    def test_evaluation_run_requires_admin(self):
        with TestClient(server.app) as client:
            resp = client.post("/api/evaluation/run", params={"user_id": "hr_staff"})
            self.assertEqual(resp.status_code, 403)


class ConsolePageTests(unittest.TestCase):
    """三个视图与导航都要在页面里，控制台脚本按契约取 id。"""

    def test_nav_and_views_present(self):
        html = str(render_chat_page())
        for value in ("nav-qa", "nav-docs", "nav-eval", "view-qa", "view-docs", "view-eval"):
            with self.subTest(value=value):
                self.assertIn(f'id="{value}"', html)

    def test_console_assets_linked(self):
        html = str(render_chat_page())
        self.assertIn("/static/console.css", html)
        self.assertIn("/static/console.js", html)

    def test_docs_and_eval_ids_present(self):
        html = str(render_chat_page())
        for value in ("docs-summary", "docs-upload", "docs-table", "docs-locked",
                      "eval-summary", "eval-run", "eval-ragas", "eval-table", "eval-reports"):
            with self.subTest(value=value):
                self.assertIn(f'id="{value}"', html)
