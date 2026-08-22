# tdxproto — 通达信全协议解析器

纯 Python 二进制协议实现，零外部依赖。覆盖 7709 A股 + 7727 期货双协议，自动故障转移。

## 特性

- **零依赖** — 仅使用 Python 标准库 (`socket`/`struct`/`zlib`)
- **双协议** — 7709 (A股: 行情/K线/分时/成交/财务/板块) + 7727 (期货/扩展行情)
- **多数据源** — 巨潮资讯网公告检索 (`cninfo`) + 7615 F10 资讯 HTTP 网关 (`info`)
- **IP 健康监控** — 自动扫描、测速、持久化、故障转移
- **断线自愈** — 同主机退避重试 + 跨主机故障转移 + 命令失败后 NOP 重连
- **板块解析** — `.dat` 板块文件本地解析
- **本地计算** — 复权因子、换手率、除权除息、竞价快照
- **数据模型** — 14 个 dataclass 统一表示 (Quote/Kline/Minute/Trade/...)
- **258 个测试** — 单元/组件全覆盖

## 安装

Python 3.9+，零第三方依赖。

```bash
pip install tdxproto
```

## 快速开始

### 股票行情 (7709)

```python
from tdxproto import StockClient

with StockClient() as client:
    # K 线 (1m/5m/15m/30m/60m/day/week/month/quarter/year)
    klines = client.kline("sz000001", "day", 0, 10)
    for k in klines:
        print(f"{k.time}: O={k.open} C={k.close}")

    # 实时行情 (五档盘口)
    q = client.quote("sz000001")
    print(f"平安银行: {q.price}  买一 {q.bid_p[0]}  卖一 {q.ask_p[0]}")

    # 分时 / 分笔
    minute = client.today_minute("sz000001")
    trades = client.today_trade("sz000001", 0, 10)

    # 全量 K 线 (自动翻页 + 复权)
    all_bars = client.kline_all("sz000001", "day", adjust="qfq")

    # 批量刷新
    quotes = client.refresh(["sz000001", "sh600000"])
```

### 期货行情 (7727)

```python
from tdxproto import FuturesClient

with FuturesClient() as fc:
    # 自动探测主力合约
    main = fc.get_main_contract("IF", mid=47)
    print(f"IF主力: {main}")

    # 实时行情（含持仓量）
    q = fc.quote(47, main)
    print(f"price={q.price} vol={q.volume} OI={q.open_interest}")

    # 日K线（含持仓量/结算价）
    klines = fc.kline(47, main, "day", 0, 5)
    for k in klines:
        print(f"{k.time}: O={k.open} H={k.high} C={k.close} pos={k.position}")

    # 1分钟K线
    k1m = fc.kline(47, main, "1m", 0, 3)

    # 分时（240条，含持仓量）
    mins = fc.today_minute(47, main)

    # 逐笔成交（含开平性质）
    trades = fc.today_trade(47, main, 0, 5)
    for t in trades:
        print(f"{t.time} {t.price} dir={t.direction} nature={t.nature}")

    # 5个交易所全量合约
    for mid, name in [(28, "郑商所"), (29, "大商所"), (30, "上期所"),
                       (47, "中金所"), (66, "广期所")]:
        codes = fc.codes_all(mid)
        print(f"{name}: {len(codes)} 个合约")
```

实测合约行情：

| 交易所 | 合约 | 代码 | 价格 | 持仓量 |
|--------|------|------|------|--------|
| 中金所 | IF2608 | `fc.quote(47, "IF2608")` | 4614.8 | 10693 |
| 中金所 | IC2608 | `fc.quote(47, "IC2608")` | 7834.2 | 87616 |
| 郑商所 | 苹果2610 | `fc.quote(28, "AP2610")` | 7666.0 | 104422 |
| 大商所 | 豆一2609 | `fc.quote(29, "A2609")` | 4993.0 | 49776 |
| 上期所 | 铝合金2609 | `fc.quote(30, "AD2609")` | 22970.0 | 3968 |
| 广期所 | 碳酸锂2609 | `fc.quote(66, "LC2609")` | 156140.0 | 90982 |

### 巨潮资讯

```python
from tdxproto import CninfoClient

cn = CninfoClient()
anns = cn.search("000001", page=1)
for a in anns:
    print(a.title, a.announce_time)
```

### F10 资讯 (7615 HTTP)

