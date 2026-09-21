"""把业务库重建成「国内旅行」数据集。

之前这份数据是从 Postgres flights 示例库搬来的国际航线（Basel / Zurich / SFO）。
本项目定位是**国内旅行攻略 + 订车/订票/订酒店**，所以这里重建一份国内数据。

运行（必须在 travel_agent_v2 目录内）：

    uv run python -m infra.scripts.seed_cn_data
    # 或：uv run python infra/scripts/seed_cn_data.py  （靠 cwd 找到 infra 包）

它做三件事：
1. 把旧的国际数据集备份成 db/travel2_intl_backup.sqlite（只在第一次备份）；
2. 生成 db/travel2.sqlite —— 种子库，update_dates() 每次启动都从它复制；
3. 顺手跑一次 update_dates()，把日期平移到「今天」，产出 db/travel_new.sqlite。

表结构沿用原来的列，工具层不用改：
- airports_data / flights / tickets / ticket_flights / boarding_passes / bookings
- hotels / car_rentals / trip_recommendations
- aircrafts_data / seats

城市字段存英文（Beijing / Chengdu），因为 infra/scripts/location_trans.py 会把模型传进来的
中文城市名翻译成英文再 LIKE 匹配。酒店、租车、景点的 name 保持中文（国内品牌）。
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

# 直接 `python infra/scripts/seed_cn_data.py` 时，sys.path[0] 是 scripts/ 而不是项目根，
# 会 ModuleNotFoundError: infra。cwd 才是项目根（README 要求在本目录启动），从 cwd 挂进去。
# 不写 __file__：路径推算只许待在 infra/paths.py。
if os.path.isfile(os.path.join(os.getcwd(), "infra", "paths.py")):
    sys.path.insert(0, os.getcwd())

from infra.paths import DB_DIR, ROOT, SEED_BACKUP_DB, SEED_DB
from infra.paths import BUSINESS_DB as LIVE_DB   # 「运行副本」在本脚本里叫 LIVE_DB（产出它的那一步）

HERE = ROOT   # 只在打印相对路径和 sys.path 里露脸，别的路径一律从 infra/paths.py 取


TZ = timezone(timedelta(hours=8))          # 全国统一用东八区，教学上够用
ANCHOR = datetime(2024, 4, 30, 12, 5, tzinfo=TZ)   # 与旧库一样：这个时刻之后算「未来」
WINDOW_BACK, WINDOW_FORWARD = 15, 12       # 航班生成窗口：anchor-15d .. anchor+12d

# ---------------------------------------------------------------------------
# 机场：(三字码, 机场名, 城市英文, 纬度, 经度)
# ---------------------------------------------------------------------------
AIRPORTS = [
    ("PEK", "北京首都国际机场", "Beijing", 40.0799, 116.6031),
    ("PKX", "北京大兴国际机场", "Beijing", 39.5098, 116.4105),
    ("SHA", "上海虹桥国际机场", "Shanghai", 31.1979, 121.3354),
    ("PVG", "上海浦东国际机场", "Shanghai", 31.1443, 121.8083),
    ("CTU", "成都双流国际机场", "Chengdu", 30.5785, 103.9470),
    ("TFU", "成都天府国际机场", "Chengdu", 30.3125, 104.4419),
    ("XIY", "西安咸阳国际机场", "Xian", 34.4471, 108.7516),
    ("HGH", "杭州萧山国际机场", "Hangzhou", 30.2295, 120.4344),
    ("CAN", "广州白云国际机场", "Guangzhou", 23.3924, 113.2988),
    ("SZX", "深圳宝安国际机场", "Shenzhen", 22.6393, 113.8107),
    ("KMG", "昆明长水国际机场", "Kunming", 25.1019, 102.9292),
    ("SYX", "三亚凤凰国际机场", "Sanya", 18.3029, 109.4123),
    ("CKG", "重庆江北国际机场", "Chongqing", 29.7192, 106.6417),
    ("XMN", "厦门高崎国际机场", "Xiamen", 24.5440, 118.1277),
    ("WUH", "武汉天河国际机场", "Wuhan", 30.7838, 114.2081),
    ("LXA", "拉萨贡嘎国际机场", "Lhasa", 29.2978, 90.9119),
    ("LJG", "丽江三义国际机场", "Lijiang", 26.6800, 100.2460),
    ("TAO", "青岛胶东国际机场", "Qingdao", 36.3617, 120.0886),
    ("HRB", "哈尔滨太平国际机场", "Harbin", 45.6234, 126.2500),
]

# 航司：呼号前缀 -> 名称（用来拼航班号，例如 CA1405）
AIRLINES = [
    ("CA", "中国国际航空"),
    ("MU", "中国东方航空"),
    ("CZ", "中国南方航空"),
    ("HU", "海南航空"),
    ("3U", "四川航空"),
    ("MF", "厦门航空"),
    ("ZH", "深圳航空"),
    ("HO", "吉祥航空"),
    ("9C", "春秋航空"),
]

# 机型：(代码, 型号, 航程公里)
AIRCRAFT = [
    ("320", "空客 A320", 5700),
    ("321", "空客 A321", 5600),
    ("330", "空客 A330", 11750),
    ("350", "空客 A350", 15000),
    ("738", "波音 737-800", 5400),
    ("789", "波音 787-9", 14140),
    ("ARJ", "中国商飞 ARJ21", 3700),
    ("C919", "中国商飞 C919", 5555),
]

# 航线：(机场A, 机场B, 飞行分钟)。生成时双向各排航班。
ROUTES = [
    ("PEK", "CTU", 180), ("PEK", "SHA", 140), ("PEK", "XIY", 150), ("PEK", "HGH", 140),
    ("PEK", "CAN", 200), ("PEK", "SYX", 250), ("PEK", "KMG", 230), ("PEK", "LXA", 290),
    ("PEK", "XMN", 190), ("PEK", "WUH", 145), ("PEK", "CKG", 175), ("PEK", "SZX", 210),
    ("PEK", "TAO", 105), ("PEK", "LJG", 245), ("PEK", "HRB", 130), ("PEK", "PKX", 0),
    ("SHA", "CTU", 190), ("SHA", "XIY", 150), ("SHA", "HGH", 60), ("SHA", "CAN", 150),
    ("SHA", "SYX", 200), ("SHA", "KMG", 220), ("SHA", "XMN", 110), ("SHA", "CKG", 170),
    ("SHA", "WUH", 110), ("SHA", "SZX", 150), ("SHA", "TAO", 110), ("SHA", "LJG", 230),
    ("SHA", "HRB", 170), ("SHA", "LXA", 330),
    ("CAN", "CTU", 150), ("CAN", "XIY", 160), ("CAN", "SYX", 90), ("CAN", "HGH", 130),
    ("CAN", "KMG", 140), ("CAN", "CKG", 140), ("CAN", "XMN", 80), ("CAN", "WUH", 120),
    ("CAN", "SZX", 55),
    ("CTU", "XIY", 90), ("CTU", "KMG", 80), ("CTU", "LXA", 150), ("CTU", "SYX", 180),
    ("CTU", "LJG", 80), ("CTU", "HGH", 170), ("CTU", "SZX", 150), ("CTU", "CKG", 60),
    ("XIY", "LXA", 180), ("XIY", "HGH", 150), ("XIY", "KMG", 140), ("XIY", "XMN", 180),
    ("SYX", "HGH", 180), ("SYX", "XMN", 150), ("SYX", "SZX", 90), ("SYX", "KMG", 160),
    ("KMG", "LJG", 60), ("HGH", "XMN", 90), ("HGH", "TAO", 110), ("WUH", "XMN", 110),
    ("CKG", "XIY", 90), ("HRB", "TAO", 150), ("LJG", "CKG", 110), ("XMN", "TAO", 130),
]
# 同城两场（PEK/PKX）不排航班，去掉占位项
ROUTES = [r for r in ROUTES if r[2] > 0]

# 每位旅客一条去程 + 一条回程；起飞日相对 anchor 的偏移
PASSENGERS = [
    {
        "passenger_id": "3442 587242",
        "ticket_no": "9990005432900001",
        "book_ref": "CN001A",
        "out": ("PEK", "CTU"),
        "back": ("CTU", "PEK"),
        "out_day": 1,
        "back_day": 8,
        "seat_out": "18A",
        "seat_back": "22C",
        "fare": "Economy",
    },
    {
        "passenger_id": "0000 000343",
        "ticket_no": "9990005432900002",
        "book_ref": "CN002B",
        "out": ("SHA", "SYX"),
        "back": ("SYX", "SHA"),
        "out_day": 2,
        "back_day": 7,
        "seat_out": "12F",
        "seat_back": "12F",
        "fare": "Comfort",
    },
    {
        "passenger_id": "0001 998571",
        "ticket_no": "9990005432900003",
        "book_ref": "CN003C",
        "out": ("CAN", "XIY"),
        "back": ("XIY", "CAN"),
        "out_day": 1,
        "back_day": 6,
        "seat_out": "9D",
        "seat_back": "14A",
        "fare": "Economy",
    },
    {
        # 运营账号自己的行程：不能和 carol 合住同一份档案，否则会话 / 偏好 / 机票都会串
        "passenger_id": "0002 445566",
        "ticket_no": "9990005432900004",
        "book_ref": "CN004D",
        "out": ("HGH", "TAO"),
        "back": ("TAO", "HGH"),
        "out_day": 3,
        "back_day": 9,
        "seat_out": "7A",
        "seat_back": "19C",
        "fare": "Economy",
    },
]

# 酒店：(名称, 城市英文, 价格档, 入住, 退房)
HOTELS = [
    ("王府井希尔顿酒店", "Beijing", "Luxury", "2026-05-02", "2026-05-05"),
    ("三里屯亚朵酒店", "Beijing", "Upscale", "2026-05-01", "2026-05-04"),
    ("前门全季酒店", "Beijing", "Midscale", "2026-05-03", "2026-05-06"),
    ("宽窄巷子亚朵酒店", "Chengdu", "Upscale", "2026-05-02", "2026-05-06"),
    ("春熙路全季酒店", "Chengdu", "Midscale", "2026-05-01", "2026-05-05"),
    ("太古里博舍酒店", "Chengdu", "Luxury", "2026-05-02", "2026-05-07"),
    ("外滩茂悦大酒店", "Shanghai", "Luxury", "2026-05-03", "2026-05-06"),
    ("静安寺亚朵酒店", "Shanghai", "Upscale", "2026-05-02", "2026-05-05"),
    ("西湖亚朵酒店", "Hangzhou", "Upscale", "2026-05-02", "2026-05-04"),
    ("灵隐山居客栈", "Hangzhou", "Midscale", "2026-05-01", "2026-05-03"),
    ("钟楼亚朵酒店", "Xian", "Upscale", "2026-05-02", "2026-05-05"),
    ("大唐不夜城全季酒店", "Xian", "Midscale", "2026-05-03", "2026-05-06"),
    ("亚龙湾万豪度假酒店", "Sanya", "Luxury", "2026-05-03", "2026-05-08"),
    ("海棠湾艾迪逊酒店", "Sanya", "Luxury", "2026-05-04", "2026-05-09"),
    ("珠江新城全季酒店", "Guangzhou", "Midscale", "2026-05-02", "2026-05-05"),
    ("鼓浪屿海景民宿", "Xiamen", "Midscale", "2026-05-03", "2026-05-06"),
    ("解放碑亚朵酒店", "Chongqing", "Upscale", "2026-05-02", "2026-05-05"),
    ("翠湖宾馆", "Kunming", "Midscale", "2026-05-01", "2026-05-04"),
    ("八大关海景酒店", "Qingdao", "Upscale", "2026-05-04", "2026-05-07"),
    ("布达拉宫旁亚朵酒店", "Lhasa", "Upscale", "2026-05-05", "2026-05-08"),
    ("中央大街马迭尔宾馆", "Harbin", "Upscale", "2026-05-02", "2026-05-05"),
    ("丽江古城纳西小院", "Lijiang", "Midscale", "2026-05-03", "2026-05-06"),
    ("武汉光谷全季酒店", "Wuhan", "Midscale", "2026-05-02", "2026-05-04"),
    ("深圳福田亚朵酒店", "Shenzhen", "Upscale", "2026-05-03", "2026-05-05"),
]

# 租车：(品牌, 城市英文, 车型档, 取车, 还车)
CAR_RENTALS = [
    ("神州租车", "Beijing", "SUV", "2026-05-02", "2026-05-05"),
    ("一嗨租车", "Beijing", "Economy", "2026-05-01", "2026-05-04"),
    ("悟空租车", "Chengdu", "SUV", "2026-05-02", "2026-05-06"),
    ("神州租车", "Chengdu", "Economy", "2026-05-01", "2026-05-05"),
    ("联动云租车", "Chengdu", "Midsize", "2026-05-03", "2026-05-06"),
    ("一嗨租车", "Shanghai", "Luxury", "2026-05-03", "2026-05-06"),
    ("首汽租车", "Shanghai", "Midsize", "2026-05-02", "2026-05-05"),
    ("神州租车", "Sanya", "SUV", "2026-05-03", "2026-05-08"),
    ("携程租车", "Sanya", "Economy", "2026-05-04", "2026-05-09"),
    ("一嗨租车", "Xian", "SUV", "2026-05-02", "2026-05-05"),
    ("悟空租车", "Guangzhou", "Midsize", "2026-05-02", "2026-05-05"),
    ("神州租车", "Hangzhou", "Economy", "2026-05-01", "2026-05-04"),
    ("联动云租车", "Kunming", "SUV", "2026-05-02", "2026-05-06"),
    ("首汽租车", "Xiamen", "Midsize", "2026-05-03", "2026-05-06"),
    ("一嗨租车", "Chongqing", "SUV", "2026-05-02", "2026-05-05"),
    ("神州租车", "Lhasa", "SUV", "2026-05-05", "2026-05-09"),
]

# 景点与玩法：(名称, 城市英文, 关键词, 攻略详情)
SPOTS = [
    ("大熊猫繁育研究基地", "Chengdu", "熊猫,亲子,动物",
     "看大熊猫要赶早，7:30 开园就进，上午熊猫最活跃。月亮产房适合拍幼崽，园区较大建议穿舒适的鞋，全程步行约 3 小时。"),
    ("宽窄巷子", "Chengdu", "老街,小吃,夜景",
     "由宽巷子、窄巷子、井巷子组成，免费开放。傍晚灯亮后最好看，可顺路吃钵钵鸡、三大炮。人流量大，周末建议避开 19:00—21:00 高峰。"),
    ("都江堰景区", "Chengdu", "世界遗产,水利,一日游",
     "距成都市区约 1 小时车程，与青城山可拼一天。重点看鱼嘴、飞沙堰、宝瓶口三大主体工程，建议请讲解或租语音导览，否则容易看不懂。"),
    ("锦里古街", "Chengdu", "小吃,三国,夜景",
     "紧邻武侯祠，以三国文化和川西民俗为主题。晚上红灯笼很好看，小吃价格偏景区价，想吃得划算可以去周边小街。"),
    ("武侯祠博物馆", "Chengdu", "三国,历史,博物馆",
     "全国影响最大的三国遗迹博物馆，与锦里相连。建议先看文物区再看园林区，旺季需提前在官方渠道预约门票。"),
    ("人民公园鹤鸣茶社", "Chengdu", "茶馆,市井,慢生活",
     "成都最地道的盖碗茶体验，一碗茶能坐一下午，可体验采耳。工作日上午人少，周末需要早点去占竹椅。"),
    ("故宫博物院", "Beijing", "博物馆,世界遗产,亲子",
     "需提前实名预约，周一闭馆（法定节假日除外）。建议从午门进、神武门出，中轴线走完约 3 小时；想避开人流可开门就进。"),
    ("八达岭长城", "Beijing", "长城,世界遗产,徒步",
     "距市区约 1.5 小时车程，建议上午去，下午风大。北八楼视野最好但坡陡，体力一般可坐缆车。旺季需提前预约，穿防滑鞋。"),
    ("颐和园", "Beijing", "园林,世界遗产,划船",
     "中国现存规模最大的皇家园林，昆明湖可划船。建议从东宫门进，沿长廊到佛香阁，全程约 3 小时；旺季门票需预约。"),
    ("南锣鼓巷", "Beijing", "胡同,小吃,文创",
     "老北京胡同肌理保存较好，主街商业化重，拐进两侧胡同更有味道。适合傍晚逛，可与什刹海连着走。"),
    ("天坛公园", "Beijing", "世界遗产,古建,晨练",
     "祈年殿是标志性建筑，早上能看到本地人晨练、唱戏。公园门票与祈年殿联票分开卖，想看建筑要买联票。"),
    ("秦始皇兵马俑博物馆", "Xian", "世界遗产,历史,必去",
     "建议按一号坑、三号坑、二号坑的顺序看，先看纪录片再进展厅理解更深。距市区约 1 小时车程，可与华清宫拼一日游。"),
    ("大雁塔", "Xian", "古建,历史,夜景",
     "大慈恩寺内，登塔需另购票。晚上北广场有音乐喷泉，是本地人纳凉的热门去处，喷泉表演时间以现场公告为准。"),
    ("西安城墙", "Xian", "古城,骑行,夜景",
     "国内保存最完整的古代城垣，可租自行车环城骑行一圈约 100 分钟。傍晚登城最舒服，日落和亮灯都能看到。"),
    ("回民街", "Xian", "小吃,夜市,烟火气",
     "牛羊肉泡馍、肉夹馍、甑糕都能找到。主街偏游客向，想吃本地味可以往洒金桥方向走。"),
    ("亚龙湾", "Sanya", "海滩,度假,亲子",
     "沙质细、水清，适合下海和浮潜。酒店多带私家沙滩，出行以打车为主。紫外线强，注意防晒和补涂。"),
    ("蜈支洲岛", "Sanya", "海岛,潜水,一日游",
     "需坐船上岛，建议一早出发避开排队。潜水、摩托艇等水上项目较多，岛上餐饮偏贵，可自带水和零食。"),
    ("南山文化旅游区", "Sanya", "佛教,文化,海景",
     "以海上观音像闻名，园区很大，建议坐电瓶车。着装得体一些，园区内步行路段较晒。"),
    ("外滩", "Shanghai", "夜景,建筑,免费",
     "万国建筑博览群，对岸是陆家嘴天际线。夜景亮灯后最值得看，建议从南京东路步行过去，江边风大记得加外套。"),
    ("豫园", "Shanghai", "园林,老城,小吃",
     "明代江南园林，与城隍庙、豫园商城连在一起。园林需买票，商城免费；南翔小笼排队久，可错峰。"),
    ("田子坊", "Shanghai", "文创,石库门,小店",
     "石库门里弄改造的文创街区，适合逛小店和咖啡馆。巷子窄，周末人多，工作日下午最舒服。"),
    ("西湖", "Hangzhou", "世界遗产,骑行,免费",
     "环湖免费，苏堤白堤适合骑行或步行。断桥、雷峰塔、三潭印月各有看点；避开节假日，清晨人少景好。"),
    ("灵隐寺", "Hangzhou", "寺庙,祈福,山林",
     "需先买飞来峰景区门票再买寺院香花券。寺内素面口碑不错，飞来峰石刻值得细看。山林湿滑，雨天注意脚下。"),
    ("西溪湿地", "Hangzhou", "湿地,慢游,摇橹船",
     "以摇橹船和水乡景致为主，建议留半天。东区开发更成熟，西区更安静；春天芦苇和梅花季最好看。"),
    ("鼓浪屿", "Xiamen", "海岛,世界遗产,建筑",
     "需提前网上购票坐轮渡，岛上不通行机动车。万国建筑和钢琴博物馆是重点，建议住一晚避开一日游人潮。"),
    ("环岛路", "Xiamen", "海岸,骑行,日出",
     "沿海骑行道风景极好，可租双人自行车。清晨看日出、傍晚看日落都合适，注意防晒。"),
    ("滇池", "Kunming", "湖泊,海鸥,散步",
     "冬季红嘴鸥聚集，是昆明标志性景观。可沿海埂大坝散步，周边有索道可上西山看全景。"),
    ("石林风景区", "Kunming", "喀斯特,地质,一日游",
     "喀斯特地貌代表，距昆明约 1.5 小时车程。园区大，建议坐电瓶车并按指示牌走，穿防滑鞋。"),
    ("丽江古城", "Lijiang", "古城,世界遗产,夜生活",
     "四方街、木府是核心，晚上酒吧街热闹。石板路多，行李箱不太好拖，建议选靠近入口的住宿。"),
    ("玉龙雪山", "Lijiang", "雪山,索道,高原",
     "海拔高，需提前预约大索道，建议备氧气瓶和防寒服。上索道后不要剧烈运动，心脏不适者谨慎前往。"),
    ("洪崖洞", "Chongqing", "夜景,吊脚楼,免费",
     "夜景是招牌，从千厮门大桥拍全景最好。旺季限流需预约，建议 19:00 前到，避免人挤人。"),
    ("磁器口古镇", "Chongqing", "古镇,小吃,老街",
     "麻花和陈麻花是招牌，主街较商业化，往江边走更清净。可与李子坝轻轨站串成半天行程。"),
    ("布达拉宫", "Lhasa", "世界遗产,藏族,预约",
     "需提前预约且分时段参观，宫内不允许拍照。台阶多，刚到拉萨建议先适应一天再登宫，避免高反。"),
    ("大昭寺", "Lhasa", "寺庙,信仰,八廓街",
     "藏传佛教圣地，门口可见信众磕长头。围绕寺庙的八廓街适合转经和买手信，注意顺时针行走。"),
    ("栈桥", "Qingdao", "海岸,地标,免费",
     "青岛老城地标，冬天有海鸥。可与中山路、八大关串起来逛，海边风大注意保暖。"),
    ("八大关", "Qingdao", "建筑,梧桐,骑行",
     "以各国风格别墅和梧桐道闻名，适合慢走或骑行。花石楼、公主楼可单独购票参观。"),
    ("中央大街", "Harbin", "老街,建筑,冰棍",
     "面包石铺成的百年老街，马迭尔冰棍是必打卡。冬天极冷，注意手脚保暖；可步行到松花江边。"),
    ("冰雪大世界", "Harbin", "冰雪,冬季,夜场",
     "冬季限定，晚上灯光最漂亮，建议 16:00 后入园。场地大且极冷，务必穿厚羽绒和防滑雪地靴，暖宝宝必备。"),
]


# 价格：酒店每晚、租车每天、景点门票。放在单独列表里，顺序与上面的清单严格对应，
# 改动清单时记得同步这里，否则会串行。订单中心按这些价格算金额。
HOTEL_PRICES = [
    1200, 600, 380, 620, 350, 1800, 1500, 580, 650, 420, 560, 360,
    1800, 2600, 400, 480, 520, 450, 700, 780, 620, 380, 330, 590,
]
CAR_PRICES = [
    450, 199, 420, 189, 260, 880, 280, 460, 210, 430, 270, 195, 440, 290, 450, 520,
]
SPOT_PRICES = [
    55, 0, 80, 0, 50, 0, 60, 40, 30, 0, 34, 120, 50, 54, 0, 0, 144, 129, 0, 40,
    0, 0, 45, 80, 100, 0, 0, 130, 50, 100, 0, 0, 200, 85, 0, 0, 0, 330,
]


def _minutes_to_dt(day: datetime, minutes: int) -> datetime:
    """把「某天 + 第几分钟」拼成时间戳。

    :param day: 基准日期（date）
    :param minutes: 从当天 0 点起的分钟数
    :return: datetime
    """
    return day.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=minutes)


def _fmt(dt: datetime) -> str:
    """把时间戳格式化成库里存的字符串。

    :param dt: datetime（或 None）
    :return: 'YYYY-MM-DD HH:MM:SS' 字符串；None 原样返回 None
    """
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f") + "+08:00"


def _slots(index: int) -> int:
    """按航班序号轮换起飞时段：早班 / 午班 / 晚班。"""
    return [7 * 60 + 30, 13 * 60 + 10, 19 * 60 + 40][index % 3]


def _route_airline(a: str, b: str) -> tuple[str, str]:
    """给航线定一个固定航司：按起降机场字符和取模，保证每次生成结果一致。"""
    seed = sum(ord(ch) for ch in (a + b))
    return AIRLINES[seed % len(AIRLINES)]


def build_flights(airports: dict) -> tuple[list[tuple], list[tuple]]:
    """按航班号前缀给每个航段排班，造出成对的去程 / 回程。

    :param airports: 机场行（含三字码与城市）
    :return: (flight_rows, by_key) 二元组；by_key 供后续造票与座位时按航线索引
    """
    flights, flights_by_key = [], {}
    flight_id = 1000
    for a, b, minutes in ROUTES:
        for origin, dest in ((a, b), (b, a)):
            prefix, _airline = _route_airline(origin, dest)
            for step in range(-WINDOW_BACK, WINDOW_FORWARD + 1):
                day = ANCHOR + timedelta(days=step)
                if minutes >= 240 and step % 2:      # 长航线隔天排，避免生成太满
                    continue
                dep = _minutes_to_dt(day, _slots(flight_id))
                arr = dep + timedelta(minutes=minutes)
                scheduled_dep = dep.astimezone(TZ)
                scheduled_arr = (dep + timedelta(minutes=minutes)).astimezone(TZ)
                # anchor 之前算「已经飞过」，填 actual；之后仍是未来，留空
                if scheduled_dep <= ANCHOR:
                    actual_dep = scheduled_dep + timedelta(minutes=11)
                    actual_arr = scheduled_arr + timedelta(minutes=7)
                    status = "Arrived"
                    ad, aa = _fmt(actual_dep), _fmt(actual_arr)
                else:
                    status = "Scheduled"
                    ad, aa = None, None
                flight_no = f"{prefix}{flight_id % 9000:04d}"
                row = (
                    flight_id, flight_no, _fmt(scheduled_dep), _fmt(scheduled_arr),
                    origin, dest, status, _pick_aircraft(minutes), ad, aa,
                )
                flights.append(row)
                flights_by_key.setdefault((origin, dest), []).append(
                    {"flight_id": flight_id, "dep": scheduled_dep, "minutes": minutes}
                )
                flight_id += 1
    for items in flights_by_key.values():
        items.sort(key=lambda item: item["dep"])
    return flights, flights_by_key


def _pick_aircraft(minutes: int) -> str:
    """按飞行时长挑一个机型名（短途窄体、长途宽体）。

    :param minutes: 飞行分钟数
    :return: 机型字符串
    """
    if minutes >= 240:
        return ["330", "350", "789"][minutes % 3]
    if minutes >= 120:
        return ["321", "738", "320"][minutes % 3]
    return ["320", "ARJ", "C919"][minutes % 3]


def build_passenger_rows(flights_by_key: dict) -> tuple[list, list, list, list]:
    """给演示旅客发机票：挑两条航线，凑出去程 / 回程两张票。

    :param flights_by_key: `build_flights` 返回的航线索引
    :return: (ticket_rows, ticket_flight_rows)
    """
    tickets, ticket_flights, boarding_passes, bookings = [], [], [], []
    seat_pool = [
        "12A", "12C", "14A", "14F", "16C", "18A", "20F", "22C", "25A", "28D",
        "31F", "33A", "36C", "39A", "41F", "44C", "47A", "50D",
    ]
    for idx, pax in enumerate(PASSENGERS):
        tickets.append((pax["ticket_no"], pax["book_ref"], pax["passenger_id"]))
        total = 0
        legs = [
            (pax["out"], pax["out_day"], pax["seat_out"]),
            (pax["back"], pax["back_day"], pax["seat_back"]),
        ]
        for leg_no, ((origin, dest), day_offset, seat) in enumerate(legs):
            target = ANCHOR + timedelta(days=day_offset)
            options = [
                item for item in flights_by_key.get((origin, dest), [])
                if item["dep"] >= target
            ]
            if not options:
                options = flights_by_key.get((origin, dest), [])
            flight = options[0]
            amount = int(300 + flight["minutes"] * 2.2)
            if pax["fare"] == "Comfort":
                amount = int(amount * 1.35)
            elif pax["fare"] == "Business":
                amount = int(amount * 2.6)
            total += amount
            ticket_flights.append((pax["ticket_no"], flight["flight_id"], pax["fare"], amount))
            boarding_passes.append(
                (pax["ticket_no"], flight["flight_id"], 40 + idx * 10 + leg_no, seat or seat_pool[(idx * 3 + leg_no) % len(seat_pool)])
            )
        bookings.append((pax["book_ref"], _fmt(ANCHOR - timedelta(days=20 + idx)), total))
    return tickets, ticket_flights, boarding_passes, bookings


def build_seats() -> list[tuple]:
    """给每张票分配座位号（按舱位分区）。

    :return: 登机牌行列表
    """
    rows = []
    for code, _model, _range in AIRCRAFT:
        for row_no in range(1, 9):
            for letter in ("A", "C", "F"):
                fare = "Business" if row_no <= 2 else "Economy"
                rows.append((code, f"{row_no}{letter}", fare))
    return rows


SCHEMA = """
DROP TABLE IF EXISTS airports_data;
CREATE TABLE airports_data (airport_code TEXT, airport_name TEXT, city TEXT, coordinates TEXT, timezone TEXT);
DROP TABLE IF EXISTS flights;
CREATE TABLE flights (flight_id INTEGER, flight_no TEXT, scheduled_departure TIMESTAMP, scheduled_arrival TIMESTAMP,
                      departure_airport TEXT, arrival_airport TEXT, status TEXT, aircraft_code TEXT,
                      actual_departure TIMESTAMP, actual_arrival TIMESTAMP);
