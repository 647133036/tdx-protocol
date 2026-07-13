"""7709 股票行情 — 全部命令的构造器与解析器。

对齐 pytdx/tdxpy (雨老) 协议:
  - 握手: SetupCmd1 → SetupCmd2 → SetupCmd3
  - 响应头: 16 字节 <IIIHH (type, counter1, counter2, zip_len, unzip_len)
  - 价格: 变长编码 (get_price, 类似 UTF-8)
  - 成交量: IEEE-754 风格编码 (get_volume)
"""

import struct
from datetime import date, datetime, time as dt_time
from typing import Optional, Sequence

from ..codec import (
    f32, u32, decode_volume,
    split_code, date_int, int_date, minute_label, recent_selector,
    get_price, cut_int, get_volume, get_volume2,
)
from ..models import (
    Quote, Kline, Minute, Trade,
    EquityChange, FinanceInfo, PriceLimit,
)

# MARKET enum for incremental refresh
class MARKET:
    SZ = 0
    SH = 1
    BJ = 2

# ============== 常量 ==============

CMD_SETUP1 = 0x1893
CMD_SETUP2 = 0x1894
CMD_SETUP3 = 0x1899
CMD_COUNT = 0x044E
CMD_LIST = 0x0450
CMD_SNAPSHOT = 0x053E
CMD_KLINE = 0x052D
CMD_TODAY_MINUTE = 0x051D
CMD_HISTORY_MINUTE = 0x0FB4
CMD_TODAY_TRADE = 0x0FC5
CMD_HISTORY_TRADE = 0x0FB5
CMD_XDXR = 0x0530
CMD_FINANCE = 0x0531
CMD_COMPANY_INFO_CAT = 0x02CF
CMD_COMPANY_INFO_CONTENT = 0x02D0
CMD_BLOCK_INFO_META = 0x06C5
CMD_BLOCK_INFO = 0x06B9
CMD_REPORT_FILE = 0x04B9
CMD_VOL_PROFILE = 0x051A
CMD_AUX = 0x051B
CMD_INDEX_MOMENTUM = 0x051C
CMD_INDEX_INFO = 0x051D
CMD_AUCTION = 0x056A
CMD_TICK_CHART = 0x0537
CMD_QUOTES_DETAIL = 0x053E
CMD_TOP_BOARD = 0x053F
CMD_QUOTES_LIST = 0x054B
CMD_UNUSUAL = 0x0563
CMD_CHART_SAMPLING = 0xFD1
CMD_HISTORY_ORDERS = 0x0FB4
CMD_QUOTES_ENCRYPT = 0x0547  # 增量刷新
CMD_RECENT_MINUTE = 0x0FEB  # 近期分时(历史tick)
CMD_LIMITS = 0x0452  # 涨跌停限制

PREFIX = 0x0C
CTRL = 0x01

from ..hosts import STOCK_HOSTS_FAST as STOCK_HOSTS

XDXR_CATEGORY_MAPPING = {
    1: "除权除息", 2: "送配股上市", 3: "非流通股上市",
    4: "未知股本变动", 5: "股本变化", 6: "增发新股",
    7: "股份回购", 8: "增发新股上市", 9: "转配股上市",
    10: "可转债上市", 11: "扩缩股", 12: "非流通股缩股",
    13: "送认购权证", 14: "送认沽权证",
}

# ============== 握手命令 ==============

def setup_cmd1() -> bytes:
    return bytes.fromhex("0c 02 18 93 00 01 03 00 03 00 0d 00 01")

def setup_cmd2() -> bytes:
    return bytes.fromhex("0c 02 18 94 00 01 03 00 03 00 0d 00 02")

def setup_cmd3() -> bytes:
    return bytes.fromhex(
        "0c 03 18 99 00 01 20 00 20 00 db 0f d5 d0"
        "c9 cc d6 a4 a8 af 00 00 00 8f c2 25 40 13"
        "00 00 d5 00 c9 cc bd f0 d7 ea 00 00 00 02"
    )

# ============== 构造器 (builders) ==============

def _b_count(market: int) -> bytes:
    """market: 0=深圳, 1=上海."""
    pkg = bytearray.fromhex("0c 0c 18 6c 00 01 08 00 08 00 4e 04")
    pkg.extend(struct.pack("<H", market))
    pkg.extend(b"\x75\xc7\x33\x01")
    return bytes(pkg)

def _b_list(market: int, start: int = 0) -> bytes:
    """获取证券列表一页."""
    pkg = bytearray.fromhex("0c 01 18 64 01 01 06 00 06 00 50 04")
    pkg.extend(struct.pack("<HH", market, start))
    return bytes(pkg)

def _b_snapshot(market: int, code: str) -> bytes:
    """获取单个证券实时行情."""
    if isinstance(code, str):
        code = code.encode("gbk")
    pkgdatalen = 19
    val = (0x10C, 0x02006320, pkgdatalen, pkgdatalen, 0x5053E, 0, 0, 1)
    pkg = bytearray(struct.pack("<HIHHIIHH", *val))
    pkg.extend(struct.pack("<B6s", market, code))
    return bytes(pkg)

def _b_kline(market: int, code: str, category: int, start: int, count: int) -> bytes:
    """
    获取K线.
    category: 0=5min, 1=15min, 2=30min, 3=1hour, 4=daily, 5=weekly, 6=monthly,
              7=1min, 8=1min, 9=daily, 10=quarterly, 11=yearly
    """
    if isinstance(code, str):
        code = code.encode("gbk")
    values = (
        0x10C, 0x01016408, 0x1C, 0x1C, 0x052D,
        market, code, category, 1, start, count, 0, 0, 0,
    )
    return struct.pack("<HIHHHH6sHHHHIIH", *values)

def _b_today_minute(market: int, code: str) -> bytes:
    """今日分时."""
    if isinstance(code, str):
        code = code.encode("gbk")
    pkg = bytearray.fromhex("0c 1b 08 00 01 01 0e 00 0e 00 1d 05")
    pkg.extend(struct.pack("<H6sI", market, code, 0))
    return bytes(pkg)

def _b_history_minute(market: int, code: str, tdate: int) -> bytes:
    """历史分时."""
    if isinstance(code, str):
        code = code.encode("gbk")
    if isinstance(tdate, str) or isinstance(tdate, bytes):
        tdate = int(tdate)
    pkg = bytearray.fromhex("0c 01 30 00 01 01 0d 00 0d 00 b4 0f")
    pkg.extend(struct.pack("<IB6s", tdate, market, code))
    return bytes(pkg)

