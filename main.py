#!/usr/bin/env python3
"""通达信全协议 CLI — 股票 + 期货 + ETF 一站式。

用法:
  股票 (7709):
    python main.py stock count sz
    python main.py stock codes sz
    python main.py stock quote sz000001,sh600000
    python main.py stock kline sz000001 --period day --adjust qfq
    python main.py stock minute sz000001
    python main.py stock auction sz000001
    python main.py stock trade sz000001 20260620
    python main.py stock equity sz000001
    python main.py stock finance sz000001,sh600000
    python main.py stock limits
    python main.py stock turnover sz000001

  期货 (7727):
    python main.py futures markets
    python main.py futures codes 47
    python main.py futures quote IF2506
    python main.py futures kline IF2506 --period day
    python main.py futures minute IF2506
    python main.py futures trade IF2506

  ETF:
    python main.py etf quote sz159919,sh510050
"""

import argparse
import json
import sys
from datetime import date

from tdxproto import StockClient, FuturesClient
from tdxproto import compute_factors, get_equity_at, calc_turnover, parse_xdxr


def js(obj, default=str):
    def _conv(o):
        if hasattr(o, "__dataclass_fields__"):
            return {f: _conv(getattr(o, f)) for f in o.__dataclass_fields__}
        if isinstance(o, list):
            return [_conv(i) for i in o]
        if isinstance(o, bytes):
            return o.hex()
        return o
    print(json.dumps(_conv(obj), indent=2, ensure_ascii=False, default=default))


# ========== Stock ==========

def stock_count(c, a): js(c.count(a.market))
def stock_codes(c, a):
    if a.all:
        js(c.codes_all(a.market))
    else:
        js(c.codes(a.market, a.start, a.limit))

def stock_quote(c, a):
    codes = [x.strip() for x in a.codes.split(",")]
    js(c.quote(codes))

def stock_kline(c, a):
    js(c.kline(a.code, a.period, a.start, a.count, a.adjust, a.anchor or ""))

def stock_kline_all(c, a):
    bars = c.kline_all(a.code, a.period, a.adjust)
    js(bars)

def stock_minute(c, a):
    if a.date:
        js(c.history_minute(a.code, a.date))
    else:
        js(c.recent_minute(a.code))

def stock_aux(c, a): js(c.aux(a.code, a.kind))
def stock_sparkline(c, a): js(c.sparkline(a.code, a.selector, a.window))

def stock_trade(c, a):
    if a.date:
        if a.all:
            js(c.history_trade_all(a.code, a.date))
        else:
            js(c.history_trade(a.code, a.date, a.start, a.count))
    else:
        js(c.today_trade(a.code, a.start, a.count))

def stock_auction(c, a): js(c.auction(a.code, a.mode))

def stock_equity(c, a):
    eq = c.capital_changes(a.code)
    js(eq)
    events = parse_xdxr(eq)
    if events:
        print("\n# 除权除息事件:")
        js(events)

def stock_finance(c, a):
    codes = [x.strip() for x in a.codes.split(",")]
    js(c.finance(codes))

def stock_limits(c, a): js(c.limits(a.start))

def stock_turnover(c, a):
    eq = c.capital_changes(a.code)
    fr = c.finance([a.code])
    float_shares = 0.0
    if fr:
        float_shares = fr[0].float_shares
    if float_shares == 0:
        eq_float, _ = get_equity_at(eq, date.today())
        float_shares = eq_float
    qs = c.quote([a.code])
    if qs:
        to = calc_turnover(qs[0].volume, float_shares)
        print(f"换手率: {to:.2f}%  (成交量={qs[0].volume}, 流通股本={float_shares:.0f}万)")

def stock_info(c, a):
    """一键输出全部可获取数据。"""
    code = a.code
    result = {"code": code}
    try: result["quote"] = [js_inner(c.quote([code]))]
    except Exception as e: result["quote"] = {"error": str(e)}
    try: result["minute"] = js_inner(c.recent_minute(code))
    except Exception as e: result["minute"] = {"error": str(e)}
    try: result["auction"] = js_inner(c.auction(code))
    except Exception as e: result["auction"] = {"error": str(e)}
    try: result["equity"] = js_inner(c.capital_changes(code))
    except Exception as e: result["equity"] = {"error": str(e)}
    try: result["finance"] = js_inner(c.finance([code]))
    except Exception as e: result["finance"] = {"error": str(e)}
    js(result)


def js_inner(obj):
    if hasattr(obj, "__dataclass_fields__"):
        return {f: js_inner(getattr(obj, f)) for f in obj.__dataclass_fields__}
    if isinstance(obj, list):
        return [js_inner(i) for i in obj]
    if isinstance(obj, bytes):
        return obj.hex()
    return obj


