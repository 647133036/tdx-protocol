#!/usr/bin/env python3
"""批量 K 线采集 CLI — 对标 easy_tdx 采集管线。

用法:
  # 指定代码文件（每行一个代码）
  python batch.py kline --codes codes.txt --period day --output ./data/

  # 逗号分隔代码
  python batch.py kline --codes "sz000001,sh600000,sz399001" --period day

  # 全市场 A 股
  python batch.py all-stocks --period day --output ./data/

  # 核心龙头池（159 只）
  python batch.py kline --universe core --period day --output ./data/

  # 基准测试
  python batch.py benchmark --codes codes.txt --workers 16

  # 扫描主机
  python batch.py scan stock
  python batch.py scan futures

性能参数:
  --workers  并发数，默认 32（期货建议 16）
  --timeout  单只股票超时秒数，默认 5.0
  --output   输出目录（JSON 格式，每只股票一个文件）
  --format   输出格式: json|csv，默认 json
"""

import argparse
import json
import os
import sys
import time
from datetime import date

from tdxproto import scan_stock, scan_futures, STOCK_HOSTS_LARGE, FUTURES_HOSTS_LARGE
from tdxproto.stock.batch_kline import (
    collect_batch_kline,
    collect_all_a_stocks,
    save_kline_to_file,
    benchmark_collect,
    BatchResult,
)


def _load_codes(raw: str | None) -> list[str]:
    """从文件或字符串解析代码列表."""
    if not raw:
        return []
    if os.path.isfile(raw):
        with open(raw, encoding="utf-8") as f:
            codes = [line.strip() for line in f if line.strip()]
    else:
        codes = [c.strip() for c in raw.split(",") if c.strip()]
    return codes


def _save_json(results: list[BatchResult], output_dir: str):
    """保存结果为单个 JSON 文件."""
    os.makedirs(output_dir, exist_ok=True)
    data = []
    for r in results:
        entry = {"code": r.code, "count": len(r.bars)}
        if r.error:
            entry["error"] = r.error
        if r.host:
            entry["host"] = r.host
        if r.bars:
            entry["bars"] = [
                {
                    "time": b.time,
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                    "amount": b.amount,
                }
                for b in r.bars
            ]
        data.append(entry)

    path = os.path.join(output_dir, "results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已保存 {len(data)} 条结果到 {path}")


def _save_csv(results: list[BatchResult], output_dir: str):
    """保存结果为 CSV 文件."""
    import csv
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "results.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["code", "time", "open", "high", "low", "close", "volume", "amount", "error"])
        for r in results:
            if r.error:
                writer.writerow([r.code, "", "", "", "", "", "", "", r.error])
                continue
            for b in r.bars:
                writer.writerow([r.code, b.time, b.open, b.high, b.low, b.close, b.volume, b.amount, ""])
    print(f"已保存 {sum(len(r.bars) for r in results)} 条 K 线到 {path}")


def cmd_kline(args):
    if getattr(args, "universe", None) == "core":
        from tdxproto import core_leader_codes
        codes = core_leader_codes()
    else:
        codes = _load_codes(args.codes)
    if not codes:
        print("错误: 代码列表为空"); return

    print(f"批量采集 {len(codes)} 只股票，周期={args.period}, workers={args.workers}")
    t0 = time.time()

    results = collect_batch_kline(
        codes=codes,
        period=args.period,
        max_workers=args.workers,
        reuse_client=args.reuse,
        failover=args.failover,
        timeout_per_stock=args.timeout,
        hosts_list=args.hosts,
    )

    elapsed = time.time() - t0
    success = sum(1 for r in results if r.bars)
    failed = sum(1 for r in results if r.error)
    total_bars = sum(len(r.bars) for r in results)

    print(f"\n完成: 成功={success}, 失败={failed}, 总K线={total_bars}, 耗时={elapsed:.1f}s, 速率={len(codes)/elapsed:.1f} stocks/sec")

    if args.output:
        if args.format == "csv":
            _save_csv(results, args.output)
        else:
            _save_json(results, args.output)
        per_file = save_kline_to_file(results, args.output)
        print(f"分文件: 保存={per_file['saved']}, 跳过={per_file['skipped']}")


