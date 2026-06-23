"""7727 期货扩展行情 — 命令构造器与解析器。

命令:
  握手:     0x2454 (80B 固定魔数)
  心跳:     0x23F0 (品种数量)
  市场表:   0x23F4
  代码表:   0x23F5
  五档行情: 0x23FA (单品种)
  批量行情: 0x2400
  K线:      0x23FF, 0x240D (区间)
  分时:     0x240B (当日), 0x240C (历史)
  成交:     0x23FC (当日), 0x2406 (历史)
"""

import struct
from datetime import date, datetime
from typing import Optional, Sequence

from ..codec import f32, u16, u32, date_int, int_date
from ..models import Quote, Kline, Minute, Trade

CMD_EX_HANDSHAKE = 0x2454
CMD_EX_HEARTBEAT = 0x23F0
CMD_EX_MARKETS = 0x23F4
CMD_EX_CODES = 0x23F5
CMD_EX_QUOTE = 0x23FA
CMD_EX_QUOTE_BATCH = 0x2400
CMD_EX_KLINE = 0x23FF
CMD_EX_KLINE_RANGE = 0x240D
CMD_EX_MINUTE_TODAY = 0x240B
CMD_EX_MINUTE_HISTORY = 0x240C
CMD_EX_TRADE_TODAY = 0x23FC
CMD_EX_TRADE_HISTORY = 0x2406

PREFIX = 0x01

HANDSHAKE_DATA = bytes.fromhex(
    "1f32c6e5d53dfb41" "1f32c6e5d53dfb41"
    "1f32c6e5d53dfb41" "1f32c6e5d53dfb41"
    "1f32c6e5d53dfb41" "1f32c6e5d53dfb41"
    "1f32c6e5d53dfb41" "1f32c6e5d53dfb41"
    "cce16dffd5ba3fb8" "cbc57a054f7748ea"
)

from ..hosts import FUTURES_HOSTS_FAST as FUTURES_HOSTS

TRADE_NATURE = {
    0x01: "多开", 0x02: "空开", 0x03: "多平", 0x04: "空平",
    0x05: "双开", 0x06: "双平", 0x07: "多换", 0x08: "空换", 0x09: "换手",
}
TRADE_DIR = {0: "买入", 1: "卖出", 2: "中性"}

PERIOD_MAP = {"1m": 8, "5m": 0, "15m": 1, "30m": 2, "60m": 3, "day": 4, "week": 5, "month": 6}


def _encode_code(mid: int, code: str) -> bytes:
    return mid.to_bytes(2, "little") + code.encode("ascii").ljust(9, b"\x00")


# ===== 构造器 =====

def _b_ex_handshake() -> bytes: return HANDSHAKE_DATA

def _b_ex_heartbeat(mid: int = 0) -> bytes: return mid.to_bytes(2, "little")

def _b_ex_markets() -> bytes: return b""

def _b_ex_codes(mid: int, start: int = 0, count: int = 200) -> bytes:
    return (mid.to_bytes(2, "little") + start.to_bytes(2, "little") + count.to_bytes(2, "little"))

def _b_ex_quote(mid: int, code: str) -> bytes: return _encode_code(mid, code)

def _b_ex_quote_batch(mid: int, start: int = 0, count: int = 200) -> bytes:
    return mid.to_bytes(2, "little") + start.to_bytes(2, "little") + count.to_bytes(2, "little")

def _b_ex_kline(mid: int, code: str, period: str = "day", start: int = 0, count: int = 800) -> bytes:
    pc = PERIOD_MAP.get(period, 4)
    return (_encode_code(mid, code) + pc.to_bytes(2, "little") +
            start.to_bytes(2, "little") + count.to_bytes(2, "little"))

def _b_ex_minute_today(mid: int, code: str) -> bytes: return _encode_code(mid, code)

def _b_ex_minute_history(mid: int, code: str, tdate) -> bytes:
    return date_int(tdate).to_bytes(4, "little") + _encode_code(mid, code)

def _b_ex_trade_today(mid: int, code: str, start: int = 0, count: int = 100) -> bytes:
    return (_encode_code(mid, code) + start.to_bytes(2, "little") + count.to_bytes(2, "little"))

def _b_ex_trade_history(mid: int, code: str, tdate, start: int = 0, count: int = 100) -> bytes:
    return (date_int(tdate).to_bytes(4, "little") + _encode_code(mid, code) +
            start.to_bytes(2, "little") + count.to_bytes(2, "little"))


# ===== 解析器 =====

def _p_ex_markets(data: bytes) -> list[dict]:
    if not data: return []
    count = data[0]
    markets = []
    off = 1
    for _ in range(count):
        if off + 2 > len(data): break
        mid = data[off]; nl = data[off + 1]; off += 2
        name = data[off:off + nl].decode("gbk", errors="ignore"); off += nl
        cat = data[off] if off < len(data) else 0; off += 1
        markets.append({"market_id": mid, "name": name, "category": cat})
    return markets

