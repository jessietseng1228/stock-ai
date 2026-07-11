"""Render Cron Job 執行入口。

Render Command:
    python cron_runner.py

Render Schedule（UTC；台灣 09:00）:
    0 1 * * *
"""
import json
import sys
from datetime import datetime, timezone

from morning_job import run_morning_report


def main() -> int:
    started_at = datetime.now(timezone.utc).isoformat()
    print(f"[CRON][START] morning_report utc={started_at}", flush=True)

    try:
        result = run_morning_report()
        print("[CRON][RESULT] " + json.dumps(result, ensure_ascii=False), flush=True)

        if result.get("failed", 0) > 0:
            print("[CRON][FAILED] one or more LINE pushes failed", flush=True)
            return 1

        print("[CRON][SUCCESS] morning_report completed", flush=True)
        return 0
    except Exception as exc:
        print(f"[CRON][FATAL] {type(exc).__name__}: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
