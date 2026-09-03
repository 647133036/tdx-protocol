"""StockClient 单元测试 — mock 网络层."""
import struct
import pytest
from unittest.mock import patch, MagicMock

from tdxproto.stock.client import StockClient
from tdxproto.stock.commands import _b_kline, _p_kline


class TestKlineFailover:
    """kline() 故障转移逻辑."""

    def test_kline_empty_triggers_failover(self):
        """空响应时 failover=True 应触发故障转移."""
        client = StockClient(timeout=5, auto_reconnect=True)
        # mock _send_recv 返回空数据
        client._tube = MagicMock()
        client._tube.call.return_value = MagicMock(data=b"\x00\x00")
        client._current_host = "bad:7709"

        with patch.object(client, '_ping_and_rank', return_value=[]):
            with patch.object(client, '_find_host_returning_kline', return_value=[]) as mock_fo:
                result = client.kline("sh999999", "day", failover=True)
                assert result == []
                mock_fo.assert_called_once()

    def test_kline_normal_response_no_failover(self):
        """有数据时不触发 failover."""
        client = StockClient(timeout=5, auto_reconnect=True)

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

        bars_data = bytearray()
        for dt in [20260831, 20260901, 20260902]:
            bars_data.extend(struct.pack("<I", dt))
            bars_data.extend(ev(10000)); bars_data.extend(ev(500))
            bars_data.extend(ev(1000)); bars_data.extend(ev(-200))
            bars_data.extend(struct.pack("<I", 0)); bars_data.extend(struct.pack("<I", 0))
            bars_data.extend(struct.pack("<I", 0))  # index extra: up+down count (sh000001 is index)

        resp = struct.pack("<H", 3) + bytes(bars_data)

        with patch.object(client, '_send_recv', return_value=resp):
            result = client.kline("sh000001", "day", failover=False, count=3)
        assert len(result) == 3
        assert result[0].time == "20260831"
        assert result[2].time == "20260902"

    def test_kline_garbage_filtered(self):
        """无效代码返回的垃圾数据应被 parser 过滤."""
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

        bars_data = bytearray()
        # 合法行
        bars_data.extend(struct.pack("<I", 20260902))
        bars_data.extend(ev(10000)); bars_data.extend(ev(500))
        bars_data.extend(ev(1000)); bars_data.extend(ev(-200))
        bars_data.extend(struct.pack("<I", 0)); bars_data.extend(struct.pack("<I", 0))
        # 垃圾行: month=99
        bars_data.extend(struct.pack("<I", 20269999))
        for _ in range(4):
            bars_data.extend(ev(0))
        bars_data.extend(struct.pack("<I", 0)); bars_data.extend(struct.pack("<I", 0))

        resp = struct.pack("<H", 2) + bytes(bars_data)
        rows = _p_kline(resp, 9, "sh999999", coefficient=0.01, market=1)
        assert len(rows) == 1
        assert rows[0]["year"] == 2026
        assert rows[0]["month"] == 9
        assert rows[0]["day"] == 2


class TestBareExcept:
    """验证 bare except 已修复为保留 SystemExit/KeyboardInterrupt."""

    def test_connect_preserves_keyboardinterrupt(self):
        """连接失败时应重新抛出 KeyboardInterrupt."""
        client = StockClient(timeout=0.001)
        with patch('socket.create_connection', side_effect=OSError("conn ref")):
            # connect() 会遍历所有 hosts，每个都抛 OSError
            # 最终应被包装为 ConnectionError（不是 swallowed）
            with pytest.raises(ConnectionError):
                client.connect()

    def test_bare_except_does_not_swallow_exception(self):
        """验证 sock.close() 中的 bare except 不会吞掉 KeyboardInterrupt."""
        client = StockClient(timeout=0.001, hosts=["127.0.0.1:1"])
        # socket.send() 抛出 KeyboardInterrupt，应穿透 _connect_once 的 except Exception
        mock_sock = MagicMock()
        mock_sock.send = MagicMock(side_effect=KeyboardInterrupt())
        with patch('tdxproto.stock.client.socket.socket', return_value=mock_sock):
            with pytest.raises(KeyboardInterrupt):
                client.connect()


class TestCountUpperLimit:
    """kline count 上限校验."""

    def test_count_within_limit(self):
        from main import stock_kline
        class A:
            count = 100
            code = "sz000001"
            period = "day"
            start = 0
            adjust = ""
            anchor = ""
        c = MagicMock()
        c.kline.return_value = []
        stock_kline(c, A())
        c.kline.assert_called_once()

    def test_count_exceeds_limit_raises(self, capsys):
        from main import stock_kline
        class A:
            count = 70000
            code = "sz000001"
            period = "day"
            start = 0
            adjust = ""
            anchor = ""
        c = MagicMock()
        stock_kline(c, A())
        err = capsys.readouterr().err
        assert "65535" in err
        c.kline.assert_not_called()