# ========== Futures ==========

def fut_markets(c, a): js(c.markets())
def fut_codes(c, a):
    if a.all: js(c.codes_all(a.market))
    else: js(c.codes(a.market, a.start, a.count))
def fut_quote(c, a): js(c.quote(a.market, a.code))
def fut_quote_batch(c, a): js(c.quote_batch(a.market, a.start, a.count))
def fut_kline(c, a): js(c.kline(a.market, a.code, a.period, a.start, a.count))
def fut_minute(c, a):
    if a.date: js(c.history_minute(a.market, a.code, a.date))
    else: js(c.today_minute(a.market, a.code))
def fut_trade(c, a):
    if a.date: js(c.history_trade(a.market, a.code, a.date, a.start, a.count))
    else: js(c.today_trade(a.market, a.code, a.start, a.count))


# ========== ETF (股票协议子集) ==========

def etf_quote(c, a):
    codes = [x.strip() for x in a.codes.split(",")]
    js(c.quote(codes))


# ========== Scan ==========

def cmd_scan_stock(args):
    from tdxproto import scan_stock, STOCK_HOSTS_LARGE
    print(f"扫描 {len(STOCK_HOSTS_LARGE)} 个 A 股主站 (7709)...")
    results = scan_stock(STOCK_HOSTS_LARGE, workers=args.workers, timeout=args.timeout)
    _print_scan_results(results, "7709 A股")

def cmd_scan_futures(args):
    from tdxproto import scan_futures, FUTURES_HOSTS_LARGE
    print(f"扫描 {len(FUTURES_HOSTS_LARGE)} 个期货主站 (7727)...")
    results = scan_futures(FUTURES_HOSTS_LARGE, workers=args.workers, timeout=args.timeout)
    _print_scan_results(results, "7727 期货")

def _print_scan_results(results, label):
    alive = [r for r in results if r.ok]
    dead  = [r for r in results if not r.ok]
    print(f"\n{'='*60}")
    print(f"{label} 扫描结果: {len(alive)} 可用 / {len(dead)} 不可用")
    print(f"{'='*60}")
    if alive:
        print(f"\n{'#':<4} {'延迟':<8} {'地址'}")
        print("-" * 40)
        for i, r in enumerate(alive[:30], 1):
            print(f"{i:<4} {r.handshake_latency_ms:>6.0f}ms  {r.host}")
    if dead:
        print(f"\n不可用 ({len(dead)}):")
        for r in dead[:10]:
            err = r.error or "tcp timeout"
            print(f"  {r.host}  — {err}")
        if len(dead) > 10:
            print(f"  ... 还有 {len(dead) - 10} 个")
    if alive:
        fastest = alive[0]
        print(f"\n最快: {fastest.host} ({fastest.handshake_latency_ms:.0f}ms)")
        # 保存到缓存文件
        import pathlib
        cache = pathlib.Path(__file__).parent / ".tdx_best_hosts.json"
        prev = {}
        if cache.exists():
            try: prev = json.loads(cache.read_text())
            except Exception: pass
        prev["stock" if "A股" in label else "futures"] = {
            "host": fastest.host, "latency_ms": fastest.handshake_latency_ms,
            "updated": str(date.today()),
        }
        cache.write_text(json.dumps(prev, indent=2))
        print(f"已缓存到 {cache}")

