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
        if eq.date is None or eq.category != 1:
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


def verify_qfq(bars: list[Kline], equity: list[EquityChange]) -> dict:
    """QFQ 交叉验证：formula 计算 vs gap 检测，结果一致才采信。

    Args:
        bars: 不复权 K 线（按时间正序）
        equity: 除权除息事件列表

    Returns:
        {
            "formula_factors": {date_str: factor, ...},  # 公式法因子
            "gap_events": [(date_str, gap_ratio), ...],  # gap 检测到的除权缺口
            "match": True/False,                          # 两种方法是否一致
            "details": {...},
        }
    """
    from datetime import datetime as dt

    # --- 方法一：公式法 ---
    factors = compute_factors(bars, equity, adjust="qfq")
    formula_factors = {str(d): round(f, 6) for d, f in sorted(factors.items())}

    # --- 方法二：gap 检测法 ---
    # 检测相邻 bar 之间的价格跳空（gap），反推复权因子
    gap_events: list[tuple[str, float]] = []
    b_sorted = sorted(bars, key=lambda b: b.time)
    for i in range(1, len(b_sorted)):
        prev_close = b_sorted[i - 1].close
        curr_open = b_sorted[i].open
        if prev_close > 0 and curr_open > 0:
            gap_ratio = curr_open / prev_close
            # 正常交易 gap 通常在 0.97~1.03 之间
            # 除权日 gap 通常超过这个范围
            if gap_ratio < 0.95 or gap_ratio > 1.05:
                d = b_sorted[i].time
                gap_events.append((d, round(gap_ratio, 6)))

    # --- 交叉验证 ---
    match = True
    details: dict = {}
    if gap_events:
        # 用 gap 检测结果估算因子
        gap_factors: dict[str, float] = {}
        running_factor = 1.0
        for d, ratio in reversed(gap_events):
            # gap_ratio = curr_open / prev_close，除权后 open 会比 prev_close 低
            # 复权因子 ≈ 1 / gap_ratio（对于 qfq，前复权放大旧价格）
            running_factor /= ratio
            gap_factors[d] = round(running_factor, 6)

        # 对比公式法与 gap 法在相同日期的因子
        common_dates = set(formula_factors.keys()) & set(gap_factors.keys())
        mismatches = []
        for d in sorted(common_dates):
            f1 = formula_factors[d]
            f2 = gap_factors[d]
            if abs(f1 - f2) > 0.01:  # 允许 1% 误差
                mismatches.append({"date": d, "formula": f1, "gap": f2})

        match = len(mismatches) == 0
        details = {
            "formula_factors": formula_factors,
            "gap_events": gap_events,
            "gap_factors": gap_factors,
            "mismatches": mismatches,
        }
    else:
        details = {
            "formula_factors": formula_factors,
            "gap_events": [],
            "reason": "未检测到除权缺口，仅采信公式法",
        }

    return {
        "formula_factors": formula_factors,
        "gap_events": gap_events,
        "match": match,
        "details": details,
    }


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
    # float_shares 单位: 万股, volume 单位: 股
    return volume / (float_shares * 10000) * 100


def parse_xdxr(equity: list[EquityChange]) -> list[dict]:
    """解析除权除息事件。"""
    events = []
    for e in sorted(equity, key=lambda x: x.date or date.min, reverse=True):
        if e.category == 1 and e.date:
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
