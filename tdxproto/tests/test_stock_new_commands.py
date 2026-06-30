"""Tests for new stock command builders and parsers."""

import struct
import unittest
from datetime import date, time

from tdxproto.stock.commands import (
    _b_vol_profile, _b_index_momentum, _b_index_info,
    _b_quotes_detail, _b_tick_chart, _b_auction,
    _b_top_board, _b_quotes_list, _b_unusual,
    _b_chart_sampling, _b_history_orders,
    _p_vol_profile, _p_index_momentum, _p_index_info,
    _p_quotes_detail, _p_tick_chart, _p_auction,
    _p_top_board, _p_quotes_list, _p_unusual,
    _p_chart_sampling, _p_history_orders,
)


class TestBuilders(unittest.TestCase):
    """Verify builder packet formats."""

    def _parse_frame(self, pkt):
        """Extract cmd and payload from a Frame-wrapped packet."""
        # Frame header: 12 bytes (prefix + msg_id + ctrl + datalen*2 + cmd)
        # But our struct pack produces 22 bytes total, with 10 bytes of payload embedded
        cmd = struct.unpack_from("<H", pkt, 10)[0]
        datalen = struct.unpack_from("<H", pkt, 6)[0]
        payload = pkt[12:]
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
        # Payload: 10B padding + <H(2) count=5 + <B6s(7) market=1, code=000001
        count = struct.unpack("<H", payload[10:12])[0]
        self.assertEqual(count, 5)

    def test_tick_chart(self):
        pkt = _b_tick_chart(1, "000001")
        cmd, dl, _ = self._parse_frame(pkt)
        self.assertEqual(cmd, 0x0537)
        self.assertEqual(dl, 12)

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
        pkt = _b_chart_sampling(1, "000001")
        cmd, dl, _ = self._parse_frame(pkt)
        self.assertEqual(cmd, 0xFD1)
        self.assertEqual(dl, 37)

    def test_history_orders(self):
        pkt = _b_history_orders(1, "000001", 20260630)
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
        result = _p_chart_sampling(b"")
        self.assertEqual(result, [])

    def test_chart_sampling_with_prices(self):
        # Response format: <H6s16xHH6xHfH + f*count
        data = struct.pack("<H6s16xHH6xHfH", 1, b"000001", 0, 0, 1, 100.0, 1)
        data += struct.pack("<f", 101.5)
        result = _p_chart_sampling(data)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0], 101.5, places=1)

    def test_history_orders_empty(self):
        result = _p_history_orders(b"\x00\x00\x00\x00\x00\x00")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