def _b_today_trade(market: int, code: str, start: int, count: int) -> bytes:
    """今日分笔."""
    if isinstance(code, str):
        code = code.encode("gbk")
    pkg = bytearray.fromhex("0c 17 08 01 01 01 0e 00 0e 00 c5 0f")
    pkg.extend(struct.pack("<H6sHH", market, code, start, count))
    return bytes(pkg)

def _b_history_trade(market: int, code: str, start: int, count: int, tdate: int) -> bytes:
    """历史分笔."""
    if isinstance(code, str):
        code = code.encode("gbk")
    pkg = bytearray.fromhex("0c 01 30 01 00 01 12 00 12 00 b5 0f")
    pkg.extend(struct.pack("<IH6sHH", tdate, market, code, start, count))
    return bytes(pkg)

def _b_xdxr(market: int, code: str) -> bytes:
    """除权除息信息."""
    if isinstance(code, str):
        code = code.encode("gbk")
    pkg = bytearray.fromhex("0c 1f 18 76 00 01 0b 00 0b 00 0f 00 01 00")
    pkg.extend(struct.pack("<B6s", market, code))
    return bytes(pkg)

def _b_finance(market: int, code: str) -> bytes:
    """财务信息."""
    if isinstance(code, str):
        code = code.encode("gbk")
    pkg = bytearray.fromhex("0c 1f 18 76 00 01 0b 00 0b 00 10 00 01 00")
    pkg.extend(struct.pack("<B6s", market, code))
    return bytes(pkg)

def _b_company_info_cat(market: int, code: str) -> bytes:
    """公司信息类别."""
    if isinstance(code, str):
        code = code.encode("gbk")
    pkg = bytearray.fromhex("0c 0f 10 9b 00 01 0e 00 0e 00 cf 02")
    pkg.extend(struct.pack("<H6sI", market, code, 0))
    return bytes(pkg)

def _b_company_info_content(market: int, code: str, filename: str, start: int, length: int) -> bytes:
    """公司信息内容."""
    if isinstance(code, str):
        code = code.encode("gbk")
    if isinstance(filename, str):
        filename = filename.encode("utf-8")
    if len(filename) < 80:
        filename = filename.ljust(80, b"\x00")
    pkg = bytearray.fromhex("0c 07 10 9c 00 01 68 00 68 00 d0 02")
    pkg.extend(struct.pack("<H6sH80sIII", market, code, 0, filename, start, length, 0))
    return bytes(pkg)

def _b_block_info_meta(block_file: str) -> bytes:
    """板块元信息."""
    if isinstance(block_file, str):
        block_file = block_file.encode("utf-8")
    pkg = bytearray.fromhex("0C 39 18 69 00 01 2A 00 2A 00 C5 02")
    pkg.extend(struct.pack(f"<{0x2A - 2}s", block_file))
    return bytes(pkg)

def _b_block_info(block_file: str, start: int, size: int) -> bytes:
    """板块内容."""
    if isinstance(block_file, str):
        block_file = block_file.encode("utf-8")
    pkg = bytearray.fromhex("0c 37 18 6a 00 01 6e 00 6e 00 b9 06")
    pkg.extend(struct.pack(f"<II{0x6E - 10}s", start, size, block_file))
    return bytes(pkg)

def _b_report_file(filename: str, offset: int = 0) -> bytes:
    """下载财务报表文件."""
    node_size = 0x7530
    raw_data = struct.pack(r"<H2I100s", 0x06B9, offset, node_size, filename.encode("utf-8"))
    raw_data_len = struct.calcsize(r"<H2I100s")
    pkg = bytearray.fromhex("0C 12 34 00 00 00")
    pkg.extend(struct.pack(f"<HH{raw_data_len}s", raw_data_len, raw_data_len, raw_data))
    return bytes(pkg)

# ============== 新增命令构造器 ==============

def _b_quotes_encrypt(stocks: list[tuple[int, str]]) -> bytes:
    """增量刷新 (0x0547). 传入 [(market, code), ...]."""
    count = len(stocks)
    if count <= 0:
        raise ValueError('stocks count must > 0')
    pkg = bytearray(struct.pack("<H", count))
    for market, code in stocks:
        if isinstance(code, str):
            code = code.encode("gbk")
        pkg.extend(struct.pack("<B6sHH", market, code, 22234, 2))
    return bytes(pkg)

