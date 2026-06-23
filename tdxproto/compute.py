"""本地计算引擎 — 不依赖服务端的衍生数据计算。

功能:
  - 复权因子: 基于不复权日K + 除权除息记录计算前/后复权因子
  - 换手率: 成交量 / 流通股本
  - 除权除息解析: 从股本变迁记录解析分红送转配股
  - 指定日股本: 从股本变迁回溯任意日期的股本
  - 09:25 竞价快照: 从历史成交明细扫描竞价最终成交
"""

from datetime import date
from typing import Optional

from .models import Kline, EquityChange, FinanceInfo


def compute_factors(bars: list[Kline], equity: list[EquityChange],
                    adjust: str = "qfq") -> dict[date, float]:
    """计算本地复权因子。

    返回 {除权日: 累计因子}。使用日K线数据校验准确性。
    """
    bmap = {date(int(b.time[:4]), int(b.time[4:6]), int(b.time[6:8])): b for b in bars}
    eq_sorted = sorted([e for e in equity if e.date], key=lambda e: e.date or date.min, reverse=True)
    factor = 1.0
    factors: dict[date, float] = {}

    for eq in eq_sorted:
        if eq.date is None or eq.category != "除权除息":
            continue
        close_before = bmap.get(eq.date)
        if not close_before or close_before.close == 0:
            continue
        # 除权比例 = (前收盘 + 分红 - 配股价*配股)/(前收盘 + 送转 + 配股)
        denominator = close_before.close + eq.rights + eq.placement
        numerator = close_before.close + eq.bonus - eq.placement * eq.placement_price
        if denominator > 0:
            ratio = numerator / denominator
            if adjust == "qfq":
                factor *= ratio
            else:
                factor /= ratio
        factors[eq.date] = factor

    return factors


def get_equity_at(equity: list[EquityChange], target_date: date) -> tuple[float, float]:
    """获取指定日期的流通股本和总股本 (回溯最近一次变更)。"""
    changes = sorted(
        [e for e in equity if e.date and e.date <= target_date],
        key=lambda e: e.date or date.min, reverse=True
    )
    for c in changes:
        if c.float_shares > 0 or c.total_shares > 0:
            return c.float_shares, c.total_shares
    return 0.0, 0.0


def calc_turnover(volume: int, float_shares: float) -> float:
    """计算换手率 (百分比)。"""
    if float_shares <= 0:
        return 0.0
    return volume / (float_shares * 100) * 100  # float_shares 单位万, volume 单位股


def parse_xdxr(equity: list[EquityChange]) -> list[dict]:
    """解析除权除息事件。"""
    events = []
    for e in sorted(equity, key=lambda x: x.date or date.min, reverse=True):
        if e.category == "除权除息" and e.date:
            events.append({
                "date": str(e.date),
                "bonus_per_share": e.bonus,
                "rights_per_share": e.rights,
                "placement_per_share": e.placement,
                "placement_price": e.placement_price,
            })
    return events


def auction_0925(trades: list["Trade"]) -> Optional[dict]:
    """从历史成交明细扫描 09:25 竞价最终成交。"""
    for t in trades:
        if t.time == "09:25":
            return {
                "time": t.time, "price": t.price,
                "volume": t.volume, "direction": t.direction,
            }
    return None
