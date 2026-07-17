"""IP健康监控系统测试。"""
import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tdxproto.ip_health import (
    HostEntry, HostPool, HostManager,
    scan_hosts, get_manager, reset_manager,
    print_status,
    HEALTH_OK, HEALTH_DEGRADED, HEALTH_DOWN,
)
from tdxproto.scanner import ProbeResult


class TestHostEntry:
    """HostEntry 单元测试。"""

    def test_from_probe_ok(self):
        result = ProbeResult(
            host="1.2.3.4:7709", port=7709,
            tcp_ok=True, tcp_latency_ms=1.5,
            handshake_ok=True, handshake_latency_ms=50.0,
        )
        entry = HostEntry.from_probe(result, "7709")
        assert entry.status == HEALTH_OK
        assert entry.tcp_ok is True
        assert entry.handshake_latency_ms == 50.0
        assert entry.total_checks == 1
        assert entry.success_rate == 1.0

    def test_from_probe_failed(self):
        result = ProbeResult(
            host="1.2.3.4:7709", port=7709,
            tcp_ok=True, tcp_latency_ms=1.0,
            handshake_ok=False, handshake_latency_ms=0.0,
            error="timeout",
        )
        entry = HostEntry.from_probe(result, "7709")
        assert entry.status == HEALTH_DOWN
        assert entry.handshake_ok is False

    def test_update_success(self):
        entry = HostEntry(host="1.2.3.4:7709", port=7709, protocol="7709",
                         handshake_ok=True, _total_latency_sum=0.0)
        result = ProbeResult(
            host="1.2.3.4:7709", port=7709,
            tcp_ok=True, handshake_ok=True, handshake_latency_ms=30.0,
        )
        entry.update(result)
        # update() sets total_checks=1 when entry was newly created
        assert entry.total_checks >= 1
        assert entry.handshake_ok is True
        assert entry.status == HEALTH_OK

    def test_update_failure(self):
        entry = HostEntry(host="1.2.3.4:7709", port=7709, protocol="7709",
                         status=HEALTH_OK, _total_latency_sum=100.0)
        result = ProbeResult(host="1.2.3.4:7709", port=7709, handshake_ok=False)
        
        for _ in range(3):
            entry.update(result)
        
        assert entry.consecutive_failures == 3
        assert entry.status == HEALTH_DOWN

    def test_serialization(self):
        entry = HostEntry(
            host="1.2.3.4:7709", port=7709, protocol="7709",
            tcp_ok=True, handshake_ok=True,
            handshake_latency_ms=45.0, status=HEALTH_OK,
            total_checks=5, success_rate=0.8,
            _total_latency_sum=225.0,
        )
        d = entry.to_dict()
        assert d["_total_latency_sum"] == 225.0
        assert d["host"] == "1.2.3.4:7709"
        
        restored = HostEntry.from_dict(d)
        assert restored.host == entry.host
        assert restored.port == entry.port
        assert restored.protocol == entry.protocol

    def test_sorting(self):
        e1 = HostEntry(host="a:7709", port=7709, protocol="7709",
                       status=HEALTH_OK, handshake_latency_ms=100.0,
                       handshake_ok=True, _total_latency_sum=100.0)
        e2 = HostEntry(host="b:7709", port=7709, protocol="7709",
                       status=HEALTH_OK, handshake_latency_ms=50.0,
                       handshake_ok=True, _total_latency_sum=50.0)
        e3 = HostEntry(host="c:7709", port=7709, protocol="7709",
                       status=HEALTH_DEGRADED, handshake_latency_ms=100.0,
                       handshake_ok=True, _total_latency_sum=100.0)
        
        assert e2 < e1  # lower latency
        assert e1 < e3  # ok < degraded


class TestHostPool:
    """HostPool 单元测试。"""

    def test_add_and_get(self):
        pool = HostPool()
        entry = HostEntry(host="1.2.3.4:7709", port=7709, protocol="7709")
        pool.add(entry)
        
        assert len(pool.entries) == 1
        assert "1.2.3.4:7709" in pool.entries

    def test_filter_by_protocol(self):
        pool = HostPool()
        pool.add(HostEntry(host="a:7709", port=7709, protocol="7709"))
        pool.add(HostEntry(host="b:7709", port=7709, protocol="7709"))
        pool.add(HostEntry(host="c:7727", port=7727, protocol="7727"))
        
        stock = pool.get_all_hosts("7709")
        futures = pool.get_all_hosts("7727")
        
        assert len(stock) == 2
        assert len(futures) == 1

    def test_get_ok_hosts_sorted(self):
        pool = HostPool()
        pool.add(HostEntry(host="a:7709", port=7709, protocol="7709",
                          status=HEALTH_OK, handshake_latency_ms=100.0,
                          handshake_ok=True, _total_latency_sum=100.0))
        pool.add(HostEntry(host="b:7709", port=7709, protocol="7709",
                          status=HEALTH_OK, handshake_latency_ms=50.0,
                          handshake_ok=True, _total_latency_sum=50.0))
        pool.add(HostEntry(host="c:7709", port=7709, protocol="7709",
                          status=HEALTH_DOWN, handshake_latency_ms=0.0,
                          handshake_ok=False, _total_latency_sum=0.0))
        
        ok = pool.get_ok_hosts("7709")
        assert len(ok) == 2
        assert ok[0].host == "b:7709"  # fastest first
        assert ok[1].host == "a:7709"