def _b_recent_minute(market: int, code: str, tdate: int) -> bytes:
    """近期分时 / 历史tick (0x0FEB)."""
    if isinstance(code, str):
        code = code.encode("gbk")
    date_neg = -(tdate // 10000 * 10000 + (tdate // 100) % 100 * 100 + tdate % 100)
    return struct.pack("<iB6s", date_neg, market, code)

def _b_limits(start: int = 0, count: int = 2000) -> bytes:
    """涨跌停限制 (0x0452)."""
    return struct.pack("<IIIH", start, count, 1, 0)

def _b_chart_sampling_sparkline(market: int, code: str) -> bytes:
    """小走势图 (0xFD1)."""
    if isinstance(code, str):
        code = code.encode("gbk")
    cmd = 0xFD1
    payload = bytearray(struct.pack("<H6s", market, code))
    payload.extend(bytes.fromhex("0000000000000000000000000000000001001400000000010000000000"))
    pkgdatalen = len(payload)
    val = (0x10C, 0x02006320, pkgdatalen, pkgdatalen, cmd, 0, 0, 1)
    pkg = bytearray(struct.pack("<HIHHIIHH", *val))
    pkg.extend(payload)
    return bytes(pkg)


def _b_history_orders(market: int, code: str) -> bytes:
    """历史委托 (0xFB4)."""
    if isinstance(code, str):
        code = code.encode("gbk")
    cmd = 0xFB4
    payload = bytearray(struct.pack("<H6s", market, code))
    pkgdatalen = len(payload)
    val = (0x10C, 0x02006320, pkgdatalen, pkgdatalen, cmd, 0, 0, 1)
    pkg = bytearray(struct.pack("<HIHHIIHH", *val))
    pkg.extend(payload)
    return bytes(pkg)

def _b_vol_profile(market: int, code: str) -> bytes:
    """分时成交量分布 (Volume Profile)."""
    if isinstance(code, str):
        code = code.encode("gbk")
    cmd = 0x051A
    # Payload: <H 8x <H 1x6s = 2+8+2+7 = 19B
    pkgdatalen = 19
    val = (0x10C, 0x02006320, pkgdatalen, pkgdatalen, cmd, 0, 0, 1)
    pkg = bytearray(struct.pack("<HIHHIIHH", *val))
    pkg.extend(struct.pack("<B6s", market, code))
    return bytes(pkg)

def _b_index_momentum(market: int, code: str) -> bytes:
    """指数动能."""
    if isinstance(code, str):
        code = code.encode("gbk")
    cmd = 0x051C
    pkgdatalen = 19
    val = (0x10C, 0x02006320, pkgdatalen, pkgdatalen, cmd, 0, 0, 1)
    pkg = bytearray(struct.pack("<HIHHIIHH", *val))
    pkg.extend(struct.pack("<B6s", market, code))
    return bytes(pkg)

def _b_aux(market: int, code: str) -> bytes:
    """分时副图."""
    if isinstance(code, str):
        code = code.encode("gbk")
    cmd = 0x051B
    pkgdatalen = 19
    val = (0x10C, 0x02006320, pkgdatalen, pkgdatalen, cmd, 0, 0, 1)
    pkg = bytearray(struct.pack("<HIHHIIHH", *val))
    pkg.extend(struct.pack("<B6s", market, code))
    return bytes(pkg)

def _b_index_info(market: int, code: str) -> bytes:
    """指数成分股/行情."""
    if isinstance(code, str):
        code = code.encode("gbk")
    cmd = 0x051D
    # Payload: <H 8x <H 1x6s I = 2+8+2+7+4 = 23B
    pkgdatalen = 23
    val = (0x10C, 0x02006320, pkgdatalen, pkgdatalen, cmd, 0, 0, 1)
    pkg = bytearray(struct.pack("<HIHHIIHH", *val))
    pkg.extend(struct.pack("<B6sI", market, code, 0))
    return bytes(pkg)

def _b_quotes_detail(stock_list: list) -> bytes:
    """详细行情 (5档买卖盘)."""
    count = len(stock_list)
    # Payload: <HH 5 count <B6s * count
    payload = bytearray(struct.pack("<HH", 5, count))
    for market, code in stock_list:
        if isinstance(code, str):
            code = code.encode("gbk")
        payload.extend(struct.pack("<B6s", market, code))
    pkgdatalen = len(payload)
    val = (0x10C, 0x02006320, pkgdatalen, pkgdatalen, 0x053E, 0, 0, 0)
    pkg = bytearray(struct.pack("<HIHHIIHH", *val))
    pkg.extend(payload)
    return bytes(pkg)

def _b_tick_chart(market: int, code: str, start: int = 0, count: int = 0xBA00) -> bytes:
    """分时明细."""
    if isinstance(code, str):
        code = code.encode("gbk")
    cmd = 0x0537
    # Payload: <H 6s H H = 2+6+2+2 = 12B
    pkgdatalen = 12
    val = (0x10C, 0x02006320, pkgdatalen, pkgdatalen, cmd, market, 0, 0)
    pkg = bytearray(struct.pack("<HIHHIIHH", *val))
    pkg.extend(code.ljust(6, b"\x00"))
    pkg.extend(struct.pack("<HH", start, count))
    return bytes(pkg)

def _b_auction(market: int, code: str, start: int = 0, count: int = 500, mode: int = 3) -> bytes:
    """集合竞价."""
    if isinstance(code, str):
        code = code.encode("gbk")
    cmd = 0x056A
    pkgdatalen = 28
    val = (0x10C, 0x02006320, pkgdatalen, pkgdatalen, cmd, market, 0, 0)
    pkg = bytearray(struct.pack("<HIHHIIHH", *val))
    pkg.extend(code.ljust(6, b"\x00"))
    pkg.extend(struct.pack("<IIIII", 0, mode, 0, start, count))
    return bytes(pkg)

def _b_top_board(category: int, size: int = 20) -> bytes:
    """涨跌停板."""
    cmd = 0x053F
    # Payload: <B 7s B = 1+7+1 = 9B
    pkgdatalen = 9
    val = (0x10C, 0x02006320, pkgdatalen, pkgdatalen, cmd, 0, 0, 0)
    pkg = bytearray(struct.pack("<HIHHIIHH", *val))
    pkg.extend(struct.pack("<B7sB", category, bytes.fromhex("000000000100"), size))
    return bytes(pkg)

def _b_quotes_list(category: int, start: int = 0, count: int = 0x50,
                   sort_type: int = 0, reverse: bool = False,
                   filter_raw: int = 0) -> bytes:
    """板块行情列表."""
    cmd = 0x054B
    sort_reverse = 0 if sort_type == 0 else (2 if reverse else 1)
    # Payload: 9I = 36B
    payload = struct.pack("<9I", category, sort_type, start, count, sort_reverse, 5, filter_raw, 1, 0)
    pkgdatalen = len(payload)
    val = (0x10C, 0x02006320, pkgdatalen, pkgdatalen, cmd, 0, 0, 0)
    pkg = bytearray(struct.pack("<HIHHIIHH", *val))
    pkg.extend(payload)
    return bytes(pkg)

def _b_unusual(market: int, start: int = 0, count: int = 600) -> bytes:
    """主力监控."""
    cmd = 0x0563
    # Payload: <H I I = 2+4+4 = 10B
    pkgdatalen = 10
    val = (0x10C, 0x02006320, pkgdatalen, pkgdatalen, cmd, market, start, count)
    pkg = bytearray(struct.pack("<HIHHIIHH", *val))
    return bytes(pkg)

def _b_chart_sampling_kline(market: int, code: str) -> bytes:
    """K线采样."""
    if isinstance(code, str):
        code = code.encode("gbk")
    cmd = 0xFD1
    # Payload: <H 22s H H 9x = 2+22+2+2+9 = 37B
    payload = struct.pack("<H22sHH9x", market, code, 1, 20)
    pkgdatalen = len(payload)
    val = (0x10C, 0x02006320, pkgdatalen, pkgdatalen, cmd, 0, 0, 0)
    pkg = bytearray(struct.pack("<HIHHIIHH", *val))
    pkg.extend(payload)
    return bytes(pkg)

def _b_history_orders_full(market: int, code: str, tdate: int) -> bytes:
    """历史委托."""
    if isinstance(code, str):
        code = code.encode("gbk")
    cmd = 0x0FB4
    # Payload: <I B 6s = 4+1+6 = 11B
    pkgdatalen = 11
    val = (0x10C, 0x02006320, pkgdatalen, pkgdatalen, cmd, market, 0, 0)
    pkg = bytearray(struct.pack("<HIHHIIHH", *val))
    pkg.extend(struct.pack("<IB6s", tdate, market, code))
    return bytes(pkg)

# ============== 解析器 (parsers) ==============

def _p_count(data: bytes) -> int:
    if len(data) < 2: return 0
    return struct.unpack("<H", data[:2])[0]

def _p_list(data: bytes) -> list[dict]:
    if len(data) < 2: return []
    count = struct.unpack("<H", data[:2])[0]
    items = []
    off = 2
    for _ in range(count):
        if off + 29 > len(data): break
        code = data[off:off+6].decode("utf-8", errors="ignore").strip("\x00")
        volunit = struct.unpack("<H", data[off+6:off+8])[0]
        name_raw = data[off+8:off+16]
        name = name_raw.decode("gbk", errors="ignore").strip("\x00")
        rev1 = data[off+16:off+20]
        decimal_point = data[off+20]
        pre_close_raw = struct.unpack("<I", data[off+21:off+25])[0]
        pre_close = decode_volume(pre_close_raw)
        items.append({
            "code": code, "name": name, "volunit": volunit,
            "decimal_point": decimal_point, "pre_close": pre_close,
        })
        off += 29
    return items

def _p_snapshot(data: bytes, coefficient: float = 0.01) -> list[dict]:
    """对齐 pytdx GetSecurityQuotesCmd.parseResponse."""
    pos = 0
    pos += 2  # skip b1 cb
    (num_stock,) = struct.unpack("<H", data[pos:pos+2])
    pos += 2
    stocks = []
    for _ in range(num_stock):
        market, code, active1 = struct.unpack("<B6sH", data[pos:pos+9])
        pos += 9
        price, pos = get_price(data, pos)
        last_close_diff, pos = get_price(data, pos)
        open_diff, pos = get_price(data, pos)
        high_diff, pos = get_price(data, pos)
        low_diff, pos = get_price(data, pos)
        reversed_bytes0, pos = get_price(data, pos)
        reversed_bytes1, pos = get_price(data, pos)
        vol, pos = get_price(data, pos)
        cur_vol, pos = get_price(data, pos)
        (amount_raw,) = struct.unpack("<I", data[pos:pos+4])
        amount = decode_volume(amount_raw)
        pos += 4
        s_vol, pos = get_price(data, pos)
        b_vol, pos = get_price(data, pos)
        reversed_bytes2, pos = get_price(data, pos)
        reversed_bytes3, pos = get_price(data, pos)
        bid1, pos = get_price(data, pos)
        ask1, pos = get_price(data, pos)
        bid_vol1, pos = get_price(data, pos)
        ask_vol1, pos = get_price(data, pos)
        bid2, pos = get_price(data, pos)
        ask2, pos = get_price(data, pos)
        bid_vol2, pos = get_price(data, pos)
        ask_vol2, pos = get_price(data, pos)
        bid3, pos = get_price(data, pos)
        ask3, pos = get_price(data, pos)
        bid_vol3, pos = get_price(data, pos)
        ask_vol3, pos = get_price(data, pos)
        bid4, pos = get_price(data, pos)
        ask4, pos = get_price(data, pos)
        bid_vol4, pos = get_price(data, pos)
        ask_vol4, pos = get_price(data, pos)
        bid5, pos = get_price(data, pos)
        ask5, pos = get_price(data, pos)
        bid_vol5, pos = get_price(data, pos)
        ask_vol5, pos = get_price(data, pos)
        (reversed_bytes4,) = struct.unpack("<H", data[pos:pos+2])
        pos += 2
        reversed_bytes5, pos = get_price(data, pos)
        reversed_bytes6, pos = get_price(data, pos)
        reversed_bytes7, pos = get_price(data, pos)
        reversed_bytes8, pos = get_price(data, pos)
        reversed_bytes9, active2 = struct.unpack("<hH", data[pos:pos+4])
        pos += 4
        code_str = code.decode("utf-8")
        one_stock = {
            "market": market, "code": code_str, "active1": active1,
            "price": _cal_price(price, 0, coefficient),
            "last_close": _cal_price(price, last_close_diff, coefficient),
            "open": _cal_price(price, open_diff, coefficient),
            "high": _cal_price(price, high_diff, coefficient),
            "low": _cal_price(price, low_diff, coefficient),
            "servertime": reversed_bytes0,
            "vol": vol, "cur_vol": cur_vol, "amount": amount,
            "s_vol": s_vol, "b_vol": b_vol,
            "bid1": _cal_price(price, bid1, coefficient),
            "ask1": _cal_price(price, ask1, coefficient),
            "bid_vol1": bid_vol1, "ask_vol1": ask_vol1,
            "bid2": _cal_price(price, bid2, coefficient),
            "ask2": _cal_price(price, ask2, coefficient),
            "bid_vol2": bid_vol2, "ask_vol2": ask_vol2,
            "bid3": _cal_price(price, bid3, coefficient),
            "ask3": _cal_price(price, ask3, coefficient),
            "bid_vol3": bid_vol3, "ask_vol3": ask_vol3,
            "bid4": _cal_price(price, bid4, coefficient),
            "ask4": _cal_price(price, ask4, coefficient),
            "bid_vol4": bid_vol4, "ask_vol4": ask_vol4,
            "bid5": _cal_price(price, bid5, coefficient),
            "ask5": _cal_price(price, ask5, coefficient),
            "bid_vol5": bid_vol5, "ask_vol5": ask_vol5,
            "reversed_bytes9": reversed_bytes9 / 100.0,
            "active2": active2,
        }
        stocks.append(one_stock)
    return stocks

@staticmethod
def _cal_price(base_p, diff, coefficient=0.01):
    return float(base_p + diff) * coefficient

def _p_kline(data: bytes, category: int, code: str = None, coefficient: float = 0.01) -> list[dict]:
    """对齐 pytdx GetSecurityBarsCmd.parseResponse.
    
    股票K线格式: date(4) + OHLC(4xget_price) + vol(4) + amt(4)
    无extra字段。
    
    使用差分编码: pre_diff_base = open_updated + close_diff_raw
    """
    if len(data) < 4:
        return []
    (ret_count,) = struct.unpack("<H", data[0:2])
    pos = 2
    klines = []
    pre_diff_base = 0
    
    for i in range(ret_count):
        year, month, day, hour, minute, pos = _get_datetime(category, data, pos)
        price_open_diff, pos = get_price(data, pos)
        price_close_diff, pos = get_price(data, pos)
        price_high_diff, pos = get_price(data, pos)
        price_low_diff, pos = get_price(data, pos)
        (vol_raw,) = struct.unpack("<I", data[pos:pos+4])
        vol = decode_volume(vol_raw)
        pos += 4
        (db_vol_raw,) = struct.unpack("<I", data[pos:pos+4])
        db_vol = decode_volume(db_vol_raw)
        pos += 4
        
        open_ = _cal_price1000(price_open_diff, pre_diff_base)
        price_open_diff = price_open_diff + pre_diff_base
        close = _cal_price1000(price_open_diff, price_close_diff)
        high = _cal_price1000(price_open_diff, price_high_diff)
        low = _cal_price1000(price_open_diff, price_low_diff)
        pre_diff_base = price_open_diff + price_close_diff
        kline = {
            "open": open_, "close": close, "high": high, "low": low,
            "vol": vol, "amount": db_vol,
            "year": year, "month": month, "day": day,
            "hour": hour, "minute": minute,
            "datetime": f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}",
        }
        klines.append(kline)
    return klines

