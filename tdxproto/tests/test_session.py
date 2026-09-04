"""交易时段与分时锚定单元测试。"""
from datetime import datetime, date

from tdxproto.session import (
    ashare_minute_labels,
    filter_minute_placeholders,
    in_auction,
    in_trading,
    last_session_date,
    prev_weekday,
    session_status,
    should_use_realtime_minute,
    stamp_minute_times,
)
from tdxproto.stock.commands import is_index_code


class TestSession:
    def test_weekday_labels(self):
        labels = ashare_minute_labels()
        assert len(labels) == 240
        assert labels[0] == "09:31"
        assert labels[119] == "11:30"
        assert labels[120] == "13:01"
        assert labels[-1] == "15:00"

    def test_in_trading_morning(self):
        now = datetime(2026, 9, 3, 10, 0)
        assert in_trading(now) is True
        assert session_status(now) == "morning"

    def test_in_trading_lunch(self):
        now = datetime(2026, 9, 3, 12, 0)
        assert in_trading(now) is False
        assert session_status(now) == "lunch"

    def test_pre_market_and_auction(self):
        assert session_status(datetime(2026, 9, 3, 8, 0)) == "pre_market"
        assert in_auction(datetime(2026, 9, 3, 9, 20)) is True
        assert should_use_realtime_minute(datetime(2026, 9, 3, 9, 20)) is False
        assert should_use_realtime_minute(datetime(2026, 9, 3, 9, 30)) is True

    def test_weekend(self):
        sat = datetime(2026, 9, 5, 10, 0)
        assert in_trading(sat) is False
        assert session_status(sat) == "weekend"
        assert should_use_realtime_minute(sat) is False
        assert last_session_date(sat) == date(2026, 9, 4)

    def test_last_session_pre_open(self):
        now = datetime(2026, 9, 3, 8, 0)
        assert last_session_date(now) == date(2026, 9, 2)

    def test_prev_weekday_monday(self):
        assert prev_weekday(date(2026, 9, 7)) == date(2026, 9, 4)

    def test_closed_after_1500(self):
        now = datetime(2026, 9, 3, 15, 30)
        assert session_status(now) == "closed"
        assert should_use_realtime_minute(now) is True


class TestMinutePlaceholders:
    def test_strip_leading_and_trailing_zeros(self):
        rows = [
            {"price": 0.0, "vol": 0},
            {"price": 10.1, "vol": 100},
            {"price": 10.2, "vol": 80},
            {"price": 0.0, "vol": 0},
        ]
        out = filter_minute_placeholders(rows)
        assert len(out) == 2
        assert out[0]["price"] == 10.1
        assert out[-1]["price"] == 10.2

    def test_all_zero(self):
        assert filter_minute_placeholders([{"price": 0}, {"price": 0}]) == []

    def test_stamp_times(self):
        rows = [{"price": 1.0}, {"price": 2.0}]
        out = stamp_minute_times(rows)
        assert out[0]["minute"] == "09:31"
        assert out[1]["minute"] == "09:32"


class TestIndexCode:
    def test_sh_index(self):
        assert is_index_code("sh000001") is True
        assert is_index_code("sh000001", 1) is True

    def test_sz_stock_not_index(self):
        assert is_index_code("sz000001") is False
        assert is_index_code("sz000001", 0) is False

    def test_sz_index(self):
        assert is_index_code("sz399001") is True

    def test_board_index(self):
        assert is_index_code("sh880001", 1) is True

    def test_plain_stock(self):
        assert is_index_code("sh600000") is False
        assert is_index_code(None) is False
