"""knowledge_graph.py —— 知识图谱：抽三元组 → 图存储 → 作为第三路召回进 RRF。

蒸馏来源：完整版 agents/knowledge_extractor + Neo4j 持久化（同款图数据库）。
对应教程：11.7（实体关系抽取与轻量图谱落地）。

双后端存储（同一套 GraphStore 接口）：
- Neo4jStore（默认，推荐）：真图数据库——Cypher 写入/查询、节点去重、属性索引；
  只需一个容器：docker run -d -p 7687:7687 -e NEO4J_AUTH=neo4j/forge12345 neo4j:5
  环境变量：FORGE_LITE_NEO4J_URI / FORGE_LITE_NEO4J_USER / FORGE_LITE_NEO4J_PASSWORD
- NetworkXStore（兜底）：没起 Neo4j 时的零依赖演示后端，落盘 runtime/graph.json。
  它只是内存对象序列化，没有 Cypher/索引/事务——只配演示，不配生产。
"""

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

from .. import config

GRAPH_JSON = config.RUNTIME_DIR / "graph.json"   # NetworkX 兜底后端的落盘文件
SEED_TRIPLES = config.BASE_DIR / "data" / "seed_triples.json"  # 离线第三路召回的垫底事实


class Triple(BaseModel):
    """一条知识三元组，也是交给模型的结构化输出契约。

    ``head`` 是头实体（尽量简短，如：一线城市住宿标准）、``relation`` 是关系
    （如：上限为 / 属于 / 处理方法是）、``tail`` 是尾实体。三个 ``Field`` 的
    ``description`` 会随 schema 一起递给模型，所以它们写的就是抽取时的要求——
    改这几句话等于改抽取质量，别当成普通注释随手删。

    用 Pydantic 而不是裸字典，是为了让模型必须吐出这三个字段：抽取是本流水线里
    唯一没法用规则兜底的环节，格式约束越早生效越好。
    """

    head: str = Field(description="头实体（尽量简短，如：一线城市住宿标准）")
    relation: str = Field(description="关系（如：上限为 / 属于 / 处理方法是）")
    tail: str = Field(description="尾实体")


class TripleList(BaseModel):
    """一次抽取的全部三元组，套一层是为了让结构化输出有确定的顶层形状。

    ``triples`` 是抽取结果列表，默认空——允许模型抽不出东西（文档本来就可能没有
    可提炼的知识），比强制它凑数编造更诚实。包这一层也让抽取结果的形状固定，
    入库脚本和测试不必先判断"顶层到底是列表还是对象"。
    """

    triples: list[Triple] = Field(default_factory=list, description="抽取到的三元组列表")


def extract_triples(text: str, source: str) -> list[dict]:
    """用 LLM 从一篇文档抽三元组（白名单式 Prompt 控制抽取范围，教程 11.7）。

    ``text`` 是这篇文档的全部切块拼起来的正文（内部只截前 3000 字：图谱要的是
    "这篇讲了什么"，不是逐字覆盖，超长文档硬塞进 Prompt 只会烧钱）。``source`` 是
    文件名，会被原样贴在每条三元组上——这条来源就是第三路召回把事实挂回切块的依据，
    丢了来源，图谱命中就没法指回原文，只能造出无出处的"幽灵块"。

    返回 ``[{head, relation, tail, source}]`` 的字典列表（不是 ``Triple`` 对象：
    下游要 JSON 落盘和按来源分组，字典更省事）。``llm`` 是延迟导入的——
    这个模块在只跑 NetworkX 兜底时不该因为装不上模型依赖而导不进来。
    """
    from ..llm import llm

    parser = llm.with_structured_output(TripleList)
    # 这里的提示词已经用 f-string 拼好了，所以直接喂字符串——不要再套一层
    # ``ChatPromptTemplate.from_template(...)``：那会把**模板对象**递给模型，
    # 而结构化输出那条链只接受字符串或消息列表，于是报
    # "Invalid input type ChatPromptTemplate"。这个坑踩过一次（05_build_graph.py 全挂），
    # 对照 agent.py 里的同款用法就能看出差别：那边多了一次 ``.format(...)``。
    prompt = (
        "从下面的企业文档中抽取知识三元组（头实体-关系-尾实体），要求：\n"
        "1. 只抽文档里明确写出的知识，禁止推测；最多 12 条；\n"
        "2. 实体名要简短完整（如\"差旅报销单\"而不是\"它\"）；\n"
        "3. 关系用短词（如：上限为 / 标准是 / 处理方法是 / 适用于）。\n\n"
        f"（来源：{source}）\n{text[:3000]}"
    )
    result = parser.invoke(prompt)
    return [{**t.model_dump(), "source": source} for t in result.triples]