def _cal_price1000(base_p, diff):
    return float(base_p + diff) / 1000

def _get_datetime(category, buffer, pos):
    """对齐 pytdx helper.get_datetime."""
    hour = 15
    minute = 0
    if category < 4 or category == 7 or category == 8:
        zip_day, minutes = struct.unpack("<HH", buffer[pos:pos+4])
        month = int((zip_day % 2048) / 100)
        year = (zip_day >> 11) + 2004
        day = (zip_day % 2048) % 100
        minute = minutes % 60
        hour = int(minutes / 60)
    else:
        (zip_day,) = struct.unpack("<I", buffer[pos:pos+4])
        month = int((zip_day % 10000) / 100)
        year = int(zip_day / 10000)
        day = zip_day % 100
    pos += 4
    return year, month, day, hour, minute, pos

def _p_today_minute(data: bytes, coefficient: float = 0.01) -> list[dict]:
    """对齐 pytdx GetMinuteTimeData.parseResponse."""
    pos = 0
    (num,) = struct.unpack("<H", data[:2])
    last_price = 0
    pos += 4
    prices = []
    for _ in range(num):
        price_raw, pos = get_price(data, pos)
        reversed1, pos = get_price(data, pos)
        vol, pos = get_price(data, pos)
        last_price = last_price + price_raw
        prices.append({
            "price": last_price * coefficient,
            "vol": vol,
        })
    return prices

