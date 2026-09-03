# tdxproto — 通达信全协议解析器

Python 3.9+，零外部依赖。原生实现通达信 7709（A 股）、7727（期货）、7615（F10 资讯）和 MAC 板块协议。

版本 **1.1.0**

## 安装

```bash
pip install tdxproto
```

## 快速开始

### 股票

```python
from tdxproto import StockClient

with StockClient() as c:
    # K 线
    bars = c.kline("sz000001", "day", 0, 10)
    for b in bars:
        print(f"{b.datetime}: O={b.open} C={b.close}")

    # 实时行情
    q = c.quote("sz000001")
    print(f"平安银行 {q.price}  涨跌 {q.price-q.pre_close:+.2f}")

    # 分时 / 分笔
    minute = c.today_minute("sz000001")
    trades = c.today_trade("sz000001", 0, 50)

    # 财务 / 除权 / 资金流向
    fin = c.finance("sz000001")
    equity = c.xdxr("sz000001")
    flow = c.capital_flow("sz000001")
```

### 期货

```python
from tdxproto import FuturesClient

with FuturesClient() as fc:
    main = fc.get_main_contract("IF")
    q = fc.quote(47, main)
    print(f"IF 主力 {q.price}  持仓 {q.open_interest}")

    klines = fc.kline(47, main, "day", 0, 5)
    trades = fc.today_trade(47, main, 0, 10)
```

### F10 资讯

```python
from tdxproto import InfoClient, InfoCollector

ic = InfoClient()
news = ic.news(1, "600519")

col = InfoCollector()
snap = col.snapshot(0, "600519")
print(f"新闻 {len(snap['news'])} 条, 研报 {len(snap['research_reports'])} 条")
```

## 特性

- **零依赖** — 仅用标准库（socket/struct/zlib/urllib）
- **四协议** — 7709 股票 + 7727 期货 + 7615 F10 资讯 + MAC 板块
- **断线自愈** — 指数退避重试 + 跨主机故障转移
- **IP 优选** — 自动测速、持久化、健康监控
- **本地计算** — 复权因子、换手率、除权除息、竞价快照
- **批量采集** — ThreadPoolExecutor，32 线程并发，failover 可控
- **异常类型** — 29 种异常类型解码 + 描述工具
- **120 分钟 K 线** — 聚合两根 60M bar
- **中金所持仓排名** — CcpmClient 采集 IF/IH/IC/IM/TS/TF/T/TL 品种

## 代码前缀规则

| 前缀 | 市场 | 示例 |
|------|------|------|
| `sz` | 深圳 A 股 | `sz000001` 平安银行 |
| `sh` | 上海 A 股 / 指数 | `sh600000` 浦发银行 / `sh000001` 上证指数 |
| `bj` | 北京证券交易所 | `bj830799` |

`000001` 这种数字在深市是股票、在沪市是指数，必须带前缀。

## API 概览

### StockClient（62 个方法）

| 模块 | 方法 | 说明 |
|------|------|------|
| **基础** | `count(market)` / `codes(market)` / `codes_all(market)` | 数量 / 代码列表 |
| **行情** | `quote(code)` / `quotes_detail(codes)` | 实时五档 |
| **K线** | `kline(code, period, start, count)` / `kline_all(code, period, adjust)` | 1m~year / 全量+复权 |
| **分时** | `today_minute(code)` / `history_minute(code, date)` / `tick_chart(code)` | 分时线 / 逐笔 |
| **成交** | `today_trade(code)` / `history_trade(code, date)` / `auction(code)` | 分笔 / 集合竞价 |
| **财务** | `finance(code)` / `xdxr(code)` / `capital_changes(code)` | 财务数据 / 除权 |
| **板块** | `board_list()` / `board_members(code)` / `stock_blocks(market, code)` | 板块列表/成分/归属 |
| **排行** | `top_board(category)` / `unusual(market)` | 涨跌停 / 大单监控 |
| **统计** | `capital_flow(code)` / `market_stat()` / `limits()` | 资金流 / 涨跌停限制 |

### FuturesClient（24 个方法）

`markets()` / `codes(mid)` / `quote(mid, code)` / `kline(mid, code, period)` / `today_minute(mid, code)` / `today_trade(mid, code)` / `get_main_contract(product)` / `table(start, mode)` ...

### InfoClient + InfoCollector（7615 HTTP）

`news(market, code)` / `announcements()` / `research_reports()` / `finance_report()` / `finance_diagnosis()` / `profile()` / `snapshot(market, code)` ...

### CninfoClient（巨潮）

`search()` / `get_announcements()` / `download_pdf()`

### CcpmClient（中金所持仓排名）

`get_rank(product, date)` / `latest_rank(product)` / `get_products_meta()`

返回成交量/持买单量/持卖单量各前 20 名会员排名，自动缓存至 ~/.easy_tdx/cache/ccpm/。

### 新特性

```python
# 异常类型描述
from tdxproto.stock.commands import UNUSUAL_TYPE_NAMES, describe_unusual
print(describe_unusual(0x13))  # 竞价试买（申报价=0, 竞价量=0手）

# 120 分钟 K 线
bars = c.kline_120m("sh600519", count=100)
for b in bars:
    print(f"{b.datetime}: O={b.open} H={b.high} L={b.low} C={b.close}")

# 中金所持仓排名
from tdxproto import CcpmClient
client = CcpmClient()
ranks = client.latest_rank("IF")
print(ranks["volume_rank"][:3])   # 成交量 Top3
print(ranks["long_rank"][:3])     # 持买单量 Top3
print(ranks["short_rank"][:3])    # 持卖单量 Top3
```

## 架构

```
tdxproto/
├── tube.py           # TCP 传输管道
├── frame.py          # 二进制帧编解码
├── codec.py          # Varint/价格/日期/成交量标准化
├── models.py         # 14 个 dataclass 模型
├── compute.py        # 复权因子/换手率/除权/竞价
├── scanner.py        # 主站探测与测速
├── hosts.py          # 服务器地址表
├── ip_health.py      # IP 健康监控
├── _reconnect.py     # 重连策略
├── stock/            # 7709 股票协议
├── futures/          # 7727 期货协议
├── info/             # 7615 F10 资讯
├── cninfo/           # 巨潮资讯
└── mac/              # MAC 板块协议
```

## 测试

```bash
python -m pytest tdxproto/tests/ -v
python -m pytest tdxproto/tests/ -v -m "not system"
```

316 个用例通过，8 个系统测试跳过（需外网）。

## 变更记录

- **1.1.0** — 新增 CcpmClient（中金所持仓排名 IF/IH/IC/IM/TS/TF/T/TL）；新增 kline_120m（120 分钟 K 线聚合）；新增 verify_qfq（QFQ 交叉验证 formula vs gap）；新增 UNUSUAL_TYPE_NAMES 25 种异常类型 + describe_unusual；修复 stock workday dateutil 依赖；--count > 65535 越界检查前置；tick_chart ETF/bond 系数；index_info 代码提取；K 线下界 1990；短包解析容错；重连 socket 泄漏；_send_recv_quick 超时废弃连接
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
