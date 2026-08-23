# tdxproto — 通达信全协议解析器

纯 Python 二进制协议实现，零外部依赖。覆盖 7709 A 股、7727 期货、7615 F10 资讯 HTTP 网关，以及 MAC 板块协议。

版本 **1.0.8**

## 特性

- **零依赖** — 仅使用 Python 标准库 (`socket`/`struct`/`zlib`/`urllib`)
- **四协议** — 7709 股票 + 7727 期货 + 7615 F10 资讯 + MAC 板块
- **多数据源** — 巨潮资讯网公告检索 (`CninfoClient`) + 7615 F10 资讯网关 (`InfoClient`)
- **IP 健康监控** — 自动扫描、测速、持久化、故障转移
- **断线自愈** — 同主机退避重试 + 跨主机故障转移
- **本地计算** — 复权因子、换手率、除权除息、竞价快照
- **数据模型** — 14 个 dataclass 统一表示
- **pip 可安装** — `pyproject.toml` 打包，`pip install git+...` 开箱即用

## 安装

Python 3.9+，零第三方依赖。

```bash
pip install git+https://github.com/647133036/tdx-protocol.git@v1.0.8
```

## 快速开始

### 股票行情 (7709)

```python
from tdxproto import StockClient

with StockClient(use_ip_health=True) as client:
    # K 线 (1m/5m/15m/30m/60m/day/week/month/quarter/year)
    klines = client.kline("sz000001", "day", 0, 10)
    for k in klines:
        print(f"{k.time}: O={k.open} C={k.close}")

    # 实时行情
    q = client.quote("sz000001")
    print(f"平安银行: {q.price}  买一 {q.bid_p[0]}  卖一 {q.ask_p[0]}")

    # 分时 / 分笔
    minute = client.today_minute("sz000001")
    trades = client.today_trade("sz000001", 0, 10)

    # 全量 K 线 (自动翻页 + 复权)
    all_bars = client.kline_all("sz000001", "day", adjust="qfq")

    # 批量行情
    quotes = client.quotes_detail(["sz000001", "sh600000"])

    # 资金流向 / 标的详情 / 市场统计
    flow = client.capital_flow("sz000001")
    info = client.symbol_info("sz000001")
    stat = client.market_stat()

    # 集合竞价
    auction = client.auction("sz000001")

    # 涨跌停排行
    tops = client.top_board(category=1)

    # 财务数据
    fin = client.finance("sz000001")

    # 除权除息
    equity = client.xdxr("sz000001")
```

**重要**：`finance` 方法接受**单个字符串 code**，不要传入列表：

```python
# 正确
data = client.finance("sz000001")

# 错误 — AttributeError: 'StockClient' object has no attribute 'finance'
data = client.finance(["sz000001"])
```

### 期货行情 (7727)

```python
from tdxproto import FuturesClient

with FuturesClient(use_ip_health=True) as fc:
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

    # 分时（240条，含持仓量）
    mins = fc.today_minute(47, main)

    # 逐笔成交（含开平性质）
    trades = fc.today_trade(47, main, 0, 5)
    for t in trades:
        print(f"{t.time} {t.price} dir={t.direction} nature={t.nature}")

    # 全量合约列表
    for mid, name in [(28, "郑商所"), (29, "大商所"), (30, "上期所"),
                       (47, "中金所"), (66, "广期所")]:
        codes = fc.codes_all(mid)
        print(f"{name}: {len(codes)} 个合约")
```

期货市场对照：

| market_id | 交易所 | 合约数 |
|-----------|--------|--------|
| 28 | 郑州商品 (ZCE) | 302 |
| 29 | 大连商品 (DCE) | 328 |
| 30 | 上海期货 (SHFE) | 377 |
| 47 | 中金所 (CFFEX) | 89 |
| 66 | 广州期货 (GFEX) | 63 |

合计 **1163 个合约**。

### F10 资讯 (7615 HTTP)

InfoClient 返回 `TqlexResponse` 对象，通过 `.result_sets[0].rows` 访问数据行：