def _p_today_trade(data: bytes) -> list[dict]:
    """对齐 pytdx GetTransactionData.parseResponse."""
    pos = 0
    (num,) = struct.unpack("<H", data[:2])
    pos += 2
    ticks = []
    last_price = 0
    for _ in range(num):
        (minutes,) = struct.unpack("<H", data[pos:pos+2]); pos += 2
        hour = int(minutes / 60)
        minute = minutes % 60
        price_raw, pos = get_price(data, pos)
        vol, pos = get_price(data, pos)
        num_orders, pos = get_price(data, pos)
        buy_or_sell, pos = get_price(data, pos)
        _, pos = get_price(data, pos)
        last_price = last_price + price_raw
        ticks.append({
            "time": f"{hour:02d}:{minute:02d}",
            "price": float(last_price) / 100,
            "vol": vol,
            "num": num_orders,
            "buyorsell": buy_or_sell,
        })
    return ticks

def _p_history_minute(data: bytes, coefficient: float = 0.01) -> list[dict]:
    """对齐 pytdx GetHistoryMinuteTimeData.parseResponse."""
    pos = 0
    (num,) = struct.unpack("<H", data[:2])
    last_price = 0
    pos += 6
    prices = []
    for _ in range(num):
        price_raw, pos = get_price(data, pos)
        reversed1, pos = get_price(data, pos)
        vol, pos = get_price(data, pos)
        last_price = last_price + price_raw
        prices.append({
            "price": float(last_price) * coefficient,
            "vol": vol,
        })
    return prices

def _p_history_trade(data: bytes) -> list[dict]:
    """对齐 pytdx GetHistoryTransactionData.parseResponse."""
    pos = 0
    (num,) = struct.unpack("<H", data[:2])
    pos += 2
    pos += 4  # skip 4 bytes
    last_price = 0
    ticks = []
    for _ in range(num):
        (minutes,) = struct.unpack("<H", data[pos:pos+2]); pos += 2
        hour = int(minutes / 60)
        minute = minutes % 60
        price_raw, pos = get_price(data, pos)
        vol, pos = get_price(data, pos)
        buy_or_sell, pos = get_price(data, pos)
        _, pos = get_price(data, pos)
        last_price = last_price + price_raw
        ticks.append({
            "time": f"{hour:02d}:{minute:02d}",
            "price": float(last_price) / 100,
            "vol": vol,
            "buyorsell": buy_or_sell,
        })
    return ticks

def _p_xdxr(data: bytes) -> list[dict]:
    """对齐 pytdx GetXdXrInfo.parseResponse."""
    pos = 0
    if len(data) < 11: return []
    pos += 9
    (num,) = struct.unpack("<H", data[pos:pos+2])
    pos += 2
    rows = []
    for _ in range(num):
        pos += 8  # skip 8 bytes (market+code+1)
        year, month, day, hour, minute, pos = _get_datetime(9, data, pos)
        (category,) = struct.unpack("<B", data[pos:pos+1]); pos += 1
        fenhong = peigujia = songzhuangu = peigu = suogu = None
        panqianliutong = panhouliutong = qianzongguben = houzongguben = None
        fenshu = xingquanjia = None
        if category == 1:
            fenhong, peigujia, songzhuangu, peigu = struct.unpack("<ffff", data[pos:pos+16])
        elif category in [11, 12]:
            _, _, suogu, _ = struct.unpack("<IIfI", data[pos:pos+16])
        elif category in [13, 14]:
            xingquanjia, _, fenshu, _ = struct.unpack("<fIfI", data[pos:pos+16])
        else:
            pl_raw, qzg_raw, phl_raw, hzg_raw = struct.unpack("<IIII", data[pos:pos+16])
            panqianliutong = decode_volume(pl_raw)
            panhouliutong = decode_volume(phl_raw)
            qianzongguben = decode_volume(qzg_raw)
            houzongguben = decode_volume(hzg_raw)
        pos += 16
        rows.append({
            "year": year, "month": month, "day": day,
            "category": category, "name": XDXR_CATEGORY_MAPPING.get(category, str(category)),
            "fenhong": fenhong, "peigujia": peigujia,
            "songzhuangu": songzhuangu, "peigu": peigu, "suogu": suogu,
            "panqianliutong": panqianliutong, "panhouliutong": panhouliutong,
            "qianzongguben": qianzongguben, "houzongguben": houzongguben,
            "fenshu": fenshu, "xingquanjia": xingquanjia,
        })
    return rows

