import struct
import pytest

from tdxproto.futures.commands import (
    CMD_EX_HANDSHAKE, CMD_EX_HEARTBEAT, CMD_EX_MARKETS, CMD_EX_CODES,
    CMD_EX_QUOTE, CMD_EX_QUOTE_BATCH, CMD_EX_KLINE, CMD_EX_KLINE_RANGE,
    CMD_EX_MINUTE_TODAY, CMD_EX_MINUTE_HISTORY,
    CMD_EX_TRADE_TODAY, CMD_EX_TRADE_HISTORY,
    HANDSHAKE_DATA,
    _b_ex_handshake, _b_ex_heartbeat, _b_ex_markets, _b_ex_codes,
    _b_ex_quote, _b_ex_quote_batch, _b_ex_kline, _b_ex_kline_range,
    _b_ex_minute_today, _b_ex_minute_history,
    _b_ex_trade_today, _b_ex_trade_history,
    _p_ex_markets, _p_ex_codes, _p_ex_quote, _p_ex_quote_batch,
    _p_ex_kline, _p_ex_kline_range, _p_ex_minute, _p_ex_minute_history, _p_ex_trade,
    TRADE_NATURE, TRADE_DIR, PERIOD_MAP,
)

CODE_PAD = b"\x00" * 9


class TestConstants:
    def test_handshake_command(self):
        assert CMD_EX_HANDSHAKE == 0x2454

    def test_codes_command(self):
        assert CMD_EX_CODES == 0x23F5

    def test_quote_command(self):
        assert CMD_EX_QUOTE == 0x23FA

    def test_handshake_data_length(self):
        assert len(HANDSHAKE_DATA) == 80

    def test_period_map(self):
        assert PERIOD_MAP["day"] == 4
        assert PERIOD_MAP["5m"] == 0
        assert PERIOD_MAP["1m"] == 8


class TestBuilders:
    def test_handshake_returns_80_bytes(self):
        assert len(_b_ex_handshake()) == 80

    def test_heartbeat_market_0(self):
        assert _b_ex_heartbeat(0) == b"\x00\x00"

    def test_heartbeat_market_1(self):
        assert _b_ex_heartbeat(1) == b"\x01\x00"

    def test_markets_empty(self):
        assert _b_ex_markets() == b""

    def test_codes_format_IH(self):
        data = _b_ex_codes(0, 500, 100)
        assert len(data) == 6
        start, count = struct.unpack("<IH", data)
        assert start == 500
        assert count == 100

    def test_quote_format_B9s(self):
        data = _b_ex_quote(47, "IF2607")
        assert len(data) == 10
        mid = struct.unpack("<B", data[:1])[0]
        assert mid == 47

    def test_quote_batch_format_BHHHH(self):
        data = _b_ex_quote_batch(47, 10, 50)
        assert len(data) == 9
        mid, zero, start, count, one = struct.unpack("<BHHHH", data)
        assert mid == 47
        assert start == 10
        assert count == 50
        assert one == 1

    def test_kline_format_B9sHHIH(self):
        data = _b_ex_kline(47, "IF2607", "day", 100, 500)
        assert len(data) == 20
        mid, code, cat, one, start, count = struct.unpack("<B9sHHIH", data)
        assert mid == 47
        assert cat == 4
        assert one == 1
        assert start == 100
        assert count == 500

    def test_kline_range_format(self):
        data = _b_ex_kline_range(47, "IF2607", "day", 20250101, 20251231)
        assert len(data) == 20
        mid, code = struct.unpack("<B9s", data[:10])
        assert mid == 47
        assert data[10:12] == b"\x07\x00"
        sd, ed = struct.unpack("<LL", data[12:20])
        assert sd == 20250101
        assert ed == 20251231

    def test_kline_range_default_dates(self):
        data = _b_ex_kline_range(47, "IF2607")
        sd, ed = struct.unpack("<LL", data[12:20])
        assert sd == 20000101
        assert ed == 20991231

    def test_minute_today_format_B9s(self):
        data = _b_ex_minute_today(47, "IF2607")
        assert len(data) == 10

    def test_minute_history_format_IB9s(self):
        data = _b_ex_minute_history(47, "IF2607", 20250629)
        assert len(data) == 14
        date_val, = struct.unpack("<I", data[:4])
        assert date_val == 20250629

    def test_trade_today_format_B9siH(self):
        data = _b_ex_trade_today(47, "IF2607", 10, 50)
        assert len(data) == 16
        mid, code, start, count = struct.unpack("<B9siH", data)
        assert mid == 47
        assert start == 10
        assert count == 50

    def test_trade_history_format_IB9siH(self):
        data = _b_ex_trade_history(47, "IF2607", 20250629, 20, 30)
        assert len(data) == 20
        date_val, mid, code, start, count = struct.unpack("<IB9siH", data)
        assert date_val == 20250629
        assert start == 20
        assert count == 30


