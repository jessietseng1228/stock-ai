import os
import requests
from typing import Dict, Optional, List

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"

if not LINE_CHANNEL_ACCESS_TOKEN:
    raise RuntimeError("Missing LINE_CHANNEL_ACCESS_TOKEN")

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
}


def _safe_post(url: str, payload: Dict) -> bool:
    try:
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=10)
        return 200 <= resp.status_code < 300
    except Exception:
        return False


def reply_text(reply_token: str, text: str) -> None:
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": (text or "")[:4900]}],
    }
    _safe_post(LINE_REPLY_URL, payload)


def push_text(user_id: str, text: str) -> bool:
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": (text or "")[:4900]}],
    }
    return _safe_post(LINE_PUSH_URL, payload)


def reply_flex(reply_token: str, alt_text: str, flex_contents: Dict, fallback_text: str = "") -> None:
    payload = {
        "replyToken": reply_token,
        "messages": [{
            "type": "flex",
            "altText": (alt_text or "股票 AI 助理")[:400],
            "contents": flex_contents,
        }],
    }
    ok = _safe_post(LINE_REPLY_URL, payload)
    if not ok and fallback_text:
        reply_text(reply_token, fallback_text)


def push_flex(user_id: str, alt_text: str, flex_contents: Dict, fallback_text: str = "") -> bool:
    payload = {
        "to": user_id,
        "messages": [{
            "type": "flex",
            "altText": (alt_text or "股票 AI 助理")[:400],
            "contents": flex_contents,
        }],
    }
    ok = _safe_post(LINE_PUSH_URL, payload)
    if ok:
        return True
    if fallback_text:
        return push_text(user_id, fallback_text)
    return False


def get_event_text(event: Dict) -> str:
    """支援 Rich Menu 用 message text 或 postback data。"""
    if event.get("type") == "message":
        msg = event.get("message", {})
        if msg.get("type") == "text":
            return (msg.get("text") or "").strip()

    if event.get("type") == "postback":
        return (event.get("postback", {}).get("data") or "").strip()

    return ""


def get_user_id(event: Dict) -> Optional[str]:
    return event.get("source", {}).get("userId")
