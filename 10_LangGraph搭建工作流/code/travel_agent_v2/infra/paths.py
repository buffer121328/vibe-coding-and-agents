"""仓库里所有固定文件位置的唯一出处。

**为什么要有这个文件**：这些路径以前散在七八个模块里，各自写
`os.path.dirname(os.path.dirname(__file__))`——一旦某个文件换了目录深度（比如
从 `web/` 挪进 `web/present/`），那些相对推算就全部错位，而且是**静默错位**：
不报错，只是读不到库、找不到图片。同一个毛病还有第二副面孔：库文件名被四五个
模块各写一遍，改个目录要追着改四五处。收成一处之后，谁要路径就 import 谁。

本文件是全仓**唯一**允许出现 `__file__` 与 `.sqlite` 字面量的地方，规矩由
`tests/test_layering.py` 静态盯着——架构约定只有被测试盯住才不会慢慢回流。

约定：本模块只做路径计算，不建目录、不连库（目录的创建交给用它的那层）。
"""
from __future__ import annotations

import os

# 项目根 = 本文件的上上层（infra/ 的上一层）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(ROOT, "db")
STATIC_DIR = os.path.join(ROOT, "static")
LOG_DIR = os.path.join(ROOT, "logs")
FAQ_PATH = os.path.join(ROOT, "order_faq.md")                 # 政策与攻略知识库（lookup_policy 检索它）
CITIES_DIR = os.path.join(STATIC_DIR, "img", "cities")        # 16 个城市的实景照
CREDITS_PATH = os.path.join(STATIC_DIR, "img", "CREDITS.md")  # 素材署名清单（CC 授权要求）

# ---------------------------------------------------------------------------
# 库文件：五个库的名字只在这里写一次
# ---------------------------------------------------------------------------
# 业务侧两份（脾气见 biz_db.py）：
#   travel2.sqlite      种子库：干净的演示数据，随时可以从它重建
#   travel_new.sqlite   运行副本：图和工具真正读写的那份，每次启动被种子库整份覆盖
# 外加一份国际数据集备份：seed_cn_data.py 首次重建成国内数据集前会存下来。
SEED_DB = os.path.join(DB_DIR, "travel2.sqlite")
BUSINESS_DB = os.path.join(DB_DIR, "travel_new.sqlite")
SEED_BACKUP_DB = os.path.join(DB_DIR, "travel2_intl_backup.sqlite")

# 应用侧的三个库（账号 / 存档 / 偏好）允许被整体挪走：测试设 TRIP_DESK_DB_DIR 指向
# 临时目录，跑一遍测试不会往开发库里塞账号、会话和订单。
#
# 注意**业务库不跟着挪**：update_dates() 要用种子库整份覆盖它，两份必须待在同一个
# 目录里；`web/orders.py` 里也有一条同样的备注（说的是别图省事去用 STATE_DB_DIR）。
STATE_DB_DIR = os.getenv("TRIP_DESK_DB_DIR") or DB_DIR
APP_DB = os.path.join(STATE_DB_DIR, "app.sqlite")                  # 账号 / 会话目录 / 订单 / 审计
CHECKPOINT_DB = os.path.join(STATE_DB_DIR, "checkpoints.sqlite")   # 对话存档（SqliteSaver 自己管）
PREFERENCES_DB = os.path.join(STATE_DB_DIR, "preferences.sqlite")  # 长期记忆：跨会话偏好档案