```python
from tdxproto import InfoClient

ic = InfoClient()

# 实时新闻（沪市 market=1）
news = ic.news(1, "600519")
for n in news[:3]:
    print(f"[{n.issue_date}] {n.title}  ({n.source})")

# 研报
reports = ic.research_reports("600519")
for r in reports[:3]:
    print(f"[{r.date}] {r.rating} {r.analyst}: {r.title}")

# 资产负债表 / 现金流量表（返回 TqlexResponse，用 .result_sets 访问）
balance = ic.finance_report("600519", "zcfzb")
for row in balance.result_sets[0].rows[:3]:
    print(row)

# 财务诊断（含同业对比）
diag = ic.finance_diagnosis("600519")
for row in diag.result_sets[0].rows[:3]:
    print(row)
```

**InfoCollector — 结构化采集（推荐）**：将 `TqlexResponse` 自动转为干净 dict/list：

```python
from tdxproto import InfoCollector

col = InfoCollector()

# 一次性采集全部 16 类数据
snap = col.snapshot(0, "000001")
print(f"新闻 {len(snap['news'])} 条, 公告 {len(snap['announcements'])} 条, "
      f"研报 {len(snap['research_reports'])} 条, 分红 {len(snap['dividends'])} 条")
print(snap["score"][0])
print(snap["balance_sheet"][0])

# 公司概况（中文可读字段名）
profile = col.profile("600519")
print(profile["上市日期"], profile["发行价"], profile["主承销商"])

# 财务报表（T 编码已翻译为标准财务科目名）
bs = col.balance_sheet("600519")
cf = col.cashflow("600519")

# 股东增减持计划 / 路演
plans = col.shareholder_plans("600519")
shows = col.roadshows(0, "000001")

# 题材内成分股排名
topics = col.topics("000001")
members = col.topic_members("000001", topics[0]["topic_id"])
```

### 巨潮资讯

```python
from tdxproto import CninfoClient

cn = CninfoClient()

# 检索公告
anns = cn.search("000001", page=1, count=10)
for a in anns:
    print(a["code"], a["title"], a["announce_time"])

# 批量拉取多只股票公告
batch = cn.get_announcements_batch(["000001", "000002"], count=10)

# 下载 PDF
cn.download_pdf(ann, dest_dir="./pdfs")
```

### 本地计算引擎

```python
from tdxproto import compute_factors, get_equity_at, calc_turnover, auction_0925

# 复权因子（前复权）
factors = compute_factors(klines, equity_changes, adjust="qfq")

# 某日股本
shares_total, shares_float = get_equity_at(equity_changes, date(2026, 7, 1))

# 换手率
turnover = calc_turnover(volume, shares_float)

# 集合竞价快照
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

### 00 开头代码（000001–000999）歧义说明

`000001`–`000999` 这个号段在深圳市场是股票，在上海市场是指数，两个市场都存在，**无法自动区分**。

| 号段 | 深圳 SZ (market=0) | 上海 SH (market=1) |
|------|--------------------|---------------------|
| 000001–000999 | 股票（约 900 只 A 股） | 指数（约 800 个指数） |

同一个 `000001`，含义完全不同：

- `sz000001` → 平安银行（深圳 A 股）
- `sh000001` → 上证指数（上海综合指数）

必须显式带 `sz`/`sh` 前缀：

```python
# 深圳股票
client.quote("sz000001")  # 平安银行

# 上海指数
client.quote("sh000001")  # 上证指数

