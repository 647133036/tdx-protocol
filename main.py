#!/usr/bin/env python3
"""通达信全协议 CLI — 股票 + 期货 + 美股 + ETF + 港股 + F10 + 巨潮 + 中金所 + MAC。

用法:
  股票 (7709):
    python main.py stock count sz
    python main.py stock codes sz
    python main.py stock quote sz000001,sh600000
    python main.py stock kline sz000001 --period day --adjust qfq
    python main.py stock kline-120m sz000001
    python main.py stock kline-derived sz000001 --period day
    python main.py stock minute sz000001
    python main.py stock auction sz000001
    python main.py stock trade sz000001 20260620
    python main.py stock quotes-detail sz000001,sh600000
    python main.py stock capital-flow sz000001
    python main.py stock market-stat
    python main.py stock equity sz000001
    python main.py stock finance sz000001,sh600000
    python main.py stock limits
    python main.py stock turnover sz000001

  期货 (7727):
    python main.py futures markets
    python main.py futures codes 47
    python main.py futures quote IF2506
    python main.py futures kline IF2506 --period day
    python main.py futures kline-range IF2506 --start-date 20260101 --end-date 20260301
    python main.py futures minute IF2506
    python main.py futures trade IF2506
    python main.py futures tick-chart IF2506
    python main.py futures main-contract IF

  美股 (7727 扩展行情, 市场 74):
    python main.py us quote AAPL
    python main.py us kline AAPL --period day
    python main.py us kline-range AAPL --start-date 20260101 --end-date 20260301
    python main.py us minute AAPL
    python main.py us trade AAPL
    python main.py us tick-chart AAPL

  ETF:
    python main.py etf quote sz159919,sh510050

  港股 (腾讯接口):
    python main.py hk quote 00700
    python main.py hk quote-batch 00700,09988,01810

  F10 / 巨潮 / 中金所 / MAC:
    python main.py info news sz000001
    python main.py info snapshot sz000001
    python main.py cninfo search 000001
    python main.py ccpm latest IF
    python main.py mac board-list
"""

import argparse
import json
import sys
from datetime import date, datetime  # noqa: F401 — datetime used by stock_workday

from tdxproto import StockClient, FuturesClient, HkClient
from tdxproto import compute_factors, get_equity_at, calc_turnover, parse_xdxr
from tdxproto import InfoClient, InfoCollector, CninfoClient, CcpmClient
try:
    from tdxproto import MacClient
except ImportError:
    MacClient = None

_MARKET_ALIASES = {"sz": 0, "sh": 1, "bj": 2, "szse": 0, "sse": 1, "bse": 2}
_CATEGORY_ALIASES = {"sh": 0, "sz": 2, "a": 6, "b": 7, "kcb": 8, "bj": 12, "cyb": 14}


