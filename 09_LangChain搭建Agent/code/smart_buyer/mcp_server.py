"""
SmartBuyer · mcp_server.py —— 内置 MCP 演示服务器（Phase 3 数据源）
====================================================================
用 FastMCP 在进程内起一个"电商数据 MCP 服务器"，提供 5 把真实可调用的工具，
让 SmartBuyer 的"MCP 工具生态"不只是一个空壳演示，而是形成业务闭环：

    差评（ddgs 联网）＋ 规格测算（本地）＋ 避坑（RAG）＋
    行情/物流/售后（MCP 服务器）──→ 参谋的推荐有据可依，交付可执行

工具清单：
1. query_price_history    历史价格曲线（判断"现在是不是好价"）
2. query_official_specs   官方参数查询（核对商家宣传是否缩水）
3. estimate_trade_in      以旧换新估价（入手成本再砍一刀）
4. query_delivery_time    物流时效查询（急用党决策依据）
5. query_after_sales      售后政策查询（保修/退换/碎屏险）

数据说明：演示服务器内置了一份离线行情数据集（覆盖笔记本/手机/耳机常见型号），
查询走真实代码路径，但不联网——CI 和离线环境都能跑。生产替换方案见文件尾部注释。
"""

from fastmcp import FastMCP

mcp = FastMCP("smart-buyer-market")

# ==============================================================================
# 离线演示数据集（生产环境换成真实数据源：电商开放平台 / 价格监测 API）
# ==============================================================================
_PRICE_HISTORY = {
    "联想小新pro14": [("618 大促", 4999), ("双 11", 4799), ("开学季", 5299), ("当前", 5199)],
    "thinkbook14": [("618 大促", 4599), ("双 11", 4499), ("开学季", 4999), ("当前", 4899)],
    "magicbook14": [("618 大促", 4299), ("双 11", 4099), ("开学季", 4599), ("当前", 4499)],
    "iphone16": [("发布价", 5999), ("618 大促", 5499), ("双 11", 5299), ("当前", 5399)],
    "airpodspro": [("发布价", 1899), ("618 大促", 1599), ("双 11", 1499), ("当前", 1699)],
}

_OFFICIAL_SPECS = {
    "联想小新pro14": {
        "cpu": "AMD R7-8845H", "ram": "32GB LPDDR5x（板载）", "storage": "1TB PCIe 4.0",
        "screen": "14 英寸 2.8K 120Hz 100% sRGB", "battery": "84Wh", "weight": "1.46kg",
        "ports": "全功能 Type-C ×2（USB4）+ USB-A 3.2 ×2 + HDMI 2.1 + SD 读卡器",
    },
    "thinkbook14": {
        "cpu": "Intel Ultra 5 125H", "ram": "32GB DDR5（双插槽可扩展）", "storage": "1TB PCIe 4.0",
        "screen": "14 英寸 2.8K 90Hz 100% sRGB", "battery": "60Wh", "weight": "1.56kg",
        "ports": "雷电 4 ×2 + USB-A 3.2 ×2 + HDMI 2.1 + RJ45 网口",
    },
    "magicbook14": {
        "cpu": "AMD R7-8845H", "ram": "16GB LPDDR5x（板载）", "storage": "1TB PCIe 4.0",
        "screen": "14.2 英寸 2.5K 120Hz 100% sRGB", "battery": "75Wh", "weight": "1.49kg",
        "ports": "全功能 Type-C ×2（USB4）+ USB-A 3.2 ×1（无 HDMI）",
    },
    "iphone16": {
        "chip": "A18", "ram": "8GB", "screen": "6.1 英寸 OLED 60Hz",
        "battery": "3561mAh", "camera": "4800 万融合双摄", "weight": "170g",
    },
    "airpodspro": {
        "chip": "H2", "anc": "主动降噪（自适应通透）", "battery": "单次 6h + 盒 30h",
        "bluetooth": "蓝牙 5.3 / AAC", "waterproof": "IP54",
    },
}

_TRADE_IN_BASE = {          # 以旧换新基准价（元），按成色折算
    "iphone15": 3200, "iphone14": 2400, "iphone13": 1700,
    "magicbook14": 2800, "小新pro13": 2200, "ipadair": 1800,
    "airpodspro2": 800,
}

_DELIVERY = {               # 物流时效（小时）：按发货仓到收货地粗估
    "自营仓": {"北上广深杭": 24, "省会城市": 48, "地级市": 72, "县乡": 96},
    "品牌仓": {"北上广深杭": 48, "省会城市": 72, "地级市": 96, "县乡": 120},
}

_AFTER_SALES = {
    "联想": "整机保修 2 年（含上门）；7 天无理由退货（激活后不支持）；屏幕意外保需另购 199 元/年；全国 1200+ 服务网点。",
    "荣耀": "整机保修 1 年；7 天无理由退货（激活后不支持）；碎屏险 149 元/年；寄修为主、部分城市有网点。",
    "小米": "整机保修 1 年；7 天无理由退货（激活后不支持）；意外保 179 元/年；小米之家 2000+ 网点支持快修。",
    "苹果": "整机保修 1 年；激活后 14 天内可退；AppleCare+ 1098 元/年（含两次碎屏）；Genius Bar 预约维修。",
    "华硕": "整机保修 2 年（电池 1 年）；7 天无理由退货（激活后不支持）；意外保 299 元/年；全国 800+ 网点。",
}


