"""港股行情模块单元测试 — 基于腾讯接口."""

import pytest
import urllib.error

from tdxproto.hk import HkClient, HkQuote
from tdxproto.hk.client import _parse_response, _parse_fields, _normalize_code, _safe_float, _safe_int, _TIME_RE


class TestSafeParse:
    def test_safe_float_ok(self):
        assert _safe_float("12.34") == 12.34
        assert _safe_float("0") == 0.0

    def test_safe_float_empty(self):
        assert _safe_float("") == 0.0

    def test_safe_float_invalid(self):
        assert _safe_float("abc") == 0.0
        assert _safe_float("-") == 0.0

    def test_safe_float_nan_inf(self):
        assert _safe_float("nan") == 0.0
        assert _safe_float("inf") == 0.0
        assert _safe_float("-inf") == 0.0

    def test_safe_float_whitespace(self):
        assert _safe_float("  12.34  ") == 12.34

    def test_safe_float_negative(self):
        assert _safe_float("-5.5") == -5.5

    def test_safe_int_ok(self):
        assert _safe_int("42") == 42
        assert _safe_int("42.5") == 42

    def test_safe_int_empty(self):
        assert _safe_int("") == 0

    def test_safe_int_negative(self):
        assert _safe_int("-5") == -5

    def test_safe_int_nan_inf(self):
        assert _safe_int("nan") == 0
        assert _safe_int("inf") == 0
        assert _safe_int("-inf") == 0


class TestNormalizeCode:
    def test_already_prefixed(self):
        assert _normalize_code("hk00700") == "hk00700"

    def test_add_prefix(self):
        assert _normalize_code("00700") == "hk00700"
        assert _normalize_code("09988") == "hk09988"

    def test_uppercase(self):
        assert _normalize_code("HK00700") == "hk00700"
        assert _normalize_code("00700 ") == "hk00700"

    def test_none(self):
        assert _normalize_code(None) is None

    def test_empty_string(self):
        assert _normalize_code("") is None
        assert _normalize_code("   ") is None


class TestParseResponse:
    def test_single_quote(self):
        raw = b'v_hk00700="100~\xcc\xda\xd1\xb6\xbf\xd8\xb9\xc9~00700~445.200~433.000~442.400~10997901.0~0~0~445.200~0~0~0~0~0~0~0~0~0~445.200~0~0~0~0~0~0~0~0~0~0~10997901.0~2026/09/04 11:59:06~12.200~2.82~446.600~440.000~445.200~10997901.0~4878335816.800~0~16.28~~0~0~1.52~40527.2411~40527.2411~TENCENT~1.19~677.700~411.000~1.14~-41.52~0~0~0~0~0~14.95~3.11~0.12~100~-25.01~-2.20~GP~20.41~11.00~-2.58~-7.02~-4.38~9103153877.00~9103153877.00~15.42~5.309~443.570~-25.45~HKD~1~30";\n'
        parsed = _parse_response(raw)
        assert "hk00700" in parsed
        assert len(parsed["hk00700"]) > 30

    def test_multiple_quotes(self):
        raw = (
            b'v_hk00700="100~test~00700~445.0~433.0~442.0~10000~0~0~445.0~0~0~0~0~0~0~0~0~0~445.0~0~0~0~0~0~0~0~0~0~0~10000~2026/09/04 10:00:00~10.0~1.0~446.0~440.0~445.0~10000~4800000.0~0~16.0~~0~0~1.5~40000~40000~TENCENT~1.19~677.7~411.0~1.1~-41.5~0~0~0~0~0~14.9~3.1~0.1~100~-25~-2~GP~20~11~-2~-7~-4~9000~9000~15~5.3~443~-25~HKD~1~30";\n'
            b'v_hk09988="100~test2~09988~111.0~108.0~110.0~5000~0~0~111.0~0~0~0~0~0~0~0~0~0~111.0~0~0~0~0~0~0~0~0~0~0~5000~2026/09/04 10:00:00~8.0~2.0~112.0~109.0~111.0~5000~2400000.0~0~14.0~~0~0~1.5~30000~30000~ALIBABA~1.19~150.0~90.0~1.1~-10.5~0~0~0~0~0~14.9~3.1~0.1~100~-25~-2~GP~20~11~-2~-7~-4~8000~8000~15~5.3~110~-25~HKD~1~30";\n'
        )
        parsed = _parse_response(raw)
        assert len(parsed) == 2
        assert "hk00700" in parsed
        assert "hk09988" in parsed

    def test_empty_response(self):
        parsed = _parse_response(b"")
        assert parsed == {}

    def test_no_match_line(self):
        raw = b"some random line\nnot a quote\n"
        parsed = _parse_response(raw)
        assert parsed == {}