def _p_finance(data: bytes) -> dict:
    """对齐 pytdx GetFinanceInfo.parseResponse."""
    pos = 0
    pos += 2  # skip count
    market, code = struct.unpack("<B6s", data[pos:pos+7])
    pos += 7
    fmt = "<fHHII" + "f" * 30
    vals = struct.unpack(fmt, data[pos:pos + struct.calcsize(fmt)])
    keys = [
        "liutongguben", "province", "industry", "updated_date", "ipo_date",
        "zongguben", "guojiagu", "faqirenfarengu", "farengu", "bgu", "hgu",
        "zhigonggu", "zongzichan", "liudongzichan", "gudingzichan", "wuxingzichan",
        "gudongrenshu", "liudongfuzhai", "changqifuzhai", "zibengongjijin",
        "jingzichan", "zhuyingshouru", "zhuyinglirun", "yingshouzhangkuan",
        "yingyelirun", "touzishouyu", "jingyingxianjinliu", "zongxianjinliu",
        "cunhuo", "lirunzonghe", "shuihoulirun", "jinglirun", "weifenlirun",
        "baoliu1", "baoliu2",
    ]
    result = {"market": market, "code": code.decode("utf-8")}
    for i, k in enumerate(keys):
        v = vals[i]
        if k in ("province", "industry", "updated_date", "ipo_date", "gudongrenshu"):
            result[k] = v
        else:
            result[k] = v * 10000
    return result

def _p_company_info_cat(data: bytes) -> list[dict]:
    """对齐 pytdx GetCompanyInfoCategory.parseResponse."""
    pos = 0
    (num,) = struct.unpack("<H", data[:2])
    pos += 2
    entries = []
    for _ in range(num):
        name, filename, start, length = struct.unpack("<64s80sII", data[pos:pos+152])
        pos += 152
        def get_str(b):
            p = b.find(b"\x00")
            if p != -1: b = b[0:p]
            return b.decode("gbk", "ignore")
        entries.append({
            "name": get_str(name), "filename": get_str(filename),
            "start": start, "length": length,
        })
    return entries

def _p_company_info_content(data: bytes) -> str:
    """对齐 pytdx GetCompanyInfoContent.parseResponse."""
    pos = 0
    _, length = struct.unpack("<10sH", data[:12])
    pos += 12
    content = data[pos:pos+length]
    return content.decode("gbk", "ignore")

def _p_block_info_meta(data: bytes) -> dict:
    """对齐 pytdx GetBlockInfoMeta.parseResponse."""
    size, _, hash_value, _ = struct.unpack("<I1s32s1s", data)
    return {"size": size, "hash_value": hash_value}

def _p_block_info(data: bytes) -> bytes:
    """对齐 pytdx GetBlockInfo.parseResponse."""
    return data[4:]

def _p_report_file(data: bytes) -> dict:
    """对齐 pytdx GetReportFile.parseResponse."""
    (chunk_size,) = struct.unpack("<I", data[:4])
    if chunk_size > 0:
        return {"chunksize": chunk_size, "chunkdata": data[4:]}
    return {"chunksize": 0}

# ============== 新增命令解析器 ==============

def _p_vol_profile(data: bytes, coefficient: float = 0.01) -> dict:
    """分时成交量分布.
    
    响应格式: <HB6sH + get_price(8项) + f(1) + get_price(2) + get_price(2) + 3x(BidAsk) + H + count x (<get_price get_price get_price get_price>)
    """
    pos = 0
    count, market, code, active = struct.unpack("<HB6sH", data[:11])
    pos = 11
    
    def _gp():
        nonlocal pos
        v, pos = get_price(data, pos)
        return v
    
    price = _gp()
    pre_close = _gp()
    open_p = _gp()
    high = _gp()
    low = _gp()
    server_time = _gp()
    neg_price = _gp()
    vol = _gp()
    cur_vol = _gp()
    
    amount, = struct.unpack("<f", data[pos:pos+4])
    pos += 4
    
    s_vol = _gp()
    b_vol = _gp()
    s_amount = _gp()
    open_amount = _gp()
    
    bids = []
    asks = []
    for _ in range(3):
        bid = _gp()
        ask = _gp()
        bid_vol = _gp()
        ask_vol = _gp()
        bids.append({"price": (price + bid) * coefficient, "vol": bid_vol})
        asks.append({"price": (price + ask) * coefficient, "vol": ask_vol})
    
    unknown, = struct.unpack("<H", data[pos:pos+2])
    pos += 2
    
    vol_profile = []
    start_price = price
    for _ in range(count):
        p_off, pos = get_price(data, pos)
        v, pos = get_price(data, pos)
        buy, pos = get_price(data, pos)
        sell, pos = get_price(data, pos)
        start_price += p_off
        vol_profile.append({
            "price": start_price * coefficient,
            "vol": v,
            "buy": buy,
            "sell": sell,
        })
    
    return {
        "market": market,
        "code": code.decode("gbk").strip("\x00"),
        "close": price * coefficient,
        "open": (price + open_p) * coefficient,
        "high": (price + high) * coefficient,
        "low": (price + low) * coefficient,
        "pre_close": (price + pre_close) * coefficient,
        "server_time": server_time,
        "neg_price": neg_price,
        "vol": vol,
        "cur_vol": cur_vol,
        "amount": amount,
        "in_vol": s_vol,
        "out_vol": b_vol,
        "s_amount": s_amount,
        "open_amount": open_amount,
        "handicap": {"bid": bids, "ask": asks},
        "active": active,
        "vol_profile": vol_profile,
    }

def _p_index_momentum(data: bytes) -> list[int]:
    """指数动能."""
    count, = struct.unpack("<H", data[:2])
    pos = 2
    start_mom = 0
    result = []
    for _ in range(count):
        mom, pos = get_price(data, pos)
        start_mom += mom
        result.append(start_mom)
    return result

def _p_aux(data: bytes, coefficient: float = 0.01) -> list[dict]:
    """分时副图."""
    count, = struct.unpack("<H", data[:2])
    pos = 2
    result = []
    for _ in range(count):
        price, pos = get_price(data, pos)
        vol, pos = get_price(data, pos)
        result.append({"price": price * coefficient, "vol": vol})
    return result

def _p_index_info(data: bytes, coefficient: float = 0.01) -> dict:
    """指数成分股/行情."""
    pos = 0
    count, market, code, active = struct.unpack("<IB6sH", data[:13])
    pos = 13
    
    def _gp():
        nonlocal pos
        v, pos = get_price(data, pos)
        return v
    
    close = _gp()
    pre_close_diff = _gp()
    open_diff = _gp()
    high_diff = _gp()
    low_diff = _gp()
    server_time = _gp()
    maybe_after_hour = _gp()
    vol = _gp()
    maybe_cur_vol = _gp()
    
    amount, = struct.unpack("<f", data[pos:pos+4])
    pos += 4
    
    fields = []
    for _ in range(16):
        fields.append(_gp())
    
    orders = []
    for _ in range(count):
        min_point = _gp()
        unknown = _gp()
        min_vol = _gp()
        orders.append({"price": min_point * coefficient, "unknown": unknown, "vol": min_vol})
    
    return {
        "market": market,
        "code": code.decode("gbk").strip("\x00"),
        "active": active,
        "close": close * coefficient,
        "pre_close": (close + pre_close_diff) * coefficient,
        "diff": -pre_close_diff * coefficient,
        "open": (close + open_diff) * coefficient,
        "high": (close + high_diff) * coefficient,
        "low": (close + low_diff) * coefficient,
        "amount": amount,
        "vol": vol,
        "orders": orders,
    }

