"""main.py / batch.py CLI 功能测试."""

import json
from unittest.mock import MagicMock, patch

from tdxproto.hk import HkQuote
from tdxproto.models import Quote


class TestJs:
    def test_js_recurses_dict_of_dataclass(self, capsys):
        from main import js

        q = HkQuote(
            code="00700", name="腾讯", price=445.2, pre_close=433.0,
            open=442.4, high=446.6, low=440.0, volume=1, amount=1.0,
            change_pct=2.82, change_amt=12.2, turnover_pct=0.0, time="t",
        )
        js({"hk00700": q, "items": [q]})
        out = json.loads(capsys.readouterr().out)
        assert out["hk00700"]["code"] == "00700"
        assert out["hk00700"]["price"] == 445.2
        assert out["items"][0]["name"] == "腾讯"

    def test_js_bytes_hex(self, capsys):
        from main import js

        js({"raw": b"\x01\xff"})
        out = json.loads(capsys.readouterr().out)
        assert out["raw"] == "01ff"

    def test_js_inner_dict(self):
        from main import js_inner

        nested = js_inner({"q": Quote(code="sz000001", price=10.0)})
        assert nested["q"]["code"] == "sz000001"
        assert nested["q"]["price"] == 10.0


class TestHkCli:
    def test_hk_quote_found(self, capsys):
        from main import hk_quote

        q = HkQuote(
            code="00700", name="腾讯", price=445.2, pre_close=433.0,
            open=442.4, high=446.6, low=440.0, volume=1, amount=1.0,
            change_pct=2.82, change_amt=12.2, turnover_pct=0.0, time="t",
        )
        c = MagicMock()
        c.quote.return_value = q
        hk_quote(c, MagicMock(code="00700"))
        out = json.loads(capsys.readouterr().out)
        assert out["code"] == "00700"
        assert out["price"] == 445.2

    def test_hk_quote_missing(self, capsys):
        from main import hk_quote

        c = MagicMock()
        c.quote.return_value = None
        hk_quote(c, MagicMock(code="99999"))
        out = json.loads(capsys.readouterr().out)
        assert out["error"] == "未找到数据"

    def test_hk_quote_batch_serializes_dataclass(self, capsys):
        from main import hk_quote_batch

        q = HkQuote(
            code="00700", name="腾讯", price=445.2, pre_close=433.0,
            open=442.4, high=446.6, low=440.0, volume=1, amount=1.0,
            change_pct=2.82, change_amt=12.2, turnover_pct=0.0, time="t",
        )
        c = MagicMock()
        c.quote_batch.return_value = {"hk00700": q}
        hk_quote_batch(c, MagicMock(codes="00700"))
        out = json.loads(capsys.readouterr().out)
        assert out["hk00700"]["code"] == "00700"
        assert isinstance(out["hk00700"], dict)


class TestBatchHelpers:
    def test_load_codes_from_string(self):
        from batch import _load_codes

        assert _load_codes("00700, 09988") == ["00700", "09988"]
        assert _load_codes("") == []
        assert _load_codes(None) == []

    def test_load_codes_from_file(self, tmp_path):
        from batch import _load_codes

        p = tmp_path / "codes.txt"
        p.write_text("00700\n09988\n\n", encoding="utf-8")
        assert _load_codes(str(p)) == ["00700", "09988"]

    def test_save_hk_json(self, tmp_path, capsys):
        from batch import _save_hk_json

        q = HkQuote(
            code="00700", name="腾讯", price=445.2, pre_close=433.0,
            open=442.4, high=446.6, low=440.0, volume=1, amount=1.0,
            change_pct=2.82, change_amt=12.2, turnover_pct=0.0, time="t",
        )
        _save_hk_json({"hk00700": q}, str(tmp_path))
        data = json.loads((tmp_path / "hk_results.json").read_text(encoding="utf-8"))
        assert data[0]["code"] == "00700"
        assert "已保存 1 条港股行情" in capsys.readouterr().out

    def test_cmd_hk_quote_empty(self, capsys):
        from batch import cmd_hk_quote

        cmd_hk_quote(MagicMock(codes=""))
        assert "代码列表为空" in capsys.readouterr().out

    def test_cmd_hk_quote_json(self, tmp_path, capsys):
        from batch import cmd_hk_quote

        q = HkQuote(
            code="00700", name="腾讯", price=445.2, pre_close=433.0,
            open=442.4, high=446.6, low=440.0, volume=1, amount=1.0,
            change_pct=2.82, change_amt=12.2, turnover_pct=0.0, time="t",
        )
        args = MagicMock(codes="00700", output=str(tmp_path), format="json")
        with patch("batch.HkClient") as cls:
            cls.return_value.quote_batch.return_value = {"hk00700": q}
            cmd_hk_quote(args)
        assert (tmp_path / "hk_results.json").exists()

    def test_cmd_futures_quote_json(self, tmp_path, capsys):
        from batch import cmd_futures_quote

        q = Quote(code="IFL0", price=3800.0, pre_close=3790.0, volume=100)
        client = MagicMock()
        client.quote_batch.return_value = [q]
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        args = MagicMock(
            market=47, start=0, count=1, timeout=1,
            output=str(tmp_path), format="json",
        )
        with patch("batch.FuturesClient", return_value=client):
            cmd_futures_quote(args)
        data = json.loads((tmp_path / "futures_results.json").read_text(encoding="utf-8"))
        assert data[0]["code"] == "IFL0"
        assert data[0]["pre_close"] == 3790.0
        assert "vol" not in data[0]