# 不带前缀会抛 ValueError
client.quote("000001")  # 歧义！需加 sz/sh 前缀
```

## API 参考

### StockClient (7709) — 62 个方法

| 分类 | 方法 | 签名 | 说明 |
|------|------|------|------|
| **基础** | `count` | `(market)` | 证券数量 |
| | `list` | `(market, start, limit)` | 证券列表 |
| | `codes` | `(market, start, limit)` | 代码列表（分页） |
| | `codes_all` | `(market)` | 全量代码（自动翻页） |
| **行情** | `quote` | `(code)` | 实时行情（五档盘口） |
| | `quotes_detail` | `(code_list)` | 批量详细行情 |
| | `refresh` | `(codes)` | 增量刷新（服务器拒绝，用 `quotes_detail`） |
| | `quote_list` | `(category, count=80, start=0, ...)` | 分类行情列表 |
| | `quotes_list` | `(category, start=0, count=80, ...)` | 分类行情列表（dict 返回） |
| | `sparkline` | `(code)` | 迷你走势 |
| **K线** | `kline` | `(code, period="day", start=0, count=800)` | K 线 |
| | `kline_all` | `(code, period="day", adjust="")` | 全量 K 线（自动翻页 + 复权） |
| | `chart_sampling` | `(code)` | K 线采样 |
| **分时** | `today_minute` | `(code)` | 今日分时 |
| | `history_minute` | `(code, tdate)` | 历史分时 |
| | `recent_minute` | `(code, tdate=None)` | 近期分时 |
| | `tick_chart` | `(code, start=0, count=47616)` | 分时明细 |
| **成交** | `today_trade` | `(code, start=0, count=115)` | 今日分笔 |
| | `history_trade` | `(code, tdate, start=0, count=900)` | 历史分笔 |
| | `auction` | `(code, mode=3)` | 集合竞价 |
| **财务** | `xdxr` | `(code)` | 除权除息 |
| | `capital_changes` | `(code)` | 股本变动 |
| | `finance` | `(code)` | 财务数据（传字符串 code，不要传列表） |
| **F10** | `company_info_cat` | `(code)` | 公司信息分类 |
| | `company_info_content` | `(code, filename, start=0, length=0)` | F10 公司信息 |
| | `get_company_info` | `(code, filename)` | 简化 F10 接口 |
| **板块** | `board_list` | `(page_size=150, board_type=0, ...)` | 板块列表 |
| | `board_members` | `(board_code, page_size=80, start=0, ...)` | 板块成分股 |
| | `board_summary` | `(board_code)` | 板块摘要 |
| | `board_change_ranking` | `(board_type=0, days=5, top_n=100)` | 板块涨跌排行 |
| | `stock_blocks` | `(market, code)` | 股票所属板块 |
| | `get_blocks_with_index` | `(block_type=0)` | 带索引的板块数据 |
| | `get_block_file_parsed` | `(block_file)` | 结构化板块数据 |
| | `block_info_meta` | `(block_file)` | 板块元信息 |
| | `block_info` | `(block_file, start=0, size=0)` | 板块内容 |
| **排行** | `top_board` | `(category=0)` | 涨跌停板排行 |
| | `unusual` | `(market=0, start=0, count=600, min_volume=1000)` | 主力监控（扫描真实股票大单） |
| **统计** | `capital_flow` | `(code)` | 资金流向 |
| | `market_stat` | `()` | 市场统计 |
| | `limits` | `(start=0, count=2000)` | 涨跌停限制 |
| | `index_momentum` | `(code, period)` | 指数动能（用 kline 计算） |
| | `index_info` | `(code, top_n=50)` | 指数成分股（用 board_members 回退） |
| | `vol_profile` | `(code, price_levels=20)` | 成交量分布（用逐笔成交计算） |
| **报表** | `report_file` | `(filename, offset=0)` | 研报文件 |
| | `get_report_file_raw` | `(filename)` | 完整研报文件下载 |
| | `get_zhb_files` | `()` | 综合报表文件 |
| | `get_tdx_zs` | `()` | 板块指数配置 |
| | `get_tdx_bk` | `()` | 概念板块简称全称 |
| | `get_tdx_stat` | `()` | 个股综合统计 |
| | `get_tdx_stat2` | `()` | 个股资金流向 |
| | `get_xgsg` | `()` | 新股申购 |
| | `get_tdx_hy` | `()` | 行业归属 |
| **其他** | `server_info` | `()` | 服务器信息 |
| | `symbol_info` | `(code)` | 标的详细信息 |
| | `history_orders` | `(code, tdate)` | 历史委托 |
| | `aux` | `(code)` | 分时副图 |
| | `do_heartbeat` | `()` | 心跳 |
| | `connect` | `()` | 连接 |
| | `disconnect` | `()` | 断开 |
| | `close` | `()` | 关闭 |

### FuturesClient (7727) — 24 个方法

| 分类 | 方法 | 签名 | 说明 |
|------|------|------|------|
| **基础** | `markets` | `()` | 市场列表 |
| | `codes` | `(mid, start, count)` | 品种代码 |
| | `codes_all` | `(mid)` | 全量品种代码（自动翻页） |
| | `count` | `()` | 品种总数 |
| **行情** | `quote` | `(mid, code)` | 实时行情（含持仓量/五档） |
| | `quote_batch` | `(mid, start=0, count=200)` | 批量行情 |
| | `quotes` | `(code_list)` | 批量详细行情 |
| **K线** | `kline` | `(mid, code, period="day", start=0, count=800)` | K 线（含持仓量/结算价） |
| | `kline_range` | `(mid, code, period, start_date, end_date)` | 区间 K 线 |
| | `chart_sampling` | `(mid, code)` | K 线采样 |
| **分时** | `today_minute` | `(mid, code)` | 今日分时（240条，含持仓量） |
| | `history_minute` | `(mid, code, tdate)` | 历史分时 |
| | `tick_chart` | `(mid, code)` | 分时图 |
| | `history_tick_chart` | `(mid, code, tdate)` | 历史分时图 |
| **成交** | `today_trade` | `(mid, code, start=0, count=100)` | 今日成交（含开平性质） |
| | `history_trade` | `(mid, code, tdate, start=0, count=100)` | 历史成交 |
| **行情表** | `table` | `(start=0, mode=1)` | 行情表 |
| | `table_detail` | `(start=0)` | 行情明细 |
| **工具** | `get_main_contract` | `(product="IF", lookahead_months=3, mid=47)` | 主力合约自动探测 |
| | `host` | `()` | 当前连接主机 |
| | `reconnect` | `()` | 重连 |
| | `safe_exec` | `(func, *args)` | 安全执行 |

### InfoClient (7615 HTTP) — 21 个方法

| 分类 | 方法 | 签名 | 说明 |
|------|------|------|------|
| **实时资讯** | `news` | `(market, code)` | 实时新闻（100条，沪市 market=1） |
| | `announcements` | `(market, code)` | 公告列表（含PDF链接） |
| | `roadshows` | `(market, code)` | 路演列表（含详情链接） |
| **研报** | `research_reports` | `(code, page=1, page_size=20)` | 研报列表（含评级/分析师） |
| | `company_news` | `(code, section, ...)` | 公司资讯 |
| **概况** | `stock_info` | `(code)` | 股票基础信息 |
| | `company_profile` | `(code, section="8")` | 公司概况（发行上市） |
| | `business_periods` | `(code)` | 主营构成可选报告期 |
| | `business_composition` | `(code, date)` | 主营构成 |
| **财务** | `finance_report` | `(code, report_type="zcfzb")` | 资产负债表/现金流量表 |
| | `finance_diagnosis` | `(code, section="yynl", scope="0")` | 财务诊断 |
| | `dividend_financing` | `(code, section)` | 分红融资 |
| **评分** | `stock_score` | `(code, section="pf", arg="")` | 个股总评 |
| | `profit_forecast` | `(code)` | 盈利预测 |
| **股东** | `shareholder_change_plans` | `(code, page=1, page_size=20, ...)` | 股东增减持计划 |
| | `northbound_holding` | `(code, ...)` | 沪深股通持股 |
| | `governance` | `(code, section)` | 资本运作治理 |
| **题材** | `hot_topics` | `(code, section)` | 热点题材 |
| | `topic_ids` | `(code)` | 题材 ID 列表 |
| | `topic_compare` | `(code, topic_id, section="gndbzfsj", ...)` | 题材内对比排名 |
| **低层** | `call` | `(entry, body)` | 任意 TQLEX Entry |

`InfoClient` 返回类型说明：

| 返回类型 | 说明 |
|----------|------|
| `list[NewsItem]` | `news` / `announcements` / `roadshows` / `research_reports` |
| `TqlexResponse` | 其余方法（财务/概况/诊断/评分等） |

`TqlexResponse` 访问数据：

```python
resp = ic.finance_report("600519", "zcfzb")
for row in resp.result_sets[0].rows:
    print(row)
