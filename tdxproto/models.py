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


# ============================================================
# 板块相关数据模型
# ============================================================

@dataclass
class TdxBlock:
    """通达信 .dat 板块文件解析结果."""
    name: str = ""
    category: int = 0       # 0=行业, 2=概念, 3=风格
    count: int = 0           # 股票数量
    codes: list[str] = field(default_factory=list)


@dataclass
class BelongBoardInfo:
    """个股所属板块信息."""
    board_type: int = 0      # 板块类型
    market: int = 0          # 市场代码
    board_code: str = ""     # 板块代码
    board_name: str = ""     # 板块名称
    close: float = 0.0       # 收盘价
    pre_close: float = 0.0   # 昨收


@dataclass
class BoardMember:
    """板块成分股."""
    market: int = 0
    code: str = ""
    name: str = ""
    price: float = 0.0
    pre_close: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    volume: int = 0
    amount: float = 0.0
    rise_speed: float = 0.0
    main_net_amount: float = 0.0
    up_count: int = 0
    down_count: int = 0
    flat_count: int = 0
    amplitude: float = 0.0
    turnover_rate: float = 0.0


@dataclass
class BoardSummary:
    """板块汇总数据."""
    member_count: int = 0
    amount: float = 0.0
    vol: int = 0
    main_net_amount: float = 0.0
    up_count: int = 0
    down_count: int = 0
    flat_count: int = 0
    avg_price: float = 0.0


@dataclass
class BoardListItem:
    """板块列表项."""
    market: int = 0
    code: str = ""
    name: str = ""
    price: float = 0.0
    rise_speed: float = 0.0
    pre_close: float = 0.0
    symbol_market: int = 0
    symbol_code: str = ""
    symbol_name: str = ""
    symbol_price: float = 0.0
    symbol_rise_speed: float = 0.0
    total: int = 0


@dataclass
class BoardRankingItem:
    """板块排行项."""
    market: int = 0
    code: str = ""
    name: str = ""
    change_pct: float = 0.0
    pre_close: float = 0.0
    symbol_market: int = 0
    symbol_code: str = ""
    symbol_name: str = ""


# ============================================================
# 资金流向 / 市场统计 / 服务器信息 / 个股详情
# ============================================================

@dataclass
class CapitalFlowData:
    """个股资金流向数据."""
    main_in: float = 0.0       # 主力流入
    main_out: float = 0.0      # 主力流出
    main_net: float = 0.0      # 主力净额
    retail_in: float = 0.0     # 散户流入
    retail_out: float = 0.0    # 散户流出
    retail_net: float = 0.0    # 散户净额
    mid_net_5d: float = 0.0    # 中单5日净额
    large_net_5d: float = 0.0  # 大单5日净额


@dataclass
class MarketStat:
    """市场统计数据."""
    up_count: int = 0          # 上涨家数
    down_count: int = 0        # 下跌家数
    neutral_count: int = 0     # 平盘家数
    total_count: int = 0       # 总家数
    limit_up: int = 0          # 涨停家数
    limit_down: int = 0        # 跌停家数
    suspended_count: int = 0   # 停牌家数
    total_amount: float = 0.0  # 总市值(元)
    total_volume: float = 0.0  # 总成交量


@dataclass
class ServerSession:
    """服务器会话信息."""
    today_date: int = 0        # 今日日期 YYYYMMDD
    last_trading_day: int = 0  # 上次交易日 YYYYMMDD
    sessions_1: list[tuple[int, int]] = field(default_factory=list)  # 交易时段1 [(open, close), ...]
    sessions_2: list[tuple[int, int]] = field(default_factory=list)  # 交易时段2 [(open, close), ...]
    market_param_1: int = 0    # 市场参数1
    market_param_2: int = 0    # 市场参数2


@dataclass
class SymbolInfo:
    """个股详细信息."""
    market: int = 0
    code: str = ""
    name: str = ""
    date_raw: int = 0          # 日期 YYYYMMDD
    time_raw: int = 0          # 时间 HHMMSS
    activity: int = 0          # 活跃度
    pre_close: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    momentum: float = 0.0      # 动量
    volume: int = 0
    amount: float = 0.0
    inside_volume: int = 0     # 内盘
    outside_volume: int = 0    # 外盘
    turnover: float = 0.0      # 换手率
    avg_price: float = 0.0     # 均价