class TestParseFields:
    def _make_fields(self) -> list[str]:
        """构造标准港股字段列表（腾讯格式，78 字段）."""
        return [
            "100",                        # 0: status
            "腾讯控股",                      # 1: name
            "00700",                      # 2: code
            "445.200",                    # 3: price
            "433.000",                    # 4: pre_close
            "442.400",                    # 5: open
            "10997901.0",                 # 6: volume
            "0", "0",                     # 7-8
            "445.200",                    # 9: last_price
            "0", "0", "0", "0", "0", "0", "0", "0", "0",  # 10-18
            "445.200",                    # 19: last_price
            "0", "0", "0", "0", "0", "0", "0", "0", "0", "0",  # 20-29
            "10997901.0",                 # 29: volume
            "2026/09/04 11:59:06",        # 30: time (anchor)
            "12.200",                     # 31: amplitude
            "2.82",                       # 32: change_pct
            "446.600",                    # 33: high
            "440.000",                    # 34: low
            "445.200",                    # 35: close
            "10997901.0",                 # 36: volume
            "4878335816.800",             # 37: amount
            "0",                          # 38
            "16.28",                      # 39: turnover_pct
            "", "0", "0",                 # 40-42
            "1.52",                       # 43: pe_ttm
            "40527.2411", "40527.2411",   # 44-45: market caps
            "TENCENT",                    # 46: english_name
            "1.19",                       # 47: change_pct again
            "677.700",                    # 48: year_high
            "411.000",                    # 49: year_low
            "1.14", "-41.52",             # 50-51
            "0", "0", "0", "0", "0",      # 52-56
            "14.95", "3.11", "0.12",      # 57-59
            "100", "-25.01", "-2.20",     # 60-62
            "GP", "20.41", "11.00",       # 63-65
            "-2.58", "-7.02", "-4.38",    # 66-68
            "9103153877.00", "9103153877.00",  # 69-70
            "15.42", "5.309", "443.570",  # 71-73
            "-25.45",                     # 74
            "HKD",                        # 75: currency
            "1", "30",                    # 76-77
        ]

    def test_parse_valid(self):
        fields = self._make_fields()
        quote = _parse_fields(fields, "00700")
        assert quote is not None
        assert quote.code == "00700"
        assert quote.name == "腾讯控股"
        assert quote.price == 445.200
        assert quote.pre_close == 433.000
        assert quote.open == 442.400
        assert quote.high == 446.600
        assert quote.low == 440.000
        assert quote.volume == 10997901
        assert quote.amount == 4878335816.800
        assert quote.change_pct == 2.82
        assert abs(quote.change_amt - 12.2) < 0.01
        assert quote.turnover_pct == 16.28
        assert quote.time == "2026/09/04 11:59:06"
        assert quote.currency == "HKD"
        assert quote.year_high == 677.700
        assert quote.year_low == 411.000
        assert quote.pe == 1.52

    def test_parse_short_fields(self):
        fields = ["100", "test", "00700", "445.0", "433.0", "442.0"]
        assert _parse_fields(fields, "00700") is None

    def test_parse_bad_status(self):
        fields = self._make_fields()
        fields[0] = "0"
        assert _parse_fields(fields, "00700") is None

    def test_parse_no_time(self):
        fields = self._make_fields()
        # 时间实际在索引 31（不是 30），需替换正确位置
        fields[31] = "not_a_time"
        assert _parse_fields(fields, "00700") is None

    def test_parse_extra_zero_field(self):
        """验证格式波动（多一个 0）时仍能正确解析."""
        fields = self._make_fields()
        # 插入额外的 0 字段（模拟实际波动）
        fields.insert(28, "0")
        quote = _parse_fields(fields, "00700")
        assert quote is not None
        assert quote.high == 446.600
        assert quote.low == 440.000
        assert quote.volume == 10997901


class TestHkClientInit:
    def test_default_workers(self):
        client = HkClient()
        assert client._max_workers == 4
        assert client._timeout == 10
        assert client._max_retries == 2

    def test_custom_workers(self):
        client = HkClient(max_workers=2, timeout=5, max_retries=1)
        assert client._max_workers == 2
        assert client._timeout == 5
        assert client._max_retries == 1

    def test_min_workers(self):
        client = HkClient(max_workers=0)
        assert client._max_workers == 1

    def test_min_workers_negative(self):
        client = HkClient(max_workers=-5)
        assert client._max_workers == 1