```

### InfoCollector — 16 个方法

封装 `InfoClient`，返回干净的 dict/list：

| 方法 | 签名 | 说明 |
|------|------|------|
| `snapshot` | `(market, code)` | 一次采集全部 16 类数据 |
| `news` | `(market, code)` | 新闻 |
| `announcements` | `(market, code)` | 公告 |
| `research_reports` | `(code, page=1, page_size=20)` | 研报 |
| `profile` | `(code)` | 公司概况 |
| `balance_sheet` | `(code)` | 资产负债表 |
| `cashflow` | `(code)` | 现金流量表 |
| `diagnosis` | `(code, section="yynl")` | 财务诊断 |
| `dividends` | `(code)` | 分红 |
| `business_composition` | `(code)` | 主营构成 |
| `northbound_holding` | `(code)` | 沪股通持股 |
| `topics` | `(code)` | 热点题材 |
| `topic_members` | `(code, topic_id=None, sort_by="zdf")` | 题材内成分股排名 |
| `score` | `(code)` | 个股评分 |
| `shareholder_plans` | `(code)` | 股东增减持计划 |
| `roadshows` | `(market, code)` | 路演 |

`snapshot()` 返回 dict，包含 16 个 key：

```
code, news, announcements, research_reports, business_composition,
northbound_holding, dividends, topics, score, profile,
balance_sheet, cashflow, diagnosis, shareholder_plans, roadshows
```

### MacClient — 11 个方法

| 分类 | 方法 | 签名 | 说明 |
|------|------|------|------|
| **板块** | `board_list` | `(page_size=150, board_type=0, ...)` | 板块列表 |
| | `board_members` | `(board_code, page_size=80, start=0, ...)` | 板块成分股 |
| | `board_summary` | `(board_code)` | 板块摘要 |
| | `board_change_ranking` | `(board_type=0, days=5, top_n=100, ...)` | 板块涨跌排行 |
| | `stock_blocks` | `(market, code)` | 股票所属板块 |
| **行情** | `capital_flow` | `(code)` | 资金流向 |
| | `category_quotes` | `(category, start=0, count=80, ...)` | 分类行情 |
| | `symbol_info` | `(code)` | 标的详情 |
| **其他** | `server_info` | `()` | 服务器信息 |
| | `connect` / `close` | | 连接/关闭 |

### CninfoClient — 5 个方法

| 方法 | 签名 | 说明 |
|------|------|------|
| `search` | `(code, **kwargs)` | 检索公告 |
| `get_announcements` | `(code, count=30, page=1, ...)` | 获取公告列表 |
| `get_announcements_batch` | `(codes, count=10, page=1, ...)` | 批量公告 |
| `get_announcement_detail` | `(announcement)` | 公告详情 |
| `download_pdf` | `(announcement, dest_dir=".", filename=None)` | 下载 PDF |

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
├── tube.py           # 协议无关 TCP 传输管道
├── frame.py          # 二进制帧编解码
├── codec.py          # Varint/价格/日期/成交量/代码标准化
├── models.py         # 14 个数据模型 dataclass
├── compute.py        # 本地计算引擎（复权因子/换手率/除权除息/竞价快照）
├── scanner.py        # 主站可用性探测与测速
├── hosts.py          # 主站地址表（A股78个, 期货16个, MAC 3个）
├── ip_health.py      # IP 健康监控与优选
├── _reconnect.py     # 重连策略
├── exceptions.py     # 异常定义
├── block_reader.py   # 通达信 .dat 板块文件解析
├── gbbq.py           # 股本变迁管理器
├── workday.py        # 交易日历管理器
├── block_bridge.py   # 板块桥接（本地 + 远程）
├── stock/            # 7709 股票协议
│   ├── client.py     # StockClient（62 个方法）
│   └── commands.py   # 命令构造器/解析器
├── futures/          # 7727 期货协议
│   ├── client.py     # FuturesClient（24 个方法）
│   └── commands.py   # 命令构造器/解析器
├── cninfo/           # 巨潮资讯网
│   ├── client.py     # CninfoClient（5 个方法）
│   └── models.py     # Announcement / CninfoError
├── info/             # 7615 F10 资讯 HTTP 网关
│   ├── client.py     # InfoClient（21 个方法）
│   ├── collector.py  # InfoCollector（16 个方法）
│   ├── field_dict.py # 官方财务字段字典
│   └── models.py     # TqlexResponse / TqlexResultSet
├── mac/              # MAC 协议
│   ├── client.py     # MacClient（11 个方法）
│   ├── commands.py   # 命令 + 枚举
│   └── frame.py      # MAC 帧编解码
└── tests/            # 276 个测试用例
```

