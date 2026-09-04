"""港股实时报价 — 腾讯行情接口.

数据源：腾讯行情 API (qt.gtimg.cn), 零依赖纯标准库实现。
格式与 A 股腾讯格式一致，仅 code 前缀为 "hk"。
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

__all__ = ["HkClient", "HkQuote"]

_QT_URL = "https://qt.gtimg.cn/q={codes}"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://xueqiu.com/",
    "Accept": "text/html,application/xhtml+xml",
}


@dataclass
class HkQuote:
    """港股实时报价."""

    code: str
    name: str
    price: float
    pre_close: float
    open: float
    high: float
    low: float
    volume: int
    amount: float
    change_pct: float
    change_amt: float
    turnover_pct: float
    time: str
    currency: str = "HKD"
    bid_p: list[float] = None  # type: ignore[assignment]
    bid_v: list[int] = None  # type: ignore[assignment]
    ask_p: list[float] = None  # type: ignore[assignment]
    ask_v: list[int] = None  # type: ignore[assignment]
    year_high: float = 0.0
    year_low: float = 0.0
    pe: float = 0.0
    eps: float = 0.0


def _fetch(code_list: list[str]) -> bytes:
    raw_codes = ",".join(code_list)
    url = _QT_URL.format(codes=raw_codes)
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read()


_FIELD_RE = re.compile(r'^v_(\w+)="(.*)";?\s*$')


def _parse_response(raw: bytes) -> dict[str, list[str]]:
    text = raw.decode("gbk", errors="ignore")
    result: dict[str, list[str]] = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = _FIELD_RE.match(line)
        if m:
            sym = m.group(1).lower()
            fields = m.group(2).split("~")
            result[sym] = fields
    return result


def _safe_float(v: str, default: float = 0.0) -> float:
    try:
        f = float(v)
        if f != f or f in (float("inf"), float("-inf")):
            return default
        return f
    except (ValueError, TypeError, OverflowError):
        return default


def _safe_int(v: str, default: int = 0) -> int:
    try:
        f = float(v)
        if f != f or f in (float("inf"), float("-inf")):
            return default
        return int(f)
    except (ValueError, TypeError, OverflowError):
        return default


_TIME_RE = re.compile(r'^\d{4}/\d{2}/\d{2} ')


def _find_time_idx(fields: list[str]) -> int:
    """在字段列表中查找时间字段索引（YYYY/MM/DD HH:MM:SS 格式）."""
    for i, f in enumerate(fields):
        if _TIME_RE.match(f):
            return i
    return -1


def _parse_fields(fields: list[str], code: str) -> Optional[HkQuote]:
    """解析腾讯港股字段列表为 HkQuote.

    字段位置使用相对定位：以 time 字段（YYYY/MM/DD HH:MM:SS）为锚点，
    向前/向后推导其余字段，避免固定索引在格式波动时失效。

    锚点相对位置（相对 time_idx）：
    -1: volume（第一次出现）
    0: time
    +1: amplitude
    +2: change_pct
    +3: high
    +4: low
    +5: close
    +6: volume（重复）
    +7: amount
    +9: turnover_pct
    +13: pe_ttm
    +16: english_name
    +18: year_high
    +19: year_low
    +45: currency (HKD/USD)
    """
    if len(fields) < 48:
        return None
    status = _safe_int(fields[0])
    if status != 100:
        return None

    t_idx = _find_time_idx(fields)
    if t_idx < 0 or t_idx + 6 >= len(fields):
        return None

    return HkQuote(
        code=code,
        name=fields[1],
        price=_safe_float(fields[3]),
        pre_close=_safe_float(fields[4]),
        open=_safe_float(fields[5]),
        high=_safe_float(fields[t_idx + 3]) if t_idx + 3 < len(fields) else 0.0,
        low=_safe_float(fields[t_idx + 4]) if t_idx + 4 < len(fields) else 0.0,
        volume=_safe_int(fields[t_idx + 6]) if t_idx + 6 < len(fields) else 0,
        amount=_safe_float(fields[t_idx + 7]) if t_idx + 7 < len(fields) else 0.0,
        change_pct=_safe_float(fields[t_idx + 2]) if t_idx + 2 < len(fields) else 0.0,
        change_amt=round(_safe_float(fields[3]) - _safe_float(fields[4]), 4),
        turnover_pct=_safe_float(fields[t_idx + 9]) if t_idx + 9 < len(fields) else 0.0,
        time=fields[t_idx],
        currency=fields[t_idx + 45] if t_idx + 45 < len(fields) else "HKD",
        bid_p=[],
        bid_v=[],
        ask_p=[],
        ask_v=[],
        year_high=_safe_float(fields[t_idx + 18]) if t_idx + 18 < len(fields) else 0.0,
        year_low=_safe_float(fields[t_idx + 19]) if t_idx + 19 < len(fields) else 0.0,
        pe=_safe_float(fields[t_idx + 13]) if t_idx + 13 < len(fields) else 0.0,
        eps=0.0,
    )


def _normalize_code(code: str | None) -> str | None:
    if not code:
        return None
    code = code.strip().lower()
    if not code:
        return None
    if not code.startswith("hk"):
        code = "hk" + code
    return code


class HkClient:
    """港股行情客户端 — 基于腾讯接口.

    使用示例：
        from tdxproto import HkClient
        client = HkClient()
        q = client.quote("00700")
        print(q.name, q.price)

        # 批量
        batch = client.quote_batch(["00700", "09988", "01810"])
        for code, q in batch.items():
            print(code, q.name, q.price)
    """

    def quote(self, code: str) -> Optional[HkQuote]:
        """获取单只港股实时报价."""
        norm = _normalize_code(code)
        if not norm:
            return None
        raw = _fetch([norm])
        parsed = _parse_response(raw)
        fields = parsed.get(norm, [])
        return _parse_fields(fields, norm[2:]) if fields else None

    def quote_batch(
        self, codes: list[str], max_batch_size: int = 80
    ) -> dict[str, HkQuote]:
        """批量获取港股报价."""
        normalized = [_normalize_code(c) for c in codes]
        normalized = [n for n in normalized if n]
        result: dict[str, HkQuote] = {}
        for i in range(0, len(normalized), max_batch_size):
            chunk = normalized[i : i + max_batch_size]
            raw = _fetch(chunk)
            parsed = _parse_response(raw)
            for sym, fields in parsed.items():
                quote = _parse_fields(fields, sym[2:])
                if quote:
                    result[sym] = quote
        return result