def main():
    p = argparse.ArgumentParser(description="通达信全协议解析器 (7709+7727)")
    sub = p.add_subparsers(dest="proto")

    # Scan
    sc = sub.add_parser("scan", help="主站可用性扫描与测速")
    scs = sc.add_subparsers(dest="scan_type")
    a = scs.add_parser("stock", help="扫描 7709 A股主站")
    a.add_argument("--workers", type=int, default=64)
    a.add_argument("--timeout", type=float, default=2.0)
    a = scs.add_parser("futures", help="扫描 7727 期货主站")
    a.add_argument("--workers", type=int, default=64)
    a.add_argument("--timeout", type=float, default=2.0)

    # Stock
    s = sub.add_parser("stock", help="7709 股票行情")
    ss = s.add_subparsers(dest="cmd")
    a = ss.add_parser("count", help="0x044e 代码数量"); a.add_argument("market")
    a = ss.add_parser("codes", help="0x044d 代码表"); a.add_argument("market"); a.add_argument("--start", type=int, default=0); a.add_argument("--limit", type=int, default=1600); a.add_argument("--all", action="store_true")
    a = ss.add_parser("quote", help="0x054c 批量快照"); a.add_argument("codes")
    a = ss.add_parser("kline", help="0x052d K线(含复权)"); a.add_argument("code"); a.add_argument("--period", default="day"); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=100); a.add_argument("--adjust", default=""); a.add_argument("--anchor", default="")
    a = ss.add_parser("kline-all", help="自动翻页拉全量K线"); a.add_argument("code"); a.add_argument("--period", default="day"); a.add_argument("--adjust", default="")
    a = ss.add_parser("minute", help="0x0feb/0x0537 分时"); a.add_argument("code"); a.add_argument("--date", default=None)
    a = ss.add_parser("aux", help="0x051b 分时副图"); a.add_argument("code"); a.add_argument("--kind", default="buy_sell")
    a = ss.add_parser("sparkline", help="0x0fd1 小走势图"); a.add_argument("code"); a.add_argument("--selector", type=int, default=1); a.add_argument("--window", type=int, default=20)
    a = ss.add_parser("trade", help="0x0fc6/0x0fc5 成交明细"); a.add_argument("code"); a.add_argument("date", nargs="?"); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=100); a.add_argument("--all", action="store_true")
    a = ss.add_parser("auction", help="0x056a 集合竞价"); a.add_argument("code"); a.add_argument("--mode", type=int, default=3)
    a = ss.add_parser("equity", help="0x000f 股本变迁+除权除息"); a.add_argument("code")
    a = ss.add_parser("finance", help="0x0010 财务基础"); a.add_argument("codes")
    a = ss.add_parser("limits", help="0x0452 涨跌停限制"); a.add_argument("--start", type=int, default=0)
    a = ss.add_parser("turnover", help="本地计算换手率"); a.add_argument("code")
    a = ss.add_parser("info", help="一键全部数据"); a.add_argument("code")

    # Futures
    f = sub.add_parser("futures", help="7727 期货行情")
    fs = f.add_subparsers(dest="cmd")
    a = fs.add_parser("markets", help="0x23F4 交易所列表")
    a = fs.add_parser("codes", help="0x23F5 代码表"); a.add_argument("market", type=int); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=200); a.add_argument("--all", action="store_true")
    a = fs.add_parser("quote", help="0x23FA 五档行情"); a.add_argument("code"); a.add_argument("--market", type=int, default=47)
    a = fs.add_parser("quote-batch", help="0x2400 批量行情"); a.add_argument("--market", type=int, default=47); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=200)
    a = fs.add_parser("kline", help="0x23FF K线"); a.add_argument("code"); a.add_argument("--market", type=int, default=47); a.add_argument("--period", default="day"); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=100)
    a = fs.add_parser("minute", help="0x240B/0x240C 分时"); a.add_argument("code"); a.add_argument("--market", type=int, default=47); a.add_argument("--date", default=None)
    a = fs.add_parser("trade", help="0x23FC/0x2406 成交"); a.add_argument("code"); a.add_argument("date", nargs="?"); a.add_argument("--market", type=int, default=47); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=100)

    # ETF
    e = sub.add_parser("etf", help="ETF 行情 (股票协议)")
    es = e.add_subparsers(dest="cmd")
    a = es.add_parser("quote", help="批量行情快照"); a.add_argument("codes")

    args = p.parse_args()
    if not args.proto:
        p.print_help(); return

    if args.proto == "scan":
        if args.scan_type == "stock":
            cmd_scan_stock(args)
        elif args.scan_type == "futures":
            cmd_scan_futures(args)
        else:
            print("用法: python main.py scan {stock|futures}"); return

    elif args.proto == "stock":
        with StockClient(timeout=5) as c:
            h = {
                "count": stock_count, "codes": stock_codes, "quote": stock_quote,
                "kline": stock_kline, "kline-all": stock_kline_all,
                "minute": stock_minute, "aux": stock_aux, "sparkline": stock_sparkline,
                "trade": stock_trade, "auction": stock_auction,
                "equity": stock_equity, "finance": stock_finance,
                "limits": stock_limits, "turnover": stock_turnover, "info": stock_info,
            }.get(args.cmd)
            if h: h(c, args)

    elif args.proto == "futures":
        with FuturesClient(timeout=5) as c:
            h = {
                "markets": fut_markets, "codes": fut_codes,
                "quote": fut_quote, "quote-batch": fut_quote_batch,
                "kline": fut_kline, "minute": fut_minute, "trade": fut_trade,
            }.get(args.cmd)
            if h: h(c, args)

    elif args.proto == "etf":
        with StockClient(timeout=5) as c:
            if args.cmd == "quote":
                etf_quote(c, args)


if __name__ == "__main__":
    main()
