#!/usr/bin/env python3
"""批量采集 CLI — K 线 + 分时/成交 + 期货 + 美股 + F10 + 巨潮 + 中金所 + MAC。

用法:
  # 指定代码文件（每行一个代码）
  python batch.py kline --codes codes.txt --period day --output ./data/

  # 逗号分隔代码
  python batch.py kline --codes "sz000001,sh600000,sz399001" --period day

  # 全市场 A 股
  python batch.py all-stocks --period day --output ./data/

  # 核心龙头池（159 只）
  python batch.py kline --universe core --period day --output ./data/

  # 股票分时 / 成交明细
  python batch.py minute --codes "sz000001,sh600000" --output ./data/
  python batch.py trade --codes "sz000001,sh600000" --date 20260620 --output ./data/

  # 港股批量行情
  python batch.py hk-quote --codes "00700,09988,01810" --output ./data/
  python batch.py hk-quote --codes hk_codes.txt --output ./data/

  # 期货批量行情 / K 线
  python batch.py futures-quote --market 47 --count 50 --output ./data/
  python batch.py futures-kline --codes "IFL0,IHL0" --market 47 --output ./data/

  # 美股行情 / K 线 / 分时 / 成交
  python batch.py us-quote --codes "AAPL,MSFT,NVDA" --output ./data/
  python batch.py us-kline --codes "AAPL,MSFT" --period day --output ./data/
  python batch.py us-minute --codes "AAPL,MSFT" --output ./data/
  python batch.py us-trade --codes "AAPL,MSFT" --output ./data/

  # F10 / 巨潮 / 中金所 / MAC
  python batch.py info-snapshot --codes "sz000001,sh600000" --output ./data/
  python batch.py cninfo --codes "000001,600000" --output ./data/
  python batch.py ccpm --products IF,IH,IC --output ./data/
  python batch.py mac-boards --type 0 --output ./data/
  python batch.py mac-flow --codes "sz000001,sh600000" --output ./data/

  # 基准测试
  python batch.py benchmark --codes codes.txt --workers 16

  # 扫描主机
  python batch.py scan stock
  python batch.py scan futures

性能参数:
  --workers  并发数，默认 32（期货建议 16）
  --timeout  单只股票超时秒数，默认 5.0
  --output   输出目录（JSON 格式，每只股票一个文件）
  --format   输出格式: json|csv|parquet，默认 json
"""

import argparse
import json
import os
import sys
import time
from datetime import date

