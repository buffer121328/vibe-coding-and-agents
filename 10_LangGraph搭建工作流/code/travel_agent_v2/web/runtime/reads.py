"""只读投影：行程、看板、卡片、偏好、订单、审计、会话列表。

这一层不写任何状态（唯一的例外是内存里的节点时间线，它由 hub 维护）。
全部函数都是「给我一份 Desk，还你一份能直接塞进 JSON 的结构」——
业务库读的是它，应用库读的也是它，但都不改。
"""
from __future__ import annotations

import json
import os
import sqlite3

from langchain_core.messages import AIMessage, ToolMessage

from infra.biz_db import BUSINESS_DB
from infra.logging import log
from memory.store import store as memory_store
from web import audit, orders, sessions
from web.present import art, cards, explore
from web.present.cities import AIRPORT_CITY_CN
from web.present.geo import AIRPORT_GEO, CITY_GEO
from web.runtime import hub
from web.runtime.identity import Desk
from web.runtime.turns import _graph_messages, _tool_calls_of


def sessions_view(desk: Desk) -> list[dict]:
    """当前账号的对话列表；正在使用的那条排在标出来。"""
    if not desk.thread_id:
        return []
    items = sessions.list_for(desk.passenger_id)
    for item in items:
        item["active"] = item["thread_id"] == desk.thread_id
    return items


def orders_view(desk: Desk) -> dict:
    """订单中心的数据。运营账号能看到全部，普通账号只看自己的。"""
    owner_view = desk.role == "ops"
    return {
        "counts": orders.counts_for(desk.passenger_id, owner_view),
        "items": orders.list_for(desk.passenger_id, owner_view),
        "owner_view": owner_view,
    }


def audit_view(desk: Desk) -> dict:
    """审计只有运营账号能看全；普通账号只看得到自己的流水。"""
    if desk.role == "ops":
        return {"summary": audit.summary(), "items": audit.recent(80), "owner_view": True}
    if not desk.actor:
        return {
            "summary": {"total": 0, "by_action": {}, "failures": 0},
            "items": [],
            "owner_view": False,
        }
    items = audit.recent(40, actor=desk.actor)
    by_action: dict[str, int] = {}
    failures = 0
    for item in items:
        by_action[item["action"]] = by_action.get(item["action"], 0) + 1
        if item["result"] != audit.OK:
            failures += 1
    return {
        "summary": {"total": len(items), "by_action": by_action, "failures": failures},
        "items": items,
        "owner_view": False,
    }


def _collect_cards(desk: Desk) -> list[dict]:
    """把**最近一轮**里查询类工具的回执收成卡片组。

    只取最后一轮：上一轮查过的酒店，不该在用户问机票时还挂在屏幕上。
    业务工具本身不用知道卡片的存在——它们照旧返回 list[dict]，
    这里用 ast.literal_eval 把 LangGraph 存下的字面量还原回结构（见 web/present/cards.py）。
    """
    msgs = _graph_messages(desk)
    # 从后往前找到最后一个人类发言，本轮就从那里开始
    start = 0
    for idx in range(len(msgs) - 1, -1, -1):
        if getattr(msgs[idx], "type", "") == "human":
            start = idx
            break
    calls: dict[str, tuple[str, dict]] = {}
    pairs: list[tuple[str, dict, object]] = []
    for msg in msgs[start:]:
        if isinstance(msg, AIMessage):
            for call in _tool_calls_of(msg):
                calls[call["id"]] = (call["name"], call["args"])
        elif isinstance(msg, ToolMessage):
            call_id = getattr(msg, "tool_call_id", "")
            name, args = calls.get(call_id, ("", {}))
            if name in cards.TOOL_KIND:
                pairs.append((name, args, msg.content))
    try:
        groups = cards.build(pairs)
    except Exception:      # noqa: BLE001 —— 画不出卡片不该影响对话
        log.exception("卡片生成失败")
        return []
    # 每组挂一枚城市标记：卡片上有一张图形，扫一眼比读一行城市名快
    for item in groups:
        city = item.get("city") or ""
        code = explore.code_of(city)
        item["art"] = art.tile(code, 34, city) if city else ""
        item["photo"] = art.photo(code) if city else ""
        item["kind_art"] = art.kind_art(item.get("kind") or "")
    return groups


def explore_cities() -> list[dict]:
    """探索面板的城市列表，带上城市标记（几何 SVG，见 web/present/art.py）。"""
    out = []
    for item in explore.cities():
        item = dict(item)
        code = item.get("code") or ""
        item["art"] = art.tile(code, 34, item.get("cn") or "")
        item["photo"] = art.photo(code)
        out.append(item)
    return out


