"""二进制编解码工具箱。

核心创新:
  - varint 增量价格编码 (delta-of-delta)
  - 通达信特殊成交量解码 (log+mantissa 浮点)
  - 市场/代码标准化与分类识别
  - 日期与时间索引的双向转换
"""

import math
import struct
from datetime import date, datetime, timedelta, timezone
from typing import Optional

SH_TZ = timezone(timedelta(hours=8))

MARKETS = {"sz": 0, "sh": 1, "bj": 2}
MARKETS_REV = {0: "sz", 1: "sh", 2: "bj"}


# ---- 整数 / 浮点读取 ----

def u16(b: bytes, off: int = 0) -> int:
    return int.from_bytes(b[off:off + 2], "little")

def u32(b: bytes, off: int = 0) -> int:
    return int.from_bytes(b[off:off + 4], "little")

def f32(b: bytes, off: int = 0) -> float:
    return struct.unpack_from("<f", b, off)[0]


# ---- varint (增量价格编码) ----

def varint(b: bytes, off: int) -> tuple[int, int]:
    """通达信 varint: 首字节低6位 + 后续字节低7位, bit6=符号位, bit7=延续位。"""
    val, pos, shift = 0, off, 0
    while True:
        byte = b[pos]
        if pos == off:
            val += byte & 0x3F; shift = 6
        else:
            val += (byte & 0x7F) << shift; shift += 7
        pos += 1
        if byte & 0x80 == 0:
            break
    if b[off] & 0x40:
        val = -val
    return val, pos


# ---- 成交量解码 (TDX 专利浮点格式) ----

def decode_volume(v: int) -> float:
    """log-point 浮点成交量解码。"""
    if v == 0:
        return 0.0
    s = int.from_bytes(v.to_bytes(4, "big"), "big", signed=True)
    lp = s >> 24
    ha = (s >> 16) & 0xFF
    la = (s >> 8) & 0xFF
    ll = s & 0xFF
    base = 2.0 ** (lp * 2 - 0x7F)
    hi = base * (64.0 + (ha & 0x7F)) / 64.0 if ha > 0x80 else base * ha / 128.0
    sc = 2.0 if ha & 0x80 else 1.0
    return base + hi + base * la / 32768.0 * sc + base * ll / 8388608.0 * sc


# ---- 代码标准化 ----

def normalize_code(s: str) -> str:
    s = s.strip().lower()
    # 完整股票代码: sz000001
    if len(s) == 8 and s[:2] in MARKETS and s[2:].isdigit():
        return s
    # 6位纯数字: 根据首位推断市场
    if len(s) == 6 and s.isdigit():
        if s[0] in "69": return "sh" + s
        if s[0] in "0123": return "sz" + s
        if s.startswith(("8", "92")): return "bj" + s
    # 期货/ETF代码: IF2506, rb2501, 510050 等 (非纯数字 或 带字母的品种代码)
    if s and s.isascii():
        return s
    raise ValueError(f"invalid code: {s!r}")


def split_code(s: str) -> tuple[int, str, str]:
    """返回 (market_id, exchange, number)。"""
    code = normalize_code(s)
    # 股票格式: sz000001
    if len(code) >= 8 and code[:2] in MARKETS and code[2:].isdigit():
        return MARKETS[code[:2]], code[:2], code[2:]
    # 期货格式: IF2506 (保留原样)
    return 47, "futures", code.upper()


def code_wire(code: str) -> bytes:
    """股票代码编码: [market_id, 0x00, number_ascii]。"""
    mid, _, num = split_code(code)
    return bytes([mid, 0]) + num.encode("ascii")


# ---- 日期编解码 ----

def date_int(v: str | int | date | datetime | None = None) -> int:
    if v is None: return int(date.today().strftime("%Y%m%d"))
    if isinstance(v, datetime): return int(v.date().strftime("%Y%m%d"))
    if isinstance(v, date): return int(v.strftime("%Y%m%d"))
    if isinstance(v, int): return v
    return int(str(v).replace("-", ""))


def int_date(raw: int) -> Optional[date]:
    try: return datetime.strptime(f"{raw:08d}", "%Y%m%d").date()
    except ValueError: return None


RECENT_BASE = 0xFED62304


def recent_selector(d: date) -> int:
    return RECENT_BASE - d.toordinal()


# ---- 分钟索引 <-> 时间标签 ----

def minute_label(idx: int) -> str:
    m = 9 * 60 + 30 + idx + 1 if idx < 120 else 13 * 60 + idx - 119
    return f"{m // 60:02d}:{m % 60:02d}"


def minute_dt(td: date, idx: int) -> datetime:
    lb = minute_label(idx)
    return datetime(td.year, td.month, td.day, int(lb[:2]), int(lb[3:]), tzinfo=SH_TZ)


# ---- 品种分类 ----

def classify(code: str) -> str:
    c = normalize_code(code)
    # 股票格式: xxNNNNNN
    if len(c) == 8 and c[:2] in MARKETS and c[2:].isdigit():
        if c.startswith("sh000") or c.startswith("sz399"):
            return "index"
        num = c[2:]
        if c.startswith("sh51") or c.startswith("sz159") or c.startswith("sz16"):
            return "etf"
        return "stock"
    # 其他均为品种代码 (期货等)
    return "futures"
