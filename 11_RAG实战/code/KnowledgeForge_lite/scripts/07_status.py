"""07_status.py —— 第七步：运行时体检（索引 / 图谱 / 会话柜 / 账本）。

用法：python scripts/07_status.py
课前自检、排障第一步。只读，不改任何运行产物。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forge_lite.service.status import build_report, render_report

if __name__ == "__main__":
    print(render_report(build_report()))