DROP TABLE IF EXISTS tickets;
CREATE TABLE tickets (ticket_no TEXT, book_ref TEXT, passenger_id TEXT);
DROP TABLE IF EXISTS ticket_flights;
CREATE TABLE ticket_flights (ticket_no TEXT, flight_id INTEGER, fare_conditions TEXT, amount INTEGER);
DROP TABLE IF EXISTS boarding_passes;
CREATE TABLE boarding_passes (ticket_no TEXT, flight_id INTEGER, boarding_no INTEGER, seat_no TEXT);
DROP TABLE IF EXISTS bookings;
CREATE TABLE bookings (book_ref TEXT, book_date TIMESTAMP, total_amount INTEGER);
DROP TABLE IF EXISTS hotels;
CREATE TABLE hotels (id INTEGER, name TEXT, location TEXT, price_tier TEXT,
                     checkin_date TEXT, checkout_date TEXT, price_per_night INTEGER, booked INTEGER);
DROP TABLE IF EXISTS car_rentals;
CREATE TABLE car_rentals (id INTEGER, name TEXT, location TEXT, price_tier TEXT,
                          start_date TEXT, end_date TEXT, price_per_day INTEGER, booked INTEGER);
DROP TABLE IF EXISTS trip_recommendations;
CREATE TABLE trip_recommendations (id INTEGER, name TEXT, location TEXT, keywords TEXT,
                                   details TEXT, ticket_price INTEGER, booked INTEGER);