def build_graph(chunks_json: Path | None = None) -> "GraphStore":
    """从 BM25 语料（与向量库同一份切块）按文档分组抽取，写入图存储。

    ``chunks_json`` 是切块 JSON 的路径，不传用 ``config.CHUNKS_JSON``——和检索读到的是
    同一份语料，图谱里的实体才可能指回检索看到的块。

    种子三元组先垫底（离线可复现），LLM 抽取再追加——完整版是抽取 Agent
    写图谱，Lite 用种子保证第三路召回课堂上一定能看见。

    按**文档**而不是按块抽：一段话里的"它""该标准"这类指代，只有放到全篇里才认得出
    指什么，按块抽会造出一堆没有主语的半截事实。返回写入用的 ``GraphStore``，
    调用方可以顺手 ``stats()`` 看看抽了多少。
    """
    chunks_json = chunks_json or config.CHUNKS_JSON
    by_source: dict[str, list[str]] = {}
    for c in json.loads(chunks_json.read_text(encoding="utf-8")):
        by_source.setdefault(c["source"], []).append(c["text"])

    triples: list[dict] = []
    if SEED_TRIPLES.exists():
        triples.extend(json.loads(SEED_TRIPLES.read_text(encoding="utf-8")))
    for source, texts in by_source.items():
        triples.extend(extract_triples("\n".join(texts), source))

    store = get_store()
    store.save(triples)
    return store


def _entity_hit(node: str, question: str) -> bool:
    """轻量实体链接：实体整串出现，或实体的任一二元组（如「住宿」）出现在问句中。

    这是有意的粗匹配——教学版宁可多召回一跳邻接交给 11.12 的分级闸门把关；
    生产版会换成实体链接模型 + 参数化 Cypher（见完整版 qa_query）。

    ``node`` 是图谱里的实体名，``question`` 是拼好的问句。返回 True 表示这个实体
    算被问到了：整串出现直接算，否则只要它任意相邻两字出现在问句里就算（"住宿费标准"
    命中问句里的"住宿"）。二元组匹配是让问法能松一点对上实体，代价是会误召回，
    所以结果必须交给后面那道路径把关，不能直接当答案。
    """
    if len(node) < 2:
        return False
    if node in question:
        return True
    return any(node[i:i + 2] in question for i in range(len(node) - 1))


# ---------------- 双后端：同一套接口 ----------------

class GraphStore:
    """图存储的接口契约：Neo4j 与 NetworkX 两个后端都按同一套方法说话。

    定这一层是为了让"换后端"只影响部署，不影响调用方：``build_graph`` / ``graph_hits``
    这些函数一行代码都不必知道跑的是真图数据库还是内存兜底。方法都带
    ``...`` 空实现（不是 ``raise NotImplementedError``）——这是纯文档性接口，
    真正干活的是下面两个子类。
    """

    def save(self, triples: list[dict]) -> None:
        """全量重建写入：先清空旧图，再写入 ``triples``（``[{head, relation, tail, source}]``）。

        语义是**重建**而不是增量：课堂每次入库都从一份完整的抽取结果重来，
        增量合并的边界（改名实体怎么算、删文档怎么清）不值得在这个阶段处理。
        """
        ...

    def entity_names(self) -> list[str]:
        """返回图里全部实体名，供实体链接（``_entity_hit``）逐个比对问句。"""
        ...

    def one_hop(self, entity: str, limit: int = 3) -> list[dict]:
        """取 ``entity`` 的一跳邻接，最多 ``limit`` 条，返回 ``[{head, rel, tail, source}]``。

        条数上限是防"以某个热门实体为中心节点"把整张图拖出来——邻接补全只是给
        答案添背景，不该成为上下文预算的大头。
        """
        ...

    def stats(self) -> tuple[int, int]:
        """返回 ``(实体数, 关系数)``，给入库脚本打印和图谱页显示用。"""
        ...

    def all_triples(self) -> list[dict]:
        """导出全量三元组（``[{head, relation, tail, source}]``），脚本展示与垫底合并用。"""
        ...


