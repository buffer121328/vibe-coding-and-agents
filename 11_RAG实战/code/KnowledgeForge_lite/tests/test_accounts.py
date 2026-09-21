"""账号与会话：注册、登录、登出，以及"身份 ↔ 工牌"这条对应关系。不联网。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite.store import accounts as acc  # noqa: E402
from forge_lite.core.identity import USERS  # noqa: E402


class TempDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "accounts.sqlite"

    def tearDown(self):
        self.tmp.cleanup()


class IdentityToBadgeTests(TempDb):
    """注册身份和演示工牌必须一一对应——这是"权限先于检索"的起点。

    曾经的真 bug：注册表单让「角色」和「部门」分开选，而工牌是按 (角色, 部门) 这一对
    映射的。选「公司管理员 + IT」（IT 还是部门下拉的默认值）会落到表外、回落到
    IT 员工的工牌，于是这个"管理员"进不去知识文档和评测治理。
    修法不是给回落打补丁，而是让表单根本拼不出工牌表里不存在的组合。
    """

    def test_every_identity_maps_to_a_real_badge(self):
        for key, spec in acc.IDENTITIES.items():
            with self.subTest(identity=key):
                account = acc.Account("x", "x", spec["role"], spec["department"])
                self.assertEqual(account.badge_id, key)
                self.assertIn(key, USERS, "工牌必须在 identity.USERS 里真实存在")

    def test_register_only_accepts_known_identities(self):
        with self.assertRaises(acc.AccountError):
            acc.register("someone", "hunter2", identity="it", path=self.db)

    def test_admin_identity_keeps_its_department(self):
        """管理员本来就不过滤部门，所以它的 (role, department) 是固定的一对。"""
        account = acc.register("laoshi", "hunter2", "王老师", "admin", self.db)
        self.assertEqual(account.badge_id, "admin")
        self.assertEqual(account.role, "company_admin")
        self.assertEqual(account.department, "company")


class RegisterTests(TempDb):
    def test_register_then_authenticate(self):
        acc.register("xiaoming", "hunter2", "小明", "hr_staff", self.db)
        account = acc.authenticate("xiaoming", "hunter2", self.db)
        self.assertIsNotNone(account)
        self.assertEqual(account.display_name, "小明")
        self.assertEqual(account.badge_id, "hr_staff")

    def test_duplicate_username_is_rejected(self):
        acc.register("xiaoming", "hunter2", path=self.db)
        with self.assertRaises(acc.AccountError):
            acc.register("xiaoming", "other123", path=self.db)

    def test_short_username_and_password_are_rejected(self):
        for username, password in (("ab", "hunter2"), ("xiaoming", "123")):
            with self.subTest(username=username, password=password):
                with self.assertRaises(acc.AccountError):
                    acc.register(username, password, path=self.db)

    def test_display_name_falls_back_to_username(self):
        account = acc.register("xiaoming", "hunter2", path=self.db)
        self.assertEqual(account.display_name, "xiaoming")


class PasswordTests(unittest.TestCase):
    def test_same_password_hashes_differently(self):
        """每条口令现生成盐，所以同一个口令两次入库的摘要不同。"""
        first = acc.hash_password("hunter2", rounds=1000)
        second = acc.hash_password("hunter2", rounds=1000)
        self.assertNotEqual(first, second)
        self.assertTrue(acc.verify_password("hunter2", first))
        self.assertTrue(acc.verify_password("hunter2", second))

    def test_wrong_password_and_broken_hash_fail_quietly(self):
        stored = acc.hash_password("hunter2", rounds=1000)
        self.assertFalse(acc.verify_password("wrong", stored))
        # 摘要串被改坏时返回 False 而不是抛异常——登录路径上不该有未捕获的异常
        self.assertFalse(acc.verify_password("hunter2", "不是摘要"))
        self.assertFalse(acc.verify_password("hunter2", ""))


class SessionTests(TempDb):
    def test_session_round_trip_and_drop(self):
        acc.register("xiaoming", "hunter2", path=self.db)
        token = acc.create_session("xiaoming", self.db)
        self.assertEqual(acc.read_session(token, self.db).username, "xiaoming")
        acc.drop_session(token, self.db)
        self.assertIsNone(acc.read_session(token, self.db), "登出就是删掉那一行，立刻失效")

    def test_expired_session_is_rejected_and_cleaned(self):
        acc.register("xiaoming", "hunter2", path=self.db)
        token = acc.create_session("xiaoming", self.db, days=0)
        self.assertIsNone(acc.read_session(token, self.db))

    def test_unknown_token_is_none(self):
        self.assertIsNone(acc.read_session("", self.db))
        self.assertIsNone(acc.read_session("随手编的", self.db))


class NoSeededAccountsTests(TempDb):
    """库建出来是空的：不预置默认口令的账号。"""

    def test_fresh_database_has_no_accounts(self):
        acc.init_db(self.db)
        with acc._connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0], 0)

    def test_authenticate_on_empty_database_returns_none(self):
        self.assertIsNone(acc.authenticate("admin", "forge123", self.db))


if __name__ == "__main__":
    unittest.main()
