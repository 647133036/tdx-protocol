"""通达信服务器IP健康监控与优选工具。

功能:
  1. 定期扫描IP池, 测试TCP连通性和协议握手
  2. 维护有效IP池, 按延迟排序
  3. 持久化IP池到JSON文件
  4. 自动剔除失效IP, 补充新发现IP
  5. 提供IP优选API供StockClient/FuturesClient使用
"""

import json
import os
import socket
import struct
import threading
import time
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from .hosts import STOCK_HOSTS_LARGE, FUTURES_HOSTS_LARGE, STOCK_HOSTS_FAST, FUTURES_HOSTS_FAST
from .scanner import (
    ProbeResult, scan_stock, scan_futures,
    DEFAULT_TIMEOUT, DEFAULT_WORKERS,
)


# 健康状态
HEALTH_OK = "ok"
HEALTH_DEGRADED = "degraded"
HEALTH_DOWN = "down"

# 持久化文件路径
DEFAULT_IP_CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", ".cache", "tdx_hosts.json")


@dataclass
class HostEntry:
    """单个主机条目, 带健康统计。"""
    host: str
    port: int
    protocol: str  # "7709" or "7727"
    tcp_ok: bool = False
    tcp_latency_ms: float = 0.0
    handshake_ok: bool = False
    handshake_latency_ms: float = 0.0
    status: str = HEALTH_DOWN
    last_check: float = 0.0  # Unix timestamp
    consecutive_failures: int = 0
    total_checks: int = 0
    success_rate: float = 0.0
    avg_handshake_ms: float = 0.0
    _total_latency_sum: float = 0.0  # transient, not serialized

    @classmethod
    def from_probe(cls, result: ProbeResult, protocol: str) -> "HostEntry":
        """从ProbeResult创建HostEntry。"""
        addr, port = result.host.rsplit(":", 1)
        port = int(port)
        
        if result.ok:
            status = HEALTH_OK if result.latency_ms < 200 else HEALTH_DEGRADED
        else:
            status = HEALTH_DOWN
        
        return cls(
            host=result.host,
            port=port,
            protocol=protocol,
            tcp_ok=result.tcp_ok,
            tcp_latency_ms=result.tcp_latency_ms,
            handshake_ok=result.handshake_ok,
            handshake_latency_ms=result.handshake_latency_ms,
            status=status,
            last_check=time.time(),
            total_checks=1,
            success_rate=1.0 if result.ok else 0.0,
            avg_handshake_ms=result.handshake_latency_ms if result.ok else 0.0,
            _total_latency_sum=result.handshake_latency_ms if result.ok else 0.0,
        )

    def update(self, result: ProbeResult):
        """更新健康统计。"""
        self.tcp_ok = result.tcp_ok
        self.tcp_latency_ms = result.tcp_latency_ms
        self.handshake_ok = result.handshake_ok
        self.handshake_latency_ms = result.handshake_latency_ms
        self.last_check = time.time()
        self.total_checks += 1
        
        if result.ok:
            self.consecutive_failures = 0
            self.success_rate = (
                (self.success_rate * (self.total_checks - 1) + 1.0) / self.total_checks
            )
            self._total_latency_sum += result.handshake_latency_ms
            self.avg_handshake_ms = self._total_latency_sum / self.total_checks
            self.status = HEALTH_OK if result.latency_ms < 200 else HEALTH_DEGRADED
        else:
            self.consecutive_failures += 1
            self.success_rate = (
                (self.success_rate * (self.total_checks - 1)) / self.total_checks
            )
            if self.consecutive_failures >= 3:
                self.status = HEALTH_DOWN
            elif self.consecutive_failures >= 1:
                self.status = HEALTH_DEGRADED

    def to_dict(self) -> dict:
        """序列化为字典。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "HostEntry":
        """从字典反序列化（兼容旧缓存不含 _total_latency_sum）。"""
        if "_total_latency_sum" not in d:
            d["_total_latency_sum"] = d.get("avg_handshake_ms", 0) * max(d.get("total_checks", 1), 1)
        return cls(**d)

    def __lt__(self, other: "HostEntry") -> bool:
        """排序: 优先ok, 然后按延迟, 然后按成功率。"""
        if self.status != other.status:
            order = {HEALTH_OK: 0, HEALTH_DEGRADED: 1, HEALTH_DOWN: 2}
            return order.get(self.status, 3) < order.get(other.status, 3)
        if self.handshake_ok and other.handshake_ok:
            return self.handshake_latency_ms < other.handshake_latency_ms
        if self.handshake_ok:
            return True
        if other.handshake_ok:
            return False
        return self.success_rate > other.success_rate


@dataclass
class HostPool:
    """IP池管理器。"""
    entries: dict[str, HostEntry] = field(default_factory=dict)  # key: "ip:port"
    
    def add(self, entry: HostEntry):
        """添加或更新主机条目。"""
        self.entries[f"{entry.host}"] = entry
    
    def get_ok_hosts(self, protocol: Optional[str] = None) -> list[HostEntry]:
        """获取所有健康的IP, 按延迟排序。"""
        hosts = [e for e in self.entries.values() if e.status == HEALTH_OK]
        if protocol:
            hosts = [e for e in hosts if e.protocol == protocol]
        hosts.sort()
        return hosts
    
    def get_any_hosts(self, protocol: Optional[str] = None) -> list[HostEntry]:
        """获取所有可用IP(ok+degraded), 按优先级排序。"""
        hosts = [e for e in self.entries.values() if e.status in (HEALTH_OK, HEALTH_DEGRADED)]
        if protocol:
            hosts = [e for e in hosts if e.protocol == protocol]
        hosts.sort()
        return hosts
    
    def get_all_hosts(self, protocol: Optional[str] = None) -> list[HostEntry]:
        """获取所有IP。"""
        hosts = list(self.entries.values())
        if protocol:
            hosts = [e for e in hosts if e.protocol == protocol]
        hosts.sort()
        return hosts
    
    def to_dict(self) -> dict:
        """序列化为字典。"""
        return {k: v.to_dict() for k, v in self.entries.items()}
    
    @classmethod
    def from_dict(cls, d: dict) -> "HostPool":
        """从字典反序列化。"""
        pool = cls()
        for k, v in d.items():
            pool.entries[k] = HostEntry.from_dict(v)
        return pool


class HostManager:
    """通达信服务器IP健康管理器。
    
    功能:
      - 加载持久化IP池
      - 定期扫描更新
      - 提供优选IP
      - 自动故障转移
    """
    
    def __init__(self, cache_path: str = DEFAULT_IP_CACHE_PATH):
        self.cache_path = cache_path
        self.pool = HostPool()
        self._load_cache()
    
    def _load_cache(self):
        """从缓存文件加载IP池。"""
        path = Path(self.cache_path)
        if path.exists() and path.stat().st_size > 0:
            try:
                data = json.loads(path.read_text())
                self.pool = HostPool.from_dict(data)
            except (json.JSONDecodeError, Exception):
                self.pool = HostPool()
    
    def save_cache(self):
        """保存IP池到缓存文件。"""
        path = Path(self.cache_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.pool.to_dict()
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    
    def scan_and_update(
        self,
        stock_hosts: Optional[list[str]] = None,
        futures_hosts: Optional[list[str]] = None,
        workers: int = DEFAULT_WORKERS,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> tuple[list[HostEntry], list[HostEntry]]:
        """扫描IP池并更新健康状态。
        
        Returns:
            (stock_entries, futures_entries) 排序后的健康IP列表
        """
        stock_hosts = stock_hosts or STOCK_HOSTS_LARGE
        futures_hosts = futures_hosts or FUTURES_HOSTS_LARGE
        
        # 扫描股票服务器
        stock_results = scan_stock(stock_hosts, workers=workers, timeout=timeout)
        for result in stock_results:
            entry = HostEntry.from_probe(result, "7709")
            existing = self.pool.entries.get(result.host)
            if existing:
                existing.update(result)
            else:
                self.pool.add(entry)

        # 扫描期货服务器
        futures_results = scan_futures(futures_hosts, workers=workers, timeout=timeout)
        for result in futures_results:
            entry = HostEntry.from_probe(result, "7727")
            existing = self.pool.entries.get(result.host)
            if existing:
                existing.update(result)
            else:
                self.pool.add(entry)
        
        # 保存缓存
        self.save_cache()
        
        # 返回排序后的健康IP
        stock_ok = self.pool.get_ok_hosts("7709")
        futures_ok = self.pool.get_ok_hosts("7727")
        
        return stock_ok, futures_ok
    
    def get_best_stock_host(self) -> Optional[HostEntry]:
        """获取最快的股票服务器IP。"""
        hosts = self.pool.get_ok_hosts("7709")
        return hosts[0] if hosts else None
    
    def get_best_futures_host(self) -> Optional[HostEntry]:
        """获取最快的期货服务器IP。"""
        hosts = self.pool.get_ok_hosts("7727")
        return hosts[0] if hosts else None
    
    def get_fallback_stock_host(self) -> Optional[HostEntry]:
        """获取备用的股票服务器IP(ok或degraded)。"""
        hosts = self.pool.get_any_hosts("7709")
        return hosts[0] if hosts else None
    
    def get_fallback_futures_host(self) -> Optional[HostEntry]:
        """获取备用的期货服务器IP(ok或degraded)。"""
        hosts = self.pool.get_any_hosts("7727")
        return hosts[0] if hosts else None
    
    def rotate_stock_host(self, current: Optional[HostEntry] = None) -> HostEntry:
        """轮询切换股票服务器IP。
        
        如果当前IP连续失败>=3次, 切换到下一个。
        """
        hosts = self.pool.get_ok_hosts("7709")
        if not hosts:
            hosts = self.pool.get_any_hosts("7709")
        
        if not hosts:
            raise RuntimeError("No available stock hosts")
        
        if current and current in hosts:
            idx = hosts.index(current)
            next_idx = (idx + 1) % len(hosts)
            return hosts[next_idx]
        
        return hosts[0]
    
    def rotate_futures_host(self, current: Optional[HostEntry] = None) -> HostEntry:
        """轮询切换期货服务器IP。"""
        hosts = self.pool.get_ok_hosts("7727")
        if not hosts:
            hosts = self.pool.get_any_hosts("7727")
        
        if not hosts:
            raise RuntimeError("No available futures hosts")
        
        if current and current in hosts:
            idx = hosts.index(current)
            next_idx = (idx + 1) % len(hosts)
            return hosts[next_idx]
        
        return hosts[0]
    
    def get_status_report(self) -> dict:
        """获取IP池状态报告。"""
        stock_ok = len([e for e in self.pool.entries.values() 
                       if e.protocol == "7709" and e.status == HEALTH_OK])
        stock_degraded = len([e for e in self.pool.entries.values() 
                             if e.protocol == "7709" and e.status == HEALTH_DEGRADED])
        stock_down = len([e for e in self.pool.entries.values() 
                         if e.protocol == "7709" and e.status == HEALTH_DOWN])
        
        futures_ok = len([e for e in self.pool.entries.values() 
                         if e.protocol == "7727" and e.status == HEALTH_OK])
        futures_degraded = len([e for e in self.pool.entries.values() 
                               if e.protocol == "7727" and e.status == HEALTH_DEGRADED])
        futures_down = len([e for e in self.pool.entries.values() 
                           if e.protocol == "7727" and e.status == HEALTH_DOWN])
        
        return {
            "stock": {
                "ok": stock_ok,
                "degraded": stock_degraded,
                "down": stock_down,
                "total": len([e for e in self.pool.entries.values() if e.protocol == "7709"]),
            },
            "futures": {
                "ok": futures_ok,
                "degraded": futures_degraded,
                "down": futures_down,
                "total": len([e for e in self.pool.entries.values() if e.protocol == "7727"]),
            },
            "best_stock": self.get_best_stock_host().host if self.get_best_stock_host() else None,
            "best_futures": self.get_best_futures_host().host if self.get_best_futures_host() else None,
        }


# 全局单例
_manager: Optional[HostManager] = None
_manager_lock = threading.Lock()

def get_manager(cache_path: str = DEFAULT_IP_CACHE_PATH) -> HostManager:
    """获取全局HostManager单例。"""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = HostManager(cache_path)
    return _manager

def reset_manager():
    """重置全局管理器(用于测试)。"""
    global _manager
    _manager = None


def scan_hosts(
    stock_hosts: Optional[list[str]] = None,
    futures_hosts: Optional[list[str]] = None,
    workers: int = DEFAULT_WORKERS,
    timeout: float = DEFAULT_TIMEOUT,
    cache_path: str = DEFAULT_IP_CACHE_PATH,
) -> tuple[list[HostEntry], list[HostEntry]]:
    """扫描IP池并返回健康IP列表。
    
    Args:
        stock_hosts: 股票服务器IP列表
        futures_hosts: 期货服务器IP列表
        workers: 并发扫描线程数
        timeout: 超时时间(秒)
        cache_path: 缓存文件路径
    
    Returns:
        (stock_entries, futures_entries) 排序后的健康IP列表
    """
    manager = HostManager(cache_path)
    return manager.scan_and_update(
        stock_hosts=stock_hosts,
        futures_hosts=futures_hosts,
        workers=workers,
        timeout=timeout,
    )


def print_status(report: dict):
    """打印IP池状态报告。"""
    print("=" * 60)
    print("通达信服务器IP健康状态报告")
    print("=" * 60)
    
    stock = report["stock"]
    print(f"\n[A股 7709] 总计:{stock['total']} OK:{stock['ok']} 降级:{stock['degraded']} 宕机:{stock['down']}")
    if report["best_stock"]:
        entry = next((e for e in get_manager().pool.entries.values() 
                     if e.host == report["best_stock"]), None)
        if entry:
            print(f"  最快: {entry.host} ({entry.handshake_latency_ms:.1f}ms)")
    
    futures = report["futures"]
    print(f"\n[期货 7727] 总计:{futures['total']} OK:{futures['ok']} 降级:{futures['degraded']} 宕机:{futures['down']}")
    if report["best_futures"]:
        entry = next((e for e in get_manager().pool.entries.values() 
                     if e.host == report["best_futures"]), None)
        if entry:
            print(f"  最快: {entry.host} ({entry.handshake_latency_ms:.1f}ms)")
    
    print("=" * 60)


if __name__ == "__main__":
    # 运行扫描
    stock_entries, futures_entries = scan_hosts()
    
    # 打印报告
    manager = get_manager()
    report = manager.get_status_report()
    print_status(report)
    
    # 打印详细列表
    print(f"\n股票服务器 ({len(stock_entries)} 个健康):")
    for entry in stock_entries[:5]:
        print(f"  {entry.host} - {entry.handshake_latency_ms:.1f}ms (成功率:{entry.success_rate:.0%})")
    
    print(f"\n期货服务器 ({len(futures_entries)} 个健康):")
    for entry in futures_entries[:5]:
        print(f"  {entry.host} - {entry.handshake_latency_ms:.1f}ms (成功率:{entry.success_rate:.0%})")