```python
from tdxproto import InfoClient

ic = InfoClient()
# 实时新闻（100条）
news = ic.news(0, "000001")
for n in news[:3]:
    print(f"[{n.issue_date}] {n.title}  ({n.source})")

# 公告（含PDF链接）
anns = ic.announcements(0, "000001")
for a in anns[:3]:
    print(f"[{a.issue_date}] {a.title}  PDF: {a.pdf_url}")

# 研报
reports = ic.research_reports("000001")
for r in reports[:3]:
    print(f"[{r.date}] {r.rating} {r.analyst}: {r.title}")

# 公司概况
profile = ic.company_profile("000001")
print(profile.rows[0] if profile.rows else "无数据")

# 财务报表
finance = ic.finance_report("000001", "zcfzb")
for row in finance.rows[:3]:
    print(row)
```

**InfoCollector — 结构化采集（推荐）**：15 个接口统一封装，T/N 编码已通过官方字段字典翻译为可读中文名，数值保真，可直接入库：

```python
from tdxproto import InfoCollector

col = InfoCollector()
# 一次性采集全部 15 类数据
snap = col.snapshot(0, "000001")
print(f"新闻 {len(snap['news'])} 条, 公告 {len(snap['announcements'])} 条, "
      f"研报 {len(snap['research_reports'])} 条, 分红 {len(snap['dividends'])} 条")
print(snap["score"][0])          # {"total_score": 2.9, "rank": 13, ...}

# 公司概况（中文可读字段名）
profile = col.profile("600519")
print(profile["上市日期"], profile["发行价"], profile["主承销商"])

# 资产负债表 / 现金流量表（T 编码已翻译为标准财务科目名）
bs = col.balance_sheet("600519")  # [{"rq": "2026-06-30", "货币资金": 535..., "存货": 613..., ...}]
cf = col.cashflow("600519")       # [{"rq": "2026-06-30", "经营活动产生的现金流量净额": 706..., ...}]

# 股东增减持计划 / 路演（含详情链接）
plans = col.shareholder_plans("600519")  # [{"action": "拟增持", "amount_max": 33亿, "status": "完成", ...}]
shows = col.roadshows(0, "000001")       # [{"title": "...", "url": "https://rs.p5w.net/...", ...}]

# 题材内成分股排名（自动用数字题材 ID，需先取 topics）
topics = col.topics("000001")
members = col.topic_members("000001", topics[0]["topic_id"])
print(members[0])                # {"rank": 1, "code": "600577", "change_pct": 10.04, ...}
```

字段字典来源：通达信官方「专业财务数据项」编号字典，规律为 `T 编码 = 官方编号 - 1`（资产负债表）和 `T 编码 = 官方编号 - 90`（现金流量表），已用 `StockClient.finance()` 交叉验证。

每个 `snapshot` 中的条目均为结构化的 `dict`，字段含中文语义（如 `holding_pct`、`plan_text`、`pdf_url`），可直接写入数据库或导出 JSON/CSV。

### IP 健康监控

```python
from tdxproto import get_manager, StockClient

manager = get_manager()
best = manager.get_best_stock_host()
print(f"最优: {best.host} ({best.handshake_latency_ms:.1f}ms)")

client = StockClient(use_ip_health=True)
```

### 板块文件解析

```python
from tdxproto import parse_block_dat

with open("block_gn.dat", "rb") as f:
    blocks = parse_block_dat(f.read(), "block_gn.dat")
for b in blocks:
    print(b["name"], len(b["stocks"]))
```

### 本地计算引擎

```python
from tdxproto import compute_factors, get_equity_at, calc_turnover, auction_0925

factors = compute_factors(klines, equity_changes, adjust="qfq")
shares = get_equity_at(equity_changes, "2026-07-01")
turnover = calc_turnover(volume, shares)
auction = auction_0925(trades)
```

## 代码前缀规则

| 代码开头 | 归属 | 示例 |
|----------|------|------|
| `sz`/`sh`/`bj` 前缀 | 显式指定 | `sz000001`, `sh000001` |
| `60`/`68`/`69` | 上海 | `600000` |
| `30`/`15`/`16`/`39` | 深圳 | `300750` |
| `5`/`9` | 上海 | `510050` |
| `1`/`2` | 深圳 | `159915` |
| `8`/`4` | 北京 | `830799` |
| `00` 纯数字 | **歧义** — 必须带前缀 | `sz000001` vs `sh000001` |

