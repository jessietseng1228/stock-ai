import os
import requests
from typing import Dict, Optional

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"

if not LINE_CHANNEL_ACCESS_TOKEN:
    raise RuntimeError("Missing LINE_CHANNEL_ACCESS_TOKEN")

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
}


def reply_text(reply_token: str, text: str) -> None:
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text[:4900]}],
    }
    requests.post(LINE_REPLY_URL, headers=HEADERS, json=payload, timeout=10)


def push_text(user_id: str, text: str) -> None:
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": text[:4900]}],
    }
    requests.post(LINE_PUSH_URL, headers=HEADERS, json=payload, timeout=10)


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
