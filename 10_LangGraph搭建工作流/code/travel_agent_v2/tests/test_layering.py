"""分层守卫：把「搬家搬出来的」几类事故写成静态检查（零 Key、秒级、不连库）。

运行：uv run python tests/test_layering.py   （在 travel_agent_v2 目录内执行）

为什么要有这个文件：规矩写在文档里等于没写。下一次有人挪个文件、顺手添一句 import，
坏掉的是运行时——页面白屏、库读不到、图片 404，而且**不报错**，最难查。所以这里把
六条规矩钉住（前五条走 AST，第六条扫注释与文档文本）：

1. **不许按值 import「会被重新绑定的模块变量」**：`from web.runtime.hub import GRAPH`
   抓到的是 import 那一刻的 None，图编译完了它还是 None。本仓真踩过（GRAPH / BUSY）。
2. **不许在 infra/paths.py 之外出现 `__file__`**：按 `__file__` 往上数两层算路径，
   文件一换目录深度就静默错位——`web/present/explore.py` 找不到业务库就是这么来的。
3. **不许在 infra/paths.py 之外写 `.sqlite` 字面量**：四个业务工具各抄了一份库文件名，
   改目录要追着改四处。
4. **不许在 infra/paths.py 之外读 `TRIP_DESK_DB_DIR`**：同一个测试开关被两处各解析一遍，
   哪天改了名字就只改到一处。
5. **层与层的方向**：`infra < memory < tools < agent < main < web`，内层不许认识外层
   （`agent/` 不许 import `web/`）。
6. **不许再提已经不存在的旧路径**（`core/`、`web/views.py`、`tools/db_init` …）：搬家之后
   注释与文档里的路径最容易烂在原地，读的人顺着找过去只会扑空。这条检查的是**散文**
   （注释、docstring、markdown），所以它是唯一按文本扫、不走 AST 的一条。

检查只读源码、只做语法分析，不 import 被测模块——所以不挑环境，也不会因为缺 Key、
缺库文件而失败。`tests/` 在规矩 2/3/4/6 上豁免（测试本来就要临时目录、临时库名，
本文件自己也要写出那些旧路径），但规矩 1 与 5 照样管测试代码。
"""
import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")     # 允许从项目根之外启动

ROOT = Path(__file__).resolve().parent.parent      # tests/ 的上一层 = 项目根
# `.impeccable/` 是设计工具的本地产物（已 gitignore），里面记的是当时的目标文件路径，
# 属于「历史留档」而不是本仓要维护的文档，所以不扫。
# `static/` **不跳过**：`app.js` 与 `img/CREDITS.md` 都是要维护的文本，规矩 6 得看住它们。
SKIP_DIRS = {"__pycache__", "db", "logs", ".git", "node_modules", ".impeccable"}

# 虚拟环境按「长得像」判，而不是只认 `.venv` 这一个名字。教训：重建环境时把旧的
# 改名成 `.venv-before-uv-sync/` 放在旁边当回滚，守卫立刻把那个环境里成百上千行
# 第三方代码的 `__file__` 全当成违规报了出来——守卫该扫的是这个仓库，不是依赖包。
VENV_NAMES = {"venv", "env", "site-packages"}


def _is_local_artifact(rel: Path) -> bool:
    """这个相对路径要不要跳过（工具产物 / 虚拟环境 / 缓存）。

    :param rel: 相对项目根的路径
    :return: True 表示不属于本仓要维护的源码与文本，跳过
    """
    for part in rel.parts:
        if part in SKIP_DIRS or part in VENV_NAMES:
            return True
        if part.startswith(".venv"):        # .venv / .venv-before-uv-sync / .venv.bak …
            return True
    return False

# 层序：索引小的在内层。内层只许 import 自己或更内层，`main` 是总装、`web` 是最外层。
STACK = ["infra", "memory", "tools", "agent", "main", "web"]

# 这几条规矩的唯一豁免者（路径与库名的唯一出处）
PATHS_MODULE = "infra.paths"

