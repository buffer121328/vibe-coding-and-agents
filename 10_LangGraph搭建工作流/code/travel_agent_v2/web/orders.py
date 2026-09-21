"""订单中心：把「订了什么」从库存里独立出来。

为什么订单不放在业务库：业务库每次启动都会被种子库重建（`update_dates()`），
`booked` 标记会被清回 0。订单是用户资产，必须留在 `db/app.sqlite`。

于是职责这样分：
- **库存**（hotels / car_rentals / trip_recommendations）留在业务库，是可重置的演示数据；
- **订单**（本模块）留在应用库，重启不丢；
- 启动时 `sync_inventory()` 把已确认订单回写到库存的 `booked` 标记，
  让看板和订单表重新一致——订单是事实来源，库存标记只是它的投影。

记录订单不需要改业务工具：运行时在 SSE 里就能看到每个 `book_*` / `cancel_*`
工具调用和它的回执，`record_tool_call()` 按工具名分派即可。
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime

from web import store
from web.present.cities import city_name

# 业务库路径固定跟着项目目录走，**不要**图省事去用 paths.STATE_DB_DIR：
# 那个目录可以被 TRIP_DESK_DB_DIR 改到临时目录（测试用），
# 而业务库（航班 / 酒店 / 租车 / 景点）永远在项目的 db/ 下。
from infra.biz_db import BUSINESS_DB

FLIGHT = "flight"
HOTEL = "hotel"
CAR = "car"
SPOT = "spot"

CONFIRMED = "confirmed"
CANCELLED = "cancelled"

KIND_LABEL = {FLIGHT: "机票", HOTEL: "酒店", CAR: "租车", SPOT: "门票"}

# 工具名 -> (类型, 参数里的主键名, 是否是取消, 是否是改日期)
TOOL_MAP = {
    "book_hotel": (HOTEL, "hotel_id", False, False),
    "update_hotel": (HOTEL, "hotel_id", False, True),
    "cancel_hotel": (HOTEL, "hotel_id", True, False),
    "book_car_rental": (CAR, "rental_id", False, False),
    "update_car_rental": (CAR, "rental_id", False, True),
    "cancel_car_rental": (CAR, "rental_id", True, False),
    "book_excursion": (SPOT, "recommendation_id", False, False),
    "update_excursion": (SPOT, "recommendation_id", False, True),
    "cancel_excursion": (SPOT, "recommendation_id", True, False),
}

TABLE_OF = {HOTEL: "hotels", CAR: "car_rentals", SPOT: "trip_recommendations"}
DATE_COLS = {
    HOTEL: ("checkin_date", "checkout_date"),
    CAR: ("start_date", "end_date"),
    SPOT: (None, None),
}


def _now() -> str:
    """当前时间戳字符串（订单表的 created_at / updated_at）。

    :return: 'YYYY-MM-DD HH:MM:SS'
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row(row) -> dict:
    """把订单行整成统一 dict。

    :param row: sqlite3.Row
    :return: dict
    """
    detail = row["detail"]
    try:
        detail = json.loads(detail) if detail else None
    except (TypeError, ValueError):
        pass
    return {
        "id": row["id"],
        "kind": row["kind"],
        "kind_label": KIND_LABEL.get(row["kind"], row["kind"]),
        "ref": row["ref"],
        "title": row["title"],
        "location": row["location"],
        "start_date": row["start_date"],
        "end_date": row["end_date"],
        "amount": row["amount"],
        "status": row["status"],
        "thread_id": row["thread_id"],
        "detail": detail,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _business_conn() -> sqlite3.Connection | None:
    """开业务库连接（算金额、回写库存标记时要读它）。

    :return: sqlite3 连接
    """
    if not os.path.exists(BUSINESS_DB):
        return None
    conn = sqlite3.connect(BUSINESS_DB)
    conn.row_factory = sqlite3.Row
    return conn


def upsert(
    passenger_id: str,
    kind: str,
    ref: str,
    *,
    title: str,
    location: str = "",
    start_date: str = "",
    end_date: str = "",
    amount: int = 0,
    status: str = CONFIRMED,
    username: str = "",
    thread_id: str = "",
    detail=None,
) -> None:
    """记一笔订单（同一 kind+ref 只留一条，重复扫描历史不会记成两单）。

    :param passenger_id: 归属旅客
    :param kind: flight / hotel / car / spot
    :param ref: 库存引用（航班号 / 酒店号 …）
    :param title: 订单标题（给人看的）
    :param location: 城市（英文，库里存的形状）
    :param start_date: 起始日期
    :param end_date: 结束日期
    :param amount: 金额（库存单价 × 天数）
    :param status: confirmed / cancelled
    :param username: 操作人
    :param thread_id: 出自哪条对话
    :param detail: 额外字段（原始参数等）
    :return: 落库后的订单 dict 或 None（没记成）
    """
    payload = json.dumps(detail, ensure_ascii=False, default=str) if detail else ""
    now = _now()
    conn = store.connect()
    try:
        conn.execute(
            """
            INSERT INTO orders (passenger_id, username, kind, ref, title, location,
                                start_date, end_date, amount, status, thread_id, detail,
                                created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(passenger_id, kind, ref) DO UPDATE SET
                title = excluded.title,
                location = excluded.location,
                start_date = excluded.start_date,
                end_date = excluded.end_date,
                amount = excluded.amount,
                status = excluded.status,
                thread_id = excluded.thread_id,
                detail = excluded.detail,
                updated_at = excluded.updated_at
            """,
            (
                passenger_id, username, kind, str(ref), title, location,
                start_date, end_date, int(amount or 0), status, thread_id, payload, now, now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def set_status(passenger_id: str, kind: str, ref: str, status: str) -> None:
    """改订单状态（退单时用）。

    :param passenger_id: 归属旅客
    :param kind: 订单类别
    :param ref: 库存引用
    :param status: 新状态
    :return: 受影响行数
    """
    conn = store.connect()
    try:
        conn.execute(
            "UPDATE orders SET status = ?, updated_at = ?"
            " WHERE passenger_id = ? AND kind = ? AND ref = ?",
            (status, _now(), passenger_id, kind, str(ref)),
        )
        conn.commit()
    finally:
        conn.close()


def list_for(passenger_id: str, owner_view: bool = False) -> list[dict]:
    """列出订单：普通账号只看自己的，运营账号看全量。

    :param passenger_id: 当前旅客
    :param owner_view: True 表示运营视图
    :return: 订单 dict 列表
    """
    conn = store.connect()
    try:
        if owner_view:      # 运营视图：看全部
            rows = conn.execute(
                "SELECT * FROM orders ORDER BY status, start_date, id DESC LIMIT 300"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM orders WHERE passenger_id = ?"
                " ORDER BY status, start_date, id DESC LIMIT 200",
                (passenger_id,),
            ).fetchall()
    finally:
        conn.close()
    return [_row(row) for row in rows]


def counts_for(passenger_id: str, owner_view: bool = False) -> dict:
    """订单汇总（单数、金额、按类别分组）。

    :param passenger_id: 当前旅客
    :param owner_view: True 表示运营视图
    :return: {"all": n, "amount": ¥, "by_kind": {...}}
    """
    conn = store.connect()
    try:
        where = "" if owner_view else " WHERE passenger_id = ?"
        params = () if owner_view else (passenger_id,)
        rows = conn.execute(
            f"SELECT status, kind, COUNT(*) AS n, COALESCE(SUM(amount), 0) AS money"
            f" FROM orders{where} GROUP BY status, kind",
            params,
        ).fetchall()
    finally:
        conn.close()
    out = {"all": 0, "confirmed": 0, "cancelled": 0, "amount": 0, "by_kind": {}}
    for row in rows:
        out["all"] += row["n"]
        out[row["status"]] = out.get(row["status"], 0) + row["n"]
        if row["status"] == CONFIRMED:
            out["amount"] += row["money"] or 0
        out["by_kind"][row["kind"]] = out["by_kind"].get(row["kind"], 0) + row["n"]
    return out


def _lookup_inventory(kind: str, ref: str) -> dict | None:
    """按 kind + ref 回库存查一行（算金额、取标题用）。

    :param kind: 订单类别
    :param ref: 库存引用
    :return: 库存行 dict 或 None
    """
    table = TABLE_OF.get(kind)
    if not table:
        return None
    conn = _business_conn()
    if conn is None:
        return None
    try:
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (ref,)).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    return dict(row) if row else None


def _inventory_dates(kind: str, item: dict) -> tuple[str, str]:
    """取库存行自带的起止日期（订单里没写日期时兜底）。

    :param kind: 订单类别
    :param item: 库存行
    :return: (start, end)
    """
    start_col, end_col = DATE_COLS.get(kind, (None, None))
    if not item or not start_col:
        return "", ""
    return str(item.get(start_col) or ""), str(item.get(end_col) or "")


def _days_between(start: str, end: str) -> int:
    """住几晚 / 租几天。日期解析不了就按 1 天算，别让金额变成 0。"""
    try:
        a = datetime.fromisoformat(str(start)[:10])
        b = datetime.fromisoformat(str(end)[:10])
    except (TypeError, ValueError):
        return 1
    return max(1, (b - a).days)


def _amount_of(kind: str, item: dict, start: str, end: str, tool_name: str) -> int:
    """按库存表里的单价算金额：酒店按晚、租车按天、门票按张。"""
    if kind == HOTEL:
        return int(item.get("price_per_night") or 0) * _days_between(start, end)
    if kind == CAR:
        return int(item.get("price_per_day") or 0) * _days_between(start, end)
    if kind == SPOT:
        return int(item.get("ticket_price") or 0)
    return 0


ACTION_LABEL = {
    "book_hotel": "订酒店", "update_hotel": "改酒店", "cancel_hotel": "退酒店",
    "book_car_rental": "订车", "update_car_rental": "改租车", "cancel_car_rental": "退租车",
    "book_excursion": "订门票", "update_excursion": "改门票", "cancel_excursion": "退门票",
    "update_ticket_to_new_flight": "改签机票", "cancel_ticket": "退机票",
}


def describe_call(name: str, args: dict) -> dict | None:
    """把一次敏感工具调用翻成审批卡上的字段：动作 / 对象 / 日期 / 金额。

    审批卡要让人一眼看清「我要同意的是什么」，所以这里把库存里的
    名称、城市、日期、单价捞出来，而不是把 JSON 原样丢给用户看。
    """
    spec = TOOL_MAP.get(name)
    if not spec:
        return {"action": ACTION_LABEL.get(name, name), "target": "", "when": "", "amount": ""}
    kind, key, is_cancel, _is_update = spec
    ref = (args or {}).get(key)
    item = _lookup_inventory(kind, str(ref)) if ref is not None else None
    item = item or {}
    start, end = _inventory_dates(kind, item)
    start = str((args or {}).get("start_date") or (args or {}).get("checkin_date") or start)
    end = str((args or {}).get("end_date") or (args or {}).get("checkout_date") or end)
    amount = 0 if is_cancel else _amount_of(kind, item, start, end, name)
    when = " → ".join(x for x in (start[:10], end[:10]) if x)
    return {
        "action": ACTION_LABEL.get(name, name),
        "target": str(item.get("name") or (f"{KIND_LABEL.get(kind, kind)} #{ref}" if ref is not None else "")),
        "city": city_name(str(item.get("location") or ""), ""),
        "when": when,
        "amount": f"¥{amount}" if amount else "",
    }


def record_tool_call(
    name: str,
    args: dict,
    *,
    passenger_id: str,
    username: str = "",
    thread_id: str = "",
) -> dict | None:
    """按工具调用把订单写下来。返回写进去的订单摘要，供审计使用。"""
    spec = TOOL_MAP.get(name)
    if not spec:
        return None
    kind, key, is_cancel, is_update = spec
    ref = (args or {}).get(key)
    if ref is None:
        return None

    item = _lookup_inventory(kind, ref) or {}
    start, end = _inventory_dates(kind, item)
    # 改期类工具的参数里有新日期，优先用
    start = str((args or {}).get("start_date") or (args or {}).get("checkin_date") or start)
    end = str((args or {}).get("end_date") or (args or {}).get("checkout_date") or end)
    title = str(item.get("name") or f"{KIND_LABEL.get(kind, kind)} #{ref}")
    location = city_name(str(item.get("location") or ""), "")
    status = CANCELLED if is_cancel else CONFIRMED

    upsert(
        passenger_id,
        kind,
        str(ref),
        title=title,
        location=location,
        start_date=start,
        end_date=end,
        amount=0 if is_cancel else _amount_of(kind, item, start, end, name),
        status=status,
        username=username,
        thread_id=thread_id,
        detail={"tool": name, "args": args, "action": "cancel" if is_cancel else ("update" if is_update else "book")},
    )
    return {
        "kind": kind,
        "ref": str(ref),
        "title": title,
        "status": status,
    }


def ensure_flight_orders(passenger_id: str, username: str = "") -> None:
    """机票订单直接从业务库推导：旅客名下的每张票每个航段一条订单。"""
    conn = _business_conn()
    if conn is None:
        return
    try:
        rows = conn.execute(
            """
            SELECT t.ticket_no, f.flight_no, f.departure_airport, f.arrival_airport,
                   f.scheduled_departure, f.scheduled_arrival, tf.amount, tf.fare_conditions,
                   bp.seat_no
            FROM tickets t
            JOIN ticket_flights tf ON t.ticket_no = tf.ticket_no
            JOIN flights f ON tf.flight_id = f.flight_id
            LEFT JOIN boarding_passes bp
                ON bp.ticket_no = t.ticket_no AND bp.flight_id = f.flight_id
            WHERE t.passenger_id = ?
            """,
            (passenger_id,),
        ).fetchall()
        ap = {
            r["airport_code"]: dict(r)
            for r in conn.execute("SELECT * FROM airports_data").fetchall()
        }
    except sqlite3.Error:
        return
    finally:
        conn.close()

    for row in rows:
        dep = ap.get(row["departure_airport"]) or {}
        arr = ap.get(row["arrival_airport"]) or {}
        # 库里存英文，界面上给中文
        city_dep = city_name(dep.get("city") or row["departure_airport"])
        city_arr = city_name(arr.get("city") or row["arrival_airport"])
        ref = f"{row['ticket_no']}-{row['flight_no']}"
        upsert(
            passenger_id,
            FLIGHT,
            ref,
            title=f"{row['flight_no']} {city_dep} → {city_arr}",
            location=city_arr,
            start_date=str(row["scheduled_departure"])[:16],
            end_date=str(row["scheduled_arrival"])[:16],
            amount=int(row["amount"] or 0),
            username=username,
            detail={
                "ticket_no": row["ticket_no"],
                "seat": row["seat_no"],
                "fare": row["fare_conditions"],
                "from": row["departure_airport"],
                "to": row["arrival_airport"],
            },
        )


def sync_inventory() -> int:
    """把已确认订单回写到库存的 booked 标记（启动时调一次）。

    种子库重建后 booked 全是 0，靠这一步让看板跟订单表重新一致。
    """
    conn = store.connect()
    try:
        rows = conn.execute(
            "SELECT kind, ref, status FROM orders WHERE kind IN ('hotel', 'car', 'spot')"
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return 0

    biz = _business_conn()
    if biz is None:
        return 0
    changed = 0
    try:
        for row in rows:
            table = TABLE_OF.get(row["kind"])
            if not table:
                continue
            flag = 1 if row["status"] == CONFIRMED else 0
            try:
                cur = biz.execute(
                    f"UPDATE {table} SET booked = ? WHERE id = ?", (flag, row["ref"])
                )
                changed += cur.rowcount
            except sqlite3.Error:
                continue
        biz.commit()
    finally:
        biz.close()
    return changed


def cancel_order(order_id: int, passenger_id: str, owner_view: bool = False) -> dict:
    """从订单中心直接取消一单，并把库存标记放回去。"""
    conn = store.connect()
    try:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not row:
            raise ValueError("订单不存在")
        if not owner_view and row["passenger_id"] != passenger_id:
            raise ValueError("这不是当前账号的订单")
        conn.execute(
            "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
            (CANCELLED, _now(), order_id),
        )
        conn.commit()
        order = _row(row)
        order["status"] = CANCELLED
    finally:
        conn.close()

    table = TABLE_OF.get(order["kind"])
    if table:
        biz = _business_conn()
        if biz is not None:
            try:
                biz.execute(f"UPDATE {table} SET booked = 0 WHERE id = ?", (order["ref"],))
                biz.commit()
            except sqlite3.Error:
                pass
            finally:
                biz.close()
    return order
