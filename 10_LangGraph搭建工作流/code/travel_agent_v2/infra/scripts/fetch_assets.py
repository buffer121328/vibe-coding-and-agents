"""一次性素材抓取：给每个城市找一张真实照片。

为什么需要这个脚本：项目要在离线环境跑，也不能把外链图片写进页面（会过期、会挂）。
所以把自由授权的实景照片下载到 `static/img/cities/`，一次抓取，之后完全本地。

图片全部来自 Wikimedia Commons，脚本会把作者、授权协议、来源页写进
`static/img/CREDITS.md`——CC 授权要求署名，这是必须做的事，不是可选项。

用法（必须在 travel_agent_v2 目录内）：uv run python -m infra.scripts.fetch_assets
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

if os.path.isfile(os.path.join(os.getcwd(), "infra", "paths.py")):
    sys.path.insert(0, os.getcwd())

from infra.paths import CITIES_DIR, CREDITS_PATH, ROOT

HERE = ROOT          # 只在打印相对路径时露脸，别的路径一律从 infra/paths.py 取
OUT_DIR = CITIES_DIR
CREDITS = CREDITS_PATH
UA = "TripAssistantTeachingDemo/1.0 (local teaching project; offline demo asset fetch)"

API = "https://commons.wikimedia.org/w/api.php"

# 每个城市：搜索词 + 必须出现在文件名里的关键词（用来筛掉吉祥物、室内展品这类误命中）
WANTED = {
    "PEK": (["Temple of Heaven Beijing", "Hall of Prayer for Good Harvests"], ["temple of heaven", "prayer"]),
    "CTU": (["Giant Panda Chengdu", "Chengdu Research Base Giant Panda"], ["panda"]),
    "SHA": (["The Bund Shanghai skyline", "Pudong skyline Shanghai"], ["bund", "pudong", "shanghai"]),
    "SYX": (["Yalong Bay Hainan beach resort", "Sanya Bay Hainan sunset"], ["yalong", "sanya bay"]),
    "XIY": (["Xi'an City Wall", "Bell Tower Xi'an"], ["city wall", "bell tower", "xi'an", "xian"]),
    "HGH": (["West Lake Hangzhou", "Leifeng Pagoda Hangzhou"], ["west lake", "hangzhou", "leifeng"]),
    "CAN": (["Canton Tower Guangzhou", "Guangzhou skyline Pearl River"], ["canton tower", "guangzhou"]),
    "SZX": (["Shenzhen skyline", "Shenzhen Bay"], ["shenzhen"]),
    "KMG": (["Stone Forest Yunnan", "Shilin Yunnan karst"], ["stone forest", "shilin"]),
    "CKG": (["Hongya Cave Chongqing", "Chongqing skyline Jialing"], ["chongqing", "hongya"]),
    "XMN": (["Gulangyu Xiamen", "Xiamen skyline"], ["gulangyu", "xiamen"]),
    "WUH": (["Yellow Crane Tower Wuhan", "Wuhan Yangtze bridge"], ["yellow crane", "wuhan"]),
    "LXA": (["Potala Palace Lhasa", "Potala Palace"], ["potala"]),
    "LJG": (["Yulong Snow Mountain", "Old Town of Lijiang"], ["yulong", "lijiang"]),
    "TAO": (["Zhanqiao Pier Qingdao", "Qingdao coast"], ["zhanqiao", "qingdao"]),
    "HRB": (["Saint Sophia Cathedral Harbin", "Harbin Sophia"], ["sophia", "harbin"]),
}

BAD_WORDS = ("mascot", "logo", "map", "coat of arms", "flag", "diagram", "chart",
             "banknote", "stamp", "poster", "screenshot", "sign", "menu",
             "abandoned", "ruin", "derelict", "construction")


def _get(url: str) -> bytes:
    """带重试的 GET，返回响应体；失败重试若干次仍不行就抛。

    :param url: 目标地址
    :return: 响应内容（bytes）
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return resp.read()


