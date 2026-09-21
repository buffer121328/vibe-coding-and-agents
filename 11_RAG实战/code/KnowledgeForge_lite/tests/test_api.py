"""HTTP 契约：会话柜、目录、图谱、页面 DOM。不调生成模型。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite.contracts import API_PATHS, CONVERSATION_CARD_KEYS, DOM_IDS, missing_keys  # noqa: E402
from forge_lite.store.conversations import ConversationStore  # noqa: E402
from forge_lite.web.pages import render_chat_page  # noqa: E402


class PageContractTests(unittest.TestCase):
    def test_legacy_server_module_reexports_the_same_app(self):
        """文档里的 uvicorn forge_lite.server:app 必须还能起服务。"""
        from forge_lite.server import app as legacy
        from forge_lite.web.app import app as current
        self.assertIs(legacy, current)

    def test_shell_and_views_are_hooked_up(self):
        html = str(render_chat_page())
        for value in DOM_IDS.values():
            self.assertIn(f'id="{value}"', html)
        self.assertIn("/static/console.css", html)
        self.assertIn("/static/workbench.js", html)
        self.assertIn("/static/console.js", html)
        self.assertNotIn("mvp.css", html)

    def test_static_files_exist(self):
        static = ROOT / "forge_lite" / "web" / "static"
        css = (static / "console.css").read_text(encoding="utf-8")
        js = (static / "workbench.js").read_text(encoding="utf-8")
        # 与完整版同一套主色
        self.assertIn("--primary: #155eef", css)
        # 问答区仍然由 workbench.js 管，接口没变
        self.assertIn("/api/conversations", js)
        self.assertIn("localStorage", js)
        self.assertIn("/ask", js)


class ApiStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ConversationStore(Path(self.tmp.name) / "c.sqlite")
        from forge_lite.store.audit import AuditLog
        self.audit = AuditLog(Path(self.tmp.name) / "audit.jsonl")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_health_and_whoami(self):
        from fastapi.testclient import TestClient
        from forge_lite.web import app as server
        # 审计改到临时账本：测试不往课堂 runtime 写事件
        with patch.object(server, "get_audit", lambda: self.audit):
            with TestClient(server.app) as client:
                health = client.get(API_PATHS["health"])
                self.assertEqual(health.status_code, 200)
                self.assertEqual(health.json()["status"], "ok")
                who = client.get(API_PATHS["whoami"])
                self.assertEqual(who.status_code, 200)
                ids = {item["user_id"] for item in who.json()["users"]}
                self.assertEqual(ids, {"admin", "finance_head", "it_staff", "hr_staff"})

    def test_conversation_crud_is_owner_scoped(self):
        from fastapi.testclient import TestClient
        from forge_lite.web import app as server
        with patch.object(server, "get_store", lambda: self.store), \
                patch.object(server, "get_audit", lambda: self.audit):
            with TestClient(server.app) as client:
                created = client.post(API_PATHS["conversations"], json={"user_id": "it_staff", "title": "差旅"})
                self.assertEqual(created.status_code, 200)
                conv_id = created.json()["id"]
                self.assertEqual(missing_keys(created.json(), CONVERSATION_CARD_KEYS), [])
                listed = client.get(API_PATHS["conversations"], params={"user_id": "hr_staff"})
                self.assertEqual(listed.json()["items"], [])
                stolen = client.get(f"{API_PATHS['conversations']}/{conv_id}", params={"user_id": "hr_staff"})
                self.assertEqual(stolen.status_code, 404)
                mine = client.get(f"{API_PATHS['conversations']}/{conv_id}", params={"user_id": "it_staff"})
                self.assertEqual(mine.status_code, 200)
                deleted = client.delete(f"{API_PATHS['conversations']}/{conv_id}", params={"user_id": "it_staff"})
                self.assertEqual(deleted.status_code, 200)

    def test_catalog_and_graph_honor_badge(self):
        from fastapi.testclient import TestClient
        from forge_lite.data import catalog as catalog_mod
        from forge_lite.web import app as server

        # 自备切块夹具：不读课堂 runtime（那边入库脚本会并发改写，测试要能独立复现）
        fixture = [
            {"source": "员工差旅管理制度.md", "chunk_index": 0, "text": "《员工差旅管理制度》住宿 500 元",
             "department": "company", "sensitivity": "public", "acl": "employee"},
            {"source": "财务薪酬密级.md", "chunk_index": 0, "text": "《财务薪酬密级》P6 年薪 35 万至 45 万",
             "department": "finance", "sensitivity": "restricted", "acl": "restricted"},
        ]
        with patch.object(server, "get_audit", lambda: self.audit), \
                patch.object(catalog_mod, "load_chunks", lambda path=None: list(fixture)), \
                TestClient(server.app) as client:
            hr = client.get(API_PATHS["catalog"], params={"user_id": "hr_staff"})
            self.assertEqual(hr.status_code, 200)
            names = {item["source"] for item in hr.json()["documents"]}
            self.assertNotIn("财务薪酬密级.md", names)
            graph = client.get(API_PATHS["graph"], params={"entity": "P6薪酬带宽", "user_id": "it_staff"})
            self.assertEqual(graph.status_code, 200)
            finance = client.get(API_PATHS["graph"], params={"entity": "P6薪酬带宽", "user_id": "finance_head"})
            self.assertEqual(finance.status_code, 200)
            prompts = client.get(API_PATHS["prompts"], params={"user_id": "it_staff"})
            self.assertTrue(prompts.json()["prompts"])


if __name__ == "__main__":
    unittest.main()
