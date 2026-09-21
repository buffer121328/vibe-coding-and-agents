"""业务库怎么用：每次启动把里面的日期平移到「今天」。

**库文件本身在哪不归这里管**——路径在 `infra/paths.py`（全仓唯一的路径出处）。
早先四个业务工具各自写了一行同样的 `os.path.join(..., "db", "travel_new.sqlite")`，
改个目录要追着改四五处；收口之后这里只剩下「怎么用它」这一步。

两份文件的脾气不一样（对应第 3.1 节）：

| 文件 | 角色 |
| :--- | :--- |
| `db/travel2.sqlite` | **种子库**：干净的演示数据，随时可以从它重建 |
| `db/travel_new.sqlite` | **运行副本**：图和工具真正读写的那份，每次启动被种子库整份覆盖 |

用户资产（账号 / 会话 / 订单 / 审计）不在这里——它们在应用库 `web/store.py` 那边，
**不参与重建**。
"""
from __future__ import annotations

import shutil
import sqlite3

import pandas as pd

# 把两个路径转出给业务工具用（`from infra.biz_db import BUSINESS_DB as db`）：
# 工具关心的是「业务库」这件事，不必被迫认识 paths 这一层。
from infra.paths import BUSINESS_DB, SEED_DB

__all__ = ["BUSINESS_DB", "SEED_DB", "update_dates"]


def update_dates() -> str:
    """用种子库覆盖运行副本，并把里面的日期整体平移到「今天」。

    为什么要有这一步：航班、酒店、租车的日期是写死在种子数据里的。不平移的话，
    跑起来看到的全是「几个月前的航班」，用户说「明天去成都」永远查不到东西。

    做法是把种子库整份复制过来（等于重置），再以 `flights.actual_departure` 的最大值
    为基准算出与当前时间的差值，把 bookings 与 flights 里所有日期列统一平移同一个差值。

    :return: 运行副本的路径（`db/travel_new.sqlite`）
    """
    shutil.copy(SEED_DB, BUSINESS_DB)   # 目标已存在就覆盖：这就是「重置」那一步

    conn = sqlite3.connect(BUSINESS_DB)
    tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table';", conn).name.tolist()
    frames = {t: pd.read_sql(f"SELECT * from {t}", conn) for t in tables}

    # 基准时间取航班表里最晚的一班；所有表共用这一个差值，日期关系才不会错位
    example_time = pd.to_datetime(frames["flights"]["actual_departure"].replace("\\N", pd.NaT)).max()
    current_time = pd.to_datetime("now").tz_localize(example_time.tz)
    time_diff = current_time - example_time

    frames["bookings"]["book_date"] = (
        pd.to_datetime(frames["bookings"]["book_date"].replace("\\N", pd.NaT), utc=True) + time_diff
    )
    for column in ("scheduled_departure", "scheduled_arrival", "actual_departure", "actual_arrival"):
        frames["flights"][column] = (
            pd.to_datetime(frames["flights"][column].replace("\\N", pd.NaT)) + time_diff
        )

    for table_name, frame in frames.items():
        frame.to_sql(table_name, conn, if_exists="replace", index=False)
        del frame        # 表多且宽，逐个释放，别把整库都留内存里

    conn.commit()
    conn.close()
    return BUSINESS_DB


if __name__ == "__main__":
    print("已把业务库日期平移到今天：", update_dates())