def cmd_all_stocks(args):
    print(f"全市场 A 股采集，周期={args.period}, workers={args.workers}")
    if args.limit:
        print(f"限制数量: {args.limit}")
    t0 = time.time()

    results = collect_all_a_stocks(
        period=args.period,
        max_workers=args.workers,
        limit=args.limit,
    )

    elapsed = time.time() - t0
    success = sum(1 for r in results if r.bars)
    failed = sum(1 for r in results if r.error)
    total_bars = sum(len(r.bars) for r in results)

    print(f"\n完成: 成功={success}, 失败={failed}, 总K线={total_bars}, 耗时={elapsed:.1f}s")

    if args.output:
        _save_json(results, args.output)
        per_file = save_kline_to_file(results, args.output)
        print(f"分文件: 保存={per_file['saved']}, 跳过={per_file['skipped']}")


def cmd_benchmark(args):
    codes = _load_codes(args.codes)
    if not codes:
        print("错误: 代码列表为空"); return

    print(f"基准测试: {len(codes)} 只股票, workers={args.workers}")
    stats = benchmark_collect(codes, max_workers=args.workers)

    print(f"\n基准测试结果:")
    print(f"  总股票数: {stats['stocks_total']}")
    print(f"  成功: {stats['stocks_success']}")
    print(f"  失败: {stats['stocks_failed']}")
    print(f"  总 K 线数: {stats['bars_total']}")
    print(f"  耗时: {stats['elapsed_sec']:.2f}s")
    print(f"  速率: {stats['bars_per_sec']:.1f} bars/sec")
    print(f"  单股耗时: {stats['ms_per_stock']:.1f} ms")


def cmd_scan(args):
    if args.scan_type == "stock":
        results = scan_stock(STOCK_HOSTS_LARGE, workers=args.workers, timeout=args.timeout)
        alive = [r for r in results if r.ok]
        dead = [r for r in results if not r.ok]
        print(f"\nA 股主站 (7709): {len(alive)} 可用 / {len(dead)} 不可用")
        if alive:
            print(f"最快: {alive[0].host} ({alive[0].handshake_latency_ms:.0f}ms)")
    elif args.scan_type == "futures":
        results = scan_futures(FUTURES_HOSTS_LARGE, workers=args.workers, timeout=args.timeout)
        alive = [r for r in results if r.ok]
        dead = [r for r in results if not r.ok]
        print(f"\n期货主站 (7727): {len(alive)} 可用 / {len(dead)} 不可用")
        if alive:
            print(f"最快: {alive[0].host} ({alive[0].handshake_latency_ms:.0f}ms)")


def main():
    p = argparse.ArgumentParser(description="批量 K 线采集 CLI")
    sub = p.add_subparsers(dest="cmd")

    # kline
    a = sub.add_parser("kline", help="批量采集指定代码的 K 线")
    a.add_argument("--codes", help="代码列表文件路径或逗号分隔代码")
    a.add_argument("--universe", choices=["core"], help="预置股票池: core=核心龙头 159 只")
    a.add_argument("--period", default="day", help="K 线周期: day/1m/5m/15m/30m/60m/week/month")
    a.add_argument("--output", help="输出目录")
    a.add_argument("--format", choices=["json", "csv"], default="json", help="输出格式")
    a.add_argument("--workers", type=int, default=32, help="并发数 (默认 32)")
    a.add_argument("--timeout", type=float, default=5.0, help="单股超时秒数")
    a.add_argument("--failover", action="store_true", default=False, help="启用故障转移 (默认关闭)")
    a.add_argument("--reuse", action="store_true", help="复用单连接 (慢但省资源)")
    a.add_argument("--hosts", nargs="*", help="指定主机列表文件")

    # all-stocks
    a = sub.add_parser("all-stocks", help="全市场 A 股 K 线采集")
    a.add_argument("--period", default="day")
    a.add_argument("--output", required=True, help="输出目录")
    a.add_argument("--workers", type=int, default=32)
    a.add_argument("--limit", type=int, help="限制采集数量")

    # benchmark
    a = sub.add_parser("benchmark", help="性能基准测试")
    a.add_argument("--codes", required=True, help="代码列表文件路径或逗号分隔")
    a.add_argument("--workers", type=int, default=16)

    # scan
    a = sub.add_parser("scan", help="扫描主站可用性")
    a.add_argument("scan_type", choices=["stock", "futures"])
    a.add_argument("--workers", type=int, default=64)
    a.add_argument("--timeout", type=float, default=2.0)

    args = p.parse_args()
    if not args.cmd:
        p.print_help(); return

    {"kline": cmd_kline, "all-stocks": cmd_all_stocks, "benchmark": cmd_benchmark, "scan": cmd_scan}[args.cmd](args)


if __name__ == "__main__":
    main()
