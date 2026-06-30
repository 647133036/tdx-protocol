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
  列表:     0x23F5 (分页代码)
  分类:     0x23F4 (品种分类)
  详细行情: 0x23FA (单品种), 0x2400 (批量)
  分时图:   0x248B (当日), 0x248C (历史)
  采样:     0x254D (K线采样)
  表格:     0x2422 (主表), 0x2423 (详情)
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
CMD_EX_TICK_CHART = 0x248B
CMD_EX_HISTORY_TICK_CHART = 0x248C
CMD_EX_CHART_SAMPLING = 0x254D
CMD_EX_TABLE = 0x2422
CMD_EX_TABLE_DETAIL = 0x2423
CMD_EX_QUOTES = 0x248A
CMD_EX_QUOTES_SINGLE = 0x23FA
CMD_EX_LIST = 0x23F5
CMD_EX_COUNT = 0x23F0
CMD_EX_CATEGORY_LIST = 0x23F4

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
    return struct.pack("<B", mid) + code.encode("utf-8").ljust(9, b"\x00")


# ===== 构造器 =====

def _b_ex_handshake() -> bytes: return HANDSHAKE_DATA

def _b_ex_heartbeat(mid: int = 0) -> bytes: return mid.to_bytes(2, "little")

def _b_ex_markets() -> bytes: return b""

def _b_ex_codes(mid: int, start: int = 0, count: int = 200) -> bytes:
    return struct.pack("<IH", start, count)

def _b_ex_quote_batch(mid: int, start: int = 0, count: int = 200) -> bytes:
    return struct.pack("<BHHHH", mid, 0, start, count, 1)

def _b_ex_quote(mid: int, code: str) -> bytes:
    return _encode_code(mid, code)

def _b_ex_kline(mid: int, code: str, period: str = "day", start: int = 0, count: int = 800) -> bytes:
    pc = PERIOD_MAP.get(period, 4)
    return struct.pack("<B9sHHIH", mid, code.encode("utf-8").ljust(9, b"\x00"), pc, 1, start, count)

def _b_ex_kline_range(mid: int, code: str, period: str = "day",
                       start_date=None, end_date=None) -> bytes:
    sd = date_int(start_date) if start_date else 20000101
    ed = date_int(end_date) if end_date else 20991231
    return (struct.pack("<B9s", mid, code.encode("utf-8").ljust(9, b"\x00")) +
            b"\x07\x00" + struct.pack("<LL", sd, ed))

def _b_ex_minute_today(mid: int, code: str) -> bytes: return _encode_code(mid, code)

def _b_ex_minute_history(mid: int, code: str, tdate) -> bytes:
    return date_int(tdate).to_bytes(4, "little") + _encode_code(mid, code)

def _b_ex_trade_today(mid: int, code: str, start: int = 0, count: int = 100) -> bytes:
    return struct.pack("<B9siH", mid, code.encode("utf-8").ljust(9, b"\x00"), start, count)

def _b_ex_trade_history(mid: int, code: str, tdate, start: int = 0, count: int = 100) -> bytes:
    return struct.pack("<IB9siH", date_int(tdate), mid, code.encode("utf-8").ljust(9, b"\x00"), start, count)


# ===== 解析器 =====

def _p_ex_markets(data: bytes) -> list[dict]:
    if len(data) < 2: return []
    count = struct.unpack("<H", data[:2])[0]
    markets = []
    off = 2
    for _ in range(count):
        if off + 64 > len(data): break
        category, raw_name, market, raw_short_name, _, _ = struct.unpack(
            "<B32sB2s26s2s", data[off:off + 64])
        off += 64
        if category == 0 and market == 0:
            continue
        name = raw_name.decode("gbk", errors="ignore").rstrip("\x00")
        short_name = raw_short_name.decode("gbk", errors="ignore").rstrip("\x00")
        markets.append({"market_id": market, "name": name, "short_name": short_name, "category": category})
    return markets

