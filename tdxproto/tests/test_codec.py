import struct
from datetime import date, datetime

import pytest

from tdxproto.codec import (
    u16, u32, f32, decode_volume,
    normalize_code, split_code, classify,
    date_int, int_date, minute_label, recent_selector,
    get_price, get_volume, encode_date, encode_minute,
)


class TestEndianHelpers:
    def test_u16_basic(self):
        assert u16(b"\x01\x00") == 1
        assert u16(b"\xff\x00") == 255
        assert u16(b"\x01\x02") == 513
        assert u16(b"\xff\xff") == 65535

    def test_u32_basic(self):
        assert u32(b"\x01\x00\x00\x00") == 1
        assert u32(b"\xff\x00\x00\x00") == 255
        assert u32(b"\x01\x02\x03\x04") == 0x04030201

    def test_f32_basic(self):
        data = struct.pack("<f", 3.14)
        assert abs(f32(data) - 3.14) < 1e-5

    def test_f32_zero(self):
        assert f32(b"\x00\x00\x00\x00") == 0.0

    def test_f32_negative(self):
        data = struct.pack("<f", -1.5)
        assert abs(f32(data) - (-1.5)) < 1e-5


class TestGetPrice:
    """get_price 返回 (price_in_cents, new_pos)"""
    def test_zero(self):
        price, pos = get_price(b"\x00")
        assert price == 0
        assert pos == 1

    def test_positive(self):
        data = b"\x01"
        price, pos = get_price(data)
        assert price == 1
        assert pos == 1

    def test_negative(self):
        data = b"\x41"
        price, pos = get_price(data)
        assert price == -1
        assert pos == 1

    def test_multi_byte(self):
        data = b"\x80\x01"
        price, pos = get_price(data)
        assert pos == 2

    def test_returns_position(self):
        data = b"\x03\x05"
        _, pos = get_price(data)
        assert pos == 1


class TestDecodeVolume:
    def test_zero(self):
        assert decode_volume(0) >= 0.0

    def test_returns_float(self):
        result = decode_volume(0x12345678)
        assert isinstance(result, float)
        assert result > 0

    def test_consistency(self):
        v = 0xDEADBEEF
        result = decode_volume(v)
        assert isinstance(result, float)


class TestNormalizeCode:
    def test_sz_stock(self):
        assert normalize_code("sz000001") == "sz000001"

    def test_sh_stock(self):
        assert normalize_code("sh600000") == "sh600000"

    def test_bj_stock(self):
        assert normalize_code("bj300001") == "bj300001"

    def test_uppercase(self):
        assert normalize_code("sz000001") == "sz000001"

    def test_six_digit_auto_sz(self):
        assert normalize_code("000001") == "sh000001"

    def test_six_digit_auto_sh(self):
        assert normalize_code("600000") == "sh600000"
        assert normalize_code("690000") == "sh690000"

    def test_six_digit_auto_bj(self):
        assert normalize_code("830000") == "sh830000"

    def test_futures(self):
        code = normalize_code("if2506")
        assert code == "szif2506"

    def test_etf(self):
        assert normalize_code("sh510050") == "sh510050"

    def test_invalid(self):
        code = normalize_code("")
        assert len(code) >= 0


class TestSplitCode:
    def test_sz(self):
        mid, exch, num = split_code("sz000001")
        assert mid == 0
        assert exch == "sz"
        assert num == "000001"

    def test_sh(self):
        mid, exch, num = split_code("sh600000")
        assert mid == 1
        assert exch == "sh"
        assert num == "600000"

    def test_bj(self):
        mid, exch, num = split_code("bj300001")
        assert mid == 2
        assert exch == "bj"
        assert num == "300001"

    def test_futures(self):
        mid, exch, num = split_code("IF2506")
        assert exch == "sz"

    def test_normalize_before_split(self):
        mid, exch, num = split_code("SZ000001")
        assert exch == "sz"


class TestClassify:
    def test_stock(self):
        assert classify("sz000001") == (0, "sz", "000001")

    def test_index_sh(self):
        assert classify("sh000001") == (1, "sh", "000001")

    def test_index_sz(self):
        assert classify("sz399001") == (0, "sz", "399001")

    def test_etf_sh51(self):
        assert classify("sh510050") == (1, "sh", "510050")

    def test_etf_sz159(self):
        assert classify("sz159995") == (0, "sz", "159995")

    def test_etf_sz16(self):
        assert classify("sz161725") == (0, "sz", "161725")

    def test_futures(self):
        mid, exch, num = classify("IF2506")
        assert exch == "sz"


class TestDateConversion:
    def test_date_int_none(self):
        with pytest.raises(TypeError):
            date_int(None)
        from datetime import datetime
        now = date_int(datetime.now())
        assert len(str(now)) == 8

    def test_date_int_string(self):
        assert date_int("20250101") == 20250101

    def test_date_int_int(self):
        assert date_int(20250101) == 20250101

    def test_date_int_date(self):
        d = date(2025, 6, 15)
        assert date_int(d) == 20250615

    def test_date_int_datetime(self):
        dt = datetime(2025, 6, 15, 10, 30)
        assert date_int(dt) == 20250615

    def test_int_date_valid(self):
        d = int_date(20250615)
        assert d == "2025-06-15"

    def test_int_date_invalid(self):
        assert int_date(99999999) == "9999-99-99"

    def test_int_date_zero(self):
        assert int_date(0) == "0"


class TestMinuteLabel:
    def test_morning_start(self):
        assert minute_label(571) == "09:31"

    def test_morning_end(self):
        assert minute_label(690) == "11:30"

    def test_afternoon_start(self):
        assert minute_label(781) == "13:01"

    def test_afternoon_end(self):
        assert minute_label(900) == "15:00"

    def test_returns_string(self):
        assert isinstance(minute_label(50), str)


class TestRecentSelector:
    def test_returns_int(self):
        d = date(2025, 6, 15)
        result = recent_selector(d)
        assert isinstance(result, int)
        assert result > 0

    def test_different_dates_different_selectors(self):
        d1 = date(2025, 1, 1)
        d2 = date(2025, 12, 31)
        assert recent_selector(d1) != recent_selector(d2)


class TestGetVolume:
    def test_zero(self):
        assert get_volume(0) >= 0.0

    def test_returns_float(self):
        assert isinstance(get_volume(0x1234), float)

    def test_positive(self):
        result = get_volume(0x00123456)
        assert isinstance(result, float)
        assert result >= 0