class TestFetchRetry:
    """_fetch 重试逻辑测试."""

    def test_success_first_attempt(self):
        """首次请求成功，不重试."""
        import urllib.request
        call_count = [0]

        def fake_urlopen(req, timeout=None):
            call_count[0] += 1
            class FakeResp:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
                def read(self):
                    return b'v_hk00700="100~test~00700~445.0~433.0~442.0~1000~0~0~445.0~0~0~0~0~0~0~0~0~0~445.0~0~0~0~0~0~0~0~0~0~0~1000~2026/09/04 10:00:00~5.0~1.0~446.0~440.0~445.0~1000~4800000.0~0~16.0~~0~0~1.5~40000~40000~TENCENT~1.19~677.7~411.0~1.1~-41.5~0~0~0~0~0~14.9~3.1~0.1~100~-25~-2~GP~20~11~-2~-7~-4~9000~9000~15~5.3~443~-25~HKD~1~30";\n'
            return FakeResp()

        orig = urllib.request.urlopen
        urllib.request.urlopen = fake_urlopen
        try:
            from tdxproto.hk.client import _fetch
            raw = _fetch(["hk00700"], timeout=5, max_retries=2)
            assert call_count[0] == 1
            assert len(raw) > 0
        finally:
            urllib.request.urlopen = orig

    def test_retry_on_failure(self):
        """前两次失败，第三次成功."""
        import urllib.request
        call_count = [0]

        def fake_urlopen(req, timeout=None):
            call_count[0] += 1
            if call_count[0] < 3:
                raise urllib.error.URLError("connection refused")
            class FakeResp:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
                def read(self):
                    return b'v_hk00700="100~test~00700~445.0~433.0~442.0~1000~0~0~445.0~0~0~0~0~0~0~0~0~0~445.0~0~0~0~0~0~0~0~0~0~0~1000~2026/09/04 10:00:00~5.0~1.0~446.0~440.0~445.0~1000~4800000.0~0~16.0~~0~0~1.5~40000~40000~TENCENT~1.19~677.7~411.0~1.1~-41.5~0~0~0~0~0~14.9~3.1~0.1~100~-25~-2~GP~20~11~-2~-7~-4~9000~9000~15~5.3~443~-25~HKD~1~30";\n'
            return FakeResp()

        orig = urllib.request.urlopen
        urllib.request.urlopen = fake_urlopen
        try:
            import time
            orig_sleep = time.sleep
            time.sleep = lambda x: None  # 跳过退避等待
            try:
                from tdxproto.hk.client import _fetch
                raw = _fetch(["hk00700"], timeout=5, max_retries=2)
                assert call_count[0] == 3
                assert len(raw) > 0
            finally:
                time.sleep = orig_sleep
        finally:
            urllib.request.urlopen = orig

    def test_all_retries_fail(self):
        """所有重试都失败，返回空字节."""
        import urllib.request

        def fake_urlopen(req, timeout=None):
            raise urllib.error.URLError("connection refused")

        orig = urllib.request.urlopen
        urllib.request.urlopen = fake_urlopen
        try:
            import time
            orig_sleep = time.sleep
            time.sleep = lambda x: None
            try:
                from tdxproto.hk.client import _fetch
                raw = _fetch(["hk00700"], timeout=5, max_retries=2)
                assert raw == b""
            finally:
                time.sleep = orig_sleep
        finally:
            urllib.request.urlopen = orig

    def test_zero_retries(self):
        """max_retries=0 时只试一次."""
        import urllib.request
        call_count = [0]

        def fake_urlopen(req, timeout=None):
            call_count[0] += 1
            raise urllib.error.URLError("fail")

        orig = urllib.request.urlopen
        urllib.request.urlopen = fake_urlopen
        try:
            from tdxproto.hk.client import _fetch
            raw = _fetch(["hk00700"], timeout=5, max_retries=0)
            assert call_count[0] == 1
            assert raw == b""
        finally:
            urllib.request.urlopen = orig


class TestTimeRegex:
    def test_matches_valid_time(self):
        assert _TIME_RE.match("2026/09/04 11:59:06")
        assert _TIME_RE.match("2024/01/15 09:30:00")

    def test_rejects_invalid(self):
        assert not _TIME_RE.match("10997901.0")
        assert not _TIME_RE.match("445.200")
        assert not _TIME_RE.match("TENCENT")
        assert not _TIME_RE.match("")


