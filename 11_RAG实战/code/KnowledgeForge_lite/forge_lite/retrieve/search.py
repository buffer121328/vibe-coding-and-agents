"""retrieve/search.py —— 三路检索：向量 + BM25 + 图谱，先裁权限再 RRF。

蒸馏来源：完整版 services/qa/retrievers.py + ranking.hybrid_rerank。
对应教程：11.4（向量库）、11.5（RRF 混合 / 去重装箱 / 首尾编排）、
11.7（图谱作为第三路召回）、11.13（检索层 ACL）。

完整版顺序不可改：授权范围 → 三路并行召回 → RRF（带来源权重）→ 可选 Cross-Encoder。
Lite 同步走同一顺序，图谱挂了记降级码，不拖死主链路。教学版省略 Cross-Encoder。
"""

from __future__ import annotations

import json
import re

import numpy as np
from rank_bm25 import BM25Okapi

from .. import config
from ..core.identity import Actor, authorize_chunks, resolve_actor
from ..core.quality import SOURCE_WEIGHTS, explain_retrieval, order_contexts, reciprocal_rank_fusion


# jieba 的静态词典是懒加载的：第一次调用要建前缀树（约 300ms）并落一份缓存，
# 之后就近似零成本。这 300ms 不该落在第一个用户请求上，所以启动时显式预热一次。
# 「这个 token 里有真字吗」——汉字、字母、数字都算；纯标点与空白不算
_HAS_WORD_CHAR = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbfA-Za-z0-9]")

_JIEBA_READY = False


def warm_tokenizer() -> bool:
    """预热分词词典，避免第一个请求吃那 300ms 的建表开销。

    返回 True 表示 jieba 可用（已预热），False 表示这条路不可用、
    分词已回落到二元组。服务启动时调一次即可；测试里不必调，影响只是首次稍慢。
    """
    global _JIEBA_READY
    if _JIEBA_READY:
        return True
    try:
        import jieba

        jieba.initialize()
    except Exception as exc:  # 没装或初始化失败都只是降级，不该让服务起不来
        print(f"[分词降级] jieba 不可用，BM25 改用二元组：{exc}")
        return False
    _JIEBA_READY = True
    return True


def _bigram_tokens(text: str) -> list[str]:
    """零依赖的兜底切词：中文切相邻二元组，英文按整词。

    ``text`` 是要切的查询或正文。中文词之间没有空格，二元组是**不装词典**时最接近
    "词"的近似——它在每个字的边界上都下刀，所以任何两字词都必然作为其中一个二元组
    出现（「上海」「出差」都跑不掉），代价是词表膨胀一倍多、且切不出三字以上的词。

    整段只有一个汉字时退化成把那个字本身当一项，否则单字查询的 BM25 向量会全零、
    得分恒为 0。返回 token 列表。
    """
    latin = re.findall(r"[A-Za-z0-9]+", text)
    han = re.sub(r"[^\u4e00-\u9fff]", "", text)
    bigrams = [han[i:i + 2] for i in range(len(han) - 1)] or ([han] if han else [])
    return latin + bigrams


def _tokenize(text: str) -> list[str]:
    """切词：jieba 分词为主，没用上就退回二元组。

    ``text`` 是要切分的查询或正文，中英混排也一样处理。

    为什么不只在查询侧分词：BM25 的"词"必须**索引侧和查询侧用同一把刀**，
    两边切法不一致时词面对不上，检索会静默地退化——不报错，只是召回变差。

    为什么还留二元组：jieba 是可选依赖，没装或初始化失败时要有一条能走的路。
    两条路的切法不同，但**同一次运行里只会用其中一条**（`_JIEBA_READY` 决定），
    所以不存在索引与查询用不同刀的情况。

    返回 token 列表，**保留重复**：BM25 吃词频，去重会把「住宿住宿」这类强调信号抹掉。
    """
    if _JIEBA_READY:
        import jieba

        tokens = []
        for piece in jieba.lcut(text or ""):
            piece = piece.strip()
            # 只丢纯标点：jieba 把「，」「。」也当 token 吐出来，它们没有任何词面信息，
            # 留在索引里只是把小语料的 IDF 搅浑。
            if piece and _HAS_WORD_CHAR.search(piece):
                tokens.append(piece)
        return tokens
    return _bigram_tokens(text)