# 规矩 6：已经不存在了的旧路径。搬完家忘了改注释，读的人会顺着找过去扑空。
# 每条写成正则片段（不含前后边界），匹配时统一加「左边不能是单词字符」的边界，
# 免得 `langchain_core/` 被 `core/` 误伤。
LEGACY_PATHS = [
    r"core/context_window",       # → agent/context.py
    r"core/memory_store",         # → memory/store.py
    r"core/graph_builder",        # → agent/graph.py
    r"core/primary_agent",        # → agent/primary.py
    r"core/sub_agents",           # → agent/specialists.py
    r"core/llm_config",           # → infra/llm.py
    r"core/state\.py",            # → agent/state.py
    r"core/models\.py",           # → agent/models.py
    r"core/utils\.py",            # → infra/logging.py + agent/nodes.py
    r"core/",                     # 整个包都没了
    r"web/views\.py",             # → web/present/views.py
    r"web/art\.py",               # → web/present/art.py
    r"web/cities\.py",            # → web/present/cities.py
    r"web/cards\.py",             # → web/present/cards.py
    r"web/explore\.py",           # → web/present/explore.py
    r"web/geo\.py",               # → web/present/geo.py
    r"web/labels\.py",            # → web/present/labels.py
    r"web/runtime\.py",           # → web/runtime/ 包
    r"tools/db_init",             # → infra/biz_db.py
    r"tools/seed_cn_data",        # → infra/scripts/seed_cn_data.py
    r"tools/fetch_assets",        # → infra/scripts/fetch_assets.py
    r"tools/location_trans",      # → infra/scripts/location_trans.py
]

# 规矩 6 扫这些后缀：注释与文档都在里头
PROSE_SUFFIXES = (".py", ".js", ".md")


def _module_name(rel: Path) -> str:
    """文件相对路径 → 模块名（`web/present/art.py` → `web.present.art`）。

    :param rel: 相对项目根的路径
    :return: 点分模块名；包的 `__init__.py` 归到包名本身
    """
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _layer_of(module: str) -> int | None:
    """模块名 → 层索引（认不出的返回 None：顶层散文件如 `langgraph.json` 之类不管）。

    :param module: 点分模块名
    :return: `STACK` 里的下标，或 None
    """
    head = module.split(".")[0]
    return STACK.index(head) if head in STACK else None


def _resolve_relative(rel: Path, level: int, module: str | None) -> str:
    """把相对 import 拼成绝对模块名（`from .x import y` 在包内 → `包.x`）。

    :param rel: 发起 import 的文件（相对项目根）
    :param level: `ast.ImportFrom.level`，1 表示同包
    :param module: `ast.ImportFrom.module`，可能为 None
    :return: 点分模块名
    """
    package = _module_name(rel).split(".")[:-1]        # 去掉文件名，留下所在包
    base = package[: len(package) - (level - 1)] if level > 1 else package
    return ".".join(base + ([module] if module else []))


def _docstring_nodes(tree: ast.Module) -> set[int]:
    """收集所有 docstring 字面量节点的 id。

    规矩 3 / 4 只管**代码**：文档里写清「库在 db/app.sqlite」是好事，不该被判违规。

    :param tree: 一棵解析好的语法树
    :return: docstring 常量节点的 id 集合（用 id 因为 AST 节点不可哈希）
    """
    marks = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            marks.add(id(first.value))
    return marks


