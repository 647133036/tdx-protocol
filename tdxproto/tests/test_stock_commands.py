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
    _get_datetime,
)
from tdxproto.codec import get_price, decode_volume


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

    def test_kline_format(self):
        """验证 _b_kline 格式: 12B header + 26B payload = 38B."""
        data = _b_kline(1, "600000", 9, 100, 5)
        assert len(data) == 38, f"expected 38B, got {len(data)}B"

        hdr_type, hdr_counter, hdr_zip, hdr_unzip, hdr_cmd = \
            struct.unpack("<HIHHH", data[:12])
        assert hdr_type == 0x10C
        assert hdr_cmd == 0x052D
        assert hdr_zip == 0x1C
        assert hdr_unzip == 0x1C

        payload = data[12:]
        assert len(payload) == 26
        mrk, cod, cat, one, stt, cnt, t1, t2, t3 = \
            struct.unpack("<H6sHHHHIIH", payload)
        assert mrk == 1
        assert cod == b"600000"
        assert cat == 9
        assert one == 1
        assert stt == 100
        assert cnt == 5
        assert t1 == t2 == t3 == 0

    def test_kline_payload_has_trailing_zeros(self):
        """kline payload 尾部 10 字节零 (I+I+H) 是协议要求, 不可删除."""
        data = _b_kline(0, "000001", 9, 0, 800)
        assert len(data) == 38
        payload = data[12:]
        assert len(payload) == 26
        assert struct.calcsize("<H6sHHHHIIH") == 26
        t1, t2, t3 = struct.unpack_from("<IIH", payload, 16)
        assert t1 == t2 == t3 == 0

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

    def test_kline_parse_daily(self):
        """分类=9 (日线): datetime 4B(I)+OHLC 4xvarint+vol 4B+amt 4B=~20B/bar."""
        def ev(val):
            if val == 0:
                return b"\x00"
            sign = 0x40 if val < 0 else 0
            av = abs(val)
            fb = (av & 0x3F) | sign
            av >>= 6
            if av == 0:
                return bytes([fb])
            r = bytearray([fb | 0x80])
            while av:
                r.append((av & 0x7F) | (0x80 if (av >> 7) else 0))
                av >>= 7
            return bytes(r)

        def encode_vol(v: float) -> int:
            return struct.unpack("<I", struct.pack("<f", v))[0]

        bars_data = bytearray()
        pre_diff = 0
        test_bars = [
            (20250110, 10.00, 10.50, 11.00, 9.80, 1000000, 10500000),
            (20250111, 10.50, 10.30, 10.80, 10.10, 800000, 8200000),
        ]
        for dt, op, cl, hi, lo, vl, am in test_bars:
            bars_data.extend(struct.pack("<I", dt))
            po = int(op * 1000) - pre_diff
            pc = int((cl - op) * 1000)
            ph = int((hi - op) * 1000)
            pl = int((lo - op) * 1000)
            bars_data.extend(ev(po))
            bars_data.extend(ev(pc))
            bars_data.extend(ev(ph))
            bars_data.extend(ev(pl))
            bars_data.extend(struct.pack("<I", encode_vol(vl)))
            bars_data.extend(struct.pack("<I", encode_vol(am)))
            pre_diff = po + pc

        count = len(test_bars)
        resp = struct.pack("<H", count) + bytes(bars_data)

        result = _p_kline(resp, 9, "600000", 0.01)
        assert len(result) == 2
        assert result[0]["open"] == pytest.approx(10.00, abs=0.001)
        assert result[0]["close"] == pytest.approx(10.50, abs=0.001)
        assert result[0]["high"] == pytest.approx(11.00, abs=0.001)
        assert result[0]["low"] == pytest.approx(9.80, abs=0.001)
        assert result[0]["vol"] == pytest.approx(1000000.0, abs=0.5)
        assert result[0]["year"] == 2025
        assert result[0]["month"] == 1
        assert result[0]["day"] == 10

        assert result[1]["open"] == pytest.approx(10.50, abs=0.001)
        assert result[1]["close"] == pytest.approx(10.30, abs=0.001)
        assert result[1]["high"] == pytest.approx(10.80, abs=0.001)
        assert result[1]["low"] == pytest.approx(10.10, abs=0.001)

    def test_xdxr_empty(self):
        assert _p_xdxr(b"") == []

    def test_finance_empty(self):
        with pytest.raises(struct.error):
            _p_finance(b"")

    def test_today_minute_empty(self):
        with pytest.raises(struct.error):
            _p_today_minute(b"")

    def test_today_minute_parse(self):
        """验证今日分时解析: 第一个varint是时间偏移(跳过), 第二个是价格差异."""
        def ev(val):
            if val == 0:
                return b"\x00"
            sign = 0x40 if val < 0 else 0
            av = abs(val)
            fb = (av & 0x3F) | sign
            av >>= 6
            if av == 0:
                return bytes([fb])
            r = bytearray([fb | 0x80])
            while av:
                r.append((av & 0x7F) | (0x80 if (av >> 7) else 0))
                av >>= 7
            return bytes(r)

        num = 3
        data = bytearray()
        # 响应头: count(2) + reserved(2) + market(1) + code(6)
        data.extend(struct.pack("<H", num))
        data.extend(b"\x00\x00")
        data.extend(b"\x00")
        data.extend(b"000001")
        bars = [
            (10, 0, 100),      # +10份, reversed=0, 100手
            (-3, 0, 50),       # -3份, reversed=0, 50手
            (7, 0, 200),       # +7份, reversed=0, 200手
        ]
        for price_diff, reversed1, vol in bars:
            data.extend(ev(price_diff))
            data.extend(ev(reversed1))
            data.extend(ev(vol))

        result = _p_today_minute(bytes(data), 0.01)
        assert len(result) == 3
        assert result[0]["price"] == 0.10
        assert result[0]["vol"] == 100
        assert result[1]["price"] == 0.07
        assert result[1]["vol"] == 50
        assert result[2]["price"] == 0.14
        assert result[2]["vol"] == 200

    def test_history_minute_parse(self):
        """验证历史分时解析: 第一个varint是时间偏移(跳过), 第二个是价格差异.
        响应格式: 2B count + 4B padding + bars."""
        def ev(val):
            if val == 0:
                return b"\x00"
            sign = 0x40 if val < 0 else 0
            av = abs(val)
            fb = (av & 0x3F) | sign
            av >>= 6
            if av == 0:
                return bytes([fb])
            r = bytearray([fb | 0x80])
            while av:
                r.append((av & 0x7F) | (0x80 if (av >> 7) else 0))
                av >>= 7
            return bytes(r)

        num = 2
        data = bytearray()
        data.extend(struct.pack("<H", num))
        data.extend(b"\x00" * 4)  # 4 bytes padding (pos+=6 from 0 = skip count(2) + padding(4))

        bars = [
            (10, 0, 500),   # price_diff=10, reversed=0, vol=500
            (20, 0, 300),   # price_diff=20, reversed=0, vol=300
        ]
        for price_diff, reversed1, vol in bars:
            data.extend(ev(price_diff))
            data.extend(ev(reversed1))
            data.extend(ev(vol))

        result = _p_history_minute(bytes(data), 0.01)
        assert len(result) == 2
        assert result[0]["price"] == 0.10
        assert result[0]["vol"] == 500
        assert result[1]["price"] == 0.30
        assert result[1]["vol"] == 300
