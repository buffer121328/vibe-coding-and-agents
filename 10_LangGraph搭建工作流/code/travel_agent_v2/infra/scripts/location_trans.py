"""中文城市名 → 库里存的英文城市名。

业务库的 `location` 列统一存英文（Beijing / Chengdu / Sanya …），
因为模型经常直接用中文说「帮我在成都订辆车」。这里做一层翻译，
让中文输入也能命中 LIKE 查询。

输入不是中文时原样返回；是中文但不在表里，返回一句明确的提示，
让模型知道该改写城市名，而不是静默查空。
"""
CITY_DICT = {
    # 直辖市
    "北京": "Beijing",
    "上海": "Shanghai",
    "重庆": "Chongqing",
    "天津": "Tianjin",
    # 省会与热门目的地
    "广州": "Guangzhou",
    "深圳": "Shenzhen",
    "成都": "Chengdu",
    "杭州": "Hangzhou",
    "西安": "Xian",
    "南京": "Nanjing",
    "武汉": "Wuhan",
    "长沙": "Changsha",
    "郑州": "Zhengzhou",
    "昆明": "Kunming",
    "贵阳": "Guiyang",
    "南宁": "Nanning",
    "福州": "Fuzhou",
    "厦门": "Xiamen",
    "青岛": "Qingdao",
    "济南": "Jinan",
    "大连": "Dalian",
    "沈阳": "Shenyang",
    "哈尔滨": "Harbin",
    "长春": "Changchun",
    "兰州": "Lanzhou",
    "西宁": "Xining",
    "银川": "Yinchuan",
    "太原": "Taiyuan",
    "石家庄": "Shijiazhuang",
    "合肥": "Hefei",
    "南昌": "Nanchang",
    "海口": "Haikou",
    "三亚": "Sanya",
    "桂林": "Guilin",
    "丽江": "Lijiang",
    "大理": "Dali",
    "拉萨": "Lhasa",
    "乌鲁木齐": "Urumqi",
    "呼和浩特": "Hohhot",
    "香港": "Hong Kong",
    "澳门": "Macau",
    "台北": "Taipei",
    # 同义词
    "蓉城": "Chengdu",
    "羊城": "Guangzhou",
    "春城": "Kunming",
}

# 用来兜底：模型可能直接给出英文城市名，这里也认一遍（大小写不敏感）
EN_CITIES = {value.lower(): value for value in CITY_DICT.values()}


def transform_location(chinese_city):
    """把中文城市名翻成库里存的英文名；参数可能为空（模型不一定会传）。"""
    if not chinese_city:
        return None

    text = str(chinese_city).strip()
    if not text:
        return None

    # 纯中文：查表；查不到给出可读提示，方便模型自我纠正
    if all("\u4e00" <= char <= "\u9fff" for char in text):
        return CITY_DICT.get(text, f"{text}（暂未开通，请换一个城市或直接给英文名）")

    # 已经是英文：如果大小写和库里不一致，统一成库里的写法
    return EN_CITIES.get(text.lower(), text)