class Neo4jStore(GraphStore):
    """默认后端：真图数据库。写入 MERGE 去重，查询走 Cypher。"""

    def __init__(self, uri: str, user: str, password: str):
        """连上 Neo4j 并当场验活。``uri`` 是 ``bolt://host:7687`` 形式的地址，
        ``user`` / ``password`` 是认证信息（缺省密码见模块顶部的 docker 命令）。

        ``verify_connectivity()`` 是刻意加的：连不上就立刻抛错，而不是等第一次检索时
        才在图谱那一路炸出个看不懂的异常——那时候报错会混在"图谱降级"的日志里，
        排查成本高得多。``neo4j`` 包延迟导入，没装驱动的人用 NetworkX 兜底不受影响。
        """
        import neo4j
        self._driver = neo4j.GraphDatabase.driver(uri, auth=(user, password))
        self._driver.verify_connectivity()   # 连不上就当场报错，别让问题潜伏到检索时
        self.uri = uri

    def save(self, triples: list[dict]) -> None:
        """全量重建：先 ``DETACH DELETE`` 清空，再逐条 MERGE 写入。

        ``triples`` 是 ``[{head, relation, tail, source}]``。用 MERGE 而不是 CREATE：
        同一个实体在多条三元组里反复出现，MERGE 让节点和关系各自只留一份，
        查询时不会因为重复节点把一跳邻接撑出好几条一样的结果。
        """
        with self._driver.session() as s:
            s.run("MATCH (n) DETACH DELETE n")   # 教学语义：全量重建
            for t in triples:
                s.run(
                    "MERGE (a:Entity {name:$h}) "
                    "MERGE (b:Entity {name:$t}) "
                    "MERGE (a)-[r:RELATES {rel:$rel}]->(b) "
                    "SET r.source=$src",
                    h=t["head"], t=t["tail"], rel=t["relation"], src=t.get("source", ""),
                )

    def entity_names(self) -> list[str]:
        """返回图里全部实体名（走 Cypher ``MATCH (e:Entity)``），供实体链接逐个比对。"""
        with self._driver.session() as s:
            return [r["name"] for r in s.run("MATCH (e:Entity) RETURN e.name AS name")]

    def one_hop(self, entity: str, limit: int = 3) -> list[dict]:
        """取 ``entity`` 的一跳邻接，最多 ``limit`` 条。

        查询里的关系写成无方向的 ``-[r:RELATES]-``：抽出来的三元组方向未必可靠
        （"A 的上限是 B"和"B 属于 A"混着写），不区分方向才不至于把该轮也漏掉。
        返回 ``[{head, rel, tail, source}]``，字段名统一成 ``rel`` 和 ``all_triples``
        的 ``relation`` 不同——这是历史遗留，改字段名会打断已有的脚本和测试。
        """
        with self._driver.session() as s:
            rows = s.run(
                "MATCH (a:Entity {name:$e})-[r:RELATES]-(b:Entity) "
                "RETURN a.name AS head, r.rel AS rel, b.name AS tail, r.source AS source "
                "LIMIT $k", e=entity, k=limit,
            )
            return [dict(r) for r in rows]

    def stats(self) -> tuple[int, int]:
        """返回 ``(实体数, 关系数)``，两条计数查询分别走 Cypher，不做拼接。"""
        with self._driver.session() as s:
            n = s.run("MATCH (e:Entity) RETURN count(e) AS c").single()["c"]
            m = s.run("MATCH ()-[r:RELATES]->() RETURN count(r) AS c").single()["c"]
            return n, m

    def all_triples(self) -> list[dict]:
        """导出全量三元组，``[{head, relation, tail, source}]``（字段名带 ``relation`` 全称）。"""
        with self._driver.session() as s:
            rows = s.run(
                "MATCH (a:Entity)-[r:RELATES]->(b:Entity) "
                "RETURN a.name AS head, r.rel AS relation, b.name AS tail, r.source AS source"
            )
            return [dict(r) for r in rows]

    def close(self) -> None:
        """关掉驱动连接。脚本退出前调一次；常驻服务里不必每次查询都关。"""
        self._driver.close()