def _p_quotes_detail(data: bytes, coefficient: float = 0.01) -> list[dict]:
    """详细行情 (5档买卖盘)."""
    _, count = struct.unpack("<HH", data[:4])
    pos = 4
    quotes = []
    for _ in range(count):
        market, code, active1 = struct.unpack("<B6sH", data[pos:pos+9])
        pos += 9
        
        def _gp():
            nonlocal pos
            v, pos = get_price(data, pos)
            return v
        
        price = _gp()
        pre_close = _gp()
        open_p = _gp()
        high = _gp()
        low = _gp()
        server_time = _gp()
        neg_price = _gp()
        vol = _gp()
        cur_vol = _gp()
        
        amount, = struct.unpack("<f", data[pos:pos+4])
        pos += 4
        
        s_vol = _gp()
        b_vol = _gp()
        s_amount = _gp()
        open_amount = _gp()
        
        bids = []
        asks = []
        for _ in range(5):
            bid = _gp()
            ask = _gp()
            bid_vol = _gp()
            ask_vol = _gp()
            bids.append({"price": (price + bid) * coefficient, "vol": bid_vol})
            asks.append({"price": (price + ask) * coefficient, "vol": ask_vol})
        
        unknown, _, rise_speed, active2 = struct.unpack("<h4shH", data[pos:pos+10])
        pos += 10
        
        quotes.append({
            "market": market,
            "code": code.decode("gbk").strip("\x00"),
            "close": price * coefficient,
            "open": (price + open_p) * coefficient,
            "high": (price + high) * coefficient,
            "low": (price + low) * coefficient,
            "pre_close": (price + pre_close) * coefficient,
            "server_time": server_time,
            "neg_price": neg_price,
            "vol": vol,
            "cur_vol": cur_vol,
            "amount": amount,
            "in_vol": b_vol,
            "out_vol": s_vol,
            "s_amount": s_amount,
            "open_amount": open_amount,
            "handicap": {"bid": bids, "ask": asks},
            "rise_speed": rise_speed,
            "active": active1,
        })
    return quotes

def _p_tick_chart(data: bytes, coefficient: float = 0.01) -> list[dict]:
    """分时明细."""
    num, _ = struct.unpack("<HH", data[:4])
    pos = 4
    result = []
    start_price = 0
    start_avg = 0
    for _ in range(num):
        price, pos = get_price(data, pos)
        avg, pos = get_price(data, pos)
        vol, pos = get_price(data, pos)
        result.append({
            "price": (start_price + price) * coefficient,
            "avg": (start_avg + avg) * coefficient,
            "vol": vol,
        })
        if start_price == 0:
            start_price = price
        if start_avg == 0:
            start_avg = avg
    return result

def _p_auction(data: bytes) -> list[dict]:
    """集合竞价."""
    count, = struct.unpack("<H", data[:2])
    result = []
    for i in range(count):
        time_raw, price, matched, unmatched, u, second = struct.unpack("<HfIiBB", data[2 + i*16: 2 + i*16 + 16])
        result.append({
            "time": f"{time_raw // 60:02d}:{time_raw % 60:02d}:{second:02d}",
            "price": price,
            "matched": matched,
            "unmatched": unmatched,
        })
    return result

def _p_top_board(data: bytes) -> dict:
    """涨跌停板."""
    size, = struct.unpack("<B", data[:1])
    pos = 1
    result = {
        "increase": [], "decrease": [], "amplitude": [],
        "rise_speed": [], "fall_speed": [], "vol_ratio": [],
        "pos_commission_ratio": [], "neg_commission_ratio": [],
        "turnover": [],
    }
    categories = list(result.keys())
    for cat in categories:
        for _ in range(size):
            market, code, price, value = struct.unpack("<B6sff", data[pos:pos+15])
            pos += 15
            result[cat].append({
                "market": market,
                "code": code.decode("gbk").strip("\x00"),
                "price": price,
                "value": value,
            })
    return result

def _p_quotes_list(data: bytes, coefficient: float = 0.01) -> list[dict]:
    """板块行情列表."""
    block, count = struct.unpack("<HH", data[:4])
    pos = 4
    stocks = []
    for _ in range(count):
        market, code, active1 = struct.unpack("<B6sH", data[pos:pos+9])
        pos += 9
        
        def _gp():
            nonlocal pos
            v, pos = get_price(data, pos)
            return v
        
        price = _gp()
        pre_close = _gp()
        open_p = _gp()
        high = _gp()
        low = _gp()
        server_time = _gp()
        neg_price = _gp()
        vol = _gp()
        cur_vol = _gp()
        
        amount, = struct.unpack("<f", data[pos:pos+4])
        pos += 4
        
        in_vol = _gp()
        out_vol = _gp()
        s_amount = _gp()
        open_amount = _gp()
        
        bid = _gp()
        ask = _gp()
        bid_vol = _gp()
        ask_vol = _gp()
        
        unknown, rise_speed, short_turnover, min2_amount, opening_rush, extra_pair, vol_rise_speed, depth, extra_meta, active2 = struct.unpack("<Hhhfh10sff24sH", data[pos:pos+56])
        pos += 56
        
        active_flag, decimal = struct.unpack("<BB", extra_pair[:2])
        
        stocks.append({
            "market": market,
            "code": code.decode("gbk").strip("\x00"),
            "close": price * coefficient,
            "open": (price + open_p) * coefficient,
            "high": (price + high) * coefficient,
            "low": (price + low) * coefficient,
            "pre_close": (price + pre_close) * coefficient,
            "server_time": server_time,
            "neg_price": neg_price,
            "vol": vol,
            "cur_vol": cur_vol,
            "amount": amount,
            "in_vol": in_vol,
            "out_vol": out_vol,
            "s_amount": s_amount,
            "open_amount": open_amount,
            "handicap": {
                "bid": [{"price": (price + bid) * coefficient, "vol": bid_vol}],
                "ask": [{"price": (price + ask) * coefficient, "vol": ask_vol}],
            },
            "rise_speed": rise_speed,
            "short_turnover": short_turnover,
            "min2_amount": min2_amount,
            "opening_rush": opening_rush,
            "active_flag": active_flag,
            "decimal": decimal,
            "vol_rise_speed": vol_rise_speed,
            "depth": depth,
            "active": active1,
        })
    return stocks

