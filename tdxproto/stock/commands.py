"""7709 股票行情 — 全部 19 个命令的构造器与解析器。

命令:
  握手/心跳: 0x000d, 0x0004
  代码表:     0x044d, 0x044e
  行情:       0x054c, 0x0547 (批量快照 / 增量刷新), 0x054b (分类行情)
  K线:       0x052d (含服务端复权)
  分时:       0x0537, 0x0fb4, 0x0feb (当日 / 历史 / 近期)
  副图/走势:  0x051b, 0x0fd1
  成交:       0x0fc5, 0x0fc6 (当日 / 历史)
  竞价:       0x056a
  公司:       0x000f, 0x0010, 0x0452 (股本 / 财务 / 涨跌停)
"""

import struct
from datetime import date, datetime
from typing import Optional, Sequence

from ..codec import (
    f32, u16, u32, varint, decode_volume,
    split_code, date_int, int_date, minute_label, recent_selector,
)
from ..models import (
    Quote, Kline, Minute, Trade,
    EquityChange, FinanceInfo, PriceLimit,
)

# ============== 常量 ==============

CMD_HANDSHAKE = 0x000D
CMD_HEARTBEAT = 0x0004
CMD_COUNT = 0x044E
CMD_LIST = 0x044D
CMD_SNAPSHOT = 0x054C
CMD_REFRESH = 0x0547
CMD_CATEGORY = 0x054B
CMD_KLINE = 0x052D
CMD_TODAY_MINUTE = 0x0537
CMD_HISTORY_MINUTE = 0x0FB4
CMD_RECENT_MINUTE = 0x0FEB
CMD_AUX = 0x051B
CMD_SPARKLINE = 0x0FD1
CMD_TODAY_TRADE = 0x0FC5
CMD_HISTORY_TRADE = 0x0FC6
CMD_AUCTION = 0x056A
CMD_CAPITAL = 0x000F
CMD_FINANCE = 0x0010
CMD_LIMIT = 0x0452

PREFIX = 0x0C

from ..hosts import STOCK_HOSTS_FAST as STOCK_HOSTS

CAPITAL_NAMES = {
    1: "除权除息", 2: "送配股上市", 3: "非流通股上市",
    4: "国家股配售", 5: "股本变化", 6: "增发新股",
    7: "股份回购", 8: "增发新股上市", 9: "转配股上市",
    10: "可转债上市", 11: "扩缩股", 12: "非流通股缩股",
    13: "送认购权证", 14: "送认沽权证", 15: "重整调整",
}
FLOAT_CATS = {1, 11, 12, 13, 14, 15}

# ============== 构造器 (builders) ==============

def _b_handshake() -> bytes: return b""
def _b_heartbeat() -> bytes: return b""

def _b_count(market: str) -> bytes:
    mid = {"sz": 0, "sh": 1, "bj": 2}[market]
    return bytes([mid, 0])

def _b_list(market: str, start: int = 0, limit: int = 1600) -> bytes:
    mid = {"sz": 0, "sh": 1, "bj": 2}[market]
    return bytes([mid, 0]) + start.to_bytes(2, "little") + limit.to_bytes(2, "little")

def _b_snapshot(codes: Sequence[str]) -> bytes:
    data = bytearray(len(codes).to_bytes(2, "little"))
    for c in codes:
        mid, _, num = split_code(c)
        data.append(mid)
        data.extend(num.encode("ascii"))
    return bytes(data)

def _b_refresh(codes: Sequence[str]) -> bytes:
    data = bytearray(len(codes).to_bytes(2, "little"))
    for c in codes:
        mid, _, num = split_code(c)
        data.append(mid)
        data.extend(num.encode("ascii"))
    return bytes(data)

def _b_category(market: str, start: int = 0, limit: int = 80) -> bytes:
    mid = {"sz": 0, "sh": 1, "bj": 2}[market]
    return mid.to_bytes(2, "little") + start.to_bytes(2, "little") + limit.to_bytes(2, "little")

