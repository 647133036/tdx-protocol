import pytest

from tdxproto.compute import (
    compute_factors, get_equity_at, calc_turnover,
    parse_xdxr, auction_0925,
)
from tdxproto.models import Kline, EquityChange, Trade
from datetime import date


class TestComputeFactors:
    def test_no_equity(self):
        bars = [Kline(time="20250101", close=10.0)]
        result = compute_factors(bars, [])
        assert result == {}

    def test_no_bars(self):
        eq = [EquityChange(date=date(2025, 1, 1), category=1, bonus=0.5)]
        result = compute_factors([], eq)
        assert result == {}

    def test_dividend_event(self):
        bars = [
            Kline(time="20241231", close=10.0),
            Kline(time="20250101", close=10.5),
        ]
        eq = [
            EquityChange(date=date(2025, 1, 1), category=1,
                        bonus=0.5, rights=0.3, placement=0.1, placement_price=8.0)
        ]
        result = compute_factors(bars, eq, "qfq")
        assert date(2025, 1, 1) in result
        assert isinstance(result[date(2025, 1, 1)], float)

    def test_hfq_adjust(self):
        bars = [Kline(time="20250101", close=10.0)]
        eq = [
            EquityChange(date=date(2025, 1, 1), category=1,
                        bonus=1.0)
        ]
        result = compute_factors(bars, eq, "hfq")
        assert date(2025, 1, 1) in result


class TestGetEquityAt:
    def test_no_equity(self):
        result = get_equity_at([], date(2025, 1, 1))
        assert result == (0.0, 0.0)

    def test_before_any_change(self):
        eq = [
            EquityChange(date=date(2025, 6, 1), float_shares=1000.0, total_shares=5000.0)
        ]
        result = get_equity_at(eq, date(2025, 1, 1))
        assert result == (0.0, 0.0)

    def test_after_change(self):
        eq = [
            EquityChange(date=date(2025, 1, 1), float_shares=1000.0, total_shares=5000.0)
        ]
        result = get_equity_at(eq, date(2025, 6, 1))
        assert result == (1000.0, 5000.0)

    def test_multiple_changes(self):
        eq = [
            EquityChange(date=date(2025, 1, 1), float_shares=1000.0, total_shares=5000.0),
            EquityChange(date=date(2025, 6, 1), float_shares=2000.0, total_shares=8000.0),
        ]
        result = get_equity_at(eq, date(2025, 7, 1))
        assert result == (2000.0, 8000.0)


class TestCalcTurnover:
    def test_zero_float(self):
        assert calc_turnover(1000, 0.0) == 0.0

    def test_negative_float(self):
        assert calc_turnover(1000, -100.0) == 0.0

    def test_normal_case(self):
        # volume=100万股, float=1000万股
        # turnover = 1000000 / (1000 * 10000) * 100 = 10%
        result = calc_turnover(1000000, 1000.0)
        assert abs(result - 10.0) < 0.1

    def test_100_percent(self):
        # volume=float (all shares traded)
        # turnover = 100000000 / (10000 * 10000) * 100 = 100%
        result = calc_turnover(100000000, 10000.0)
        assert abs(result - 100.0) < 0.1


class TestParseXdXr:
    def test_no_events(self):
        eq = [EquityChange(date=date(2025, 1, 1), category=5)]
        result = parse_xdxr(eq)
        assert result == []

    def test_dividend_event(self):
        eq = [
            EquityChange(date=date(2025, 1, 1), category=1,
                        bonus=0.5, rights=0.3, placement=0.1, placement_price=8.0
            )
        ]
        result = parse_xdxr(eq)
        assert len(result) == 1
        assert result[0]["date"] == "2025-01-01"
        assert result[0]["bonus_per_share"] == 0.5

    def test_non_dividend_category(self):
        eq = [
            EquityChange(date=date(2025, 1, 1), category=5),
            EquityChange(date=date(2025, 6, 1), category=5),
        ]
        result = parse_xdxr(eq)
        assert result == []


class TestAuction0925:
    def test_no_auction(self):
        trades = [
            Trade(time="09:30", price=10.0, volume=100),
            Trade(time="10:00", price=10.5, volume=200),
        ]
        result = auction_0925(trades)
        assert result is None

    def test_found_auction(self):
        trades = [
            Trade(time="09:25", price=10.0, volume=5000, direction="B"),
            Trade(time="09:30", price=10.1, volume=100),
        ]
        result = auction_0925(trades)
        assert result is not None
        assert result["price"] == 10.0
        assert result["volume"] == 5000

    def test_empty_trades(self):
        result = auction_0925([])
        assert result is None
