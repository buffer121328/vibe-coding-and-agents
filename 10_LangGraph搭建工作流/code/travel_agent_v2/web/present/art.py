"""城市几何标记：给每个城市一枚地标图形。

为什么自己画：这个项目不能引入 npm 构建链，也不该依赖外链图片（离线要能跑）。
所以用纯几何图形做城市标记——圆、矩形、多边形，扁平单色，像机场里的地标图标，
而不是"用 SVG 假装照片"（那种描摹照片的做法既不像又廉价）。

每枚图形都是 `viewBox="0 0 64 64"`，用 `currentColor` 上色，
所以同一个函数既能放进票面的深色方块，也能放进浅色的卡片角标。
"""
from __future__ import annotations

import os

from infra.paths import CITIES_DIR

# 每个城市一段 SVG 图形（不含外层 <svg>）。形状刻意保持少而清晰，
# 目标是缩小到 28px 还认得出，而不是放大后有多少细节。
ART = {
    # 北京：天坛三层圆顶
    "PEK": """
      <polygon points="32,7 35,14 29,14"/>
      <circle cx="32" cy="20" r="9"/>
      <rect x="21" y="28" width="22" height="4"/>
      <rect x="18" y="34" width="28" height="4"/>
      <rect x="15" y="40" width="34" height="4"/>
      <rect x="12" y="46" width="40" height="5"/>
      <rect x="9" y="53" width="46" height="4"/>
    """,
    # 成都：熊猫头
    "CTU": """
      <circle cx="17" cy="19" r="7"/>
      <circle cx="47" cy="19" r="7"/>
      <circle cx="32" cy="34" r="18"/>
      <ellipse cx="24" cy="30" rx="5" ry="6.5"/>
      <ellipse cx="40" cy="30" rx="5" ry="6.5"/>
      <circle cx="32" cy="41" r="3.2"/>
      <path d="M26 47 q6 5 12 0" fill="none" stroke="currentColor" stroke-width="2.4"/>
    """,
    # 上海：东方明珠与楼群
    "SHA": """
      <rect x="30" y="5" width="4" height="10"/>
      <circle cx="32" cy="22" r="8"/>
      <rect x="30" y="28" width="4" height="14"/>
      <circle cx="32" cy="48" r="6"/>
      <polygon points="24,60 40,60 36,54 28,54"/>
      <rect x="46" y="28" width="7" height="32"/>
      <rect x="12" y="38" width="6" height="22"/>
    """,
    # 三亚：椰树与浪
    "SYX": """
      <path d="M30 54 q-3 -18 2 -26" fill="none" stroke="currentColor" stroke-width="3.4"/>
      <path d="M32 26 q-13 -7 -20 2 q11 -3 20 3 Z"/>
      <path d="M32 26 q13 -7 20 2 q-11 -3 -20 3 Z"/>
      <path d="M32 25 q-4 -12 3 -19 q1 11 -3 19 Z"/>
      <path d="M4 56 q8 -5 16 0 q8 5 16 0 q8 -5 16 0 q4 2 8 1" fill="none"
            stroke="currentColor" stroke-width="2.6"/>
    """,
    # 西安：钟楼
    "XIY": """
      <polygon points="32,6 36,13 28,13"/>
      <rect x="20" y="13" width="24" height="4"/>
      <rect x="23" y="17" width="18" height="10"/>
      <rect x="16" y="27" width="32" height="4"/>
      <rect x="13" y="31" width="38" height="10"/>
      <rect x="8" y="41" width="48" height="5"/>
      <rect x="6" y="48" width="52" height="4"/>
    """,
    # 杭州：拱桥与塔
    "HGH": """
      <path d="M4 50 q14 -16 28 0" fill="none" stroke="currentColor" stroke-width="3.4"/>
      <rect x="4" y="48" width="56" height="5"/>
      <rect x="44" y="20" width="10" height="24"/>
      <polygon points="49,8 54,20 44,20"/>
      <rect x="42" y="26" width="14" height="3"/>
      <path d="M6 60 q9 -4 18 0 q9 4 18 0 q9 -4 16 0" fill="none"
            stroke="currentColor" stroke-width="2.4"/>
    """,
    # 广州：小蛮腰
    "CAN": """
      <polygon points="32,6 36,26 35,42 32,56 29,42 28,26"/>
      <ellipse cx="32" cy="20" rx="7" ry="3"/>
      <ellipse cx="32" cy="34" rx="5" ry="2.4"/>
      <rect x="20" y="40" width="7" height="20"/>
      <rect x="38" y="44" width="7" height="16"/>
      <rect x="46" y="34" width="6" height="26"/>
    """,
    # 深圳：楼群天际线
    "SZX": """
      <rect x="6" y="34" width="9" height="26"/>
      <rect x="17" y="24" width="9" height="36"/>
      <rect x="28" y="42" width="8" height="18"/>
      <rect x="38" y="14" width="10" height="46"/>
      <polygon points="43,6 46,14 40,14"/>
      <rect x="50" y="30" width="8" height="30"/>
    """,
    # 昆明：石林
    "KMG": """
      <polygon points="10,58 14,24 18,58"/>
      <polygon points="22,58 26,14 30,58"/>
      <polygon points="34,58 38,30 42,58"/>
      <polygon points="46,58 50,20 54,58"/>
      <rect x="4" y="56" width="56" height="4"/>
    """,
    # 重庆：山城层叠
    "CKG": """
      <path d="M2 58 q14 -14 28 -6 q14 -12 32 -4" fill="none" stroke="currentColor" stroke-width="3"/>
      <rect x="12" y="26" width="10" height="20"/>
      <rect x="26" y="16" width="11" height="30"/>
      <rect x="24" y="12" width="15" height="4"/>
      <rect x="42" y="32" width="10" height="14"/>
    """,
    # 厦门：鼓浪屿灯塔与浪
    "XMN": """
      <polygon points="32,8 38,46 26,46"/>
      <rect x="28" y="46" width="8" height="8"/>
      <rect x="22" y="54" width="20" height="4"/>
      <path d="M4 50 q8 -5 16 0 q8 5 16 0 q8 -5 16 0 q4 2 8 1" fill="none"
            stroke="currentColor" stroke-width="2.6"/>
    """,
    # 武汉：黄鹤楼
    "WUH": """
      <polygon points="32,4 35,10 29,10"/>
      <rect x="22" y="10" width="20" height="4"/>
      <rect x="17" y="14" width="30" height="4"/>
      <rect x="25" y="18" width="14" height="9"/>
      <rect x="14" y="27" width="36" height="4"/>
      <rect x="22" y="31" width="20" height="9"/>
      <rect x="10" y="40" width="44" height="4"/>
      <rect x="18" y="44" width="28" height="12"/>
      <rect x="6" y="56" width="52" height="4"/>
    """,
    # 拉萨：布达拉宫
    "LXA": """
      <rect x="26" y="18" width="12" height="34"/>
      <polygon points="32,8 36,18 28,18"/>
      <rect x="14" y="28" width="12" height="24"/>
      <rect x="38" y="26" width="12" height="26"/>
      <rect x="44" y="18" width="7" height="8"/>
      <polygon points="47,11 50,18 44,18"/>
      <rect x="8" y="52" width="48" height="5"/>
      <rect x="5" y="57" width="54" height="3"/>
    """,
    # 丽江：玉龙雪山
    "LJG": """
      <polygon points="2,58 22,18 34,44 40,32 62,58"/>
      <polygon points="22,18 28,29 16,29"/>
      <polygon points="40,32 44,39 36,39"/>
      <rect x="2" y="58" width="60" height="3"/>
    """,
    # 青岛：栈桥与亭
    "TAO": """
      <rect x="4" y="44" width="40" height="4"/>
      <rect x="10" y="48" width="4" height="8"/>
      <rect x="22" y="48" width="4" height="8"/>
      <rect x="34" y="48" width="4" height="8"/>
      <rect x="44" y="30" width="14" height="14"/>
      <polygon points="51,20 58,30 44,30"/>
      <rect x="49" y="16" width="4" height="5"/>
      <path d="M2 58 q8 -5 16 0 q8 5 16 0 q8 -5 16 0 q6 3 12 1" fill="none"
            stroke="currentColor" stroke-width="2.6"/>
    """,
    # 哈尔滨：索菲亚教堂洋葱顶
    "HRB": """
      <path d="M32 8 q9 8 9 16 q0 7 -9 7 q-9 0 -9 -7 q0 -8 9 -16 Z"/>
      <rect x="30" y="4" width="4" height="6"/>
      <rect x="28" y="31" width="8" height="7"/>
      <rect x="20" y="38" width="24" height="20"/>
      <polygon points="14,38 20,30 20,38"/>
      <polygon points="50,38 44,30 44,38"/>
      <rect x="28" y="48" width="8" height="10"/>
      <rect x="12" y="58" width="40" height="3"/>
    """,
}

