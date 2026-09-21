"""分层纪律：forge_lite 的六层只能单向依赖，发现回边就报错。不联网、不调模型。

为什么要有这条测试：分层写在文档里会腐烂（"当时是这么设计的"），写成断言才不会。
新人（或未来的自己）随手 `from ..answer.agent import get_llm` 就把环建起来了——
这类代码跑得通、测试也全绿，只在某天导入顺序一变时炸掉，或者永远悄悄多一层耦合。
让它在这里当场红掉，比事后画架构图便宜得多。
"""

from __future__ import annotations

import ast
import sys
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PKG = ROOT / "forge_lite"

# 层号越小越靠底。上层可以 import 下层，反之不行；同层之间也不许互相 import。
LAYERS = {
    "core": 0,
    "store": 1,
    "data": 1,
    "retrieve": 2,
    "answer": 3,
    "service": 3,
    "web": 4,
}
# 顶层公共件：谁都能用，它们自己不依赖任何包（config 例外，见下）
TOP_LEVEL = ("config", "contracts", "llm")


def module_names() -> dict[str, Path]:
    """扫出所有模块，键是 ``包/文件名``（顶层文件用 ``./文件名``）。"""
    found = {}
    for path in sorted(PKG.rglob("*.py")):
        if "__pycache__" in str(path) or path.name == "__init__.py":
            continue
        rel = path.relative_to(PKG)
        key = rel.with_suffix("").as_posix()
        found[key] = path
    return found


def imports_of(path: Path) -> list[tuple[int, str]]:
    """列出这个文件里的相对 import，返回 ``[(相对层级, 模块路径)]``。"""
    out = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.ImportFrom) or not node.level:
            continue
        if node.module:
            out.append((node.level, node.module))
        else:                                   # from . import X
            for alias in node.names:
                out.append((node.level, alias.name))
    return out


class LayerTests(unittest.TestCase):
    def setUp(self):
        self.modules = module_names()

    def _layer_of(self, key: str) -> int | None:
        return LAYERS.get(key.split("/")[0]) if "/" in key else None

    def test_no_import_cycles(self):
        """整图无环。这一条比"不跨层"更根本——环会让任何分层都失去意义。"""
        deps: dict[str, set[str]] = defaultdict(set)
        for key, path in self.modules.items():
            pkg = key.split("/")[0] if "/" in key else None
            for level, target in imports_of(path):
                root = target.split(".")[0]
                if level == 1 and pkg:                       # 同包
                    deps[key].add(f"{pkg}/{root}")
                elif level == 2:
                    deps[key].add(target if "/" in target else target)
                elif level >= 2 and pkg:
                    deps[key].add(target.replace(".", "/"))

        def reaches(start: str, goal: str, seen: set[str]) -> bool:
            if start == goal:
                return True
            if start in seen or start not in deps:
                return False
            seen.add(start)
            return any(reaches(nxt, goal, seen) for nxt in deps[start])

        cycles = sorted(
            f"{key} → {nxt}"
            for key in deps
            for nxt in deps[key]
            if reaches(nxt, key, set())
        )
        self.assertEqual(cycles, [], f"发现依赖环：{cycles}")

    def test_upper_layer_never_imports_lower_from_above(self):
        """上层可以被下层依赖，不能反过来依赖下层的上层。"""
        violations = []
        for key, path in self.modules.items():
            if "/" not in key:
                continue
            mine = LAYERS.get(key.split("/")[0])
            if mine is None:
                continue
            for level, target in imports_of(path):
                if level < 2:
                    continue
                other_pkg = target.split(".")[0]
                if other_pkg in TOP_LEVEL or other_pkg not in LAYERS:
                    continue
                theirs = LAYERS[other_pkg]
                if theirs > mine:
                    violations.append(f"{key} (L{mine}) → {other_pkg} (L{theirs})")
        self.assertEqual(violations, [], f"出现反向依赖：{violations}")

    def test_same_layer_packages_do_not_import_each_other(self):
        """同层之间不许互相 import——那说明这一层的边界划错了，或者该拆成两层。"""
        violations = []
        for key, path in self.modules.items():
            if "/" not in key:
                continue
            mine = key.split("/")[0]
            for level, target in imports_of(path):
                if level < 2:
                    continue
                other = target.split(".")[0]
                if other in LAYERS and LAYERS[other] == LAYERS[mine] and other != mine:
                    violations.append(f"{key} → {other}")
        self.assertEqual(violations, [], f"同层互相依赖：{violations}")

    def test_core_depends_on_nothing_inside(self):
        """core 是零件层：它只依赖标准库、第三方包和顶层公共件。"""
        violations = []
        for key, path in self.modules.items():
            if not key.startswith("core/"):
                continue
            for level, target in imports_of(path):
                if level < 2:
                    continue
                other = target.split(".")[0]
                if other in LAYERS:
                    violations.append(f"{key} → {other}")
        self.assertEqual(violations, [], f"core 混进了内部依赖：{violations}")

    def test_llm_is_imported_as_a_leaf(self):
        """llm.py 是被抽出来解环的：它自己不能反过来依赖任何包。

        这条是有来历的——模型客户端原本住在 ``answer/agent.py``，数据层要用就得反过来
        依赖编排层，于是 agent → retrieve → knowledge_graph → agent 成了环。
        """
        path = PKG / "llm.py"
        self.assertTrue(path.exists(), "llm.py 不该被删——它是解环的那个零件")
        for level, target in imports_of(path):
            if level >= 2:
                self.assertNotIn(target.split(".")[0], LAYERS,
                                 f"llm.py 又依赖了 {target}，环会回来")


if __name__ == "__main__":
    unittest.main()