def _prefs(desk: Desk) -> list[dict]:
    """跨会话档案（Store）里这个人的那几行。

    :param desk: 这次请求的身份
    :return: [{"key": ..., "value": ...}]
    """
    return [{"key": i.key, "value": i.value["value"]} for i in memory_store.search(desk.namespace)]


def _dialog_state(desk: Desk) -> list[str]:
    """当前对话状态栈（主助理 / 某个专员的层叠情况）。

    :param desk: 这次请求的身份
    :return: 状态名列表
    """
    state = hub.GRAPH.get_state(desk.config).values or {}
    stack = state.get("dialog_state") or []
    return list(stack)


def _parse_airport_row(code: str, name: str, city: str, coordinates: str) -> dict:
    """把机场行拼成地图要的格式（坐标缺失时用内置表兜底）。

    :param code: 三字码
    :param name: 机场名
    :param city: 库里存的英文城市名
    :param coordinates: 库里的坐标 JSON
    :return: {code, name, city, city_en, lat, lon}
    """
    lat, lon = AIRPORT_GEO.get(code, {}).get("lat"), AIRPORT_GEO.get(code, {}).get("lon")
    try:
        coords = json.loads(coordinates) if coordinates else None
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            lat, lon = float(coords[0]), float(coords[1])
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    fallback = AIRPORT_GEO.get(code, {})
    # 库里 city 存英文（Beijing / Chengdu），是给 LIKE 查询用的；
    # 界面上要显示中文，所以这里把中文名放在 city，英文名留在 city_en。
    city_en = city or fallback.get("city") or code
    return {
        "code": code,
        "name": name or fallback.get("name") or code,
        # 中文显示名统一来自 web/present/cities.py，别再各写一份
        "city": AIRPORT_CITY_CN.get(code) or fallback.get("city") or city_en,
        "city_en": city_en,
        "lat": lat if lat is not None else fallback.get("lat"),
        "lon": lon if lon is not None else fallback.get("lon"),
    }


def _airports(codes: set[str] | None = None) -> dict[str, dict]:
    """取一批机场元数据（内置表 + 库里覆盖）。

    :param codes: 需要哪些三字码；None 表示全都要
    :return: {code: 机场 dict}
    """
    wanted = set(codes or ()) | set(AIRPORT_GEO)
    out = {code: dict(meta, code=code) for code, meta in AIRPORT_GEO.items()}
    if not os.path.exists(BUSINESS_DB):
        return {k: v for k, v in out.items() if k in wanted}
    conn = sqlite3.connect(BUSINESS_DB)
    try:
        placeholders = ",".join("?" * len(wanted))
        rows = conn.execute(
            f"SELECT airport_code, airport_name, city, coordinates FROM airports_data WHERE airport_code IN ({placeholders})",
            tuple(wanted),
        ).fetchall()
    except sqlite3.Error:
        conn.close()
        return {k: v for k, v in out.items() if k in wanted}
    conn.close()
    for code, name, city, coordinates in rows:
        parsed = _parse_airport_row(code, name, city, coordinates)
        if parsed["lat"] is None or parsed["lon"] is None:
            continue
        out[code] = parsed
    return {k: v for k, v in out.items() if k in wanted}


def _fmt_when(value) -> str:
    """把时间戳截成「YYYY-MM-DD HH:MM」给人看。

    :param value: 原始时间
    :return: 截断后的字符串
    """
    if value is None:
        return ""
    text = str(value)
    return text[:16].replace("T", " ")


def _itinerary(desk: Desk) -> dict:
    """旅客真实行程 + 库存城市，给平铺航段图用。"""
    raw_legs = []
    if os.path.exists(BUSINESS_DB):
        conn = sqlite3.connect(BUSINESS_DB)
        try:
            raw_legs = conn.execute(
                """
                SELECT
                    f.flight_no, f.departure_airport, f.arrival_airport,
                    f.scheduled_departure, f.scheduled_arrival,
                    bp.seat_no, tf.fare_conditions
                FROM tickets t
                JOIN ticket_flights tf ON t.ticket_no = tf.ticket_no
                JOIN flights f ON tf.flight_id = f.flight_id
                LEFT JOIN boarding_passes bp
                    ON bp.ticket_no = t.ticket_no AND bp.flight_id = f.flight_id
                WHERE t.passenger_id = ?
                ORDER BY f.scheduled_departure
                """,
                (desk.passenger_id,),
            ).fetchall()
        except sqlite3.Error:
            raw_legs = []
        conn.close()

    needed = set()
    for _no, dep, arr, *_rest in raw_legs:
        if dep:
            needed.add(dep)
        if arr:
            needed.add(arr)
    for city in _inventory_cities():
        code = (CITY_GEO.get(city) or {}).get("iata")
        if code:
            needed.add(code)
    airports = _airports(needed)

    legs = []
    for flight_no, dep, arr, dep_at, arr_at, seat, fare in raw_legs:
        origin = airports.get(dep) or {"code": dep, "name": dep, "city": dep, "lat": None, "lon": None}
        dest = airports.get(arr) or {"code": arr, "name": arr, "city": arr, "lat": None, "lon": None}
        legs.append(
            {
                "flight_no": flight_no,
                "from": dep,
                "to": arr,
                "depart": _fmt_when(dep_at),
                "arrive": _fmt_when(arr_at),
                "seat": seat or "",
                "fare": fare or "",
                "origin": origin,
                "dest": dest,
            }
        )

    # 行程图上要出现的节点：旅客真正飞到的机场 + 有库存的城市
    cities = []
    seen = set()
    for code in [leg["from"] for leg in legs] + [leg["to"] for leg in legs]:
        if code and code in airports and code not in seen:
            seen.add(code)
            cities.append(airports[code])
    for city in _inventory_cities():
        code = (CITY_GEO.get(city) or {}).get("iata")
        if not code or code in seen or code not in airports:
            continue
        seen.add(code)
        cities.append(airports[code])
    return {"legs": legs, "airports": cities, "passenger_id": desk.passenger_id}


