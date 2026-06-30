# tdxproto — 通达信全协议解析器

纯 Python 二进制协议实现，零外部依赖。覆盖 7709 股票 + 7727 期货双协议。

## 特性

- **零依赖** — 仅使用 Python 标准库 (`socket`/`struct`/`zlib`)
- **双协议** — 7709 (A股) + 7727 (期货/扩展行情)
- **IP健康监控** — 自动扫描、测速、持久化、故障转移
- **258 测试** — 单元/组件/系统/功能全覆盖
- **对齐 pytdx** — 协议字节级兼容雨老的 pytdx/tdxpy

## 安装

```bash
pip install tdxproto
# 或直接使用源码
git clone <repo>
cd tdxproto
```

无第三方依赖，Python 3.11+。

## 快速开始

### 股票行情 (7709)

```python
from tdxproto.stock import StockClient

client = StockClient()
client.connect()

# 获取证券数量
count = client.count(1)  # 上海: 27439

# 实时行情
quote = client.quote("600000")
print(f"浦发银行: ¥{quote['price']}")

# K线
klines = client.kline("600000", period="day", count=10)
for k in klines:
    print(f"{k['datetime']}: O={k['open']} C={k['close']}")

# 分时/成交
minute = client.today_minute("600000")
trade = client.today_trade("600000", count=10)

client.close()
```

### 期货行情 (7727)

```python
from tdxproto.futures import FuturesClient

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

### IP健康监控

```python
from tdxproto.ip_health import scan_hosts, get_manager

# 扫描并更新IP池
stock_ok, futures_ok = scan_hosts()

# 获取最快IP
manager = get_manager()
best = manager.get_best_stock_host()
print(f"最快股票IP: {best.host} ({best.handshake_latency_ms:.1f}ms)")

# 客户端自动使用优选IP
from tdxproto.stock import StockClient
client = StockClient(use_ip_health=True)  # 默认开启
```

## 支持的命令

### 股票 (7709) — 19个命令

| 命令 | 方法 | 说明 |
|------|------|------|
| count | `client.count(market)` | 证券数量 |
| list | `client.list(market, limit)` | 证券列表 |
| snapshot | `client.quote(code)` | 实时行情 |
| kline | `client.kline(code, period)` | K线 (1m~year) |
| today_minute | `client.today_minute(code)` | 今日分时 |
| history_minute | `client.history_minute(code, date)` | 历史分时 |
| today_trade | `client.today_trade(code)` | 今日分笔 |
| history_trade | `client.history_trade(code, date)` | 历史分笔 |
| xdxr | `client.xdxr(code)` | 除权除息 |
| finance | `client.finance(code)` | 财务信息 |
| vol_profile | `client.vol_profile(code)` | 成交量分布 |
| tick_chart | `client.tick_chart(code)` | 分时明细 |
| top_board | `client.top_board(cat)` | 涨跌停板 |
| sparkline | `client.sparkline(code)` | 小走势图 |

### 期货 (7727) — 12个命令

| 命令 | 方法 | 说明 |
|------|------|------|
| markets | `fc.markets()` | 市场列表 |
| codes | `fc.codes(mid, start, count)` | 品种代码 |
| quote | `fc.quote(mid, code)` | 实时行情 |
| kline | `fc.kline(mid, code, period)` | K线 |
| kline_range | `fc.kline_range(mid, code, start, end)` | 区间K线 |
| today_minute | `fc.today_minute(mid, code)` | 今日分时 |
| today_trade | `fc.today_trade(mid, code)` | 今日成交 |
| tick_chart | `fc.tick_chart(mid, code)` | 分时图 |
| chart_sampling | `fc.chart_sampling(mid, code)` | K线采样 |
| table | `fc.table(start, mode)` | 表格数据 |
| quotes | `fc.quotes(code_list)` | 批量行情 |

## 架构

```
tdxproto/
├── tube.py          # 协议无关 TCP 传输管道 (连接池/心跳/故障转移)
├── frame.py         # 二进制帧编解码
├── codec.py         # Varint/价格/日期/成交量编码
├── models.py        # Quote/Kline/Minute/Trade 数据模型
├── compute.py       # 复权因子/换手率/除权除息计算
├── scanner.py       # 服务器可用性探测与测速
├── hosts.py         # 服务器IP地址表
├── ip_health.py     # IP健康监控与优选
├── stock/           # 7709 股票协议
│   ├── client.py    # StockClient
│   └── commands.py  # 命令构造器/解析器
└── futures/         # 7727 期货协议
    ├── client.py    # FuturesClient
    └── commands.py  # 命令构造器/解析器
```

## 测试

```bash
python -m pytest tdxproto/tests/ -v
# 258 passed
```

## 协议说明

### 7709 股票协议

- **握手**: 3步 (SetupCmd1 → SetupCmd2 → SetupCmd3)
- **响应头**: 16字节 `<IIIHH` (type, counter1, counter2, zip_len, unzip_len)
- **压缩**: zlib (zip_len != unzip_len 时解压)
- **价格**: 变长编码 (get_price)
- **成交量**: IEEE-754 风格编码 (decode_volume)

### 7727 期货协议

- **握手**: 1步 (0x2454 + 80B magic)
- **帧格式**: `<BIBHHH` (prefix, msg_id, ctrl, data_len, data_len, cmd)
- **心跳**: 定期发送 0x2456 维持连接

## License

MIT
