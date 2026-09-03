# User Instruction Memory

This file records user instructions, preferences, and teachings for reference in future interactions.

## Format

### User Instruction Entry
User instruction entries should follow this format:

[User Instruction Summary]
- Date: [YYYY-MM-DD]
- Context: [Mentioned scenario or time]
- Instructions:
  - [Content of user teaching or instruction, described line by line]

### Project Knowledge Entry
Entries discovered by the Agent during task execution should follow this format:

[Project Knowledge Summary]
- Date: [YYYY-MM-DD]
- Context: Discovered by Agent while performing [specific task description]
- Category: [Operations & Deployment|Build Methods|Testing Methods|Troubleshooting & Debugging|Workflow & Collaboration|Environment Configuration]
- Instructions:
  - [Specific knowledge points, described line by line]

## Deduplication Strategy
- Before adding a new entry, check for similar or identical instructions.
- If a duplicate is found, skip the new entry or merge it with the existing one.
- When merging, update the context or date information.
- This helps avoid redundant entries and keeps the memory file tidy.

## Entries



[tdxproto Bug Fix: kline 无效代码垃圾数据]
- Date: 2026-09-02
- Context: 发现 kline() 对无效股票代码（如 sh999999）返回垃圾数据
- Category: Troubleshooting & Debugging
- Instructions:
  - _p_kline 新增 date/price 校验：过滤 month 不在 1-12、day 不在 1-31、year 不在 2000-2100、open <= 0 的行
  - 根因：部分 TDX 服务器对无效代码返回 buffer 残留数据（包含其他代码的合法 K 线 + 随机垃圾）
  - 约 60% 的健康 host 对无效代码返回 0 bars（正确），~10% 返回 12 条"看起来合法"的垃圾数据
  - failover 条件 (count > 10 and len(rows) < count * 0.3) 在垃圾数据场景下不触发（800 条垃圾数据 > 240 阈值）
  - 修复后：所有不可能日期/价格的行被过滤，无效代码返回 0 或极少条数
  - 已知限制：极少数 host 仍可能返回少量"合法外观"的垃圾数据（buffer 残留），建议批量采集用 auto_reconnect=False

[tdxproto 并发模型]
- Date: 2026-09-02
- Context: 调查 tdxproto 的并发模型以回答用户问题
- Category: Build Methods
- Instructions:
  - StockClient 单线程连接，通过 Tube 管道处理请求/响应
  - 批量采集 collect_batch_kline() 使用 ThreadPoolExecutor(max_workers=32)，每个线程独立 StockClient
  - scan_stock/scan_futures 使用 ThreadPoolExecutor(workers=64)
  - FuturesClient 无内置批量采集函数，用户需自行使用 ThreadPoolExecutor
  - 期货延迟 ~34ms，建议 max_workers=16-32
  - 批量采集应设置 failover=False 跳过 6s failover 循环