## 命令参考

### 股票 (7709) — 60 个方法

| 分类 | 方法 | 说明 |
|------|------|------|
| **基础** | `count(market)` | 证券数量 |
| | `list(market, start, limit)` | 证券列表 |
| | `codes(market, start, limit)` | 代码列表（分页） |
| | `codes_all(market)` | 全量代码（自动翻页） |
| **行情** | `quote(code)` | 实时行情（五档盘口） |
| | `quotes_detail(code_list)` | 批量详细行情 |
| | `refresh(codes)` | 增量刷新 |
| | `quote_list(category, ...)` | 分类行情列表 |
| **K线** | `kline(code, period, start, count)` | K 线 |
| | `kline_all(code, period, adjust)` | 全量 K 线（自动翻页 + 复权） |
| | `chart_sampling(code)` | K 线采样 |
| | `sparkline(code)` | 迷你走势 |
| **分时** | `today_minute(code)` | 今日分时 |
| | `history_minute(code, date)` | 历史分时 |
| | `recent_minute(code, date)` | 近期分时 |
| | `tick_chart(code, start, count)` | 分时明细 |
| **成交** | `today_trade(code, start, count)` | 今日分笔 |
| | `history_trade(code, date, start, count)` | 历史分笔 |
| | `auction(code, mode)` | 集合竞价 |
| **财务** | `xdxr(code)` | 除权除息 |
| | `capital_changes(code)` | 股本变动 |
| | `finance(code)` | 财务数据 |
| **F10** | `company_info_cat(code)` | 公司信息分类 |
| | `company_info_content(code, file, start, len)` | F10 公司信息 |
| | `get_company_info(code, filename)` | 简化 F10 接口 |
| **板块** | `board_list(...)` | 板块列表 |
| | `board_members(...)` | 板块成分股 |
| | `board_summary(board_code)` | 板块摘要 |
| | `board_change_ranking(...)` | 板块涨跌排行 |
| | `stock_blocks(market, code)` | 股票所属板块 |
| | `get_block_file_parsed(file)` | 结构化板块数据 |
| | `get_blocks_with_index(type)` | 带索引的板块数据 |
| | `block_info_meta(file)` | 板块元信息 |
| | `block_info(file, start, size)` | 板块内容 |
| **排行** | `top_board(category)` | 涨跌停板排行 |
| | `quotes_list(category, start, count)` | 分类行情列表 |
| | `unusual(market, start, count)` | 主力监控 |
| **统计** | `capital_flow(code)` | 资金流向 |
| | `market_stat()` | 市场统计 |
| | `limits(start, count)` | 涨跌停限制 |
| | `index_momentum(code)` | 指数动能 |
| | `index_info(code)` | 指数成分股 |
| **报表** | `report_file(filename, offset)` | 研报文件 |
| | `get_report_file_raw(filename)` | 完整研报文件下载 |
| | `get_zhb_files()` | 综合报表文件 (45 个) |
| | `get_tdx_zs()` | 板块指数配置 (604 个) |
| | `get_tdx_bk()` | 概念板块简称全称 (58 个) |
| | `get_tdx_stat()` | 个股综合统计 (7964 条) |
| | `get_tdx_stat2()` | 个股资金流向 (7964 条) |
| | `get_xgsg()` | 新股申购 |
| | `get_tdx_hy()` | 行业归属 (5634 条) |
| **其他** | `server_info()` | 服务器信息 |
| | `symbol_info(code)` | 标的详细信息 |
| | `history_orders(code, date)` | 历史委托 |
| | `vol_profile(code)` | 成交量分布 |
| | `aux(code)` | 分时副图 |
| | `do_heartbeat()` | 心跳 |

### 期货 (7727) — 23 个方法

