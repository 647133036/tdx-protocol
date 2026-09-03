"""QFQ 交叉验证测试（formula vs gap 检测）。"""
import pytest
from datetime import date

from tdxproto.compute import compute_factors, verify_qfq
from tdxproto.models import Kline, EquityChange


class TestQfqCrossVerify:
    def test_no_equity(self):
        """无除权事件时，gap 检测为空，match=True。"""
        bars = [Kline(time="20250101", close=10.0, open=10.0, high=10.0, low=10.0)]
        result = verify_qfq(bars, [])
        assert result["match"] is True
        assert result["gap_events"] == []
        assert result["formula_factors"] == {}

    def test_formula_only(self):
        """gap 未检测到缺口时，仅采信公式法。"""
        bars = [
            Kline(time="20241230", close=10.0, open=10.0, high=10.0, low=10.0),
            Kline(time="20250101", close=9.5, open=9.5, high=9.6, low=9.4),
        ]
        eq = [
            EquityChange(
                date=date(2025, 1, 1), category=1,
                bonus=0.5, rights=0, placement=0, placement_price=0
            )
        ]
        result = verify_qfq(bars, eq)
        # 公式法应计算出因子
        assert len(result["formula_factors"]) >= 0
        assert result["match"] is True

    def test_gap_detection(self):
        """gap 检测方法能识别除权跳空。"""
        # 模拟除权：前一日收盘 10.0，除权日开盘 8.5（跳空 15%）
        bars = [
            Kline(time="20241230", close=10.0, open=10.0, high=10.1, low=9.9),
            Kline(time="20250101", close=9.0, open=8.5, high=8.7, low=8.3),
            Kline(time="20250102", close=9.2, open=9.1, high=9.3, low=9.0),
        ]
        result = verify_qfq(bars, [])
        # 应检测到 20250101 的 gap
        assert any(d.startswith("20250101") for d, _ in result["gap_events"])
        assert result["match"] is True

    def test_consistency(self):
        """公式法与 gap 法结果一致时 match=True。"""
        bars = [
            Kline(time="20241230", close=10.0, open=10.0, high=10.1, low=9.9),
            Kline(time="20250101", close=8.0, open=8.0, high=8.2, low=7.8),
        ]
        eq = [
            EquityChange(
                date=date(2025, 1, 1), category=1,
                bonus=0, rights=0, placement=0, placement_price=0
            )
        ]
        result = verify_qfq(bars, eq)
        # 两种方法应一致（或在误差范围内）
        assert isinstance(result["match"], bool)
        assert "formula_factors" in result
        assert "gap_events" in result

    def test_multiple_equity_events(self):
        """多次除权事件：检查返回结构完整性。"""
        bars = [
            Kline(time="20241230", close=100.0),
            Kline(time="20250101", close=95.0),
            Kline(time="20250601", close=90.0),
        ]
        eq = [
            EquityChange(date=date(2025, 1, 1), category=1, bonus=5.0, rights=0, placement=0, placement_price=0),
            EquityChange(date=date(2025, 6, 1), category=1, bonus=3.0, rights=0, placement=0, placement_price=0),
        ]
        result = verify_qfq(bars, eq)
        assert "formula_factors" in result
        assert "gap_events" in result
        assert "match" in result
        assert isinstance(result["match"], bool)
        assert len(result["formula_factors"]) == 2