def _route_svg(desk: Desk) -> str:
    """行程坐标示意图：省会城市做底，可订城市与旅客航段画在上面。"""
    data = _itinerary(desk)
    legs = data.get("legs") or []
    if not legs:
        return ""
    try:
        return art.route_map(data.get("airports") or [], legs)
    except Exception:      # noqa: BLE001 —— 画不出来不影响文字行程
        log.exception("航线示意图生成失败")
        return ""


def _inventory_cities() -> list[str]:
    """库里有酒店 / 租车 / 景点库存的城市，用来画「库存城市」那一排。"""
    if not os.path.exists(BUSINESS_DB):
        return []
    conn = sqlite3.connect(BUSINESS_DB)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT location FROM hotels
            UNION SELECT DISTINCT location FROM car_rentals
            UNION SELECT DISTINCT location FROM trip_recommendations
            """
        ).fetchall()
    except sqlite3.Error:
        rows = []
    finally:
        conn.close()
    return sorted(str(row[0]) for row in rows if row and row[0])


def _table_board(conn, table: str, price_col: str | None = None, tier_col: str | None = None) -> dict:
    """一类库存的看板数据。

    价格与档位的列名各家不同（每晚 / 每天 / 门票；档位只有酒店和租车有），
    所以由调用方点名，缺的留空——看板上宁可空一格，也不要编一个数出来。
    """
    total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    booked = conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE booked = 1"
    ).fetchone()[0]
    items = []
    price_sel = f", {price_col}" if price_col else ", NULL"
    tier_sel = f", {tier_col}" if tier_col else ", NULL"
    try:
        rows = conn.execute(
            f"SELECT id, name, location, booked{price_sel}{tier_sel} FROM {table} ORDER BY id"
        ).fetchall()
    except sqlite3.Error:
        rows = []
    for rid, name, location, booked_flag, price, tier in rows:
        items.append(
            {
                "id": rid,
                "name": name,
                "location": location,
                "price": int(price) if price is not None else None,
                "tier": tier or "",
                "booked": bool(booked_flag),
            }
        )
    return {"total": total, "booked": booked, "open": total - booked, "items": items}


def _board(desk: Desk) -> dict:
    """看板数据：四类库存的「总数 / 已订 / 空位 / 明细」，航班只报条数。

    :param desk: 这次请求的身份（航段数按人算）
    :return: {cars, hotels, trips, flights}
    """
    def empty() -> dict:
        """空看板里的一格（某类库存一件都没有时的形状）。

        :return: {"total": 0, "booked": 0, "open": 0, "items": []}
        """
        return {"total": 0, "booked": 0, "open": 0, "items": []}

    board = {
        "cars": empty(),
        "hotels": empty(),
        "trips": empty(),
        "flights": {"total": 0, "legs": 0},
    }
    if not os.path.exists(BUSINESS_DB):
        return board
    conn = sqlite3.connect(BUSINESS_DB)
    try:
        board["cars"] = _table_board(conn, "car_rentals", price_col="price_per_day", tier_col="price_tier")
        board["hotels"] = _table_board(conn, "hotels", price_col="price_per_night", tier_col="price_tier")
        board["trips"] = _table_board(conn, "trip_recommendations", price_col="ticket_price")
        board["flights"]["legs"] = conn.execute(
            """
            SELECT COUNT(*) FROM tickets t
            JOIN ticket_flights tf ON t.ticket_no = tf.ticket_no
            WHERE t.passenger_id = ?
            """,
            (desk.passenger_id,),
        ).fetchone()[0]
        board["flights"]["total"] = conn.execute("SELECT COUNT(*) FROM flights").fetchone()[0]
    except sqlite3.Error:
        pass
    conn.close()
    return board
