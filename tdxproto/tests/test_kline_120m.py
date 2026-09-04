"""kline_120m 与 kline_with_derived 组件测试。"""
from unittest.mock import patch

from tdxproto.models import Kline, Minute
from tdxproto.stock.client import StockClient
from datetime import datetime, date


def _bar(time_str, o, h, l, c, vol=1, amt=10.0):
    return Kline(time=time_str, open=o, high=h, low=l, close=c, volume=vol, amount=amt)


class TestKlineDatetime:
    def test_datetime_alias(self):
        k = Kline(time="202609011130", open=1)
        assert k.datetime == "202609011130"


class TestKline120m:
    def test_pair_aggregate(self):
        client = StockClient(timeout=1, auto_reconnect=False)
        bars = [
            _bar("202609011030", 10, 11, 9, 10.5, 1, 10),
            _bar("202609011130", 10.5, 12, 10, 11, 2, 20),
            _bar("202609011330", 11, 13, 10.5, 12, 3, 30),
            _bar("202609011430", 12, 14, 11, 13, 4, 40),
        ]
        with patch.object(client, "kline", return_value=bars):
            result = client.kline_120m("sz000001", count=10)
        assert len(result) == 2
        assert result[0].time == "202609011130"
        assert result[0].open == 10
        assert result[0].high == 12
        assert result[0].low == 9
        assert result[0].close == 11
        assert result[0].volume == 3
        assert result[0].amount == 30
        assert result[1].time == "202609011430"
        assert result[1].open == 11
        assert result[1].close == 13

    def test_odd_drops_oldest(self):
        client = StockClient(timeout=1, auto_reconnect=False)
        bars = [
            _bar("202609011030", 10, 11, 9, 10.5),
            _bar("202609011130", 10.5, 12, 10, 11),
            _bar("202609011330", 11, 13, 10.5, 12),
        ]
        with patch.object(client, "kline", return_value=bars):
            result = client.kline_120m("sz000001")
        assert len(result) == 1
        assert result[0].time == "202609011330"
        assert result[0].open == 10.5
        assert result[0].close == 12

    def test_too_short(self):
        client = StockClient(timeout=1, auto_reconnect=False)
        with patch.object(client, "kline", return_value=[_bar("202609011030", 10, 11, 9, 10)]):
            assert client.kline_120m("sz000001") == []


class TestKlineWithDerived:
    def test_derived_fields(self):
        client = StockClient(timeout=1, auto_reconnect=False)
        bars = [
            _bar("20260901", 10, 11, 9, 10.5),
            _bar("20260902", 10.5, 12, 10, 11),
        ]
        with patch.object(client, "kline", return_value=bars):
            rows = client.kline_with_derived("sz000001", "day", 0, 2)
        assert rows[0]["pre_close"] == 10
        assert rows[0]["datetime"] == "20260901"
        assert rows[1]["pre_close"] == 10.5
        assert rows[1]["change"] == 0.5


class TestTodayMinuteAnchor:
    def test_pre_market_uses_history(self):
        client = StockClient(timeout=1, auto_reconnect=False)
        now = datetime(2026, 9, 3, 8, 0)
        hist = [Minute(time="09:31", price=10.0, volume=100)]
        with patch.object(client, "history_minute", return_value=hist) as mock_h:
            with patch.object(client, "_send_recv") as mock_send:
                result = client.today_minute("sz000001", now=now)
        mock_send.assert_not_called()
        mock_h.assert_called()
        assert mock_h.call_args[0][1] == date(2026, 9, 2)
        assert result == hist

    def test_weekend_uses_friday(self):
        client = StockClient(timeout=1, auto_reconnect=False)
        now = datetime(2026, 9, 5, 10, 0)
        hist = [Minute(time="09:31", price=11.0, volume=50)]
        with patch.object(client, "history_minute", return_value=hist) as mock_h:
            result = client.today_minute("sz000001", now=now)
        assert mock_h.call_args[0][1] == date(2026, 9, 4)
        assert result == hist

    def test_trading_hours_uses_realtime(self):
        client = StockClient(timeout=1, auto_reconnect=False)
        now = datetime(2026, 9, 3, 10, 0)
        packet = __import__("struct").pack("<H", 1) + b"\x00\x00\x00" + b"000001"
        packet += b"\x0a\x00\x64"
        with patch.object(client, "_send_recv", return_value=packet):
            with patch.object(client, "_get_coefficient", return_value=0.01):
                with patch.object(client, "history_minute") as mock_h:
                    result = client.today_minute("sz000001", now=now)
        mock_h.assert_not_called()
        assert len(result) == 1
        assert result[0].price == 0.10
        assert result[0].time == "09:31"

    def test_realtime_empty_falls_back(self):
        client = StockClient(timeout=1, auto_reconnect=False)
        now = datetime(2026, 9, 3, 10, 0)
        hist = [Minute(time="09:31", price=9.9, volume=1)]
        with patch.object(client, "_send_recv", return_value=b"\x00\x00"):
            with patch.object(client, "history_minute", return_value=hist):
                result = client.today_minute("sz000001", now=now)
        assert result == hist
