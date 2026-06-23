"""7727 期货行情客户端。"""

from datetime import date
from typing import Optional, Sequence

from ..tube import Tube
from ..models import Quote, Kline, Minute, Trade
from .commands import (
    CMD_EX_HANDSHAKE, CMD_EX_HEARTBEAT, CMD_EX_MARKETS, CMD_EX_CODES,
    CMD_EX_QUOTE, CMD_EX_QUOTE_BATCH, CMD_EX_KLINE, CMD_EX_KLINE_RANGE,
    CMD_EX_MINUTE_TODAY, CMD_EX_MINUTE_HISTORY,
    CMD_EX_TRADE_TODAY, CMD_EX_TRADE_HISTORY,
    PREFIX, FUTURES_HOSTS, HANDSHAKE_DATA,
    _b_ex_heartbeat, _b_ex_markets, _b_ex_codes,
    _b_ex_quote, _b_ex_quote_batch, _b_ex_kline,
    _b_ex_minute_today, _b_ex_minute_history,
    _b_ex_trade_today, _b_ex_trade_history,
    _p_ex_markets, _p_ex_codes, _p_ex_quote, _p_ex_quote_batch,
    _p_ex_kline, _p_ex_minute, _p_ex_trade,
)
from ..hosts import FUTURES_HOSTS_FAST, FUTURES_HOSTS_LARGE


class FuturesClient:
    def __init__(self, hosts: list[str] | None = None, timeout: float = 8.0,
                 scanner_hosts: list[str] | None = None):
        self._tube = Tube(
            hosts=hosts or FUTURES_HOSTS, timeout=timeout,
            heartbeat_cmd=CMD_EX_HEARTBEAT, heartbeat_data=_b_ex_heartbeat(0),
        )
        self._scanner_hosts = scanner_hosts or FUTURES_HOSTS_LARGE

    def __enter__(self):
        self._tube.open(PREFIX, CMD_EX_HANDSHAKE, HANDSHAKE_DATA,
                        scalar_hosts=self._scanner_hosts)
        return self

    def __exit__(self, *a): self._tube.close()
    def close(self): self._tube.close()
    @property
    def host(self): return self._tube.host

    def _exec(self, cmd: int, payload: bytes):
        return self._tube.call(cmd, payload, PREFIX)

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
        while True:
            batch = self.codes(mid, start, 200)
            if not batch: break
            all_codes.extend(batch)
            if len(batch) < 200: break
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

    # -- 分时 --
    def today_minute(self, mid: int, code: str) -> list[Minute]:
        r = self._exec(CMD_EX_MINUTE_TODAY, _b_ex_minute_today(mid, code))
        return _p_ex_minute(r.data, mid, code)

    def history_minute(self, mid: int, code: str, tdate) -> list[Minute]:
        r = self._exec(CMD_EX_MINUTE_HISTORY, _b_ex_minute_history(mid, code, tdate))
        return _p_ex_minute(r.data, mid, code)

    # -- 成交 --
    def today_trade(self, mid: int, code: str, start: int = 0, count: int = 100) -> list[Trade]:
        r = self._exec(CMD_EX_TRADE_TODAY, _b_ex_trade_today(mid, code, start, count))
        return _p_ex_trade(r.data, mid, code)

    def history_trade(self, mid: int, code: str, tdate, start: int = 0, count: int = 100) -> list[Trade]:
        r = self._exec(CMD_EX_TRADE_HISTORY, _b_ex_trade_history(mid, code, tdate, start, count))
        return _p_ex_trade(r.data, mid, code)