# 同城两场共用一枚图形（旅客看不出差别，也没必要画两枚）
ALIAS = {"PKX": "PEK", "PVG": "SHA", "TFU": "CTU"}


# 按业务类型区分的小图形：同一座城市里，景点/酒店/租车各用各的图标，
# 不然一列卡片全是同一张缩略图，反而看不出差别。
KIND_ART = {
    "spot": """
      <circle cx="32" cy="20" r="8"/>
      <path d="M14 46 q18 -14 36 0" fill="none" stroke="currentColor" stroke-width="3.4"/>
      <rect x="10" y="49" width="44" height="4"/>
    """,
    "hotel": """
      <rect x="10" y="30" width="44" height="22"/>
      <rect x="10" y="18" width="44" height="8"/>
      <rect x="18" y="36" width="12" height="9" fill="#fffdf8"/>
      <rect x="36" y="36" width="12" height="9" fill="#fffdf8"/>
      <rect x="26" y="9" width="12" height="7"/>
    """,
    "car": """
      <path d="M10 40 l6 -14 h32 l6 14 Z"/>
      <rect x="8" y="40" width="48" height="9"/>
      <circle cx="20" cy="51" r="6" fill="#fffdf8"/>
      <circle cx="44" cy="51" r="6" fill="#fffdf8"/>
    """,
    "flight": """
      <path d="M6 34 l50 -20 -14 20 14 20 Z"/>
    """,
}


