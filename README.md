# tdxproto — 通达信行情协议解析器

Python 3.9+ 纯 Python 实现。核心库仅依赖标准库，可连接通达信 7709 股票协议、7727 期货协议，并支持 7615 F10 资讯、巨潮资讯、中金所持仓排名、港股行情、导出工具、CLI、批量采集和本地 Web 查询界面。

版本 **1.1.4**

## 能力概览

| 能力 | 支持情况 |
|------|----------|
| A 股实时行情 | `StockClient.quote()`，五档盘口、价格、成交量、内盘外盘 |
| A 股 K 线 | 1m / 5m / 15m / 30m / 60m / day / week / month / year，支持复权 |
| A 股分时 / 分笔 | `today_minute()` / `history_minute()` / `today_trade()` / `history_trade()` |
| 集合竞价 | `auction()`，本地竞价快照工具 `auction_0925()` |
| 财务 / 股本 | `finance()` / `capital_changes()` / `xdxr()` |
| 资金 / 涨跌停 | `capital_flow()` / `market_stat()` / `limits()` |
| 板块 / 排行 | MAC 板块列表、成分股、排行、归属，以及 `top_board()` / `unusual()` |
| 期货行情 | `FuturesClient.quote()` / `quote_batch()`，五档、成交量、持仓量 |
| 期货 K 线 / 分时 / 分笔 | `kline()` / `kline_range()` / `today_minute()` / `today_trade()` |
| ETF | 通过股票协议查询 ETF 实时行情 |
| 港股 | `HkClient.quote()` / `quote_batch()`，腾讯行情接口 |
| F10 资讯 | `InfoClient` / `InfoCollector`，新闻、公告、研报、财务诊断、资料快照 |
| 巨潮资讯 | `CninfoClient`，公告检索、公告列表、PDF 下载 |
| 中金所持仓排名 | `CcpmClient`，IF / IH / IC / IM / TS / TF / T / TL 会员排名 |
| 批量采集 | `batch.py` K 线、港股、期货行情批量采集 |
| 数据导出 | JSON / CSV / DataFrame / Parquet，Parquet 为可选依赖 |
| 本地 Web | `web_server.py` 股票、期货、港股查询界面 |
| 断线自愈 | 重试、主机故障转移、IP 健康监控、主机测速 |

## 安装

```bash
pip install tdxproto
```

启用 Parquet 导出：

```bash
pip install "tdxproto[parquet]"
```

从仓库安装：

```bash
pip install git+https://github.com/647133036/tdx-protocol.git
```

## 快速开始

### 股票

```python
from tdxproto import StockClient

with StockClient() as c:
    quote = c.quote("sz000001")
    print(quote.name, quote.price, quote.pre_close, quote.change_pct)

    bars = c.kline("sz000001", "day", 0, 10)
    for bar in bars:
        print(bar.time, bar.open, bar.high, bar.low, bar.close, bar.volume)

    minute = c.today_minute("sz000001")
    trades = c.today_trade("sz000001", 0, 50)

    finance = c.finance("sz000001")
    equity = c.xdxr("sz000001")
    flow = c.capital_flow("sz000001")
```

### 期货

```python
from tdxproto import FuturesClient

with FuturesClient() as f:
    quote = f.quote(47, "IFL0")
    print(quote.price, quote.pre_close, quote.volume, quote.open_interest)

    quotes = f.quote_batch(47, 0, 50)
    bars = f.kline(47, "IFL0", "day", 0, 100)
```

### ETF

```python
from tdxproto import StockClient

with StockClient() as c:
    etf = c.quote("sh510050")
    print(etf.price, etf.volume)
```

### 港股

```python
from tdxproto import HkClient

hk = HkClient()
quote = hk.quote("00700")
if quote:
    print(quote.code, quote.name, quote.price, quote.change_pct)

batch = hk.quote_batch(["00700", "09988", "01810"])
```

### F10 资讯

```python
from tdxproto import InfoClient, InfoCollector

info = InfoClient()
news = info.news(1, "600519")

collector = InfoCollector()
snapshot = collector.snapshot(1, "600519")
```

### 数据导出

```python
from tdxproto import to_json, to_csv_string, to_dataframe, to_parquet, to_dict

to_json({"quote": quote})
to_csv_string(to_dict(bars))

df = to_dataframe(to_dict(bars))

to_parquet(to_dict(bars), "bars.parquet")
```

Parquet 输出需要可选依赖：

```bash
pip install "tdxproto[parquet]"
```

## CLI

单协议命令入口是 `main.py`：

```bash
# A 股
python main.py stock count sz
python main.py stock quote sz000001,sh600000
python main.py stock kline sz000001 --period day --start 0 --count 10
python main.py stock minute sz000001
python main.py stock trade sz000001 20260620
python main.py stock equity sz000001
python main.py stock finance sz000001,sh600000
python main.py stock limits

# 期货
python main.py futures markets
python main.py futures codes 47
python main.py futures quote IFL0 --market 47
python main.py futures kline IFL0 --market 47 --period day
python main.py futures trade IFL0 --market 47

# ETF
python main.py etf quote sz159919,sh510050

# 港股
python main.py hk quote 00700
python main.py hk quote-batch 00700,09988,01810

# 主机扫描
python main.py scan stock
python main.py scan futures
```