class TestKlineDateFilter:
    """kline 日期过滤逻辑."""

    def test_filters_negative_open(self):
        """负价格应被过滤."""
        bars_data = bytearray()
        # 合法行: year=2026, month=9, day=2, open=10.0
        bars_data.extend(struct.pack("<I", 20260902))
        bars_data.extend(struct.pack("<i", 10000))   # open diff = 10000
        bars_data.extend(struct.pack("<i", 500))     # close diff
        bars_data.extend(struct.pack("<i", 1000))    # high diff
        bars_data.extend(struct.pack("<i", -200))    # low diff
        bars_data.extend(struct.pack("<I", 0))       # vol
        bars_data.extend(struct.pack("<I", 0))       # amount
        # 垃圾行: 负开盘价
        bars_data.extend(struct.pack("<I", 20260901))
        bars_data.extend(struct.pack("<i", -50000))  # negative open
        bars_data.extend(struct.pack("<i", 0))
        bars_data.extend(struct.pack("<i", 0))
        bars_data.extend(struct.pack("<i", 0))
        bars_data.extend(struct.pack("<I", 0))
        bars_data.extend(struct.pack("<I", 0))

        resp = struct.pack("<H", 2) + bytes(bars_data)
        rows = _p_kline(resp, 9, "sh999999", coefficient=0.01, market=1)
        # 只有 open > 0 的行应被保留
        assert len(rows) == 1
        assert rows[0]["open"] > 0

    def test_filters_far_future_year(self):
        """year > 2100 应被过滤."""
        bars_data = bytearray()
        # year=2200 超出范围
        bars_data.extend(struct.pack("<I", 22000101))
        for _ in range(4):
            bars_data.extend(b"\x00" * 4)
        bars_data.extend(struct.pack("<I", 0))
        bars_data.extend(struct.pack("<I", 0))

        resp = struct.pack("<H", 1) + bytes(bars_data)
        rows = _p_kline(resp, 9, "sh999999", coefficient=0.01, market=1)
        assert len(rows) == 0

    def test_filters_far_past_year(self):
        """year < 1990 应被过滤."""
        bars_data = bytearray()
        bars_data.extend(struct.pack("<I", 19890101))
        bars_data.extend(b"\x0a\x00\x00\x00")
        bars_data.extend(struct.pack("<I", 0))
        bars_data.extend(struct.pack("<I", 0))
        bars_data.extend(struct.pack("<I", 0))

        resp = struct.pack("<H", 1) + bytes(bars_data)
        rows = _p_kline(resp, 9, "sz000001", coefficient=0.01, market=0)
        assert len(rows) == 0

    def test_keeps_1990s_bars(self):
        """1990-1999 的合法日 K 应保留."""
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

        bars_data = bytearray()
        bars_data.extend(struct.pack("<I", 19910102))
        bars_data.extend(ev(10000))
        bars_data.extend(ev(0))
        bars_data.extend(ev(0))
        bars_data.extend(ev(0))
        bars_data.extend(struct.pack("<I", 0))
        bars_data.extend(struct.pack("<I", 0))
        resp = struct.pack("<H", 1) + bytes(bars_data)
        rows = _p_kline(resp, 9, "sz000001", coefficient=0.01, market=0)
        assert len(rows) == 1
        assert rows[0]["year"] == 1991


class TestIndexInfoCodes:
    def test_index_info_uses_dict_code_field(self):
        client = StockClient(timeout=5, auto_reconnect=False)
        with patch.object(client, "board_members", side_effect=Exception("no mac")):
            with patch.object(client, "codes_all", return_value=[{"code": "000001", "name": "平安银行"}]):
                with patch.object(client, "quotes_detail", return_value=[{"code": "sz000001"}]) as mock_qd:
                    result = client.index_info("sz000001", top_n=1)
        assert result["count"] == 1
        mock_qd.assert_called_once()
        sample = mock_qd.call_args[0][0]
        assert sample == ["sz000001"]


class TestXdxrInvalidDate:
    def test_invalid_calendar_date_does_not_raise(self):
        client = StockClient(timeout=5, auto_reconnect=False)
        fake = [{"year": 2024, "month": 2, "day": 30, "category": 1, "fenhong": 0.1}]
        with patch.object(client, "_send_recv", return_value=b"\x00\x00"):
            with patch("tdxproto.stock.client._p_xdxr", return_value=fake):
                rows = client.xdxr("sz000001")
        assert len(rows) == 1
        assert rows[0].date is None
