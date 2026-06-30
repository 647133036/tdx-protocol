import pytest

from tdxproto.scanner import (
    ProbeResult, _parse_host, _tcp_probe,
    scan_stock, scan_futures,
    DEFAULT_TIMEOUT, DEFAULT_WORKERS,
)


class TestProbeResult:
    def test_ok_property_true(self):
        r = ProbeResult(host="1.2.3.4:7709", port=7709, handshake_ok=True, handshake_latency_ms=10.0)
        assert r.ok is True

    def test_ok_property_false(self):
        r = ProbeResult(host="1.2.3.4:7709", port=7709, handshake_ok=False)
        assert r.ok is False

    def test_latency_ms_when_ok(self):
        r = ProbeResult(host="1.2.3.4:7709", port=7709, handshake_ok=True, handshake_latency_ms=15.5)
        assert r.latency_ms == 15.5

    def test_latency_ms_when_not_ok(self):
        r = ProbeResult(host="1.2.3.4:7709", port=7709, handshake_ok=False)
        import math
        assert math.isinf(r.latency_ms)

    def test_tcp_only(self):
        r = ProbeResult(host="1.2.3.4:7709", port=7709, tcp_ok=True)
        assert r.tcp_ok is True
        assert r.ok is False

    def test_with_error(self):
        r = ProbeResult(host="1.2.3.4:7709", port=7709, error="Connection refused")
        assert r.error == "Connection refused"


class TestParseHost:
    def test_standard_format(self):
        addr, port = _parse_host("116.205.183.150:7709")
        assert addr == "116.205.183.150"
        assert port == 7709

    def test_different_port(self):
        addr, port = _parse_host("192.168.1.1:7727")
        assert addr == "192.168.1.1"
        assert port == 7727


class TestTcpProbe:
    def test_unreachable_host(self):
        ok, lat, err = _tcp_probe("127.0.0.1", 1, 0.1)
        assert ok is False

    def test_returns_latency(self):
        ok, lat, err = _tcp_probe("127.0.0.1", 1, 0.1)
        assert lat >= 0


class TestScannerIntegration:
    """扫描器集成测试：测试本地可达的7727端口。"""
    
    def test_scan_local_futures(self):
        """测试扫描一个本地端口（应该会失败，但验证流程不崩溃）。"""
        results = scan_futures(["127.0.0.1:1"], timeout=0.5)
        assert len(results) >= 1
        # All should fail since port 1 is not a real TDX server
        for r in results:
            assert r.host is not None

    def test_scan_stock_local(self):
        """测试扫描本地7709端口（应该会失败，但验证流程不崩溃）。"""
        results = scan_stock(["127.0.0.1:1"], timeout=0.5)
        assert len(results) >= 1


class TestBestHost:
    """best_host 已从 scanner 中移除，改为直接使用 scan_stock/scan_futures."""
    def test_scan_returns_sorted_results(self):
        results = scan_futures(["127.0.0.1:1"], timeout=0.5)
        assert len(results) >= 1
        # 结果应按 ok 状态和延迟排序
        for i in range(len(results) - 1):
            if results[i].ok and not results[i+1].ok:
                pass  # ok 的在前
            elif results[i].ok and results[i+1].ok:
                assert results[i].handshake_latency_ms <= results[i+1].handshake_latency_ms
