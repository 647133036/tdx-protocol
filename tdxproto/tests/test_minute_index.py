"""指数分时自适应解析单元测试。"""
import struct

from tdxproto.stock.commands import _p_today_minute, _p_history_minute


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


class TestTodayMinuteIndex:
    def test_stock_stride3_unchanged(self):
        num = 2
        data = bytearray()
        data.extend(struct.pack("<H", num))
        data.extend(b"\x00\x00")
        data.extend(b"\x00")
        data.extend(b"000001")
        for price_diff, vol in [(10, 100), (5, 50)]:
            data.extend(ev(price_diff))
            data.extend(ev(0))
            data.extend(ev(vol))
        result = _p_today_minute(bytes(data), 0.01, is_idx=False)
        assert len(result) == 2
        assert result[0]["price"] == 0.10
        assert result[1]["price"] == 0.15

    def test_index_prefers_stride4_when_better(self):
        num = 2
        data = bytearray()
        data.extend(struct.pack("<H", num))
        data.extend(b"\x00\x00")
        data.extend(b"\x00")
        data.extend(b"000001")
        for price_diff, extra, vol in [(1000, 0, 10), (20, 0, 20)]:
            data.extend(ev(price_diff))
            data.extend(ev(0))
            data.extend(ev(vol))
            data.extend(ev(extra))
        result = _p_today_minute(bytes(data), 0.01, is_idx=True)
        assert len(result) == 2
        assert result[0]["price"] == 10.0
        assert abs(result[1]["price"] - 10.20) < 1e-9


class TestHistoryMinuteIndex:
    def test_stock_no_extra(self):
        num = 2
        data = bytearray()
        data.extend(struct.pack("<H", num))
        data.extend(b"\x00" * 4)
        for price_diff, vol in [(10, 500), (20, 300)]:
            data.extend(ev(price_diff))
            data.extend(ev(0))
            data.extend(ev(vol))
        result = _p_history_minute(bytes(data), 0.01, is_idx=False)
        assert len(result) == 2
        assert result[0]["price"] == 0.10
        assert result[1]["price"] == 0.30

    def test_index_skips_extra_4_bytes(self):
        num = 2
        data = bytearray()
        data.extend(struct.pack("<H", num))
        data.extend(b"\x00" * 4)
        for price_diff, vol in [(100, 10), (50, 20)]:
            data.extend(ev(price_diff))
            data.extend(ev(0))
            data.extend(ev(vol))
            data.extend(b"\x00\x00\x00\x00")
        result = _p_history_minute(bytes(data), 0.01, is_idx=True)
        assert len(result) == 2
        assert result[0]["price"] == 1.00
        assert result[1]["price"] == 1.50
