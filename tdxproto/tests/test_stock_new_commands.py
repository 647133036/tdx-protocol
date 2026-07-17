"""Tests for new stock command builders and parsers."""

import struct
import unittest
from datetime import date, time
from unittest.mock import patch, MagicMock

from tdxproto.stock.commands import (
    _b_vol_profile, _b_index_momentum, _b_index_info,
    _b_quotes_detail, _b_tick_chart, _b_auction,
    _b_top_board, _b_quotes_list, _b_unusual,
    _b_chart_sampling_kline, _b_history_orders_full,
    _p_vol_profile, _p_index_momentum, _p_index_info,
    _p_quotes_detail, _p_tick_chart, _p_auction,
    _p_top_board, _p_quotes_list, _p_unusual,
    _p_chart_sampling_kline, _p_history_orders,
)
from tdxproto.stock.client import StockClient


class TestBuilders(unittest.TestCase):
    """Verify builder packet formats."""

    def _parse_frame(self, pkt):
        """Extract cmd and payload from a old-format packet.
        Format: H(2) I(4) H(2 zip_len) H(2 unzip_len) I(4) I(4 cmd) H(2) H(2) payload
        Total header: 22 bytes
        """
        cmd = struct.unpack_from("<I", pkt, 10)[0]
        datalen = struct.unpack_from("<H", pkt, 6)[0]
        payload = pkt[22:]
        return cmd, datalen, payload

    def test_vol_profile(self):
        pkt = _b_vol_profile(1, "000001")
        cmd, dl, _ = self._parse_frame(pkt)
        self.assertEqual(cmd, 0x051A)
        self.assertEqual(dl, 19)

    def test_index_momentum(self):
        pkt = _b_index_momentum(1, "000001")
        cmd, dl, _ = self._parse_frame(pkt)
        self.assertEqual(cmd, 0x051C)
        self.assertEqual(dl, 19)

    def test_index_info(self):
        pkt = _b_index_info(1, "000001")
        cmd, dl, _ = self._parse_frame(pkt)
        self.assertEqual(cmd, 0x051D)
        self.assertEqual(dl, 23)

    def test_quotes_detail(self):
        pkt = _b_quotes_detail([(1, "000001")])
        cmd, dl, payload = self._parse_frame(pkt)
        self.assertEqual(cmd, 0x053E)
        self.assertEqual(dl, 11)
        # Payload: H(msg_id=2) + H(5=2) + H(count=1=2) + B(market=1=1) + 6s(code=6)
        self.assertEqual(struct.unpack("<H", payload[0:2])[0], 5)
        stock_count = struct.unpack("<H", payload[2:4])[0]
        self.assertEqual(stock_count, 1)

    def test_tick_chart(self):
        """Verify pytdx GetTransactionData format (CMD 0x0FC5)."""
        pkt = _b_tick_chart(1, "000001")
        # Header: 0c 17 08 01 01 01 0e 00 0e 00 c5 0f (12 bytes)
        self.assertEqual(pkt[:12], bytes.fromhex("0c 17 08 01 01 01 0e 00 0e 00 c5 0f"))
        # Payload: <H6sHH = market + code + start + count = 2+6+2+2 = 12 bytes
        self.assertEqual(len(pkt), 24)
        market, code, start, count = struct.unpack_from("<H6sHH", pkt, 12)
        self.assertEqual(market, 1)
        self.assertEqual(code.decode("gbk").strip("\x00"), "000001")

    def test_auction(self):
        pkt = _b_auction(1, "000001")
        cmd, dl, _ = self._parse_frame(pkt)
        self.assertEqual(cmd, 0x056A)
        self.assertEqual(dl, 28)

    def test_top_board(self):
        pkt = _b_top_board(1)
        cmd, dl, _ = self._parse_frame(pkt)
        self.assertEqual(cmd, 0x053F)
        self.assertEqual(dl, 9)

    def test_quotes_list(self):
        pkt = _b_quotes_list(1)
        cmd, dl, _ = self._parse_frame(pkt)
        self.assertEqual(cmd, 0x054B)
        self.assertEqual(dl, 36)

    def test_unusual(self):
        pkt = _b_unusual(1)
        cmd, dl, _ = self._parse_frame(pkt)
        self.assertEqual(cmd, 0x0563)
        self.assertEqual(dl, 10)

    def test_chart_sampling(self):
        pkt = _b_chart_sampling_kline(1, "000001")
        cmd, dl, _ = self._parse_frame(pkt)
        self.assertEqual(cmd, 0xFD1)
        self.assertEqual(dl, 37)

    def test_history_orders(self):
        pkt = _b_history_orders_full(1, "000001", 20260630)
        cmd, dl, _ = self._parse_frame(pkt)
        self.assertEqual(cmd, 0x0FB4)
        self.assertEqual(dl, 11)


