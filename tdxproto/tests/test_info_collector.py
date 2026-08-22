"""InfoCollector 结构化采集测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tdxproto.info import InfoCollector
from tdxproto.info.models import NewsItem, AnnouncementItem, ResearchReport


def _mock_response(rows: list[dict], cols: list[str]):
    return MagicMock(
        rows=rows,
        result_sets=[MagicMock(columns=cols, rows=rows, count=len(rows))],
    )


class TestCollector:
    def test_news_rows(self):
        items = [
            NewsItem(issue_date="2026-08-21", title="新闻1", source="财联社",
                     redistime="2026-08-21 10:00", rec_id="1"),
        ]
        rows = __import__("tdxproto.info.collector", fromlist=["news_rows"]).news_rows(items)
        assert rows[0]["title"] == "新闻1"
        assert rows[0]["source"] == "财联社"
        assert rows[0]["url"] == ""

    def test_announcement_rows(self):
        items = [
            AnnouncementItem(issue_date="2026-08-22", title="公告", typecode="0123",
                             typename="其它重大事项", rec_id="9",
                             pdf_url="http://x/1.pdf", source="深交所", redistime="t"),
        ]
        rows = __import__("tdxproto.info.collector", fromlist=["announcement_rows"]).announcement_rows(items)
        assert rows[0]["pdf_url"] == "http://x/1.pdf"
        assert rows[0]["typename"] == "其它重大事项"

    def test_report_rows(self):
        items = [
            ResearchReport(title="点评", rating="买入", analyst="张三",
                           date="20260817", report_id=123),
        ]
        rows = __import__("tdxproto.info.collector", fromlist=["report_rows"]).report_rows(items)
        assert rows[0]["report_id"] == 123
        assert rows[0]["rating"] == "买入"

    def test_composition_rows(self):
        raw = [{"N000": "按地区", "N002": "总部", "N003": 38896000000,
                "N004": 55.08, "N005": 10682000000, "N006": 26.85,
                "N007": 28214000000, "N008": 55.58, "N009": 72.54}]
        rows = __import__("tdxproto.info.collector", fromlist=["composition_rows"]).composition_rows(raw)
        assert rows[0]["dimension"] == "按地区"
        assert rows[0]["revenue"] == 38896000000
        assert rows[0]["gross_margin_pct"] == 72.54

    def test_northbound_rows(self):
        raw = [{"N001": "2026-06-30", "N002": 3.79, "N003": 736878410,
                "N004": 166106362, "N005": 29.102, "N006": 10.05}]
        rows = __import__("tdxproto.info.collector", fromlist=["northbound_rows"]).northbound_rows(raw)
        assert rows[0]["date"] == "2026-06-30"
        assert rows[0]["holding_pct"] == 3.79

    def test_dividend_rows(self):
        raw = [{"rq": "2026-06-30", "T003": "2026-08-15", "T004": "10派2.49元(含税)",
                "T006": 1.24, "T026": 5.22, "T021": None, "T023": None,
                "T036": "董事会预案", "aT036": "036001", "glzfl": 18.8, "jdcode": "全体股东"}]
        rows = __import__("tdxproto.info.collector", fromlist=["dividend_rows"]).dividend_rows(raw)
        assert rows[0]["plan_text"] == "10派2.49元(含税)"
        assert rows[0]["status"] == "董事会预案"
        assert rows[0]["record_date"] is None

    def test_topic_rows(self):
        raw = [{"t001": "2817", "t002": "跨境支付CIPS"}]
        rows = __import__("tdxproto.info.collector", fromlist=["topic_rows"]).topic_rows(raw)
        assert rows[0]["topic_id"] == "2817"
        assert rows[0]["topic_name"] == "跨境支付CIPS"

    def test_score_rows(self):
        raw = [{"N001": 2.9027, "N002": 13, "N003": 15, "N004": 3392, "N005": 5549,
                "N006": 38.89, "N007": "2026-08-21", "N008": 2.2, "N009": 2.1567,
                "N010": 3, "N011": 5, "N012": "全国性银行", "N018": "平安银行",
                "N013": 2.55, "N014": 2.14, "N015": 3.23, "N016": 5, "N017": 3.01}]
        rows = __import__("tdxproto.info.collector", fromlist=["score_rows"]).score_rows(raw)
        assert rows[0]["name"] == "平安银行"
        assert rows[0]["total_score"] == 2.9027
        assert rows[0]["rank"] == 13

    def test_snapshot_all_sections(self):
        ic = MagicMock()
        ic.news.return_value = []
        ic.announcements.return_value = []
        ic.research_reports.return_value = []
        ic.business_composition.return_value = _mock_response([], [])
        ic.northbound_holding.return_value = _mock_response([], [])
        ic.dividend_financing.return_value = _mock_response([], [])
        ic.topic_ids.return_value = _mock_response([], [])
        ic.stock_score.return_value = _mock_response([], [])
        ic.company_profile.return_value = _mock_response([], [])
        ic.finance_report.return_value = _mock_response([], [])
        ic.finance_diagnosis.return_value = _mock_response([], [])
        ic.shareholder_change_plans.return_value = _mock_response([], [])
        ic.roadshows.return_value = []
        col = InfoCollector(ic)
        snap = col.snapshot(0, "000001")
        assert set(snap.keys()) == {
            "code", "news", "announcements", "research_reports",
            "business_composition", "northbound_holding",
            "dividends", "topics", "score",
            "profile", "balance_sheet", "cashflow",
            "diagnosis", "shareholder_plans", "roadshows",
        }
        assert snap["code"] == "000001"

    def test_topic_members_uses_numeric_id(self):
        ic = MagicMock()
        ic.topic_compare.return_value = _mock_response(
            [{"pm": 1, "zqdm": "600577", "zqjc": "精达股份", "sc": 1, "zdf": 10.04,
              "zdf_3d": 0.35, "zdf_5d": 6.78, "zdf_20d": 21.97, "zdf_60d": -38.88,
              "zdf_ys": -29.99, "tjdate": 20260821}],
            ["pm", "zqdm", "zqjc", "sc", "zdf"],
        )
        col = InfoCollector(ic)
        rows = col.topic_members("000001", "2817")
        ic.topic_compare.assert_called_once()
        assert rows[0]["code"] == "600577"
        assert rows[0]["change_pct"] == 10.04
