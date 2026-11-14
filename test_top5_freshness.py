import importlib
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class Top5Table:
    def __init__(self, rows):
        self.rows = list(rows)

    def select(self, columns):
        return self

    def eq(self, column, value):
        self.rows = [row for row in self.rows if row[column] == value]
        return self

    def neq(self, column, value):
        self.rows = [row for row in self.rows if row[column] != value]
        return self

    def order(self, column, desc=False):
        self.rows.sort(key=lambda row: row[column], reverse=desc)
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


class Top5FreshnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict("os.environ", {
            "SUPABASE_URL": "https://example.invalid",
            "SUPABASE_KEY": "local-test-placeholder",
            "LINE_CHANNEL_ACCESS_TOKEN": "local-test-placeholder",
        }), patch("supabase.create_client"):
            cls.app_module = importlib.import_module("app")
        cls.app_module.app.testing = True

    def setUp(self):
        self.date = "2026-11-11"
        self.rows = []
        self.client = self.app_module.app.test_client()
        self.enterContext(patch("report.today_taipei", side_effect=lambda: self.date))
        self.enterContext(patch("market_scan.today_taipei", side_effect=lambda: self.date))
        self.enterContext(patch("supabase_db.supabase.table", side_effect=lambda _: Top5Table(self.rows)))
        self.enterContext(patch("app.clear_user_state"))
        self.reply = self.enterContext(patch("app.reply_flex"))
        self.scan = self.enterContext(patch("app.scan_market_top5"))

    def add_row(self, symbol, date=None, rank=1):
        from supabase_db import _encode_v20_plan

        self.rows.append({
            "scan_date": date or self.date,
            "symbol": symbol,
            "rank": rank,
            "trend": _encode_v20_plan({"trade_plan": {"decision": "🟢 可分批布局"}}),
        })

    def assert_today(self, text, has_result, count):
        page = self.client.get("/top5").get_data(as_text=True)
        event = {
            "type": "message",
            "replyToken": "local-test",
            "source": {"userId": "local-user"},
            "message": {"type": "text", "text": "今日 Top5"},
        }
        self.assertEqual(self.client.post("/webhook", json={"events": [event]}).status_code, 200)
        self.reply.assert_called_once()
        _, _, flex, fallback = self.reply.call_args.args
        self.assertEqual(page, fallback)
        self.assertIn(text, page)
        self.assertIn(text, json.dumps(flex, ensure_ascii=False))
        self.assertNotIn("1101", page)
        self.assertNotIn("2026-10-13", page)
        status = self.client.get("/top5_status").get_json()
        self.assertEqual(status["version"], self.app_module.VERSION)
        self.assertEqual(status["scan_date"], self.date)
        self.assertIs(status["has_result"], has_result)
        self.assertEqual(status["count"], count)
        self.scan.assert_not_called()
        return page

    def test_today_has_eligible_stocks(self):
        self.add_row("2330")
        self.assert_today("2330", True, 1)

    def test_today_completed_empty_with_history(self):
        self.add_row("1101", "2026-10-13")
        self.add_row("__EMPTY__", rank=0)
        self.assert_today("今日無符合進場條件標的", True, 0)

    def test_empty_marker_keeps_cron_locked(self):
        self.add_row("__EMPTY__", rank=0)
        result = self.client.get("/scan_top5_cron?limit=30").get_json()
        self.assertTrue(result["locked"])
        self.assertEqual(result["scan_date"], self.date)
        self.assertEqual(result["eligible_count"], 0)
        self.assertEqual(result["saved_count"], 0)
        self.assertEqual(result["top5"], [])
        self.scan.assert_not_called()
        import market_scan

        with patch("market_scan.scan_market_top5") as auto_scan:
            self.assertEqual(market_scan.get_saved_or_scan_top5(auto_scan=True), [])
            auto_scan.assert_not_called()

    def test_marker_does_not_consume_rank_slot(self):
        self.add_row("__EMPTY__", rank=0)
        for rank, symbol in enumerate(["2330", "2317", "2454", "2308", "2881"], 1):
            self.add_row(symbol, rank=rank)
        page = self.assert_today("2881", True, 5)
        self.assertNotIn("__EMPTY__", page)

    def test_today_not_scanned(self):
        self.assert_today("今日 Top5 尚未完成掃描", False, 0)

    def test_today_not_scanned_with_history(self):
        self.add_row("1101", "2026-10-13")
        self.assert_today("今日 Top5 尚未完成掃描", False, 0)

    def test_weekend_with_history(self):
        self.date = "2026-11-14"
        self.add_row("1101", "2026-10-13")
        self.assert_today("今日 Top5 尚未完成掃描", False, 0)