def _scan() -> dict:
    """把全仓源码解析一遍，收集前五条规矩各自关心的东西（一次解析，多个检查共用）。

    第六条不看语法树、只看文本，所以在这里不参与（它自己读文件扫注释与文档）。

    :return: 含 rebound / imports / file_refs / sqlite_literals / env_refs 的字典，
             每项都是「文件、行号、说明」三元组或等价结构
    """
    found = {
        "rebound": {},        # 模块名 -> {被重新绑定的变量名: 行号}
        "imports": [],        # (文件, 行号, 目标模块, 变量名)
        "file_refs": [],      # (文件, 行号)
        "sqlite_literals": [],
        "env_refs": [],
    }
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT)
        if _is_local_artifact(rel):
            continue
        module = _module_name(rel)
        tree = ast.parse(path.read_text(encoding="utf8"))
        docstrings = _docstring_nodes(tree)

        for node in ast.walk(tree):
            # 规矩 1：收集「函数里 global 声明的名字」= 会被重新绑定的模块变量
            if isinstance(node, ast.Global):
                found["rebound"].setdefault(module, {}).update(
                    {name: node.lineno for name in node.names}
                )

            # 规矩 1：收集所有按值 import
            if isinstance(node, ast.ImportFrom):
                target = (
                    node.module or ""
                    if node.level == 0
                    else _resolve_relative(rel, node.level, node.module)
                )
                for alias in node.names:
                    found["imports"].append((str(rel), node.lineno, target, alias.name))

            # 规矩 2：`__file__` 出现即违规（本仓只允许 infra/paths.py 用）
            if isinstance(node, ast.Name) and node.id == "__file__":
                found["file_refs"].append((str(rel), node.lineno))

            # 规矩 3 / 4：字符串里出现库文件名或那个测试开关（docstring 豁免；
            # f-string 也拆开看——`f"db/{name}.sqlite"` 正是要拦的形状）
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) in docstrings:
                    continue
                fragments = [node.value]
            elif isinstance(node, ast.JoinedStr):
                fragments = [
                    part.value
                    for part in node.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                ]
            else:
                fragments = []
            for text in fragments:
                if ".sqlite" in text:
                    found["sqlite_literals"].append((str(rel), node.lineno, text[:60]))
                if "TRIP_DESK_DB_DIR" in text:
                    found["env_refs"].append((str(rel), node.lineno, text[:60]))
    return found


_SCAN = None


def _scan_cached() -> dict:
    """解析结果只算一次（五个用例共用一个进程时省点事）。

    :return: 同 `_scan()`
    """
    global _SCAN
    if _SCAN is None:
        _SCAN = _scan()
    return _SCAN


def _fmt(items) -> str:
    """把违规列表排成一段可读的失败信息（文件:行）。

    :param items: 迭代器，元素是至少含「文件、行号」的元组/字符串
    :return: 每个违规一行
    """
    lines = []
    for item in items:
        if isinstance(item, str):
            lines.append("  - " + item)
        else:
            lines.append("  - " + ":".join(str(part) for part in item if part is not None))
    return "\n".join(lines)


def test_no_by_value_import_of_rebound_globals():
    """规矩 1：被 `global` 重新绑定的名字，别处一律走模块属性（`hub.GRAPH`）或访问器。

    这类 bug 的形状是：变量在 import 时是 None，之后的赋值只改了自己模块的名字，
    import 方手里的那份副本永远停在 None。改成 `hub.GRAPH`（模块属性查表）就活了。
    """
    scan = _scan_cached()
    bad = []
    for path, line, target, name in scan["imports"]:
        rebound = scan["rebound"].get(target)
        if rebound and name in rebound:
            bad.append(
                f"{path}:{line} 按值 import 了 {target}.{name}"
                f"（它在该模块第 {rebound[name]} 行被 global 重新绑定）——"
                f"改成 `import {target}` 后用 `{target}.{name}`，或走访问器函数"
            )
    assert not bad, "按值 import 了会被重新绑定的模块变量：\n" + _fmt(bad)


def test_no_file_path_math_outside_paths():
    """规矩 2：路径推算只许待在 infra/paths.py（`__file__` 出别处就报）。

    按 `__file__` 往上数层数，等于把「这个文件在目录树的第几层」写进了代码；
    一搬家就静默错位。要新路径就加在 `infra/paths.py` 里，然后 import。
    """
    scan = _scan_cached()
    bad = [
        f"{path}:{line} 用到了 __file__——路径推算请写进 {PATHS_MODULE}，别处 import 它"
        for path, line in scan["file_refs"]
        if path != "infra/paths.py" and not path.startswith("tests/")
    ]
    assert not bad, "infra/paths.py 之外出现了 __file__：\n" + _fmt(bad)


