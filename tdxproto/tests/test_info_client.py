"""InfoClient 测试 — 7615 HTTP 网关。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, mock_open

from tdxproto.info import InfoClient, TqlexResponse, TqlexResultSet


def _make_mock_response(entry: str, rows: list[dict], cols: list[str] | None = None) -> bytes:
    if cols is None and rows:
        cols = list(rows[0].keys())
    result_set = {
        "ResultSetKey": "table0",
        "ColName": cols or [],
        "Content": [[r.get(c, "") for c in (cols or [])] for r in rows],
        "Count": len(rows),
    }
    resp = {"ErrorCode": 0, "ResultSets": [result_set]}
    return json.dumps(resp, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class TestInfoClient:
    def test_news_parses_response(self):
        data = _make_mock_response("CWSearch.tzx_rcache", [
            {"issue_date": "2026-08-21", "title": "测试新闻1", "source": "财联社", "redistime": "2026-08-21 10:00", "rec_id": "1"},
            {"issue_date": "2026-08-20", "title": "测试新闻2", "source": "上证报", "redistime": "2026-08-20 10:00", "rec_id": "2"},
        ])
        with patch("urllib.request.urlopen") as mock:
            ctx = MagicMock()
            ctx.read.return_value = data
            mock.return_value.__enter__.return_value = ctx
            ic = InfoClient()
            news = ic.news(0, "000001")
        assert len(news) == 2
        assert news[0].title == "测试新闻1"
        assert news[0].source == "财联社"
        assert news[1].title == "测试新闻2"

    def test_announcements_parses_response(self):
        data = _make_mock_response("CWSearch.tzx_rcache", [
            {"issue_date": "2026-08-21", "title": "测试公告", "typecode": "010303",
             "typename": "半年度报告", "rec_id": "123", "url": "http://example.com/a.pdf",
             "source": "深交所", "redistime": "2026-08-21 20:00"},
        ])
        with patch("urllib.request.urlopen") as mock:
            ctx = MagicMock()
            ctx.read.return_value = data
            mock.return_value.__enter__.return_value = ctx
            ic = InfoClient()
            anns = ic.announcements(0, "000001")
        assert len(anns) == 1
        assert anns[0].title == "测试公告"
        assert anns[0].pdf_url == "http://example.com/a.pdf"
        assert anns[0].typename == "半年度报告"

    def test_empty_response(self):
        data = _make_mock_response("CWSearch.tzx_rcache", [])
        with patch("urllib.request.urlopen") as mock:
            ctx = MagicMock()
            ctx.read.return_value = data
            mock.return_value.__enter__.return_value = ctx
            ic = InfoClient()
            news = ic.news(0, "000001")
        assert len(news) == 0

    def test_call_raw_endpoint(self):
        data = _make_mock_response("CWServ.tdxf10_gg_comreq", [
            {"T003": "平安银行", "T002": "000001", "sc": 0},
        ])
        with patch("urllib.request.urlopen") as mock:
            ctx = MagicMock()
            ctx.read.return_value = data
            mock.return_value.__enter__.return_value = ctx
            ic = InfoClient()
            resp = ic.stock_info("000001")
        assert resp.ok
        assert len(resp.rows) == 1
        assert resp.rows[0]["T003"] == "平安银行"

    def test_tqlex_response_properties(self):
        rs = TqlexResultSet(key="t0", columns=["a", "b"], rows=[{"a": 1, "b": 2}])
        resp = TqlexResponse(entry="test", error_code=0, result_sets=[rs], raw={})
        assert resp.ok
        assert resp.rows == [{"a": 1, "b": 2}]

    def test_error_code_handling(self):
        resp = TqlexResponse(entry="test", error_code=1, result_sets=[], raw={})
        assert not resp.ok