class NetworkXStore(GraphStore):
    """兜底后端：NetworkX + JSON 落盘。没有 Cypher/索引/事务，只配演示。"""

    def __init__(self):
        """只记一个空引用，图在读或写的时候才建——构造它不该产生任何磁盘访问。"""
        self._g = None

    def _load(self):
        """惰性加载：第一次用到时才建图，已有内存图就直接复用。

        落盘的 ``runtime/graph.json`` 只在内存为空时读一次，之后每次查询走内存，
        不反复读文件。文件不存在就返回空图（还没入过库是正常状态，不是错误）。
        返回 NetworkX 的 ``DiGraph``。
        """
        import networkx as nx
        if self._g is None:
            g = nx.DiGraph()
            if GRAPH_JSON.exists():
                for t in json.loads(GRAPH_JSON.read_text(encoding="utf-8")):
                    g.add_edge(t["head"], t["tail"], rel=t["relation"], source=t["source"])
            self._g = g
        return self._g

    def save(self, triples: list[dict]) -> None:
        """全量重建：拿 ``triples`` 新建一张图覆盖内存，再把**原始字典**落盘。

        ``triples`` 是 ``[{head, relation, tail, source}]``。落的是字典而不是序列化
        后的图对象：下次真要换 Neo4j 时，这份 JSON 能直接喂给 ``Neo4jStore.save``，
        不必先从图对象反解出三元组。写盘前先建目录，是因为 ``runtime/`` 在干净
        检出里并不存在，少这一句会让第一次入库以 FileNotFoundError 收场。
        """
        import networkx as nx
        g = nx.DiGraph()
        for t in triples:
            g.add_edge(t["head"], t["tail"], rel=t["relation"], source=t.get("source", ""))
        self._g = g
        config.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        GRAPH_JSON.write_text(json.dumps(triples, ensure_ascii=False, indent=2), encoding="utf-8")

    def entity_names(self) -> list[str]:
        """返回图里全部实体名（NetworkX 的节点集合，转成列表给调用方）。"""
        return list(self._load().nodes)

    def one_hop(self, entity: str, limit: int = 3) -> list[dict]:
        """取 ``entity`` 的一跳邻接，最多 ``limit`` 条。

        先取出边再取入边：出边是"从它出发"的事实（更可能在回答这个问题），
        入边是"指向它"的事实（补充说明）。入边循环里带 ``break``，是因为出边可能
        已经吃掉大半名额——两条循环共用一个 ``limit``，避免邻接条数翻倍。
        返回 ``[{head, rel, tail, source}]``；实体不在图里时返回空列表，不抛 KeyError。
        """
        g = self._load()
        out = []
        for _, v, d in list(g.out_edges(entity, data=True))[:limit]:
            out.append({"head": entity, "rel": d["rel"], "tail": v, "source": d.get("source", "")})
        for u, _, d in list(g.in_edges(entity, data=True)):
            if len(out) >= limit:
                break
            out.append({"head": u, "rel": d["rel"], "tail": entity, "source": d.get("source", "")})
        return out

    def stats(self) -> tuple[int, int]:
        """返回 ``(节点数, 边数)``。注意同名的多个关系会各算一条边，不做合并。"""
        g = self._load()
        return g.number_of_nodes(), g.number_of_edges()

    def all_triples(self) -> list[dict]:
        """导出全量三元组，``[{head, relation, tail, source}]``。

        边上的属性名是 ``rel``，这里翻成全称 ``relation`` 再出去，和 Neo4j 后端的
        输出对齐——两个后端返回的字典键必须一致，否则换后端就会静默改变下游的分组结果。
        """
        return [{"head": u, "relation": d["rel"], "tail": v, "source": d.get("source", "")}
                for u, v, d in self._load().edges(data=True)]


def get_store() -> GraphStore:
    """按环境变量选后端：设了 Neo4j 就用真图数据库，否则降级 NetworkX 演示兜底。"""
    uri = os.getenv("FORGE_LITE_NEO4J_URI")
    if uri:
        return Neo4jStore(uri,
                          os.getenv("FORGE_LITE_NEO4J_USER", "neo4j"),
                          os.getenv("FORGE_LITE_NEO4J_PASSWORD", ""))
    return NetworkXStore()


