"""把工具结果提升成结构化卡片。

业务工具（`search_flights` / `search_hotels` / …）返回的是 `list[dict]`，
LangGraph 把它塞进 ToolMessage 时变成了 Python 字面量的字符串。与其改八个工具，
不如在渲染层把这串字面量**还原**回结构：用 `ast.literal_eval` 安全地取值
（不回退到 `eval`，因为它会执行代码），再挑出界面上要显示的字段。

这样模型返回什么，界面就长出什么形状的卡片——比固定模板更接近「生成式 UI」：
- 查机票 → 航班卡
- 查酒店 → 酒店卡（带单价与档位）
- 查景点 → 景点卡（带关键词标签与玩法摘要）
- 一次问四类 → 自动多出一张比价对照卡
"""
from __future__ import annotations

import ast
from typing import Any

# 工具名 -> 卡片类型
TOOL_KIND = {
    "search_flights": "flight",
    "search_hotels": "hotel",
    "search_car_rentals": "car",
    "search_trip_recommendations": "spot",
}

KIND_LABEL = {"flight": "航班", "hotel": "酒店", "car": "租车", "spot": "景点"}

MAX_PER_GROUP = 12
DETAIL_LIMIT = 96


def _as_list(content: Any) -> list[dict] | None:
    """把工具回执还原成 list[dict]。不是这个形状就返回 None。"""
    if isinstance(content, list):
        rows = content
    else:
        text = str(content or "").strip()
        if not text.startswith("["):
            return None
        try:
            # literal_eval 只认字面量，不会执行任意代码；这里刻意不用 eval
            rows = ast.literal_eval(text)
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            return None
        if not isinstance(rows, list):
            return None
    out = []
    for row in rows:
        if isinstance(row, dict):
            out.append({str(k): v for k, v in row.items()})
    return out


def _clip(text: Any, limit: int = DETAIL_LIMIT) -> str:
    """把长文本截短，留个省略号。

    :param text: 原文
    :param limit: 最多留几个字符
    :return: 截断后的字符串
    """
    s = " ".join(str(text or "").split())
    return s[:limit] + "…" if len(s) > limit else s


def _flight(row: dict) -> dict:
    """把一行航班库存翻成卡片。

    :param row: 库存行（dict）
    :return: 卡片 dict（title / code / when / price / ...）
    """
    return {
        "code": row.get("flight_no") or "—",
        "from": row.get("departure_airport") or "",
        "to": row.get("arrival_airport") or "",
        "when": str(row.get("scheduled_departure") or "")[:16],
        "arrive": str(row.get("scheduled_arrival") or "")[:16],
        "note": row.get("status") or "",
    }


def _hotel(row: dict) -> dict:
    """把一行酒店库存翻成卡片。

    :param row: 库存行（dict）
    :return: 卡片 dict
    """
    price = row.get("price_per_night")
    return {
        "code": row.get("location") or "",
        "title": row.get("name") or "—",
        "tag": row.get("price_tier") or "",
        "price": f"¥{price}/晚" if price else "",
        "note": " · ".join(x for x in (str(row.get("checkin_date") or ""), str(row.get("checkout_date") or "")) if x),
        "booked": bool(row.get("booked")),
    }


def _car(row: dict) -> dict:
    """把一行租车库存翻成卡片。

    :param row: 库存行（dict）
    :return: 卡片 dict
    """
    price = row.get("price_per_day")
    return {
        "code": row.get("location") or "",
        "title": row.get("name") or "—",
        "tag": row.get("price_tier") or "",
        "price": f"¥{price}/天" if price else "",
        "note": " · ".join(x for x in (str(row.get("start_date") or ""), str(row.get("end_date") or "")) if x),
        "booked": bool(row.get("booked")),
    }


def _spot(row: dict) -> dict:
    """把一行景点翻成卡片（带关键词标签，正文压两行）。

    :param row: 库存行（dict）
    :return: 卡片 dict
    """
    price = row.get("ticket_price")
    return {
        "code": row.get("location") or "",
        "title": row.get("name") or "—",
        "tag": "",
        "price": "免费" if price == 0 else (f"¥{price}" if price else ""),
        "note": _clip(row.get("details")),
        "keywords": [k.strip() for k in str(row.get("keywords") or "").split(",") if k.strip()][:4],
        "booked": bool(row.get("booked")),
    }


SHAPE = {"flight": _flight, "hotel": _hotel, "car": _car, "spot": _spot}


def group(tool_name: str, args: dict | None, content: Any) -> dict | None:
    """一个工具调用 → 一组卡片。不认识的工具返回 None。"""
    kind = TOOL_KIND.get(tool_name)
    if not kind:
        return None
    rows = _as_list(content)
    if not rows:
        return None
    shape = SHAPE[kind]
    items = [shape(row) for row in rows[:MAX_PER_GROUP]]
    return {
        "kind": kind,
        "label": KIND_LABEL[kind],
        "city": str((args or {}).get("location") or (args or {}).get("city") or ""),
        "total": len(rows),
        "shown": len(items),
        "items": items,
    }


def build(pairs: list[tuple[str, dict, Any]]) -> list[dict]:
    """把一轮里的 (工具名, 参数, 回执) 收成卡片组，同类合并。

    一次问四类业务时，四组卡片各长各的；再额外给一张「比价对照卡」，
    用条形把四类的数量差异画出来——比让用户读四行文字快。
    """
    groups: dict[str, dict] = {}
    for name, args, content in pairs:
        made = group(name, args, content)
        if not made:
            continue
        key = f"{made['kind']}|{made['city']}"
        if key in groups:
            existing = groups[key]
            merged = {item["title"] or item["code"]: item for item in existing["items"]}
            for item in made["items"]:
                merged.setdefault(item["title"] or item["code"], item)
            existing["items"] = list(merged.values())[:MAX_PER_GROUP]
            existing["total"] += made["total"]
            existing["shown"] = len(existing["items"])
        else:
            groups[key] = made

    ordered = sorted(groups.values(), key=lambda g: (g["kind"], g["city"]))
    if len(ordered) >= 2:
        ordered.insert(0, compare_card(ordered))
    return ordered


def compare_card(groups: list[dict]) -> dict:
    """比价对照：把各组命中数量画成条形。"""
    top = max((g["total"] for g in groups), default=1) or 1
    return {
        "kind": "compare",
        "label": "行情对照",
        "city": "",
        "total": sum(g["total"] for g in groups),
        "shown": len(groups),
        "items": [
            {
                "title": g["label"],
                "code": g["city"] or "",
                "note": f"{g['total']} 条",
                "bar": round(g["total"] / top * 100),
            }
            for g in groups
        ],
    }
