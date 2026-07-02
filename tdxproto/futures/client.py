"""7727 期货行情客户端。

基于扫描结果动态调整服务器IP，支持自动故障转移和健康评分。
"""

import time
from datetime import date, datetime, timedelta
from typing import Optional, Sequence

from ..tube import Tube, TubeError
from ..models import Quote, Kline, Minute, Trade
from ..ip_health import get_manager
from .commands import (
    CMD_EX_HANDSHAKE, CMD_EX_HEARTBEAT, CMD_EX_MARKETS, CMD_EX_CODES,
    CMD_EX_QUOTE, CMD_EX_QUOTE_BATCH, CMD_EX_KLINE, CMD_EX_KLINE_RANGE,
    CMD_EX_MINUTE_TODAY, CMD_EX_MINUTE_HISTORY,
    CMD_EX_TRADE_TODAY, CMD_EX_TRADE_HISTORY,
    CMD_EX_TICK_CHART, CMD_EX_HISTORY_TICK_CHART,
    CMD_EX_CHART_SAMPLING, CMD_EX_TABLE, CMD_EX_TABLE_DETAIL,
    CMD_EX_QUOTES,
    PREFIX, FUTURES_HOSTS, HANDSHAKE_DATA,
    _b_ex_heartbeat, _b_ex_markets, _b_ex_codes,
    _b_ex_quote, _b_ex_quote_batch, _b_ex_kline, _b_ex_kline_range,
    _b_ex_minute_today, _b_ex_minute_history,
    _b_ex_trade_today, _b_ex_trade_history,
    _b_ex_tick_chart, _b_ex_history_tick_chart,
    _b_ex_chart_sampling, _b_ex_table, _b_ex_quotes,
    _p_ex_markets, _p_ex_codes, _p_ex_quote, _p_ex_quote_batch,
    _p_ex_kline, _p_ex_kline_range, _p_ex_minute, _p_ex_minute_history, _p_ex_trade,
    _p_ex_tick_chart, _p_ex_history_tick_chart,
    _p_ex_chart_sampling, _p_ex_table, _p_ex_quotes,
)
from ..hosts import FUTURES_HOSTS_FAST, FUTURES_HOSTS_LARGE