def _p_ex_codes(data: bytes) -> list[dict]:
    if len(data) < 6: return []
    start, count = struct.unpack("<IH", data[:6])
    codes = []
    off = 6
    for _ in range(count):
        if off + 64 > len(data): break
        category, market, _, code_raw, name_raw, desc_raw = struct.unpack(
            "<BB3s9s17s9s", data[off:off + 40])
        code = code_raw.decode("gbk", errors="ignore").rstrip("\x00")
        name = name_raw.decode("gbk", errors="ignore").rstrip("\x00")
        codes.append({"market_id": market, "code": code, "name": name, "category": category})
        off += 64
    return codes

def _p_ex_quote(data: bytes, mid: int, code: str) -> Quote:
    if len(data) < 20: return Quote(code=code)
    pos = 0
    rmid, rcode_raw = struct.unpack("<B9s", data[pos:pos + 10])
    pos += 10
    rcode = rcode_raw.decode("utf-8", errors="ignore").rstrip("\x00") or code
    pos += 4  # padding
    if pos + 136 > len(data): return Quote(code=rcode)
    (
        pre_close, open_price, high, low, price,
        kaicang, _, zongliang, xianliang, _, neipan, waipan, _, chicang,
        b1, b2, b3, b4, b5, bv1, bv2, bv3, bv4, bv5,
        a1, a2, a3, a4, a5, av1, av2, av3, av4, av5,
    ) = struct.unpack("<fffffIIIIIIIIIfffffIIIIIfffffIIIII", data[pos:pos + 136])
    q = Quote(code=rcode)
    q.pre_close = pre_close
    q.open = open_price
    q.high = high
    q.low = low
    q.price = price
    q.volume = zongliang
    q.amount = xianliang
    q.open_interest = chicang
    q.inner_vol = neipan
    q.outer_vol = waipan
    q.bid_p = [b1, b2, b3, b4, b5]
    q.ask_p = [a1, a2, a3, a4, a5]
    q.bid_v = [bv1, bv2, bv3, bv4, bv5]
    q.ask_v = [av1, av2, av3, av4, av5]
    q.raw = data
    return q

def _p_ex_quote_batch(data: bytes) -> list[Quote]:
    if len(data) < 2: return []
    count = struct.unpack("<H", data[:2])[0]
    quotes = []
    pos = 2
    for _ in range(count):
        if pos + 10 > len(data): break
        market, code_raw = struct.unpack("<B9s", data[pos:pos + 10])
        code = code_raw.decode("gbk", errors="ignore").rstrip("\x00")
        pos += 10
        if pos + 140 > len(data): break
        (
            _, zuojie, jinkai, zuigao, zuidi, maichu,
            kaicang, _, zongliang, xianliang, zongjine, neipan, waipan, _, chicang,
            b1, _, _, _, _, bv1, _, _, _, _,
            a1, _, _, _, _, av1, _, _, _, _,
        ) = struct.unpack("<IfffffIIIIfIIfIfIIIIIIIIIfIIIIIIIII", data[pos:pos + 140])
        pos += 290  # skip padding to next record
        q = Quote(code=code)
        q.pre_close = zuojie
        q.open = jinkai
        q.high = zuigao
        q.low = zuidi
        q.price = maichu
        q.volume = zongliang
        q.amount = xianliang
        q.open_interest = chicang
        q.bid_p[0] = b1
        q.bid_v[0] = bv1
        q.ask_p[0] = a1
        q.ask_v[0] = av1
        q.raw = data[pos - 440:pos] if pos >= 440 else data
        quotes.append(q)
    return quotes