批量采集入口是 `batch.py`：

```bash
# 指定代码采集 K 线
python batch.py kline --codes "sz000001,sh600000" --period day --output ./data/

# 核心龙头池
python batch.py kline --universe core --period day --output ./data/

# 全市场 A 股
python batch.py all-stocks --period day --output ./data/ --workers 32

# 港股行情
python batch.py hk-quote --codes "00700,09988,01810" --output ./data/
python batch.py hk-quote --codes hk_codes.txt --output ./data/

# 期货行情
python batch.py futures-quote --market 47 --count 50 --output ./data/

# 输出格式
python batch.py kline --codes codes.txt --format json --output ./data/
python batch.py kline --codes codes.txt --format csv --output ./data/
python batch.py kline --codes codes.txt --format parquet --output ./data/
```

## 本地 Web 查询

```bash
python web_server.py
```

默认访问：

```text
http://127.0.0.1:8080
```

Web 页面支持股票行情、K 线、分时、成交、除权、财务、代码列表、期货行情和港股行情。后端接口包括：

| 路径 | 说明 |
|------|------|
| `/api/status` | 股票、期货、港股连接状态 |
| `/api/quote` | A 股实时行情 |
| `/api/kline` | A 股 K 线 |
| `/api/kline-all` | A 股全量 K 线 |
| `/api/codes` | 代码列表 |
| `/api/xdxr` | 除权除息 |
| `/api/finance` | 财务数据 |
| `/api/trade` | 成交明细 |
| `/api/count` | 市场代码数量 |
| `/api/futures/quote` | 期货实时行情 |
| `/api/hk/quote` | 港股实时行情 |

## 数据模型

核心模型定义在 `tdxproto/models.py`：

| 模型 | 用途 |
|------|------|
| `Quote` | 实时行情快照，含价格、成交量、五档盘口、持仓量、原始字节 |
| `Kline` | K 线，含时间、OHLC、成交量、成交额、持仓量、结算价 |
| `Minute` | 分时点 |
| `Trade` | 分笔成交 |
| `EquityChange` | 股本变迁 |
| `FinanceInfo` | 财务基础信息 |
| `PriceLimit` | 涨跌停限制 |

导出函数会处理 dataclass、bytes、list、dict：

```python
from tdxproto import to_dict, to_json, to_csv_string, to_dataframe, to_parquet, to_parquet_string
```

## 代码前缀

| 前缀 | 市场 | 示例 |
|------|------|------|
| `sz` | 深圳 A 股 / 深市指数 | `sz000001` 平安银行，`sz399001` 深证成指 |
| `sh` | 上海 A 股 / 沪市指数 | `sh600000` 浦发银行，`sh000001` 上证指数 |
| `bj` | 北京证券交易所 | `bj830799` |

数字代码在不同市场含义不同，例如 `000001` 在深市是股票，在沪市是上证指数，因此推荐使用带前缀代码。

## API 概览

### StockClient

主要方法包括：

```python
count(), codes(), codes_all(), quote(), quotes_detail(),
kline(), kline_all(), kline_120m(), kline_with_derived(),
today_minute(), history_minute(), tick_chart(),
today_trade(), history_trade(), auction(),
finance(), xdxr(), capital_changes(), capital_flow(), market_stat(), limits(),
board_list(), board_members(), stock_blocks(), top_board(), unusual()
```

### FuturesClient

主要方法包括：

```python
markets(), codes(), codes_all(), quote(), quote_batch(),
kline(), kline_range(), today_minute(), history_minute(),
today_trade(), history_trade(), get_main_contract()
```

### 港股 HkClient

```python
quote(code)
quote_batch(codes, max_batch_size=80)
```

### InfoClient / InfoCollector

```python
news(), announcements(), research_reports(), finance_report(),
finance_diagnosis(), profile(), snapshot()
```

### CninfoClient

```python
search()
get_announcements()
download_pdf()
```

### CcpmClient

```python
get_rank(product, date)
latest_rank(product)
get_products_meta()
```

中金所持仓排名自动缓存至：

```text
~/.easy_tdx/cache/ccpm/
```

## 架构

```text
tdxproto/
├── tube.py           # TCP 传输管道
├── frame.py          # 二进制帧编解码
├── codec.py          # Varint / 价格 / 日期 / 成交量标准化
├── models.py         # 数据模型
├── compute.py        # 复权因子 / 换手率 / 除权 / 竞价
├── scanner.py        # 主站探测与测速
├── hosts.py          # 服务器地址表
├── ip_health.py      # IP 健康监控
├── export.py         # JSON / CSV / DataFrame / Parquet 导出
├── _reconnect.py     # 重连策略
├── stock/            # 7709 股票协议
├── futures/          # 7727 期货协议
├── hk/               # 港股行情
├── info/             # 7615 F10 资讯
├── cninfo/           # 巨潮资讯
├── ccpm/             # 中金所持仓排名
└── mac/              # MAC 板块协议
```

