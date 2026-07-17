# tdxproto — 通达信全协议解析器

纯 Python 二进制协议实现，零外部依赖。覆盖 7709 A股 + 7727 期货双协议，50+ 命令。

## 特性

- **零依赖** — 仅使用 Python 标准库 (`socket`/`struct`/`zlib`)
- **双协议** — 7709 (A股) + 7727 (期货/扩展行情)
- **多数据源** — 巨潮资讯网公告检索 (`cninfo`)
- **IP 健康监控** — 自动扫描、测速、持久化、故障转移
- **断线自愈** — 同主机退避重试 + 跨主机故障转移 + 命令失败后 NOP 重连
- **板块解析** — `.dat` 板块文件本地解析
- **本地计算** — 复权因子、换手率、除权除息、竞价快照
- **266 个测试** — 单元/组件/系统全覆盖

## 安装

Python 3.11+，零第三方依赖。

```bash
pip install tdxproto
```

源码使用：

```bash
git clone https://github.com/647133036/tdx-protocol
cd tdx-protocol
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
    print(f"平安银行: {q.price}  买一 {q.bid1}  卖一 {q.ask1}")

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
    markets = fc.markets()
    klines = fc.kline(42, "IF2607", "day")
    quote = fc.quote(42, "IF2607")
    main = fc.get_main_contract("IF")
```

> 期货系统测试在当前沙箱环境跳过（7727 端口不可达）。

### 巨潮资讯

```python
from tdxproto import CninfoClient

cn = CninfoClient()
# 按代码搜公告
anns = cn.search("000001", page=1)
for a in anns:
    print(a.title, a.announce_time)
```

### IP 健康监控

