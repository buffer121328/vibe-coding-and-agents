"""01_ingest.py —— 第一步：把 data/docs 同步进向量库 + BM25 + 种子图谱。

用法：python scripts/01_ingest.py
重复执行是幂等的：内容没变的文档会被跳过（教程 11.13 的内容哈希同步）。
切块会打上部门 / 密级（11.13 ACL）；种子三元组垫进图存储，问答时作为第三路召回。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forge_lite.data.ingest import ingest

if __name__ == "__main__":
    stats = ingest()
    print("入库完成：", stats)
    if stats.get("quarantined"):
        print(f"⚠️ 隔离 {stats['quarantined']} 篇（投毒扫描命中，未进检索索引，见教程 11.13）")
    print("→ 下一步：python scripts/02_ask.py \"去上海出差住一晚能报多少？\"")
    print("   权限对照：python scripts/02_ask.py \"P6 薪酬带宽是多少？\" it_staff")
    print("             python scripts/02_ask.py \"P6 薪酬带宽是多少？\" finance_head")