## 协议说明

### 7709 股票

- **握手**: 3 步 (SetupCmd1 → SetupCmd2 → SetupCmd3)
- **响应头**: 16 字节 `<IIIHH` (type, counter1, counter2, zip_len, unzip_len)
- **压缩**: zlib (zip_len != unzip_len 时解压)
- **价格**: 变长编码 (get_price, 类似 UTF-8)
- **成交量**: IEEE-754 风格编码 (decode_volume)

### 7727 期货

- **握手**: `0x2454` + 80B magic
- **帧格式**: `<BIBHHH` (prefix, msg_id, ctrl, data_len, data_len, cmd)
- **心跳**: 定期发送 `0x23F0` 维持连接
- **动态主机**: 连接前扫描 16 个服务器，按延迟排序，失败 3 次自动轮换

### MAC 协议

- **帧格式**: 请求头 `0x1C` + msg_id + body；响应头 `0xB1`
- 支持板块列表、成分股报价、个股所属板块、资金流向、板块汇总、涨跌排行、服务器信息、个股详情
- `MacClient` 连接 7709 端口，握手复用 StockClient 的 SetupCmd1/2/3
- `StockClient` 自动代理板块相关方法到 `MacClient`

### 7615 F10 资讯

- **传输**: HTTP POST，JSON 请求/响应
- **网关**: `static.tdx.com.cn:7615/TQLEX?Entry=<endpoint>`
- **返回类型**: `TqlexResponse(entry, error_code, result_sets, raw)`
- **访问数据**: `resp.result_sets[0].rows`