def js(obj, default=str):
    def _conv(o):
        if hasattr(o, "__dataclass_fields__"):
            return {f: _conv(getattr(o, f)) for f in o.__dataclass_fields__}
        if isinstance(o, dict):
            return {k: _conv(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_conv(i) for i in o]
        if isinstance(o, bytes):
            return o.hex()
        return o
    print(json.dumps(_conv(obj), indent=2, ensure_ascii=False, default=default))


def _parse_market(value):
    if value is None:
        return 0
    key = str(value).strip().lower()
    if key in _MARKET_ALIASES:
        return _MARKET_ALIASES[key]
    return int(key)


def _parse_codes(value):
    if not value:
        return []
    return [x.strip() for x in str(value).split(",") if x.strip()]


def _parse_category(value):
    key = str(value).strip().lower()
    if key in _CATEGORY_ALIASES:
        return _CATEGORY_ALIASES[key]
    return int(key)


def _code_market(code, fallback=0):
    raw = str(code).strip().lower()
    if raw.startswith("sh"):
        return 1
    if raw.startswith("sz"):
        return 0
    if raw.startswith("bj"):
        return 2
    return fallback


def _code6(code):
    raw = str(code).strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits[-6:] if len(digits) >= 6 else digits


def _us_code(code):
    raw = str(code).strip()
    if raw.startswith("us") and len(raw) > 2:
        return raw[2:]
    return raw


def _require_mac():
    if MacClient is None:
        print("MAC 模块不可用", file=sys.stderr)
        return False
    return True


# ========== Stock ==========

def stock_count(c, a): js(c.count(_parse_market(a.market)))
def stock_codes(c, a):
    mid = _parse_market(a.market)
    if a.all:
        js(c.codes_all(mid))
    else:
        js(c.codes(mid, a.start, a.limit))

def stock_quote(c, a):
    codes = [x.strip() for x in a.codes.split(",")]
    result = []
    for code in codes:
        try:
            result.append(c.quote(code))
        except Exception as e:
            result.append({"code": code, "error": str(e)})
    js(result)

def stock_kline(c, a):
    if a.count > 65535:
        print(f"错误: --count 最大值为 65535, 当前值={a.count}", file=sys.stderr); return
    js(c.kline(a.code, a.period, a.start, a.count, a.adjust, a.anchor or ""))

def stock_kline_all(c, a):
    bars = c.kline_all(a.code, a.period, a.adjust)
    js(bars)

def stock_minute(c, a):
    if a.date:
        js(c.history_minute(a.code, a.date))
    else:
        js(c.recent_minute(a.code))

def stock_aux(c, a): js(c.aux(a.code))
def stock_sparkline(c, a): js(c.sparkline(a.code))

def stock_trade(c, a):
    if a.date:
        if a.all:
            all_rows = []
            start = 0
            while True:
                batch = c.history_trade(a.code, a.date, start, 900)
                if not batch:
                    break
                all_rows.extend(batch)
                if len(batch) < 900:
                    break
                start += len(batch)
            js(all_rows)
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
    result = []
    for code in codes:
        try:
            result.append(c.finance(code))
        except Exception as e:
            result.append({"code": code, "error": str(e)})
    js(result)

def stock_limits(c, a): js(c.limits(a.start))

def stock_turnover(c, a):
    eq = c.capital_changes(a.code)
    fr = c.finance(a.code)
    float_shares = 0.0
    if fr and "error" not in fr:
        float_shares = fr.get("liutongguben", 0.0) / 10000
    if not float_shares:
        eq_float, _ = get_equity_at(eq, date.today())
        float_shares = eq_float
    qs = c.quote(a.code)
    if qs:
        vol = getattr(qs, "volume", 0) if not isinstance(qs, dict) else qs.get("vol", qs.get("volume", 0))
        to = calc_turnover(vol, float_shares)
        print(f"换手率: {to:.2f}%  (成交量={vol}, 流通股本={float_shares:.0f}万)")

def stock_info(c, a):
    """一键输出全部可获取数据。"""
    code = a.code
    result = {"code": code}
    try: result["quote"] = js_inner(c.quote(code))
    except Exception as e: result["quote"] = {"error": str(e)}
    try: result["minute"] = js_inner(c.recent_minute(code))
    except Exception as e: result["minute"] = {"error": str(e)}
    try: result["auction"] = js_inner(c.auction(code))
    except Exception as e: result["auction"] = {"error": str(e)}
    try: result["equity"] = js_inner(c.capital_changes(code))
    except Exception as e: result["equity"] = {"error": str(e)}
    try: result["finance"] = js_inner(c.finance(code))
    except Exception as e: result["finance"] = {"error": str(e)}
    js(result)

def stock_blocks(c, a):
    js(c.get_blocks_with_index(a.type))

def stock_block_members(c, a):
    js(c.block_members(a.block_code))

def stock_workday(c, a):
    from tdxproto.workday import get_workday_manager
    d = datetime.fromisoformat(a.date).date() if a.date else None
    wm = get_workday_manager(c)
    result = {"date": str(d or date.today()), "is_workday": wm.is_workday(d)}
    js(result)

def stock_kline_120m(c, a): js(c.kline_120m(a.code, a.start, a.count))
def stock_kline_derived(c, a):
    js(c.kline_with_derived(a.code, a.period, a.start, a.count, a.adjust, a.anchor or ""))
def stock_quotes_detail(c, a): js(c.quotes_detail(_parse_codes(a.codes)))
def stock_tick_chart(c, a): js(c.tick_chart(a.code, a.start, a.count))
def stock_top_board(c, a): js(c.top_board(a.category))
def stock_quotes_list(c, a):
    js(c.quotes_list(a.category, a.start, a.count, a.sort_type, a.reverse, a.filter_raw))
def stock_unusual(c, a): js(c.unusual(_parse_market(a.market), a.start, a.count, a.min_volume))
def stock_chart_sampling(c, a): js(c.chart_sampling(a.code))
def stock_history_orders(c, a): js(c.history_orders(a.code, a.date))
def stock_refresh(c, a): js(c.refresh(_parse_codes(a.codes)))
def stock_price_limits(c, a): js(c.get_price_limits(a.code))
def stock_vol_profile(c, a): js(c.vol_profile(a.code, a.price_levels))
def stock_index_momentum(c, a): js(c.index_momentum(a.code, a.period))
def stock_index_info(c, a): js(c.index_info(a.code, a.top_n))
def stock_capital_flow(c, a):
    if not _require_mac():
        return
    js(c.capital_flow(a.code))
def stock_market_stat(c, a): js(c.market_stat())
def stock_board_list(c, a):
    if not _require_mac():
        return
    js(c.board_list(a.page_size, a.type, a.sort_column, a.sort_order, a.start))
def stock_board_members_mac(c, a):
    if not _require_mac():
        return
    js(c.board_members(a.board_code, a.page_size, a.start, a.sort_type, a.sort_order))
def stock_stock_blocks(c, a):
    if not _require_mac():
        return
    js(c.stock_blocks(_code_market(a.code), _code6(a.code)))
def stock_board_summary(c, a):
    if not _require_mac():
        return
    js(c.board_summary(a.board_code))
def stock_quote_list(c, a):
    if not _require_mac():
        return
    js(c.quote_list(_parse_category(a.category), a.count, a.start, a.sort_type, a.sort_order, a.exclude_flags))
def stock_server_info(c, a):
    if not _require_mac():
        return
    js(c.server_info())
def stock_symbol_info(c, a):
    if not _require_mac():
        return
    js(c.symbol_info(a.code))
def stock_company_info(c, a): js(c.company_info_cat(a.code))
def stock_company_content(c, a): js(c.company_info_content(a.code, a.filename, a.start, a.length))


def js_inner(obj):
    if hasattr(obj, "__dataclass_fields__"):
        return {f: js_inner(getattr(obj, f)) for f in obj.__dataclass_fields__}
    if isinstance(obj, dict):
        return {k: js_inner(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [js_inner(i) for i in obj]
    if isinstance(obj, bytes):
        return obj.hex()
    return obj


# ========== Futures ==========

def fut_markets(c, a): js(c.markets())
def fut_count(c, a): js(c.count())
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
def fut_kline_range(c, a):
    js(c.kline_range(a.market, a.code, a.period, a.start_date, a.end_date))
def fut_tick_chart(c, a):
    if a.date:
        js(c.history_tick_chart(a.market, a.code, a.date))
    else:
        js(c.tick_chart(a.market, a.code))
def fut_chart_sampling(c, a): js(c.chart_sampling(a.market, a.code))
def fut_quotes(c, a):
    items = []
    for raw in _parse_codes(a.codes):
        if ":" in raw:
            mid_s, code = raw.split(":", 1)
            items.append((_parse_market(mid_s), code))
        else:
            items.append((a.market, raw))
    js(c.quotes(items))
def fut_main_contract(c, a):
    code = c.get_main_contract(a.product, a.lookahead, a.market)
    js({"product": a.product, "market": a.market, "code": code})
def fut_table(c, a):
    total, next_start, text = c.table(a.start, a.mode)
    js({"total": total, "next_start": next_start, "text": text})


# ========== US (7727 扩展行情, 默认市场 74) ==========

def us_codes(c, a):
    if a.all:
        js(c.codes_all(a.market))
    else:
        js(c.codes(a.market, a.start, a.count))
def us_quote(c, a): js(c.quote(a.market, _us_code(a.code)))
def us_quote_batch(c, a): js(c.quote_batch(a.market, a.start, a.count))
def us_kline(c, a): js(c.kline(a.market, _us_code(a.code), a.period, a.start, a.count))
def us_kline_range(c, a):
    js(c.kline_range(a.market, _us_code(a.code), a.period, a.start_date, a.end_date))
def us_minute(c, a):
    code = _us_code(a.code)
    if a.date:
        js(c.history_minute(a.market, code, a.date))
    else:
        js(c.today_minute(a.market, code))
def us_trade(c, a):
    code = _us_code(a.code)
    if a.date:
        js(c.history_trade(a.market, code, a.date, a.start, a.count))
    else:
        js(c.today_trade(a.market, code, a.start, a.count))
def us_tick_chart(c, a):
    code = _us_code(a.code)
    if a.date:
        js(c.history_tick_chart(a.market, code, a.date))
    else:
        js(c.tick_chart(a.market, code))
def us_quotes(c, a):
    items = []
    for raw in _parse_codes(a.codes):
        if ":" in raw:
            mid_s, code = raw.split(":", 1)
            items.append((_parse_market(mid_s), _us_code(code)))
        else:
            items.append((a.market, _us_code(raw)))
    js(c.quotes(items))


# ========== ETF (股票协议子集) ==========

def etf_quote(c, a):
    codes = [x.strip() for x in a.codes.split(",")]
    result = []
    for code in codes:
        try:
            result.append(c.quote(code))
        except Exception as e:
            result.append({"code": code, "error": str(e)})
    js(result)


# ========== HK (港股 - 腾讯接口) ==========

def hk_quote(c, a):
    code = a.code.strip()
    q = c.quote(code)
    if q:
        js(q)
    else:
        js({"code": code, "error": "未找到数据"})

def hk_quote_batch(c, a):
    codes = [x.strip() for x in a.codes.split(",")]
    result = c.quote_batch(codes)
    js(result)


# ========== Info (7615 F10) ==========

def _info_market(a):
    if getattr(a, "market", None) is not None:
        return _parse_market(a.market)
    return _code_market(a.code)


def _announcement_from_row(item):
    from tdxproto.cninfo import Announcement
    return Announcement(
        title=item.get("title") or "",
        type=item.get("type") or "",
        date=item.get("date") or "",
        url=item.get("url") or "",
        code=item.get("code") or "",
        org_id=item.get("org_id") or "",
        announcement_id=item.get("announcement_id") or "",
        announcement_time=int(item.get("announcement_time") or 0),
        pdf_url=item.get("pdf_url") or "",
        body=item.get("body") or "",
    )

def info_news(c, a): js(c.news(_info_market(a), _code6(a.code)))
def info_announcements(c, a): js(c.announcements(_info_market(a), _code6(a.code)))
def info_roadshows(c, a): js(c.roadshows(_info_market(a), _code6(a.code)))
def info_research(c, a): js(c.research_reports(_code6(a.code), a.page, a.page_size))
def info_company_news(c, a): js(c.company_news(_code6(a.code), a.section, a.keyword, a.rating, a.page, a.page_size))
def info_stock_info(c, a): js(c.stock_info(_code6(a.code)))
def info_profile(c, a): js(c.company_profile(_code6(a.code), a.section))
def info_business(c, a): js(c.business_composition(_code6(a.code), a.report_date))
def info_finance_report(c, a): js(c.finance_report(_code6(a.code), a.report_type))
def info_diagnosis(c, a): js(c.finance_diagnosis(_code6(a.code), a.section, a.scope))
def info_dividend(c, a): js(c.dividend_financing(_code6(a.code), a.section))
def info_score(c, a): js(c.stock_score(_code6(a.code), a.section, a.arg))
def info_forecast(c, a): js(c.profit_forecast(_code6(a.code)))
def info_shareholder(c, a): js(c.shareholder_change_plans(_code6(a.code), a.page, a.page_size))
def info_northbound(c, a): js(c.northbound_holding(_code6(a.code), a.section, a.filter_value, a.page, a.page_size))
def info_governance(c, a): js(c.governance(_code6(a.code), a.section, a.arg))
def info_topics(c, a): js(c.hot_topics(_code6(a.code), a.section))
def info_snapshot(c, a):
    collector = InfoCollector(c)
    js(collector.snapshot(_info_market(a), _code6(a.code)))


# ========== Cninfo ==========

def cninfo_search(c, a):
    js(c.search(_code6(a.code), count=a.count, page=a.page, searchkey=a.keyword, category=a.category, plate=a.plate, se_date=a.se_date))
def cninfo_batch(c, a):
    js(c.get_announcements_batch(_parse_codes(a.codes), count=a.count, page=a.page, searchkey=a.keyword, category=a.category, plate=a.plate, se_date=a.se_date))
def cninfo_detail(c, a):
    rows = c.get_announcements(_code6(a.code), count=a.count, page=a.page, searchkey=a.keyword)
    if not rows:
        js({"code": a.code, "error": "未找到公告"}); return
    js(c.get_announcement_detail(_announcement_from_row(rows[0])))
def cninfo_pdf(c, a):
    rows = c.get_announcements(_code6(a.code), count=1, page=1)
    if not rows:
        js({"code": a.code, "error": "未找到公告"}); return
    ann = _announcement_from_row(rows[0])
    path = c.download_pdf(ann, dest_dir=a.dest)
    js({"path": path, "title": ann.title})


# ========== CCPM ==========

def ccpm_rank(c, a): js(c.get_rank(a.product, date=a.date, refresh=a.refresh))
def ccpm_latest(c, a): js(c.latest_rank(a.product))
def ccpm_meta(c, a): js(c.get_products_meta())


# ========== MAC ==========

def mac_board_list(c, a): js(c.board_list(a.page_size, a.type, a.sort_column, a.sort_order, a.start))
def mac_board_members(c, a): js(c.board_members(a.board_code, a.page_size, a.start, a.sort_type, a.sort_order))
def mac_stock_blocks(c, a): js(c.stock_blocks(_code_market(a.code), _code6(a.code)))
def mac_board_summary(c, a): js(c.board_summary(a.board_code))
def mac_change_ranking(c, a): js(c.board_change_ranking(a.type, a.days, a.top_n, a.sort_order))
def mac_amount_ranking(c, a): js(c.board_amount_ranking(a.type, a.top_n, a.sort_order))
def mac_volume_ranking(c, a): js(c.board_volume_ranking(a.type, a.top_n, a.sort_order))
def mac_net_ranking(c, a): js(c.board_main_net_amount_ranking(a.type, a.top_n, a.sort_order))
def mac_category_quotes(c, a):
    js(c.category_quotes(_parse_category(a.category), a.page_size, a.start, a.sort_type, a.sort_order, a.exclude_flags))
def mac_capital_flow(c, a): js(c.capital_flow(_code_market(a.code), _code6(a.code)))
def mac_server_info(c, a): js(c.server_info())
def mac_symbol_info(c, a): js(c.symbol_info(_code_market(a.code), _code6(a.code)))


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

def build_parser():
    p = argparse.ArgumentParser(description="通达信全协议解析器 (7709+7727+7615)")
    sub = p.add_subparsers(dest="proto")

    sc = sub.add_parser("scan", help="主站可用性扫描与测速")
    scs = sc.add_subparsers(dest="scan_type")
    a = scs.add_parser("stock", help="扫描 7709 A股主站")
    a.add_argument("--workers", type=int, default=64)
    a.add_argument("--timeout", type=float, default=2.0)
    a = scs.add_parser("futures", help="扫描 7727 期货主站")
    a.add_argument("--workers", type=int, default=64)
    a.add_argument("--timeout", type=float, default=2.0)

    s = sub.add_parser("stock", help="7709 股票行情")
    ss = s.add_subparsers(dest="cmd")
    a = ss.add_parser("count", help="0x044e 代码数量"); a.add_argument("market")
    a = ss.add_parser("codes", help="0x044d 代码表"); a.add_argument("market"); a.add_argument("--start", type=int, default=0); a.add_argument("--limit", type=int, default=1600); a.add_argument("--all", action="store_true")
    a = ss.add_parser("quote", help="0x054c 批量快照"); a.add_argument("codes")
    a = ss.add_parser("kline", help="0x052d K线(含复权)"); a.add_argument("code"); a.add_argument("--period", default="day"); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=100, dest="count", metavar="COUNT"); a.add_argument("--adjust", default=""); a.add_argument("--anchor", default="")
    a = ss.add_parser("kline-all", help="自动翻页拉全量K线"); a.add_argument("code"); a.add_argument("--period", default="day"); a.add_argument("--adjust", default="")
    a = ss.add_parser("kline-120m", help="120分钟K线"); a.add_argument("code"); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=400)
    a = ss.add_parser("kline-derived", help="K线+涨跌幅衍生字段"); a.add_argument("code"); a.add_argument("--period", default="day"); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=100); a.add_argument("--adjust", default=""); a.add_argument("--anchor", default="")
    a = ss.add_parser("minute", help="0x0feb/0x0537 分时"); a.add_argument("code"); a.add_argument("--date", default=None)
    a = ss.add_parser("aux", help="0x051b 分时副图"); a.add_argument("code")
    a = ss.add_parser("sparkline", help="0x0fd1 小走势图"); a.add_argument("code")
    a = ss.add_parser("trade", help="0x0fc6/0x0fc5 成交明细"); a.add_argument("code"); a.add_argument("date", nargs="?"); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=100); a.add_argument("--all", action="store_true")
    a = ss.add_parser("auction", help="0x056a 集合竞价"); a.add_argument("code"); a.add_argument("--mode", type=int, default=3)
    a = ss.add_parser("quotes-detail", help="五档详细行情"); a.add_argument("codes")
    a = ss.add_parser("tick-chart", help="分时明细"); a.add_argument("code"); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=0xBA00)
    a = ss.add_parser("top-board", help="涨跌停/涨速排行"); a.add_argument("--category", type=int, default=0)
    a = ss.add_parser("quotes-list", help="板块行情列表"); a.add_argument("category", type=int); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=80); a.add_argument("--sort-type", type=int, default=0); a.add_argument("--reverse", action="store_true"); a.add_argument("--filter-raw", type=int, default=0)
    a = ss.add_parser("unusual", help="主力大单监控"); a.add_argument("--market", default="sz"); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=600); a.add_argument("--min-volume", type=int, default=1000)
    a = ss.add_parser("chart-sampling", help="K线采样"); a.add_argument("code")
    a = ss.add_parser("history-orders", help="历史委托"); a.add_argument("code"); a.add_argument("date")
    a = ss.add_parser("refresh", help="增量刷新"); a.add_argument("codes")
    a = ss.add_parser("price-limits", help="个股涨跌停价"); a.add_argument("code")
    a = ss.add_parser("vol-profile", help="成交量分布"); a.add_argument("code"); a.add_argument("--price-levels", type=int, default=20)
    a = ss.add_parser("index-momentum", help="指数动能"); a.add_argument("code"); a.add_argument("--period", type=int, default=5)
    a = ss.add_parser("index-info", help="指数成分行情"); a.add_argument("code"); a.add_argument("--top-n", type=int, default=50)
    a = ss.add_parser("equity", help="0x000f 股本变迁+除权除息"); a.add_argument("code")
    a = ss.add_parser("finance", help="0x0010 财务基础"); a.add_argument("codes")
    a = ss.add_parser("limits", help="0x0452 涨跌停限制"); a.add_argument("--start", type=int, default=0)
    a = ss.add_parser("turnover", help="本地计算换手率"); a.add_argument("code")
    a = ss.add_parser("info", help="一键全部数据"); a.add_argument("code")
    a = ss.add_parser("blocks", help="板块列表(含指数代码)"); a.add_argument("--type", type=int, default=0)
    a = ss.add_parser("block-members", help="板块成分股"); a.add_argument("block_code")
    a = ss.add_parser("workday", help="工作日判断"); a.add_argument("--date", default=None)
    a = ss.add_parser("capital-flow", help="个股资金流向"); a.add_argument("code")
    a = ss.add_parser("market-stat", help="市场涨跌家数统计")
    a = ss.add_parser("board-list", help="MAC板块列表"); a.add_argument("--type", type=int, default=0); a.add_argument("--page-size", type=int, default=150); a.add_argument("--sort-column", type=int, default=0); a.add_argument("--sort-order", type=int, default=1); a.add_argument("--start", type=int, default=0)
    a = ss.add_parser("board-members-mac", help="MAC板块成分股"); a.add_argument("board_code"); a.add_argument("--page-size", type=int, default=80); a.add_argument("--start", type=int, default=0); a.add_argument("--sort-type", type=int, default=0); a.add_argument("--sort-order", type=int, default=1)
    a = ss.add_parser("stock-blocks", help="个股所属板块"); a.add_argument("code")
    a = ss.add_parser("board-summary", help="板块汇总"); a.add_argument("board_code")
    a = ss.add_parser("quote-list", help="市场分类报价"); a.add_argument("category"); a.add_argument("--count", type=int, default=80); a.add_argument("--start", type=int, default=0); a.add_argument("--sort-type", type=int, default=0); a.add_argument("--sort-order", type=int, default=1); a.add_argument("--exclude-flags", type=int, default=0)
    a = ss.add_parser("server-info", help="MAC服务器信息")
    a = ss.add_parser("symbol-info", help="个股详细信息"); a.add_argument("code")
    a = ss.add_parser("company-info", help="公司信息类别"); a.add_argument("code")
    a = ss.add_parser("company-content", help="公司信息内容"); a.add_argument("code"); a.add_argument("filename"); a.add_argument("--start", type=int, default=0); a.add_argument("--length", type=int, default=0)

    f = sub.add_parser("futures", help="7727 期货行情")
    fs = f.add_subparsers(dest="cmd")
    a = fs.add_parser("markets", help="0x23F4 交易所列表")
    a = fs.add_parser("codes", help="0x23F5 代码表"); a.add_argument("market", type=int); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=200); a.add_argument("--all", action="store_true")
    a = fs.add_parser("count", help="0x23F0 品种数量")
    a = fs.add_parser("quote", help="0x23FA 五档行情"); a.add_argument("code"); a.add_argument("--market", type=int, default=47)
    a = fs.add_parser("quote-batch", help="0x2400 批量行情"); a.add_argument("--market", type=int, default=47); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=200)
    a = fs.add_parser("kline", help="0x23FF K线"); a.add_argument("code"); a.add_argument("--market", type=int, default=47); a.add_argument("--period", default="day"); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=100)
    a = fs.add_parser("kline-range", help="按日期范围K线"); a.add_argument("code"); a.add_argument("--market", type=int, default=47); a.add_argument("--period", default="day"); a.add_argument("--start-date"); a.add_argument("--end-date")
    a = fs.add_parser("minute", help="0x240B/0x240C 分时"); a.add_argument("code"); a.add_argument("--market", type=int, default=47); a.add_argument("--date", default=None)
    a = fs.add_parser("trade", help="0x23FC/0x2406 成交"); a.add_argument("code"); a.add_argument("date", nargs="?"); a.add_argument("--market", type=int, default=47); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=100)
    a = fs.add_parser("tick-chart", help="分时图"); a.add_argument("code"); a.add_argument("--market", type=int, default=47); a.add_argument("--date", default=None)
    a = fs.add_parser("chart-sampling", help="K线采样"); a.add_argument("code"); a.add_argument("--market", type=int, default=47)
    a = fs.add_parser("quotes", help="多品种详细行情"); a.add_argument("codes"); a.add_argument("--market", type=int, default=47)
    a = fs.add_parser("main-contract", help="主力合约"); a.add_argument("product"); a.add_argument("--market", type=int, default=47); a.add_argument("--lookahead", type=int, default=3)
    a = fs.add_parser("table", help="表格数据"); a.add_argument("--start", type=int, default=0); a.add_argument("--mode", type=int, default=1)

    u = sub.add_parser("us", help="7727 美股行情 (市场 74)")
    us = u.add_subparsers(dest="cmd")
    a = us.add_parser("codes", help="0x23F5 代码表"); a.add_argument("--market", type=int, default=74); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=200); a.add_argument("--all", action="store_true")
    a = us.add_parser("quote", help="0x23FA 五档行情"); a.add_argument("code"); a.add_argument("--market", type=int, default=74)
    a = us.add_parser("quote-batch", help="0x2400 批量行情"); a.add_argument("--market", type=int, default=74); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=200)
    a = us.add_parser("kline", help="0x23FF K线"); a.add_argument("code"); a.add_argument("--market", type=int, default=74); a.add_argument("--period", default="day"); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=100)
    a = us.add_parser("kline-range", help="按日期范围K线"); a.add_argument("code"); a.add_argument("--market", type=int, default=74); a.add_argument("--period", default="day"); a.add_argument("--start-date"); a.add_argument("--end-date")
    a = us.add_parser("minute", help="0x240B/0x240C 分时"); a.add_argument("code"); a.add_argument("--market", type=int, default=74); a.add_argument("--date", default=None)
    a = us.add_parser("trade", help="0x23FC/0x2406 成交"); a.add_argument("code"); a.add_argument("date", nargs="?"); a.add_argument("--market", type=int, default=74); a.add_argument("--start", type=int, default=0); a.add_argument("--count", type=int, default=100)
    a = us.add_parser("tick-chart", help="分时图"); a.add_argument("code"); a.add_argument("--market", type=int, default=74); a.add_argument("--date", default=None)
    a = us.add_parser("quotes", help="多品种详细行情"); a.add_argument("codes"); a.add_argument("--market", type=int, default=74)

    e = sub.add_parser("etf", help="ETF 行情 (股票协议)")
    es = e.add_subparsers(dest="cmd")
    a = es.add_parser("quote", help="批量行情快照"); a.add_argument("codes")

    h = sub.add_parser("hk", help="港股行情 (腾讯接口)")
    hs = h.add_subparsers(dest="cmd")
    a = hs.add_parser("quote", help="单只港股行情"); a.add_argument("code")
    a = hs.add_parser("quote-batch", help="批量港股行情"); a.add_argument("codes")

    i = sub.add_parser("info", help="7615 F10 资讯")
    isp = i.add_subparsers(dest="cmd")
    a = isp.add_parser("news", help="实时新闻"); a.add_argument("code"); a.add_argument("--market", default=None)
    a = isp.add_parser("announcements", help="公告列表"); a.add_argument("code"); a.add_argument("--market", default=None)
    a = isp.add_parser("roadshows", help="路演列表"); a.add_argument("code"); a.add_argument("--market", default=None)
    a = isp.add_parser("research", help="研报列表"); a.add_argument("code"); a.add_argument("--page", type=int, default=1); a.add_argument("--page-size", type=int, default=20)
    a = isp.add_parser("company-news", help="公司资讯"); a.add_argument("code"); a.add_argument("--section", default="gsyj"); a.add_argument("--keyword", default=""); a.add_argument("--rating", default="0"); a.add_argument("--page", type=int, default=1); a.add_argument("--page-size", type=int, default=20)
    a = isp.add_parser("stock-info", help="股票基础信息"); a.add_argument("code")
    a = isp.add_parser("profile", help="公司概况"); a.add_argument("code"); a.add_argument("--section", default="8")
    a = isp.add_parser("business", help="主营构成"); a.add_argument("code"); a.add_argument("--report-date", default=None)
    a = isp.add_parser("finance-report", help="财务报表"); a.add_argument("code"); a.add_argument("--report-type", default="zcfzb")
    a = isp.add_parser("diagnosis", help="财务诊断"); a.add_argument("code"); a.add_argument("--section", default="yynl"); a.add_argument("--scope", default="0")
    a = isp.add_parser("dividend", help="分红融资"); a.add_argument("code"); a.add_argument("--section", default="fh")
    a = isp.add_parser("score", help="个股总评"); a.add_argument("code"); a.add_argument("--section", default="pf"); a.add_argument("--arg", default="")
    a = isp.add_parser("forecast", help="盈利预测"); a.add_argument("code")
    a = isp.add_parser("shareholder", help="股东增减持"); a.add_argument("code"); a.add_argument("--page", type=int, default=1); a.add_argument("--page-size", type=int, default=20)
    a = isp.add_parser("northbound", help="沪深股通持股"); a.add_argument("code"); a.add_argument("--section", default="bszj"); a.add_argument("--filter-value", default=""); a.add_argument("--page", type=int, default=1); a.add_argument("--page-size", type=int, default=20)
    a = isp.add_parser("governance", help="资本运作治理"); a.add_argument("code"); a.add_argument("--section", default="wgcl"); a.add_argument("--arg", default="")
    a = isp.add_parser("topics", help="热点题材"); a.add_argument("code"); a.add_argument("--section", default="zttzbkz")
    a = isp.add_parser("snapshot", help="F10资料快照"); a.add_argument("code"); a.add_argument("--market", default=None)

    n = sub.add_parser("cninfo", help="巨潮资讯公告")
    nsp = n.add_subparsers(dest="cmd")
    a = nsp.add_parser("search", help="公告检索"); a.add_argument("code"); a.add_argument("--count", type=int, default=30); a.add_argument("--page", type=int, default=1); a.add_argument("--keyword", default=""); a.add_argument("--category", default=""); a.add_argument("--plate", default=""); a.add_argument("--se-date", default="")
    a = nsp.add_parser("batch", help="批量公告"); a.add_argument("codes"); a.add_argument("--count", type=int, default=10); a.add_argument("--page", type=int, default=1); a.add_argument("--keyword", default=""); a.add_argument("--category", default=""); a.add_argument("--plate", default=""); a.add_argument("--se-date", default="")
    a = nsp.add_parser("detail", help="公告正文"); a.add_argument("code"); a.add_argument("--count", type=int, default=1); a.add_argument("--page", type=int, default=1); a.add_argument("--keyword", default="")
    a = nsp.add_parser("pdf", help="下载公告PDF"); a.add_argument("code"); a.add_argument("--dest", default=".")

    ccp = sub.add_parser("ccpm", help="中金所持仓排名")
    csp = ccp.add_subparsers(dest="cmd")
    a = csp.add_parser("rank", help="指定日期持仓排名"); a.add_argument("product"); a.add_argument("--date", default=None); a.add_argument("--refresh", action="store_true")
    a = csp.add_parser("latest", help="最新持仓排名"); a.add_argument("product")
    a = csp.add_parser("meta", help="品种元数据")

    m = sub.add_parser("mac", help="MAC 板块/资金")
    msp = m.add_subparsers(dest="cmd")
    a = msp.add_parser("board-list", help="板块列表"); a.add_argument("--type", type=int, default=0); a.add_argument("--page-size", type=int, default=150); a.add_argument("--sort-column", type=int, default=0); a.add_argument("--sort-order", type=int, default=1); a.add_argument("--start", type=int, default=0)
    a = msp.add_parser("board-members", help="板块成分股"); a.add_argument("board_code"); a.add_argument("--page-size", type=int, default=80); a.add_argument("--start", type=int, default=0); a.add_argument("--sort-type", type=int, default=0); a.add_argument("--sort-order", type=int, default=1)
    a = msp.add_parser("stock-blocks", help="个股所属板块"); a.add_argument("code")
    a = msp.add_parser("board-summary", help="板块汇总"); a.add_argument("board_code")
    a = msp.add_parser("change-ranking", help="板块涨跌幅排行"); a.add_argument("--type", type=int, default=0); a.add_argument("--days", type=int, default=5); a.add_argument("--top-n", type=int, default=100); a.add_argument("--sort-order", type=int, default=1)
    a = msp.add_parser("amount-ranking", help="板块成交额排行"); a.add_argument("--type", type=int, default=0); a.add_argument("--top-n", type=int, default=100); a.add_argument("--sort-order", type=int, default=1)
    a = msp.add_parser("volume-ranking", help="板块成交量排行"); a.add_argument("--type", type=int, default=0); a.add_argument("--top-n", type=int, default=100); a.add_argument("--sort-order", type=int, default=1)
    a = msp.add_parser("net-ranking", help="板块主力净流入排行"); a.add_argument("--type", type=int, default=0); a.add_argument("--top-n", type=int, default=100); a.add_argument("--sort-order", type=int, default=1)
    a = msp.add_parser("category-quotes", help="市场分类报价"); a.add_argument("category"); a.add_argument("--page-size", type=int, default=80); a.add_argument("--start", type=int, default=0); a.add_argument("--sort-type", type=int, default=0); a.add_argument("--sort-order", type=int, default=1); a.add_argument("--exclude-flags", type=int, default=0)
    a = msp.add_parser("capital-flow", help="个股资金流向"); a.add_argument("code")
    a = msp.add_parser("server-info", help="服务器信息")
    a = msp.add_parser("symbol-info", help="个股详细信息"); a.add_argument("code")
    return p