class TestCliHelpers:
    def test_parse_market_aliases(self):
        from main import _parse_market

        assert _parse_market("sz") == 0
        assert _parse_market("SH") == 1
        assert _parse_market("bj") == 2
        assert _parse_market(47) == 47

    def test_parse_codes_and_category(self):
        from main import _parse_codes, _parse_category, _code6, _code_market, _us_code

        assert _parse_codes("sz000001, sh600000") == ["sz000001", "sh600000"]
        assert _parse_codes("") == []
        assert _parse_category("a") == 6
        assert _parse_category("kcb") == 8
        assert _code6("sz000001") == "000001"
        assert _code_market("sh600000") == 1
        assert _code_market("sz000001") == 0
        assert _us_code("AAPL") == "AAPL"
        assert _us_code("usAAPL") == "AAPL"
        assert _us_code("USB") == "USB"


class TestParserCoverage:
    def test_stock_and_futures_commands_exist(self):
        from main import build_parser, STOCK_HANDLERS, FUTURES_HANDLERS

        p = build_parser()
        stock = p.parse_args(["stock", "kline-120m", "sz000001", "--count", "10"])
        assert stock.proto == "stock" and stock.cmd == "kline-120m"
        fut = p.parse_args(["futures", "kline-range", "IFL0", "--start-date", "20260101"])
        assert fut.cmd == "kline-range"
        info = p.parse_args(["info", "news", "sz000001"])
        assert info.proto == "info" and info.cmd == "news"
        assert "capital-flow" in STOCK_HANDLERS
        assert "main-contract" in FUTURES_HANDLERS
        us = p.parse_args(["us", "quote", "AAPL"])
        assert us.proto == "us" and us.cmd == "quote" and us.market == 74
        us_k = p.parse_args(["us", "kline", "usAAPL", "--period", "day"])
        assert us_k.cmd == "kline" and us_k.code == "usAAPL"

    def test_info_cninfo_ccpm_mac_commands(self):
        from main import build_parser, INFO_HANDLERS, CNINFO_HANDLERS, CCPM_HANDLERS, MAC_HANDLERS

        p = build_parser()
        assert p.parse_args(["cninfo", "search", "000001"]).cmd == "search"
        assert p.parse_args(["ccpm", "latest", "IF"]).cmd == "latest"
        assert p.parse_args(["mac", "board-list"]).cmd == "board-list"
        assert "snapshot" in INFO_HANDLERS
        assert "batch" in CNINFO_HANDLERS
        assert "meta" in CCPM_HANDLERS
        assert "capital-flow" in MAC_HANDLERS