def load_corpus() -> tuple[list[dict], BM25Okapi]:
    """读切块语料并就地建好 BM25 索引，返回 ``(chunks, bm25)``。

    ``chunks`` 是原始切块字典列表，``bm25`` 是用同一批文本建好的检索器——
    两者必须配套使用：BM25 的得分按下标对应 ``chunks``，索引和列表错位一位就会
    召回"隔壁那一块"，而且召回的文本看着也相关，几乎不可能被发现。

    这里读的是和向量库同一份 ``config.CHUNKS_JSON``（"BM25 同源语料"），
    保证两路召回看到的是同一批块、同一套 id。没入库时文件不存在会直接抛异常——
    和 ``catalog.load_chunks`` 的宽容取向不同，检索路径上静默返回空会让"库空"
    伪装成"没搜到"。
    """
    chunks = json.loads(config.CHUNKS_JSON.read_text(encoding="utf-8"))
    bm25 = BM25Okapi([_tokenize(c["text"]) for c in chunks])
    return chunks, bm25


def rrf_fuse(
    rankings: list[list[str]],
    k: int = config.RRF_K,
    weights: list[float] | None = None,
) -> list[str]:
    """手写 RRF：每个列表按名次给 weight/(k+rank) 分，总分排序（教程 11.5）。

    ``rankings`` 是各路召回结果，内层按名次从高到低存 ``文件名#切块号``；``k`` 是名次
    平滑项（默认取 ``config.RRF_K``，量级 60）；``weights`` 与 ``rankings`` 等长，
    按来源给权（图谱 1.05），不传则每路等权。

    这里只返回排好序的 key 列表、不带分数，因为调用方紧接着要按 ``fused_rank``
    重排上下文（``order_contexts`` 用的是名次而不是分数）——把分数传出去反而会诱使
    别人拿它跨路比大小。真正的加权计分在 ``quality.reciprocal_rank_fusion``，
    两处只有一份实现，避免"课上一种算法、总装里又手写一份"。
    """
    return [doc_id for doc_id, _ in reciprocal_rank_fusion(rankings, rank_constant=k, weights=weights)]


def _chunk_key(chunk: dict) -> str:
    """切块的全局身份钥匙：``文件名#切块号``，三路召回共用它对齐。

    ``chunk`` 是切块字典。向量路拿到的是 metadata、BM25 路拿到的是语料条目、
    图谱路拿到的是挂回源文档的块——三者的对象形状不同，只有这个字符串是同一把钥匙。
    跨路对齐一旦不用同一把钥匙，RRF 就会把同一块算成两条，融合结果里出现重复上下文。
    """
    return f"{chunk['source']}#{chunk['chunk_index']}"


def _pack_hits(hits: list[dict], max_chars: int) -> list[dict]:
    """先去近重复，再按字符预算装箱（11.5）。超过预算的块直接丢掉，不截断半句。

    ``hits`` 是排好序的命中列表（顺序即优先级），``max_chars`` 是上下文总预算。
    返回装进预算的子列表，保持原相对顺序。

    第一个块无条件装（``if used and ...`` 里的 ``used`` 就是这个意思）：排在最前面的
    那块往往最相关，如果它单独就超过预算，装不下就整段丢掉，模型手上会一块资料都没有。
    宁可超一点预算，也不能让最该看的那块消失。
    """
    from ..core.quality import deduplicate_contexts
    keep = set(deduplicate_contexts([h["text"] for h in hits]))
    packed, used, seen = [], 0, set()
    for hit in hits:
        text = hit["text"]
        if text not in keep or text in seen:
            continue
        if used and used + len(text) > max_chars:
            continue
        packed.append(hit)
        used += len(text)
        seen.add(text)
    return packed