## 主站地址

| 市场 | 快速池 | 全量池 |
|------|--------|--------|
| A 股 7709 | 7 个 | 78 个 |
| 期货 7727 | 3 个 | 16 个 |
| MAC 板块 | — | 3 个 |

## 测试

```bash
python -m pytest tdxproto/tests/ -v
python -m pytest tdxproto/tests/ -v -m "not system"
```

## 性能

- 单次行情查询: 10-50ms
- 全量 K 线翻页 (8000+ 条): 1-3s
- 全市场代码扫描 (27000+ 只): 2-5s
- 期货全市场扫描 (5 个交易所, 1163 个合约): 10-20s
- zhb.zip 下载 (45 个 cfg 文件): 20-22s（首次下载后缓存，后续 0s）

## 变更记录

- **1.0.8** — 修复 `_recv_response` 中 `zlib.error` 未捕获导致全链路崩溃的根因问题；`finance`/`report_file`/`vol_profile`/`top_board` 分别加固异常处理；`auction` 切换为短超时通道消除 3.6s 重试链；`index_info` 增加备用路径；`main.py` 修正 `finance` 调用方式
- **1.0.7** — 核心修复：缺失 `pyproject.toml` 导致 `pip install git+...` 静默失败；修复 `KeyError: 0`（`_p_capital_flow` 在 dict 响应上索引崩溃）；修复 `AttributeError: 'Quote' object has no attribute 'get'`；`get_tdx_*` 系列改用 `_send_recv_quick` 消除超时；`chart_sampling`/`history_orders` 超时修复；`vol_profile` 参数优化；`unusual` 前缀过滤修正；`_p_quotes_list` 空响应守卫；`_get_zhb_file` 缓存空结果修复
- **1.0.6** — 4 个服务器不支持的命令改用替代实现（vol_profile 用 today_trade 计算；index_momentum 用 kline 计算；index_info 用 board_members/codes_all+quotes_detail；unusual 用 today_trade 过滤大单）
- **1.0.5** — 4 个命令超时修复（新增 `_send_recv_quick` 短超时方法）
- **1.0.4** — 修复 `market_stat`（`Quote` dataclass 误用 `.get()`）；50 接口全量实测验证；README 重写加入实测结果表和参数注意事项
- **1.0.3** — 修复 6 个 InfoClient bug；新增官方字段字典 `field_dict.py`；InfoCollector 新增 6 个语义化方法
- **1.0.2** — 新增 InfoClient (7615 F10 HTTP 网关)；InfoCollector 结构化采集
- **1.0.1** — 完整 API 参考文档

## License

MIT