def _b_kline(code: str, period: str = "day", start: int = 0, count: int = 800,
             adjust: str = "", anchor_date: str = "") -> bytes:
    mid, _, num = split_code(code)
    period_map = {"1m": 0, "5m": 1, "15m": 2, "30m": 3, "60m": 4, "day": 5, "week": 6, "month": 7, "quarter": 8, "year": 9}
    period_byte = period_map.get(period, 5)
    data = bytes([mid]) + num.encode("ascii") + bytes([period_byte, 0])
    if adjust:
        if adjust == "qfq":
            data += b"\x01\x00" + date_int(anchor_date).to_bytes(4, "little") + b"\x00"
        elif adjust == "hfq":
            data += b"\x02\x00" + date_int(anchor_date).to_bytes(4, "little") + b"\x00"
        else:
            data += b"\x00" * 7
    else:
        data += b"\x00" * 7
    data += start.to_bytes(2, "little") + count.to_bytes(2, "little")
    return data

def _b_today_minute(code: str) -> bytes:
    from ..codec import code_wire
    return code_wire(code) + b"\x00\x00\x00\x93"

def _b_history_minute(code: str, tdate) -> bytes:
    mid, _, num = split_code(code)
    return date_int(tdate).to_bytes(4, "little") + bytes([mid]) + num.encode("ascii")

def _b_recent_minute(code: str, tdate) -> bytes:
    mid, _, num = split_code(code)
    d = date_int(tdate)
    td = int_date(d) or date.today()
    sel = recent_selector(td)
    return sel.to_bytes(4, "little") + bytes([mid]) + num.encode("ascii")

def _b_aux(code: str, kind: str = "buy_sell") -> bytes:
    mid, _, num = split_code(code)
    sel_map = {"buy_sell": 0x00, "volume_compare": 0x0B}
    sel = sel_map.get(kind, 0x00)
    return mid.to_bytes(2, "little") + num.encode("ascii") + b"\x00" * 19 + bytes([sel])

def _b_sparkline(code: str, selector: int = 1, window: int = 20) -> bytes:
    mid, _, num = split_code(code)
    return (bytes([mid, 0]) + num.encode("ascii") + b"\x00" * 16 +
            bytes([selector, 0]) + window.to_bytes(2, "little") +
            b"\x00\x00\x00\x01" + b"\x00" * 5)

def _b_today_trade(code: str, start: int = 0, count: int = 115) -> bytes:
    mid, _, num = split_code(code)
    return bytes([mid, 0]) + num.encode("ascii") + start.to_bytes(2, "little") + count.to_bytes(2, "little")

def _b_history_trade(code: str, tdate, start: int = 0, count: int = 900) -> bytes:
    mid, _, num = split_code(code)
    return (date_int(tdate).to_bytes(4, "little") + mid.to_bytes(2, "little") +
            num.encode("ascii") + start.to_bytes(2, "little") + count.to_bytes(2, "little"))

def _b_auction(code: str, mode: int = 3, start: int = 0, limit: int = 500) -> bytes:
    mid, _, num = split_code(code)
    return (bytes([mid, 0]) + num.encode("ascii") + b"\x00" * 4 +
            mode.to_bytes(4, "little") + b"\x00" * 4 +
            start.to_bytes(4, "little") + limit.to_bytes(4, "little"))

def _b_capital(code: str) -> bytes:
    mid, _, num = split_code(code)
    return b"\x01\x00" + bytes([mid]) + num.encode("ascii")

def _b_finance(codes: Sequence[str]) -> bytes:
    data = bytearray(len(codes).to_bytes(2, "little"))
    for c in codes:
        mid, _, num = split_code(c)
        data.append(mid)
        data.extend(num.encode("ascii"))
    return bytes(data)

def _b_limit(start: int = 0) -> bytes:
    return start.to_bytes(2, "little") + b"\x00" * 12


# ============== 解析器 (parsers) ==============

def _p_handshake(data: bytes) -> dict:
    if len(data) < 20:
        return {"raw": data.hex()}
    return {
        "server_date": f"{u16(data, 4):04d}-{u16(data, 6):02d}-{u16(data, 8):02d}",
        "server_time": f"{u16(data, 10):02d}:{u16(data, 12):02d}:{u16(data, 14):02d}",
    }

