"""7709 股票行情客户端 — 对齐 pytdx/tdxpy TdxHq_API。

使用 pytdx 原始的字节格式，不经过 Frame 封装。
"""
from __future__ import annotations

import socket
import struct
import time
import threading
import zlib
from typing import Optional, Sequence

from ..codec import split_code, decode_volume, get_price, u32, int_date
from ..ip_health import get_manager, HostManager
from .commands import (
    setup_cmd1, setup_cmd2, setup_cmd3,
    _b_count, _b_list, _b_snapshot, _b_kline, _b_today_minute,
    _b_history_minute, _b_today_trade, _b_history_trade,
    _b_xdxr, _b_finance, _b_company_info_cat, _b_company_info_content,
    _b_block_info_meta, _b_block_info, _b_report_file,
    _b_vol_profile, _b_index_momentum, _b_index_info,
    _b_quotes_detail, _b_tick_chart, _b_auction,
    _b_top_board, _b_quotes_list, _b_unusual,
    _b_chart_sampling, _b_history_orders,
    _b_quotes_encrypt, _b_recent_minute, _b_limits,
    _p_count, _p_list, _p_snapshot, _p_kline, _p_today_minute,
    _p_today_trade, _p_history_minute, _p_history_trade,
    _p_xdxr, _p_finance, _p_company_info_cat, _p_company_info_content,
    _p_block_info_meta, _p_block_info, _p_report_file,
    _p_vol_profile, _p_index_momentum, _p_index_info,
    _p_quotes_detail, _p_tick_chart, _p_auction,
    _p_top_board, _p_quotes_list, _p_unusual,
    _p_chart_sampling, _p_history_orders,
    _p_quotes_encrypt, _p_recent_minute, _p_limits,
    _get_datetime, _cal_price, _cal_price1000,
)
from ..hosts import STOCK_HOSTS_FAST as STOCK_HOSTS

# K线 category 映射
KLINE_CAT = {
    "1m": 8, "5m": 0, "15m": 1, "30m": 2, "60m": 3,
    "day": 9, "week": 5, "month": 6, "quarter": 10, "year": 11,
}

RSP_HEADER_LEN = 0x10  # 16 bytes


