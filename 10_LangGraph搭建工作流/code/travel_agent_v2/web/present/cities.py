"""城市显示名。

业务库的 `location` / `city` 列存英文（Beijing / Chengdu），因为模型传中文进来要
先翻译成英文再做 LIKE 匹配（见 infra/scripts/location_trans.py）。但**界面上要显示中文**，
订单标题、行程卡片、库存标签都得有一份英文 → 中文的对照。

放在这里一处，运行时和订单模块共用，避免两边各写一份慢慢跑偏。
"""

# 库里存的英文城市名 -> 中文显示名
CITY_CN = {
    "Beijing": "北京",
    "Shanghai": "上海",
    "Guangzhou": "广州",
    "Shenzhen": "深圳",
    "Chengdu": "成都",
    "Hangzhou": "杭州",
    "Xian": "西安",
    "Kunming": "昆明",
    "Sanya": "三亚",
    "Chongqing": "重庆",
    "Xiamen": "厦门",
    "Wuhan": "武汉",
    "Lhasa": "拉萨",
    "Lijiang": "丽江",
    "Qingdao": "青岛",
    "Harbin": "哈尔滨",
}

# 机场三字码 -> 中文显示名（行程图上按航段画卡片时用）
AIRPORT_CITY_CN = {
    "PEK": "北京",
    "PKX": "北京",
    "SHA": "上海",
    "PVG": "上海",
    "CTU": "成都",
    "TFU": "成都",
    "XIY": "西安",
    "HGH": "杭州",
    "CAN": "广州",
    "SZX": "深圳",
    "KMG": "昆明",
    "SYX": "三亚",
    "CKG": "重庆",
    "XMN": "厦门",
    "WUH": "武汉",
    "LXA": "拉萨",
    "LJG": "丽江",
    "TAO": "青岛",
    "HRB": "哈尔滨",
}


def city_name(value: str, default: str = "") -> str:
    """英文城市名或机场码都认；认不出来就原样返回。"""
    if not value:
        return default
    text = str(value)
    return AIRPORT_CITY_CN.get(text) or CITY_CN.get(text) or text
