"""06_demo.py —— 第六步：无 API Key 的离线走查（工牌矩阵 / 证据资格 / 会话柜 / 图谱）。

用法：python scripts/06_demo.py
课前一分钟自检：装对了没有、权限裁得对不对、会话柜落不落盘，全都不用网络。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forge_lite.service.demo import run_all

if __name__ == "__main__":
    run_all()