STOCK_HANDLERS = {
    "count": stock_count, "codes": stock_codes, "quote": stock_quote,
    "kline": stock_kline, "kline-all": stock_kline_all,
    "kline-120m": stock_kline_120m, "kline-derived": stock_kline_derived,
    "minute": stock_minute, "aux": stock_aux, "sparkline": stock_sparkline,
    "trade": stock_trade, "auction": stock_auction,
    "quotes-detail": stock_quotes_detail, "tick-chart": stock_tick_chart,
    "top-board": stock_top_board, "quotes-list": stock_quotes_list,
    "unusual": stock_unusual, "chart-sampling": stock_chart_sampling,
    "history-orders": stock_history_orders, "refresh": stock_refresh,
    "price-limits": stock_price_limits, "vol-profile": stock_vol_profile,
    "index-momentum": stock_index_momentum, "index-info": stock_index_info,
    "equity": stock_equity, "finance": stock_finance,
    "limits": stock_limits, "turnover": stock_turnover, "info": stock_info,
    "blocks": stock_blocks, "block-members": stock_block_members,
    "workday": stock_workday, "capital-flow": stock_capital_flow,
    "market-stat": stock_market_stat, "board-list": stock_board_list,
    "board-members-mac": stock_board_members_mac, "stock-blocks": stock_stock_blocks,
    "board-summary": stock_board_summary, "quote-list": stock_quote_list,
    "server-info": stock_server_info, "symbol-info": stock_symbol_info,
    "company-info": stock_company_info, "company-content": stock_company_content,
}

