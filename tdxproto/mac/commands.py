"""MAC 协议板块命令构造器与解析器."""

import struct
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import TdxBlock, BelongBoardInfo, BoardMember, BoardSummary


class BoardType:
    """板块类型枚举."""
    HY = 0          # 行业一级
    HY2 = 1         # 行业二级
    GN = 3          # 概念
    FG = 4          # 风格
    DQ = 5          # 地区
    OTHER = 6       # 其他
    YJ_LEVEL1 = 7   # 业绩一级
    YJ_LEVEL2 = 8   # 业绩二级
    YJ_LEVEL3 = 9   # 业绩三级
    ALL = 255       # 全部


class SortColumn:
    """排序列."""
    RISE_SPEED = 0      # 涨速
    CHANGE_PCT = 1      # 涨跌幅
    AMOUNT = 2          # 成交额
    VOL = 3             # 成交量
    MAIN_NET_AMOUNT = 4 # 主力净流入


class SortOrder:
    """排序方向."""
    ASC = 0
    DESC = 1


class FieldBit:
    """字段位图定义 (MAC 协议)."""
    PRE_CLOSE = 0x00
    OPEN = 0x01
    HIGH = 0x02
    LOW = 0x03
    CLOSE = 0x04
    VOL = 0x05
    AMOUNT = 0x06
    PRICE = 0x07
    RISE_SPEED = 0x08
    SHORT_TURNOVER = 0x09
    MIN2_AMOUNT = 0x0A
    OPENING_RUSH = 0x0B
    VOL_RISE_SPEED = 0x0C
    DEPTH = 0x0D
    MAIN_NET_AMOUNT = 0x0E
    NET_MAJOR_ORDER = 0x0F
    NET_MID_ORDER = 0x10
    NET_SMALL_ORDER = 0x11
    NET_HUGE_ORDER = 0x12
    UP_COUNT = 0x13
    DOWN_COUNT = 0x14
    FLAT_COUNT = 0x15
    UP_LIMIT = 0x16
    DOWN_LIMIT = 0x17
    NEW_HIGH = 0x18
    NEW_LOW = 0x19
    LIMIT_OPEN_TIMES = 0x1A
    AMPLITUDE = 0x1B
    TURNOVER_RATE = 0x1C
    TURN_OVER_RATIO = 0x1D
    MAIN_NET_BUY = 0x1E
    MAIN_NET_SELL = 0x1F
    BID1 = 0x20
    ASK1 = 0x21
    BID_VOL1 = 0x22
    ASK_VOL1 = 0x23
    SERVER_TIME = 0x24
    RISE_SPEED_SECOND = 0x25
    BID2 = 0x26
    ASK2 = 0x27
    BID_VOL2 = 0x28
    ASK_VOL2 = 0x29
    BID3 = 0x2A
    ASK3 = 0x2B
    BID_VOL3 = 0x2C
    ASK_VOL3 = 0x2D
    BID4 = 0x2E
    ASK4 = 0x2F
    BID_VOL4 = 0x30
    ASK_VOL4 = 0x31
    BID5 = 0x32
    ASK5 = 0x33
    BID_VOL5 = 0x34
    ASK_VOL5 = 0x35
    BID6 = 0x36
    ASK6 = 0x37
    BID_VOL6 = 0x38
    ASK_VOL6 = 0x39
    BID7 = 0x3A
    ASK7 = 0x3B
    BID_VOL7 = 0x3C
    ASK_VOL7 = 0x3D
    BID8 = 0x3E
    ASK8 = 0x3F
    BID_VOL8 = 0x40
    ASK_VOL8 = 0x41
    BID9 = 0x42
    ASK9 = 0x43
    BID_VOL9 = 0x44
    ASK_VOL9 = 0x45
    BID10 = 0x46
    ASK10 = 0x47
    BID_VOL10 = 0x48
    ASK_VOL10 = 0x49
    NET_IN_ORDER = 0x4A
    NET_OUT_ORDER = 0x4B
    MA5_CLOSE = 0x4C
    MA10_CLOSE = 0x4D
    MA20_CLOSE = 0x4E
    MA30_CLOSE = 0x4F
    MA60_CLOSE = 0x50
    VWAP = 0x51
    UPPER_BAND = 0x52
    LOWER_BAND = 0x53
    MID_BAND = 0x54
    STO_K = 0x55
    STO_D = 0x56
    STO_J = 0x57
    KDJ_RSI = 0x58
    RSI_6 = 0x59
    RSI_12 = 0x5A
    RSI_24 = 0x5B
    EXPAND = 0x5C
    WR_1 = 0x5D
    WR_2 = 0x5E
    MTM = 0x5F
    MOMENTUM = 0x60
    OBV = 0x61
    ASI = 0x62
    VOLATILITY = 0x63
    CCI = 0x64
    BIAS = 0x65
    PSY = 0x66
    PSYMA = 0x67
    EMV = 0x68
    DPO = 0x69
    TRIX = 0x6A
    DMA = 0x6B
    AROON_UP = 0x6C
    AROON_DOWN = 0x6D
    AROON_OSC = 0x6E
    AROON_IND = 0x6F
    DIF = 0x70
    DEA = 0x71
    MACD = 0x72
    K = 0x73
    D = 0x74
    J = 0x75
    BOLL_UPPER = 0x76
    BOLL_MID = 0x77
    BOLL_LOWER = 0x78
    PDI = 0x79
    MDI = 0x7A
    ADX = 0x7B
    ADXR = 0x7C
    WAD = 0x7D
    ATR = 0x7E
    BIAS_MAIN = 0x7F
    DIST = 0x80
    CYR = 0x81
    CYW = 0x82
    ZIG_CHANGE = 0x83
    ZIG_PERCENT = 0x84
    LWR_1 = 0x85
    LWR_2 = 0x86
    VAMA = 0x87
    VAMAD = 0x88
    VAMAJ = 0x89
    FSL = 0x8A
    FSL1 = 0x8B
    FSL2 = 0x8C
    FSL3 = 0x8D