| 分类 | 方法 | 说明 |
|------|------|------|
| **基础** | `markets()` | 市场列表 (52 个市场) |
| | `codes(mid, start, count)` | 品种代码 |
| | `codes_all(mid)` | 全量品种代码（自动翻页） |
| | `count()` | 品种总数 |
| **行情** | `quote(mid, code)` | 实时行情（含持仓量/五档） |
| | `quote_batch(mid, start, count)` | 批量行情 |
| | `quotes(code_list)` | 批量详细行情 |
| **K线** | `kline(mid, code, period, start, count)` | K 线（含持仓量/结算价） |
| | `kline_range(mid, code, period, start, end)` | 区间 K 线 |
| | `chart_sampling(mid, code)` | K 线采样 |
| **分时** | `today_minute(mid, code)` | 今日分时（240条，含持仓量） |
| | `history_minute(mid, code, date)` | 历史分时 |
| | `tick_chart(mid, code)` | 分时图 |
| | `history_tick_chart(mid, code, date)` | 历史分时图 |
| **成交** | `today_trade(mid, code, start, count)` | 今日成交（含开平性质） |
| | `history_trade(mid, code, date, start, count)` | 历史成交 |
| **行情表** | `table(start, mode)` | 行情表 |
| | `table_detail(start)` | 行情明细 |
| **工具** | `get_main_contract(product, months, mid)` | 主力合约自动探测 |
| | `host()` | 当前连接主机 |
| | `reconnect()` | 重连 |
| | `safe_exec(func, *args)` | 安全执行 |

#### 期货市场

| market_id | 名称 | 合约数 | 实测行情 |
|-----------|------|--------|----------|
| 28 | 郑州商品 (ZCE) | 302 | AP2610 苹果: price=7666 OI=104422 |
| 29 | 大连商品 (DCE) | 328 | A2609 豆一: price=4993 OI=49776 |
| 30 | 上海期货 (SHFE) | 377 | AD2609 铝合金: price=22970 OI=3968 |
| 47 | 中金所 (CFFEX) | 89 | IF2608 沪深300: price=4614 OI=10693 |
| 66 | 广州期货 (GFEX) | 63 | LC2609 碳酸锂: price=156140 OI=90982 |
| 4/5/6/7/67 | 期权 | — | — |

全部 **1163 个合约** 实测可查。

### F10 资讯 (7615 HTTP) — 17 个方法

| 分类 | 方法 | 说明 |
|------|------|------|
| **实时资讯** | `news(market, code)` | 实时新闻（100条） |
| | `announcements(market, code)` | 公告列表（含PDF链接） |
| | `roadshows(market, code)` | 路演列表 |
| **研报** | `research_reports(code, page, size)` | 研报列表（含评级/分析师） |
| | `company_news(code, section, ...)` | 公司资讯 |
| **概况** | `stock_info(code)` | 股票基础信息 |
| | `company_profile(code, section)` | 公司概况（发行上市） |
| | `business_periods(code)` | 主营构成可选报告期 |
| | `business_composition(code, date)` | 主营构成 |
| **财务** | `finance_report(code, type)` | 财务报表（资产负债/利润/现金流） |
| | `finance_diagnosis(code, section)` | 财务诊断（营运/偿还/成长/盈利） |
| | `dividend_financing(code, section)` | 分红融资 |
| **评分** | `stock_score(code, section)` | 个股总评 |
| | `profit_forecast(code)` | 盈利预测 |
| **股东** | `shareholder_change_plans(code, ...)` | 股东增减持计划 |
| | `northbound_holding(code, ...)` | 沪深股通持股 |
| | `governance(code, section)` | 资本运作治理 |
| **题材** | `hot_topics(code, section)` | 热点题材 |
| | `topic_ids(code)` | 题材 ID 列表 |
| | `topic_compare(code, topic_id, ...)` | 题材内对比排名 |
| **低层** | `call(entry, body)` | 任意 TQLEX Entry |

`InfoCollector`（推荐用于入库）：`snapshot()` 一次采集 15 类数据；`balance_sheet()`/`cashflow()` 已翻译 T 编码为标准财务科目名；`profile()` 字段全部中文化；`topic_members()` 需传数字题材 ID（来自 `topics()` 的 `topic_id` 字段，传中文名会返回空）。利润表端点无数据，利润数据用 `StockClient.finance()` 获取。

## 数据模型

| 类 | 字段 | 用途 |
|----|------|------|
| `Quote` | 价格/成交量/持仓量/五档盘口/内外盘 | 实时快照 |
| `Kline` | OHLCV/成交额/持仓量/结算价 | K 线 |
| `Minute` | 价格/均价/成交量/持仓量 | 分时线 |
| `Trade` | 价格/量/方向/性质/增仓 | 逐笔成交 |
| `EquityChange` | 送转/分红/配股/股本变动 | 除权除息 |
| `FinanceInfo` | EPS/净资产/营收/利润 | 财务数据 |
| `PriceLimit` | 涨跌停价格 | 涨跌停限制 |
| `TdxBlock` | 板块名称/代码列表 | 板块文件解析 |
| `BoardMember` | 成分股代码/行情数据 | 板块成员 |
| `BoardSummary` | 成交额/涨跌家数/加权指标 | 板块汇总 |
| `CapitalFlowData` | 主力/散户净额 | 资金流向 |
| `MarketStat` | 涨跌家数/总市值 | 市场统计 |
| `ServerSession` | 交易时段/市场参数 | 服务器信息 |
| `SymbolInfo` | 动量/换手率/上市日期 | 标的详情 |