def load_seed_triples() -> list[dict]:
    """读种子三元组。文件缺了或坏了都返回空列表——课堂垫底不能变成崩溃点。"""
    if not SEED_TRIPLES.exists():
        return []
    try:
        payload = json.loads(SEED_TRIPLES.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _merge_triples(*groups: list[dict]) -> list[dict]:
    """按（头, 关系, 尾, 来源）去重合并。种子里有的事实不该被旧图存储挤掉。

    ``groups`` 是任意多组三元组，靠前的先入选（同名事实保留先出现的那条）。
    去重键带上 ``source`` 是故意的：同一个事实出自两篇文档就保留两条，
    引用时才能给出两处出处；只按（头, 关系, 尾）去重会让其中一篇的出处永远消失。

    返回合并后的列表；缺 ``head`` 的条目直接丢掉（没有头实体的三元组挂不回任何块）。
    """
    merged: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    for group in groups:
        for item in group or []:
            if not isinstance(item, dict):
                continue
            key = (
                str(item.get("head") or ""),
                str(item.get("relation") or ""),
                str(item.get("tail") or ""),
                str(item.get("source") or ""),
            )
            if not key[0] or key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _triples_from_store() -> list[dict]:
    """图存储 + 种子垫底，合并去重。

    种子三元组是课堂的保底事实：图存储还是旧版本（少了几篇文档）时，
    第三路也不该整条消失。入库脚本会把两者一起写进图存储。
    """
    stored: list[dict] = []
    try:
        stored = get_store().all_triples()
    except Exception:
        stored = []
    return _merge_triples(stored, load_seed_triples())


def graph_hits(queries: list[str], visible: list[dict], limit: int = 6) -> list[dict]:
    """第三路召回：实体一跳邻接 → 映射回可见切块（完整版 graph_retrieve 课堂版）。

    图谱命中必须能指回源文档切块，RRF 才能和向量/BM25 用同一把身份钥匙
    （``文件名#切块号``）。映射不上的事实直接丢掉，不另造「知识图谱」幽灵块。

    ``queries`` 是本次检索的查询列表（含改写结果，拼成一个问句用），``visible`` 是
    已过授权的可见切块（图谱也绝不能绕开权限），``limit`` 是这一路最多返回几块。

    返回挂回源文档的切块字典列表（带 ``source`` / ``chunk_index`` / ``text``），
    每个源文档最多一块：图谱的作用是"把相关文档捞进候选池"，同篇文档送多块只会
    挤占上下文预算，价值不如多覆盖一篇。返回空列表表示图谱这轮没捞到东西。
    """
    if not visible:
        return []
    question = " ".join(queries)
    triples = _triples_from_store()
    if not triples:
        return []
    ranked: list[dict] = []
    seen: set[str] = set()
    for triple in triples:
        head, tail = str(triple.get("head") or ""), str(triple.get("tail") or "")
        source = str(triple.get("source") or "")
        if not (_entity_hit(head, question) or _entity_hit(tail, question)):
            continue
        candidates = [chunk for chunk in visible if not source or chunk.get("source") == source]
        if not candidates:
            continue
        matched = [
            chunk for chunk in candidates
            if (head and head in (chunk.get("text") or "")) or (tail and tail in (chunk.get("text") or ""))
        ]
        # 每个源文档只留一块：优先实体字面命中，否则退回该文档第一块
        chosen = matched[:1] or candidates[:1]
        for chunk in chosen:
            key = f"{chunk['source']}#{chunk['chunk_index']}"
            if key in seen:
                continue
            seen.add(key)
            ranked.append(dict(chunk))
            if len(ranked) >= limit:
                return ranked
    return ranked


def graph_context(question: str, max_facts: int = 6) -> list[str]:
    """查询时的实体邻接补充（教程 11.7 的 Local Search 微缩版，脚本演示用）。

    ``question`` 是要补全的问题，``max_facts`` 是最多补几条事实。

    返回中文事实句列表，每条形如 ``头实体+关系+尾实体（来源：文件名）``——拼成人话
    是为了直接塞进 Prompt 或打印给人看，不必再由调用方拼装。全程包在 try 里：
    图谱是增强件，它挂了这一跑就不带图谱补充，不能把问答主链路一起拖下水。
    """
    try:
        facts, seen = [], set()
        for triple in _triples_from_store():
            head, tail = str(triple.get("head") or ""), str(triple.get("tail") or "")
            if _entity_hit(head, question) or _entity_hit(tail, question):
                rel = triple.get("relation") or triple.get("rel") or ""
                fact = f"{head}{rel}{tail}"
                if fact not in seen:
                    seen.add(fact)
                    facts.append(f"{fact}（来源：{triple.get('source') or '图谱'}）")
            if len(facts) >= max_facts:
                break
        return facts[:max_facts]
    except Exception as e:   # 图谱挂了不能拖死问答主链路
        print(f"[图谱降级] 邻接补充失败，本次问答不带图谱：{e}")
        return []


if __name__ == "__main__":
    store = get_store()
    n, m = store.stats()
    print(f"图谱：{n} 实体 / {m} 关系（后端：{type(store).__name__}）")
    print("试查「出差住宿」的图谱补充：")
    for f in graph_context("出差住宿标准"):
        print(" -", f)