def _convert_board_code(board_code: str | int) -> int:
    """转换板块代码为服务器协议代码.

    US0401   → 30401
    HK0283   → 20283
    000686   → 31686
    399372   → 30372
    899050   → 32050
    880686   → 20686
    其他     → int(N)
    """
    code_str = str(board_code)
    if code_str.startswith("US"):
        return 30000 + int(code_str[2:])
    if code_str.startswith("HK"):
        return 20000 + int(code_str[2:])
    if code_str.startswith("00") and len(code_str) == 6:
        return 31000 + int(code_str)
    if code_str.startswith("399") and len(code_str) == 6:
        return int(code_str) - 399000 + 30000
    if code_str.startswith("899") and len(code_str) == 6:
        return int(code_str) - 899000 + 32000
    if code_str.startswith("880") and len(code_str) == 6:
        return int(code_str) - 880000 + 20000
    return int(code_str)


# ============================================================
# BoardListCmd — 板块列表查询 (cmd=0x1231)
# ============================================================

def _b_board_list(page_size: int = 150, board_type: int = BoardType.ALL,
                  sort_column: int = SortColumn.RISE_SPEED,
                  sort_order: int = SortOrder.DESC,
                  start: int = 0) -> bytes:
    """构建板块列表请求."""
    payload = struct.pack("<HHBBHH8x", page_size, board_type, sort_column,
                          sort_order, start, 1)
    return payload


def _p_board_list(data: bytes) -> list[dict]:
    """解析板块列表响应.

    前 4 字节: count_all(H) + total(H)
    之后每 160 字节一条记录.
    """
    if len(data) < 4:
        return []
    count_all, total = struct.unpack("<HH", data[:4])
    count = count_all // 2
    results = []
    pos = 4
    for _ in range(count):
        if len(data) < pos + 160:
            break
        market, code_b, name_b, price, rise_speed, pre_close, \
            symbol_market, symbol_code_b, symbol_name_b, \
            symbol_price, symbol_rise_speed, symbol_pre_close = \
            struct.unpack_from("<H6s16s44sfffH6s16s44sfff", data, pos)
        results.append({
            "market": market,
            "code": code_b.decode("gbk", errors="replace").strip("\x00"),
            "name": name_b.decode("gbk", errors="replace").strip("\x00"),
            "price": round(price, 3),
            "rise_speed": round(rise_speed, 2),
            "pre_close": round(pre_close, 3),
            "symbol_market": symbol_market,
            "symbol_code": symbol_code_b.decode("gbk", errors="replace").strip("\x00"),
            "symbol_name": symbol_name_b.decode("gbk", errors="replace").strip("\x00"),
            "symbol_price": round(symbol_price, 3),
            "symbol_rise_speed": round(symbol_rise_speed, 2),
            "total": total,
        })
        pos += 160
    return results


# ============================================================
# BoardMembersQuotesCmd — 板块成分股报价 (cmd=0x122C)
# ============================================================

