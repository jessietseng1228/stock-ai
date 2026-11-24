import json
from copy import deepcopy
import unittest
from datetime import date, datetime
from unittest.mock import Mock, patch

import requests

import overnight_risk as risk
import test_overnight_risk as existing
from test_overnight_risk import tx_response, us_response


class HotfixTests(unittest.TestCase):
    def test_expected_dates_for_issue_week(self):
        for day, expected in ((16, 13), (17, 16), (18, 17), (19, 18), (20, 19), (23, 20)):
            for hour in (9, 11):
                with self.subTest(day=day, hour=hour):
                    now = datetime(2026, 11, day, hour, 58, tzinfo=risk.TAIPEI)
                    previous = risk._previous_trading_day(now.date(), risk.TW_HOLIDAYS)
                    expected_date = date(2026, 11, expected)
                    prior = risk._previous_trading_day(expected_date, risk.US_HOLIDAYS)
                    response = us_response(f"{prior},100,100\n{expected_date},101,99")
                    with patch.object(risk.requests, "get", return_value=response):
                        sources = risk._fetch_us(now.date(), previous, now)
                    for source in sources.values():
                        self.assertEqual(source["status"], "ok")
                        self.assertEqual(source["expected_trade_date"], str(expected_date))
                        self.assertEqual(source["latest_available_trade_date"], str(expected_date))

    def snapshot(self, change="-5.25%"):
        now = datetime(2026, 11, 23, 11, 58, tzinfo=risk.TAIPEI)
        tx = tx_response(change, "2026/11/23", "2026/11/20")
        tx.content = tx.content.replace(b"202611", b"202612").replace(b"<td>99</td>", b"<td>33919</td>")
        return existing.OvernightRiskTests().collect(
            now=now, tx=tx,
            us=us_response("2026-11-18,100,100\n2026-11-19,101,99"),
        )

    def test_known_tx_crash_with_delayed_us(self):
        result = self.snapshot()
        self.assertEqual(result["risk_level"], "高")
        self.assertEqual(result["data_completeness"], "incomplete")
        self.assertEqual(result["sources"]["tx"]["contract"], "202612")
        self.assertEqual(result["sources"]["tx"]["value"], 33919)
        self.assertEqual(result["sources"]["tx"]["market_data_time"], "2026-11-21T05:00:00+08:00")
        for key in ("sp500", "nasdaq"):
            source = result["sources"][key]
            self.assertEqual(source["status"], "stale")
            self.assertEqual(source["detail"], "source_delayed")
            self.assertEqual(source["expected_trade_date"], "2026-11-20")
            self.assertEqual(source["latest_available_trade_date"], "2026-11-19")
            self.assertIsNone(source["change_pct"])
        summary = risk.format_overnight_summary(result)
        self.assertIn("已知高風險", summary)
        self.assertIn("美股資料不完整", summary)
        self.assertIn("資料延遲／待更新", summary)
        self.assertIn("最後有效資料交易日：11/19（美東）｜預期交易日：11/20（美東）", summary)
        self.assertNotIn("11/20 05:00 台北", summary)
        self.assertLess(len(summary), 400)

    def test_delayed_us_dates_with_missing_values(self):
        for latest, expected in ((None, None), ("2026-11-19", None), (None, "2026-11-20")):
            with self.subTest(latest=latest, expected=expected):
                snapshot = self.snapshot()
                for key in ("sp500", "nasdaq"):
                    snapshot["sources"][key].update(
                        latest_available_trade_date=latest, expected_trade_date=expected,
                        market_data_time=None,
                    )
                summary = risk.format_overnight_summary(snapshot)
                self.assertIn("最後有效資料交易日：" + ("11/19（美東）" if latest else "未知"), summary)
                self.assertIn("預期交易日：" + ("11/20（美東）" if expected else "未知"), summary)
                self.assertNotIn("None", summary)
                self.assertEqual(snapshot["risk_level"], "高")

    def test_partial_medium_and_no_partial_low(self):
        self.assertEqual(self.snapshot("-0.50%")["risk_level"], "中")
        self.assertIn("已知部分風險", risk.format_overnight_summary(self.snapshot("-0.50%")))
        self.assertEqual(self.snapshot("+0.50%")["risk_level"], "資料不足")

    def test_us_crash_with_missing_tx_and_all_failed(self):
        now = datetime(2026, 11, 23, 9, tzinfo=risk.TAIPEI)
        result = existing.OvernightRiskTests().collect(now, requests.Timeout(), us_response(
            "2026-11-19,100,100\n2026-11-20,98,101"))
        self.assertEqual(result["risk_level"], "高")
        self.assertEqual(result["data_completeness"], "incomplete")
        failed = existing.OvernightRiskTests().collect(now, requests.Timeout(), requests.Timeout())
        self.assertEqual(failed["risk_level"], "資料不足")
        self.assertEqual(failed["sources"]["sp500"]["detail"], "network_error")

    def test_complete_and_stale_crash(self):
        sources = {key: risk._source(key, "ok", change_pct=0) for key in risk.SOURCES}
        self.assertEqual(risk.assess_risk(sources)[0], "低")
        sources["tx"] = risk._source("tx", "stale", change_pct=-5.25)
        self.assertEqual(risk.assess_risk(sources)[0], "資料不足")

    def test_missing_column_is_isolated(self):
        now = datetime(2026, 11, 23, 9, tzinfo=risk.TAIPEI)
        response = Mock(text="observation_date,SP500\n2026-11-19,100\n2026-11-20,101\n")
        with patch.object(risk.requests, "get", return_value=response):
            result = risk._fetch_us(now.date(), date(2026, 11, 20), now)
        self.assertEqual(result["sp500"]["status"], "ok")
        self.assertEqual(result["nasdaq"]["detail"], "column_missing")

    def test_invalid_response_and_previous_close_gap(self):
        now = datetime(2026, 11, 23, 9, tzinfo=risk.TAIPEI)
        for response, detail in (
            (Mock(text="<html>error</html>"), "invalid_response"),
            (us_response("2026-11-20,100,100"), "previous_close_missing"),
        ):
            with patch.object(risk.requests, "get", return_value=response):
                sources = risk._fetch_us(now.date(), date(2026, 11, 20), now)
            self.assertEqual(sources["sp500"]["detail"], detail)


class HotfixIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        existing.OvernightIntegrationTests.setUpClass()
        cls.client = existing.OvernightIntegrationTests.client

    def test_history_performance_and_learning_routes(self):
        with (
            patch("app.get_completed_ai_learning_history", return_value=[]),
            patch("app.get_ai_performance_history", return_value=[]),
            patch("app.build_ai_history_report", return_value="history"),
            patch("app.build_performance_report", return_value="performance"),
            patch("app.get_overnight_risk") as overnight,
        ):
            self.assertEqual(self.client.get("/ai_history").get_data(as_text=True), "history")
            self.assertEqual(self.client.get("/performance").get_data(as_text=True), "performance")
            for route in ("/learning_status", "/performance_status"):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json()["status"], "ok")
                self.assertIn("version", response.get_json())
        overnight.assert_not_called()

    def test_diagnostics_manual_and_push_consistency(self):
        snapshot = HotfixTests().snapshot()
        original = deepcopy(snapshot)
        event = {"type": "message", "replyToken": "test", "source": {"userId": "test"},
                 "message": {"type": "text", "text": "今日早報"}}
        with (
            patch("app.get_overnight_risk", return_value=snapshot),
            patch("report.get_overnight_risk", return_value=snapshot),
            patch("report.get_stock_data", return_value=None),
            patch("app.clear_user_state"),
            patch("app.get_user_stocks", return_value=["2330"]),
            patch("app.reply_flex") as reply,
            patch("morning_job.get_all_user_ids", return_value=["test"]),
            patch("morning_job.get_user_stocks", return_value=["2330"]),
            patch("morning_job.push_flex", return_value=True) as push,
        ):
            response = self.client.get("/overnight_risk_status")
            self.assertEqual(response.get_json()["data_completeness"], "incomplete")
            self.assertEqual(response.get_json()["risk_level"], "高")
            self.client.post("/webhook", json={"events": [event]})
            from morning_job import run_morning_report
            self.assertEqual(run_morning_report()["sent"], 1)
        self.assertEqual(reply.call_args.args[1:], push.call_args.args[1:])
        self.assertIn("已知高風險", json.dumps(reply.call_args.args, ensure_ascii=False))
        self.assertEqual(snapshot, original)
        _, _, flex, fallback = reply.call_args.args
        self.assertIn("最後有效資料交易日：11/19（美東）", fallback)
        self.assertIn("預期交易日：11/20（美東）", json.dumps(flex, ensure_ascii=False))
        self.assertLess(len(fallback), 500)
        self.assertLess(len(json.dumps(flex, ensure_ascii=False).encode("utf-8")), 30_000)