FUTURES_HANDLERS = {
    "markets": fut_markets, "count": fut_count, "codes": fut_codes,
    "quote": fut_quote, "quote-batch": fut_quote_batch,
    "kline": fut_kline, "kline-range": fut_kline_range,
    "minute": fut_minute, "trade": fut_trade, "tick-chart": fut_tick_chart,
    "chart-sampling": fut_chart_sampling, "quotes": fut_quotes,
    "main-contract": fut_main_contract, "table": fut_table,
}

US_HANDLERS = {
    "codes": us_codes, "quote": us_quote, "quote-batch": us_quote_batch,
    "kline": us_kline, "kline-range": us_kline_range,
    "minute": us_minute, "trade": us_trade, "tick-chart": us_tick_chart,
    "quotes": us_quotes,
}

INFO_HANDLERS = {
    "news": info_news, "announcements": info_announcements, "roadshows": info_roadshows,
    "research": info_research, "company-news": info_company_news,
    "stock-info": info_stock_info, "profile": info_profile, "business": info_business,
    "finance-report": info_finance_report, "diagnosis": info_diagnosis,
    "dividend": info_dividend, "score": info_score, "forecast": info_forecast,
    "shareholder": info_shareholder, "northbound": info_northbound,
    "governance": info_governance, "topics": info_topics, "snapshot": info_snapshot,
}