class StockClient:
    """7709 股票行情客户端，对齐 pytdx TdxHq_API."""

    def __init__(self, hosts: Optional[list] = None, timeout: float = 5.0,
                 use_ip_health: bool = True):
        if hosts:
            self.hosts = hosts
        elif use_ip_health:
            # 优先使用IP健康管理的优选IP
            manager = get_manager()
            best = manager.get_best_stock_host()
            if best:
                self.hosts = [best.host]
            else:
                self.hosts = STOCK_HOSTS
        else:
            self.hosts = STOCK_HOSTS
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._coefficients = {}
        self._use_ip_health = use_ip_health
        self._current_host_entry = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

    def connect(self):
        """连接服务器并执行 3 步握手, 支持自动故障转移。"""
        last_err = None
        hosts_to_try = list(self.hosts)
        
        # 如果当前IP失败次数多, 尝试轮换
        if self._current_host_entry and self._current_host_entry.consecutive_failures >= 3:
            manager = get_manager() if self._use_ip_health else None
            if manager:
                rotated = manager.rotate_stock_host(self._current_host_entry)
                if rotated.host not in hosts_to_try:
                    hosts_to_try.insert(0, rotated.host)
        
        for host_str in hosts_to_try:
            sock = None
            try:
                host, port = host_str.rsplit(":", 1)
                port = int(port)
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                sock.connect((host, port))
                # 执行握手
                sock.send(setup_cmd1())
                self._recv_pass(sock)
                sock.send(setup_cmd2())
                self._recv_pass(sock)
                sock.send(setup_cmd3())
                self._recv_pass(sock)
                self.sock = sock
                
                # 更新当前主机记录
                if self._use_ip_health:
                    manager = get_manager()
                    for entry in manager.pool.entries.values():
                        if entry.host == host_str and entry.protocol == "7709":
                            self._current_host_entry = entry
                            break
                
                return
            except Exception as e:
                last_err = e
                if sock:
                    try: sock.close()
                    except: pass
                # 更新失败计数
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
            chunk = s.recv(n - len(buf))
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
            body = zlib.decompress(body)
        return body

    def disconnect(self):
        self.close()

    def close(self):
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            self.sock.close()
            self.sock = None

    def _send_recv(self, pkg: bytes) -> bytes:
        """发送请求包并接收响应（带锁）."""
        with self._lock:
            if not self.sock:
                raise ConnectionError("not connected")
            self.sock.send(pkg)
            return self._recv_response(self.sock)

    # ---- 公共 API ----

    def count(self, market: int) -> int:
        """获取证券数量 (market: 0=深圳, 1=上海)."""
        data = self._send_recv(_b_count(market))
        return _p_count(data)

    def list(self, market: int, start: int = 0, limit: int = 100) :
        """获取证券列表."""
        data = self._send_recv(_b_list(market, start))
        return _p_list(data)[:limit]

    def quote(self, code: str):
        """获取实时行情."""
        mid, _, num = split_code(code)
        coeff = self._get_coefficient(mid, num)
        data = self._send_recv(_b_snapshot(mid, num))
        result = _p_snapshot(data, coefficient=coeff)
        return result[0] if result else {}

    def kline(self, code: str, period: str = "day", start: int = 0, count: int = 800) :
        """获取K线数据."""
        mid, _, num = split_code(code)
        cat = KLINE_CAT.get(period, 9)
        data = self._send_recv(_b_kline(mid, num, cat, start, count))
        return _p_kline(data, cat, code)

    def today_minute(self, code: str) :
        """今日分时."""
        mid, _, num = split_code(code)
        coeff = self._get_coefficient(mid, num)
        data = self._send_recv(_b_today_minute(mid, num))
        return _p_today_minute(data, coefficient=coeff)

    def history_minute(self, code: str, tdate) :
        """历史分时."""
        mid, _, num = split_code(code)
        coeff = self._get_coefficient(mid, num)
        d = self._parse_tdate(tdate)
        data = self._send_recv(_b_history_minute(mid, num, d))
        return _p_history_minute(data, coefficient=coeff)

    def today_trade(self, code: str, start: int = 0, count: int = 115) :
        """今日分笔."""
        mid, _, num = split_code(code)
        data = self._send_recv(_b_today_trade(mid, num, start, count))
        return _p_today_trade(data)

    def history_trade(self, code: str, tdate, start: int = 0, count: int = 900) :
        """历史分笔."""
        mid, _, num = split_code(code)
        d = self._parse_tdate(tdate)
        data = self._send_recv(_b_history_trade(mid, num, start, count, d))
        return _p_history_trade(data)

    def xdxr(self, code: str) :
        """除权除息信息."""
        mid, _, num = split_code(code)
        data = self._send_recv(_b_xdxr(mid, num))
        return _p_xdxr(data)

    def finance(self, code: str) -> dict:
        """财务信息."""
        mid, _, num = split_code(code)
        data = self._send_recv(_b_finance(mid, num))
        return _p_finance(data)

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
        data = self._send_recv(_b_report_file(filename, offset))
        return _p_report_file(data)

    # ---- 新增命令 ----

    def vol_profile(self, code: str) -> dict:
        """分时成交量分布."""
        mid, _, num = split_code(code)
        coeff = self._get_coefficient(mid, num)
        data = self._send_recv(_b_vol_profile(mid, num))
        return _p_vol_profile(data, coefficient=coeff)

    def index_momentum(self, code: str):
        """指数动能."""
        mid, _, num = split_code(code)
        data = self._send_recv(_b_index_momentum(mid, num))
        return _p_index_momentum(data)

    def index_info(self, code: str) -> dict:
        """指数成分股/行情."""
        mid, _, num = split_code(code)
        coeff = self._get_coefficient(mid, num)
        data = self._send_recv(_b_index_info(mid, num))
        return _p_index_info(data, coefficient=coeff)

    def quotes_detail(self, code_list) -> dict:
        """详细行情 (5档买卖盘)."""
        stocks = []
        for code in code_list:
            mid, _, num = split_code(code)
            stocks.append((mid, num))
        data = self._send_recv(_b_quotes_detail(stocks))
        coeff = self._get_coefficient(stocks[0][0], stocks[0][1]) if stocks else 0.01
        return _p_quotes_detail(data, coefficient=coeff)

    def tick_chart(self, code: str, start: int = 0, count: int = 0xBA00):
        """分时明细."""
        mid, _, num = split_code(code)
        coeff = self._get_coefficient(mid, num)
        data = self._send_recv(_b_tick_chart(mid, num, start, count))
        return _p_tick_chart(data, coefficient=coeff)

    def auction(self, code: str):
        """集合竞价."""
        mid, _, num = split_code(code)
        data = self._send_recv(_b_auction(mid, num))
        return _p_auction(data)

    def top_board(self, category: int = 0):
        """涨跌停板. category: 0=涨停, 1=跌停, 2=振幅, 3=涨速, 4=跌速, 5=量比, 6=正委比, 7=负委比, 8=换手."""
        data = self._send_recv(_b_top_board(category))
        return _p_top_board(data)

    def quotes_list(self, category: int, start: int = 0, count: int = 80,
                    sort_type: int = 0, reverse: bool = False,
                    filter_raw: int = 0) -> dict:
        """板块行情列表."""
        data = self._send_recv(_b_quotes_list(category, start, count, sort_type, reverse, filter_raw))
        return _p_quotes_list(data)

    def unusual(self, market: int = 0, start: int = 0, count: int = 600):
        """主力监控."""
        data = self._send_recv(_b_unusual(market, start, count))
        return _p_unusual(data)

    def chart_sampling(self, code: str):
        """K线采样."""
        mid, _, num = split_code(code)
        data = self._send_recv(_b_chart_sampling(mid, num))
        return _p_chart_sampling(data)

    def history_orders(self, code: str, tdate):
        """历史委托."""
        mid, _, num = split_code(code)
        coeff = self._get_coefficient(mid, num)
        d = self._parse_tdate(tdate)
        data = self._send_recv(_b_history_orders(mid, num))
        return _p_history_orders(data, coefficient=coeff)

    def refresh(self, codes: list[str]) -> list[dict]:
        """增量刷新 (0x0547). 传入代码列表, 返回实时快照."""
        stocks = []
        for code in codes:
            mid, _, num = split_code(code)
            stocks.append((mid, num))
        data = self._send_recv(_b_quotes_encrypt(stocks))
        return _p_quotes_encrypt(data)

    def recent_minute(self, code: str, tdate) -> list[dict]:
        """近期分时 / 历史tick (0x0FEB)."""
        mid, _, num = split_code(code)
        coeff = self._get_coefficient(mid, num)
        d = self._parse_tdate(tdate)
        data = self._send_recv(_b_recent_minute(mid, num, d))
        return _p_recent_minute(data, coefficient=coeff)

    def limits(self, start: int = 0, count: int = 2000) -> list[dict]:
        """涨跌停限制 (0x0452)."""
        data = self._send_recv(_b_limits(start, count))
        return _p_limits(data)

    def sparkline(self, code: str) -> list[float]:
        """小走势图 (0xFD1)."""
        mid, _, num = split_code(code)
        data = self._send_recv(_b_chart_sampling(mid, num))
        return _p_chart_sampling(data)

    def aux(self, code: str) -> list[dict]:
        """分时副图 (0x051B). 暂未实现解析器."""
        raise NotImplementedError("aux (0x051B) not yet implemented")

    def _get_coefficient(self, market: int, code: str) -> float:
        key = (market, code)
        if key not in self._coefficients:
            self._coefficients[key] = self._calc_coefficient(market, code)
        return self._coefficients[key]

    @staticmethod
    def _calc_coefficient(market: int, code: str) -> float:
        code_head = code[:2]
        if market == 0:  # SZ
            if code_head in ["00", "30", "60", "68"]: return 0.01
            if code_head in ["20"]: return 0.01
            if code_head in ["39"]: return 0.01
            if code_head in ["15", "16"]: return 0.001
            if code_head in ["10", "11", "12", "13", "14"]: return 0.0001
        elif market == 1:  # SH
            if code_head in ["60", "68"]: return 0.01
            if code_head in ["90"]: return 0.001
            if code_head in ["00", "88", "99"]: return 0.01
            if code_head in ["50", "51", "58"]: return 0.001
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