def kind_art(kind: str, size: int = 34) -> str:
    """按业务种类给一枚小图形（卡片上的角标）。

    :param kind: flight / hotel / car / spot
    :param size: 图形边长像素
    :return: 内联 SVG 字符串
    """
    body = KIND_ART.get(kind)
    if not body:
        return ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="{size}" height="{size}" '
        f'aria-hidden="true" fill="currentColor">{body}</svg>'
    )


PHOTO_DIR = "/static/img/cities"      # 给浏览器看的 URL（不是文件系统路径）
_PHOTO_KEYS: dict[str, set[str]] = {}   # 目录里到底有哪些照片，第一次用时扫一遍


def _photo_keys() -> set[str]:
    """目录里现成的实景照三字码集合（第一次调用扫目录，之后走缓存）。

    缓存故意放在 dict 里**原地写**，不做模块级重新绑定：`_AVAILABLE = xxx` 这种写法
    配上别处一句 `from ... import _AVAILABLE`，别人拿到的就永远是初始值 None。
    本仓真发生过一次同型事故（`web/runtime/hub.GRAPH` 被按值 import 抓成 None），
    所以这里连同 `tests/test_layering.py` 的静态检查一起避开这种写法。

    :return: 形如 {"PEK", "CTU", ...} 的三字码集合；目录读不到就是空集合
    """
    cached = _PHOTO_KEYS.get("keys")
    if cached is not None:
        return cached
    try:
        keys = {f[:-4].upper() for f in os.listdir(CITIES_DIR) if f.endswith(".jpg")}
    except OSError:
        keys = set()
    _PHOTO_KEYS["keys"] = keys
    return keys


def photo(code: str) -> str:
    """城市的实景照路径；没有这张照片就返回空串，调用方回退到几何图形。

    :param code: 机场三字码（大小写都行，内部会走别名表）
    :return: 形如 `/static/img/cities/PEK.jpg` 的 URL；没有照片就是空串
    """
    key = (code or "").upper()
    key = ALIAS.get(key, key)
    if not key:
        return ""
    return f"{PHOTO_DIR}/{key}.jpg" if key in _photo_keys() else ""


def has_art(code: str) -> bool:
    """这个城市有没有现成的几何标记（没有就得回退到默认图）。

    :param code: 机场三字码
    :return: bool
    """
    return (code or "").upper() in ART or (code or "").upper() in ALIAS