CNINFO_HANDLERS = {
    "search": cninfo_search, "batch": cninfo_batch,
    "detail": cninfo_detail, "pdf": cninfo_pdf,
}

CCPM_HANDLERS = {"rank": ccpm_rank, "latest": ccpm_latest, "meta": ccpm_meta}

MAC_HANDLERS = {
    "board-list": mac_board_list, "board-members": mac_board_members,
    "stock-blocks": mac_stock_blocks, "board-summary": mac_board_summary,
    "change-ranking": mac_change_ranking, "amount-ranking": mac_amount_ranking,
    "volume-ranking": mac_volume_ranking, "net-ranking": mac_net_ranking,
    "category-quotes": mac_category_quotes, "capital-flow": mac_capital_flow,
    "server-info": mac_server_info, "symbol-info": mac_symbol_info,
}


def main(argv=None):
    p = build_parser()
    args = p.parse_args(argv)
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
            h = STOCK_HANDLERS.get(args.cmd)
            if h: h(c, args)

    elif args.proto == "futures":
        with FuturesClient(timeout=5) as c:
            h = FUTURES_HANDLERS.get(args.cmd)
            if h: h(c, args)

    elif args.proto == "us":
        with FuturesClient(timeout=5) as c:
            h = US_HANDLERS.get(args.cmd)
            if h: h(c, args)

    elif args.proto == "etf":
        with StockClient(timeout=5) as c:
            if args.cmd == "quote":
                etf_quote(c, args)

    elif args.proto == "hk":
        c = HkClient()
        if args.cmd == "quote":
            hk_quote(c, args)
        elif args.cmd == "quote-batch":
            hk_quote_batch(c, args)

    elif args.proto == "info":
        h = INFO_HANDLERS.get(args.cmd)
        if h: h(InfoClient(), args)

    elif args.proto == "cninfo":
        h = CNINFO_HANDLERS.get(args.cmd)
        if h: h(CninfoClient(), args)

    elif args.proto == "ccpm":
        h = CCPM_HANDLERS.get(args.cmd)
        if h: h(CcpmClient(), args)

    elif args.proto == "mac":
        if not _require_mac():
            return
        with MacClient() as c:
            h = MAC_HANDLERS.get(args.cmd)
            if h: h(c, args)


if __name__ == "__main__":
    main()
