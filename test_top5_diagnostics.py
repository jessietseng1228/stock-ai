import unittest
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import test_top5_freshness


class Top5DiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_top5_freshness.Top5FreshnessTests.setUpClass()
        cls.client = test_top5_freshness.Top5FreshnessTests.app_module.app.test_client()

    def setUp(self):
        self.date = "2026-11-14"
        self.quotes = [
            {"symbol": str(code), "turnover": 200_000_000, "volume": 0}
            for code in range(2300, 2305)
        ]
        self.enterContext(patch("market_scan.today_taipei", return_value=self.date))
        self.enterContext(patch("market_scan.MIN_TURNOVER", 100_000_000))
        self.enterContext(patch("market_scan.requests.get", side_effect=self.exchange_response))
        self.enterContext(patch("market_scan.get_completed_ai_learning_history", return_value=[]))
        self.enterContext(patch("market_scan.detect_market_regime", return_value={}))
        self.batch = self.enterContext(patch("market_scan._batch_download", return_value=None))
        self.fallback = self.enterContext(patch("market_scan._fallback_chart_batch", return_value={}))
        self.save = self.enterContext(patch("market_scan.save_market_top5"))
        self.save_history = self.enterContext(patch("market_scan.save_ai_recommend_history"))

    def exchange_response(self, url, **kwargs):
        response = Mock()
        if "twse.com.tw" in url:
            rows = [[q["symbol"], "測試", q["turnover"]] for q in self.quotes]
            rows.extend([["0050", "ETF", 200_000_000], ["2400", "測試", 0], rows[0]])
            response.json.return_value = {
                "tables": [{"fields": ["證券代號", "證券名稱", "成交金額"], "data": rows}]
            }
        else:
            response.json.return_value = []
        return response

    def preview(self):
        response = self.client.get("/scan_top5?limit=30")
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertEqual(result["version"], test_top5_freshness.Top5FreshnessTests.app_module.VERSION)
        self.assertEqual(result["scan_date"], self.date)
        self.assertFalse(result["locked"])
        self.assertEqual(result["saved_count"], 0)
        self.save.assert_not_called()
        self.save_history.assert_not_called()
        diagnostics = result["diagnostics"]
        universe = diagnostics["universe"]
        self.assertEqual(universe["raw_count"], 8)
        self.assertEqual(universe["non_common_or_malformed"], 1)
        self.assertEqual(universe["invalid_or_duplicate"], 1)
        self.assertEqual(universe["turnover_excluded"], 1)
        self.assertEqual(universe["count"], 5)
        self.assertEqual(
            sum(diagnostics["primary_exclusions"].values()) + result["eligible_count"],
            result["candidate_count"],
        )
        self.assertEqual(sum(diagnostics["decision_types"].values()), result["scored_count"])
        return result, diagnostics

    def test_no_quotes(self):
        result, diagnostics = self.preview()
        self.assertEqual(result["top5"], [])
        self.assertEqual(result["scored_count"], 0)
        self.assertEqual(diagnostics["quotes"], {
            "batch_success": 0, "batch_failure": 5,
            "fallback_success": 0, "fallback_failure": 5, "fallback_not_attempted": 0,
        })
        self.assertEqual(diagnostics["technical_data_insufficient_count"], 5)
        self.assertEqual(diagnostics["primary_exclusions"], {"no_quotes": 5})
        self.assertEqual(diagnostics["missing_quote_fields"]["close"], 5)

    def test_partial_eligible_with_overlapping_reasons(self):
        self.fallback.return_value = {
            f"{q['symbol']}.TW": {"closes": [1]} for q in self.quotes[:4]
        }
        data = [
            {"symbol": "2300", "price": 100, "stop_loss": 90},
            {"symbol": "2301", "price": 100, "stop_loss": 0},
            {"symbol": "2302", "price": 0, "change_pct": -6, "five_pct": -12, "volume": 1},
            None,
            None,
        ]
        allowed = {"decision": "🟢 可分批布局", "rr": 1, "entry_low": 100, "entry_high": 100}
        excluded = {"decision": "等待", "rr": 0, "entry_low": 0}
        with (
            patch("market_scan._build_data_from_values", side_effect=data),
            patch("market_scan.learning_adjustment", return_value={"learned_score": 70}),
            patch("market_scan.trade_plan", side_effect=[allowed, excluded]),
            patch("market_scan.decision_narrative", return_value=""),
            patch("market_scan.apply_decision_engine", return_value={"final_score": 70}),
        ):
            result, diagnostics = self.preview()
        self.assertEqual([row["symbol"] for row in result["top5"]], ["2300"])
        self.assertEqual(result["excluded_count"], 1)
        self.assertEqual(result["eligible_count"], 1)
        self.assertEqual(diagnostics["quotes"]["fallback_success"], 4)
        self.assertEqual(diagnostics["quotes"]["fallback_failure"], 1)
        primary = {"decision": 1, "price": 1, "technical_data_insufficient": 1, "no_quotes": 1}
        self.assertEqual(diagnostics["primary_exclusions"], primary)
        self.assertEqual(diagnostics["all_exclusions"], {
            **primary, "rr": 1, "entry": 1, "stop_loss": 1,
            "daily_change": 1, "five_day_change": 1, "volume": 1,
        })
        self.assertEqual(diagnostics["missing_quote_fields"]["volume"], 5)

    def test_nonempty_batch_only_retries_missing_closes(self):
        self.batch.return_value = SimpleNamespace(empty=False, shape=(1, 1))
        self.fallback.return_value = {"2301.TW": {"closes": [110]}}
        with patch("market_scan._extract_series", side_effect=lambda _, ticker, field:
                   [100] if ticker == "2300.TW" and field == "Close" else []):
            result, diagnostics = self.preview()
        self.assertEqual(
            [row["symbol"] for row in self.fallback.call_args.args[0]],
            ["2301", "2302", "2303", "2304"],
        )
        self.assertFalse(result["batch_empty"])
        self.assertEqual(result["eligible_count"], 0)
        self.assertEqual(diagnostics["quotes"]["batch_success"], 1)
        self.assertEqual(diagnostics["quotes"]["batch_failure"], 4)
        self.assertEqual(diagnostics["quotes"]["fallback_success"], 1)
        self.assertEqual(diagnostics["quotes"]["fallback_failure"], 3)
        self.assertEqual(diagnostics["primary_exclusions"]["no_quotes"], 3)
        self.assertEqual(sum(diagnostics["decision_types"].values()), 2)

    def test_partial_fallback_is_bounded_and_skipped_in_official_scan(self):
        from market_scan import scan_market_top5

        self.quotes.extend({"symbol": str(code), "turnover": 200_000_000} for code in range(2305, 2312))
        self.batch.return_value = SimpleNamespace(empty=False, shape=(1, 1))
        with patch("market_scan._extract_series", side_effect=lambda _, ticker, field:
                   [100] if ticker == "2300.TW" and field == "Close" else []):
            diagnostics = self.client.get("/scan_top5?limit=30").get_json()["diagnostics"]
            self.assertEqual(len(self.fallback.call_args.args[0]), 8)
            self.assertEqual(diagnostics["quotes"]["fallback_failure"], 8)
            self.assertEqual(diagnostics["quotes"]["fallback_not_attempted"], 3)
            self.fallback.reset_mock()
            self.save_history.return_value = {}
            result = scan_market_top5(limit=30, save=True)
        self.fallback.assert_not_called()
        self.assertEqual(result["diagnostics"]["quotes"]["fallback_not_attempted"], 11)

    def test_source_failure_is_distinct_from_empty(self):
        empty_twse = Mock()
        empty_twse.json.return_value = {"stat": "OK", "tables": []}
        with patch("market_scan.requests.get", side_effect=[empty_twse, TimeoutError("private details")]):
            diagnostics = self.client.get("/scan_top5?limit=30").get_json()["diagnostics"]
        self.assertEqual(diagnostics["universe"]["raw_count"], 0)
        self.assertEqual(diagnostics["universe"]["source_fetch_status"], {"twse": "empty", "tpex": "error"})
        self.assertNotIn("private details", json.dumps(diagnostics))