def tile(code: str, size: int = 40, label: str = "") -> str:
    """返回一枚城市标记的 SVG（含外层 <svg>）。取不到图形就返回一个占位方块。

    `label` 会写进 aria-label，读屏软件能念出来，不然这枚图对无障碍用户就是空白。
    """
    key = (code or "").upper()
    key = ALIAS.get(key, key)
    body = ART.get(key)
    if body is None:
        body = '<rect x="14" y="14" width="36" height="36" rx="3"/>'
    aria = f"{label or key} 城市标记"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="{size}" height="{size}" '
        f'role="img" aria-label="{aria}" fill="currentColor">{body}</svg>'
    )


# ---------------------------------------------------------------------------
# 行程地图
# ---------------------------------------------------------------------------
# 底图用 Wikimedia 的定位地图（等距圆柱投影，边界是公开的），
# 下载一次放 static/img/map/china.svg，之后完全离线可用。
# 这类地图的投影是线性的：经纬度 -> 画布坐标只需一个比例换算，
# 所以站点位置能算准，不用猜。
MAP_PATH = "/static/img/map/china.svg"
MAP_W, MAP_H = 1181.0, 940.0
MAP_TOP, MAP_BOTTOM = 54.0, 17.0        # 北纬 54 到北纬 17
MAP_LEFT, MAP_RIGHT = 72.0, 136.0       # 东经 72 到东经 136

# 省会级城市（含直辖市与自治区首府，共 31 座）——地图的底点层。
# 为什么单独写一张静态表：它是**地理常识**，不是业务数据。业务库里的机场是"能订票的
# 城市"，会随种子数据变；而地图不该因为库里少了一个城市就变成一片空白。坐标取市中心的
# 公开经纬度，两位小数足够（一位小数在底图上就是几十公里）。
CAPITALS: list[tuple[str, str, float, float]] = [
    ("PEK", "北京", 116.41, 39.90), ("TSN", "天津", 117.20, 39.13),
    ("SJW", "石家庄", 114.51, 38.04), ("TYN", "太原", 112.55, 37.87),
    ("HET", "呼和浩特", 111.75, 40.84), ("SHE", "沈阳", 123.43, 41.80),
    ("CGQ", "长春", 125.32, 43.82), ("HRB", "哈尔滨", 126.53, 45.80),
    ("SHA", "上海", 121.47, 31.23), ("NKG", "南京", 118.78, 32.06),
    ("HGH", "杭州", 120.15, 30.27), ("HFE", "合肥", 117.28, 31.86),
    ("FOC", "福州", 119.30, 26.08), ("KHN", "南昌", 115.89, 28.68),
    ("TNA", "济南", 117.00, 36.65), ("CGO", "郑州", 113.62, 34.75),
    ("WUH", "武汉", 114.31, 30.60), ("CSX", "长沙", 112.94, 28.23),
    ("CAN", "广州", 113.26, 23.13), ("NNG", "南宁", 108.32, 22.82),
    ("HAK", "海口", 110.20, 20.04), ("CKG", "重庆", 106.55, 29.56),
    ("CTU", "成都", 104.07, 30.57), ("KWE", "贵阳", 106.63, 26.65),
    ("KMG", "昆明", 102.83, 24.88), ("LXA", "拉萨", 91.14, 29.65),
    ("XIY", "西安", 108.94, 34.34), ("LHW", "兰州", 103.83, 36.06),
    ("XNN", "西宁", 101.78, 36.62), ("INC", "银川", 106.23, 38.49),
    ("URC", "乌鲁木齐", 87.62, 43.83),
]


def map_xy(lon: float, lat: float) -> tuple[float, float]:
    """经纬度 -> 底图坐标。线性投影，和底图自带的投影一致。"""
    x = (float(lon) - MAP_LEFT) / (MAP_RIGHT - MAP_LEFT) * MAP_W
    y = (MAP_TOP - float(lat)) / (MAP_TOP - MAP_BOTTOM) * MAP_H
    return round(x, 1), round(y, 1)