class TestParsers:
    def test_markets_empty(self):
        assert _p_ex_markets(b"") == []

    def test_markets_zero_count(self):
        assert _p_ex_markets(b"\x00\x00") == []

    def test_markets_valid_record_64byte(self):
        record = bytearray(64)
        record[0] = 30
        raw_name = "测试市场".encode("gbk").ljust(32, b"\x00")
        record[1:33] = raw_name
        record[33] = 5
        raw_short = "TS".encode("gbk").ljust(2, b"\x00")
        record[34:36] = raw_short
        data = struct.pack("<H", 1) + bytes(record)
        result = _p_ex_markets(data)
        assert len(result) == 1
        assert result[0]["market_id"] == 5
        assert result[0]["name"] == "测试市场"
        assert result[0]["short_name"] == "TS"
        assert result[0]["category"] == 30

    def test_markets_skip_zero_category_and_market(self):
        record = bytearray(64)
        data = struct.pack("<H", 1) + bytes(record)
        result = _p_ex_markets(data)
        assert len(result) == 0

    def test_codes_empty(self):
        assert _p_ex_codes(b"") == []

    def test_codes_short_header(self):
        assert _p_ex_codes(b"\x00\x00") == []

    def test_codes_valid_IH_plus_64byte_record(self):
        header = struct.pack("<IH", 0, 1)
        record = bytearray(64)
        record[0] = 3
        record[1] = 47
        code_raw = "IF2607".encode("gbk").ljust(9, b"\x00")
        record[5:14] = code_raw
        name_raw = "沪深2607".encode("gbk").ljust(17, b"\x00")
        record[14:31] = name_raw
        data = header + bytes(record)
        result = _p_ex_codes(data)
        assert len(result) == 1
        assert result[0]["market_id"] == 47
        assert result[0]["code"] == "IF2607"
        assert result[0]["name"] == "沪深2607"
        assert result[0]["category"] == 3

    def test_codes_multiple_records(self):
        header = struct.pack("<IH", 0, 2)
        records = bytearray()
        for i in range(2):
            rec = bytearray(64)
            rec[0] = 3
            rec[1] = 47
            code_raw = f"IF{(i + 1) * 100}07".encode("gbk").ljust(9, b"\x00")
            rec[5:14] = code_raw
            name_raw = f"沪深{(i + 1) * 100}07".encode("gbk").ljust(17, b"\x00")
            rec[14:31] = name_raw
            records += bytes(rec)
        data = header + bytes(records)
        result = _p_ex_codes(data)
        assert len(result) == 2
        assert result[0]["code"] == "IF10007"
        assert result[1]["code"] == "IF20007"

    def test_quote_empty(self):
        from tdxproto.models import Quote
        q = _p_ex_quote(b"", 2, "T001")
        assert isinstance(q, Quote)
        assert q.code == "T001"

    def test_quote_short(self):
        from tdxproto.models import Quote
        q = _p_ex_quote(b"\x00" * 30, 2, "T001")
        assert isinstance(q, Quote)

    def test_quote_batch_empty(self):
        assert _p_ex_quote_batch(b"") == []

    def test_kline_empty(self):
        assert _p_ex_kline(b"", 2, "T001", "day") == []

    def test_kline_valid_daily_bars(self):
        data = bytearray(18 + 2)
        ret_count = 2
        struct.pack_into("<H", data, 18, ret_count)
        for i in range(2):
            bar = bytearray(32)
            zip_day = 20260101 + i
            struct.pack_into("<I", bar, 0, zip_day)
            struct.pack_into("<ffffIIf", bar, 4,
                             100.0 + i, 110.0 + i, 90.0 + i, 105.0 + i,
                             200000, 50000 + i, 10000.0)
            data += bytes(bar)
        result = _p_ex_kline(bytes(data), 47, "IF2607", "day")
        assert len(result) == 2
        assert result[0].open == 100.0
        assert result[0].close == 105.0
        assert result[0].position == 200000
        assert result[1].volume == 50001

    def test_kline_valid_1m_bars(self):
        data = bytearray(18 + 2)
        ret_count = 1
        struct.pack_into("<H", data, 18, ret_count)
        bar = bytearray(32)
        zip_day = 0x0001
        minutes = 570
        struct.pack_into("<HH", bar, 0, zip_day, minutes)
        struct.pack_into("<ffffIIf", bar, 4, 10.0, 12.0, 9.0, 11.0, 100, 1000, 11.0)
        data += bytes(bar)
        result = _p_ex_kline(bytes(data), 47, "IF2607", "1m")
        assert len(result) == 1
        assert result[0].open == 10.0
        assert "09:30" in result[0].time

    def test_kline_range_valid(self):
        data = bytearray(12 + 2)
        ret_count = 1
        struct.pack_into("<H", data, 12, ret_count)
        bar = struct.pack("<HHffffIIf",
                          0x0001, 570, 10.0, 12.0, 9.0, 11.0, 200000, 1000, 10.5)
        data += bar
        result = _p_ex_kline_range(bytes(data), 47, "IF2607", "1m")
        assert len(result) == 1
        assert result[0].settlement == 10.5
        assert result[0].position == 200000

    def test_kline_range_empty(self):
        assert _p_ex_kline_range(b"", 2, "T001", "day") == []

    def test_minute_today_empty(self):
        assert _p_ex_minute(b"", 2, "T001") == []

    def test_minute_today_valid(self):
        header = struct.pack("<B9sH", 47, "IF2607".encode().ljust(9, b"\x00"), 2)
        records = bytearray()
        records += struct.pack("<HffII", 570, 100.0, 99.5, 1000, 50000)
        records += struct.pack("<HffII", 571, 101.0, 100.0, 800, 51000)
        data = header + bytes(records)
        result = _p_ex_minute(data, 47, "IF2607")
        assert len(result) == 2
        assert result[0].time == "09:30"
        assert result[0].price == 100.0
        assert result[0].volume == 1000
        assert result[1].time == "09:31"

    def test_minute_history_valid(self):
        header = struct.pack("<B9s8sH", 47, "IF2607".encode().ljust(9, b"\x00"),
                             b"\x00" * 8, 1)
        records = struct.pack("<HffII", 570, 100.0, 99.5, 1000, 50000)
        data = header + records
        result = _p_ex_minute_history(data, 47, "IF2607")
        assert len(result) == 1
        assert result[0].time == "09:30"
        assert result[0].open_interest == 50000

    def test_trade_empty(self):
        assert _p_ex_trade(b"", 2, "T001") == []

    def test_trade_valid(self):
        header = struct.pack("<B9s4sH", 47, "IF2607".encode().ljust(9, b"\x00"),
                             b"\x00" * 4, 2)
        records = bytearray()
        records += struct.pack("<HIIiH", 855, 4869000, 2, 1, 10053)
        records += struct.pack("<HIIiH", 856, 4870000, 3, -1, 20059)
        data = header + bytes(records)
        result = _p_ex_trade(data, 47, "IF2607")
        assert len(result) == 2
        assert result[0].time.startswith("14:15")
        assert result[0].price == 4869000
        assert result[0].volume == 2
        assert result[1].price == 4870000


class TestTradeMaps:
    def test_nature_map(self):
        assert TRADE_NATURE[0x01] == "多开"
        assert TRADE_NATURE[0x02] == "空开"

    def test_dir_map(self):
        assert TRADE_DIR[0] == "买入"
        assert TRADE_DIR[1] == "卖出"
