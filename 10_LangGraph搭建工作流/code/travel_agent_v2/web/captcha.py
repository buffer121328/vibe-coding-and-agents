"""图形验证码：服务端出题，前端展示，提交时回兑。

为什么自己做而不用第三方：这是本地教学项目，拉一个验证码 SaaS 反而看不清原理。
为什么是 SVG 而不是位图：机器上没装 Pillow，而且 SVG 在任何 DPI 下都清晰、
体积也就一两 KB，不需要额外的图像库。

防的是「机器批量刷」而不是「人眼识别」，所以只做三件事：
- 字符随机旋转、抖动，让直线切图不好切；
- 叠几条干扰线和一个噪点波纹；
- 一次性 + 有过期时间 + 服务端保存答案（前端拿不到答案）。

注意：这不是强防护。真要挡自动化，得靠行为风控 + 频率限制 + 号码/邮箱信誉，
验证码只是把最低成本的脚本挡在门外。
"""
from __future__ import annotations

import random
import secrets
import threading
import time

# 去掉容易看错的 0/O、1/I/L、2/Z、5/S
CHARS = "ABCDEFGHJKMNPQRSTUVWXY346789"
LENGTH = 4
TTL = 300              # 5 分钟
MAX_BOX = 2000         # 同时保存的题目上限，防止内存被刷爆

W, H = 148, 46
FONT = "IBM Plex Mono, ui-monospace, monospace"

_BOX: dict[str, tuple[str, float]] = {}
_LOCK = threading.Lock()


def _sweep() -> None:
    """清掉过期或超量的题目（防内存被刷爆）。

    :return: 无
    """
    now = time.time()
    for key in [k for k, (_, exp) in _BOX.items() if exp < now]:
        _BOX.pop(key, None)


def _noise() -> str:
    """干扰线：三条随机折线，颜色贴近票面，不遮字。"""
    parts = []
    for _ in range(3):
        y0 = random.randint(6, H - 6)
        d = [f"M 0 {y0}"]
        x = 0
        while x < W:
            x += random.randint(18, 42)
            d.append(f"Q {x - 12} {random.randint(2, H - 2)} {x} {random.randint(6, H - 6)}")
        parts.append(
            f'<path d="{" ".join(d)}" fill="none" stroke="#8c7f63" '
            f'stroke-width="{random.choice((0.6, 0.8))}" opacity="0.55"/>'
        )
    return "".join(parts)


def _wave() -> str:
    """一条波浪，模拟印刷时的套印偏移。"""
    y = random.randint(12, H - 12)
    return (
        f'<path d="M 0 {y} C {W * 0.3:.0f} {y - 9}, {W * 0.6:.0f} {y + 9}, {W} {y - 4}" '
        f'fill="none" stroke="#a8341f" stroke-width="0.7" opacity="0.28"/>'
    )


def _glyphs(code: str) -> str:
    """每个字符单独摆位：随机旋转、上下抖动、深浅不一。"""
    step = (W - 16) / LENGTH
    out = []
    for i, ch in enumerate(code):
        x = 10 + step * i + random.uniform(-2.5, 2.5)
        y = H / 2 + random.uniform(-4, 4)
        rot = random.uniform(-26, 26)
        size = random.uniform(23, 28)
        ink = random.choice(("#191713", "#1d3f63", "#3a3226"))
        out.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size:.1f}" '
            f'font-weight="600" fill="{ink}" '
            f'transform="rotate({rot:.1f} {x:.1f} {y:.1f})" '
            f'dominant-baseline="middle">{ch}</text>'
        )
    return "".join(out)


def new_challenge() -> tuple[str, str]:
    """出一道题，返回 (captcha_id, svg)。答案只留在服务端。"""
    code = "".join(random.choice(CHARS) for _ in range(LENGTH))
    captcha_id = secrets.token_urlsafe(12)
    with _LOCK:
        _sweep()
        if len(_BOX) > MAX_BOX:
            # 超量就清最早的一半，别让内存无上限涨
            for key in sorted(_BOX, key=lambda k: _BOX[k][1])[: len(_BOX) // 2]:
                _BOX.pop(key, None)
        _BOX[captcha_id] = (code, time.time() + TTL)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'role="img" aria-label="图形验证码">'
        f'<rect width="{W}" height="{H}" fill="#f4efe3"/>'
        f"{_noise()}{_wave()}{_glyphs(code)}"
        f"</svg>"
    )
    return captcha_id, svg


def check(captcha_id: str, answer: str) -> bool:
    """兑答案。无论对错都作废——一题只能用一次，避免被暴力试。"""
    if not captcha_id or not answer:
        return False
    with _LOCK:
        _sweep()
        item = _BOX.pop(captcha_id, None)
    if not item:
        return False
    code, exp = item
    if exp < time.time():
        return False
    return answer.strip().upper() == code


def peek(captcha_id: str) -> str | None:
    """只给测试用：看某道题的答案，不要在生产路径里调用。"""
    with _LOCK:
        item = _BOX.get(captcha_id)
    return item[0] if item else None