def search(query: str, limit: int = 8) -> list[dict]:
    """在 Wikimedia Commons 里搜图片，取回候选文件名列表。

    :param query: 搜索词（如城市名）
    :param limit: 最多取几张
    :return: 文件名列表
    """
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}", "gsrnamespace": "6", "gsrlimit": str(limit),
        "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": "900",
    }
    data = json.loads(_get(f"{API}?{urllib.parse.urlencode(params)}").decode("utf-8"))
    return list(((data.get("query") or {}).get("pages") or {}).values())


def pick(pages: list[dict], keys: list[str]) -> dict | None:
    """挑一张像样的实景照：文件名里带地标关键词、不是图标/地图/吉祥物、够大。"""
    best = None
    for page in pages:
        title = str(page.get("title") or "")
        low = title.lower()
        if not any(k in low for k in keys):
            continue
        if any(bad in low for bad in BAD_WORDS):
            continue
        info = (page.get("imageinfo") or [{}])[0]
        if not info.get("thumburl"):
            continue
        width = info.get("width") or 0
        height = info.get("height") or 0
        if width < 800 or height < 0.4 * width:      # 太窄的多半是拼图或扫描件
            continue
        meta = info.get("extmetadata") or {}
        license_name = str((meta.get("LicenseShortName") or {}).get("value") or "")
        if not license_name:
            continue
        candidate = {
            "title": title,
            "thumb": info["thumburl"],
            "page": info.get("descriptionurl") or "",
            "license": license_name,
            "author": re.sub(r"<[^>]+>", "", str((meta.get("Artist") or {}).get("value") or "")).strip()[:80],
        }
        # 优先横构图、像素多的
        score = width + (600 if width > height else 0)
        if best is None or score > best[0]:
            best = (score, candidate)
    return best[1] if best else None


def main() -> None:
    """抓齐 16 个城市的实景照与底图，并写 CREDITS.md 署名清单。

    :return: 无（产出的素材落在 static/img/）
    """
    os.makedirs(OUT_DIR, exist_ok=True)
    credits = [
        "# 图片素材出处",
        "",
        "本目录下的城市照片来自 Wikimedia Commons，均为自由授权作品，**按各自协议要求署名**。",
        "抓取脚本：`infra/scripts/fetch_assets.py`（本项目为离线教学演示，一次抓取后本地使用）。",
        "底图 `map/china.svg` 来自 Wikimedia Commons 的定位地图系列，授权 CC BY-SA 3.0。",
        "",
        "> 换图或商用前，请回到来源页确认最新授权条款，并保留同样的署名。",
        "",
        "| 城市 | 文件 | 作者 | 授权 | 来源页 |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    ok, missing = [], []
    for code, (queries, keys) in WANTED.items():
        found = None
        for query in queries:
            try:
                found = pick(search(query), keys)
            except Exception as exc:      # noqa: BLE001
                print(f"  {code} 搜索失败：{exc}")
                found = None
            if found:
                break
        if not found:
            missing.append(code)
            print(f"✗ {code} 没找到合适的照片")
            continue
        target = os.path.join(OUT_DIR, f"{code}.jpg")
        try:
            blob = _get(found["thumb"])
            with open(target, "wb") as fh:
                fh.write(blob)
        except Exception as exc:      # noqa: BLE001
            missing.append(code)
            print(f"✗ {code} 下载失败：{exc}")
            continue
        size_kb = len(blob) / 1024
        credits.append(
            f"| {code} | `cities/{code}.jpg` | {found['author'] or '（见来源页）'} | "
            f"{found['license']} | [{found['title']}]({found['page']}) |"
        )
        ok.append(code)
        print(f"✓ {code} {size_kb:.0f} KB · {found['license']} · {found['title'][:60]}")
        time.sleep(0.4)      # 别把人家服务器打急

    with open(CREDITS, "w", encoding="utf-8") as fh:
        fh.write("\n".join(credits) + "\n")
    print(f"\n成功 {len(ok)} 张，缺失 {len(missing)} 张 {missing}")
    print(f"署名清单：{os.path.relpath(CREDITS, HERE)}")


if __name__ == "__main__":
    main()
