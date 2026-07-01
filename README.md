# tdxproto — 通达信全协议解析器

纯 Python 二进制协议实现，零外部依赖。覆盖 7709 A股 + 7727 期货双协议。

## 特性

- **零依赖** — 仅使用 Python 标准库 (`socket`/`struct`/`zlib`)
- **双协议** — 7709 (A股) + 7727 (期货/扩展行情)
- **IP健康监控** — 自动扫描、测速、持久化、故障转移
- **动态主机轮换** — 连续失败 3 次自动切换最优主机
- **250 测试** — 单元/组件/系统/功能全覆盖
- **对齐 pytdx** — 协议字节级兼容雨老的 pytdx/tdxpy

## 安装

```bash
pip install tdxproto
```

或直接使用源码：

```bash
git clone <repo>
cd tdxproto
```

Python 3.11+，无第三方依赖。

## 快速开始

### 股票行情 (7709)

```python
from tdxproto import StockClient

with StockClient() as client:
    # 获取证券数量
    count = client.count(1)  # 上海: 27439

    # 实时行情
    quote = client.quote("600000")
    print(f"浦发银行: ¥{quote.price}")

    # K线
    klines = client.kline("600000", period="day", count=10)
    for k in klines:
        print(f"{k.time}: O={k.open} C={k.close}")

    # 分时 / 成交
    minute = client.today_minute("600000")
    trade = client.today_trade("600000", count=10)

    # 增量刷新
    refreshed = client.refresh(["600000", "000001"])
```

### 期货行情 (7727)

```python
from tdxproto import FuturesClient

with FuturesClient() as fc:
    # 市场列表
    markets = fc.markets()

    # 品种代码
    codes = fc.codes(42, 0, 10)

    # K线
    klines = fc.kline(42, "IF2607", period="day", count=10)

    # 分时图
    tick = fc.tick_chart(42, "IF2607")
```

### IP 健康监控

```python
from tdxproto.ip_health import scan_hosts, get_manager

# 扫描并更新IP池
stock_ok, futures_ok = scan_hosts()

# 获取最快IP
manager = get_manager()
best = manager.get_best_stock_host()
print(f"最快股票IP: {best.host} ({best.handshake_latency_ms:.1f}ms)")

# 客户端自动使用优选IP
from tdxproto import StockClient
client = StockClient(use_ip_health=True)  # 默认开启
```

### 本地计算引擎

```python
from tdxproto import compute_factors, get_equity_at, calc_turnover, auction_0925

# 复权因子计算
factors = compute_factors(klines, equity_changes, adjust="qfq")

# 指定日期股本
float_shares = get_equity_at(equity_changes, target_date)

# 换手率
turnover = calc_turnover(volume, float_shares)

# 09:25 竞价快照
auction = auction_0925(trade_list)
```

## 支持的命令

### 股票 (7709) — 30+ 命令

| 方法 | 说明 |
|------|------|
| `count(market)` | 证券数量 |
| `list(market, limit)` | 证券列表 |
| `quote(code)` | 实时行情 (五档盘口) |
| `kline(code, period, count)` | K线 (1m/5m/15m/30m/60m/day/week/month/quarter/year) |
| `kline_all(code, period, adjust)` | 全量K线 (自动翻页+复权) |
| `today_minute(code)` | 今日分时 |
| `history_minute(code, date)` | 历史分时 |
| `today_trade(code, count)` | 今日分笔 |
| `history_trade(code, date, count)` | 历史分笔 |
| `xdxr(code)` | 除权除息 |
| `finance(code)` | 财务信息 |
| `company_info_cat(code)` | 公司信息类别 |
| `company_info_content(code, filename)` | 公司信息内容 |
| `block_info_meta(file)` | 板块元信息 |
| `block_info(file, start, size)` | 板块内容 |
| `report_file(filename, offset)` | 研报文件 |
| `vol_profile(code)` | 成交量分布 |
| `aux(code)` | 分时副图 |
| `index_momentum(code)` | 指数动能 |
| `index_info(code)` | 指数成分股 |
| `tick_chart(code)` | 分时明细 |
| `auction(code)` | 集合竞价 |
| `top_board(category)` | 涨跌停板 |
| `quotes_list(category, start, count)` | 板块行情列表 |
| `unusual(market, count)` | 主力监控 |
| `chart_sampling(code)` | K线采样 |
| `history_orders(code, date)` | 历史委托 |
| `refresh(codes)` | 增量刷新 |
| `recent_minute(code, date)` | 近期分时 |
| `limits(start, count)` | 涨跌停限制 |
| `sparkline(code)` | 小走势图 |

### 期货 (7727) — 15 命令

| 方法 | 说明 |
|------|------|
| `markets()` | 市场列表 |
| `codes(mid, start, count)` | 品种代码 |
| `codes_all(mid)` | 全量品种代码 |
| `quote(mid, code)` | 实时行情 |
| `quote_batch(mid, start, count)` | 批量行情 |
| `kline(mid, code, period, count)` | K线 |
| `kline_range(mid, code, period, start, end)` | 区间K线 |
| `today_minute(mid, code)` | 今日分时 |
| `history_minute(mid, code, date)` | 历史分时 |
| `today_trade(mid, code, count)` | 今日成交 |
| `history_trade(mid, code, date, count)` | 历史成交 |
| `tick_chart(mid, code)` | 分时图 |
| `history_tick_chart(mid, code, date)` | 历史分时图 |
| `chart_sampling(mid, code)` | K线采样 |
| `table(start, mode)` | 表格数据 |
| `table_detail(start)` | 表格详情 |
| `quotes(code_list)` | 批量详细行情 |

## 架构

```
tdxproto/
├── tube.py          # 协议无关 TCP 传输管道 (连接池/心跳/故障转移)
├── frame.py         # 二进制帧编解码
├── codec.py         # Varint/价格/日期/成交量/代码标准化
├── models.py        # Quote/Kline/Minute/Trade/EquityChange/FinanceInfo/PriceLimit
├── compute.py       # 本地计算引擎 (复权因子/换手率/除权除息/竞价快照)
├── scanner.py       # 服务器可用性探测与测速 (TCP + 协议握手)
├── hosts.py         # 服务器IP地址表 (A股43+个, 期货16+个)
├── ip_health.py     # IP健康监控与优选 (扫描/持久化/故障转移)
├── stock/           # 7709 股票协议
│   ├── client.py    # StockClient
│   └── commands.py  # 30+ 命令构造器/解析器
└── futures/         # 7727 期货协议
    ├── client.py    # FuturesClient (动态主机轮换)
    └── commands.py  # 15 命令构造器/解析器
```

## 测试

```bash
python -m pytest tdxproto/tests/ -v
# 250 passed, 0 failed, 8 skipped (期货系统测试需真实网络)
```

## 协议说明

### 7709 股票协议

- **握手**: 3步 (SetupCmd1 → SetupCmd2 → SetupCmd3)
- **响应头**: 16 字节 `<IIIHH` (type, counter1, counter2, zip_len, unzip_len)
- **压缩**: zlib (zip_len != unzip_len 时解压)
- **价格**: 变长编码 (get_price, 类似 UTF-8)
- **成交量**: IEEE-754 风格编码 (decode_volume)

### 7727 期货协议

- **握手**: 1步 (0x2454 + 80B magic)
- **帧格式**: `<BIBHHH` (prefix, msg_id, ctrl, data_len, data_len, cmd)
- **心跳**: 定期发送 0x23F0 维持连接
- **动态主机**: 连接前扫描 16 个服务器，按延迟排序，失败 3 次自动轮换

## License

MIT