项目根目录还有：

```text
main.py        # CLI
batch.py       # 批量采集 CLI
web_server.py  # 本地 Web 查询界面
```

## 测试

完整测试：

```bash
python3 -m pytest tdxproto/tests/ -q
```

非系统测试：

```bash
python3 -m pytest tdxproto/tests/ -q -m "not system"
```

当前非系统测试状态：

```text
436 passed, 2 skipped, 16 deselected
```

系统测试依赖外网通达信服务器、行情接口和数据源接口；默认通过 `-m "not system"` 排除。

## 变更记录

- **1.1.4** — 新增数据导出模块 `tdxproto/export.py`，支持 `to_dict()` / `to_json()` / `to_csv_string()` / `to_dataframe()` / `to_parquet()` / `to_parquet_string()`；新增 `tdxproto[parquet]` 可选依赖；`main.py` 新增港股 CLI（`hk quote` / `hk quote-batch`），并修复嵌套 dict 递归 JSON 输出；`batch.py` 新增港股行情、期货行情批量采集与 Parquet 输出；`web_server.py` 新增期货、港股查询 API 和页面，并修复行情字段映射；修正 `Quote.change_pct`、MAC 可选导出和 bytes 序列化；补充导出、CLI、Web、包导出、Quote 映射测试；非系统测试 436 passed
- **1.1.3** — 修复板块成分股字段解析顺序与类型：新增 `_BOARD_MEMBERS_FIELD_ORDER` 按预期顺序解析（PRE_CLOSE/CLOSE/VOL/AMOUNT/PRICE/RISE_SPEED/MAIN_NET_AMOUNT/UP_COUNT/DOWN_COUNT）；RISE_SPEED 加入 `_INT_FIELD_BITS` 并转换为百分比（基点/10000）；VOL 正确读取为 INT 类型；测试 407 passed
- **1.1.2** — 新增 `tdxproto/hk/` 港股行情模块（HkClient/HkQuote，腾讯行情 API，`quote` / `quote_batch`，时间锚点相对定位应对字段波动）；板块排行细化（`board_amount_ranking` / `board_volume_ranking`，服务器端排序 + top_n 截断）；代码审查 9 项修复；安全审查 4 项修复
- **1.1.1** — 对标 easy_tdx 补齐采集能力：新增 `session.py` 交易时段/分时锚定工具；`today_minute` 盘前/休市自动锚定最近交易日历史分时；指数分时自适应；`Kline.datetime` property 别名；`kline_120m` 修复；`kline_with_derived` 补充 `time` 键；workday 入库改存 ISO 日期；新增 `universe.py` 核心龙头池 159 只；安全加固 cninfo URL 白名单、PDF 下载路径穿越防护、ccpm 主机白名单和 web_server 代码正则
- **1.1.0** — 新增 `CcpmClient` 中金所持仓排名；新增 `kline_120m`；新增 `verify_qfq`；新增异常类型描述工具；修复 stock workday dateutil 依赖、`--count > 65535` 越界检查、`tick_chart` ETF/bond 系数、`index_info` 代码提取、K 线下界、短包解析容错、重连 socket 泄漏和 `_send_recv_quick` 超时废弃连接
- **1.0.8** — 修复 `_recv_response` 中 `zlib.error` 未捕获导致全链路崩溃的问题；加固 `finance` / `report_file` / `vol_profile` / `top_board` 异常处理；`auction` 切换为短超时通道；`index_info` 增加备用路径；`main.py` 修正 `finance` 调用方式
- **1.0.7** — 修复缺失 `pyproject.toml` 导致 `pip install git+...` 静默失败；修复 `KeyError: 0`；修复 `AttributeError: 'Quote' object has no attribute 'get'`；`get_tdx_*` 系列改用 `_send_recv_quick`；修复 `chart_sampling` / `history_orders` 超时；优化 `vol_profile` 参数；修正 `unusual` 前缀过滤；加固 `_p_quotes_list` 和 `_get_zhb_file` 空响应处理
- **1.0.6** — 4 个服务器不支持的命令改用替代实现：`vol_profile` 用 `today_trade` 计算，`index_momentum` 用 `kline` 计算，`index_info` 用 `board_members` / `codes_all` + `quotes_detail`，`unusual` 用 `today_trade` 过滤大单
- **1.0.5** — 4 个命令超时修复，新增 `_send_recv_quick` 短超时方法
- **1.0.4** — 修复 `market_stat`（`Quote` dataclass 误用 `.get()`）；补充实测结果表和参数注意事项
- **1.0.3** — 修复 6 个 `InfoClient` bug；新增官方字段字典 `field_dict.py`；`InfoCollector` 新增 6 个语义化方法
- **1.0.2** — 新增 `InfoClient`（7615 F10 HTTP 网关）；新增 `InfoCollector` 结构化采集
- **1.0.1** — 完整 API 参考文档

## License

MIT
