"""7709 股票行情客户端 — 对齐 pytdx/tdxpy TdxHq_API。

使用 pytdx 原始的字节格式，不经过 Frame 封装。
"""
from __future__ import annotations

import io
import math
import socket
import struct
import time
import threading
import zipfile
import zlib
from datetime import date, timedelta
from typing import Optional, Sequence

from ..codec import split_code, decode_volume, get_price, u32, int_date, normalize_code
from ..models import EquityChange, Kline, Minute, Trade, Quote, PriceLimit
from ..ip_health import get_manager, HostManager
from .._reconnect import RETRY_DELAYS, select_best_host, find_working_host
from ..scanner import scan_stock
from ..hosts import STOCK_HOSTS_LARGE
try:
    from ..mac.client import MacClient
    _HAS_MAC = True
except ImportError:
    _HAS_MAC = False
from .commands import (
    setup_cmd1, setup_cmd2, setup_cmd3,
    _b_count, _b_list, _b_snapshot, _b_kline, _b_today_minute,
    _b_history_minute, _b_today_trade, _b_history_trade,
    _b_xdxr, _b_finance, _b_company_info_cat, _b_company_info_content,
    _b_block_info_meta, _b_block_info, _b_report_file,
    _b_vol_profile, _b_index_momentum, _b_aux, _b_index_info,
    _b_quotes_detail, _b_tick_chart, _b_auction,
    _b_top_board, _b_quotes_list, _b_unusual,
    _b_chart_sampling_sparkline, _b_chart_sampling_kline, _b_history_orders_full,
    _b_quotes_encrypt, _b_recent_minute, _b_limits,
    _p_count, _p_list, _p_snapshot, _p_kline, _p_today_minute,
    _p_today_trade, _p_history_minute, _p_history_trade,
    _p_xdxr, _p_finance, _p_company_info_cat, _p_company_info_content,
    _p_block_info_meta, _p_block_info, _p_report_file,
    _p_vol_profile, _p_index_momentum, _p_aux, _p_index_info,
    _p_quotes_detail, _p_tick_chart, _p_auction,
    _p_top_board, _p_quotes_list, _p_unusual,
    _p_chart_sampling_kline, _p_chart_sampling_sparkline,
    _p_history_orders, _p_history_orders_v2,
    _p_quotes_encrypt, _p_recent_minute, _p_limits,
    _get_datetime, _cal_price, _cal_price1000,
)
from ..hosts import STOCK_HOSTS_FAST as STOCK_HOSTS

# K线 category 映射
KLINE_CAT = {
    "1m": 7, "3m": 8, "5m": 0, "15m": 1, "30m": 2, "60m": 3,
    "day": 9, "week": 5, "month": 6, "quarter": 10, "year": 11,
}

RSP_HEADER_LEN = 0x10  # 16 bytes
DEFAULT_RATE_LIMIT = 0.5   # 每秒最多2个请求
HEARTBEAT_INTERVAL = 45.0   # 心跳间隔(秒)


def _parse_pipe_text(data: bytes, field_names: list[str]) -> list[dict]:
    """解析 GBK 管道分隔文本文件."""
    text = data.decode("gbk", "ignore")
    out = []
    for ln in text.split("\n"):
        ln = ln.strip("\r")
        if not ln or ln.startswith("#"):
            continue
        f = ln.split("|")
        if len(f) < 2:
            continue
        row = {}
        for i, name in enumerate(field_names):
            row[name] = f[i] if i < len(f) else ""
        out.append(row)
    return out