def _p_ex_codes(data: bytes) -> list[dict]:
    if len(data) < 2: return []
    count = u16(data, 0)
    codes = []
    off = 2
    for _ in range(count):
        if off + 11 > len(data): break
        mid = u16(data, off)
        code = data[off + 2:off + 11].rstrip(b"\x00").decode("ascii", errors="ignore")
        codes.append({"market_id": mid, "code": code})
        off += 11
    return codes

def _p_ex_quote(data: bytes, mid: int, code: str) -> Quote:
    if len(data) < 60: return Quote(code=code)
    off = 0
    rmid = u16(data, off) or mid; off += 2
    rcode = data[off:off + 9].rstrip(b"\x00").decode("ascii", errors="ignore") or code; off += 9
    nl = data[off]; off += 1
    name = data[off:off + nl].decode("gbk", errors="ignore") if off + nl <= len(data) else ""; off += nl
    if off + 100 > len(data): return Quote(code=rcode, name=name)
    q = Quote(code=rcode, name=name)
    q.pre_close = f32(data, off)
    q.open = f32(data, off + 4)
    q.high = f32(data, off + 8)
    q.low = f32(data, off + 12)
    q.price = f32(data, off + 16)
    q.volume = u32(data, off + 20)
    q.amount = f32(data, off + 24)
    q.open_interest = u32(data, off + 44)
    for i in range(5):
        q.bid_p[i] = f32(data, off + 48 + i * 4)
        q.ask_p[i] = f32(data, off + 48 + 20 + i * 4)
        q.bid_v[i] = u32(data, off + 48 + 40 + i * 4)
        q.ask_v[i] = u32(data, off + 48 + 60 + i * 4)
    q.raw = data
    return q

def _p_ex_quote_batch(data: bytes) -> list[Quote]:
    if len(data) < 2: return []
    count = u16(data, 0)
    quotes = []
    off = 2
    for _ in range(count):
        if off + 60 > len(data): break
        mid = u16(data, off)
        code = data[off + 2:off + 11].rstrip(b"\x00").decode("ascii", errors="ignore")
        q = Quote(code=code)
        q.price = f32(data, off + 11)
        q.volume = u32(data, off + 15)
        q.amount = f32(data, off + 19)
        q.open_interest = u32(data, off + 35)
        q.bid_p[0] = f32(data, off + 39)
        q.ask_p[0] = f32(data, off + 43)
        q.raw = data[off:off + 60]
        quotes.append(q)
        off += 60
    return quotes

def _p_ex_kline(data: bytes, mid: int, code: str, period: str) -> list[Kline]:
    if len(data) < 4: return []
    count = u16(data, 0)
    bars = []
    off = 4
    rsize = 40
    for _ in range(min(count, (len(data) - 4) // rsize)):
        if off + rsize > len(data): break
        dt = u32(data, off)
        k = Kline(
            time=f"{dt:08d}" if period in ("day", "week", "month") else f"{u16(data, off):02d}:{u16(data, off + 2):02d}",
            open=f32(data, off + 4), high=f32(data, off + 8),
            low=f32(data, off + 12), close=f32(data, off + 16),
            volume=u32(data, off + 20), amount=f32(data, off + 24),
            position=u32(data, off + 28), settlement=f32(data, off + 32),
        )
        bars.append(k)
        off += rsize
    return bars

def _p_ex_minute(data: bytes, mid: int, code: str) -> list[Minute]:
    if len(data) < 4: return []
    count = u16(data, 0)
    prev_close = f32(data, 4)
    pts = []
    off = 8
    for i in range(count):
        if off + 16 > len(data): break
        pts.append(Minute(
            time=f"{i:03d}",
            price=f32(data, off), volume=u32(data, off + 4),
            avg_price=f32(data, off + 8), open_interest=u32(data, off + 12),
        ))
        off += 16
    return pts

def _p_ex_trade(data: bytes, mid: int, code: str) -> list[Trade]:
    if len(data) < 6: return []
    count = u16(data, 4)
    ticks = []
    off = 6
    rsize = 48
    for _ in range(min(count, (len(data) - 6) // rsize)):
        if off + rsize > len(data): break
        rec = data[off:off + rsize]; off += rsize
        h, m, s = rec[2:5] if len(rec) >= 5 else (0, 0, 0)
        price = f32(rec, 6)
        vol = u32(rec, 10)
        nat = rec[23] if len(rec) > 23 else 0
        d = rec[25] if len(rec) > 25 else 0
        zc = u32(rec, 26) if len(rec) >= 30 else 0
        ticks.append(Trade(
            time=f"{h:02d}:{m:02d}:{s:02d}",
            price=price, volume=vol,
            direction=TRADE_DIR.get(d, f"{d}"),
            nature=TRADE_NATURE.get(nat, f"{nat}"),
            zeng_cang=zc,
        ))
    return ticks
