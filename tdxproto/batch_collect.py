"""批量采集管线 — 期货/美股、股票分时/成交、F10、巨潮、中金所、MAC。"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .export import to_dict, to_parquet

_MARKET_ALIASES = {"sz": 0, "sh": 1, "bj": 2}
_SAFE_NAME = str.maketrans("", "", "/\\:*?\"<>|")


@dataclass
class ItemResult:
    key: str
    data: Any = None
    error: Optional[str] = None


def _code_market(code: str, fallback: int = 0) -> int:
    raw = str(code).strip().lower()
    if raw.startswith("sh"):
        return 1
    if raw.startswith("sz"):
        return 0
    if raw.startswith("bj"):
        return 2
    return fallback


def _code6(code: str) -> str:
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    return digits[-6:] if len(digits) >= 6 else digits


def _safe_stem(name: str) -> str:
    return "".join(ch for ch in str(name) if ch.isalnum() or ch in "-_.") or "item"


def _us_code(code: str) -> str:
    raw = str(code).strip()
    if raw.startswith("us") and len(raw) > 2:
        return raw[2:]
    return raw


def _split_market_code(raw: str, default_market: int) -> tuple[int, str]:
    text = str(raw).strip()
    if ":" in text:
        mid_s, code = text.split(":", 1)
        return int(mid_s), _us_code(code)
    return default_market, _us_code(text)


def collect_parallel(
    items: list[str],
    worker: Callable[[str], Any],
    max_workers: int = 8,
    timeout: float = 30.0,
) -> list[ItemResult]:
    if not items:
        return []
    workers = max(1, min(max_workers, len(items)))
    results: dict[int, ItemResult] = {}

    def run(idx: int, key: str) -> tuple[int, ItemResult]:
        try:
            return idx, ItemResult(key=key, data=worker(key))
        except Exception as e:
            return idx, ItemResult(key=key, error=str(e))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(run, i, key): i for i, key in enumerate(items)}
        for fut in as_completed(futs):
            idx = futs[fut]
            try:
                _, result = fut.result(timeout=timeout)
                results[idx] = result
            except Exception as e:
                results[idx] = ItemResult(key=items[idx], error=str(e))
    return [results[i] for i in range(len(items))]


def results_payload(results: list[ItemResult], flatten: bool = False) -> Any:
    if not flatten:
        rows = []
        for r in results:
            entry = {"code": r.key, "data": to_dict(r.data)}
            if r.error:
                entry["error"] = r.error
            rows.append(entry)
        return rows
    rows = []
    for r in results:
        if r.error:
            rows.append({"code": r.key, "error": r.error})
            continue
        data = to_dict(r.data)
        if isinstance(data, list):
            if not data:
                rows.append({"code": r.key})
                continue
            for item in data:
                row = dict(item) if isinstance(item, dict) else {"value": item}
                row["code"] = r.key
                rows.append(row)
        elif isinstance(data, dict):
            row = dict(data)
            row["code"] = r.key
            rows.append(row)
        else:
            rows.append({"code": r.key, "value": data})
    return rows


def dump_output(data: Any, output_dir: str, stem: str, fmt: str = "json") -> str:
    os.makedirs(output_dir, exist_ok=True)
    records = to_dict(data)
    name = _safe_stem(stem)
    if fmt == "csv":
        from .export import to_csv_string
        path = os.path.join(output_dir, f"{name}.csv")
        with open(path, "w", encoding="utf-8") as f:
            f.write(to_csv_string(records))
        return path
    if fmt == "parquet":
        path = os.path.join(output_dir, f"{name}.parquet")
        to_parquet(records, path)
        return path
    path = os.path.join(output_dir, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2, default=str)
    return path


def dump_results(
    results: list[ItemResult],
    output_dir: str,
    stem: str,
    fmt: str = "json",
    flatten: bool = False,
    per_file: bool = False,
) -> dict[str, Any]:
    payload = results_payload(results, flatten=flatten)
    path = dump_output(payload, output_dir, stem, fmt)
    saved = 0
    skipped = 0
    if per_file:
        for r in results:
            if r.error or r.data in (None, [], {}):
                skipped += 1
                continue
            dump_output(to_dict(r.data), output_dir, r.key, "json")
            saved += 1
    return {"path": path, "count": len(results), "saved": saved, "skipped": skipped}


def collect_futures_kline(
    codes: list[str],
    market: int = 47,
    period: str = "day",
    start: int = 0,
    count: int = 100,
    max_workers: int = 16,
    timeout: float = 8.0,
) -> list[ItemResult]:
    from .futures import FuturesClient

    def worker(raw: str):
        mid = market
        code = raw
        if ":" in raw:
            mid_s, code = raw.split(":", 1)
            mid = int(mid_s)
        with FuturesClient(timeout=timeout) as c:
            return c.kline(mid, code, period, start, count)

    return collect_parallel(codes, worker, max_workers=max_workers, timeout=timeout * 3)


def collect_us_quote(
    codes: list[str],
    market: int = 74,
    max_workers: int = 16,
    timeout: float = 8.0,
) -> list[ItemResult]:
    from .futures import FuturesClient

    def worker(raw: str):
        mid, code = _split_market_code(raw, market)
        with FuturesClient(timeout=timeout) as c:
            return c.quote(mid, code)

    return collect_parallel(codes, worker, max_workers=max_workers, timeout=timeout * 3)


def collect_us_kline(
    codes: list[str],
    market: int = 74,
    period: str = "day",
    start: int = 0,
    count: int = 100,
    max_workers: int = 16,
    timeout: float = 8.0,
) -> list[ItemResult]:
    from .futures import FuturesClient

    def worker(raw: str):
        mid, code = _split_market_code(raw, market)
        with FuturesClient(timeout=timeout) as c:
            return c.kline(mid, code, period, start, count)

    return collect_parallel(codes, worker, max_workers=max_workers, timeout=timeout * 3)


def collect_us_minute(
    codes: list[str],
    market: int = 74,
    date: str | None = None,
    max_workers: int = 16,
    timeout: float = 8.0,
) -> list[ItemResult]:
    from .futures import FuturesClient

    def worker(raw: str):
        mid, code = _split_market_code(raw, market)
        with FuturesClient(timeout=timeout) as c:
            if date:
                return c.history_minute(mid, code, date)
            return c.today_minute(mid, code)

    return collect_parallel(codes, worker, max_workers=max_workers, timeout=timeout * 3)


def collect_us_trade(
    codes: list[str],
    market: int = 74,
    date: str | None = None,
    start: int = 0,
    count: int = 100,
    max_workers: int = 16,
    timeout: float = 8.0,
) -> list[ItemResult]:
    from .futures import FuturesClient

    def worker(raw: str):
        mid, code = _split_market_code(raw, market)
        with FuturesClient(timeout=timeout) as c:
            if date:
                return c.history_trade(mid, code, date, start, count)
            return c.today_trade(mid, code, start, count)

    return collect_parallel(codes, worker, max_workers=max_workers, timeout=timeout * 3)


def collect_stock_minute(
    codes: list[str],
    date: str | None = None,
    max_workers: int = 16,
    timeout: float = 5.0,
) -> list[ItemResult]:
    from .stock import StockClient

    def worker(code: str):
        with StockClient(timeout=timeout, auto_reconnect=False) as c:
            if date:
                return c.history_minute(code, date)
            return c.recent_minute(code)

    return collect_parallel(codes, worker, max_workers=max_workers, timeout=timeout * 3)


def collect_stock_trade(
    codes: list[str],
    date: str | None = None,
    start: int = 0,
    count: int = 100,
    max_workers: int = 16,
    timeout: float = 5.0,
) -> list[ItemResult]:
    from .stock import StockClient

    def worker(code: str):
        with StockClient(timeout=timeout, auto_reconnect=False) as c:
            if date:
                return c.history_trade(code, date, start, count)
            return c.today_trade(code, start, count)

    return collect_parallel(codes, worker, max_workers=max_workers, timeout=timeout * 3)


def collect_info_snapshot(
    codes: list[str],
    max_workers: int = 8,
    timeout: float = 15.0,
) -> list[ItemResult]:
    from .info import InfoCollector

    def worker(code: str):
        col = InfoCollector()
        return col.snapshot(_code_market(code), _code6(code))

    return collect_parallel(codes, worker, max_workers=max_workers, timeout=timeout)


def collect_cninfo(
    codes: list[str],
    count: int = 10,
    page: int = 1,
    keyword: str = "",
    max_workers: int = 8,
    timeout: float = 20.0,
) -> list[ItemResult]:
    from .cninfo import CninfoClient

    def worker(code: str):
        client = CninfoClient(timeout=timeout)
        return client.get_announcements(_code6(code), count=count, page=page, searchkey=keyword)

    return collect_parallel(codes, worker, max_workers=max_workers, timeout=timeout)


def collect_ccpm(
    products: list[str],
    date: str | None = None,
    latest: bool = True,
    refresh: bool = False,
    max_workers: int = 4,
    timeout: float = 20.0,
) -> list[ItemResult]:
    from .ccpm import CcpmClient
    from .ccpm.client import _ALL_PRODUCTS

    keys = products
    if not keys or keys == ["all"]:
        keys = list(_ALL_PRODUCTS)

    def worker(product: str):
        client = CcpmClient()
        if latest and not date:
            return client.latest_rank(product)
        return client.get_rank(product, date=date, refresh=refresh)

    return collect_parallel(keys, worker, max_workers=max_workers, timeout=timeout)


def collect_mac_boards(
    board_type: int = 0,
    page_size: int = 150,
    timeout: float = 8.0,
) -> list[ItemResult]:
    from .mac.client import MacClient

    try:
        with MacClient(timeout=timeout) as c:
            data = c.board_list(page_size=page_size, board_type=board_type)
        return [ItemResult(key=f"boards-{board_type}", data=data)]
    except Exception as e:
        return [ItemResult(key=f"boards-{board_type}", error=str(e))]


def collect_mac_flow(
    codes: list[str],
    max_workers: int = 4,
    timeout: float = 8.0,
) -> list[ItemResult]:
    from .mac.client import MacClient

    def worker(code: str):
        with MacClient(timeout=timeout) as c:
            return c.capital_flow(_code_market(code), _code6(code))

    return collect_parallel(codes, worker, max_workers=max_workers, timeout=timeout * 3)