def _p_unusual(data: bytes) -> list[dict]:
    """主力监控."""
    count, = struct.unpack("<H", data[:2])
    results = []
    for i in range(count):
        offset = 2 + 32 * i
        market, code, _, unusual_type, _, index, z = struct.unpack("<H6sBBBHH", data[offset+1:offset+16])
        v1, v2, v3, v4 = struct.unpack("<BBBB", data[offset+17:offset+21])
        flag, = struct.unpack("<B", data[offset+30:offset+31])
        hour, minute_sec = struct.unpack("<BH", data[offset+31:offset+34])
        results.append({
            "index": index,
            "market": market,
            "code": code.decode("gbk").strip("\x00"),
            "time": f"{hour:02d}:{minute_sec // 100:02d}:{minute_sec % 100:02d}",
            "unusual_type": unusual_type,
            "v1": v1, "v2": v2, "v3": v3, "v4": v4,
            "flag": flag,
        })
    return results

def _p_chart_sampling_kline(data: bytes) -> list[float]:
    """K线采样."""
    if len(data) < 42:
        return []
    market, code = struct.unpack("<H6s", data[:8])
    mode, divisor = struct.unpack("<16xHH6x", data[8:34])
    interval, pre_close, count = struct.unpack("<HfH", data[34:42])
    prices = []
    available_count = max(0, (len(data) - 42) // 4)
    actual_count = min(count, available_count)
    for i in range(actual_count):
        p, = struct.unpack("<f", data[i * 4 + 42: i * 4 + 46])
        prices.append(p)
    return prices

def _p_history_orders(data: bytes, coefficient: float = 0.01) -> list[dict]:
    """历史委托."""
    count, pre_close = struct.unpack("<Hf", data[:6])
    pos = 6
    orders = []
    last_price = 0
    for _ in range(count):
        price, pos = get_price(data, pos)
        unknown, pos = get_price(data, pos)
        vol, pos = get_price(data, pos)
        last_price += price
        orders.append({
            "price": last_price * coefficient,
            "unknown": unknown,
            "vol": vol,
        })
    return orders

# ============== 新增命令解析器 ==============

def _p_quotes_encrypt(data: bytes, coefficient: float = 0.01) -> list[dict]:
    """增量刷新 (0x0547). 数据经过 XOR 0x93 解密."""
    data = bytes(b ^ 0x93 for b in data)
    count, = struct.unpack("<H", data[:2])
    pos = 2
    result = []
    for _ in range(count):
        market, code, active = struct.unpack("<B6sH", data[pos:pos+9])
        pos += 9
        close, pos = get_price(data, pos)
        pre_close, pos = get_price(data, pos)
        open_, pos = get_price(data, pos)
        high, pos = get_price(data, pos)
        low, pos = get_price(data, pos)
        time_raw, = struct.unpack("<I", data[pos:pos+4]); pos += 4
        u1, pos = get_price(data, pos)
        vol, pos = get_price(data, pos)
        cur_vol, pos = get_price(data, pos)
        amount_raw, = struct.unpack("<f", data[pos:pos+4]); pos += 4
        amount = amount_raw * 10000
        in_vol, pos = get_price(data, pos)
        out_vol, pos = get_price(data, pos)
        s_amount, pos = get_price(data, pos)
        open_amount, pos = get_price(data, pos)
        bids, asks = [], []
        for _ in range(5):
            bid, pos = get_price(data, pos)
            ask, pos = get_price(data, pos)
            bid_vol, pos = get_price(data, pos)
            ask_vol, pos = get_price(data, pos)
            bid += close
            ask += close
            bids.append({"price": bid * coefficient, "vol": bid_vol})
            asks.append({"price": ask * coefficient, "vol": ask_vol})
        u2, u3, u4 = struct.unpack("<HII", data[pos:pos+10]); pos += 10
        for _ in range(6):
            _, pos = get_price(data, pos)
        from datetime import time as dt_time
        result.append({
            "market": market,
            "code": code.decode("gbk").strip("\x00"),
            "active": active,
            "close": close * coefficient,
            "pre_close": (close + pre_close) * coefficient,
            "open": (close + open_) * coefficient,
            "high": (close + high) * coefficient,
            "low": (close + low) * coefficient,
            "time": dt_time(time_raw // 10000, time_raw // 100 % 100, time_raw % 100),
            "vol": vol, "cur_vol": cur_vol, "amount": amount,
            "in_vol": in_vol, "out_vol": out_vol,
            "s_amount": s_amount, "open_amount": open_amount,
            "bids": bids, "asks": asks,
        })
    return result

def _p_recent_minute(data: bytes, coefficient: float = 0.01) -> list[dict]:
    """近期分时 / 历史tick (0x0FEB)."""
    count, m, n = struct.unpack("<HII", data[:10])
    pos = 10
    result = []
    start_price = 0
    avg_price = 0
    for _ in range(count):
        price, pos = get_price(data, pos)
        avg, pos = get_price(data, pos)
        vol, pos = get_price(data, pos)
        if start_price == 0:
            start_price = price
        if avg_price == 0:
            avg_price = avg
        result.append({
            "price": (start_price + price) * coefficient,
            "avg": (avg_price + avg) * coefficient,
            "vol": vol,
        })
    return result

def _p_limits(data: bytes) -> list[dict]:
    """涨跌停限制 (0x0452)."""
    count, = struct.unpack("<H", data[:2])
    result = []
    for i in range(count):
        market, code_num, p1, p2 = struct.unpack("<BIff", data[i*13+2:i*13+15])
        result.append({
            "market": market,
            "code": str(code_num),
            "p1": p1,
            "p2": p2,
        })
    return result

def _p_chart_sampling_sparkline(data: bytes) -> list[float]:
    """小走势图 (0xFD1)."""
    if len(data) < 42:
        return []
    market, code = struct.unpack("<H6s", data[:8])
    mode, divisor = struct.unpack("<16xHH6x", data[8:34])
    interval, pre_close, count = struct.unpack("<HfH", data[34:42])
    prices = []
    available_count = max(0, (len(data) - 42) // 4)
    actual_count = min(count, available_count)
    for i in range(actual_count):
        p, = struct.unpack("<f", data[i*4+42:i*4+46])
        prices.append(p)
    return prices

def _p_history_orders_v2(data: bytes, coefficient: float = 0.01) -> list[dict]:
    """历史委托 (0xFB4) 备用解析器."""
    count, pre_close = struct.unpack("<Hf", data[:6])
    pos = 6
    orders = []
    last_price = 0
    for _ in range(count):
        price, pos = get_price(data, pos)
        unknown, pos = get_price(data, pos)
        vol, pos = get_price(data, pos)
        last_price += price
        orders.append({
            "price": last_price * coefficient,
            "unknown": unknown,
            "vol": vol,
        })
    return orders