def _p_ex_kline(data: bytes, mid: int, code: str, period: str) -> list[Kline]:
    if len(data) < 20: return []
    pos = 18
    ret_count = u16(data, pos); pos += 2
    pc = PERIOD_MAP.get(period, 4)
    bars = []
    for _ in range(ret_count):
        if pos + 32 > len(data): break
        if pc < 4 or pc == 7 or pc == 8:
            zip_day, minutes = struct.unpack("<HH", data[pos:pos + 4])
            year = (zip_day >> 11) + 2004
            month = (zip_day % 2048) // 100
            day = (zip_day % 2048) % 100
            hour = minutes // 60
            minute = minutes % 60
        else:
            zip_day, = struct.unpack("<I", data[pos:pos + 4])
            year = zip_day // 10000
            month = (zip_day % 10000) // 100
            day = zip_day % 100
            hour = 15
            minute = 0
        open_p, high, low, close, position, trade, price = struct.unpack(
            "<ffffIIf", data[pos + 4:pos + 32])
        pos += 32
        bars.append(Kline(
            time=f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}",
            open=open_p, high=high, low=low, close=close,
            volume=trade, amount=price, position=position, settlement=price,
        ))
    return bars

def _parse_md_date(num: int):
    month = (num % 2048) // 100
    year = num // 2048 + 2004
    day = (num % 2048) % 100
    return year, month, day

def _parse_md_time(num: int):
    return num // 60, num % 60

def _p_ex_kline_range(data: bytes, mid: int, code: str, period: str) -> list[Kline]:
    if len(data) < 14: return []
    pos = 12
    ret_count = u16(data, pos); pos += 2
    bars = []
    for _ in range(ret_count):
        if pos + 32 > len(data): break
        d1, d2, open_p, high, low, close, position, trade, settlementprice = struct.unpack(
            "<HHffffIIf", data[pos:pos + 32])
        pos += 32
        year, month, day = _parse_md_date(d1)
        hour, minute = _parse_md_time(d2)
        bars.append(Kline(
            time=f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}",
            open=open_p, high=high, low=low, close=close,
            volume=trade, amount=settlementprice, position=position, settlement=settlementprice,
        ))
    return bars

def _p_ex_minute(data: bytes, mid: int, code: str) -> list[Minute]:
    if len(data) < 12: return []
    rmid, rcode_raw, num = struct.unpack("<B9sH", data[:12])
    rcode = rcode_raw.decode("utf-8", errors="ignore").rstrip("\x00") or code
    pos = 12
    pts = []
    for _ in range(num):
        if pos + 18 > len(data): break
        raw_time, price, avg_price, volume, open_interest = struct.unpack(
            "<HffII", data[pos:pos + 18])
        pos += 18
        hour = raw_time // 60
        minute = raw_time % 60
        pts.append(Minute(
            time=f"{hour:02d}:{minute:02d}",
            price=price, avg_price=avg_price,
            volume=volume, open_interest=open_interest,
        ))
    return pts

def _p_ex_minute_history(data: bytes, mid: int, code: str) -> list[Minute]:
    if len(data) < 20: return []
    rmid, rcode_raw, _, num = struct.unpack("<B9s8sH", data[:20])
    rcode = rcode_raw.decode("utf-8", errors="ignore").rstrip("\x00") or code
    pos = 20
    pts = []
    for _ in range(num):
        if pos + 18 > len(data): break
        raw_time, price, avg_price, volume, open_interest = struct.unpack(
            "<HffII", data[pos:pos + 18])
        pos += 18
        hour = raw_time // 60
        minute = raw_time % 60
        pts.append(Minute(
            time=f"{hour:02d}:{minute:02d}",
            price=price, avg_price=avg_price,
            volume=volume, open_interest=open_interest,
        ))
    return pts