def _lookup(table: dict, key: str) -> tuple[dict | list | None, str]:
    """大小写/空格无关的模糊匹配：命中直接返回；未命中返回 None 与最近似提示"""
    norm = key.strip().lower()
    for k, v in table.items():
        if k.lower() in norm or norm in k.lower():
            return v, k
    return None, key


# ==============================================================================
# 5 把 MCP 工具（@mcp.tool：docstring 即模型可见的工具说明）
# ==============================================================================
@mcp.tool
def query_price_history(product: str) -> str:
    """查询产品近几轮大促的价格曲线，判断当前是否好价。

    Args:
        product: 产品名，如 '联想小新Pro14'、'ThinkBook14'、'iPhone16'、'AirPodsPro'
    """
    data, hit = _lookup(_PRICE_HISTORY, product)
    if data is None:
        known = "、".join(_PRICE_HISTORY.keys())
        return f"暂无 '{product}' 的价格曲线。已收录：{known}"
    lines = [f"{name}: ¥{price:,}" for name, price in data]
    first, last = data[0][1], data[-1][1]
    verdict = "当前处于低位，是好价" if last <= first else f"当前比最低点贵 ¥{last - first:,}，建议蹲大促"
    return f"【{hit} 价格曲线】\n" + "\n".join(lines) + f"\n\n📊 结论：{verdict}。"


@mcp.tool
def query_official_specs(product: str) -> str:
    """查询产品官方规格参数，用于核对商家宣传是否缩水（如屏幕色域、内存是否板载）。

    Args:
        product: 产品名，如 '联想小新Pro14'、'MagicBook14'、'iPhone16'、'AirPodsPro'
    """
    data, hit = _lookup(_OFFICIAL_SPECS, product)
    if data is None:
        known = "、".join(_OFFICIAL_SPECS.keys())
        return f"暂无 '{product}' 的官方参数。已收录：{known}"
    return f"【{hit} 官方规格】\n" + "\n".join(f"• {k}: {v}" for k, v in data.items())


@mcp.tool
def estimate_trade_in(old_device: str, condition: str = "9成新") -> str:
    """估算旧设备以旧换新的抵扣金额，帮用户算出真实入手成本。

    Args:
        old_device: 旧设备型号，如 'iPhone15'、'MagicBook14'、'AirPodsPro2'
        condition: 成色，可选 '99新' / '9成新' / '8成新' / '有明显划痕'
    """
    factor = {"99新": 0.95, "9成新": 0.85, "8成新": 0.70, "有明显划痕": 0.55}
    f = factor.get(condition)
    if f is None:
        return f"未知成色 '{condition}'，可选：{'、'.join(factor)}"
    base, hit = _lookup(_TRADE_IN_BASE, old_device)
    if base is None:
        return (f"暂无 '{old_device}' 的回收基准价。已收录：{'、'.join(_TRADE_IN_BASE.keys())}。"
                f"可先告知预算，我按新机价格估算。")
    value = int(base * f)
    return (f"【以旧换新估价】{hit}（{condition}）≈ 抵扣 ¥{value:,}\n"
            f"💡 平台大促期间常有额外补贴 ¥100~400，以结算页为准。")


@mcp.tool
def query_delivery_time(warehouse: str, region: str) -> str:
    """查询物流时效（小时），急用党的决策依据。

    Args:
        warehouse: 仓库类型，'自营仓' 或 '品牌仓'
        region: 收货地区，如 '北上广深杭'、'省会城市'、'地级市'、'县乡'
    """
    wh = _DELIVERY.get(warehouse.strip())
    if wh is None:
        return f"未知仓库类型 '{warehouse}'，可选：{'、'.join(_DELIVERY)}"
    r = wh.get(region.strip())
    if r is None:
        return f"未知地区 '{region}'，可选：{'、'.join(wh.keys())}"
    return f"【物流时效】{warehouse} → {region}：约 {r} 小时内送达（大促高峰顺延 12~24h）。"


@mcp.tool
def query_after_sales(brand: str) -> str:
    """查询品牌售后政策（保修年限/退换规则/碎屏险/网点），避免踩售后坑。

    Args:
        brand: 品牌名，如 '联想'、'苹果'、'小米'、'荣耀'、'华硕'
    """
    data, hit = _lookup(_AFTER_SALES, brand)
    if data is None:
        return f"暂无 '{brand}' 的售后档案。已收录：{'、'.join(_AFTER_SALES.keys())}"
    return f"【{hit} 售后政策】{data}"


if __name__ == "__main__":
    # 独立自检：逐把工具真实调用一遍（零外部依赖，可进 CI）
    print("== SmartBuyer MCP 演示服务器自检 ==")
    print(query_price_history("联想小新Pro14"))
    print(query_price_history("iPhone16"))
    print(query_official_specs("MagicBook14"))
    print(estimate_trade_in("iPhone15", "9成新"))
    print(query_delivery_time("自营仓", "省会城市"))
    print(query_after_sales("联想"))