def build_bitmap(fields: set[int]) -> tuple[bytes, bytes]:
    """构建字段位图.

    返回 (bitmap_bytes, control_bytes).
    """
    bitmap = bytearray(16)
    for f in fields:
        byte_idx = f >> 3
        bit_idx = f & 0x07
        if byte_idx < 16:
            bitmap[byte_idx] |= (1 << bit_idx)
    control = bytearray(4)
    control[3] = 1  # CTRL_EXTENDED
    return bytes(bitmap), bytes(control)


def get_active_fields(bitmap: bytes) -> list[int]:
    """从位图解析活跃字段."""
    fields = []
    for i in range(16):
        byte_val = bitmap[i]
        for bit in range(8):
            if byte_val & (1 << bit):
                fields.append(i * 8 + bit)
    return sorted(fields)


def _b_board_members_quotes(board_code: str | int, page_size: int = 80,
                            start: int = 0, sort_type: int = 0,
                            sort_order: int = SortOrder.DESC,
                            fields: set[int] | None = None) -> bytes:
    """构建板块成分股请求."""
    if fields is None:
        fields = {
            FieldBit.PRE_CLOSE, FieldBit.OPEN, FieldBit.HIGH,
            FieldBit.LOW, FieldBit.CLOSE, FieldBit.VOL,
            FieldBit.AMOUNT, FieldBit.PRICE, FieldBit.RISE_SPEED,
            FieldBit.MAIN_NET_AMOUNT,
        }

    converted_code = _convert_board_code(board_code)
    bitmap_bytes, control_bytes = build_bitmap(fields)

    # Part 1: 24 字节
    part1 = struct.pack("<I9xHIHBB", converted_code, sort_type, start,
                        page_size, sort_order, 0)
    return part1 + bitmap_bytes + control_bytes


def _p_board_members_quotes(data: bytes, coefficient: float = 0.01) -> list[dict]:
    """解析板块成分股响应."""
    if len(data) < 20:
        return []

    resp_bitmap = data[:16]
    active_fields = get_active_fields(resp_bitmap)

    pos = 20
    if pos >= len(data):
        return []
    total, row_count = struct.unpack_from("<IH", data, pos)
    pos += 6

    results = []
    for _ in range(row_count):
        if pos + 68 > len(data):
            break
        market, code_b, name_b = struct.unpack_from("<H22s44s", data, pos)
        pos += 68
        code = code_b.decode("gbk", errors="replace").strip("\x00")
        name = name_b.decode("gbk", errors="replace").strip("\x00")

        row_data = {"market": market, "code": code, "name": name}
        field_values = []
        for _ in range(len(active_fields)):
            if pos + 4 <= len(data):
                val = struct.unpack_from("<f", data, pos)[0]
                field_values.append(val)
                pos += 4
            else:
                field_values.append(0.0)

        for i, field_bit in enumerate(active_fields):
            if i < len(field_values):
                name_map = {
                    FieldBit.PRICE: "price",
                    FieldBit.CLOSE: "close",
                    FieldBit.OPEN: "open",
                    FieldBit.HIGH: "high",
                    FieldBit.LOW: "low",
                    FieldBit.PRE_CLOSE: "pre_close",
                    FieldBit.VOL: "vol",
                    FieldBit.AMOUNT: "amount",
                    FieldBit.RISE_SPEED: "rise_speed",
                    FieldBit.MAIN_NET_AMOUNT: "main_net_amount",
                    FieldBit.NET_MAJOR_ORDER: "net_major_order",
                    FieldBit.NET_MID_ORDER: "net_mid_order",
                    FieldBit.NET_SMALL_ORDER: "net_small_order",
                    FieldBit.UP_COUNT: "up_count",
                    FieldBit.DOWN_COUNT: "down_count",
                    FieldBit.FLAT_COUNT: "flat_count",
                    FieldBit.UP_LIMIT: "up_limit",
                    FieldBit.DOWN_LIMIT: "down_limit",
                    FieldBit.AMPLITUDE: "amplitude",
                    FieldBit.TURNOVER_RATE: "turnover_rate",
                    FieldBit.SERVER_TIME: "server_time",
                }
                key = name_map.get(field_bit, f"field_{field_bit}")
                row_data[key] = round(field_values[i], 3) if isinstance(field_values[i], float) else field_values[i]

        results.append(row_data)

    return results


# ============================================================
# SymbolBelongBoardCmd — 个股所属板块 (cmd=0x1218, head_flag=1)
# ============================================================