class TestHostManager:
    """HostManager 测试 - 使用隔离的缓存文件。"""

    def test_cache_roundtrip(self, tmp_path):
        cache_file = tmp_path / "test_hosts.json"
        manager = HostManager(str(cache_file))
        
        entry = HostEntry(
            host="1.2.3.4:7709", port=7709, protocol="7709",
            status=HEALTH_OK, handshake_latency_ms=30.0,
            total_checks=10, success_rate=0.9,
            _total_latency_sum=300.0,
        )
        manager.pool.add(entry)
        manager.save_cache()
        
        assert cache_file.exists()
        data = json.loads(cache_file.read_text())
        assert "1.2.3.4:7709" in data
        
        manager2 = HostManager(str(cache_file))
        assert "1.2.3.4:7709" in manager2.pool.entries

    def test_get_best_hosts_empty(self, tmp_path):
        cache_file = tmp_path / "empty.json"
        manager = HostManager(str(cache_file))
        assert manager.get_best_stock_host() is None
        assert manager.get_best_futures_host() is None

    def test_status_report(self, tmp_path):
        cache_file = tmp_path / "report.json"
        manager = HostManager(str(cache_file))
        manager.pool.add(HostEntry(host="a:7709", port=7709, protocol="7709",
                                  status=HEALTH_OK, handshake_latency_ms=30.0,
                                  _total_latency_sum=30.0))
        manager.pool.add(HostEntry(host="b:7709", port=7709, protocol="7709",
                                  status=HEALTH_DOWN, handshake_latency_ms=0.0,
                                  _total_latency_sum=0.0))
        manager.pool.add(HostEntry(host="c:7727", port=7727, protocol="7727",
                                  status=HEALTH_OK, handshake_latency_ms=50.0,
                                  _total_latency_sum=50.0))
        
        report = manager.get_status_report()
        assert report["stock"]["ok"] == 1
        assert report["stock"]["down"] == 1
        assert report["futures"]["ok"] == 1
        assert report["best_stock"] == "a:7709"
        assert report["best_futures"] == "c:7727"

    def test_rotate_stock_host(self, tmp_path):
        cache_file = tmp_path / "rotate.json"
        manager = HostManager(str(cache_file))
        for i in range(3):
            manager.pool.add(HostEntry(
                host=f"10.0.0.{i}:7709", port=7709, protocol="7709",
                status=HEALTH_OK, handshake_latency_ms=30.0 + i * 10,
                _total_latency_sum=30.0 + i * 10,
            ))
        
        h1 = manager.rotate_stock_host()
        assert h1.host == "10.0.0.0:7709"
        
        h2 = manager.rotate_stock_host(h1)
        assert h2.host == "10.0.0.1:7709"
        
        h3 = manager.rotate_stock_host(h2)
        assert h3.host == "10.0.0.2:7709"

    def test_scan_and_update(self, tmp_path):
        """扫描实际IP(需要网络)。"""
        cache_file = tmp_path / "scan_test.json"
        manager = HostManager(str(cache_file))
        stock_entries, futures_entries = manager.scan_and_update(
            stock_hosts=["150.158.160.2:7709"],
            futures_hosts=["116.205.143.214:7727"],
            workers=2,
            timeout=3.0,
        )
        # 可能网络不通, 不强制断言


class TestScanHostsFunction:
    """scan_hosts 函数测试。"""

    def test_returns_sorted_entries(self, tmp_path):
        cache_file = str(tmp_path / "test.json")
        stock_entries, futures_entries = scan_hosts(
            stock_hosts=["150.158.160.2:7709"],
            workers=1,
            timeout=3.0,
            cache_path=cache_file,
        )
        if stock_entries:
            for i in range(len(stock_entries) - 1):
                assert stock_entries[i].handshake_latency_ms <= stock_entries[i+1].handshake_latency_ms


class TestGetManager:
    """单例测试。"""

    def teardown_method(self):
        reset_manager()

    def test_singleton(self):
        m1 = get_manager()
        m2 = get_manager()
        assert m1 is m2

    def test_reset(self):
        m1 = get_manager()
        reset_manager()
        m2 = get_manager()
        assert m1 is not m2
