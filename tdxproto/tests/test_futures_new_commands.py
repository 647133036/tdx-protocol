"""Tests for new futures commands: tick_chart, chart_sampling, quotes, table."""

import struct
import unittest

from tdxproto.futures.commands import (
    _b_ex_tick_chart, _b_ex_history_tick_chart,
    _b_ex_chart_sampling, _b_ex_table, _b_ex_quotes,
    _p_ex_tick_chart, _p_ex_history_tick_chart,
    _p_ex_chart_sampling, _p_ex_table, _p_ex_quotes,
)


class TestTickChartBuilder(unittest.TestCase):
    def test_basic(self):
        pkt = _b_ex_tick_chart(47, "IF2607")
        self.assertEqual(len(pkt), 32)
        mkt, code = struct.unpack("<B23s", pkt[:24])
        self.assertEqual(mkt, 47)
        self.assertTrue(code.startswith(b"IF2607"))

    def test_history(self):
        pkt = _b_ex_history_tick_chart(47, "IF2607", 20260630)
        self.assertEqual(len(pkt), 36)
        dt, mkt, code = struct.unpack("<IB23s", pkt[:28])
        self.assertEqual(dt, 20260630)
        self.assertEqual(mkt, 47)


class TestTickChartParser(unittest.TestCase):
    def test_tick_chart_empty(self):
        self.assertEqual(_p_ex_tick_chart(b""), [])

    def test_tick_chart_one_point(self):
        code = b"IF2607" + b"\x00" * 17
        data = struct.pack("<B31sH", 47, code + b"\x00" * 8, 1)
        data += struct.pack("<HffII", 570, 4050.5, 4051.0, 100000, 50000)
        result = _p_ex_tick_chart(data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["market"], 47)
        self.assertAlmostEqual(result[0]["price"], 4050.5, places=1)
        self.assertEqual(result[0]["vol"], 100000)

    def test_history_tick_chart(self):
        code = b"CJ2607" + b"\x00" * 15
        data = struct.pack("<B23sIfIIH", 47, code, 20260630, 4050.0, 0, 0, 1)
        data += struct.pack("<HffII", 570, 4050.5, 4051.0, 100000, 50000)
        result = _p_ex_history_tick_chart(data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["date"], 20260630)


class TestChartSampling(unittest.TestCase):
    def test_builder(self):
        pkt = _b_ex_chart_sampling(47, "IF2607")
        mkt, code = struct.unpack("<H22s", pkt[:24])
        self.assertEqual(mkt, 47)
        self.assertTrue(code.startswith(b"IF2607"))

    def test_parser_empty(self):
        self.assertEqual(_p_ex_chart_sampling(b""), [])

    def test_parser_four_prices(self):
        code = b"IF2607" + b"\x00" * 15
        data = struct.pack("<H22s9H", 47, code, 1, 2, 0, 0, 0, 0, 0, 0, 4)
        data += struct.pack("<ffff", 100.0, 200.0, 300.0, 400.0)
        result = _p_ex_chart_sampling(data)
        self.assertEqual(len(result), 4)
        self.assertEqual(result, [100.0, 200.0, 300.0, 400.0])


class TestTable(unittest.TestCase):
    def test_builder_default(self):
        pkt = _b_ex_table()
        start, = struct.unpack("<I", pkt[:4])
        self.assertEqual(start, 0)

    def test_builder_with_start(self):
        pkt = _b_ex_table(start=200)
        start, = struct.unpack("<I", pkt[:4])
        self.assertEqual(start, 200)

    def test_parser_empty(self):
        self.assertEqual(_p_ex_table(b""), (0, 0, ""))

    def test_parser_with_context(self):
        data = b"\x00" * 169
        data = data[:32] + struct.pack("<HBB", 1, 0, 0) + data[36:]
        data = data[:36] + struct.pack("<I", 200) + data[40:]
        data = data[:116] + b"\x01" + data[117:]
        ctx_text = "hello world"
        data = data[:161] + struct.pack("<II", 11, len(ctx_text)) + data[169:]
        data += ctx_text.encode("gbk")
        start, count, ctx = _p_ex_table(data)
        self.assertEqual(start, 200)
        self.assertEqual(count, 11)
        self.assertEqual(ctx, "hello world")


class TestQuotes(unittest.TestCase):
    def test_builder_empty_raises(self):
        with self.assertRaises(ValueError):
            _b_ex_quotes([])

    def test_builder_single(self):
        pkt = _b_ex_quotes([(47, "IF2607")])
        u, _, count = struct.unpack("<IIH", pkt[:10])
        self.assertEqual(count, 1)

    def test_builder_multiple(self):
        codes = [(47, "IF2607"), (47, "IC2607"), (47, "IH2607")]
        pkt = _b_ex_quotes(codes)
        u, _, count = struct.unpack("<IIH", pkt[:10])
        self.assertEqual(count, 3)

    def test_parser_empty(self):
        self.assertEqual(_p_ex_quotes(b""), [])

    def test_parser_single_record(self):
        code = b"IF2607" + b"\x00" * 15
        data = struct.pack("<IIH", 0, 0, 1)
        rec = struct.pack("<B23s", 47, code)
        rec += struct.pack("<I5f", 1, 4050.0, 4055.0, 4060.0, 4040.0, 4052.0)
        rec += struct.pack("<4If", 100000, 50000, 2000000, 500000, 100000)
        rec += struct.pack("<4I", 100000, 200000, 300000, 400000)
        rec += struct.pack("<5f5I5f5I",
                           4051.0, 4050.0, 4049.0, 4048.0, 4047.0,
                           100, 200, 300, 400, 500,
                           4053.0, 4054.0, 4055.0, 4056.0, 4057.0,
                           100, 200, 300, 400, 500)
        rec += struct.pack("<HfIff", 0, 4052.0, 0, 4051.5, 20260630)
        rec += b"\x00" * (314 - len(rec))
        data += rec
        result = _p_ex_quotes(data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["market"], 47)
        self.assertEqual(result[0]["code"], "IF2607")
        self.assertEqual(result[0]["pre_close"], 4050.0)
        self.assertEqual(result[0]["close"], 4052.0)
        self.assertEqual(result[0]["vol"], 2000000)


if __name__ == "__main__":
    unittest.main()
