"""系统测试：连接真实通达信服务器端到端验证."""
import pytest

from tdxproto.stock.client import StockClient
from tdxproto.futures.client import FuturesClient


@pytest.mark.system
class TestStockSystem:
    def test_count(self):
        with StockClient() as c:
            count = c.count(1)
            assert count > 0

    def test_list(self):
        with StockClient() as c:
            stocks = c.list(1, 0, 10)
            assert len(stocks) > 0
            assert "code" in stocks[0]

    def test_quote(self):
        with StockClient() as c:
            results = c.quote("000001")
            assert len(results) > 0

    def test_kline(self):
        with StockClient() as c:
            bars = c.kline("000001", "day", 0, 5)
            assert len(bars) > 0

    def test_today_minute(self):
        with StockClient() as c:
            pts = c.today_minute("000001")
            assert isinstance(pts, list)

    def test_today_trade(self):
        with StockClient() as c:
            ticks = c.today_trade("000001", 0, 5)
            assert isinstance(ticks, list)


@pytest.mark.system
class TestFuturesSystem:
    def test_markets(self):
        with FuturesClient() as c:
            mk = c.markets()
            assert len(mk) > 0

    def test_codes(self):
        with FuturesClient() as c:
            codes = c.codes_all(47)
            assert len(codes) > 0
            assert all(r["market_id"] == 47 for r in codes)

    def test_quote(self):
        with FuturesClient() as c:
            q = c.quote(47, "IF2607")
            assert q.code == "IF2607"
            assert q.price != 0

    def test_batch_quote(self):
        with FuturesClient() as c:
            batch = c.quote_batch(47, 0, 5)
            assert len(batch) > 0

    def test_kline(self):
        with FuturesClient() as c:
            bars = c.kline(47, "IF2607", "day", 0, 5)
            assert len(bars) > 0

    def test_kline_range(self):
        with FuturesClient() as c:
            bars = c.kline_range(47, "IF2607", "1m", 20260625, 20260629)
            assert len(bars) > 0

    def test_today_minute(self):
        with FuturesClient() as c:
            pts = c.today_minute(47, "IF2607")
            assert len(pts) > 0

    def test_today_trade(self):
        with FuturesClient() as c:
            ticks = c.today_trade(47, "IF2607", 0, 5)
            assert isinstance(ticks, list)