class FuturesClient:
    def __init__(self, hosts: list[str] | None = None, timeout: float = 8.0,
                 scanner_hosts: list[str] | None = None, use_ip_health: bool = True):
        self._use_ip_health = use_ip_health
        self._scanner_hosts = scanner_hosts or FUTURES_HOSTS_LARGE
        self._hosts_override = hosts
        self._timeout = timeout
        self._tube: Tube | None = None
        self._current_host_entry = None

    def _resolve_hosts(self) -> list[str]:
        """根据 ip_health 评分或静态列表解析主机列表。"""
        if self._hosts_override:
            return self._hosts_override
        if self._use_ip_health:
            manager = get_manager()
            best = manager.get_best_futures_host()
            if best:
                return [best.host]
            return FUTURES_HOSTS
        return FUTURES_HOSTS

    def _create_tube(self, hosts: list[str] | None = None) -> Tube:
        if hosts is None:
            hosts = self._resolve_hosts()
        return Tube(
            hosts=hosts, timeout=self._timeout,
            heartbeat_cmd=CMD_EX_HEARTBEAT, heartbeat_data=_b_ex_heartbeat(0),
        )

    def _feed_scan_to_ip_health(self):
        """从扫描器获取结果并写入 ip_health 池。"""
        if not self._use_ip_health:
            return
        try:
            from ..scanner import scan_futures
            results = scan_futures(
                self._scanner_hosts, workers=64, timeout=0.5)
            manager = get_manager()
            for r in results:
                existing = manager.pool.entries.get(r.host)
                if existing:
                    existing.update(r)
                else:
                    from ..ip_health import HostEntry
                    manager.pool.add(HostEntry.from_probe(r, "7727"))
            manager.save_cache()
        except Exception:
            pass

    def _connect(self):
        """建立连接，集成扫描评分和故障转移。"""
        if self._tube is not None:
            try:
                self._tube.close()
            except Exception:
                pass
            self._tube = None

        # 先尝试扫描，但如果超时则回退到缓存
        if self._use_ip_health:
            self._feed_scan_to_ip_health()

        hosts_to_try = list(self._resolve_hosts())

        if self._use_ip_health and self._current_host_entry is not None:
            manager = get_manager()
            if self._current_host_entry.consecutive_failures >= 3:
                try:
                    rotated = manager.rotate_futures_host(self._current_host_entry)
                    if rotated.host not in hosts_to_try:
                        hosts_to_try.insert(0, rotated.host)
                except RuntimeError:
                    pass

        # 如果没有可用主机，先尝试缓存的 hosts 作为快速回退
        if not hosts_to_try:
            hosts_to_try = list(FUTURES_HOSTS)

        self._tube = self._create_tube(hosts=hosts_to_try)

        try:
            self._tube.open(PREFIX, CMD_EX_HANDSHAKE, HANDSHAKE_DATA,
                            scalar_hosts=self._scanner_hosts)
        except TubeError as e:
            self._mark_host_failed(None)
            self._tube.close()
            self._tube = None
            raise TubeError(f"failed to connect to any futures host: {e}") from None

        self._update_host_entry_on_success()

    def _mark_host_failed(self, host_str: str | None):
        if not self._use_ip_health:
            return
        target = host_str or (self._tube.host if self._tube else None)
        if not target:
            return
        manager = get_manager()
        for entry in manager.pool.entries.values():
            if entry.host == target and entry.protocol == "7727":
                entry.consecutive_failures += 1
                entry.total_checks += 1
                entry.last_check = time.time()
                if entry.consecutive_failures >= 3:
                    entry.status = "down"
                elif entry.consecutive_failures >= 1:
                    entry.status = "degraded"
                self._current_host_entry = entry
                manager.save_cache()
                return

    def _update_host_entry_on_success(self):
        if not self._use_ip_health or not self._tube or not self._tube.host:
            return
        manager = get_manager()
        for entry in manager.pool.entries.values():
            if entry.host == self._tube.host and entry.protocol == "7727":
                entry.consecutive_failures = 0
                entry.last_check = time.time()
                if entry.handshake_ok:
                    entry.status = "ok" if entry.handshake_latency_ms < 200 else "degraded"
                self._current_host_entry = entry
                manager.save_cache()
                return

    def reconnect(self):
        """根据最新扫描结果重新连接。"""
        self._connect()

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, *a):
        if self._tube:
            self._tube.close()
            self._tube = None

    def close(self):
        if self._tube:
            self._tube.close()
            self._tube = None

    @property
    def host(self):
        return self._tube.host if self._tube else None

    @property
    def ip_health_entry(self):
        return self._current_host_entry

    def _exec(self, cmd: int, payload: bytes, _retry: int = 0):
        try:
            return self._tube.call(cmd, payload, PREFIX)
        except TubeError as e:
            self._mark_host_failed(self._tube.host if self._tube else None)
            if _retry >= 1:
                raise
            self._connect()
            return self._exec(cmd, payload, _retry=_retry + 1)

    # -- 市场/代码 --
    def markets(self) -> list[dict]:
        r = self._exec(CMD_EX_MARKETS, _b_ex_markets())
        return _p_ex_markets(r.data)

    def codes(self, mid: int, start: int = 0, count: int = 200) -> list[dict]:
        r = self._exec(CMD_EX_CODES, _b_ex_codes(mid, start, count))
        return _p_ex_codes(r.data)

    def codes_all(self, mid: int) -> list[dict]:
        all_codes = []
        start = 0
        empty_pages = 0
        while start < 50000:
            batch = self.codes(mid, start, 200)
            if not batch:
                break
            matched = [r for r in batch if r.get("market_id") == mid]
            all_codes.extend(matched)
            if matched:
                empty_pages = 0
            else:
                empty_pages += 1
                if empty_pages >= 10:
                    break
            start += 200
        return all_codes

    # -- 行情 --
    def quote(self, mid: int, code: str) -> Quote:
        r = self._exec(CMD_EX_QUOTE, _b_ex_quote(mid, code))
        return _p_ex_quote(r.data, mid, code)

    def quote_batch(self, mid: int, start: int = 0, count: int = 200) -> list[Quote]:
        r = self._exec(CMD_EX_QUOTE_BATCH, _b_ex_quote_batch(mid, start, count))
        return _p_ex_quote_batch(r.data)

    # -- K线 --
    def kline(self, mid: int, code: str, period: str = "day",
              start: int = 0, count: int = 800) -> list[Kline]:
        r = self._exec(CMD_EX_KLINE, _b_ex_kline(mid, code, period, start, count))
        return _p_ex_kline(r.data, mid, code, period)

    def kline_range(self, mid: int, code: str, period: str = "day",
                    start_date=None, end_date=None) -> list[Kline]:
        if isinstance(start_date, str):
            start_date = int(start_date.replace("-", "").replace("/", ""))
        if isinstance(end_date, str):
            end_date = int(end_date.replace("-", "").replace("/", ""))
        r = self._exec(CMD_EX_KLINE_RANGE, _b_ex_kline_range(
            mid, code, period, start_date, end_date))
        return _p_ex_kline_range(r.data, mid, code, period)

    # -- 分时 --
    def today_minute(self, mid: int, code: str) -> list[Minute]:
        r = self._exec(CMD_EX_MINUTE_TODAY, _b_ex_minute_today(mid, code))
        return _p_ex_minute(r.data, mid, code)

    def history_minute(self, mid: int, code: str, tdate) -> list[Minute]:
        if isinstance(tdate, str):
            tdate = int(tdate.replace("-", "").replace("/", ""))
        r = self._exec(CMD_EX_MINUTE_HISTORY, _b_ex_minute_history(mid, code, tdate))
        return _p_ex_minute_history(r.data, mid, code)

    # -- 成交 --
    def today_trade(self, mid: int, code: str, start: int = 0, count: int = 100) -> list[Trade]:
        r = self._exec(CMD_EX_TRADE_TODAY, _b_ex_trade_today(mid, code, start, count))
        return _p_ex_trade(r.data, mid, code)

    def history_trade(self, mid: int, code: str, tdate, start: int = 0, count: int = 100) -> list[Trade]:
        if isinstance(tdate, str):
            tdate = int(tdate.replace("-", "").replace("/", ""))
        r = self._exec(CMD_EX_TRADE_HISTORY, _b_ex_trade_history(mid, code, tdate, start, count))
        return _p_ex_trade(r.data, mid, code)

    # -- 分时图 --

    def tick_chart(self, mid: int, code: str) -> list[dict]:
        """当日分时图."""
        r = self._exec(CMD_EX_TICK_CHART, _b_ex_tick_chart(mid, code))
        return _p_ex_tick_chart(r.data)

    def history_tick_chart(self, mid: int, code: str, tdate) -> list[dict]:
        """历史分时图."""
        if isinstance(tdate, str):
            tdate = int(tdate.replace("-", "").replace("/", ""))
        r = self._exec(CMD_EX_HISTORY_TICK_CHART, _b_ex_history_tick_chart(mid, code, tdate))
        return _p_ex_history_tick_chart(r.data)

    # -- K线采样 --

    def chart_sampling(self, mid: int, code: str) -> list[float]:
        """K线采样价格序列."""
        r = self._exec(CMD_EX_CHART_SAMPLING, _b_ex_chart_sampling(mid, code))
        return _p_ex_chart_sampling(r.data)

    # -- 表格数据 --

    def table(self, start: int = 0, mode: int = 1) -> tuple[int, int, str]:
        """表格数据 (分页)."""
        r = self._exec(CMD_EX_TABLE, _b_ex_table(start, mode))
        return _p_ex_table(r.data)

    def table_detail(self, start: int = 0) -> tuple[int, int, str]:
        """表格详情."""
        r = self._exec(CMD_EX_TABLE_DETAIL, _b_ex_table(start, mode=0))
        return _p_ex_table(r.data)

    # -- 批量行情 --

    def quotes(self, code_list: list[tuple[int, str]]) -> list[dict]:
        """批量详细行情 (多品种)."""
        r = self._exec(CMD_EX_QUOTES, _b_ex_quotes(code_list))
        return _p_ex_quotes(r.data)

    def get_main_contract(self, product: str = "IF", lookahead_months: int = 3) -> str | None:
        """自动探测活跃合约。
        
        从当前月份起向后轮询 lookahead_months 个月，
        返回第一个 price > 0 的合约代码。
        """
        now = datetime.now()
        for offset in range(lookahead_months):
            target = now + timedelta(days=32 * offset)
            code = f"{product}{target.strftime('%y%m')}"
            try:
                q = self.quote(47, code)
                if hasattr(q, 'price') and q.price > 0:
                    return code
            except Exception:
                continue
        return None

    def safe_exec(self, func, *args, **kwargs):
        """安全执行，捕获 remote closed 等异常并返回空数据。"""
        try:
            return func(*args, **kwargs)
        except (ConnectionError, TubeError, TimeoutError, OSError):
            return kwargs.get("_fallback", [])
