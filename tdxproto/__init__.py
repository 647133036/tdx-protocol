"""通达信全协议解析器 (7709 股票 + 7727 期货)。

纯 Python 二进制协议实现，零外部依赖。

架构:
  tube.py      — 协议无关的 TCP 传输管道
  frame.py     — 二进制帧编解码
  codec.py     — varint/f32/date/volume/代码标准化
  models.py    — 统一数据模型 (Quote/Kline/Minute/Trade/EquityChange/FinanceInfo/PriceLimit)
  compute.py   — 本地计算引擎 (复权因子/换手率/除权除息/竞价快照)
  scanner.py   — 主站可用性探测与测速 (TCP + 协议握手)
  hosts.py     — 主站地址表 (A股43+个, 期货16+个)
  stock/       — 7709 股票 (19 个命令完整覆盖)
  futures/     — 7727 期货 (12 个命令完整覆盖)
"""

from .codec import classify, normalize_code, date_int, int_date
from .models import Quote, Kline, Minute, Trade, EquityChange, FinanceInfo, PriceLimit
from .compute import compute_factors, get_equity_at, calc_turnover, parse_xdxr, auction_0925
from .stock import StockClient
from .futures import FuturesClient
from .scanner import (
    scan_stock, scan_futures, best_host, ProbeResult,
    DEFAULT_TIMEOUT, DEFAULT_WORKERS,
)
from .hosts import (
    STOCK_HOSTS_FAST, STOCK_HOSTS_LARGE,
    FUTURES_HOSTS_FAST, FUTURES_HOSTS_LARGE,
)

__version__ = "1.1.0"
__all__ = [
    "StockClient", "FuturesClient",
    "Quote", "Kline", "Minute", "Trade",
    "EquityChange", "FinanceInfo", "PriceLimit",
    "compute_factors", "get_equity_at", "calc_turnover", "parse_xdxr", "auction_0925",
    "classify", "normalize_code",
    "scan_stock", "scan_futures", "best_host", "ProbeResult",
    "DEFAULT_TIMEOUT", "DEFAULT_WORKERS",
    "STOCK_HOSTS_FAST", "STOCK_HOSTS_LARGE",
    "FUTURES_HOSTS_FAST", "FUTURES_HOSTS_LARGE",
]
