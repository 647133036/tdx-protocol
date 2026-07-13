"""编解码工具 — 对齐 pytdx/tdxpy helper.py."""

import struct
from typing import Tuple

def u32(data: bytes, off: int = 0) -> int:
    return struct.unpack_from("<I", data, off)[0]

def u16(data: bytes, off: int = 0) -> int:
    return struct.unpack_from("<H", data, off)[0]

def f32(data: bytes, off: int = 0) -> float:
    return struct.unpack_from("<f", data, off)[0]

def split_code(code: str) -> Tuple[int, str, str]:
    """解析股票代码为 (market_int, exchange_str, numeric_code)."""
    code = code.strip().lower()
    if code.startswith(("sz", "sh", "bj")):
        exchange = code[:2]
        num = code[2:]
    else:
        num = code[:6]
        if num.startswith(("60", "68", "69")):
            exchange = "sh"
        elif num.startswith(("8", "4")):
            exchange = "bj"
        elif num.startswith(("00", "30", "15", "16", "39")):
            exchange = "sz"
        elif num.startswith(("5", "9")):
            exchange = "sh"
        elif num.startswith(("1", "2")):
            exchange = "sz"
        else:
            exchange = "sz"
    mid = {"sz": 0, "sh": 1, "bj": 2}.get(exchange, 0)
    return mid, exchange, num

def date_int(d) -> int:
    if hasattr(d, 'strftime'):
        return int(d.strftime("%Y%m%d"))
    return int(d)

def int_date(val: int) -> str:
    s = str(val)
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s

def minute_label(minutes: int) -> str:
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"

def recent_selector(tdate=None) -> int:
    """获取最近交易日整数."""
    if tdate:
        return date_int(tdate)
    from datetime import datetime
    return int(datetime.now().strftime("%Y%m%d"))

# ============================================================
# 变长价格解码 — 对齐 pytdx helper.get_price
# ============================================================

def _index_bytes(data: bytes, pos: int) -> int:
    return data[pos]

def get_price(data: bytes, pos: int = 0) -> Tuple[int, int]:
    """
    变长价格解码，类似 UTF-8 编码的有符号数字。
    返回 (价格增量_分, 下一个偏移).
    对齐 pytdx helper.get_price.
    """
    pos_byte = 6
    bdata = _index_bytes(data, pos)
    int_data = bdata & 0x3F
    if bdata & 0x40:
        sign = True
    else:
        sign = False
    if bdata & 0x80:
        while True:
            pos += 1
            bdata = _index_bytes(data, pos)
            int_data += (bdata & 0x7F) << pos_byte
            pos_byte += 7
            if bdata & 0x80:
                pass
            else:
                break
    pos += 1
    if sign:
        int_data = -int_data
    return int_data, pos

# ============================================================
# 成交量解码 — 对齐 pytdx helper.get_volume
# ============================================================

def decode_volume(vol: int) -> float:
    """
    变长成交量解码，IEEE-754 风格。
    对齐 pytdx helper.get_volume.
    """
    logpoint = vol >> (8 * 3)
    hleax = (vol >> (8 * 2)) & 0xFF
    lheax = (vol >> 8) & 0xFF
    lleax = vol & 0xFF
    dw_ecx = logpoint * 2 - 0x7F
    dw_edx = logpoint * 2 - 0x86
    dw_esi = logpoint * 2 - 0x8E
    dw_eax = logpoint * 2 - 0x96
    if dw_ecx < 0:
        tmp_eax = -dw_ecx
    else:
        tmp_eax = dw_ecx
    dbl_xmm6 = 2.0 ** tmp_eax
    if dw_ecx < 0:
        dbl_xmm6 = 1.0 / dbl_xmm6
    if hleax > 0x80:
        dwtmpeax = dw_edx + 1
        tmpdbl_xmm3 = 2.0 ** dwtmpeax
        dbl_xmm0 = (2.0 ** dw_edx) * 128.0
        dbl_xmm0 += (hleax & 0x7F) * tmpdbl_xmm3
        dbl_xmm4 = dbl_xmm0
    else:
        dbl_xmm0 = (2.0 ** dw_edx) * hleax
        dbl_xmm4 = dbl_xmm0
    dbl_xmm3 = (2.0 ** dw_esi) * lheax
    dbl_xmm1 = (2.0 ** dw_eax) * lleax
    if hleax & 0x80:
        dbl_xmm3 *= 2.0
        dbl_xmm1 *= 2.0
    dbl_ret = dbl_xmm6 + dbl_xmm4 + dbl_xmm3 + dbl_xmm1
    return dbl_ret

def cut_int(data: bytes, off: int) -> Tuple[int, int]:
    """截断整数 — 与 get_price 相同实现."""
    val, off = get_price(data, off)
    return val, off

def get_volume(vol_raw: int) -> float:
    """快捷调用."""
    return decode_volume(vol_raw)

def get_volume2(vol_raw: int) -> float:
    """同 get_volume."""
    return decode_volume(vol_raw)

# ============================================================
# 时间编码
# ============================================================

def encode_date(year: int, month: int, day: int) -> int:
    """编码日期为 YYYYMMDD."""
    return year * 10000 + month * 100 + day

def encode_minute(hour: int, minute: int) -> int:
    """编码时间为距午夜分钟数."""
    return hour * 60 + minute

# ============================================================
# 代码分类与标准化
# ============================================================

def classify(code: str) -> tuple:
    """分类股票代码: (market_int, exchange_str, numeric_code)."""
    return split_code(code)

def normalize_code(code: str) -> str:
    """标准化股票代码为 sz000001 / sh600001 格式."""
    mid, exchange, num = split_code(code)
    return f"{exchange}{num}"