def test_no_sqlite_filename_outside_paths():
    """规矩 3：库文件名只许在 infra/paths.py 写一次。

    以前四个业务工具各写一份同样的路径字符串，改目录要追着改四处（还容易漏一处，
    漏掉的那个会连到别的库上去，且不报错）。
    """
    scan = _scan_cached()
    bad = [
        f"{path}:{line} 写了库文件名 {text!r}——请从 {PATHS_MODULE} import 现成常量"
        for path, line, text in scan["sqlite_literals"]
        if path != "infra/paths.py" and not path.startswith("tests/")
    ]
    assert not bad, "infra/paths.py 之外出现了库文件名字面量：\n" + _fmt(bad)


def test_no_env_override_reread_outside_paths():
    """规矩 4：`TRIP_DESK_DB_DIR` 只在 infra/paths.py 解析一次。

    同一个开关被两个模块各解析一遍，就会出现「改了一处、另一处忘了」的经典事故；
    而且两个模块必须都记得在建连接前把目录造出来。
    """
    scan = _scan_cached()
    bad = [
        f"{path}:{line} 又读了一遍 {text!r}——请从 {PATHS_MODULE} import 已解析好的常量"
        for path, line, text in scan["env_refs"]
        if path != "infra/paths.py" and not path.startswith("tests/")
    ]
    assert not bad, "infra/paths.py 之外又解析了 TRIP_DESK_DB_DIR：\n" + _fmt(bad)


def test_layer_direction():
    """规矩 5：内层不许认识外层（`infra < memory < tools < agent < main < web`）。

    分层解耦的判据只有一句「谁认识谁」：业务工具不该知道工作台长什么样，
    大脑不该知道浏览器、HTTP、页面；要串起来由 `main.py` 总装去串。
    """
    scan = _scan_cached()
    bad = []
    for path, line, target, name in scan["imports"]:
        here, there = _layer_of(_module_name(Path(path))), _layer_of(target)
        if here is None or there is None or there <= here:
            continue
        bad.append(
            f"{path}:{line} 从 {STACK[here]}/ 里 import 了更外层的 {target}"
            f"（层序：{' < '.join(STACK)}）"
        )
    assert not bad, "出现了从内层指向外层的依赖：\n" + _fmt(bad)


def test_no_legacy_paths_in_comments_and_docs():
    """规矩 6：注释 / docstring / markdown 里不许再提已经搬走的旧路径。

    为什么值得单列一条：这四类毛病里，只有「路径写错」是**人眼读代码时最容易发现、
    机器最难发现**的——它不报错、不影响运行、ruff 也管不着，只有人顺着注释去找文件
    才会扑空。搬完家我漏了十来处（脚本用法、CREDITS 里的抓取脚本、app.js 的下线说明…），
    所以把它变成一条测试。范围是整个应用的文本文件，但跳过 `tests/`（本文件自己就得
    列出这些旧路径）与本地工具产物目录。
    """
    bad = []
    patterns = [(token, re.compile(r"(?<![A-Za-z0-9_])" + token)) for token in LEGACY_PATHS]
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT)
        if not path.is_file() or path.suffix not in PROSE_SUFFIXES:
            continue
        if _is_local_artifact(rel) or rel.parts[0] == "tests":
            continue
        text = path.read_text(encoding="utf8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for token, pattern in patterns:
                hit = pattern.search(line)
                if hit:
                    bad.append(
                        f"{rel}:{lineno} 还在提旧路径 `{token}`（{line.strip()[:60]}）"
                        f"——文件早搬走了，写成新路径或删掉这句话"
                    )
    assert not bad, "注释与文档里还留着不存在的旧路径：\n" + _fmt(bad)


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"✅ {name}")
            except AssertionError as e:
                failed += 1
                print(f"❌ {name}: {e}")
    print(f"\n{'全部通过' if not failed else f'{failed} 个用例失败'}")
    sys.exit(1 if failed else 0)
