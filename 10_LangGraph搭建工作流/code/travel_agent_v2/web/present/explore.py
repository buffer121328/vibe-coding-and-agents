"""探索：不靠对话，直接按城市翻库存。

对话适合"我要订 X"，不适合"随便看看有什么"。所以单开一个浏览入口：
选城市 → 出景点 / 酒店 / 租车的卡片。数据直接读业务库，
和专员工具用的是同一份库存，只是不经过模型。

这一层让界面不再是"只有聊天能做事"：想逛就逛，想订再回对话。
"""
from __future__ import annotations

import os
import sqlite3

from web.present.cities import CITY_CN, city_name

from infra.biz_db import BUSINESS_DB

# 库里的英文城市名 -> 所在机场三字码，用来取城市标记
CITY_CODE = {
    "Beijing": "PEK",
    "Shanghai": "SHA",
    "Chengdu": "CTU",
    "Xian": "XIY",
    "Hangzhou": "HGH",
    "Guangzhou": "CAN",
    "Shenzhen": "SZX",
    "Kunming": "KMG",
    "Sanya": "SYX",
    "Chongqing": "CKG",
    "Xiamen": "XMN",
    "Wuhan": "WUH",
    "Lhasa": "LXA",
    "Lijiang": "LJG",
    "Qingdao": "TAO",
    "Harbin": "HRB",
}


def _conn() -> sqlite3.Connection | None:
    """开一个业务库连接（只读浏览用，默认 row 工厂便于按列名取值）。

    :return: sqlite3 连接
    """
    if not os.path.exists(BUSINESS_DB):
        return None
    conn = sqlite3.connect(BUSINESS_DB)
    conn.row_factory = sqlite3.Row
    return conn


def cities() -> list[dict]:
    """有库存的城市，带三类库存的数量，前端拿它画城市选择器。"""
    conn = _conn()
    if conn is None:
        return []
    try:
        counts: dict[str, dict] = {}
        for table, key in (
            ("trip_recommendations", "spots"),
            ("hotels", "hotels"),
            ("car_rentals", "cars"),
        ):
            rows = conn.execute(
                f"SELECT location, COUNT(*) AS n, SUM(booked) AS booked FROM {table} GROUP BY location"
            ).fetchall()
            for row in rows:
                city = str(row["location"] or "")
                if not city:
                    continue
                slot = counts.setdefault(city, {"spots": 0, "hotels": 0, "cars": 0, "booked": 0})
                slot[key] = row["n"]
                slot["booked"] += row["booked"] or 0
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    out = []
    for city, slot in counts.items():
        total = slot["spots"] + slot["hotels"] + slot["cars"]
        out.append(
            {
                "city": city,
                "cn": city_name(city),
                "code": CITY_CODE.get(city, ""),
                "spots": slot["spots"],
                "hotels": slot["hotels"],
                "cars": slot["cars"],
                "total": total,
                "booked": slot["booked"],
            }
        )
    return sorted(out, key=lambda item: (-item["total"], item["cn"]))


def browse(city: str, limit: int = 12) -> dict:
    """一个城市的三类库存。city 接受中文或英文。"""
    wanted = _resolve(city)
    if not wanted:
        return {"city": "", "cn": "", "code": "", "spots": [], "hotels": [], "cars": []}
    conn = _conn()
    if conn is None:
        return {"city": wanted, "cn": city_name(wanted), "code": CITY_CODE.get(wanted, ""),
                "spots": [], "hotels": [], "cars": []}
    try:
        spots = conn.execute(
            "SELECT id, name, location, keywords, details, ticket_price, booked"
            " FROM trip_recommendations WHERE location = ? ORDER BY booked, id LIMIT ?",
            (wanted, limit),
        ).fetchall()
        hotels = conn.execute(
            "SELECT id, name, location, price_tier, price_per_night, checkin_date, checkout_date, booked"
            " FROM hotels WHERE location = ? ORDER BY booked, price_per_night LIMIT ?",
            (wanted, limit),
        ).fetchall()
        cars = conn.execute(
            "SELECT id, name, location, price_tier, price_per_day, start_date, end_date, booked"
            " FROM car_rentals WHERE location = ? ORDER BY booked, price_per_day LIMIT ?",
            (wanted, limit),
        ).fetchall()
    except sqlite3.Error:
        spots = hotels = cars = []
    finally:
        conn.close()

    def rows(items, shape):
        """把库存行列表套上同一个「整形函数」。

        :param items: 原始行（dict）列表
        :param shape: 单行 → dict 的转换函数
        :return: 转换后的列表
        """
        return [shape(dict(row)) for row in items]

    return {
        "city": wanted,
        "cn": city_name(wanted),
        "code": CITY_CODE.get(wanted, ""),
        "spots": rows(spots, lambda r: {
            "id": r["id"],
            "title": r["name"],
            "price": "免费" if r["ticket_price"] == 0 else f"¥{r['ticket_price']}",
            "note": " ".join(str(r["details"] or "").split())[:110],
            "keywords": [k.strip() for k in str(r["keywords"] or "").split(",") if k.strip()][:4],
            "booked": bool(r["booked"]),
        }),
        "hotels": rows(hotels, lambda r: {
            "id": r["id"],
            "title": r["name"],
            "tag": r["price_tier"],
            "price": f"¥{r['price_per_night']}/晚",
            "note": f"{r['checkin_date']} → {r['checkout_date']}",
            "booked": bool(r["booked"]),
        }),
        "cars": rows(cars, lambda r: {
            "id": r["id"],
            "title": r["name"],
            "tag": r["price_tier"],
            "price": f"¥{r['price_per_day']}/天",
            "note": f"{r['start_date']} → {r['end_date']}",
            "booked": bool(r["booked"]),
        }),
    }


def code_of(city: str) -> str:
    """城市（中文或英文）-> 三字码，用来取城市标记。"""
    return CITY_CODE.get(_resolve(city), "")


def _resolve(city: str) -> str:
    """把中文城市名换成库里存的英文名；已经是英文就照样返回。"""
    text = str(city or "").strip()
    if not text:
        return ""
    if text in CITY_CODE or text in CITY_CN:
        return text
    for en, cn in CITY_CN.items():
        if cn == text:
            return en
    return ""