DROP TABLE IF EXISTS aircrafts_data;
CREATE TABLE aircrafts_data (aircraft_code TEXT, model TEXT, range INTEGER);
DROP TABLE IF EXISTS seats;
CREATE TABLE seats (aircraft_code TEXT, seat_no TEXT, fare_conditions TEXT);
"""


def _insert(conn, table: str, rows: list[tuple]) -> None:
    """把一批行插进某张表（列名由行长决定，表结构必须是自建的）。

    :param conn: 业务库连接
    :param table: 目标表名
    :param rows: 行列表（dict）
    """
    placeholders = ",".join("?" * len(rows[0]))
    conn.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)


def seed(path: str = SEED_DB) -> str:
    """重建整套国内演示数据：机场 / 航班 / 票 / 座位 / 酒店 / 租车 / 景点 / 旅客。

    先删旧表再建，所以它是「从零重建」，不是「增量更新」。

    :param path: 目标库文件路径（默认写种子库）
    """
    airports = {code: (code, name, city, lat, lon) for code, name, city, lat, lon in AIRPORTS}
    flights, flights_by_key = build_flights(airports)
    tickets, ticket_flights, boarding_passes, bookings = build_passenger_rows(flights_by_key)

    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        _insert(conn, "airports_data", [
            (code, name, city, json.dumps([lat, lon]), "Asia/Shanghai")
            for code, name, city, lat, lon in AIRPORTS
        ])
        _insert(conn, "flights", flights)
        _insert(conn, "tickets", tickets)
        _insert(conn, "ticket_flights", ticket_flights)
        _insert(conn, "boarding_passes", boarding_passes)
        _insert(conn, "bookings", bookings)
        _insert(conn, "hotels", [
            (i + 1, name, loc, tier, ci, co, HOTEL_PRICES[i], 0)
            for i, (name, loc, tier, ci, co) in enumerate(HOTELS)
        ])
        _insert(conn, "car_rentals", [
            (i + 1, name, loc, tier, sd, ed, CAR_PRICES[i], 0)
            for i, (name, loc, tier, sd, ed) in enumerate(CAR_RENTALS)
        ])
        _insert(conn, "trip_recommendations", [
            (i + 1, name, loc, kw, detail, SPOT_PRICES[i], 0)
            for i, (name, loc, kw, detail) in enumerate(SPOTS)
        ])
        _insert(conn, "aircrafts_data", AIRCRAFT)
        _insert(conn, "seats", build_seats())
        conn.commit()
        # DROP TABLE 只是把页标成空闲，不还盘；VACUUM 之后文件才真正变小
        conn.execute("VACUUM")
    finally:
        conn.close()
    return path


def main() -> None:
    """命令行入口：直接跑一次 seed()，打一行结果。

    :return: 无
    """
    os.makedirs(DB_DIR, exist_ok=True)
    if os.path.exists(SEED_DB) and not os.path.exists(SEED_BACKUP_DB):
        shutil.copy2(SEED_DB, SEED_BACKUP_DB)
        print(f"旧国际数据集已备份：{os.path.relpath(SEED_BACKUP_DB, HERE)}")

    seed(SEED_DB)
    size = os.path.getsize(SEED_DB) / 1024 / 1024
    print(f"国内数据集已写入 {os.path.relpath(SEED_DB, HERE)} （{size:.1f} MB）")

    # 平移日期，产出运行库
    from infra.biz_db import update_dates

    update_dates()
    conn = sqlite3.connect(LIVE_DB)
    try:
        conn.execute("VACUUM")
        counts = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("airports_data", "flights", "tickets", "hotels", "car_rentals", "trip_recommendations")
        }
        legs = conn.execute(
            """
            SELECT f.flight_no, f.departure_airport, f.arrival_airport, f.scheduled_departure
            FROM tickets t
            JOIN ticket_flights tf ON t.ticket_no = tf.ticket_no
            JOIN flights f ON tf.flight_id = f.flight_id
            WHERE t.passenger_id = '3442 587242'
            ORDER BY f.scheduled_departure
            """
        ).fetchall()
    finally:
        conn.close()
    print("运行库行数：", counts)
    for row in legs:
        print("  默认旅客航段：", row)


if __name__ == "__main__":
    main()