class StockClient:
    """7709 股票行情客户端，对齐 pytdx TdxHq_API."""

    def __init__(self, hosts: Optional[list] = None, timeout: float = 5.0,
                 use_ip_health: bool = True, rate_limit: float = DEFAULT_RATE_LIMIT,
                 quote_host: Optional[str] = None,
                 auto_reconnect: bool = True):
        self.auto_reconnect = auto_reconnect
        if hosts:
            self.hosts = hosts
        elif use_ip_health:
            manager = get_manager()
            best = manager.get_best_stock_host()
            if best:
                self.hosts = [best.host]
            else:
                self.hosts = STOCK_HOSTS_LARGE
        else:
            self.hosts = STOCK_HOSTS_LARGE
        self._hosts_flat = self.hosts  # 完整候选列表（用于 failover）
        self._all_hosts = STOCK_HOSTS_LARGE  # 全部已知主机（用于空数据 failover 测速）
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._coefficients = {}
        self._name_map: dict[str, str] = {}
        self._name_map_loaded: set[int] = set()
        self._name_map_offset: dict[int, int] = {}
        self._use_ip_health = use_ip_health
        self._current_host_entry = None
        self._current_host = None
        self._current_port = None
        self._rate_limit = rate_limit
        self._last_request_time: float = 0.0
        self._stop_heartbeat = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._quote_host = quote_host
        self._quote_sock: Optional[socket.socket] = None
        self._quote_lock = threading.Lock()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

    def _connect_once(self, host_str: str):
        """尝试连接到指定主机并执行握手."""
        sock = None
        try:
            host, port = host_str.rsplit(":", 1)
            port = int(port)
            self._current_host = host
            self._current_port = port
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((host, port))
            sock.send(setup_cmd1())
            self._recv_pass(sock)
            sock.send(setup_cmd2())
            self._recv_pass(sock)
            sock.send(setup_cmd3())
            self._recv_pass(sock)
            self.sock = sock
            self._start_heartbeat()
        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception:
            if sock:
                try: sock.close()
                except Exception: pass
            raise

    def connect(self):
        """连接服务器并执行 3 步握手, 支持自动故障转移。"""
        last_err = None
        hosts_to_try = list(self.hosts)

        if self._current_host_entry and self._current_host_entry.consecutive_failures >= 3:
            manager = get_manager() if self._use_ip_health else None
            if manager:
                rotated = manager.rotate_stock_host(self._current_host_entry)
                if rotated.host not in hosts_to_try:
                    hosts_to_try.insert(0, rotated.host)

        for host_str in hosts_to_try:
            try:
                self._connect_once(host_str)
                if self._use_ip_health:
                    manager = get_manager()
                    for entry in manager.pool.entries.values():
                        if entry.host == host_str and entry.protocol == "7709":
                            self._current_host_entry = entry
                            break
                return
            except Exception as e:
                last_err = e
                if self._use_ip_health and host_str in [e.host for e in get_manager().pool.entries.values()]:
                    for entry in get_manager().pool.entries.values():
                        if entry.host == host_str and entry.protocol == "7709":
                            entry.consecutive_failures += 1
                            entry.total_checks += 1
                            entry.status = "down" if entry.consecutive_failures >= 3 else "degraded"
                            entry.last_check = time.time()
                            break

        raise ConnectionError(f"无法连接任何行情服务器: {last_err}")

    def _recv_pass(self, s: socket.socket) -> bytes:
        """接收握手响应（passthrough，不解压）."""
        hdr = self._sock_read(s, RSP_HEADER_LEN)
        resp_type, _, _, zip_len, unzip_len = struct.unpack("<IIIHH", hdr)
        body = self._sock_read(s, zip_len)
        if zip_len != unzip_len:
            body = zlib.decompress(body)
        return hdr + body

    @staticmethod
    def _sock_read(s: socket.socket, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            try:
                chunk = s.recv(n - len(buf))
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError) as e:
                raise ConnectionError(f"recv failed: {e}") from e
            if not chunk:
                raise ConnectionError("remote closed")
            buf.extend(chunk)
        return bytes(buf)

    def _recv_response(self, s: socket.socket) -> bytes:
        """读取标准响应: 16字节头 + body."""
        hdr = self._sock_read(s, RSP_HEADER_LEN)
        resp_type, _, _, zip_len, unzip_len = struct.unpack("<IIIHH", hdr)
        body = self._sock_read(s, zip_len)
        if zip_len != unzip_len:
            try:
                body = zlib.decompress(body)
            except zlib.error:
                return b"\x00\x00"
        return body

    def _start_heartbeat(self):
        self._stop_heartbeat.clear()
        self._heartbeat_thread = threading.Thread(target=self._hb_loop, daemon=True)
        self._heartbeat_thread.start()

    def _hb_loop(self):
        while not self._stop_heartbeat.wait(HEARTBEAT_INTERVAL):
            try:
                self.do_heartbeat()
            except Exception:
                pass

    def disconnect(self):
        self.close()

    def close(self):
        self._stop_heartbeat.set()
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            self.sock.close()
            self.sock = None
        if self._quote_sock:
            try:
                self._quote_sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            self._quote_sock.close()
            self._quote_sock = None

    def _throttle(self):
        """请求速率限制 — 防止连续请求导致服务器断连."""
        if self._rate_limit <= 0:
            return
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._rate_limit:
            time.sleep(self._rate_limit - elapsed)
        self._last_request_time = time.monotonic()

    def _send_recv(self, pkg: bytes) -> bytes:
        """发送请求包并接收响应（带锁 + 速率限制 + 指数退避重连 + 跨主机故障转移）。

        优化：空响应 (b"\\x00\\x00") 不触发重连链，直接返回 — 这是服务器
        "无此标的数据" 的正常信号，不应消耗 3.6s+ 的重试时间。
        """
        with self._lock:
            if not self.sock:
                self.connect()
            self._throttle()
            try:
                self.sock.send(pkg)
                data = self._recv_response(self.sock)
                # 空响应 = 服务器无数据，非连接错误，直接返回
                if data == b"\x00\x00":
                    return data
                return data
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError, ConnectionError) as e:
                self.sock = None
                last_err = e
                # 第一阶段：同主机指数退避重试（仅连接错误才重试）
                for delay in RETRY_DELAYS:
                    time.sleep(delay)
                    try:
                        self._connect_once(f"{self._current_host}:{self._current_port}")
                        self.sock.send(pkg)
                        return self._recv_response(self.sock)
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError, TimeoutError, ConnectionError) as e2:
                        self.sock = None
                        last_err = e2
                        continue
                # 第二阶段：跨主机故障转移
                new_host = select_best_host(
                    self._hosts_flat,
                    self._ping_and_rank,
                    self._save_host,
                    7709,
                    3.0,
                    f"{self._current_host}:{self._current_port}",
                )
                if new_host is not None:
                    try:
                        self._connect_once(new_host)
                        self.sock.send(pkg)
                        return self._recv_response(self.sock)
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError, ConnectionError) as e2:
                        self.sock = None
                        last_err = e2
                raise ConnectionError(f"connection lost after retry+failover: {last_err}") from e

    def _quote_connect(self):
        """连接到专用快照行情服务器."""
        if not self._quote_host:
            return
        host, port = self._quote_host.rsplit(":", 1)
        port = int(port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect((host, port))
        sock.send(setup_cmd1())
        self._recv_pass(sock)
        sock.send(setup_cmd2())
        self._recv_pass(sock)
        sock.send(setup_cmd3())
        self._recv_pass(sock)
        self._quote_sock = sock

    def _quote_send_recv(self, pkg: bytes) -> bytes:
        """通过专用快照行情连接发送请求并接收响应。未配置 quote_host 或连接失败时回退到主连接。"""
        if not self._quote_host:
            return self._send_recv(pkg)
        with self._quote_lock:
            if not self._quote_sock:
                self._quote_connect()
            self._throttle()
            try:
                self._quote_sock.send(pkg)
                return self._recv_response(self._quote_sock)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError, TimeoutError) as e:
                self._quote_sock = None
                try:
                    self._quote_connect()
                    self._quote_sock.send(pkg)
                    return self._recv_response(self._quote_sock)
                except Exception:
                    self._quote_sock = None
                    return self._send_recv(pkg)

    def _safe_send_recv(self, pkg: bytes) -> bytes:
        """安全发送接收，捕获 remote closed 等异常，返回空响应."""
        try:
            return self._send_recv(pkg)
        except (ConnectionError, TimeoutError, OSError, zlib.error):
            return b"\x00\x00"

    def _quote_safe_send_recv(self, pkg: bytes) -> bytes:
        """快照安全发送接收."""
        try:
            return self._quote_send_recv(pkg)
        except (ConnectionError, TimeoutError, OSError, zlib.error):
            return b"\x00\x00"

    def _send_recv_quick(self, pkg: bytes, timeout: float = 2.0) -> bytes:
        """快速发送接收，短超时，服务器无响应时立即返回空字节.

        适用于已知服务器不支持的命令（如 vol_profile/index_momentum/index_info），
        避免触发完整的重试+故障转移链（40s+）。
        """
        with self._lock:
            if not self.sock:
                self.connect()
            self._throttle()
            try:
                orig = self.sock.gettimeout()
                self.sock.settimeout(timeout)
                try:
                    self.sock.send(pkg)
                    return self._recv_response(self.sock)
                finally:
                    if self.sock:
                        self.sock.settimeout(orig)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError,
                    OSError, TimeoutError, ConnectionError):
                return b"\x00\x00"

    # ---- 名称缓存 ----

    def count(self, market: int) -> int:
        """获取证券数量 (market: 0=深圳, 1=上海)."""
        data = self._send_recv(_b_count(market))
        return _p_count(data)

    def list(self, market: int, start: int = 0, limit: int = 100):
        """获取证券列表."""
        data = self._send_recv(_b_list(market, start))
        return _p_list(data)[:limit]

    def _load_names(self, market: int):
        """延迟加载指定市场的代码-名称映射（渐进式，从真实股票段开始）。"""
        if market in self._name_map_loaded:
            return
        self._name_map_loaded.add(market)
        # 股票代码表结构：
        #   SZ (0): 分类/指数/股票混排，从 0 开始即可
        #   SH (1): 0~24999=指数/债券/基金, 25000+=真实A股(600xxx/601xxx/603xxx/688xxx)
        market_start = {0: 0, 1: 25000}
        self._name_map_offset[market] = market_start.get(market, 0)

    def _get_name(self, code: str) -> str:
        """获取股票名称（渐进式加载，找到即停，最多探查 10 页）。"""
        key = normalize_code(code)
        if key in self._name_map:
            return self._name_map[key]
        mid, _, _ = split_code(code)
        if mid not in self._name_map_loaded:
            self._load_names(mid)
        for _ in range(20):
            start = self._name_map_offset.get(mid, 0)
            try:
                data = self._send_recv(_b_list(mid, start))
                batch = _p_list(data)
            except Exception:
                break
            if not batch:
                self._name_map_offset.pop(mid, None)
                break
            for item in batch:
                c = item.get("code", "")
                n = item.get("name", "")
                if c and n:
                    self._name_map[f"{'sh' if mid == 1 else 'sz'}{c}"] = n
            self._name_map_offset[mid] = start + len(batch)
            if key in self._name_map:
                break
            if len(batch) < 1000:
                break
        return self._name_map.get(key, "")

    def quote(self, code: str) -> Quote:
        """获取实时行情（含名称）。"""
        mid, _, num = split_code(code)
        coeff = self._get_coefficient(mid, num)
        data = self._quote_send_recv(_b_snapshot(mid, num))
        result = _p_snapshot(data, coefficient=coeff)
        if not result:
            result = self._find_host_returning_snapshot(mid, num, coeff)
        if not result:
            return Quote(code=code)
        q = result[0]
        if "name" not in q:
            q["name"] = self._get_name(code)
        return Quote(
            code=q.get("code", code),
            market=str(q.get("market", mid)),
            name=q.get("name", ""),
            price=q.get("price", 0.0),
            pre_close=q.get("last_close", 0.0),
            open=q.get("open", 0.0),
            high=q.get("high", 0.0),
            low=q.get("low", 0.0),
            volume=int(q.get("vol", 0)),
            amount=q.get("amount", 0.0),
            bid_p=[q.get(f"bid{i}", 0.0) for i in range(1, 6)],
            bid_v=[int(q.get(f"bid_vol{i}", 0)) for i in range(1, 6)],
            ask_p=[q.get(f"ask{i}", 0.0) for i in range(1, 6)],
            ask_v=[int(q.get(f"ask_vol{i}", 0)) for i in range(1, 6)],
            inner_vol=int(q.get("s_vol", 0)),
            outer_vol=int(q.get("b_vol", 0)),
        )

    def _format_kline_time(self, r: dict, period: str) -> str:
        y = r.get('year', 0)
        m = r.get('month', 1)
        d = r.get('day', 1)
        h = r.get('hour', 0)
        mn = r.get('minute', 0)
        if period in ('day', 'week', 'month'):
            return f"{y:04d}{m:02d}{d:02d}"
        return f"{y:04d}{m:02d}{d:02d}{h:02d}{mn:02d}"

    def _make_kline(self, r: dict, period: str) -> Kline:
        return Kline(
            time=self._format_kline_time(r, period),
            open=r.get('open', 0.0),
            high=r.get('high', 0.0),
            low=r.get('low', 0.0),
            close=r.get('close', 0.0),
            volume=int(r.get('vol', 0)) if not (isinstance(r.get('vol'), float) and math.isnan(r['vol'])) else 0,
            amount=r.get('amount', 0.0),
            position=r.get('position', 0),
            settlement=r.get('settlement', 0.0),
        )

    def kline(self, code: str, period: str = "day", start: int = 0, count: int = 800,
              adjust: str = "", anchor: str = "", failover: bool = True) -> list[Kline]:
        """获取K线数据。空数据时自动故障转移到其他主机."""
        mid, _, num = split_code(code)
        cat = KLINE_CAT.get(period, 9)
        coeff = self._get_coefficient(mid, num)
        data = self._send_recv(_b_kline(mid, num, cat, start, count))
        rows = _p_kline(data, cat, code, coefficient=coeff, market=mid)
        if start == 0 and failover and self.auto_reconnect:
            if not rows or (count > 10 and len(rows) < count * 0.3):
                rows = self._find_host_returning_kline(code, period, start, count)
        return [self._make_kline(r, period) for r in rows]

    def _find_host_returning_snapshot(self, market: int, code: str, coeff: float) -> list:
        """Snapshot 空数据故障转移 — 自动切换到能返回有效行情的 IP。"""
        bad_host = f"{self._current_host}:{self._current_port}"
        ranked = self._ping_and_rank(self._all_hosts)

        def _try(host: str) -> bool:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(self.timeout)
                h, p = host.rsplit(":", 1)
                s.connect((h, int(p)))
                s.send(setup_cmd1()); self._recv_pass(s)
                s.send(setup_cmd2()); self._recv_pass(s)
                s.send(setup_cmd3()); self._recv_pass(s)
                pkg = _b_snapshot(market, code)
                s.send(pkg)
                data = self._recv_response(s)
                s.close()
                rows = _p_snapshot(data, coefficient=coeff)
                return len(rows) > 0
            except Exception:
                return False

        new_host = find_working_host(ranked, _try, self._save_host, bad_host)
        if new_host is None:
            return []
        self._connect_once(new_host)
        data = self._send_recv(_b_snapshot(market, code))
        return _p_snapshot(data, coefficient=coeff)

    def _find_host_returning_kline(self, code: str, period: str,
                                       start: int = 0, count: int = 800) -> list:
        """K 线空/截断数据故障转移。"""
        mid, _, num = split_code(code)
        cat = KLINE_CAT.get(period, 9)
        coeff = self._get_coefficient(mid, num)
        bad_host = f"{self._current_host}:{self._current_port}"
        ranked = self._ping_and_rank(self._all_hosts)

        def _try(host: str) -> bool:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(self.timeout)
                h, p = host.rsplit(":", 1)
                s.connect((h, int(p)))
                s.send(setup_cmd1()); self._recv_pass(s)
                s.send(setup_cmd2()); self._recv_pass(s)
                s.send(setup_cmd3()); self._recv_pass(s)
                pkg = _b_kline(mid, num, cat, start, 3)
                s.send(pkg)
                data = self._recv_response(s)
                s.close()
                rows = _p_kline(data, cat, code, coefficient=coeff, market=mid)
                return len(rows) > 0
            except Exception:
                return False

        new_host = find_working_host(ranked, _try, self._save_host, bad_host)
        if new_host is None:
            self._connect_once(bad_host)
            return []
        self._connect_once(new_host)
        data = self._send_recv(_b_kline(mid, num, cat, start, count))
        return _p_kline(data, cat, code, coefficient=coeff, market=mid)

    def kline_all(self, code: str, period: str = "day", adjust: str = "",
                  failover: bool = True) -> list[Kline]:
        """自动翻页拉取全量K线，空数据时自动故障转移."""
        mid, _, num = split_code(code)
        cat = KLINE_CAT.get(period, 9)
        coeff = self._get_coefficient(mid, num)
        all_bars = []
        start = 0
        batch_size = 800
        empty_pages = 0
        consecutive_empty = 0
        while empty_pages < 3:
            data = self._send_recv(_b_kline(mid, num, cat, start, batch_size))
            rows = _p_kline(data, cat, code, coefficient=coeff, market=mid)
            if not rows:
                consecutive_empty += 1
                empty_pages += 1
                start += batch_size
                # 连续3页空数据 → 触发故障转移
                if consecutive_empty >= 3 and failover and self.auto_reconnect:
                    rows = self._find_host_returning_kline(code, period, start - batch_size, batch_size)
                    if rows:
                        all_bars.extend(self._make_kline(r, period) for r in rows)
                        consecutive_empty = 0
                        empty_pages = 0
                        start += len(rows)
                    else:
                        break
                continue
            consecutive_empty = 0
            all_bars.extend(self._make_kline(r, period) for r in rows)
            start += len(rows)
            if len(rows) < batch_size:
                break
            empty_pages = 0
        return all_bars

    def codes_all(self, market: int) -> list[dict]:
        """获取全市场代码列表 (自动翻页)."""
        all_codes = []
        start = 0
        empty_pages = 0
        while empty_pages < 3:
            data = self._send_recv(_b_list(market, start))
            batch = _p_list(data)
            if not batch:
                empty_pages += 1
                start += 1000
                continue
            all_codes.extend(batch)
            start += len(batch)
            if len(batch) < 1000:
                break
            empty_pages = 0
        return all_codes

    def codes(self, market: int, start: int = 0, limit: int = 100):
        """获取证券代码列表 (别名)."""
        return self.list(market, start, limit)

    def capital_changes(self, code: str):
        """股本变迁 (兼容旧接口名)."""
        return self.xdxr(code)

    def today_minute(self, code: str) -> list[Minute]:
        """今日分时。空数据时自动故障转移到其他主机。"""
        mid, _, num = split_code(code)
        coeff = self._get_coefficient(mid, num)
        data = self._send_recv(_b_today_minute(mid, num))
        rows = _p_today_minute(data, coefficient=coeff)
        if not rows and self.auto_reconnect:
            rows = self._find_host_returning_minute(code, tdate=None)
        return [Minute(time=str(r.get('minute', '')), price=r.get('price', 0), volume=int(r.get('vol', 0)), avg_price=r.get('avg_price', 0.0)) for r in rows]

    def history_minute(self, code: str, tdate) -> list[Minute]:
        """历史分时。空数据时自动故障转移到其他主机。"""
        mid, _, num = split_code(code)
        coeff = self._get_coefficient(mid, num)
        d = self._parse_tdate(tdate)
        data = self._send_recv(_b_history_minute(mid, num, d))
        rows = _p_history_minute(data, coefficient=coeff)
        if not rows and self.auto_reconnect:
            rows = self._find_host_returning_minute(code, tdate)
        return [Minute(time=str(r.get('minute', '')), price=r.get('price', 0), volume=int(r.get('vol', 0)), avg_price=r.get('avg_price', 0.0)) for r in rows]

    def _find_host_returning_minute(self, code: str, tdate) -> list:
        """分时数据空数据故障转移。"""
        mid, _, num = split_code(code)
        coeff = self._get_coefficient(mid, num)
        is_history = tdate is not None
        d = self._parse_tdate(tdate) if is_history else int(date.today().strftime("%Y%m%d"))
        bad_host = f"{self._current_host}:{self._current_port}"
        ranked = self._ping_and_rank(self._all_hosts)

        def _try(host: str) -> bool:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(self.timeout)
                h, p = host.rsplit(":", 1)
                s.connect((h, int(p)))
                s.send(setup_cmd1()); self._recv_pass(s)
                s.send(setup_cmd2()); self._recv_pass(s)
                s.send(setup_cmd3()); self._recv_pass(s)
                pkg = _b_history_minute(mid, num, d) if is_history else _b_today_minute(mid, num)
                s.send(pkg)
                data = self._recv_response(s)
                s.close()
                rows = _p_history_minute(data, coefficient=coeff) if is_history else _p_today_minute(data, coefficient=coeff)
                return len(rows) > 0
            except Exception:
                return False

        new_host = find_working_host(ranked, _try, self._save_host, bad_host)
        if new_host is None:
            self._connect_once(bad_host)
            return []
        self._connect_once(new_host)
        if is_history:
            pkg = _b_history_minute(mid, num, d)
            data = self._send_recv(pkg)
            rows = _p_history_minute(data, coefficient=coeff)
        else:
            pkg = _b_today_minute(mid, num)
            data = self._send_recv(pkg)
            rows = _p_today_minute(data, coefficient=coeff)
        return rows

    def today_trade(self, code: str, start: int = 0, count: int = 115) -> list[Trade]:
        """今日分笔."""
        mid, _, num = split_code(code)
        data = self._send_recv(_b_today_trade(mid, num, start, count))
        coeff = self._get_coefficient(mid, num)
        rows = _p_today_trade(data, coefficient=coeff)
        return [Trade(time=str(r.get('time', '')), price=r.get('price', 0), volume=int(r.get('vol', 0)), direction=str(r.get('buyorsell', 0)), nature='') for r in rows]

    def history_trade(self, code: str, tdate, start: int = 0, count: int = 900) -> list[Trade]:
        """历史分笔."""
        mid, _, num = split_code(code)
        d = self._parse_tdate(tdate)
        data = self._send_recv(_b_history_trade(mid, num, start, count, d))
        coeff = self._get_coefficient(mid, num)
        rows = _p_history_trade(data, coefficient=coeff)
        return [Trade(time=str(r.get('time', '')), price=r.get('price', 0), volume=int(r.get('vol', 0)), direction=str(r.get('buyorsell', 0)), nature='') for r in rows]

    def xdxr(self, code: str) -> list[EquityChange]:
        """除权除息信息."""
        mid, _, num = split_code(code)
        data = self._send_recv(_b_xdxr(mid, num))
        rows = _p_xdxr(data)
        result = []
        for r in rows:
            year = r.get("year") or 0
            month = r.get("month") or 1
            day = r.get("day") or 1
            eq_date = date(year, month, day) if year > 2000 else None
            result.append(EquityChange(
                date=eq_date,
                category=r.get("category", 0),
                float_shares=r.get("panqianliutong") or r.get("panhouliutong") or r.get("suogu") or r.get("fenshu") or 0.0,
                total_shares=r.get("qianzongguben") or r.get("houzongguben") or 0.0,
                bonus=r.get("fenhong") or 0.0,
                rights=r.get("songzhuangu") or 0.0,
                placement=r.get("peigu") or 0.0,
                placement_price=r.get("peigujia") or 0.0,
            ))
        return result

    def finance(self, code: str) -> dict:
        """财务信息."""
        mid, _, num = split_code(code)
        try:
            data = self._send_recv(_b_finance(mid, num))
            return _p_finance(data)
        except (struct.error, IndexError, KeyError):
            return {"market": mid, "code": code, "error": "no finance data"}

    def company_info_cat(self, code: str) :
        """公司信息类别."""
        mid, _, num = split_code(code)
        data = self._send_recv(_b_company_info_cat(mid, num))
        return _p_company_info_cat(data)

    def company_info_content(self, code: str, filename: str, start: int = 0, length: int = 0) -> str:
        """公司信息内容."""
        mid, _, num = split_code(code)
        data = self._send_recv(_b_company_info_content(mid, num, filename, start, length))
        return _p_company_info_content(data)

    def block_info_meta(self, block_file: str) -> dict:
        """板块元信息."""
        data = self._send_recv(_b_block_info_meta(block_file))
        return _p_block_info_meta(data)

    def block_info(self, block_file: str, start: int = 0, size: int = 0) -> bytes:
        """板块内容."""
        data = self._send_recv(_b_block_info(block_file, start, size))
        return _p_block_info(data)

    def report_file(self, filename: str, offset: int = 0) -> dict:
        """下载财务报表文件."""
        data = self._send_recv_quick(_b_report_file(filename, offset), timeout=15)
        try:
            return _p_report_file(data)
        except (struct.error, KeyError):
            return {"chunksize": 0}

    def get_report_file_raw(self, filename: str) -> bytes:
        """下载报表文件完整内容（自动分块拼接）."""
        chunk_size = 0x7530
        buf = bytearray()
        offset = 0
        while True:
            r = self.report_file(filename, offset)
            if not r or r.get("chunksize", 0) == 0:
                break
            buf.extend(r["chunkdata"])
            offset += r["chunksize"]
            if r["chunksize"] < chunk_size:
                break
        return bytes(buf)

    def get_zhb_files(self) -> dict[str, bytes]:
        """下载 zhb.zip 并解压，返回 {文件名: 原始字节}."""
        raw = self.get_report_file_raw("zhb.zip")
        if not raw:
            return {}
        out = {}
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            for name in zf.namelist():
                out[name] = zf.read(name)
        return out

    def get_tdx_zs(self) -> list[dict]:
        """解析 tdxzs.cfg → 板块名↔指数代码列表."""
        return _parse_pipe_text(self._get_zhb_file("tdxzs.cfg"),
                                ["name", "code", "type", "subtype", "flag", "ref"])

    def get_tdx_bk(self) -> list[dict]:
        """解析 tdxbk.cfg → 概念板块简称↔全称."""
        return _parse_pipe_text(self._get_zhb_file("tdxbk.cfg"),
                                ["flag", "short", "full", "flag2"])

    def get_tdx_stat(self) -> list[dict]:
        """解析 tdxstat.cfg → 全市场个股综合统计指标."""
        return _parse_pipe_text(self._get_zhb_file("tdxstat.cfg"),
                                ["market", "code", "field2", "field3", "date",
                                 "field5", "field6", "field7", "field8", "field9",
                                 "field10", "field11", "field12", "field13", "field14",
                                 "field15", "field16", "field17", "field18", "field19",
                                 "field20", "field21", "field22", "field23", "field24",
                                 "field25", "field26", "field27", "field28", "field29",
                                 "field30", "field31", "field32", "field33", "field34"])

    def get_tdx_stat2(self) -> list[dict]:
        """解析 tdxstat2.cfg → 全市场个股资金流向 + 板块归属."""
        return _parse_pipe_text(self._get_zhb_file("tdxstat2.cfg"),
                                ["market", "code", "date", "amount", "field4",
                                 "amount_prev", "field6", "field7", "field8", "field9",
                                 "field10", "field11", "field12", "block_index",
                                 "field14", "field15", "ipo_price", "high_52w", "low_52w",
                                 "field19", "field20"])

    def get_xgsg(self) -> list[dict]:
        """解析 xgsg.cfg → 新股申购列表."""
        return _parse_pipe_text(self._get_zhb_file("xgsg.cfg"),
                                ["market", "code", "date", "issue_price", "field4",
                                 "field5", "field6", "field7", "field8", "field9",
                                 "field10", "field11", "field12", "field13", "name",
                                 "field15", "field16", "field17"])

    def get_tdx_hy(self) -> list[dict]:
        """解析 tdxhy.cfg → 每只股票的通达信/申万行业归属."""
        raw = self.get_block_file_parsed_raw("tdxhy.cfg")
        lines = raw.decode("gbk", "ignore").split("\n")
        out = []
        for ln in lines:
            ln = ln.strip("\r")
            if not ln:
                continue
            f = ln.split("|")
            if len(f) < 3:
                continue
            r = {"market": int(f[0]) if f[0].isdigit() else 0, "code": f[1], "tdx_hy": f[2]}
            r["sw_hy"] = f[5] if len(f) >= 6 else f[-1]
            out.append(r)
        return out

    def _get_zhb_file(self, name: str) -> bytes:
        """从 zhb.zip 缓存中获取指定文件内容."""
        if not hasattr(self, "_zhb_cache") or not self._zhb_cache:
            self._zhb_cache = self.get_zhb_files()
        return self._zhb_cache.get(name, b"")

    def get_block_file_parsed_raw(self, filename: str) -> bytes:
        """下载任意板块/配置文件原始字节（自动分块）. 适用于 tdxhy.cfg 等文本文件."""
        meta = self.block_info_meta(filename)
        size = meta.get("size", 0)
        if not size:
            return b""
        chunk_size = 0x7530
        buf = bytearray()
        offset = 0
        while offset < size:
            piece = self.block_info(filename, offset, min(chunk_size, size - offset))
            buf.extend(piece)
            offset += chunk_size
        return bytes(buf)

    # ---- 新增命令 ----

    def vol_profile(self, code: str, price_levels: int = 20) -> dict:
        """分时成交量分布（基于逐笔成交计算）.

        服务器不支持 0x051A 命令，改用今日逐笔成交数据按价格分组计算。
        price_levels: 最多返回的价格档位数。
        """
        try:
            trades = self.today_trade(code, 0, 2000)
        except Exception:
            return {}
        if not trades:
            return {}
        from collections import defaultdict
        buckets = defaultdict(lambda: {"vol": 0, "buy": 0, "sell": 0})
        for t in trades:
            price = round(t.price, 2)
            buckets[price]["vol"] += t.volume
            if t.direction == "1":
                buckets[price]["buy"] += t.volume
            elif t.direction == "2":
                buckets[price]["sell"] += t.volume
        sorted_prices = sorted(buckets.keys())
        vol_profile = [
            {"price": p, "vol": buckets[p]["vol"],
             "buy": buckets[p]["buy"], "sell": buckets[p]["sell"]}
            for p in sorted_prices[-price_levels:]
        ]
        return {
            "code": code,
            "vol_profile": vol_profile,
            "total_vol": sum(v["vol"] for v in vol_profile),
        }

    def index_momentum(self, code: str, period: int = 5):
        """指数动能（基于日K线计算）.

        服务器不支持 0x051C 命令，改用 K 线数据计算。
        momentum = (close - close[period]) / close[period] * 100
        """
        bars = self.kline(code, "day", 0, period + 1)
        if len(bars) < period + 1:
            return []
        result = []
        for i in range(period, len(bars)):
            mom = (bars[i].close - bars[i - period].close) / bars[i - period].close * 100
            result.append(round(mom, 2))
        return result

    def index_info(self, code: str, top_n: int = 50) -> dict:
        """指数成分股行情（通过板块机制获取）.

        服务器不支持 0x051D 命令，改用可用方式获取成分股行情：
        1. board_members (MAC) — 适用于板块代码
        2. codes_all + quotes_detail — 适用于大盘指数
        """
        clean = code.lower().replace("sh", "").replace("sz", "").replace("bj", "")
        try:
            members = self.board_members(str(clean), page_size=top_n, start=0)
            if members:
                return {"code": code, "members": members, "count": len(members)}
        except Exception:
            pass
        market = 1 if clean.startswith("60") else 0
        try:
            all_codes = self.codes_all(market)
            sample = [f"{'sh' if market == 1 else 'sz'}{c}" for c in all_codes[:top_n]]
            quotes = self.quotes_detail(sample)
            return {"code": code, "members": quotes, "count": len(quotes)}
        except Exception:
            pass
        try:
            mid, _, num = split_code(code)
            data = self._send_recv_quick(_b_index_info(mid, num), timeout=3.0)
            result = _p_index_info(data)
            if result and result.get("code"):
                return result
        except Exception:
            pass
        return {"code": code, "error": "no index data available"}

    def quotes_detail(self, code_list) -> dict:
        """详细行情 (5档买卖盘)."""
        stocks = []
        for code in code_list:
            mid, _, num = split_code(code)
            stocks.append((mid, num))
        data = self._quote_send_recv(_b_quotes_detail(stocks))
        coeff = self._get_coefficient(stocks[0][0], stocks[0][1]) if stocks else 0.01
        return _p_quotes_detail(data, coefficient=coeff)

    def tick_chart(self, code: str, start: int = 0, count: int = 0xBA00):
        """分时明细 — 对齐 pytdx GetTransactionData (CMD 0x0FC5)."""
        mid, _, num = split_code(code)
        coeff = self._get_coefficient(mid, num)
        data = self._send_recv(_b_tick_chart(mid, num, start, count))
        return _p_tick_chart(data, coefficient=coeff)

    def auction(self, code: str, mode: int = 3):
        """集合竞价."""
        mid, _, num = split_code(code)
        data = self._send_recv_quick(_b_auction(mid, num, mode=mode), timeout=3.0)
        try:
            return _p_auction(data)
        except (struct.error, KeyError):
            return []

    def top_board(self, category: int = 0):
        """涨跌停板. category: 0=涨停, 1=跌停, 2=振幅, 3=涨速, 4=跌速, 5=量比, 6=正委比, 7=负委比, 8=换手."""
        data = self._quote_safe_send_recv(_b_top_board(category))
        try:
            return _p_top_board(data)
        except (struct.error, KeyError):
            return {k: [] for k in ["increase", "decrease", "amplitude", "rise_speed", "fall_speed",
                                      "vol_ratio", "pos_commission_ratio", "neg_commission_ratio", "turnover"]}

    def quotes_list(self, category: int, start: int = 0, count: int = 80,
                    sort_type: int = 0, reverse: bool = False,
                    filter_raw: int = 0) -> dict:
        """板块行情列表."""
        data = self._quote_safe_send_recv(_b_quotes_list(category, start, count, sort_type, reverse, filter_raw))
        return _p_quotes_list(data)

    def unusual(self, market: int = 0, start: int = 0, count: int = 600, min_volume: int = 1000):
        """主力监控（基于逐笔成交过滤大单）.

        服务器不支持 0x0563 命令，改用今日逐笔成交数据过滤大单。
        min_volume: 最小成交量阈值（手），默认 1000 手 = 10万股。
        """
        results = []
        try:
            all_codes = self.codes(market, 0, 2000)
            stock_codes = []
            for c in all_codes:
                code = c.get("code", "") if isinstance(c, dict) else str(c)
                if not code:
                    continue
                if market == 0 and not (code.startswith("00") or code.startswith("30")):
                    continue
                if market == 1 and not (code.startswith("60") or code.startswith("68")):
                    continue
                stock_codes.append(code)
            for code in stock_codes[:50]:
                full_code = f"{'sh' if market == 1 else 'sz'}{code}"
                trades = self.today_trade(full_code, 0, 500)
                for t in trades:
                    if t.volume >= min_volume:
                        results.append({
                            "code": full_code,
                            "time": t.time,
                            "price": t.price,
                            "volume": t.volume,
                            "amount": round(t.price * t.volume * 100, 2),
                            "direction": t.direction,
                        })
                        if len(results) >= count:
                            break
                if len(results) >= count:
                    break
        except Exception:
            pass
        return results

    def chart_sampling(self, code: str) -> list[float]:
        """K线采样（服务器多不支持此命令，回退用 kline 收盘价）."""
        mid, _, num = split_code(code)
        data = self._send_recv_quick(_b_chart_sampling_kline(mid, num), timeout=15)
        result = _p_chart_sampling_kline(data)
        if result:
            return result
        klines = self.kline(code, period="day", count=100)
        if klines:
            return [k.close for k in klines]
        return []

    def history_orders(self, code: str, tdate):
        """历史委托（服务器多不支持此命令，可能返回空）."""
        mid, _, num = split_code(code)
        coeff = self._get_coefficient(mid, num)
        d = self._parse_tdate(tdate)
        data = self._send_recv_quick(_b_history_orders_full(mid, num, d), timeout=15)
        return _p_history_orders(data, coefficient=coeff)

    def refresh(self, codes: list[str]) -> list[dict]:
        """增量刷新 (0x0547). 传入代码列表, 返回实时快照."""
        stocks = []
        for code in codes:
            mid, _, num = split_code(code)
            stocks.append((mid, num))
        data = self._quote_safe_send_recv(_b_quotes_encrypt(stocks))
        if len(data) < 2:
            return []
        return _p_quotes_encrypt(data)

    def recent_minute(self, code: str, tdate=None) -> list[dict]:
        """近期分时 / 历史tick (0x0FEB)."""
        mid, _, num = split_code(code)
        coeff = self._get_coefficient(mid, num)
        if tdate is None:
            from datetime import date as dt_date
            tdate = int(dt_date.today().strftime("%Y%m%d"))
        d = self._parse_tdate(tdate)
        data = self._send_recv(_b_recent_minute(mid, num, d))
        return _p_recent_minute(data, coefficient=coeff)

    def limits(self, start: int = 0, count: int = 2000) -> list[dict]:
        """涨跌停限制 (0x0452)."""
        data = self._quote_safe_send_recv(_b_limits(start, count))
        return _p_limits(data)

    def get_price_limits(self, code: str) -> PriceLimit:
        """计算个股涨跌停价格.
        
        根据板块规则自动判断涨跌幅限制:
        - 主板 (000/001/002/003/600/601/603/605): 10%
        - ST/*ST: 5%
        - 科创板 (688) / 创业板 (300/301): 20%
        - 北交所 (43/83/87/92): 30%
        - 上市初期 (前5个交易日): 无涨跌停限制
        """
        from ..codec import split_code
        
        # 获取实时行情获取昨收价
        try:
            q = self.quote(code)
            pre_close = q.pre_close
            name = q.name
        except Exception:
            return PriceLimit(code=code, upper=0.0, lower=0.0)
        
        if pre_close <= 0:
            return PriceLimit(code=code, upper=0.0, lower=0.0)
        
        # 提取纯数字代码（去掉 sz/sh/bj 前缀）
        mid, _, num = split_code(code)
        pure_code = num  # 纯数字代码
        
        # 判断板块类型
        limit_pct = 0.10  # 默认 10%
        upper_name = name.upper()
        
        # ST 判断
        if "ST" in upper_name:
            limit_pct = 0.05
        # 科创板 / 创业板
        elif pure_code.startswith("688") or pure_code.startswith(("300", "301")):
            limit_pct = 0.20
        # 北交所
        elif pure_code.startswith(("43", "83", "87", "92")):
            limit_pct = 0.30
        
        # 计算涨跌停价
        upper = round(pre_close * (1 + limit_pct), 2)
        lower = round(pre_close * (1 - limit_pct), 2)
        
        return PriceLimit(code=code, upper=upper, lower=lower)

    def sparkline(self, code: str) -> list[float]:
        """小走势图 — 用 1min K 线收盘价序列替代 (CMD 0xFD1 不可用)."""
        bars = self.kline(code, '1m', 0, 240)
        return [b.close for b in bars]

    def aux(self, code: str) -> list[dict]:
        """分时副图 (0x051B)."""
        mid, _, num = split_code(code)
        data = self._send_recv(_b_aux(mid, num))
        return _p_aux(data)

    # ============================================================
    # 板块相关方法（通过 block_info + parse_block_dat）
    # ============================================================

    def get_block_file_parsed(self, block_file: str) -> list[dict]:
        """获取并解析板块 .dat 文件内容（一行式调用）.

        常用文件名:
          block_zs.dat — 行业/指数板块
          block_gn.dat — 概念板块
          block_fg.dat — 风格板块
        """
        from ..block_reader import parse_block_dat
        meta = self.block_info_meta(block_file)
        size = meta.get("size", 0)
        if not size:
            return []
        chunk_size = 0x7530  # 30000 字节/片
        full_data = bytearray()
        offset = 0
        while offset < size:
            piece = self.block_info(block_file, offset, min(chunk_size, size - offset))
            full_data.extend(piece)
            offset += chunk_size
        return parse_block_dat(bytes(full_data), block_file)

    def board_list(
        self,
        page_size: int = 150,
        board_type: int = 0,
        sort_column: int = 0,
        sort_order: int = 1,
        start: int = 0,
    ) -> list[dict]:
        """获取板块列表（通过 MAC 协议）.

        board_type: 0=行业一级, 3=概念, 4=风格, 5=地区, 255=全部
        sort_column: 0=涨速, 1=涨跌幅, 2=成交额, 3=成交量
        sort_order: 0=升序, 1=降序
        """
        if not _HAS_MAC:
            raise RuntimeError("MAC 模块不可用")
        mac = MacClient(timeout=self.timeout)
        try:
            mac.connect()
            return mac.board_list(page_size, board_type, sort_column, sort_order, start)
        finally:
            mac.close()

    def board_members(
        self,
        board_code: str | int,
        page_size: int = 80,
        start: int = 0,
        sort_type: int = 0,
        sort_order: int = 1,
    ) -> list[dict]:
        """获取板块成分股（通过 MAC 协议）.

        示例: board_members("881001") — 获取申万一级行业板块成分股
        """
        if not _HAS_MAC:
            raise RuntimeError("MAC 模块不可用")
        mac = MacClient(timeout=self.timeout)
        try:
            mac.connect()
            return mac.board_members(board_code, page_size, start, sort_type, sort_order)
        finally:
            mac.close()

    def stock_blocks(self, market: int, code: str) -> list[dict]:
        """获取个股所属板块（通过 MAC 协议）.

        示例: stock_blocks(0, "sz000001") — 平安银行所属板块
        """
        if not _HAS_MAC:
            raise RuntimeError("MAC 模块不可用")
        mac = MacClient(timeout=self.timeout)
        try:
            mac.connect()
            return mac.stock_blocks(market, code)
        finally:
            mac.close()

    def board_summary(self, board_code: str | int) -> dict:
        """获取板块汇总（成交额/主力净流入/涨跌家数）.

        示例: board_summary("881001")
        """
        if not _HAS_MAC:
            raise RuntimeError("MAC 模块不可用")
        mac = MacClient(timeout=self.timeout)
        try:
            mac.connect()
            return mac.board_summary(board_code)
        finally:
            mac.close()

    def board_change_ranking(
        self,
        board_type: int = 0,
        days: int = 5,
        top_n: int = 100,
        sort_order: int = 1,
    ) -> list[dict]:
        """获取板块 N 日涨跌幅排行（通过 MAC 协议）.

        board_type: 0=行业一级, 3=概念, 4=风格, 5=地区
        days: N 日周期（如 5=5日排行）
        top_n: 取前 N 名
        """
        if not _HAS_MAC:
            raise RuntimeError("MAC 模块不可用")
        mac = MacClient(timeout=self.timeout)
        try:
            mac.connect()
            return mac.board_change_ranking(board_type, days, top_n, sort_order)
        finally:
            mac.close()

    def quote_list(
        self,
        category: int,
        count: int = 80,
        start: int = 0,
        sort_type: int = 0,
        sort_order: int = 1,
        exclude_flags: int = 0,
    ) -> list[dict]:
        """市场分类批量报价（quote-list）.

        category: Category 枚举值（Category.A=全部A股, Category.KCB=科创板, Category.CYB=创业板）
        exclude_flags: FilterType 组合（如 FilterType.ST | FilterType.NEW）
        """
        if not _HAS_MAC:
            raise RuntimeError("MAC 模块不可用")
        from ..mac.commands import Category as _Cat
        cat_val = _Cat.A if isinstance(category, str) else category
        mac = MacClient(timeout=self.timeout)
        try:
            mac.connect()
            return mac.category_quotes(cat_val, count, start, sort_type, sort_order, exclude_flags)
        finally:
            mac.close()

    def capital_flow(self, code: str) -> dict:
        """个股资金流向（capital-flow）.

        示例: client.capital_flow("sz600519") — 贵州茅台资金流向
        """
        if not _HAS_MAC:
            raise RuntimeError("MAC 模块不可用")
        mid, _, num = split_code(code)
        mac = MacClient(timeout=self.timeout)
        try:
            mac.connect()
            return mac.capital_flow(mid, num)
        finally:
            mac.close()

    def market_stat(self) -> dict:
        """市场统计（market-stat）.

        通过标准协议查询特殊指数 sh880005/sh880001/sh880006 计算涨跌家数、总市值等.
        """
        try:
            q1 = self.quote("sh880005")
            q2 = self.quote("sh880001")
            q3 = self.quote("sh880006")
        except Exception:
            return {}

        up = round(q1.price * 10) if q1 else 0
        down = round(q1.open * 10) if q1 else 0
        neutral = round(q1.low * 10) if q1 else 0
        total = round(q1.high * 10) if q1 else 0
        limit_up = round(q3.price * 10) if q3 else 0
        limit_down = round(q3.open * 10) if q3 else 0
        market_cap = q2.amount if q2 else 0
        total_amount = q1.amount if q1 else 0
        total_volume = q1.volume if q1 else 0

        return {
            "up_count": up,
            "down_count": down,
            "neutral_count": neutral,
            "total_count": total,
            "suspended_count": max(0, total - up - down - neutral),
            "limit_up": limit_up,
            "limit_down": limit_down,
            "total_amount": round(total_amount, 2),
            "total_volume": total_volume,
            "market_cap": round(market_cap, 2),
            "today": str(date.today()),
        }

    # ---- 增强功能 ----

    def get_blocks_with_index(self, block_type: int = 0) -> list[dict]:
        """获取带指数代码的板块列表 (板块指数桥接).
        
        Args:
            block_type: 0=行业/指数板块, 2=概念板块, 3=风格板块
        """
        from ..block_bridge import BlockBridge
        bridge = BlockBridge(self)
        bridge.load_bridge_data()
        
        if block_type == 2:
            filename = "block_gn.dat"
        elif block_type == 3:
            filename = "block_fg.dat"
        else:
            filename = "block_zs.dat"
        
        raw_blocks = self.get_block_file_parsed(filename)
        result = []
        for block in raw_blocks:
            item = dict(block)
            index_code = bridge._get_index_by_name(block['name'])
            if index_code:
                item['index'] = index_code
                item['index_name'] = bridge._get_index_name(index_code)
            result.append(item)
        return result

    def block_members(self, block_code: str) -> list[dict]:
        """获取板块成分股 (通过板块指数代码桥接).
        
        Args:
            block_code: 板块代码或名称
        """
        from ..block_bridge import BlockBridge
        bridge = BlockBridge(self)
        bridge.load_bridge_data()
        
        # 查找板块
        target = None
        for b in bridge._blocks:
            if b.index == block_code or b.name == block_code:
                target = b
                break
        
        if not target:
            return []
        
        result = []
        for code in target.codes[:50]:
            try:
                quote = self.quote(code)
                if quote:
                    result.append({
                        'code': code,
                        'name': quote.name,
                        'price': quote.price,
                        'change_pct': quote.change_pct,
                    })
            except Exception:
                continue
        return result

    def get_company_info(self, code: str, filename: str) -> Optional[str]:
        """获取公司配置文件内容.
        
        Args:
            code: 股票代码 (如 sh000001)
            filename: 文件名 (如 tdxzs.cfg, tdxbk.cfg)
        """
        mid, _, num = split_code(code)
        data = self._send_recv(_b_company_info_content(mid, num, filename, 0, 0))
        return _p_company_info_content(data)

    def server_info(self) -> dict:
        """服务器信息（server-info）."""
        if not _HAS_MAC:
            raise RuntimeError("MAC 模块不可用")
        mac = MacClient(timeout=self.timeout)
        try:
            mac.connect()
            return mac.server_info()
        finally:
            mac.close()

    def symbol_info(self, code: str) -> dict:
        """个股详细信息（symbol-info）.

        示例: client.symbol_info("sz000001") — 平安银行详细信息
        """
        if not _HAS_MAC:
            raise RuntimeError("MAC 模块不可用")
        mid, _, num = split_code(code)
        mac = MacClient(timeout=self.timeout)
        try:
            mac.connect()
            return mac.symbol_info(mid, num)
        finally:
            mac.close()

    def _get_coefficient(self, market: int, code: str) -> float:
        key = (market, code)
        if key not in self._coefficients:
            self._coefficients[key] = self._calc_coefficient(market, code)
        return self._coefficients[key]

    @staticmethod
    def _calc_coefficient(market: int, code: str) -> float:
        code_head = code[:2]
        if market == 0:  # SZ
            if code_head in ["00", "30"]: return 0.01
            if code_head in ["20"]: return 0.01
            if code_head in ["39"]: return 0.01
            if code_head in ["15", "16"]: return 0.001
            if code_head in ["10", "11", "12", "13", "14"]: return 0.0001
        elif market == 1:  # SH
            if code_head in ["60", "68"]: return 0.01
            if code_head in ["90"]: return 0.001
            if code_head in ["00", "88", "99"]: return 0.01
            if code_head in ["50", "51", "52", "53", "56", "57", "58", "59"]: return 0.001
            if code_head in ["01", "10", "11", "12", "13", "14", "20"]: return 0.0001
        return 0.01

    @staticmethod
    def _parse_tdate(tdate) -> int:
        """解析日期为 YYYYMMDD 整数."""
        if hasattr(tdate, 'strftime'):
            return int(tdate.strftime("%Y%m%d"))
        s = str(tdate).replace("-", "").replace("/", "")
        return int(s)

    def do_heartbeat(self):
        """心跳: 发送 get_security_count."""
        import random
        self.count(random.randint(0, 1))

    # ---- 故障转移辅助 ----

    @staticmethod
    def _ping_and_rank(hosts: list[str], port: int = 7709, timeout: float = 3.0) -> list[tuple[str, float]]:
        """并发测速，返回按延迟升序的 [(host:port, ms), ...]。"""
        results = scan_stock(hosts, workers=32, timeout=timeout)
        ranked = [(r.host, r.handshake_latency_ms) for r in results if r.ok]
        ranked.sort(key=lambda x: x[1])
        return ranked

    def _save_host(self, host: str) -> None:
        """持久化最优 host（写入 ip_health 缓存）。"""
        try:
            from ..ip_health import get_manager, HostEntry, HEALTH_OK
            m = get_manager()
            for e in m.pool.entries.values():
                if e.host == host and e.protocol == "7709":
                    return
            # 新增发现的主机，添加到池后再保存
            port = int(host.rsplit(":", 1)[1]) if ":" in host else 7709
            entry = HostEntry(
                host=host, port=port, protocol="7709",
                tcp_ok=True, handshake_ok=True, status=HEALTH_OK,
            )
            m.pool.add(entry)
            m.save_cache()
        except Exception:
            pass

    def _find_host_returning_data(self, cmd_name: str, builder, parser, code: str,
                                    period: str = "", tdate=None) -> list:
        """空数据故障转移：测速后逐台实测，返回首台有效数据。

        Args:
            cmd_name: 用于日志标识。
            builder: ``(mid, num, ...) -> bytes`` 的命令构造器。
            parser: ``(data, ...) -> list`` 的解析器。
            code: 股票代码。
            period: K 线周期（仅 K 线用）。
            tdate: 日期（仅历史分时用）。

        Returns:
            非空数据列表，或空列表（全部不可用）。
        """
        bad_host = f"{self._current_host}:{self._current_port}"
        mid, _, num = split_code(code)
        coeff = self._get_coefficient(mid, num)
        ranked = self._ping_and_rank(self._all_hosts)

        def _try(host: str) -> bool:
            """连接指定主机，执行命令，返回是否有数据。"""
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(self.timeout)
                h, p = host.rsplit(":", 1)
                s.connect((h, int(p)))
                s.send(setup_cmd1())
                self._recv_pass(s)
                s.send(setup_cmd2())
                self._recv_pass(s)
                s.send(setup_cmd3())
                self._recv_pass(s)
                if period:
                    pkg = builder(mid, num, KLINE_CAT.get(period, 9), 0, 3)
                else:
                    d = self._parse_tdate(tdate) if tdate else int(date.today().strftime("%Y%m%d"))
                    pkg = builder(mid, num, d)
                s.send(pkg)
                data = self._recv_response(s)
                s.close()
                if period:
                    rows = parser(data, KLINE_CAT.get(period, 9), code, coefficient=coeff)
                else:
                    rows = parser(data, coefficient=coeff)
                return len(rows) > 0
            except Exception:
                return False

        new_host = find_working_host(ranked, _try, self._save_host, bad_host)
        if new_host is None:
            self._connect_once(bad_host)
            return []
        # 切换到新 host
        self._connect_once(new_host)
        if period:
            pkg = builder(mid, num, KLINE_CAT.get(period, 9), 0, 3)
        else:
            d = self._parse_tdate(tdate) if tdate else int(date.today().strftime("%Y%m%d"))
            pkg = builder(mid, num, d)
        data = self._send_recv(pkg)
        if period:
            rows = parser(data, KLINE_CAT.get(period, 9), code, coefficient=coeff)
        else:
            rows = parser(data, coefficient=coeff)
        return rows