def _b_stock_blocks(market: int, code: str) -> bytes:
    """构建个股所属板块请求.

    格式: <H8s16x21s (55 字节)
    """
    if isinstance(code, str):
        code = code.encode("gbk")
    code_padded = code.ljust(8, b"\x00")
    marker = b"Stock_GLHQ"
    payload = struct.pack("<H8s16x21s", market, code_padded, marker)
    return payload


def _p_stock_blocks(data: bytes) -> list[dict]:
    """解析个股所属板块响应.

    前 27 字节头，之后是 JSON 数组（GBK 编码）.
    """
    if len(data) < 27:
        return []

    json_start = 27
    json_raw = data[json_start:]
    try:
        json_str = json_raw.decode("gbk", errors="replace")
    except Exception:
        json_str = json_raw.decode("utf-8", errors="replace")

    import json
    try:
        items = json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        return []

    results = []
    for item in items:
        if not isinstance(item, (list, tuple)) or len(item) < 4:
            continue
        results.append({
            "board_type": item[0],
            "market": item[1],
            "board_code": str(item[2]),
            "board_name": str(item[3]) if len(item) > 3 else "",
            "close": item[4] if len(item) > 4 else 0.0,
            "pre_close": item[5] if len(item) > 5 else 0.0,
        })
    return results


# ============================================================
# BoardSummaryCmd — 板块汇总 (cmd=0x122B)
# ============================================================

def _b_board_summary(board_code: str | int, fields: set[int] | None = None) -> bytes:
    """构建板块汇总请求（复用成分股接口，获取全量成分股后聚合）."""
    if fields is None:
        fields = {
            FieldBit.PRICE, FieldBit.CLOSE, FieldBit.AMOUNT,
            FieldBit.RISE_SPEED, FieldBit.MAIN_NET_AMOUNT,
            FieldBit.UP_COUNT, FieldBit.DOWN_COUNT,
        }
    return _b_board_members_quotes(board_code, page_size=2000, fields=fields)


def _p_board_summary(data: bytes, coefficient: float = 0.01) -> dict:
    """解析板块汇总数据（从成分股聚合）.

    返回: member_count, amount, vol, main_net_amount, up_count, down_count 等.
    """
    members = _p_board_members_quotes(data, coefficient=coefficient)
    if not members:
        return {}

    total_amount = 0.0
    total_vol = 0
    total_main_net = 0.0
    up_count = 0
    down_count = 0
    flat_count = 0
    prices = []

    for m in members:
        amount = m.get("amount", 0) or 0
        vol = m.get("vol", 0) or 0
        main_net = m.get("main_net_amount", 0) or 0
        close = m.get("close", 0) or m.get("price", 0)
        prices.append(close)

        total_amount += amount
        total_vol += vol
        total_main_net += main_net

        pre_close = m.get("pre_close", 0) or 0
        if close > pre_close and pre_close > 0:
            up_count += 1
        elif close < pre_close and pre_close > 0:
            down_count += 1
        else:
            flat_count += 1

    avg_price = sum(prices) / len(prices) if prices else 0
    return {
        "member_count": len(members),
        "amount": round(total_amount, 2),
        "vol": total_vol,
        "main_net_amount": round(total_main_net, 2),
        "up_count": up_count,
        "down_count": down_count,
        "flat_count": flat_count,
        "avg_price": round(avg_price, 3),
    }


# ============================================================
# BoardChangeRankingCmd — N日涨跌幅排行 (cmd=0x122B)
# ============================================================

def _b_board_change_ranking(board_type: int, days: int = 5,
                            sort_order: int = SortOrder.DESC, top_n: int = 100) -> bytes:
    """构建板块N日涨跌幅排行请求."""
    payload = struct.pack("<HHHB", board_type, days, top_n, sort_order)
    return payload


def _p_board_change_ranking(data: bytes) -> list[dict]:
    """解析N日涨跌幅排行响应."""
    if len(data) < 4:
        return []
    count = struct.unpack("<H", data[:2])[0]
    results = []
    pos = 4
    for _ in range(count):
        if pos + 160 > len(data):
            break
        market, code_b, name_b, change_pct, pre_close, \
            symbol_market, symbol_code_b, symbol_name_b = \
            struct.unpack_from("<H6s44sfH6s44s", data, pos)
        results.append({
            "market": market,
            "code": code_b.decode("gbk", errors="replace").strip("\x00"),
            "name": name_b.decode("gbk", errors="replace").strip("\x00"),
            "change_pct": round(change_pct, 2),
            "pre_close": round(pre_close, 3),
            "symbol_market": symbol_market,
            "symbol_code": symbol_code_b.decode("gbk", errors="replace").strip("\x00"),
            "symbol_name": symbol_name_b.decode("gbk", errors="replace").strip("\x00"),
        })
        pos += 160
    return results