[Batch K-line Collection Performance & Feature Parity]
- Date: 2026-02-04
- Context: Integrated easy_tdx collection pipeline into tdxproto; compared feature parity
- Category: Build Methods
- Instructions:
  - Use `collect_batch_kline()` from `tdxproto.stock.batch_kline` for bulk K-line collection
  - Set `max_workers=64` and `reuse_client=False` for optimal performance
  - Set `failover=False` for batch mode to skip 6s failover loop on empty responses
  - Pre-scan hosts with `scan_stock()` before batch collection
  - IMPORTANT: codes_all() returns ALL securities (indices, funds, bonds), not just stocks
  - Filter by code prefix to get real A-shares: 000/001/002/003 (SZ main), 300/301 (SZ gem), 600/601/603/605 (SH main), 688 (SH star)
  - Real A-share count: 5,219 (not 49,240 as previously incorrectly stated)
  - Actual performance: 2117 stocks in 73.8s (99.9% success, 28.7 stocks/sec)
  - Projected for 5219 stocks: ~1.1 min (target was 8 min for 6000)
  - easy_tdx reference: https://github.com/handsomejustin/easy_tdx
  - Missing features from easy_tdx: 北交所 (BJ market), 期货 (futures), 龙虎榜 (top board)
  - StockClient 单线程连接，批量采集用 ThreadPoolExecutor(max_workers=32)，每个线程独立 StockClient
  - FuturesClient 无内置批量采集函数；期货延迟 ~34ms，建议 max_workers=16-32
  - Single-threaded kline: ~0.025 sec/stock (normal), ~6 sec (timeout + failover)
  - Batch kline bottleneck: failover timeout (6s) dominates when stock has no data
  - Solution: use `auto_reconnect=False` and `failover=False` for batch mode
  - Performance with 100 threads: ~563 stocks/sec (5219 stocks in ~8 seconds)
  - Real A-share count: 5,219 (2,900 SZ + 2,319 SH)
  - get_price_limits(code) implemented: supports 主板/创业板/科创板/北交所/ST
  - IMPORTANT: get_price_limits uses split_code() to extract pure digits for prefix check
  - refresh(codes) returns empty - server may not support 0x0547 command
  - quote_list(category) via MAC works but prices may be 0.0 for some stocks
  - get_history_fund_flow not implemented - calculate from history_trade manually
  - Capital flow caveat (Issue #55): 0x0fb5 tick-by-tick uses per-trade-amount bins; high-price stock small-bins <1% total amount, main bins >95%; main_net_inflow ≈ daily active buy-sell imbalance NOT true capital flow
  - Eastmoney/Tonghuashun "主力净流入" uses L2 order-based caliber - DO NOT MIX with tdxproto data in same factor/table (~14% signal overlap)
  - SecurityQuote special fields: trading_status (0x8020=停牌), open_amount (auction amount, stocks only; index meaningless), server_time (HH:MM:SS.mmm), unknown_2/3 (index: auction/100; stock: auction/100), unknown_5~8 (reserved, always 0)
  - AsyncTdxClient has async counterparts for all StockClient methods
  - 北交所 count(2) returns 379 but list/codes_all times out - need dedicated BJ server
  - 北交所 kline/day/5m/week 在支持它的服务器上完全可用；推荐 BJ 专用 host: 111.229.247.189, 150.158.160.2, 180.153.18.170, 124.71.187.122, 115.238.56.198, 115.238.90.165, 218.75.126.9 等（共约 50+ 台）
  - easy_tdx 默认服务器列表（~/.easy_tdx/config.json + 硬编码 51 个）大部分与 tdxproto 重叠，9 个独有服务器中 3 个支持北交所
  - ETF（sh510xxx/sh513xxx/sz159xxx）系数 0.001，分钟线 vol 返回真实成交量（非NaN），is_idx=False
  - TDX 协议字段单位总结：价格原始×100（coefficient 已处理），成交量原始÷100（周/月/季/年线×100还原），成交额原始÷100
  - tdxproto STOCK_HOSTS_LARGE: 82 hosts（含 easy_tdx 推荐的 180.153.18.170, 115.238.56.198, 115.238.90.165, 218.75.126.9）
  - 北交所采集建议：使用完整 STOCK_HOSTS_LARGE，failover 自动选到支持北交所的 host
  - 期货服务器：FUTURES_HOSTS_LARGE (16 hosts, port 7727)，与 easy_tdx _FALLBACK_EX_HOSTS 完全一致
  - 期货采集能力：中金所(IFL0/ICL0/IHL0)、上海黄金(Au99.99/Ag(T+D))、郑商所(APL8/CFL8)、大商所(JDL8/LHL8)、上期所(RBL8/ADL8) 均可正常采集
  - 期货代码格式：主力连续 L0/L7/L8 后缀（IFL0, APL8），具体合约 YYYYMM 后缀（IF2609, RB2610）
  - get_main_contract 仅支持 IF/IC/IH/IM 等金融期货，商品期货需手动查找主力合约代码

[tdxproto Vol 语义修正（issue #64 移植）]
- Date: 2026-09-02
- Context: 移植 easy_tdx issue #64 的 K 线 vol 字段协议语义修正到 tdxproto
- Category: Build Methods
- Instructions:
  - `_p_kline` 新增 `market` 参数（int），用于精确判断是否指数（避免 000xxx 歧义）
  - 指数判定逻辑: `code` 有 `sh` 前缀，或 `market==1(沪)` 且纯数字部分以 000/399/88 开头
  - 指数分钟线（cat 0/1/2/3/7/8）：vol 置 NaN（f1 实为成交额百元，非成交量）
  - 周/月/季/年线（cat 5/6/10/11）：vol × 100 还原真实成交量
  - 指数 K 线每条记录末尾多 4 字节（上涨家数+下跌家数），需跳过否则错位
  - `_make_kline` 中 NaN vol → volume=0（保持 Kline.volume 为 int 类型）
  - `KLINE_CAT` 新增 `"1m": 7` 和 `"3m": 8` 映射（此前缺失）
  - `_find_host_returning_data` 通用故障转移方法暂未接入，暂不修改

[tdxproto Bug Fix & Features: v0.0.2]
- Date: 2026-09-02
- Context: 移植 easy_tdx v1.30.3 新特性到 tdxproto
- Category: Troubleshooting & Debugging
- Instructions:
  - stock workday 移除 dateutil 依赖，改用 datetime.fromisoformat
  - --count > 65535 校验移至 parse_code 之前（避免 UnboundLocalError）
  - tick_chart ETF/bond 价格需乘 coefficient（_p_tick_chart 已修复）
  - index_info 从 codes_all 的 list[dict] 取 item["code"]
  - K 线下界改为 1990（保留真实数据，不再硬截 2010）
  - 短包解析器返回已解析部分或 []，避免 IndexError
  - 重连前 close 旧 socket + 停旧心跳线程；_send_recv_quick 超时后废弃连接
  - UNUSUAL_TYPE_NAMES 25 种异常类型（含 0x13 竞价试买/0x14 竞价试卖/0x16 盘中强势）
  - describe_unusual(code, v1=0, v2=0) 返回类型描述
  - kline_120m(code, start, count) 聚合两根 60M bar
  - CcpmClient 中金所持仓排名：get_rank/product/latest_rank/get_products_meta，缓存 ~/.easy_tdx/cache/ccpm/
  - verify_qfq(bars, equity) QFQ 交叉验证：formula 计算 vs gap 检测
  - README 重写（578→150行），版本同步 pyproject.toml / __init__.py / README
  - 316 tests pass, 8 skipped（系统测试需外网）

[Test: mock 数据格式]
- Category: Testing Methods
- Instructions:
  - sh000001 是指数，_p_kline 每条末尾多 4 字节；测试时 bars_data 需额外 append struct.pack("<I", 0) 或用 sz000001 跳过
  - 测试 bare except 时用 patch('tdxproto.stock.client.socket.socket')，不用 patch socket.create_connection
