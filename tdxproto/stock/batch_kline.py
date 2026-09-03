"""批量 K 线采集模块 — 对标 easy_tdx 采集管线。

性能目标:
  - 6000 只股票日 K 线 ≤ 8 分钟 (easy_tdx 基准)
  - 支持并发采集、自动故障转移、断线自愈

设计要点:
  1. 多连接并发：每个工作线程独立连接，避免单连接串行瓶颈
  2. 故障转移：单股票失败时自动切换主机
  3. 速率控制：全局并发数限制，避免触发服务器限流
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Optional

from .client import StockClient
from ..models import Kline
from ..hosts import STOCK_HOSTS_LARGE as STOCK_HOSTS
from ..scanner import scan_stock

logger = logging.getLogger(__name__)


@dataclass
class BatchResult:
    """单只股票采集结果."""
    code: str
    bars: list[Kline]
    error: Optional[str] = None
    host: Optional[str] = None


def collect_single_kline(
    code: str,
    period: str,
    client: StockClient,
    max_retries: int = 2,
) -> BatchResult:
    """采集单只股票的日 K 线（带故障转移和重试）."""
    for attempt in range(max_retries + 1):
        try:
            bars = client.kline_all(code, period)
            if bars:
                return BatchResult(
                    code=code,
                    bars=bars,
                    error=None,
                    host=client._current_host,
                )
            # 空数据但无错误：可能是该股票不存在，直接返回
            return BatchResult(code=code, bars=[], error=None)
        except Exception as e:
            if attempt < max_retries:
                logger.debug("采集 %s 失败 (attempt %d): %s", code, attempt + 1, e)
                # 尝试重连
                try:
                    client.connect()
                except Exception:
                    pass
            else:
                logger.warning("采集 %s 最终失败: %s", code, e)
                return BatchResult(code=code, bars=[], error=str(e))
    return BatchResult(code=code, bars=[], error="max retries exceeded")


def collect_batch_kline(
    codes: list[str],
    period: str = "day",
    max_workers: int = 32,
    reuse_client: bool = False,
    failover: bool = True,
    timeout_per_stock: float = 5.0,
    hosts_list: Optional[list[str]] = None,
) -> list[BatchResult]:
    """批量采集多只股票的日 K 线数据。

    Args:
        codes: 股票代码列表
        period: K 线周期，默认 "day"
        max_workers: 最大并发数，默认 32
        reuse_client: 是否复用同一连接，默认 False
        failover: 是否启用故障转移（空数据时自动切换主机），默认 True
        timeout_per_stock: 单只股票超时时间（秒）

    Returns:
        采集结果列表，每项包含股票代码、K 线数据和错误信息
    """
    if not codes:
        return []

    total = len(codes)
    logger.info("开始批量采集 %d 只股票，并发数: %d", total, max_workers)

    t0 = time.time()

    def collect_single(code: str, client: StockClient) -> BatchResult:
        """采集单只股票（单页，无 failover）."""
        try:
            bars = client.kline(code, period, failover=failover)
            if bars:
                return BatchResult(
                    code=code,
                    bars=bars,
                    error=None,
                    host=client._current_host,
                )
            return BatchResult(code=code, bars=[], error=None)
        except Exception as e:
            logger.debug("采集 %s 失败: %s", code, e)
            return BatchResult(code=code, bars=[], error=str(e))

    def collect_single_full(code: str, client: StockClient) -> BatchResult:
        """采集单只股票（翻页全量，可选 failover）."""
        for attempt in range(3):
            try:
                bars = client.kline_all(code, period, failover=failover)
                if bars:
                    return BatchResult(
                        code=code,
                        bars=bars,
                        error=None,
                        host=client._current_host,
                    )
                return BatchResult(code=code, bars=[], error=None)
            except Exception as e:
                if attempt < 2:
                    try:
                        client.connect()
                    except Exception:
                        pass
                else:
                    return BatchResult(code=code, bars=[], error=str(e))
        return BatchResult(code=code, bars=[], error="max retries exceeded")

    if reuse_client:
        # 单连接模式：复用同一连接，避免频繁重连开销
        logger.info("使用单连接模式（复用客户端）")
        results = []
        with StockClient(rate_limit=0, timeout=timeout_per_stock) as shared_client:
            for i, code in enumerate(codes):
                result = collect_single_full(code, shared_client)
                results.append(result)
                if (i + 1) % 100 == 0:
                    elapsed = time.time() - t0
                    rate = (i + 1) / elapsed
                    logger.info(
                        "进度: %d/%d, 耗时: %.1fs, 速率: %.1f stocks/sec, 预计总时间: %.1f min",
                        i + 1, total, elapsed, rate, total / rate / 60,
                    )
    else:
        # 多连接模式：每个工作线程独立连接，避免线程安全问题
        logger.info("使用多连接模式（独立客户端）")
        results_dict: dict[int, BatchResult] = {}

        def worker_task(args: tuple[int, str, str]) -> tuple[int, BatchResult]:
            """工作线程任务：每个任务创建独立客户端."""
            idx, code, host = args
            try:
                with StockClient(hosts=[host], rate_limit=0, timeout=timeout_per_stock) as c:
                    bars = c.kline_all(code, period, failover=failover)
                    return (idx, BatchResult(
                        code=code,
                        bars=bars,
                        error=None,
                        host=c._current_host,
                    ))
            except Exception as e:
                return (idx, BatchResult(code=code, bars=[], error=str(e)))

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            # 均匀分配代码到已知好主机
            if hosts_list:
                scanned = scan_stock(hosts_list, workers=min(8, len(hosts_list)), timeout=2.0)
                hosts = [h.host for h in scanned if h.ok]
            else:
                hosts = []
            if not hosts:
                hosts = STOCK_HOSTS[:max_workers]

            task_list = []
            for i, code in enumerate(codes):
                host = hosts[i % len(hosts)]
                task_list.append((i, code, host))

            futures = {pool.submit(worker_task, task): task[0] for task in task_list}

            for future in as_completed(futures):
                idx = futures[future]
                try:
                    _, result = future.result(timeout=timeout_per_stock * 3)
                    results_dict[idx] = result
                except Exception as e:
                    logger.error("采集任务异常: %s", e)
                    results_dict[idx] = BatchResult(code=codes[idx], bars=[], error=str(e))

        results = [results_dict[i] for i in range(total)]

    elapsed = time.time() - t0
    success = sum(1 for r in results if r.bars)
    failed = sum(1 for r in results if r.error)
    total_bars = sum(len(r.bars) for r in results)

    logger.info(
        "采集完成: 总数=%d, 成功=%d, 失败=%d, 耗时=%.1fs, 速率=%.1f stocks/sec",
        total, success, failed, elapsed, total / elapsed,
    )
    return results


def collect_all_a_stocks(
    period: str = "day",
    max_workers: int = 32,
    limit: Optional[int] = None,
) -> list[BatchResult]:
    """采集全市场 A 股日 K 线（自动获取代码列表）.

    Args:
        period: K 线周期
        max_workers: 并发线程数（默认 32）
        limit: 限制采集数量（None=全部）

    Returns:
        BatchResult 列表
    """
    # 获取 A 股代码列表
    logger.info("获取 A 股代码列表...")
    all_codes = []

    with StockClient(rate_limit=0, timeout=5.0) as sample_client:
        for market in (0, 1):  # SZ, SH
            codes = sample_client.codes_all(market)
            for item in codes:
                code = item.get("code", "")
                name = item.get("name", "")
                if code and name and "ST" not in name and "*" not in name:
                    prefix = "sz" if market == 0 else "sh"
                    all_codes.append(f"{prefix}{code}")

    if limit:
        all_codes = all_codes[:limit]

    logger.info("共 %d 只 A 股，开始批量采集...", len(all_codes))
    return collect_batch_kline(all_codes, period=period, max_workers=max_workers)


def save_kline_to_file(
    results: list[BatchResult],
    output_dir: str,
) -> dict[str, int]:
    """将采集结果保存到文件（JSON 格式）.

    Args:
        results: collect_batch_kline 返回的结果列表
        output_dir: 输出目录

    Returns:
        {"total": N, "saved": M, "skipped": K}
    """
    import os
    os.makedirs(output_dir, exist_ok=True)

    saved = 0
    skipped = 0
    total = len(results)

    for r in results:
        if r.error:
            skipped += 1
            continue
        if not r.bars:
            skipped += 1
            continue

        safe = "".join(ch for ch in r.code if ch.isalnum())
        if not safe:
            skipped += 1
            continue
        filename = os.path.join(output_dir, f"{safe}.json")

        data = {
            "code": r.code,
            "count": len(r.bars),
            "bars": [
                {
                    "time": bar.time,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "amount": bar.amount,
                }
                for bar in r.bars
            ],
        }

        import json
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            saved += 1

    return {"total": total, "saved": saved, "skipped": skipped}


def benchmark_collect(codes: list[str], max_workers: int = 16) -> dict[str, Any]:
    """性能基准测试."""
    t0 = time.time()
    results = collect_batch_kline(codes, max_workers=max_workers)
    elapsed = time.time() - t0

    total_bars = sum(len(r.bars) for r in results)
    success = sum(1 for r in results if r.bars)
    failed = sum(1 for r in results if r.error)

    return {
        "elapsed_sec": elapsed,
        "stocks_total": len(codes),
        "stocks_success": success,
        "stocks_failed": failed,
        "bars_total": total_bars,
        "bars_per_sec": total_bars / elapsed if elapsed else 0,
        "ms_per_stock": elapsed / len(codes) * 1000 if codes else 0,
    }
