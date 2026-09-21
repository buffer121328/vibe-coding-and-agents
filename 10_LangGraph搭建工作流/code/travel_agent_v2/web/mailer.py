"""发信：有 SMTP 配置就真发，没有就打到日志（本地教学用）。

本地起服务时通常没有邮件服务器，但注册流程又必须能看到验证码。
所以这里做两档：
- 配了 `SMTP_HOST`：走真实 SMTP（465 用 SSL，587 用 STARTTLS）把信发出去；
- 没配：不静默失败，而是把验证码写进日志，并告诉调用方「这是本地兜底」，
  由上层决定要不要在界面上提示（见 web/api.py 的 dev_mode 标记）。

生产必须配 SMTP 并关掉本地兜底，否则验证码会出现在服务端日志里。
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

from infra.logging import log

PURPOSE_LABEL = {
    "register": "注册",
    "login": "登录",
    "reset": "重置密码",
}


def smtp_configured() -> bool:
    """配没配 SMTP（没配就走本地兜底：验证码写日志）。

    :return: bool
    """
    return bool((os.getenv("SMTP_HOST") or "").strip())


def _dev_mode() -> bool:
    """显式打开本地兜底（TRIP_DESK_DEV_MAIL=1），或者在没配 SMTP 时默认打开。"""
    flag = (os.getenv("TRIP_DESK_DEV_MAIL") or "").strip()
    if flag in {"0", "false", "no"}:
        return False
    if flag in {"1", "true", "yes"}:
        return True
    return not smtp_configured()


def compose(to_email: str, code: str, purpose: str = "register") -> EmailMessage:
    """拼一封验证码邮件（主题 + 纯文本正文）。

    :param to_email: 收件人
    :param code: 6 位验证码
    :param purpose: 用途（注册 / 登录 / 重置）
    :return: (subject, body) 二元组
    """
    label = PURPOSE_LABEL.get(purpose, "验证")
    msg = EmailMessage()
    msg["Subject"] = f"【旅行管家】{label}验证码 {code}"
    msg["From"] = os.getenv("SMTP_FROM") or os.getenv("SMTP_USER") or "no-reply@trip.local"
    msg["To"] = to_email
    msg.set_content(
        f"你的{label}验证码是 {code}，10 分钟内有效。\n"
        f"如果不是你本人操作，忽略这封邮件即可。\n"
    )
    return msg


def send_code(to_email: str, code: str, purpose: str = "register") -> dict:
    """发一封验证码邮件。返回投递结果，供上层决定要不要在界面上兜底显示。"""
    label = PURPOSE_LABEL.get(purpose, "验证")
    if not smtp_configured():
        log.warning(f"[本地邮件兜底] 发给 {to_email} 的{label}验证码：{code}（未配置 SMTP_HOST）")
        return {"delivered": "console", "dev_mode": True, "code": code}

    host = os.environ["SMTP_HOST"].strip()
    port = int(os.getenv("SMTP_PORT") or 465)
    user = (os.getenv("SMTP_USER") or "").strip()
    password = os.getenv("SMTP_PASSWORD") or ""
    try:
        if port == 587:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.starttls(context=ssl.create_default_context())
                if user:
                    server.login(user, password)
                server.send_message(compose(to_email, code, purpose))
        else:
            with smtplib.SMTP_SSL(host, port, timeout=15, context=ssl.create_default_context()) as server:
                if user:
                    server.login(user, password)
                server.send_message(compose(to_email, code, purpose))
    except Exception as exc:      # noqa: BLE001 —— 发信失败不该把注册整条打挂
        log.exception(exc)
        if _dev_mode():
            log.warning(f"[本地邮件兜底] SMTP 发送失败，验证码：{code}")
            return {"delivered": "console", "dev_mode": True, "code": code, "error": str(exc)}
        return {"delivered": "failed", "dev_mode": False, "error": str(exc)}

    log.info(f"验证码邮件已发送：{to_email}（{label}）")
    return {"delivered": "smtp", "dev_mode": False}
