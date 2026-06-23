"""统一数据模型 — 跨股票/期货/ETF 共用。

所有行情数据归于 4 种基础结构:
  Quote   — 快照 + 五档盘口
  Kline   — OHLCV + 成交额
  Minute  — 分时点序列
  Trade   — 逐笔成交

及 3 种公司数据结构:
  Equity  — 股本变迁
  Finance — 财务基础
  Limit   — 涨跌停限制

期货特有字段 (position, settlement, nature) 整合进基础结构，
不做派生类。用 Optional 表达协议差异。
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class Quote:
    code: str
    market: str = ""
    name: str = ""
    price: float = 0.0
    pre_close: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    volume: int = 0
    amount: float = 0.0
    change_pct: float = 0.0
    bid_p: list[float] = field(default_factory=lambda: [0.0] * 5)
    bid_v: list[int] = field(default_factory=lambda: [0] * 5)
    ask_p: list[float] = field(default_factory=lambda: [0.0] * 5)
    ask_v: list[int] = field(default_factory=lambda: [0] * 5)
    # 期货特有
    open_interest: int = 0
    # 股票特有
    inner_vol: int = 0
    outer_vol: int = 0
    raw: bytes = b""


@dataclass
class Kline:
    time: str
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    amount: float = 0.0
    position: int = 0       # 期货持仓量
    settlement: float = 0.0  # 期货结算价


@dataclass
class Minute:
    time: str
    price: float = 0.0
    volume: int = 0
    avg_price: float = 0.0
    open_interest: int = 0


@dataclass
class Trade:
    time: str
    price: float = 0.0
    volume: int = 0
    direction: str = ""
    order_count: int = 0
    nature: str = ""        # 期货: 多开/空开/...
    zeng_cang: int = 0      # 期货: 增仓


@dataclass
class EquityChange:
    date: Optional[date] = None
    category: str = ""
    float_shares: float = 0.0
    total_shares: float = 0.0
    bonus: float = 0.0       # 每股分红
    rights: float = 0.0      # 每股送转
    placement: float = 0.0   # 每股配股
    placement_price: float = 0.0  # 配股价


@dataclass
class FinanceInfo:
    code: str = ""
    exchange: str = ""
    float_shares: float = 0.0
    total_shares: float = 0.0
    eps: float = 0.0
    bvps: float = 0.0        # 每股净资产
    revenue: float = 0.0
    profit: float = 0.0
    net_profit: float = 0.0
    total_assets: float = 0.0
    net_assets: float = 0.0
    ipo_date: Optional[date] = None
    updated: Optional[date] = None


@dataclass
class PriceLimit:
    code: str = ""
    exchange: str = ""
    upper: float = 0.0
    lower: float = 0.0