def route_map(airports: list[dict], legs: list[dict]) -> str:
    """真实底图 + 省会底点 + 可订城市 + 行程航段。

    三层，从后往前说：

    1. **底点层**：31 座省会级城市的小灰点。它们只是"这里有一座城"的坐标事实，
       不带业务含义，所以不写标签（东部密集区会糊成一团），鼠标悬停用 <title> 报名字。
    2. **可订层**：业务库里有库存的城市，大一圈、写三字码——这是"能订票的地方"。
    3. **行程层**：旅客自己的航段，粗弧线两端实心点，弧顶骑航班号。

    地图是一块**浅色台面**（页面上唯一像印刷品的地方），所以配色走 --map-* 专用变量，
    不跟着页面主题走。
    """
    usable = [a for a in airports if a.get("lon") is not None and a.get("lat") is not None]
    # 已经有库存的城市不再画底点，免得两个点叠在一起
    booked_codes = {a.get("code") for a in usable}

    base = []
    for code, name, lon, lat in CAPITALS:
        if code in booked_codes:
            continue
        x, y = map_xy(lon, lat)
        base.append(
            f'<g class="cap"><title>{name}（{code}）</title>'
            f'<circle cx="{x}" cy="{y}" r="6" fill="var(--map-city)" opacity="0.55"/></g>'
        )

    # 库存城市：大一圈的圆点 + 三字码
    dots = []
    for a in usable:
        x, y = map_xy(a["lon"], a["lat"])
        # 底图在界面上放大显示，所以这些尺寸是「viewBox 单位」，
        # 看着偏大，实际落到屏幕上正好：圆点约 7px、字约 15px。
        dots.append(
            f'<circle cx="{x}" cy="{y}" r="9" fill="var(--map-fill)" '
            f'stroke="var(--map-city)" stroke-width="3"/>'
            f'<text x="{x + 14}" y="{y + 8}" font-family="Azeret Mono, ui-monospace, monospace" '
            f'font-size="26" font-weight="500" fill="var(--map-city)">{a.get("code") or ""}</text>'
        )

    # 旅客航段：先算出两个端点，再画一条向一侧鼓起的弧
    routes = []
    for idx, leg in enumerate(legs):
        origin, dest = leg.get("origin") or {}, leg.get("dest") or {}
        if origin.get("lon") is None or dest.get("lon") is None:
            continue
        ax, ay = map_xy(origin["lon"], origin["lat"])
        bx, by = map_xy(dest["lon"], dest["lat"])
        dx, dy = bx - ax, by - ay
        ln = max((dx * dx + dy * dy) ** 0.5, 1.0)
        # 方向先归一化成「从左往右」，往返两条弧才会往两侧弯、航班号不叠
        ux, uy = (-dx, -dy) if dx < 0 else (dx, dy)
        lift = min(210.0, 70 + ln * 0.42) * (1 if idx % 2 == 0 else -1)
        cx, cy = (ax + bx) / 2 - uy / ln * lift, (ay + by) / 2 + ux / ln * lift
        lx, ly = (ax + bx) / 2 - uy / ln * lift * 0.52, (ay + by) / 2 + ux / ln * lift * 0.52
        routes.append(
            f'<path d="M {ax} {ay} Q {cx:.1f} {cy:.1f} {bx} {by}" fill="none" '
            f'stroke="var(--map-ink)" stroke-width="7" stroke-linecap="round"/>'
            f'<circle cx="{ax}" cy="{ay}" r="16" fill="var(--map-ink)"/>'
            f'<circle cx="{bx}" cy="{by}" r="16" fill="var(--map-ink)"/>'
            f'<text x="{lx:.1f}" y="{ly - 18:.1f}" text-anchor="middle" '
            f'font-family="Azeret Mono, ui-monospace, monospace" font-size="34" font-weight="500" '
            f'fill="var(--map-ink)">{leg.get("flight_no") or ""}</text>'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 {MAP_W:.0f} {MAP_H:.0f}" role="img" '
        f'aria-label="行程地图：省会城市底点、可订城市与旅客航段" preserveAspectRatio="xMidYMid meet" '
        f'class="route-svg">'
        f'<image href="{MAP_PATH}" xlink:href="{MAP_PATH}" x="0" y="0" '
        f'width="{MAP_W:.0f}" height="{MAP_H:.0f}" preserveAspectRatio="none"/>'
        + "".join(base) + "".join(dots) + "".join(routes) +
        "</svg>"
    )