## 架构

```
tdxproto/
├── tube.py           # 协议无关 TCP 传输管道（连接池/心跳/故障转移）
├── frame.py          # 二进制帧编解码
├── codec.py          # Varint/价格/日期/成交量/代码标准化
├── models.py         # 14 个数据模型 dataclass
├── compute.py        # 本地计算引擎（复权因子/换手率/除权除息/竞价快照）
├── scanner.py        # 主站可用性探测与测速（TCP + 协议握手）
├── hosts.py          # 主站地址表（A 股 78 个, 期货 17 个）
├── ip_health.py      # IP 健康监控与优选（扫描/持久化/故障转移）
├── _reconnect.py     # 重连策略（同主机退避 + 跨主机故障转移）
├── exceptions.py     # 异常定义
├── block_reader.py   # 通达信 .dat 板块文件解析
├── gbbq.py           # 股本变迁管理器
├── workday.py        # 交易日历管理器
├── block_bridge.py   # 板块桥接（本地 + 远程）
├── stock/            # 7709 股票协议
│   ├── client.py     # StockClient（60 个方法）
│   └── commands.py   # 命令构造器/解析器
├── futures/          # 7727 期货协议
│   ├── client.py     # FuturesClient（23 个方法 / 动态主机轮换）
│   └── commands.py   # 命令构造器/解析器
├── cninfo/           # 巨潮资讯网
│   ├── client.py     # CninfoClient（公告检索）
│   └── models.py     # Announcement / CninfoError
├── info/             # 7615 F10 资讯 HTTP 网关
│   ├── client.py     # InfoClient（新闻/公告/研报/财务/概况/题材）
│   └── models.py     # 响应模型
├── mac/              # MAC 协议
│   ├── client.py     # MacClient（板块/成分股/排行）
│   ├── commands.py   # 命令 + 枚举
│   └── frame.py      # MAC 帧编解码
└── tests/            # 258 个测试用例
```

## 协议说明

### 7709 股票

- **握手**: 3 步 (SetupCmd1 → SetupCmd2 → SetupCmd3)
- **响应头**: 16 字节 `<IIIHH` (type, counter1, counter2, zip_len, unzip_len)
- **压缩**: zlib (zip_len != unzip_len 时解压)
- **价格**: 变长编码 (get_price, 类似 UTF-8)
- **成交量**: IEEE-754 风格编码 (decode_volume)
- **对齐 pytdx**: 字节级兼容 `TdxHq_API`

### 7727 期货

- **握手**: `0x2454` + 80B magic
- **帧格式**: `<BIBHHH` (prefix, msg_id, ctrl, data_len, data_len, cmd)
- **心跳**: 定期发送 `0x23F0` 维持连接
- **动态主机**: 连接前扫描 17 个服务器，按延迟排序，失败 3 次自动轮换
- **实测数据**: 5 个交易所共 1163 个合约，行情/日K/1分钟K/分时/逐笔成交全部可用

### MAC 协议

- **帧格式**: 请求头 `0x1C` + msg_id + body；响应头 `0xB1`
- 支持板块列表、成分股报价、个股所属板块、资金流向、板块汇总、涨跌排行、服务器信息、个股详情
- `MacClient` 连接 7709 端口，握手复用 StockClient 的 SetupCmd1/2/3
- `StockClient` 自动代理板块相关方法到 `MacClient`

## 测试

```bash
python -m pytest tdxproto/tests/ -v
python -m pytest tdxproto/tests/ -v -m "not system"
```

测试覆盖：258 passed, 8 skipped（系统测试需连接真实服务器）。

## 性能

- 单次行情查询: 10-50ms
- 全量 K 线翻页 (8000+ 条): 1-3s
- 全市场代码扫描 (27000+ 只): 2-5s
- 期货全市场扫描 (5 个交易所, 1163 个合约): 10-20s

## License

MIT