def _p_heartbeat(data: bytes) -> dict:
    return {"echo": data.hex()[:20]}

def _p_count(data: bytes, market: str) -> int:
    return u16(data, 0) if len(data) >= 2 else 0

def _p_list(data: bytes) -> list[dict]:
    if len(data) < 2: return []
    count = u16(data, 0)
    items = []
    off = 2
    for _ in range(count):
        if off + 30 > len(data): break
        mid = data[off]
        code = data[off + 1:off + 7].decode("ascii")
        name = data[off + 8:off + 16].rstrip(b"\x00").decode("gbk", errors="ignore")
        market = {0: "sz", 1: "sh", 2: "bj"}.get(mid, "?")
        items.append({"code": f"{market}{code}", "name": name, "market": market})
        off += 30
    return items

def _p_snapshot(data: bytes) -> list[Quote]:
    if len(data) < 2: return []
    count = u16(data, 0)
    quotes = []
    off = 2
    for _ in range(count):
        if off + 60 > len(data): break
        mid = u16(data, off)
        code = data[off + 2:off + 8].decode("ascii")
        market = {0: "sz", 1: "sh", 2: "bj"}.get(mid, "?")
        q = Quote(code=f"{market}{code}", market=market)
        q.price = f32(data, off + 8)
        q.pre_close = f32(data, off + 12)
        q.open = f32(data, off + 16)
        q.high = f32(data, off + 20)
        q.low = f32(data, off + 24)
        q.volume = u32(data, off + 28)
        q.amount = f32(data, off + 32)
        change = q.price - q.pre_close
        q.change_pct = change / q.pre_close * 100 if q.pre_close else 0.0
        q.raw = data[off:off + 60]
        quotes.append(q)
        off += 60
    return quotes

def _p_refresh(data: bytes) -> list[Quote]:
    return _p_snapshot(data)

def _p_category(data: bytes) -> list[Quote]:
    if len(data) < 20: return []
    count = u16(data, 14)
    items = []
    off = 20
    for _ in range(count):
        if off + 68 > len(data): break
        mid = u16(data, off)
        code = data[off + 2:off + 8].decode("ascii")
        market = {0: "sz", 1: "sh", 2: "bj"}.get(mid, "?")
        q = Quote(code=f"{market}{code}", market=market)
        q.price = f32(data, off + 16)
        q.change_pct = f32(data, off + 20)
        q.volume = u32(data, off + 24)
        q.amount = f32(data, off + 28)
        q.raw = data[off:off + 68]
        items.append(q)
        off += 68
    return items

