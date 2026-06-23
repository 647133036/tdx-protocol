"""7709 股票行情客户端。

组合 Tube 传输层 + 命令构造器/解析器，提供业务级 API。
"""

from datetime import date
from typing import Optional, Sequence

from ..tube import Tube
from ..models import Quote, Kline, Minute, Trade, EquityChange, FinanceInfo, PriceLimit
from .commands import (
    CMD_HANDSHAKE, CMD_HEARTBEAT, CMD_COUNT, CMD_LIST,
    CMD_SNAPSHOT, CMD_REFRESH, CMD_CATEGORY, CMD_KLINE,
    CMD_TODAY_MINUTE, CMD_HISTORY_MINUTE, CMD_RECENT_MINUTE,
    CMD_AUX, CMD_SPARKLINE, CMD_TODAY_TRADE, CMD_HISTORY_TRADE,
    CMD_AUCTION, CMD_CAPITAL, CMD_FINANCE, CMD_LIMIT,
    PREFIX, STOCK_HOSTS,
    _b_handshake, _b_heartbeat, _b_count, _b_list,
    _b_snapshot, _b_refresh, _b_category,
    _b_kline, _b_today_minute, _b_history_minute, _b_recent_minute,
    _b_aux, _b_sparkline, _b_today_trade, _b_history_trade,
    _b_auction, _b_capital, _b_finance, _b_limit,
    _p_handshake, _p_heartbeat, _p_count, _p_list,
    _p_snapshot, _p_refresh, _p_category, _p_kline,
    _p_today_minute, _p_history_minute, _p_recent_minute,
    _p_aux, _p_sparkline, _p_today_trade, _p_history_trade,
    _p_auction, _p_capital, _p_finance, _p_limit,
)
from ..hosts import STOCK_HOSTS_FAST, STOCK_HOSTS_LARGE


class StockClient:
    def __init__(self, hosts: list[str] | None = None, timeout: float = 8.0,
                 scanner_hosts: list[str] | None = None):
        self._tube = Tube(
            hosts=hosts or STOCK_HOSTS, timeout=timeout,
            heartbeat_cmd=CMD_HEARTBEAT, heartbeat_data=_b_heartbeat(),
        )
        self._scanner_hosts = scanner_hosts or STOCK_HOSTS_LARGE

    def __enter__(self):
        self._tube.open(PREFIX, CMD_HANDSHAKE, _b_handshake(),
                        scalar_hosts=self._scanner_hosts)
        return self

    def __exit__(self, *a): self._tube.close()
    def close(self): self._tube.close()
    @property
    def host(self): return self._tube.host

    def _exec(self, cmd: int, payload: bytes):
        return self._tube.call(cmd, payload, PREFIX)

    # -- 代码表 --
    def count(self, market: str) -> int:
        r = self._exec(CMD_COUNT, _b_count(market))
        return _p_count(r.data, market)

    def codes(self, market: str, start: int = 0, limit: int = 1600) -> list[dict]:
        r = self._exec(CMD_LIST, _b_list(market, start, limit))
        return _p_list(r.data)

    def codes_all(self, market: str) -> list[dict]:
        all_codes = []
        start = 0
        while True:
            batch = self.codes(market, start, 800)
            if not batch: break
            all_codes.extend(batch)
            if len(batch) < 800: break
            start += 800
        return all_codes

    # -- 行情 --
    def quote(self, codes: Sequence[str]) -> list[Quote]:
        r = self._exec(CMD_SNAPSHOT, _b_snapshot(codes))
        return _p_snapshot(r.data)

    def refresh(self, codes: Sequence[str]) -> list[Quote]:
        r = self._exec(CMD_REFRESH, _b_refresh(codes))
        return _p_refresh(r.data)

    def category(self, market: str = "sz", start: int = 0, limit: int = 80) -> list[Quote]:
        r = self._exec(CMD_CATEGORY, _b_category(market, start, limit))
        return _p_category(r.data)

    # -- K线 --
    def kline(self, code: str, period: str = "day", start: int = 0, count: int = 800,
              adjust: str = "", anchor_date: str = "") -> list[Kline]:
        r = self._exec(CMD_KLINE, _b_kline(code, period, start, count, adjust, anchor_date))
        return _p_kline(r.data, code, period)

    def kline_all(self, code: str, period: str = "day", adjust: str = "") -> list[Kline]:
        all_bars = []
        start = 0
        while True:
            batch = self.kline(code, period, start, 800, adjust)
            if not batch: break
            all_bars.extend(batch)
            if len(batch) < 800: break
            start += 800
        return all_bars

    # -- 分时 --
    def today_minute(self, code: str) -> list[Minute]:
        r = self._exec(CMD_TODAY_MINUTE, _b_today_minute(code))
        return _p_today_minute(r.data, code)

    def history_minute(self, code: str, tdate) -> list[Minute]:
        r = self._exec(CMD_HISTORY_MINUTE, _b_history_minute(code, tdate))
        return _p_history_minute(r.data, code)

    def recent_minute(self, code: str, tdate=None) -> list[Minute]:
        r = self._exec(CMD_RECENT_MINUTE, _b_recent_minute(code, tdate))
        return _p_recent_minute(r.data, code)

    # -- 副图/走势图 --
    def aux(self, code: str, kind: str = "buy_sell") -> list[dict]:
        r = self._exec(CMD_AUX, _b_aux(code, kind))
        return _p_aux(r.data)

    def sparkline(self, code: str, selector: int = 1, window: int = 20) -> dict:
        r = self._exec(CMD_SPARKLINE, _b_sparkline(code, selector, window))
        return _p_sparkline(r.data)

    # -- 成交 --
    def today_trade(self, code: str, start: int = 0, count: int = 115) -> list[Trade]:
        r = self._exec(CMD_TODAY_TRADE, _b_today_trade(code, start, count))
        return _p_today_trade(r.data, code, start)

    def history_trade(self, code: str, tdate, start: int = 0, count: int = 900) -> list[Trade]:
        r = self._exec(CMD_HISTORY_TRADE, _b_history_trade(code, tdate, start, count))
        return _p_history_trade(r.data, code)

    def history_trade_all(self, code: str, tdate) -> list[Trade]:
        all_ticks = []
        start = 0
        while True:
            batch = self.history_trade(code, tdate, start, 900)
            if not batch: break
            all_ticks.extend(batch)
            if len(batch) < 900: break
            start += 900
        return all_ticks

    # -- 竞价 --
    def auction(self, code: str, mode: int = 3) -> list[dict]:
        r = self._exec(CMD_AUCTION, _b_auction(code, mode))
        return _p_auction(r.data, code)

    # -- 公司 --
    def capital_changes(self, code: str) -> list[EquityChange]:
        r = self._exec(CMD_CAPITAL, _b_capital(code))
        return _p_capital(r.data, code)

    def finance(self, codes: Sequence[str]) -> list[FinanceInfo]:
        r = self._exec(CMD_FINANCE, _b_finance(codes))
        return _p_finance(r.data)

    def limits(self, start: int = 0) -> list[PriceLimit]:
        r = self._exec(CMD_LIMIT, _b_limit(start))
        return _p_limit(r.data)