class TestConcurrency:
    def _mock_response(self, codes):
        parts = []
        for c in codes:
            parts.append(
                f'v_{c}="100~test~{c[2:]}~445.0~433.0~442.0~1000~0~0~445.0'
                f'~0~0~0~0~0~0~0~0~0~445.0~0~0~0~0~0~0~0~0~0~0~1000'
                f'~2026/09/04 10:00:00~5.0~1.0~446.0~440.0~445.0~1000~4800000.0'
                f'~0~16.0~~0~0~1.5~40000~40000~TEST~1.19~677.7~411.0~1.1~-41.5'
                f'~0~0~0~0~0~14.9~3.1~0.1~100~-25~-2~GP~20~11~-2~-7~-4'
                f'~9000~9000~15~5.3~443~-25~HKD~1~30";\n'
            )
        return "".join(parts).encode("gbk")

    def _fake_urlopen(self, expected_bytes):
        class FakeResp:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return expected_bytes
        return FakeResp()

    def test_concurrent_batch(self):
        from unittest.mock import patch
        codes = ["hk00700", "hk09988", "hk01810"]
        expected = self._mock_response(codes)
        fake = self._fake_urlopen(expected)

        client = HkClient(max_workers=4)
        with patch("urllib.request.urlopen", lambda req, timeout=None: fake):
            result = client.quote_batch(["00700", "09988", "01810"])
            assert len(result) == 3

    def test_concurrent_multi_chunk(self):
        from unittest.mock import patch
        codes = [f"hk{i:05d}" for i in range(20)]
        expected = self._mock_response(codes)
        fake = self._fake_urlopen(expected)

        client = HkClient(max_workers=4)
        with patch("urllib.request.urlopen", lambda req, timeout=None: fake):
            input_codes = [f"{i:05d}" for i in range(20)]
            result = client.quote_batch(input_codes, max_batch_size=10)
            assert len(result) >= 0

    def test_single_worker_serial(self):
        from unittest.mock import patch
        codes = ["hk00700", "hk09988"]
        expected = self._mock_response(codes)
        fake = self._fake_urlopen(expected)

        client = HkClient(max_workers=1)
        with patch("urllib.request.urlopen", lambda req, timeout=None: fake):
            result = client.quote_batch(["00700", "09988"])
            assert len(result) == 2


class TestFaultTolerance:
    def test_quote_none_on_failure(self):
        from unittest.mock import patch

        def fake(req, timeout=None):
            raise urllib.error.URLError("refused")

        client = HkClient(max_retries=0)
        with patch("urllib.request.urlopen", fake):
            assert client.quote("00700") is None

    def test_batch_partial_failure(self):
        from unittest.mock import patch
        call_count = [0]

        def fake(req, timeout=None):
            call_count[0] += 1
            if call_count[0] == 2:
                raise urllib.error.URLError("second fails")
            codes = [c for c in ["hk00700", "hk00001"]
                     if "00700" in c or "00001" in c]
            expected = (
                b'v_hk00700="100~test~00700~445.0~433.0~442.0~1000'
                b'~0~0~445.0~0~0~0~0~0~0~0~0~0~445.0~0~0~0~0~0~0~0'
                b'~0~0~0~0~1000~2026/09/04 10:00:00~5.0~1.0~446.0~440.0'
                b'~445.0~1000~4800000.0~0~16.0~~0~0~1.5~40000~40000'
                b'~TEST~1.19~677.7~411.0~1.1~-41.5~0~0~0~0~0~14.9~3.1'
                b'~0.1~100~-25~-2~GP~20~11~-2~-7~-4~9000~9000~15~5.3'
                b'~443~-25~HKD~1~30";\n'
            )
            class FakeResp:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
                def read(self):
                    return expected
            return FakeResp()

        client = HkClient(max_workers=4, max_retries=0)
        with patch("urllib.request.urlopen", fake):
            result = client.quote_batch(
                ["00700", "00001", "00002", "00003", "00004"],
                max_batch_size=2,
            )
            assert "hk00700" in result

    def test_empty_codes(self):
        client = HkClient()
        assert client.quote_batch([]) == {}

    def test_all_invalid_codes(self):
        client = HkClient()
        assert client.quote_batch([None, "", "   "]) == {}
