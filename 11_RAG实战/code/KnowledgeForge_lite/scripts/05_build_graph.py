"""05_build_graph.py —— 第五步：构建知识图谱（教程 11.7 落地）。

用法：python scripts/05_build_graph.py
  - 入库已经垫了 data/seed_triples.json，第三路召回默认就能走；
  - 本脚本再用 LLM 从种子文档补抽三元组 → 写入图存储（默认首选 Neo4j）；
    图谱命中会映射回源文档切块，和向量/BM25 一起进 RRF，而不是事后加餐。

图数据库（默认推荐，与完整版同款）：
      docker run -d --name neo4j -p 7474:7474 -p 7687:7687 \\
        -e NEO4J_AUTH=neo4j/forge12345 neo4j:5
  然后在 .env / 环境变量里配置：
      FORGE_LITE_NEO4J_URI=bolt://localhost:7687
      FORGE_LITE_NEO4J_USER=neo4j
      FORGE_LITE_NEO4J_PASSWORD=forge12345
  建库后打开 http://localhost:7474 可视化浏览，Cypher 抽查：
      MATCH (a)-[r:RELATES]->(b) RETURN a,r,b LIMIT 25

  未设置上述环境变量时自动降级为 NetworkX 演示后端（runtime/graph.json，
  无 Cypher/索引/事务，只配演示不配生产）。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forge_lite.data.knowledge_graph import build_graph, get_store, graph_context

if __name__ == "__main__":
    store = build_graph()
    n, m = store.stats()
    print(f"图谱构建完成：{n} 实体 / {m} 关系（后端：{type(store).__name__}）")
    print("\n关系示例（前 10 条）：")
    for t in store.all_triples()[:10]:
        print(f"  {t['head']} -[{t['relation']}]-> {t['tail']}   （{t['source']}）")

    if hasattr(store, "uri"):
        print(f"\nNeo4j 控制台：http://localhost:7474（浏览器可视化浏览图谱）")
    else:
        print("\n（当前为 NetworkX 演示后端。要上真图数据库，按本脚本头注释起 Neo4j 容器并配置环境变量）")

    print("\n试查「出差住宿」的图谱补充：")
    for f in graph_context("出差住宿标准"):
        print(" -", f)