class TestParsers(unittest.TestCase):
    """Verify parser logic with mock data."""

    def test_vol_profile_empty(self):
        # Need at least 11B header + 9 get_price calls + 4B amount + 4 get_price + 12 get_price(3x4) + 2B = ~50B
        data = struct.pack("<HB6sH", 0, 1, b"000001", 0)
        data += bytes([0x01]) * 60
        result = _p_vol_profile(data)
        self.assertIn("vol_profile", result)
        self.assertEqual(result["vol_profile"], [])

    def test_vol_profile_with_data(self):
        data = struct.pack("<HB6sH", 2, 1, b"000001", 0)
        data += bytes([0x01]) * 60
        result = _p_vol_profile(data)
        self.assertIn("vol_profile", result)

    def test_index_momentum_empty(self):
        result = _p_index_momentum(b"\x00\x00")
        self.assertEqual(result, [])

    def test_index_momentum_values(self):
        # count=3, get_price encoded values: +10(0x0A), -5(0x45), +15(0x0F)
        data = struct.pack("<H", 3)
        data += bytes([0x0A, 0x45, 0x0F])
        result = _p_index_momentum(data)
        self.assertEqual(len(result), 3)
        self.assertEqual(result, [10, 5, 20])

    def test_index_info(self):
        data = struct.pack("<IB6sH", 0, 1, b"000001", 0)
        # Add enough get_price encoded bytes for all fields
        data += bytes([0x01]) * 100
        data += struct.pack("<f", 1000000.0)
        data += bytes([0x01]) * 50
        result = _p_index_info(data)
        self.assertIn("close", result)

    def test_quotes_detail_empty(self):
        data = struct.pack("<HH", 0, 0)
        result = _p_quotes_detail(data)
        self.assertEqual(result, [])

    def test_tick_chart_empty(self):
        data = struct.pack("<HH", 0, 0)
        result = _p_tick_chart(data)
        self.assertEqual(result, [])

    def test_auction_empty(self):
        result = _p_auction(b"\x00\x00")
        self.assertEqual(result, [])

    def test_top_board_empty(self):
        result = _p_top_board(b"\x00")
        for key in result:
            self.assertEqual(result[key], [])

    def test_quotes_list_empty(self):
        data = struct.pack("<HH", 0, 0)
        result = _p_quotes_list(data)
        self.assertEqual(result, [])

    def test_unusual_empty(self):
        result = _p_unusual(b"\x00\x00")
        self.assertEqual(result, [])

    def test_chart_sampling_empty(self):
        result = _p_chart_sampling_kline(b"")
        self.assertEqual(result, [])

    def test_chart_sampling_with_prices(self):
        # Response format: <H6s16xHH6xHfH + f*count
        data = struct.pack("<H6s16xHH6xHfH", 1, b"000001", 0, 0, 1, 100.0, 1)
        data += struct.pack("<f", 101.5)
        result = _p_chart_sampling_kline(data)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0], 101.5, places=1)

    def test_history_orders_empty(self):
        result = _p_history_orders(b"\x00\x00\x00\x00\x00\x00")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()


class TestQuoteHostRouting(unittest.TestCase):
    """验证 quote_host 分离路由逻辑."""

    def _make_snapshot_response(self):
        """构造最小合法快照响应 (跳过b1cb后: num=1, market=0, code=000001, active=0)."""
        data = struct.pack("<HH", 0, 1)
        data += struct.pack("<B6sH", 0, b"000001", 0)
        data += b"\x00" * 200
        return data

    def test_quote_method_uses_quote_connection(self):
        """quote() 方法应使用 _quote_send_recv 而非 _send_recv."""
        c = StockClient(hosts=["127.0.0.1:7709"], timeout=0.5, quote_host="60.12.136.250:7709")
        c._quote_send_recv = MagicMock(return_value=self._make_snapshot_response())
        c._send_recv = MagicMock()
        with patch.object(c, '_get_coefficient', return_value=0.01):
            with patch.object(c, '_get_name', return_value="test"):
                result = c.quote("sz000001")
        c._quote_send_recv.assert_called_once()
        c._send_recv.assert_not_called()

    def test_kline_uses_main_connection(self):
        """kline() 方法应使用 _send_recv 而非 _quote_send_recv."""
        c = StockClient(hosts=["127.0.0.1:7709"], timeout=0.5, quote_host="60.12.136.250:7709",
                        auto_reconnect=False)
        c._send_recv = MagicMock(return_value=b"\x00\x00")
        c._quote_send_recv = MagicMock()
        with patch.object(c, '_get_coefficient', return_value=0.01):
            result = c.kline("sz000001", "day", 0, 5)
        c._send_recv.assert_called_once()
        c._quote_send_recv.assert_not_called()
        assert result == []

    def test_today_minute_uses_main_connection(self):
        """today_minute() 应使用主连接, 00代码需显式前缀."""
        c = StockClient(hosts=["127.0.0.1:7709"], timeout=0.5, quote_host="60.12.136.250:7709",
                        auto_reconnect=False)
        valid = struct.pack("<H", 1) + b"\x00\x00\x00\x30\x30\x30\x30\x30\x31" + b"\x0a\x00\x64"
        c._send_recv = MagicMock(return_value=valid)
        c._quote_send_recv = MagicMock()
        with patch.object(c, '_get_coefficient', return_value=0.01):
            with self.assertRaises(ValueError) as ctx:
                c.today_minute("000001")
            self.assertIn("ambiguous", str(ctx.exception))
        c._send_recv.assert_not_called()
        c._quote_send_recv.assert_not_called()

    def test_quotes_detail_uses_quote_connection(self):
        """quotes_detail() 应使用 quote 连接."""
        c = StockClient(hosts=["127.0.0.1:7709"], timeout=0.5, quote_host="60.12.136.250:7709")
        c._quote_send_recv = MagicMock(return_value=b"\x00\x00\x00\x00")
        c._send_recv = MagicMock()
        with patch.object(c, '_get_coefficient', return_value=0.01):
            result = c.quotes_detail(["sz000001"])
        c._quote_send_recv.assert_called_once()
        c._send_recv.assert_not_called()

    def test_no_quote_host_fallback_to_main(self):
        """quote_host=None 时 quote() 应回退到主连接."""
        c = StockClient(hosts=["127.0.0.1:7709"], timeout=0.5, quote_host=None)
        with patch.object(c, '_send_recv', return_value=self._make_snapshot_response()) as mock_send:
            with patch.object(c, '_get_coefficient', return_value=0.01):
                with patch.object(c, '_get_name', return_value="test"):
                    result = c.quote("sz000001")
            mock_send.assert_called_once()