def _p_kline(data: bytes, code: str, period: str) -> list[Kline]:
    if len(data) < 4: return []
    count = u16(data, 0)
    bars = []
    off = 4
    rsize = 32
    for _ in range(min(count, (len(data) - 4) // rsize)):
        if off + rsize > len(data): break
        dt_val = u32(data, off)
        dt_str = f"{dt_val:08d}"
        k = Kline(
            time=dt_str,
            open=f32(data, off + 4), high=f32(data, off + 8),
            low=f32(data, off + 12), close=f32(data, off + 16),
            volume=u32(data, off + 20), amount=f32(data, off + 24),
        )
        bars.append(k)
        off += rsize
    return bars

def _p_today_minute(data: bytes, code: str) -> list[Minute]:
    if len(data) < 4: return []
    count = u16(data, 0)
    pts = []
    off = 4
    fp, fa = None, None
    for i in range(count):
        pf, off = varint(data, off)
        af, off = varint(data, off)
        vol, off = varint(data, off)
        if fp is None: fp, fa = pf, af
        pr = pf if i == 0 else fp + pf
        ar = af if i == 0 else fa + af
        pts.append(Minute(time=minute_label(i), price=pr / 1000.0,
                          volume=vol, avg_price=ar / 10000.0))
    return pts

def _p_history_minute(data: bytes, code: str) -> list[Minute]:
    if len(data) < 6: return []
    count = u16(data, 0)
    prev_close = f32(data, 2)
    pts = []
    off = 6
    price_acc = 0
    for i in range(count):
        pd, off = varint(data, off)
        ad, off = varint(data, off)
        vol, off = varint(data, off)
        price_acc += pd
        pts.append(Minute(time=minute_label(i), price=price_acc / 1000.0, volume=vol))
    return pts

def _p_recent_minute(data: bytes, code: str) -> list[Minute]:
    if len(data) < 10: return []
    count = u16(data, 0)
    prev_close = f32(data, 2)
    open_p = f32(data, 6)
    pts = []
    off = 10
    fp, fa = None, None
    for i in range(count):
        pf, off = varint(data, off)
        af, off = varint(data, off)
        vol, off = varint(data, off)
        if fp is None: fp, fa = pf, af
        pr = pf if i == 0 else fp + pf
        ar = af if i == 0 else fa + af
        pts.append(Minute(time=minute_label(i), price=pr / 1000.0,
                          volume=vol, avg_price=ar / 10000.0))
    return pts

def _p_aux(data: bytes) -> list[dict]:
    if len(data) < 2: return []
    count = u16(data, 0)
    pts = []
    off = 2
    for i in range(count):
        a, off = varint(data, off)
        b, off = varint(data, off)
        pts.append({"time": minute_label(i), "buy": a, "sell": b})
    return pts

def _p_sparkline(data: bytes) -> dict:
    if len(data) < 42: return {}
    base = f32(data, 36)
    count = u16(data, 40)
    prices = [f32(data, 42 + i * 4) for i in range(count)]
    return {"base_price": base, "prices": prices}

def _p_today_trade(data: bytes, code: str, start: int) -> list[Trade]:
    if len(data) < 2: return []
    count = u16(data, 0)
    ticks = []
    off = 2
    price_acc = 0
    for i in range(count):
        if off + 2 > len(data): break
        tm = u16(data, off); off += 2
        pd, off = varint(data, off)
        vol, off = varint(data, off)
        oc, off = varint(data, off)
        st, off = varint(data, off)
        tl, off = varint(data, off)
        price_acc += pd
        side = {0: "B", 1: "S", 2: "N"}.get(st, f"{st}")
        ticks.append(Trade(
            time=f"{tm // 60:02d}:{tm % 60:02d}",
            price=price_acc / 100.0, volume=vol,
            direction=side, order_count=oc,
        ))
    return ticks

def _p_history_trade(data: bytes, code: str) -> list[Trade]:
    if len(data) < 6: return []
    count = u16(data, 0)
    base = f32(data, 2)
    ticks = []
    off = 6
    price_acc = 0
    for i in range(count):
        if off + 2 > len(data): break
        tm = u16(data, off); off += 2
        pd, off = varint(data, off)
        vol, off = varint(data, off)
        oc, off = varint(data, off)
        st, off = varint(data, off)
        tl, off = varint(data, off)
        price_acc += pd
        side = {0: "B", 1: "S", 2: "N"}.get(st, f"{st}")
        ticks.append(Trade(
            time=f"{tm // 60:02d}:{tm % 60:02d}",
            price=price_acc / 100.0, volume=vol,
            direction=side, order_count=oc,
        ))
    return ticks

def _p_auction(data: bytes, code: str) -> list[dict]:
    if len(data) < 2: return []
    count = u16(data, 0)
    pts = []
    off = 2
    for i in range(count):
        if off + 16 > len(data): break
        mo = u16(data, off)
        price = f32(data, off + 2)
        mv = u32(data, off + 6)
        us = int.from_bytes(data[off + 10:off + 14], "little", signed=True)
        sec = data[off + 15]
        pts.append({
            "time": f"{mo // 60:02d}:{mo % 60:02d}:{sec:02d}",
            "price": price, "matched_volume": mv,
            "unmatched_volume": abs(us), "direction": 1 if us >= 0 else -1,
        })
        off += 16
    return pts

def _p_capital(data: bytes, code: str) -> list[EquityChange]:
    if len(data) < 11: return []
    bc = u16(data, 0)
    mid = data[2]
    cd = data[3:9].decode("ascii")
    rc = u16(data, 9)
    records = []
    off = 11
    for _ in range(rc):
        if off + 29 > len(data): break
        rec = data[off:off + 29]; off += 29
        dt = int_date(u32(rec, 8))
        cat = rec[12]
        c1r, c2r, c3r, c4r = rec[13:17], rec[17:21], rec[21:25], rec[25:29]
        c1f, c2f, c3f, c4f = f32(c1r), f32(c2r), f32(c3r), f32(c4r)
        if cat in FLOAT_CATS:
            c1, c2, c3, c4 = c1f, c2f, c3f, c4f
        else:
            c1 = decode_volume(u32(c1r)) * 10000
            c2 = decode_volume(u32(c2r)) * 10000
            c3 = decode_volume(u32(c3r)) * 10000
            c4 = decode_volume(u32(c4r)) * 10000
        eq = EquityChange(date=dt, category=CAPITAL_NAMES.get(cat, f"未知({cat})"))
        if cat == 1:  # 除权除息
            eq.bonus = c1f; eq.rights = c2f; eq.placement = c3f; eq.placement_price = c4f
        else:
            eq.float_shares = c2 if c2 > 0 else c1
            eq.total_shares = c4 if c4 > 0 else c3
        records.append(eq)
    return records

def _p_finance(data: bytes) -> list[FinanceInfo]:
    if len(data) < 2: return []
    count = u16(data, 0)
    records = []
    off = 2
    rsize = 143
    for _ in range(min(count, (len(data) - 2) // rsize)):
        if off + rsize > len(data): break
        rec = data[off:off + rsize]; off += rsize
        mid = rec[0]
        exchange = {0: "sz", 1: "sh", 2: "bj"}.get(mid, "?")
        code = rec[1:7].decode("ascii")
        info = rec[7:143]
        unpacked = struct.unpack("<fHHII30f", info)
        records.append(FinanceInfo(
            code=code, exchange=exchange,
            float_shares=unpacked[0], total_shares=unpacked[5],
            eps=unpacked[11], bvps=unpacked[35],
            revenue=unpacked[20], profit=unpacked[21], net_profit=unpacked[32],
            total_assets=unpacked[12], net_assets=unpacked[18],
            ipo_date=int_date(unpacked[4]), updated=int_date(unpacked[3]),
        ))
    return records

def _p_limit(data: bytes) -> list[PriceLimit]:
    if len(data) < 2: return []
    count = u16(data, 0)
    items = []
    off = 2
    for _ in range(count):
        if off + 13 > len(data): break
        rec = data[off:off + 13]; off += 13
        mid = rec[0]
        exchange = {0: "sz", 1: "sh", 2: "bj"}.get(mid, "?")
        cn = u32(rec, 1)
        items.append(PriceLimit(
            code=f"{cn:06d}", exchange=exchange,
            upper=f32(rec, 5), lower=f32(rec, 9),
        ))
    return items


# ============== 命令注册表 ==============

COMMANDS = {
    CMD_HANDSHAKE:     (_b_handshake,      _p_handshake),
    CMD_HEARTBEAT:     (_b_heartbeat,      _p_heartbeat),
    CMD_COUNT:         (None,               _p_count),
    CMD_LIST:          (None,               _p_list),
    CMD_SNAPSHOT:      (None,               _p_snapshot),
    CMD_REFRESH:       (None,               _p_refresh),
    CMD_CATEGORY:      (None,               _p_category),
    CMD_KLINE:         (None,               _p_kline),
    CMD_TODAY_MINUTE:  (None,               _p_today_minute),
    CMD_HISTORY_MINUTE:(None,               _p_history_minute),
    CMD_RECENT_MINUTE: (None,               _p_recent_minute),
    CMD_AUX:           (None,               _p_aux),
    CMD_SPARKLINE:     (None,               _p_sparkline),
    CMD_TODAY_TRADE:   (None,               _p_today_trade),
    CMD_HISTORY_TRADE: (None,               _p_history_trade),
    CMD_AUCTION:       (None,               _p_auction),
    CMD_CAPITAL:       (None,               _p_capital),
    CMD_FINANCE:       (None,               _p_finance),
    CMD_LIMIT:         (None,               _p_limit),
}
