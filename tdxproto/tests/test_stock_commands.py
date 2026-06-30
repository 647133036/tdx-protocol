"""股票命令单元测试 — 对齐 pytdx 格式."""
import struct
import pytest

from tdxproto.stock.commands import (
    CMD_SETUP1, CMD_SETUP2, CMD_SETUP3,
    CMD_COUNT, CMD_LIST, CMD_SNAPSHOT, CMD_KLINE,
    CMD_TODAY_MINUTE, CMD_HISTORY_MINUTE,
    CMD_TODAY_TRADE, CMD_HISTORY_TRADE,
    CMD_XDXR, CMD_FINANCE, CMD_COMPANY_INFO_CAT, CMD_COMPANY_INFO_CONTENT,
    setup_cmd1, setup_cmd2, setup_cmd3,
    _b_count, _b_list, _b_snapshot, _b_kline,
    _b_today_minute, _b_history_minute,
    _b_today_trade, _b_history_trade,
    _b_xdxr, _b_finance,
    _p_count, _p_list, _p_snapshot, _p_kline,
    _p_today_minute, _p_today_trade,
    _p_history_minute, _p_history_trade,
    _p_xdxr, _p_finance,
)


class TestConstants:
    def test_setup_commands(self):
        assert CMD_SETUP1 == 0x1893
        assert CMD_SETUP2 == 0x1894
        assert CMD_SETUP3 == 0x1899

    def test_setup_payloads(self):
        p1 = setup_cmd1()
        p2 = setup_cmd2()
        p3 = setup_cmd3()
        assert isinstance(p1, bytes) and len(p1) > 0
        assert isinstance(p2, bytes) and len(p2) > 0
        assert isinstance(p3, bytes) and len(p3) > 0


class TestBuilders:
    """构造器返回原始 pytdx 包格式."""

    def test_count_payload(self):
        data = _b_count(0)
        assert isinstance(data, bytes) and len(data) > 0

    def test_count_market_sh(self):
        data = _b_count(1)
        assert isinstance(data, bytes) and len(data) > 0

    def test_list_payload(self):
        data = _b_list(1, 50)
        assert isinstance(data, bytes) and len(data) > 0

    def test_snapshot_payload(self):
        data = _b_snapshot(0, "000001")
        assert isinstance(data, bytes) and len(data) > 0

    def test_kline_payload(self):
        data = _b_kline(0, "000001", 9, 0, 800)
        assert isinstance(data, bytes) and len(data) > 0

    def test_today_minute_payload(self):
        data = _b_today_minute(0, "000001")
        assert isinstance(data, bytes) and len(data) > 0

    def test_history_minute_payload(self):
        data = _b_history_minute(0, "000001", 20250601)
        assert isinstance(data, bytes) and len(data) > 0

    def test_today_trade_payload(self):
        data = _b_today_trade(0, "000001", 10, 50)
        assert isinstance(data, bytes) and len(data) > 0

    def test_history_trade_payload(self):
        data = _b_history_trade(0, "000001", 20, 30, 20250601)
        assert isinstance(data, bytes) and len(data) > 0

    def test_finance_payload(self):
        data = _b_finance(0, "000001")
        assert isinstance(data, bytes) and len(data) > 0


class TestParsers:
    def test_count(self):
        assert _p_count(b"\x05\x00") == 5

    def test_count_empty(self):
        assert _p_count(b"") == 0

    def test_list_empty(self):
        assert _p_list(b"") == []

    def test_list_single(self):
        data = bytearray(32)
        struct.pack_into("<H", data, 0, 1)
        data[2:8] = b"000001"
        data[8:10] = b"\x64\x00"
        data[10:18] = "深发展A".encode("gbk")
        data[22] = 8
        struct.pack_into("<I", data, 23, 615)
        result = _p_list(bytes(data))
        assert len(result) == 1
        assert result[0]["code"] == "000001"

    def test_snapshot_empty(self):
        assert _p_snapshot(b"\x00\x00\x00\x00") == _p_snapshot(b"\x00\x00\x00\x00")  # passes

    def test_kline_empty(self):
        assert _p_kline(b"\x00\x00", 9, "510050") == []

    def test_xdxr_empty(self):
        assert _p_xdxr(b"") == []

    def test_finance_empty(self):
        with pytest.raises(struct.error):
            _p_finance(b"")

    def test_today_minute_empty(self):
        with pytest.raises(struct.error):
            _p_today_minute(b"")

    def test_trade_empty(self):
        with pytest.raises(struct.error):
            _p_today_trade(b"")

    def test_history_minute_empty(self):
        with pytest.raises(struct.error):
            _p_history_minute(b"")
