"""消息推送：飞书 / 钉钉（支持加签）/ 企业微信 webhook。

任一渠道未配置则跳过；失败只记警告，绝不影响数据落盘主流程。
"""

import base64
import hashlib
import hmac
import os
import time
import urllib.parse

import requests

TIMEOUT = 15


def _ding_sign(url: str) -> str:
    """钉钉「加签」安全模式：追加 timestamp 与 HMAC-SHA256 签名参数。"""
    secret = os.environ.get("DINGTALK_SECRET", "")
    if not secret:
        return url
    ts = str(round(time.time() * 1000))
    digest = base64.b64encode(
        hmac.new(secret.encode(), f"{ts}\n{secret}".encode(), hashlib.sha256).digest()
    )
    return f"{url}&timestamp={ts}&sign={urllib.parse.quote_plus(digest)}"


def _post(channel: str, url: str, payload: dict) -> dict:
    try:
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
        code = 0
        if resp.headers.get("content-type", "").startswith("application/json"):
            body = resp.json()
            # 飞书新接口返回 {"code":0}，钉钉/企微返回 {"errcode":0}
            code = body.get("errcode", body.get("code", 0))
        ok = resp.ok and code == 0
        return {"channel": channel, "ok": bool(ok), "detail": resp.text[:200]}
    except Exception as e:
        return {"channel": channel, "ok": False, "detail": f"{type(e).__name__}: {e}"[:200]}


def send_all(text: str, title: str = "GitHub 热门监控", channels: dict | None = None) -> list[dict]:
    """把推送文本发到所有已配置且启用的渠道。

    channels: config.json 的 notify 开关 {feishu/dingtalk/wecom: bool}，None 视为全开。
    """
    switches = channels or {}
    results = []

    feishu = os.environ.get("FEISHU_WEBHOOK")
    if feishu and switches.get("feishu", True):
        results.append(_post("飞书", feishu, {"msg_type": "text", "content": {"text": text}}))

    dingtalk = os.environ.get("DINGTALK_WEBHOOK")
    if dingtalk and switches.get("dingtalk", True):
        results.append(_post("钉钉", _ding_sign(dingtalk), {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": text.replace("\n", "\n\n")},
        }))

    wecom = os.environ.get("WECOM_WEBHOOK")
    if wecom and switches.get("wecom", True):
        # 企业微信 markdown 上限 4096 字节，截断保护
        truncated = text.encode("utf-8")[:3800].decode("utf-8", "ignore")
        results.append(_post("企业微信", wecom, {
            "msgtype": "markdown",
            "markdown": {"content": truncated},
        }))

    return results