def _p_ex_trade(data: bytes, mid: int, code: str) -> list[Trade]:
    if len(data) < 16: return []
    rmid, rcode_raw, _, num = struct.unpack("<B9s4sH", data[:16])
    rcode = rcode_raw.decode("utf-8", errors="ignore").rstrip("\x00") or code
    pos = 16
    ticks = []
    for _ in range(num):
        if pos + 16 > len(data): break
        raw_time, price, volume, zengcang, direction = struct.unpack(
            "<HIIiH", data[pos:pos + 16])
        pos += 16
        hour = raw_time // 60
        minute = raw_time % 60
        second = direction % 10000
        value = direction // 10000
        if value == 0:
            dflag = 1
            if zengcang > 0:
                nature = "多开" if volume > zengcang else ("双开" if volume == zengcang else "")
            elif zengcang == 0:
                nature = "多换"
            else:
                nature = "双平" if volume == -zengcang else "空平"
        elif value == 1:
            dflag = -1
            if zengcang > 0:
                nature = "空开" if volume > zengcang else ("双开" if volume == zengcang else "")
            elif zengcang == 0:
                nature = "空换"
            else:
                nature = "双平" if volume == -zengcang else "多平"
        else:
            dflag = 0
            if zengcang > 0:
                nature = "开仓" if volume > zengcang else ("双开" if volume == zengcang else "")
            elif zengcang < 0:
                nature = "平仓" if volume > -zengcang else ("双平" if volume == -zengcang else "")
            else:
                nature = "换手"
        ticks.append(Trade(
            time=f"{hour:02d}:{minute:02d}:{min(second, 59):02d}",
            price=price, volume=volume, direction=str(dflag), nature=nature,
        ))
    return ticks


# ===== 新增命令构造器 =====

def _b_ex_tick_chart(mid: int, code: str) -> bytes:
    """当日分时图."""
    return struct.pack("<B23s8x", mid, code.encode("gbk"))

def _b_ex_history_tick_chart(mid: int, code: str, tdate) -> bytes:
    """历史分时图."""
    td = date_int(tdate) if isinstance(tdate, (date, datetime)) else tdate
    return struct.pack("<IB23s6sH", td, mid, code.encode("gbk"), b"", 0)

def _b_ex_chart_sampling(mid: int, code: str) -> bytes:
    """K线采样."""
    return struct.pack("<H22sHH9x", mid, code.encode("gbk"), 1, 20)

def _b_ex_table(start: int = 0, mode: int = 1) -> bytes:
    """表格数据."""
    return struct.pack("<II16s85xB16x", start, 0,
                       bytes.fromhex("00781f0e6a37447b502b7c0d01404c0a"), mode)

def _b_ex_quotes(code_list: list[tuple[int, str]]) -> bytes:
    """批量行情 (多品种)."""
    length = len(code_list)
    if length <= 0:
        raise ValueError("futures count must > 0")
    body = bytearray(struct.pack("<B7xH", 5, length))
    for market, code in code_list:
        body.extend(struct.pack("<B23s", market, code.encode("gbk")))
    return bytes(body)

def _b_ex_quotes_single(mid: int, code: str) -> bytes:
    """单品种详细行情."""
    return struct.pack("<B9s", mid, code.encode("gbk"))


# ===== 新增命令解析器 =====

