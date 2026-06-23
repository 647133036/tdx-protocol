# tdx-protocol

通达信全协议解析器 — 纯 Python 二进制协议实现，零外部依赖。

支持 7709 (A股/ETF) 和 7727 (期货/期权) 双端口，覆盖 **31 个命令**，内置**主站并发扫描器**和**本地计算引擎**。

## 快速开始

```bash
git clone https://github.com/647133036/tdx-protocol.git
cd tdx-protocol

# 扫描可用主站 (自动选最快)
python main.py scan stock      # A股 7709，41 个候选
python main.py scan futures    # 期货 7727，16 个候选

# A股行情
python main.py stock quote sz000001,sh600000
python main.py stock kline sz000001 --period day --count 100 --adjust qfq
python main.py stock minute sz000001
python main.py stock trade sz000001 20250623
python main.py stock auction sz000001
python main.py stock turnover sz000001

# 期货行情
python main.py futures markets
python main.py futures codes 47
python main.py futures quote IF2607 --market 47
python main.py futures kline IFL9 --market 47 --period day
python main.py futures trade IF2607 --market 47

# 一键全部数据
python main.py stock info sz000001
```

## Python API

```python
from tdxproto import StockClient, FuturesClient

# A股
with StockClient() as c:
    quotes = c.quote(["sz000001", "sh600000"])
    bars   = c.kline("sz000001", period="day", adjust="qfq")

# 期货
with FuturesClient() as c:
    markets = c.markets()
    codes   = c.codes_all(47)          # 中金所全部品种
    quote   = c.quote(47, "IF2607")
```

## 命令覆盖

### 7709 A股 (19 个命令)

| 命令号 | 功能 | 方法 |
|--------|------|------|
| 0x000D | 握手 | 自动 |
| 0x0004 | 心跳 | 后台 30s |
| 0x044D | 代码表 | `codes()` / `codes_all()` |
| 0x044E | 代码数量 | `count()` |
| 0x054C | 批量快照 | `quote()` |
| 0x0547 | 增量刷新 | `refresh()` |
| 0x054B | 分类行情 | `category()` |
| 0x052D | K线 (含复权) | `kline()` / `kline_all()` |
| 0x0537 | 当日分时 | `today_minute()` |
| 0x0FB4 | 历史分时 | `history_minute()` |
| 0x0FEB | 近期分时 | `recent_minute()` |
| 0x051B | 分时副图 | `aux()` |
| 0x0FD1 | 小走势图 | `sparkline()` |
| 0x0FC5 | 当日成交 | `today_trade()` |
| 0x0FC6 | 历史成交 | `history_trade()` / `history_trade_all()` |
| 0x056A | 集合竞价 | `auction()` |
| 0x000F | 股本变迁 | `capital_changes()` |
| 0x0010 | 财务基础 | `finance()` |
| 0x0452 | 涨跌停限制 | `limits()` |

### 7727 期货 (12 个命令)

| 命令号 | 功能 | 方法 |
|--------|------|------|
| 0x2454 | 握手 (80B 魔数) | 自动 |
| 0x23F0 | 心跳 | 后台 |
| 0x23F4 | 交易所列表 | `markets()` |
| 0x23F5 | 代码表 | `codes()` / `codes_all()` |
| 0x23FA | 五档行情 | `quote()` |
| 0x2400 | 批量行情 | `quote_batch()` |
| 0x23FF | K线 | `kline()` |
| 0x240D | K线区间 | (已定义) |
| 0x240B | 当日分时 | `today_minute()` |
| 0x240C | 历史分时 | `history_minute()` |
| 0x23FC | 当日成交 | `today_trade()` |
| 0x2406 | 历史成交 | `history_trade()` |

## 本地计算引擎

服务端不直接提供的指标，本地计算：

| 函数 | 说明 |
|------|------|
| `compute_factors()` | 复权因子 (基于不复权K线 + 除权除息记录) |
| `get_equity_at()` | 任意日期股本回溯 |
| `calc_turnover()` | 换手率 (成交量/流通股本) |
| `parse_xdxr()` | 除权除息解析 (分红/送转/配股) |
| `auction_0925()` | 09:25 集合竞价快照 |

## 主站扫描

```bash
python main.py scan stock --workers 64 --timeout 2.0
```

两层验证：
1. TCP 连通性探测
2. 协议握手响应校验 (过滤版本不匹配的假阳性)

按握手延迟排序，结果缓存到 `.tdx_best_hosts.json`。客户端初始化时自动扫描选最快主站。

## 架构

```
tdxproto/
├── tube.py          # 协议无关 TCP 传输管道 (心跳/多主站failover)
├── frame.py         # 二进制帧编解码 (7709/7727 双前缀)
├── codec.py         # varint / 成交量解码 / 代码标准化
├── models.py        # 统一数据模型 (Quote/Kline/Minute/Trade/...)
├── compute.py       # 本地计算引擎
├── scanner.py       # 主站可用性探测
├── hosts.py         # 41+ A股 / 16+ 期货主站地址表
├── stock/           # 7709 A股实现
│   ├── commands.py  # 19 个命令构造器 + 解析器
│   └── client.py
└── futures/         # 7727 期货实现
    ├── commands.py  # 12 个命令构造器 + 解析器
    └── client.py
```

## 要求

- Python >= 3.9
- 零外部依赖

## License

MIT