# ============================================================
# Category 枚举（用于 quote-list 市场分类批量报价）
# ============================================================

class Category:
    """市场分类枚举，用作 board_code 参数."""
    SH = 0          # 上证A股
    SZ = 2          # 深证A股
    A = 6           # 全部A股
    B = 7           # B股
    KCB = 8         # 科创板
    BJ = 12         # 北证A
    CYB = 14        # 创业板


class FilterType:
    """排除标志位掩码."""
    NEW = 1         # 次新股
    KC = 2          # 科创板
    ST = 4          # ST/*ST
    CY = 8          # 创业板
    HK_CONNECT = 16 # 互联互通标的
    BJ = 32         # 北交所
    APPROVAL = 64   # 核准制
    REGISTRATION = 128 # 注册制


def _b_category_quotes(category: int, page_size: int = 80,
                       start: int = 0, sort_type: int = 0,
                       sort_order: int = 1, exclude_flags: int = 0) -> bytes:
    """构建市场分类批量报价请求（复用 0x122C）.

    category: Category 枚举值（如 Category.A=6, Category.KCB=8）
    exclude_flags: FilterType 组合（如 FilterType.ST | FilterType.NEW）
    """
    fields = {
        FieldBit.PRICE, FieldBit.CLOSE, FieldBit.OPEN,
        FieldBit.HIGH, FieldBit.LOW, FieldBit.PRE_CLOSE,
        FieldBit.VOL, FieldBit.AMOUNT, FieldBit.RISE_SPEED,
        FieldBit.MAIN_NET_AMOUNT, FieldBit.UP_COUNT,
        FieldBit.DOWN_COUNT, FieldBit.FLAT_COUNT,
        FieldBit.AMPLITUDE, FieldBit.TURNOVER_RATE,
    }
    bitmap_bytes, control_bytes = build_bitmap(fields)
    control_bytes_list = bytearray(control_bytes)
    control_bytes_list[1] = exclude_flags & 0xFF
    control_bytes = bytes(control_bytes_list)

    part1 = struct.pack("<I9xHIHBB", category, sort_type, start,
                        page_size, sort_order, 0)
    return part1 + bitmap_bytes + control_bytes


def _p_category_quotes(data: bytes, coefficient: float = 0.01) -> list[dict]:
    """解析市场分类批量报价响应（复用成分股解析器逻辑）."""
    return _p_board_members_quotes(data, coefficient=coefficient)


# ============================================================
# CapitalFlowCmd — 个股资金流向 (cmd=0x1218, head_flag=2)
# ============================================================

def _b_capital_flow(market: int, code: str) -> bytes:
    """构建资金流向请求.

    格式: <H8s16x21s (55 字节)，marker="Stock_ZJLX"
    """
    if isinstance(code, str):
        code = code.encode("gbk")
    code_padded = code.ljust(8, b"\x00")
    marker = b"Stock_ZJLX"
    payload = struct.pack("<H8s16x21s", market, code_padded, marker)
    return payload


def _p_capital_flow(data: bytes) -> dict:
    """解析资金流向响应.

    前 27 字节头，之后是 JSON 数组（GBK 编码）.
    """
    if len(data) < 27:
        return {}

    json_start = 27
    json_raw = data[json_start:]
    try:
        json_str = json_raw.decode("gbk", errors="replace")
    except Exception:
        json_str = json_raw.decode("utf-8", errors="replace")

    import json
    try:
        items = json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        return {}

    result = {}
    if not items or len(items) < 2:
        return result

    today = items[0]
    if len(today) >= 4:
        result["main_in"] = round(float(today[0]), 2)
        result["main_out"] = round(float(today[1]), 2)
        result["main_net"] = round(result["main_in"] - result["main_out"], 2)
        result["retail_in"] = round(float(today[2]), 2)
        result["retail_out"] = round(float(today[3]), 2)
        result["retail_net"] = round(result["retail_in"] - result["retail_out"], 2)

    five_days = items[1] if len(items) > 1 else []
    if len(five_days) >= 6:
        result["mid_net_5d"] = round(float(five_days[4]), 2)
        result["large_net_5d"] = round(float(five_days[3]), 2)

    return result