def _p_ex_tick_chart(data: bytes) -> list[dict]:
    """当日分时图解析."""
    if len(data) < 34: return []
    market, code_raw, count = struct.unpack("<B31sH", data[:34])
    code = code_raw.rstrip(b"\x00").decode("gbk", errors="ignore")
    from datetime import time as dt_time
    charts = []
    pos = 34
    for _ in range(count):
        if pos + 18 > len(data): break
        minutes, price, avg, vol, _ = struct.unpack("<HffII", data[pos:pos + 18])
        pos += 18
        charts.append({
            "market": market,
            "code": code,
            "time": dt_time(minutes // 60 % 24, minutes % 60),
            "price": price,
            "avg": avg,
            "vol": vol,
        })
    return charts

def _p_ex_history_tick_chart(data: bytes) -> list[dict]:
    """历史分时图解析."""
    if len(data) < 42: return []
    market, code_raw, date_val, avg_price, _, _, count = struct.unpack(
        "<B23sIfIIH", data[:42])
    code = code_raw.rstrip(b"\x00").decode("gbk", errors="ignore")
    from datetime import time as dt_time
    charts = []
    pos = 42
    for _ in range(count):
        if pos + 18 > len(data): break
        minutes, price, avg, vol, _ = struct.unpack("<HffII", data[pos:pos + 18])
        pos += 18
        charts.append({
            "market": market,
            "code": code,
            "date": date_val,
            "time": dt_time(minutes // 60 % 24, minutes % 60),
            "price": price,
            "avg": avg,
            "vol": vol,
        })
    return charts

def _p_ex_chart_sampling(data: bytes) -> list[float]:
    """K线采样解析."""
    if len(data) < 42: return []
    market, code_raw, a, b, c, d, e, f, g, h, count = struct.unpack(
        "<H22s9H", data[:42])
    code = code_raw.rstrip(b"\x00").decode("gbk", errors="ignore")
    prices = []
    for i in range(count):
        if 42 + 4 * i + 4 <= len(data):
            p, = struct.unpack("<f", data[42 + 4 * i: 42 + 4 * i + 4])
            prices.append(p)
    return prices

def _p_ex_table(data: bytes) -> tuple[int, int, str]:
    """表格数据解析. 返回 (start, count, context)."""
    if len(data) < 169: return (0, 0, "")
    category, flag, tail_byte = struct.unpack("<HBB", data[32:36])
    start, = struct.unpack("<I", data[36:40])
    flag2, = struct.unpack("<B", data[116:117])
    count, ctx_len = struct.unpack("<II", data[161:169])
    ctx = data[169:169 + ctx_len].decode("gbk", errors="ignore").replace("\x00", "") if ctx_len > 0 else ""
    return start, count, ctx

def _p_ex_quotes(data: bytes) -> list[dict]:
    """批量行情解析."""
    if len(data) < 10: return []
    u, _, count = struct.unpack("<IIH", data[:10])
    results = []
    for i in range(count):
        rec_start = 10 + 314 * i
        rec_end = rec_start + 314
        if rec_end > len(data): break
        rec = data[rec_start:rec_end]
        if len(rec) < 314: break
        market, code_raw = struct.unpack("<B23s", rec[:24])
        code = code_raw.rstrip(b"\x00").decode("gbk", errors="ignore")
        pos = 24
        if pos + 24 > len(rec): break
        active, pre_close, open_p, high, low, close = struct.unpack(
            "<I5f", rec[pos:pos + 24])
        pos += 24
        if pos + 20 > len(rec): break
        open_pos, add_pos, vol, curr_vol, amount = struct.unpack(
            "<4If", rec[pos:pos + 20])
        pos += 20
        if pos + 16 > len(rec): break
        in_vol, out_vol, u14, hold_pos = struct.unpack(
            "<4I", rec[pos:pos + 16])
        pos += 16
        if pos + 40 > len(rec): break
        b1, b2, b3, b4, b5, bv1, bv2, bv3, bv4, bv5 = struct.unpack(
            "<5f5I", rec[pos:pos + 40])
        pos += 40
        if pos + 40 > len(rec): break
        a1, a2, a3, a4, a5, av1, av2, av3, av4, av5 = struct.unpack(
            "<5f5I", rec[pos:pos + 40])
        pos += 40
        if pos + 18 > len(rec): break
        settlement, u2, avg, pre_settlement, date_raw = struct.unpack(
            "<HfIff", rec[pos:pos + 18])
        pos += 18
        from datetime import date as dt_date
        date_int_val = int(date_raw)
        if date_int_val // 10000 == 0:
            date_obj = dt_date(1900, 1, 1)
        else:
            date_obj = dt_date(date_int_val // 10000, date_int_val % 10000 // 100, date_int_val % 100)
        results.append({
            "market": market,
            "code": code,
            "active": active,
            "pre_close": pre_close,
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "open_position": open_pos,
            "add_position": add_pos,
            "vol": vol,
            "curr_vol": curr_vol,
            "amount": amount,
            "in_vol": in_vol,
            "out_vol": out_vol,
            "hold_position": hold_pos,
            "bid_p": [b1, b2, b3, b4, b5],
            "bid_v": [bv1, bv2, bv3, bv4, bv5],
            "ask_p": [a1, a2, a3, a4, a5],
            "ask_v": [av1, av2, av3, av4, av5],
            "settlement": settlement,
            "avg": avg,
            "pre_settlement": pre_settlement,
            "date": date_obj,
        })
    return results
