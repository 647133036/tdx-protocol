"""中金所成交持仓排名采集客户端。

每个交易日收盘后约 16:15，中金所官网公布各期货品种「成交量 / 持买单量 / 持卖单量」
各前 20 名期货公司会员排名。

品种覆盖：IF 沪深300 / IH 上证50 / IC 中证500 / IM 中证1000
          TS/TF/T/TL 2/5/10/30 年期国债期货
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

from .models import CcpmError, CcpmNoDataError, CcpmProductMeta, MemberRank

logger = logging.getLogger(__name__)

_CCPM_URL_TEMPLATE = (
    "http://www.cffex.com.cn/sj/hqsj/ccpm/{yearmonth}/{day}/{product}.xml"
)
_CACHE_DIR = Path.home() / ".easy_tdx" / "cache" / "ccpm"
_ALLOWED_HOSTS = frozenset({"www.cffex.com.cn"})

PRODUCT_META: dict[str, CcpmProductMeta] = {
    "IF": CcpmProductMeta(code="IF", name="沪深300股指期货", underlying="CSI 300",
                          contract_size=300000, description="跟踪沪深300指数，每点300元"),
    "IH": CcpmProductMeta(code="IH", name="上证50股指期货", underlying="SSE 50",
                          contract_size=300000, description="跟踪上证50指数，每点300元"),
    "IC": CcpmProductMeta(code="IC", name="中证500股指期货", underlying="CSI 500",
                          contract_size=200000, description="跟踪中证500指数，每点200元"),
    "IM": CcpmProductMeta(code="IM", name="中证1000股指期货", underlying="CSI 1000",
                          contract_size=200000, description="跟踪中证1000指数，每点200元"),
    "TS": CcpmProductMeta(code="TS", name="2年期国债期货", underlying="2Y CGB",
                          contract_size=2000000, description="2年期利率期货，价格与利率反向"),
    "TF": CcpmProductMeta(code="TF", name="5年期国债期货", underlying="5Y CGB",
                          contract_size=1000000, description="5年期利率期货，价格与利率反向"),
    "T": CcpmProductMeta(code="T", name="10年期国债期货", underlying="10Y CGB",
                         contract_size=1000000, description="10年期利率期货，价格与利率反向"),
    "TL": CcpmProductMeta(code="TL", name="30年期国债期货", underlying="30Y CGB",
                          contract_size=1000000, description="30年期利率期货，价格与利率反向"),
}

_ALL_PRODUCTS = list(PRODUCT_META.keys())


def _xml_to_ranks(xml_text: str) -> dict[str, list[MemberRank]]:
    """解析中金所 XML，返回三个排名列表。"""
    result: dict[str, list[MemberRank]] = {
        "volume_rank": [],
        "long_rank": [],
        "short_rank": [],
    }
    current_section: Optional[str] = None
    for line in xml_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("<?xml") or stripped.startswith("<!--"):
            continue
        if "<成交量排名" in stripped or "<持仓量排名" in stripped:
            if "成交量" in stripped:
                current_section = "volume"
            elif "持买单量" in stripped:
                current_section = "long"
            elif "持卖单量" in stripped:
                current_section = "short"
            continue
        if stripped in ("</成交量排名>", "</持仓量排名>"):
            current_section = None
            continue
        if not stripped or not stripped.startswith("<"):
            continue
        if current_section == "volume" and stripped.startswith("<排名"):
            m = re.search(r'名次="(\d+)"[^>]*会员名称="([^"]+)"[^>]*成交量="(\d+)"', stripped)
            if m:
                result["volume_rank"].append(MemberRank(
                    rank=int(m.group(1)), member=m.group(2), volume=int(m.group(3)),
                ))
        elif current_section == "long" and stripped.startswith("<排名"):
            m = re.search(r'名次="(\d+)"[^>]*会员名称="([^"]+)"[^>]*持买单量="(\d+)"', stripped)
            if m:
                result["long_rank"].append(MemberRank(
                    rank=int(m.group(1)), member=m.group(2), long_pos=int(m.group(3)),
                ))
        elif current_section == "short" and stripped.startswith("<排名"):
            m = re.search(r'名次="(\d+)"[^>]*会员名称="([^"]+)"[^>]*持卖单量="(\d+)"', stripped)
            if m:
                result["short_rank"].append(MemberRank(
                    rank=int(m.group(1)), member=m.group(2), short_pos=int(m.group(3)),
                ))
    return result


def _fetch_xml(url: str) -> str:
    """抓取 XML，非交易日或无数据时返回空字符串。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return ""
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_HOSTS:
        return ""
    try:
        req = urlrequest.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; tdxproto/0.0.1)",
            "Accept": "*/*",
        })
        with urlrequest.urlopen(req, timeout=10) as resp:
            if resp.status in (302, 404):
                return ""
            return resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, OSError):
        return ""


