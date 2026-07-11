"""每日早報共用工作。

Web 路由 /cron 與 Render Cron Job 都呼叫這裡，避免排程依賴
免費 Web Service 的冷啟動與 HTTP 回應限制。
"""
from typing import Dict, List

from line import push_flex
from report import build_morning_flex
from supabase_db import get_all_user_ids, get_user_stocks


def run_morning_report() -> Dict:
    """產生並推播所有使用者的自選股早報。

    回傳精簡結果，方便 Flask JSON 與 Render Cron log 使用。
    若個別使用者失敗，會繼續處理其他使用者，並記錄失敗 user_id。
    """
    user_ids = get_all_user_ids()
    sent = 0
    skipped = 0
    failed_user_ids: List[str] = []

    for user_id in user_ids:
        try:
            stocks = get_user_stocks(user_id)
            if not stocks:
                skipped += 1
                continue

            alt, flex, fallback = build_morning_flex(stocks)
            ok = push_flex(user_id, alt, flex, fallback)
            if ok:
                sent += 1
            else:
                failed_user_ids.append(user_id)
        except Exception as exc:
            print(f"[MORNING_REPORT][USER_FAILED] user_id={user_id} error={type(exc).__name__}: {exc}")
            failed_user_ids.append(user_id)

    return {
        "status": "ok" if not failed_user_ids else "partial_failed",
        "job": "morning_push",
        "users": len(user_ids),
        "sent": sent,
        "skipped": skipped,
        "failed": len(failed_user_ids),
        "failed_user_ids": failed_user_ids,
    }
