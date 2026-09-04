"""A 股交易时段判断与最近交易日锚定。"""

from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta
from typing import Optional

AUCTION_OPEN = dt_time(9, 15)
MARKET_OPEN = dt_time(9, 30)
MORNING_CLOSE = dt_time(11, 30)
AFTERNOON_OPEN = dt_time(13, 0)
MARKET_CLOSE = dt_time(15, 0)

_MINUTE_LABELS: list[str] | None = None


def _now(now: Optional[datetime] = None) -> datetime:
    return now if now is not None else datetime.now()


def prev_weekday(d: date) -> date:
    d = d - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def last_session_date(now: Optional[datetime] = None) -> date:
    """最近一个应已开盘或已收盘的日历交易日（跳过周末；节假日由上层回溯）。"""
    now = _now(now)
    d = now.date()
    if d.weekday() >= 5:
        return prev_weekday(d)
    if now.time() < MARKET_OPEN:
        return prev_weekday(d)
    return d


def should_use_realtime_minute(now: Optional[datetime] = None) -> bool:
    """工作日 09:30 起使用当日分时命令。"""
    now = _now(now)
    return now.weekday() < 5 and now.time() >= MARKET_OPEN


def in_trading(now: Optional[datetime] = None) -> bool:
    now = _now(now)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (MARKET_OPEN <= t <= MORNING_CLOSE) or (AFTERNOON_OPEN <= t <= MARKET_CLOSE)


def in_auction(now: Optional[datetime] = None) -> bool:
    now = _now(now)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return AUCTION_OPEN <= t < MARKET_OPEN


def session_status(now: Optional[datetime] = None) -> str:
    now = _now(now)
    if now.weekday() >= 5:
        return "weekend"
    t = now.time()
    if t < AUCTION_OPEN:
        return "pre_market"
    if t < MARKET_OPEN:
        return "auction"
    if t <= MORNING_CLOSE:
        return "morning"
    if t < AFTERNOON_OPEN:
        return "lunch"
    if t <= MARKET_CLOSE:
        return "afternoon"
    return "closed"


def ashare_minute_labels(n: int = 240) -> list[str]:
    """连续竞价 240 根分时标签：09:31-11:30 + 13:01-15:00。"""
    global _MINUTE_LABELS
    if _MINUTE_LABELS is None:
        labels: list[str] = []
        h, m = 9, 31
        for _ in range(120):
            labels.append(f"{h:02d}:{m:02d}")
            m += 1
            if m >= 60:
                h += 1
                m = 0
        h, m = 13, 1
        for _ in range(120):
            labels.append(f"{h:02d}:{m:02d}")
            m += 1
            if m >= 60:
                h += 1
                m = 0
        _MINUTE_LABELS = labels
    if n <= 240:
        return _MINUTE_LABELS[:n]
    extra = []
    h, m = 15, 1
    for _ in range(n - 240):
        extra.append(f"{h:02d}:{m:02d}")
        m += 1
        if m >= 60:
            h += 1
            m = 0
    return _MINUTE_LABELS + extra


def stamp_minute_times(rows: list[dict]) -> list[dict]:
    if not rows:
        return rows
    labels = ashare_minute_labels(len(rows))
    for i, row in enumerate(rows):
        if not row.get("minute"):
            row["minute"] = labels[i]
    return rows


def filter_minute_placeholders(rows: list[dict]) -> list[dict]:
    """去掉盘前/收盘后价格为 0 的占位脏数据。"""
    if not rows:
        return rows
    start = 0
    end = len(rows)
    while start < end and float(rows[start].get("price") or 0) <= 0:
        start += 1
    while end > start and float(rows[end - 1].get("price") or 0) <= 0:
        end -= 1
    return rows[start:end]