class TestNewHandlers:
    def test_stock_kline_120m(self, capsys):
        from main import stock_kline_120m

        c = MagicMock()
        c.kline_120m.return_value = [{"time": 1, "close": 10.0}]
        stock_kline_120m(c, MagicMock(code="sz000001", start=0, count=10))
        out = json.loads(capsys.readouterr().out)
        assert out[0]["close"] == 10.0
        c.kline_120m.assert_called_once_with("sz000001", 0, 10)

    def test_stock_quotes_detail(self, capsys):
        from main import stock_quotes_detail

        c = MagicMock()
        c.quotes_detail.return_value = {"sz000001": {"price": 10.5}}
        stock_quotes_detail(c, MagicMock(codes="sz000001,sh600000"))
        out = json.loads(capsys.readouterr().out)
        assert out["sz000001"]["price"] == 10.5
        c.quotes_detail.assert_called_once_with(["sz000001", "sh600000"])

    def test_stock_market_stat(self, capsys):
        from main import stock_market_stat

        c = MagicMock()
        c.market_stat.return_value = {"up_count": 1200, "down_count": 800}
        stock_market_stat(c, MagicMock())
        out = json.loads(capsys.readouterr().out)
        assert out["up_count"] == 1200

    def test_fut_kline_range_and_main_contract(self, capsys):
        from main import fut_kline_range, fut_main_contract

        c = MagicMock()
        c.kline_range.return_value = [{"close": 3800}]
        fut_kline_range(c, MagicMock(market=47, code="IFL0", period="day", start_date="20260101", end_date="20260301"))
        out = json.loads(capsys.readouterr().out)
        assert out[0]["close"] == 3800

        c.get_main_contract.return_value = "IF2506"
        fut_main_contract(c, MagicMock(product="IF", lookahead=3, market=47))
        out = json.loads(capsys.readouterr().out)
        assert out["code"] == "IF2506"

    def test_us_quote_and_kline(self, capsys):
        from main import us_quote, us_kline, us_minute, us_trade

        c = MagicMock()
        c.quote.return_value = Quote(code="AAPL", price=180.0, pre_close=179.0, volume=100)
        us_quote(c, MagicMock(market=74, code="usAAPL"))
        out = json.loads(capsys.readouterr().out)
        assert out["code"] == "AAPL"
        assert out["pre_close"] == 179.0
        c.quote.assert_called_once_with(74, "AAPL")

        c.kline.return_value = [{"close": 180.5}]
        us_kline(c, MagicMock(market=74, code="AAPL", period="day", start=0, count=10))
        out = json.loads(capsys.readouterr().out)
        assert out[0]["close"] == 180.5
        c.kline.assert_called_once_with(74, "AAPL", "day", 0, 10)

        c.today_minute.return_value = [{"time": "0930", "price": 180.0}]
        us_minute(c, MagicMock(market=74, code="AAPL", date=None))
        out = json.loads(capsys.readouterr().out)
        assert out[0]["price"] == 180.0

        c.today_trade.return_value = [{"time": "0930", "volume": 10}]
        us_trade(c, MagicMock(market=74, code="AAPL", date=None, start=0, count=100))
        out = json.loads(capsys.readouterr().out)
        assert out[0]["volume"] == 10

    def test_info_news_and_cninfo_search(self, capsys):
        from main import info_news, cninfo_search
        from tdxproto.info.models import NewsItem

        c = MagicMock()
        c.news.return_value = [NewsItem("2026-01-01", "t", "src", "1", "id")]
        info_news(c, MagicMock(code="sz000001", market=None))
        out = json.loads(capsys.readouterr().out)
        assert out[0]["title"] == "t"
        c.news.assert_called_once_with(0, "000001")

        c.search.return_value = [{"title": "年报", "code": "000001"}]
        cninfo_search(c, MagicMock(code="000001", count=5, page=1, keyword="", category="", plate="", se_date=""))
        out = json.loads(capsys.readouterr().out)
        assert out[0]["title"] == "年报"

    def test_ccpm_latest(self, capsys):
        from main import ccpm_latest

        c = MagicMock()
        c.latest_rank.return_value = {"product": "IF", "date": "2026-01-01"}
        ccpm_latest(c, MagicMock(product="IF"))
        out = json.loads(capsys.readouterr().out)
        assert out["product"] == "IF"

    def test_main_dispatches_info(self, capsys):
        from main import main
        from tdxproto.info.models import NewsItem

        client = MagicMock()
        client.news.return_value = [NewsItem("d", "n", "s", "r", "i")]
        with patch("main.InfoClient", return_value=client):
            main(["info", "news", "sz000001"])
        out = json.loads(capsys.readouterr().out)
        assert out[0]["title"] == "n"
