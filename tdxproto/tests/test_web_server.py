"""web_server 单元 / 功能测试."""

from unittest.mock import MagicMock, patch

from tdxproto.hk import HkQuote
from tdxproto.models import Quote


class TestDcToDict:
    def test_quote_bytes_hex(self):
        import web_server

        q = Quote(code="IFL0", price=1.0, raw=b"\x01\xff")
        d = web_server.dc_to_dict(q)
        assert d["code"] == "IFL0"
        assert d["raw"] == "01ff"


class TestGetFuturesClient:
    def test_uses_reconnect_not_private_connect(self):
        import web_server

        fake = MagicMock()
        fake._tube = object()
        prev = web_server._futures_client
        try:
            web_server._futures_client = None
            with patch.object(web_server, "FuturesClient", return_value=fake) as cls:
                c = web_server.get_futures_client()
            cls.assert_called_once()
            fake.reconnect.assert_called_once()
            fake._connect.assert_not_called()
            assert c is fake
        finally:
            web_server._futures_client = prev


class TestHtmlFields:
    def test_quote_template_uses_model_fields(self):
        import web_server

        html = web_server.HTML_TEMPLATE
        assert "q.bid_p" in html
        assert "q.pre_close" in html
        assert "q.volume" in html
        assert "q.pre_settle" not in html
        assert 'q["bid1"]' not in html
        assert "last_close" not in html


class TestApiHandlers:
    def test_futures_quote_ok(self):
        import web_server

        q = Quote(
            code="IFL0", price=3800.0, pre_close=3790.0, volume=12,
            open_interest=100, bid_p=[1.0] * 5, bid_v=[2] * 5,
        )
        handler = web_server.Handler.__new__(web_server.Handler)
        handler.path = "/api/futures/quote?code=IFL0&market=47"
        sent = {}

        def _send_json(data, status=200):
            sent["data"] = data
            sent["status"] = status

        handler._send_json = _send_json
        handler._sanitize_error = web_server.Handler._sanitize_error.__get__(handler)
        fake = MagicMock()
        fake.quote.return_value = q
        with patch.object(web_server, "get_futures_client", return_value=fake):
            handler._handle_futures_quote()
        assert sent["status"] == 200
        quote = sent["data"]["quote"]
        assert quote.pre_close == 3790.0
        assert quote.volume == 12
        assert not hasattr(quote, "pre_settle")

    def test_hk_quote_ok(self):
        import web_server

        q = HkQuote(
            code="00700", name="腾讯", price=445.2, pre_close=433.0,
            open=442.4, high=446.6, low=440.0, volume=1, amount=1.0,
            change_pct=2.82, change_amt=12.2, turnover_pct=0.0, time="t",
        )
        handler = web_server.Handler.__new__(web_server.Handler)
        handler.path = "/api/hk/quote?code=00700"
        sent = {}
        handler._send_json = lambda data, status=200: sent.update(data=data, status=status)
        handler._sanitize_error = web_server.Handler._sanitize_error.__get__(handler)
        fake = MagicMock()
        fake.quote.return_value = q
        with patch.object(web_server, "get_hk_client", return_value=fake):
            handler._handle_hk_quote()
        assert sent["data"]["quote"].code == "00700"

    def test_hk_quote_missing(self):
        import web_server

        handler = web_server.Handler.__new__(web_server.Handler)
        handler.path = "/api/hk/quote?code=99999"
        sent = {}
        handler._send_json = lambda data, status=200: sent.update(data=data, status=status)
        handler._sanitize_error = web_server.Handler._sanitize_error.__get__(handler)
        fake = MagicMock()
        fake.quote.return_value = None
        with patch.object(web_server, "get_hk_client", return_value=fake):
            handler._handle_hk_quote()
        assert sent["data"]["error"] == "未找到数据"
