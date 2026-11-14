import json
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime
from io import StringIO
from unittest.mock import Mock, patch

import requests

import overnight_risk as risk
import test_top5_freshness


def taipei(day=16, hour=8, month=11):
    return datetime(2026, month, day, hour, tzinfo=risk.TAIPEI)


def tx_response(change="-0.20%", attribution="2026/11/16", start="2026/11/13", label="盤後"):
    cells = ["TX", "202611", "100", "101", "97", "99", "-1", change, "5",
             "-", "98", "99", "101", "90"]
    # 15 columns, including the open-interest placeholder after settlement.
    cells.insert(10, "-")
    html = f"<h2>日期：{attribution}</h2><h3>{start} 15:00~次日05:00 {label}交易時段行情表</h3>"
    html += "<table><tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr></table>"
    return Mock(content=html.encode("utf-8"))


def us_response(rows="2026-11-12,100,100\n2026-11-13,101,99"):
    return Mock(text=f"observation_date,SP500,NASDAQCOM\n{rows}\n")


class OvernightRiskTests(unittest.TestCase):
    def collect(self, now=None, tx=None, us=None):
        def fetch(url, **kwargs):
            self.assertEqual(kwargs["timeout"], 4)
            response = tx if url == risk.TAIFEX_URL else us
            if isinstance(response, Exception):
                raise response
            return response

        with patch.object(risk.requests, "get", side_effect=fetch):
            return risk.collect_overnight_risk(now or taipei())

    def test_completed_friday_night_and_diverging_us(self):
        result = self.collect(tx=tx_response("+0.20%"), us=us_response())
        sources = result["sources"]
        self.assertEqual(result["mode"], "shadow")
        self.assertEqual(result["risk_level"], "中")
        self.assertEqual(sources["tx"]["trade_date"], "2026-11-16")
        self.assertEqual(sources["tx"]["market_data_time"], "2026-11-14T05:00:00+08:00")
        self.assertEqual(sources["tx"]["contract"], "202611")
        self.assertEqual(sources["tx"]["change_pct"], 0.2)
        self.assertEqual(sources["sp500"]["change_pct"], 1)
        self.assertEqual(sources["nasdaq"]["change_pct"], -1)
        self.assertEqual(sources["nasdaq"]["market_data_time"], "2026-11-13T16:00:00-05:00")
        summary = risk.format_overnight_summary(result)
        self.assertIn("11/14 05:00 台北", summary)
        self.assertIn("非買賣訊號", summary)
        self.assertLess(len(summary), 200)

    def test_risk_thresholds(self):
        self.assertEqual(self.collect(tx=tx_response("-0.50%"), us=us_response())["risk_level"], "高")
        self.assertEqual(self.collect(tx=tx_response("-1.50%"), us=us_response(
            "2026-11-12,100,100\n2026-11-13,101,101"))["risk_level"], "高")
        self.assertEqual(self.collect(tx=tx_response(), us=us_response(
            "2026-11-12,100,100\n2026-11-13,101,101"))["risk_level"], "低")

    def test_taifex_direction_markers_in_risk_and_line_summary(self):
        stocks_up = us_response("2026-11-12,100,100\n2026-11-13,101,101")
        for raw, change, level in (
            ("▼0.50%", -0.5, "中"),
            ("▼1.50%", -1.5, "高"),
            ("▲1.50%", 1.5, "低"),
            ("▼-1.50%", -1.5, "高"),
            ("▲+1.50%", 1.5, "低"),
        ):
            with self.subTest(raw=raw):
                result = self.collect(tx=tx_response(raw), us=stocks_up)
                self.assertEqual(result["sources"]["tx"]["change_pct"], change)
                self.assertEqual(result["risk_level"], level)
                self.assertIn(f"台指期夜盤 TX202611 {change:+.2f}%", risk.format_overnight_summary(result))

    def test_plain_numbers_and_missing_tx_change(self):
        self.assertEqual(risk._number("43,706"), 43706)
        self.assertEqual(risk._number("56,132"), 56132)
        self.assertEqual(risk._tx_change_pct("-1.50%"), -1.5)
        self.assertEqual(risk._tx_change_pct("+1.50%"), 1.5)
        self.assertIsNone(risk._tx_change_pct("▼-"))

    def test_source_failures_and_missing_data(self):
        error = requests.Timeout("private debug details")
        partial = self.collect(tx=error, us=us_response("2026-11-12,100,100\n2026-11-13,101,"))
        self.assertEqual(partial["risk_level"], "資料不足")
        self.assertEqual(partial["sources"]["tx"]["status"], "unavailable")
        self.assertEqual(partial["sources"]["sp500"]["status"], "ok")
        self.assertEqual(partial["sources"]["nasdaq"]["status"], "stale")
        self.assertIsNone(partial["sources"]["nasdaq"]["change_pct"])
        failed = self.collect(tx=error, us=error)
        self.assertEqual(failed["risk_level"], "資料不足")
        self.assertTrue(all(item["status"] == "unavailable" for item in failed["sources"].values()))
        self.assertNotIn("private debug", json.dumps(failed))

    def test_stale_and_day_session_rejected(self):
        for response, status in (
            (tx_response(attribution="2026/11/13", start="2026/11/12"), "stale"),
            (tx_response(start="2026/11/12"), "stale"),
            (tx_response(label="一般"), "unavailable"),
        ):
            with self.subTest(status=status):
                source = self.collect(tx=response, us=us_response())["sources"]["tx"]
                self.assertEqual(source["status"], status)
                self.assertIsNone(source["value"])

    def test_incomplete_session_never_fetched(self):
        with patch.object(risk.requests, "get") as get:
            result = risk.collect_overnight_risk(taipei(day=13, hour=4))
        get.assert_not_called()
        self.assertEqual(result["risk_level"], "資料不足")
        self.assertTrue(all(item["detail"] == "session_not_complete" for item in result["sources"].values()))

    def test_tw_weekend_and_holiday(self):
        for now in (taipei(day=14), taipei(day=25, month=12)):
            with patch.object(risk.requests, "get") as get:
                result = risk.collect_overnight_risk(now)
            get.assert_not_called()
            self.assertIsNone(result["as_of"]["trade_date"])
            self.assertEqual(result["risk_reasons"], ["台股休市"])

    def test_us_holiday_and_early_close(self):
        closed = self.collect(
            now=taipei(day=27), tx=tx_response(attribution="2026/11/27", start="2026/11/26"),
            us=us_response("2026-11-24,100,100\n2026-11-25,101,101"),
        )
        self.assertEqual(closed["sources"]["sp500"]["status"], "stale")
        self.assertEqual(closed["risk_level"], "資料不足")
        self.assertEqual(risk._us_close(date(2026, 11, 27)).hour, 13)

    def test_dst_close_time(self):
        for day, expected_hour in ((date(2026, 3, 6), 5), (date(2026, 3, 9), 4),
                                   (date(2026, 10, 30), 4), (date(2026, 11, 2), 5)):
            with self.subTest(day=day):
                self.assertEqual(risk._us_close(day).astimezone(risk.TAIPEI).hour, expected_hour)


class OvernightIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_top5_freshness.Top5FreshnessTests.setUpClass()
        cls.client = test_top5_freshness.Top5FreshnessTests.app_module.app.test_client()

    def test_read_only_status_and_health(self):
        with (
            patch("app.get_overnight_risk", return_value=risk.collect_overnight_risk(taipei(day=14))),
            patch("app.run_morning_report") as morning,
            patch("app.scan_market_top5") as scan,
        ):
            response = self.client.get("/overnight_risk_status")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["version"], "v21.3")
            self.assertEqual(response.get_json()["mode"], "shadow")
            self.assertEqual(self.client.get("/health").get_json(), {"status": "ok", "version": "v21.3"})
        morning.assert_not_called()
        scan.assert_not_called()

    def test_cron_logs_exclude_user_ids_and_exception_details(self):
        from cron_runner import main
        from morning_job import run_morning_report

        logs = StringIO()
        with (
            patch("cron_runner.run_morning_report", side_effect=run_morning_report),
            patch("morning_job.get_all_user_ids", return_value=["private-user-id"]),
            patch("morning_job.get_user_stocks", side_effect=RuntimeError("private-token")),
            redirect_stdout(logs),
        ):
            self.assertEqual(main(), 1)
        self.assertIn('"failed": 1', logs.getvalue())
        self.assertNotIn("private-", logs.getvalue())

    def test_line_and_push_share_summary_even_when_sources_fail(self):
        from morning_job import run_morning_report

        event = {"type": "message", "replyToken": "test", "source": {"userId": "test"},
                 "message": {"type": "text", "text": "今日早報"}}
        with (
            patch("app.clear_user_state"),
            patch("app.get_user_stocks", return_value=["2330", "2317"]),
            patch("app.reply_flex") as reply,
            patch("morning_job.get_all_user_ids", return_value=["first", "second"]),
            patch("morning_job.get_user_stocks", return_value=["2330", "2317"]),
            patch("morning_job.push_flex", return_value=True) as push,
            patch("report.get_overnight_risk", side_effect=requests.Timeout) as get_risk,
            patch("report.get_stock_data", return_value=None),
        ):
            self.assertEqual(self.client.post("/webhook", json={"events": [event]}).status_code, 200)
            get_risk.assert_called_once()
            get_risk.reset_mock()
            self.assertEqual(run_morning_report()["sent"], 2)
            get_risk.assert_called_once()
        for call in push.call_args_list:
            self.assertEqual(reply.call_args.args[1:], call.args[1:])
            self.assertIn("隔夜市場風險｜資料不足", call.args[-1])
            self.assertIn("目前自選股都查不到資料", call.args[-1])