# ============================================================
# ServerInfoCmd — 服务器信息 (cmd=0x120F)
# ============================================================

def _b_server_info() -> bytes:
    """构建服务器信息查询请求.

    固定 68 字节.
    """
    header = bytes.fromhex("04002d31")
    padding = b"\x00" * 8
    mid = bytes.fromhex("0027060e")
    tail = b"\x00" * 52
    return header + padding + mid + tail


def _p_server_info(data: bytes) -> dict:
    """解析服务器会话信息.

    最小响应长度 87 字节.
    """
    if len(data) < 87:
        return {}

    count, = struct.unpack_from("<H", data, 0)
    pos = 22  # skip flags(8) + tag(3) + reserved(9)
    today_date, ts1, sessions_1_raw, sessions_2_raw, flag, \
        last_trading_day, ts2, market_param_1, market_param_2 = \
        struct.unpack_from("<II8H8HBII", data, pos)

    sessions_1 = []
    for i in range(4):
        open_min = sessions_1_raw[i * 2]
        close_min = sessions_1_raw[i * 2 + 1]
        sessions_1.append((open_min // 60, open_min % 60))
        if open_min == 0 and close_min == 0:
            sessions_1.pop()

    sessions_2 = []
    for i in range(4):
        open_min = sessions_2_raw[i * 2]
        close_min = sessions_2_raw[i * 2 + 1]
        sessions_2.append((open_min // 60, open_min % 60))
        if open_min == 0 and close_min == 0:
            sessions_2.pop()

    def _format_time(minutes: int) -> str:
        h = minutes // 60
        m = minutes % 60
        return f"{h:02d}:{m:02d}"

    def _parse_date(d: int) -> str:
        y = d // 10000
        mo = (d % 10000) // 100
        dy = d % 100
        return f"{y:04d}-{mo:02d}-{dy:02d}"

    return {
        "today_date": _parse_date(today_date),
        "last_trading_day": _parse_date(last_trading_day),
        "sessions_1": [_format_time(o) + "-" + _format_time(c) for o, c in sessions_1],
        "sessions_2": [_format_time(o) + "-" + _format_time(c) for o, c in sessions_2],
        "market_param_1": market_param_1,
        "market_param_2": market_param_2,
    }


# ============================================================
# SymbolInfoCmd — 个股详细信息 (cmd=0x122A)
# ============================================================

def _b_symbol_info(market: int, code: str) -> bytes:
    """构建个股详细信息请求.

    格式: <H22sI12x (40 字节)
    """
    if isinstance(code, str):
        code = code.encode("gbk")
    code_padded = code.ljust(22, b"\x00")
    payload = struct.pack("<H22sI12x", market, code_padded, 1)
    return payload


def _p_symbol_info(data: bytes) -> dict:
    """解析个股详细信息响应.

    核心字段偏移 96，额外字段偏移 148.
    """
    if len(data) < 158:
        return {}

    market, code_b, name_b = struct.unpack_from("<H22s44s", data, 8)
    code = code_b.decode("gbk", errors="replace").strip("\x00")
    name = name_b.decode("gbk", errors="replace").strip("\x00")

    date_raw, time_raw, activity, pre_close, open_, high, low, \
        close, momentum, vol, amount, inside_vol, outside_vol = \
        struct.unpack_from("<IIIffIfIIfff", data, 96)

    _, turnover, avg_price = struct.unpack_from("<HIf", data, 148)

    def _parse_dt(date_raw: int, time_raw: int) -> tuple[str, str]:
        dt_str = f"{date_raw // 10000:04d}-{(date_raw % 10000) // 100:02d}-{date_raw % 100:02d}"
        tm_str = f"{time_raw // 10000:02d}:{(time_raw % 10000) // 100:02d}:{time_raw % 100:02d}"
        return dt_str, tm_str

    dt_str, tm_str = _parse_dt(date_raw, time_raw)

    return {
        "market": market,
        "code": code,
        "name": name,
        "date": dt_str,
        "time": tm_str,
        "activity": activity,
        "pre_close": round(pre_close, 3),
        "open": round(open_, 3),
        "high": round(high, 3),
        "low": round(low, 3),
        "close": round(close, 3),
        "momentum": round(momentum, 3),
        "volume": vol,
        "amount": round(amount, 2),
        "inside_volume": inside_vol,
        "outside_volume": outside_vol,
        "turnover": round(turnover, 2),
        "avg_price": round(avg_price, 3),
    }