def _graph_hits(queries: list[str], visible: list[dict], fetch: int) -> tuple[list[dict], str | None]:
    """第三路：图谱邻接。命中的事实挂回源文档切块；图谱挂了返回空 + 降级码。

    ``queries`` 是本次要检索的查询（含改写结果），``visible`` 是已过授权的可见切块
    （图谱命中也要先裁权限，不能绕开），``fetch`` 是这一路取多少条候选。

    返回 ``(命中列表, 降级码)``：正常时降级码为 None；图谱抛异常或没开
    （``config.ENABLE_GRAPH``）时返回空列表。没开图谱不算降级，不算进降级码里——
    关了它是配置选择，不是故障，报成降级会让 trace 上天天飘着假告警。
    """
    if not config.ENABLE_GRAPH:
        return [], None
    try:
        from ..data.knowledge_graph import graph_hits
        return graph_hits(queries, visible, limit=fetch), None
    except Exception as exc:  # 图谱是增强件，不能变成单点故障
        print(f"[图谱降级] 第三路召回失败，本次只走向量+BM25：{exc}")
        return [], "graph_unavailable"


def hybrid_search(
    query: str | list[str],
    top_k: int = config.TOP_K,
    max_chars: int | None = None,
    actor: Actor | str | None = None,
) -> list[dict]:
    """授权裁剪 → 三路召回 → 加权 RRF → 首尾编排 → 预算装箱。

    ``query`` 可以是原问题，也可以是 11.6 改写后的查询列表（原问题必须在第一位）；
    空列表直接返回空，不去打向量库。``top_k`` 是最终返回条数，同时也是每路召回的
    抓取倍数基数（内部取 ``top_k * 2`` 条候选再融合，留出被 RRF 重排淘汰的余量）。
    ``max_chars`` 是上下文字符预算，不传用 ``config.CONTEXT_BUDGET``。
    ``actor`` 是提问人（``Actor`` / 工牌 id / None），**在打分之前**用来裁可见范围。

    返回 ``[{source, chunk_index, text, rank, fused_rank, why, route, route_rank,
    degraded, ...}]``——``rank`` 从 0 起、``fused_rank`` 从 1 起（前者给代码用、
    后者给人看），``why`` 是中文召回理由，``degraded`` 图谱降级时带回降级码。
    actor 可见库为空时直接返回空列表：没有可见资料，就不必付向量检索的延迟。
    """
    import chromadb
    from chromadb.utils import embedding_functions

    queries = [query] if isinstance(query, str) else [q for q in query if q]
    if not queries:
        return []
    person = resolve_actor(actor)
    max_chars = config.CONTEXT_BUDGET if max_chars is None else max_chars
    chunks, _ = load_corpus()
    visible = authorize_chunks(chunks, person)
    if not visible:
        return []
    index = {(c["source"], c["chunk_index"]): c for c in visible}
    bm25 = BM25Okapi([_tokenize(c["text"]) for c in visible])

    ef = embedding_functions.OpenAIEmbeddingFunction(
        api_key=config.OPENAI_API_KEY or None,
        api_base=config.OPENAI_API_BASE or None,
        model_name=config.EMBED_MODEL,
    )
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    col = client.get_collection("forge_lite", embedding_function=ef)

    rankings: list[list[str]] = []
    ranking_weights: list[float] = []
    lookup: dict[str, dict] = {}
    route_rank: dict[str, list[tuple[str, int]]] = {}
    fetch = top_k * 2
    allowed_sources = list({c["source"] for c in visible})

    for q in queries:
        bm_ids = np.argsort(bm25.get_scores(_tokenize(q)))[::-1][:fetch]
        bm_ranking = [visible[i] for i in bm_ids]
        bm_keys = [_chunk_key(c) for c in bm_ranking]
        rankings.append(bm_keys)
        ranking_weights.append(SOURCE_WEIGHTS["bm25"])
        for rank, chunk in enumerate(bm_ranking, 1):
            key = _chunk_key(chunk)
            lookup[key] = chunk
            route_rank.setdefault(key, []).append(("bm25", rank))

        where: dict = {"acl": {"$in": ["employee", "restricted"]}}
        if allowed_sources:
            where = {"$and": [where, {"source": {"$in": allowed_sources}}]}
        vec = col.query(
            query_texts=[q],
            n_results=min(fetch, max(len(visible), 1)),
            where=where,
        )
        metadatas = (vec.get("metadatas") or [[]])[0] or []
        vec_keys = []
        for rank, meta in enumerate(metadatas, 1):
            pair = (meta.get("source"), meta.get("chunk_index"))
            if pair not in index:
                continue
            chunk = index[pair]
            key = _chunk_key(chunk)
            vec_keys.append(key)
            lookup[key] = chunk
            route_rank.setdefault(key, []).append(("dense", rank))
        if vec_keys:
            rankings.append(vec_keys)
            ranking_weights.append(SOURCE_WEIGHTS["vector"])

    graph_ranking, graph_degraded = _graph_hits(queries, visible, fetch)
    graph_keys = []
    for rank, chunk in enumerate(graph_ranking, 1):
        key = _chunk_key(chunk)
        graph_keys.append(key)
        lookup[key] = chunk
        route_rank.setdefault(key, []).append(("graph", rank))
    if graph_keys:
        rankings.append(graph_keys)
        ranking_weights.append(SOURCE_WEIGHTS["graph"])

    fused = rrf_fuse(rankings, weights=ranking_weights) if rankings else []
    scores = {key: 1.0 / (i + 1) for i, key in enumerate(fused)}

    # 顺序要紧：**先按相关度装箱，再对装进来的做首尾编排**。
    # 反过来写会踩一个不显眼的坑：order_contexts 为了对抗 lost-in-the-middle 把榜眼
    # 放到列表最末，而 _pack_hits 是按预算从尾部截断的——于是"预算不够"时第一个被砍掉的
    # 正是那个被特意安排到结尾、最该给模型看的第二名。谁进得来必须由相关度决定，
    # 进来之后怎么摆才是编排的事。
    hits = []
    for key in fused:
        chunk = lookup[key]
        routes = route_rank.get(key) or [("hybrid", 0)]
        primary_route, primary_rank = routes[0]
        hits.append({
            **chunk,
            "rank": len(hits),
            "fused_rank": len(hits) + 1,
            "route": "+".join(sorted({r for r, _ in routes})),
            "route_rank": primary_rank,
            "degraded": graph_degraded,
        })

    packed = _pack_hits(hits, max_chars)[:top_k]

    # 装进预算的这些才轮到编排：榜首占开头、榜眼占结尾，中间按升序
    by_key = {_chunk_key(hit): hit for hit in packed}
    ordered = order_contexts([(_chunk_key(hit), scores.get(_chunk_key(hit), 0.0)) for hit in packed])
    final = [by_key[key] for key in ordered if key in by_key]

    explained = explain_retrieval([
        {"id": _chunk_key(h), "route": h.get("route", "hybrid"),
         "rank": h.get("route_rank", 0), "fused_rank": h.get("fused_rank", 0)}
        for h in final
    ])
    for i, (hit, extra) in enumerate(zip(final, explained)):
        hit["why"] = extra["why"]
        hit["is_confidence_comparable"] = extra["is_confidence_comparable"]
        hit["rank"] = i
    return final


if __name__ == "__main__":
    for hit in hybrid_search("出差住一晚最多报多少"):
        print(f"[{hit['rank']}] {hit['source']}#{hit['chunk_index']} :: {hit['text'][:60]}…")
        print(f"    {hit.get('why', '')}")