```python
from tdxproto import get_manager, scan_hosts, StockClient

# 扫描全网主站
stock_ok, futures_ok = scan_hosts()

# 查看健康状态
manager = get_manager()
best = manager.get_best_stock_host()
print(f"最优: {best.host} ({best.handshake_latency_ms:.1f}ms)")

# 客户端自动使用优选 IP（默认开启）
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

# 前复权
factors = compute_factors(klines, equity_changes, adjust="qfq")

# 指定日期股本
shares = get_equity_at(equity_changes, "2026-07-01")

# 换手率
turnover = calc_turnover(volume, shares)

# 09:25 竞价快照
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

### 股票 (7709) — 50 个方法

| 方法 | 说明 |
|------|------|
| `count(market)` | 证券数量 |
| `list(market, start, limit)` | 证券列表 |
| `codes(market, start, limit)` | 代码列表（分页） |
| `codes_all(market)` | 全量代码 |
| `quote(code)` | 实时行情（五档盘口） |
| `quotes_detail(code_list)` | 批量详细行情 |
| `kline(code, period, start, count)` | K 线 |
| `kline_all(code, period, adjust)` | 全量 K 线（自动翻页+复权） |
| `today_minute(code)` | 今日分时 |
| `history_minute(code, date)` | 历史分时 |
| `recent_minute(code, date)` | 近期分时 |
| `today_trade(code, start, count)` | 今日分笔 |
| `history_trade(code, date, start, count)` | 历史分笔 |
| `tick_chart(code, start, count)` | 分时明细 |
| `auction(code, mode)` | 集合竞价 |
| `xdxr(code)` | 除权除息 |
| `capital_changes(code)` | 股本变动 |
| `finance(code)` | 财务数据 |
| `company_info_cat(code)` | 公司信息分类 |
| `company_info_content(code, filename, start, length)` | F10 公司信息 |
| `block_info_meta(file)` | 板块元信息 |
| `block_info(file, start, size)` | 板块内容 |
| `report_file(filename, offset)` | 研报文件 |
| `top_board(category)` | 涨跌停板排行 |
| `quotes_list(category, start, count)` | 分类行情列表 |
| `unusual(market, start, count)` | 主力监控 |
| `chart_sampling(code)` | K 线采样 |
| `history_orders(code, date)` | 历史委托 |
| `refresh(codes)` | 增量刷新 |
| `sparkline(code)` | 迷你走势（基于 1min K 线） |
| `limits(start, count)` | 涨跌停限制 |
| `server_info()` | 服务器信息 |
| `symbol_info(code)` | 标的详细信息 |
| `board_list(...)` | 板块列表 |
| `board_members(...)` | 板块成分股 |
| `stock_blocks(market, code)` | 股票所属板块 |
| `board_summary(board_code)` | 板块摘要 |
| `board_change_ranking(...)` | 板块涨跌排行 |
| `get_block_file_parsed(file)` | 结构化板块数据 |
| `quote_list(...)` | 行情列表（增强版） |
| `capital_flow(code)` | 资金流向 |
| `market_stat()` | 市场统计 |

社区命令（服务器可能不支持）：
| `vol_profile(code)` | 成交量分布 |
| `index_momentum(code)` | 指数动能 |
| `index_info(code)` | 指数成分股 |
| `aux(code)` | 分时副图 |

### 期货 (7727) — 23 个方法

| 方法 | 说明 |
|------|------|
| `markets()` | 市场列表 |
| `codes(mid, start, count)` | 品种代码 |
| `codes_all(mid)` | 全量品种代码 |
| `quote(mid, code)` | 实时行情 |
| `quote_batch(mid, start, count)` | 批量行情 |
| `kline(mid, code, period)` | K 线 |
| `kline_range(mid, code, period, start, end)` | 区间 K 线 |
| `today_minute(mid, code)` | 今日分时 |
| `history_minute(mid, code, date)` | 历史分时 |
| `today_trade(mid, code, start, count)` | 今日成交 |
| `history_trade(mid, code, date, start, count)` | 历史成交 |
| `tick_chart(mid, code)` | 分时图 |
| `history_tick_chart(mid, code, date)` | 历史分时图 |
| `chart_sampling(mid, code)` | K 线采样 |
| `table(start, mode)` | 行情表 |
| `table_detail(start)` | 行情明细 |
| `quotes(code_list)` | 批量详细行情 |
| `get_main_contract(product, months)` | 主力合约 |
| `host()` | 当前连接主机 |
| `reconnect()` | 重连 |

> 期货系统测试在沙箱环境跳过。生产环境需确保可访问 7727 端口。

## 架构

```
tdxproto/
├── tube.py           # 协议无关 TCP 传输管道（连接池/心跳/故障转移）
├── frame.py          # 二进制帧编解码
├── codec.py          # Varint/价格/日期/成交量/代码标准化
├── models.py         # Quote/Kline/Minute/Trade/EquityChange/FinanceInfo/PriceLimit
├── compute.py        # 本地计算引擎（复权因子/换手率/除权除息/竞价快照）
├── scanner.py        # 主站可用性探测与测速（TCP + 协议握手）
├── hosts.py          # 主站地址表（A 股 78 个, 期货 17 个）
├── ip_health.py      # IP 健康监控与优选（扫描/持久化/故障转移）
├── _reconnect.py     # 重连策略（同主机退避 + 跨主机故障转移）
├── exceptions.py     # 异常定义
├── block_reader.py   # 通达信 .dat 板块文件解析
├── stock/            # 7709 股票协议
│   ├── client.py     # StockClient（50 个方法）
│   └── commands.py   # 命令构造器/解析器
├── futures/          # 7727 期货协议
│   ├── client.py     # FuturesClient（23 个方法 / 动态主机轮换）
│   └── commands.py   # 命令构造器/解析器
├── cninfo/           # 巨潮资讯网
│   ├── client.py     # CninfoClient（公告检索）
│   └── models.py     # Announcement / CninfoError
└── mac/              # MAC 协议（板块/成分股/排行）
    ├── client.py     # MacClient
    ├── commands.py   # 命令 + 枚举（BoardType/SortColumn/...）
    └── frame.py      # MAC 帧编解码
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

### MAC 协议

- **帧格式**: `0x1C` 头 + msg_id + body
- 当前公网无可用 MAC 服务器，`MacClient` 保留供后续使用

## 测试

```bash
python -m pytest tdxproto/tests/ -v
# 258 passed, 8 skipped（期货系统测试需 7727 端口可达）
```

## License

MIT