def _cache_path(date_str: str, product: str) -> Path:
    return _CACHE_DIR / date_str / f"{product}.json"


def _load_cached(date_str: str, product: str) -> Optional[dict]:
    p = _cache_path(date_str, product)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _save_cached(date_str: str, product: str, data: dict) -> None:
    p = _cache_path(date_str, product)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")


def _prev_trading_days(n: int = 15) -> list[str]:
    """最近 n 个日历日（跳过周末）。"""
    today = date.today()
    days: list[str] = []
    for i in range(n):
        d = today - timedelta(days=i)
        if d.weekday() < 5:
            days.append(d.strftime("%Y-%m-%d"))
    return days


class CcpmClient:
    """中金所成交持仓排名采集客户端。

    用法::

        from tdxproto.ccpm import CcpmClient

        client = CcpmClient()
        ranks = client.get_rank("IF", date="2026-09-02")
        latest = client.latest_rank("IF")
        meta = client.get_products_meta()
    """

    def __init__(self, use_cache: bool = True, max_backtrack: int = 15):
        self._use_cache = use_cache
        self._max_backtrack = max_backtrack

    def get_rank(self, product: str, date: Optional[str] = None,
                 refresh: bool = False) -> dict:
        """获取指定品种指定日期的持仓排名。

        Args:
            product: 品种代码（IF/IH/IC/IM/TS/TF/T/TL），或 "all" 获取全部
            date: ISO 日期（YYYY-MM-DD），缺省取最近交易日
            refresh: 强制重抓，忽略缓存

        Returns:
            {"product": "...", "date": "...",
             "volume_rank": [...], "long_rank": [...], "short_rank": [...],
             "meta": {...}}

        Raises:
            CcpmNoDataError: 非交易日或数据未发布
            ValueError: product 不支持
        """
        if product == "all":
            return {p: self.get_rank(p, date=date, refresh=refresh)
                    for p in _ALL_PRODUCTS}

        if product not in PRODUCT_META:
            raise ValueError(f"不支持的品种 {product!r}，可选：{_ALL_PRODUCTS}")

        target_date = date or self._find_latest_date()
        if self._use_cache and not refresh:
            cached = _load_cached(target_date, product)
            if cached:
                return cached

        yearmonth = target_date.replace("-", "")[:6]
        day = target_date.replace("-", "")[6:]
        url = _CCPM_URL_TEMPLATE.format(yearmonth=yearmonth, day=day, product=product)
        xml_text = _fetch_xml(url)
        if not xml_text:
            raise CcpmNoDataError(
                f"{product} 在 {target_date} 无数据（非交易日或未发布）"
            )

        ranks = _xml_to_ranks(xml_text)
        result = {
            "product": product,
            "date": target_date,
            "fetched_at": datetime.now().isoformat(),
            "volume_rank": [r.to_dict() for r in ranks["volume_rank"]],
            "long_rank": [r.to_dict() for r in ranks["long_rank"]],
            "short_rank": [r.to_dict() for r in ranks["short_rank"]],
            "meta": PRODUCT_META[product].to_dict(),
        }
        _save_cached(target_date, product, result)
        return result

    def latest_rank(self, product: str) -> dict:
        """自动回溯最近交易日，获取最新可用数据（最多回溯 max_backtrack 天）。"""
        if product == "all":
            return {p: self.latest_rank(p) for p in _ALL_PRODUCTS}

        if product not in PRODUCT_META:
            raise ValueError(f"不支持的品种 {product!r}")

        for d in _prev_trading_days(self._max_backtrack):
            try:
                return self.get_rank(product, date=d)
            except CcpmNoDataError:
                continue
        raise CcpmNoDataError(f"{product} 最近 {self._max_backtrack} 个交易日均无数据")

    def _find_latest_date(self) -> str:
        """找最近有数据的交易日。"""
        for d in _prev_trading_days(15):
            try:
                self.get_rank("IF", date=d)
                return d
            except CcpmNoDataError:
                continue
        return str(date.today())

    def get_products_meta(self) -> dict[str, dict]:
        """返回所有品种的元数据（标的/合约规模/一句话科普）。"""
        return {k: v.to_dict() for k, v in PRODUCT_META.items()}