from tdxproto import scan_stock, scan_futures, STOCK_HOSTS_LARGE, FUTURES_HOSTS_LARGE
from tdxproto import HkClient, FuturesClient
from tdxproto.stock.batch_kline import (
    collect_batch_kline,
    collect_all_a_stocks,
    save_kline_to_file,
    benchmark_collect,
    BatchResult,
)
from tdxproto.batch_collect import (
    collect_futures_kline,
    collect_us_quote,
    collect_us_kline,
    collect_us_minute,
    collect_us_trade,
    collect_stock_minute,
    collect_stock_trade,
    collect_info_snapshot,
    collect_cninfo,
    collect_ccpm,
    collect_mac_boards,
    collect_mac_flow,
    dump_results,
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
        elif args.format == "parquet":
            _save_parquet(results, args.output)
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


def _save_parquet(results: list[BatchResult], output_dir: str):
    """保存结果为 Parquet 文件（需要 pyarrow + pandas）."""
    os.makedirs(output_dir, exist_ok=True)
    data = []
    for r in results:
        if r.error:
            data.append({"code": r.code, "time": "", "open": None, "high": None,
                         "low": None, "close": None, "volume": None, "amount": None,
                         "error": r.error, "host": r.host or ""})
            continue
        for b in r.bars:
            data.append({"code": r.code, "time": b.time, "open": b.open, "high": b.high,
                         "low": b.low, "close": b.close, "volume": b.volume,
                         "amount": b.amount, "error": "", "host": r.host or ""})
    if not data:
        print("无数据可保存")
        return
    try:
        from tdxproto import to_parquet
        path = os.path.join(output_dir, "results.parquet")
        to_parquet(data, path)
        print(f"已保存 {len(data)} 条 K 线到 {path}")
    except ImportError as e:
        print(f"Parquet 输出需要安装依赖: {e}")
        print("请运行: pip install tdxproto[parquet]")


def _save_hk_json(results: dict, output_dir: str):
    """保存港股行情为 JSON 文件."""
    os.makedirs(output_dir, exist_ok=True)
    from tdxproto import to_dict
    data = list(to_dict(results).values()) if isinstance(results, dict) else to_dict(results)
    path = os.path.join(output_dir, "hk_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已保存 {len(data)} 条港股行情到 {path}")


def _save_hk_parquet(results: dict, output_dir: str):
    """保存港股行情为 Parquet 文件."""
    os.makedirs(output_dir, exist_ok=True)
    from tdxproto import to_dict
    data = list(to_dict(results).values()) if isinstance(results, dict) else to_dict(results)
    if not data:
        print("无数据可保存")
        return
    try:
        from tdxproto import to_parquet
        path = os.path.join(output_dir, "hk_results.parquet")
        to_parquet(data, path)
        print(f"已保存 {len(data)} 条港股行情到 {path}")
    except ImportError as e:
        print(f"Parquet 输出需要安装依赖: {e}")
        print("请运行: pip install tdxproto[parquet]")


def cmd_hk_quote(args):
    """批量采集港股行情."""
    codes = _load_codes(args.codes)
    if not codes:
        print("错误: 代码列表为空"); return

    print(f"批量采集 {len(codes)} 只港股行情...")
    t0 = time.time()

    client = HkClient()
    results = client.quote_batch(codes)

    elapsed = time.time() - t0
    print(f"\n完成: 成功={len(results)}, 耗时={elapsed:.2f}s")

    if args.output:
        if args.format == "parquet":
            _save_hk_parquet(results, args.output)
        else:
            _save_hk_json(results, args.output)


def cmd_futures_quote(args):
    """批量采集期货行情."""
    print(f"批量采集期货行情，市场={args.market}, 数量={args.count}...")
    t0 = time.time()

    with FuturesClient(timeout=args.timeout) as client:
        try:
            quotes = client.quote_batch(args.market, args.start, args.count)
        except Exception as e:
            print(f"错误: {e}")
            return

    elapsed = time.time() - t0
    print(f"\n完成: 获取={len(quotes)} 条行情, 耗时={elapsed:.2f}s")

    if args.output:
        os.makedirs(args.output, exist_ok=True)
        from tdxproto import to_dict
        data = to_dict(quotes)
        if args.format == "parquet":
            try:
                from tdxproto import to_parquet
                path = os.path.join(args.output, "futures_results.parquet")
                to_parquet(data, path)
                print(f"已保存 {len(data)} 条期货行情到 {path}")
            except ImportError as e:
                print(f"Parquet 输出需要安装依赖: {e}")
                print("请运行: pip install tdxproto[parquet]")
        else:
            path = os.path.join(args.output, "futures_results.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"已保存 {len(data)} 条期货行情到 {path}")


def _run_item_batch(args, results, stem, flatten=True):
    ok = sum(1 for r in results if r.error is None)
    failed = sum(1 for r in results if r.error)
    print(f"\n完成: 成功={ok}, 失败={failed}")
    if args.output:
        try:
            info = dump_results(
                results, args.output, stem,
                fmt=getattr(args, "format", "json"),
                flatten=flatten,
                per_file=getattr(args, "per_file", False),
            )
            print(f"已保存到 {info['path']}")
        except ImportError as e:
            print(f"导出失败: {e}")
            print("请运行: pip install tdxproto[parquet]")


def cmd_minute(args):
    codes = _load_codes(args.codes)
    if not codes:
        print("错误: 代码列表为空"); return
    print(f"批量采集 {len(codes)} 只股票分时, workers={args.workers}")
    t0 = time.time()
    results = collect_stock_minute(codes, date=args.date, max_workers=args.workers, timeout=args.timeout)
    print(f"耗时={time.time()-t0:.1f}s")
    _run_item_batch(args, results, "minute_results")


def cmd_trade(args):
    codes = _load_codes(args.codes)
    if not codes:
        print("错误: 代码列表为空"); return
    print(f"批量采集 {len(codes)} 只股票成交明细, workers={args.workers}")
    t0 = time.time()
    results = collect_stock_trade(
        codes, date=args.date, start=args.start, count=args.count,
        max_workers=args.workers, timeout=args.timeout,
    )
    print(f"耗时={time.time()-t0:.1f}s")
    _run_item_batch(args, results, "trade_results")


def cmd_futures_kline(args):
    codes = _load_codes(args.codes)
    if not codes:
        print("错误: 代码列表为空"); return
    print(f"批量采集 {len(codes)} 只期货 K 线, market={args.market}, period={args.period}")
    t0 = time.time()
    results = collect_futures_kline(
        codes, market=args.market, period=args.period, start=args.start, count=args.count,
        max_workers=args.workers, timeout=args.timeout,
    )
    print(f"耗时={time.time()-t0:.1f}s")
    _run_item_batch(args, results, "futures_kline_results")


def cmd_us_quote(args):
    codes = _load_codes(args.codes)
    if not codes:
        print("错误: 代码列表为空"); return
    print(f"批量采集 {len(codes)} 只美股行情, market={args.market}")
    t0 = time.time()
    results = collect_us_quote(
        codes, market=args.market, max_workers=args.workers, timeout=args.timeout,
    )
    print(f"耗时={time.time()-t0:.1f}s")
    _run_item_batch(args, results, "us_quote_results")


def cmd_us_kline(args):
    codes = _load_codes(args.codes)
    if not codes:
        print("错误: 代码列表为空"); return
    print(f"批量采集 {len(codes)} 只美股 K 线, market={args.market}, period={args.period}")
    t0 = time.time()
    results = collect_us_kline(
        codes, market=args.market, period=args.period, start=args.start, count=args.count,
        max_workers=args.workers, timeout=args.timeout,
    )
    print(f"耗时={time.time()-t0:.1f}s")
    _run_item_batch(args, results, "us_kline_results")


def cmd_us_minute(args):
    codes = _load_codes(args.codes)
    if not codes:
        print("错误: 代码列表为空"); return
    print(f"批量采集 {len(codes)} 只美股分时, market={args.market}")
    t0 = time.time()
    results = collect_us_minute(
        codes, market=args.market, date=args.date, max_workers=args.workers, timeout=args.timeout,
    )
    print(f"耗时={time.time()-t0:.1f}s")
    _run_item_batch(args, results, "us_minute_results")


def cmd_us_trade(args):
    codes = _load_codes(args.codes)
    if not codes:
        print("错误: 代码列表为空"); return
    print(f"批量采集 {len(codes)} 只美股成交, market={args.market}")
    t0 = time.time()
    results = collect_us_trade(
        codes, market=args.market, date=args.date, start=args.start, count=args.count,
        max_workers=args.workers, timeout=args.timeout,
    )
    print(f"耗时={time.time()-t0:.1f}s")
    _run_item_batch(args, results, "us_trade_results")


def cmd_info_snapshot(args):
    codes = _load_codes(args.codes)
    if not codes:
        print("错误: 代码列表为空"); return
    print(f"批量采集 {len(codes)} 只 F10 snapshot, workers={args.workers}")
    t0 = time.time()
    results = collect_info_snapshot(codes, max_workers=args.workers, timeout=args.timeout)
    print(f"耗时={time.time()-t0:.1f}s")
    _run_item_batch(args, results, "info_snapshot_results", flatten=False)


def cmd_cninfo(args):
    codes = _load_codes(args.codes)
    if not codes:
        print("错误: 代码列表为空"); return
    print(f"批量采集 {len(codes)} 只巨潮公告, workers={args.workers}")
    t0 = time.time()
    results = collect_cninfo(
        codes, count=args.count, page=args.page, keyword=args.keyword,
        max_workers=args.workers, timeout=args.timeout,
    )
    print(f"耗时={time.time()-t0:.1f}s")
    _run_item_batch(args, results, "cninfo_results")


def cmd_ccpm(args):
    products = _load_codes(args.products) or ["all"]
    print(f"批量采集中金所持仓排名: {','.join(products)}")
    t0 = time.time()
    results = collect_ccpm(
        products, date=args.date, latest=not args.date, refresh=args.refresh,
        max_workers=args.workers, timeout=args.timeout,
    )
    print(f"耗时={time.time()-t0:.1f}s")
    _run_item_batch(args, results, "ccpm_results", flatten=False)


def cmd_mac_boards(args):
    print(f"采集 MAC 板块列表, type={args.type}")
    t0 = time.time()
    results = collect_mac_boards(board_type=args.type, page_size=args.page_size, timeout=args.timeout)
    print(f"耗时={time.time()-t0:.1f}s")
    _run_item_batch(args, results, "mac_boards_results")


def cmd_mac_flow(args):
    codes = _load_codes(args.codes)
    if not codes:
        print("错误: 代码列表为空"); return
    print(f"批量采集 {len(codes)} 只 MAC 资金流向")
    t0 = time.time()
    results = collect_mac_flow(codes, max_workers=args.workers, timeout=args.timeout)
    print(f"耗时={time.time()-t0:.1f}s")
    _run_item_batch(args, results, "mac_flow_results", flatten=False)


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
    p = argparse.ArgumentParser(description="批量采集 CLI — K 线 + 分时/成交 + 期货 + 美股 + F10 + 巨潮 + 中金所 + MAC")
    sub = p.add_subparsers(dest="cmd")

    # kline
    a = sub.add_parser("kline", help="批量采集指定代码的 K 线")
    a.add_argument("--codes", help="代码列表文件路径或逗号分隔代码")
    a.add_argument("--universe", choices=["core"], help="预置股票池: core=核心龙头 159 只")
    a.add_argument("--period", default="day", help="K 线周期: day/1m/5m/15m/30m/60m/week/month")
    a.add_argument("--output", help="输出目录")
    a.add_argument("--format", choices=["json", "csv", "parquet"], default="json", help="输出格式")
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

    a = sub.add_parser("minute", help="批量采集股票分时")
    a.add_argument("--codes", required=True)
    a.add_argument("--date", default=None)
    a.add_argument("--output", required=True)
    a.add_argument("--format", choices=["json", "csv", "parquet"], default="json")
    a.add_argument("--workers", type=int, default=16)
    a.add_argument("--timeout", type=float, default=5.0)
    a.add_argument("--per-file", action="store_true")

    a = sub.add_parser("trade", help="批量采集股票成交明细")
    a.add_argument("--codes", required=True)
    a.add_argument("--date", default=None)
    a.add_argument("--start", type=int, default=0)
    a.add_argument("--count", type=int, default=100)
    a.add_argument("--output", required=True)
    a.add_argument("--format", choices=["json", "csv", "parquet"], default="json")
    a.add_argument("--workers", type=int, default=16)
    a.add_argument("--timeout", type=float, default=5.0)
    a.add_argument("--per-file", action="store_true")

    a = sub.add_parser("hk-quote", help="批量采集港股行情")
    a.add_argument("--codes", required=True, help="代码列表文件路径或逗号分隔代码")
    a.add_argument("--output", help="输出目录")
    a.add_argument("--format", choices=["json", "parquet"], default="json", help="输出格式")

    # futures-quote
    a = sub.add_parser("futures-quote", help="批量采集期货行情")
    a.add_argument("--market", type=int, default=47, help="市场代码 (默认 47=中金所)")
    a.add_argument("--start", type=int, default=0, help="起始位置")
    a.add_argument("--count", type=int, default=50, help="获取数量")
    a.add_argument("--output", help="输出目录")
    a.add_argument("--format", choices=["json", "parquet"], default="json", help="输出格式")
    a.add_argument("--timeout", type=float, default=8.0, help="超时秒数")

    a = sub.add_parser("futures-kline", help="批量采集期货 K 线")
    a.add_argument("--codes", required=True)
    a.add_argument("--market", type=int, default=47)
    a.add_argument("--period", default="day")
    a.add_argument("--start", type=int, default=0)
    a.add_argument("--count", type=int, default=100)
    a.add_argument("--output", required=True)
    a.add_argument("--format", choices=["json", "csv", "parquet"], default="json")
    a.add_argument("--workers", type=int, default=16)
    a.add_argument("--timeout", type=float, default=8.0)
    a.add_argument("--per-file", action="store_true")

    a = sub.add_parser("us-quote", help="批量采集美股行情")
    a.add_argument("--codes", required=True)
    a.add_argument("--market", type=int, default=74)
    a.add_argument("--output", required=True)
    a.add_argument("--format", choices=["json", "csv", "parquet"], default="json")
    a.add_argument("--workers", type=int, default=16)
    a.add_argument("--timeout", type=float, default=8.0)
    a.add_argument("--per-file", action="store_true")

    a = sub.add_parser("us-kline", help="批量采集美股 K 线")
    a.add_argument("--codes", required=True)
    a.add_argument("--market", type=int, default=74)
    a.add_argument("--period", default="day")
    a.add_argument("--start", type=int, default=0)
    a.add_argument("--count", type=int, default=100)
    a.add_argument("--output", required=True)
    a.add_argument("--format", choices=["json", "csv", "parquet"], default="json")
    a.add_argument("--workers", type=int, default=16)
    a.add_argument("--timeout", type=float, default=8.0)
    a.add_argument("--per-file", action="store_true")

    a = sub.add_parser("us-minute", help="批量采集美股分时")
    a.add_argument("--codes", required=True)
    a.add_argument("--market", type=int, default=74)
    a.add_argument("--date", default=None)
    a.add_argument("--output", required=True)
    a.add_argument("--format", choices=["json", "csv", "parquet"], default="json")
    a.add_argument("--workers", type=int, default=16)
    a.add_argument("--timeout", type=float, default=8.0)
    a.add_argument("--per-file", action="store_true")

    a = sub.add_parser("us-trade", help="批量采集美股成交")
    a.add_argument("--codes", required=True)
    a.add_argument("--market", type=int, default=74)
    a.add_argument("--date", default=None)
    a.add_argument("--start", type=int, default=0)
    a.add_argument("--count", type=int, default=100)
    a.add_argument("--output", required=True)
    a.add_argument("--format", choices=["json", "csv", "parquet"], default="json")
    a.add_argument("--workers", type=int, default=16)
    a.add_argument("--timeout", type=float, default=8.0)
    a.add_argument("--per-file", action="store_true")

    a = sub.add_parser("info-snapshot", help="批量采集 F10 资料快照")
    a.add_argument("--codes", required=True)
    a.add_argument("--output", required=True)
    a.add_argument("--format", choices=["json", "parquet"], default="json")
    a.add_argument("--workers", type=int, default=8)
    a.add_argument("--timeout", type=float, default=15.0)
    a.add_argument("--per-file", action="store_true")

    a = sub.add_parser("cninfo", help="批量采集巨潮公告")
    a.add_argument("--codes", required=True)
    a.add_argument("--count", type=int, default=10)
    a.add_argument("--page", type=int, default=1)
    a.add_argument("--keyword", default="")
    a.add_argument("--output", required=True)
    a.add_argument("--format", choices=["json", "csv", "parquet"], default="json")
    a.add_argument("--workers", type=int, default=8)
    a.add_argument("--timeout", type=float, default=20.0)
    a.add_argument("--per-file", action="store_true")

    a = sub.add_parser("ccpm", help="批量采集中金所持仓排名")
    a.add_argument("--products", default="all", help="IF,IH,IC 或 all")
    a.add_argument("--date", default=None)
    a.add_argument("--refresh", action="store_true")
    a.add_argument("--output", required=True)
    a.add_argument("--format", choices=["json", "parquet"], default="json")
    a.add_argument("--workers", type=int, default=4)
    a.add_argument("--timeout", type=float, default=20.0)

    a = sub.add_parser("mac-boards", help="采集 MAC 板块列表并落盘")
    a.add_argument("--type", type=int, default=0)
    a.add_argument("--page-size", type=int, default=150)
    a.add_argument("--output", required=True)
    a.add_argument("--format", choices=["json", "csv", "parquet"], default="json")
    a.add_argument("--timeout", type=float, default=8.0)

    a = sub.add_parser("mac-flow", help="批量采集 MAC 资金流向")
    a.add_argument("--codes", required=True)
    a.add_argument("--output", required=True)
    a.add_argument("--format", choices=["json", "parquet"], default="json")
    a.add_argument("--workers", type=int, default=4)
    a.add_argument("--timeout", type=float, default=8.0)

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

    {
        "kline": cmd_kline, "all-stocks": cmd_all_stocks,
        "minute": cmd_minute, "trade": cmd_trade,
        "hk-quote": cmd_hk_quote, "futures-quote": cmd_futures_quote,
        "futures-kline": cmd_futures_kline,
        "us-quote": cmd_us_quote, "us-kline": cmd_us_kline,
        "us-minute": cmd_us_minute, "us-trade": cmd_us_trade,
        "info-snapshot": cmd_info_snapshot, "cninfo": cmd_cninfo,
        "ccpm": cmd_ccpm, "mac-boards": cmd_mac_boards, "mac-flow": cmd_mac_flow,
        "benchmark": cmd_benchmark, "scan": cmd_scan,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
