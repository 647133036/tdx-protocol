#!/usr/bin/env python3
"""通达信行情 Web 验证界面 — 纯 Python 标准库实现."""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from tdxproto.stock import StockClient

# 全局客户端 (懒连接)
_client = None
_client_lock = threading.Lock()


def get_client():
    global _client
    if _client is None or _client.sock is None:
        with _client_lock:
            if _client is None or _client.sock is None:
                _client = StockClient(timeout=5, rate_limit=0.5)
                try:
                    _client.connect()
                except Exception:
                    _client = None
                    raise
    return _client


def _retry_on_conn_error(handler_func):
    """装饰器: 捕获 ConnectionError 并重试一次 get_client()."""
    def wrapper(*args, **kwargs):
        self = args[0]
        try:
            return handler_func(*args, **kwargs)
        except ConnectionError:
            # 重置全局客户端, 重试
            global _client
            with _client_lock:
                if _client:
                    _client.close()
                    _client = None
            try:
                return handler_func(*args, **kwargs)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
    return wrapper


def release_client():
    global _client
    with _client_lock:
        if _client:
            _client.close()
            _client = None


class Handler(BaseHTTPRequestHandler):
    """HTTP 请求处理器."""

    def log_message(self, format, *args):
        pass  # 静默日志

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self._serve_html()
        elif parsed.path == "/api/quote":
            self._handle_quote()
        elif parsed.path == "/api/kline":
            self._handle_kline()
        elif parsed.path == "/api/kline-all":
            self._handle_kline_all()
        elif parsed.path == "/api/codes":
            self._handle_codes()
        elif parsed.path == "/api/xdxr":
            self._handle_xdxr()
        elif parsed.path == "/api/finance":
            self._handle_finance()
        elif parsed.path == "/api/trade":
            self._handle_trade()
        elif parsed.path == "/api/count":
            self._handle_count()
        elif parsed.path == "/api/status":
            self._handle_status()
        else:
            self._send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        if parsed.path == "/api/kline-all":
            self._handle_kline_all(body)
        elif parsed.path == "/api/codes":
            self._handle_codes(body)
        elif parsed.path == "/api/xdxr":
            self._handle_xdxr(body)
        elif parsed.path == "/api/finance":
            self._handle_finance(body)
        elif parsed.path == "/api/trade":
            self._handle_trade(body)
        else:
            self._send_error(404, "Not Found")

    def _serve_html(self):
        html = HTML_TEMPLATE
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _handle_status(self):
        self._send_json({"status": "ok", "connected": True})

    @_retry_on_conn_error
    def _handle_count(self):
        c = get_client()
        sz = c.count(0)
        sh = c.count(1)
        self._send_json({"sz_count": sz, "sh_count": sh})

    @_retry_on_conn_error
    def _handle_quote(self):
        params = parse_qs(urlparse(self.path).query)
        code = params.get("code", ["sh600000"])[0]
        c = get_client()
        q = c.quote(code)
        self._send_json({"code": code, "quote": q})

    @_retry_on_conn_error
    def _handle_kline_all(self, body=None):
        try:
            if body:
                data = json.loads(body)
                code = data.get("code", "sh600000")
                period = data.get("period", "day")
            else:
                params = parse_qs(urlparse(self.path).query)
                code = params.get("code", ["sh600000"])[0]
                period = params.get("period", ["day"])[0]

            c = get_client()
            bars = c.kline_all(code, period=period)
            self._send_json({"code": code, "period": period, "count": len(bars), "kline": bars})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    @_retry_on_conn_error
    def _handle_codes(self, body=None):
        try:
            if body:
                data = json.loads(body)
                market = int(data.get("market", 1))
            else:
                params = parse_qs(urlparse(self.path).query)
                market = int(params.get("market", ["1"])[0])

            c = get_client()
            codes = c.codes_all(market)
            self._send_json({"market": market, "count": len(codes), "codes": codes[:200]})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    @_retry_on_conn_error
    def _handle_xdxr(self, body=None):
        try:
            if body:
                data = json.loads(body)
                code = data.get("code", "sh600000")
            else:
                params = parse_qs(urlparse(self.path).query)
                code = params.get("code", ["sh600000"])[0]

            c = get_client()
            eq = c.xdxr(code)
            self._send_json({"code": code, "count": len(eq), "xdxr": eq})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    @_retry_on_conn_error
    def _handle_finance(self, body=None):
        try:
            if body:
                data = json.loads(body)
                code = data.get("code", "sh600000")
            else:
                params = parse_qs(urlparse(self.path).query)
                code = params.get("code", ["sh600000"])[0]

            c = get_client()
            fn = c.finance(code)
            self._send_json({"code": code, "finance": fn})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    @_retry_on_conn_error
    def _handle_trade(self, body=None):
        try:
            if body:
                data = json.loads(body)
                code = data.get("code", "sh600000")
            else:
                params = parse_qs(urlparse(self.path).query)
                code = params.get("code", ["sh600000"])[0]

            c = get_client()
            trades = c.today_trade(code, 0, 50)
            self._send_json({"code": code, "count": len(trades), "trade": trades})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    @_retry_on_conn_error
    def _handle_kline(self):
        params = parse_qs(urlparse(self.path).query)
        code = params.get("code", ["sh600000"])[0]
        period = params.get("period", ["day"])[0]
        count = int(params.get("count", ["50"])[0])
        c = get_client()
        bars = c.kline(code, period=period, start=0, count=count)
        self._send_json({"code": code, "period": period, "count": len(bars), "kline": bars})

    def _send_error(self, code, message):
        self._send_json({"error": message}, code)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>通达信行情验证 v2</title>
<link rel="icon" href="data:,">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "SF Mono", "Consolas", monospace; background: #0d1117; color: #c9d1d9; font-size: 14px; }
.header { background: #161b22; border-bottom: 1px solid #30363d; padding: 12px 20px; display: flex; align-items: center; gap: 16px; }
.header h1 { font-size: 18px; color: #58a6ff; }
.header .status { font-size: 12px; padding: 3px 10px; border-radius: 12px; }
.header .status.ok { background: #238636; color: white; }
.header .status.err { background: #da3633; color: white; }
.tabs { display: flex; background: #161b22; border-bottom: 1px solid #30363d; padding: 0 20px; overflow-x: auto; }
.tab { padding: 10px 16px; cursor: pointer; border-bottom: 2px solid transparent; color: #8b949e; white-space: nowrap; }
.tab:hover { color: #c9d1d9; }
.tab.active { color: #58a6ff; border-bottom-color: #58a6ff; }
.controls { background: #161b22; border-bottom: 1px solid #30363d; padding: 12px 20px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.controls label { color: #8b949e; font-size: 12px; }
.controls input, .controls select { background: #0d1117; border: 1px solid #30363d; color: #c9d1d9; padding: 6px 10px; border-radius: 6px; font-size: 13px; font-family: inherit; }
.controls input:focus, .controls select:focus { outline: none; border-color: #58a6ff; }
.controls button { background: #238636; color: white; border: none; padding: 6px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; font-family: inherit; }
.controls button:hover { background: #2ea043; }
.controls button:disabled { background: #30363d; cursor: not-allowed; }
.controls .info { margin-left: auto; color: #8b949e; font-size: 12px; }
.content { padding: 16px 20px; }
.panel { display: none; }
.panel.active { display: block; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 16px; }
.stat-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 12px; }
.stat-card .label { color: #8b949e; font-size: 11px; text-transform: uppercase; }
.stat-card .value { color: #58a6ff; font-size: 20px; font-weight: bold; margin-top: 4px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { background: #161b22; color: #8b949e; padding: 8px 10px; text-align: left; border-bottom: 1px solid #30363d; position: sticky; top: 0; }
td { padding: 6px 10px; border-bottom: 1px solid #21262d; }
tr:hover td { background: #161b22; }
.up { color: #f85149; }
.down { color: #3fb950; }
.loading { color: #58a6ff; padding: 20px; text-align: center; }
.error { color: #f85149; padding: 20px; text-align: center; background: #161b22; border-radius: 8px; margin: 10px 0; }
.summary { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 12px; margin-bottom: 12px; }
.summary .row { display: flex; gap: 20px; flex-wrap: wrap; }
.summary .item { color: #8b949e; }
.summary .item span { color: #c9d1d9; }
</style>
</head>
<body>

<div class="header">
  <h1>通达信行情验证 v2.1</h1>
  <div id="connStatus" class="status ok">已连接</div>
</div>

<div class="tabs">
  <div class="tab active" data-tab="overview">总览</div>
  <div class="tab" data-tab="quote">实时行情</div>
  <div class="tab" data-tab="kline">K线</div>
  <div class="tab" data-tab="klineAll">全量K线</div>
  <div class="tab" data-tab="trade">成交明细</div>
  <div class="tab" data-tab="xdxr">股本变迁</div>
  <div class="tab" data-tab="finance">财务信息</div>
  <div class="tab" data-tab="codes">代码列表</div>
</div>

<div id="overviewPanel" class="panel active">
  <div class="controls">
    <button onclick="loadOverview()">刷新</button>
  </div>
  <div class="content">
    <div class="stats" id="overviewStats"></div>
  </div>
</div>

<div id="quotePanel" class="panel">
  <div class="controls">
    <label>代码</label>
    <input id="quoteCode" value="sh600000" style="width:120px">
    <button onclick="loadQuote()">查询</button>
  </div>
  <div class="content">
    <div id="quoteResult"></div>
  </div>
</div>

<div id="klinePanel" class="panel">
  <div class="controls">
    <label>代码</label>
    <input id="klineCode" value="sh600000" style="width:120px">
    <label>周期</label>
    <select id="klinePeriod">
      <option value="day" selected>日线</option>
      <option value="1m">1分钟</option>
      <option value="5m">5分钟</option>
      <option value="15m">15分钟</option>
      <option value="30m">30分钟</option>
      <option value="60m">60分钟</option>
      <option value="week">周线</option>
    </select>
    <label>数量</label>
    <input id="klineCount" type="number" value="50" style="width:60px">
    <button onclick="loadKline()">查询</button>
  </div>
  <div class="content">
    <div id="klineResult"></div>
  </div>
</div>

<div id="klineAllPanel" class="panel">
  <div class="controls">
    <label>代码</label>
    <input id="klineAllCode" value="sh600000" style="width:120px">
    <label>周期</label>
    <select id="klineAllPeriod">
      <option value="day" selected>日线</option>
      <option value="week">周线</option>
      <option value="month">月线</option>
    </select>
    <button onclick="loadKlineAll()">全量查询</button>
  </div>
  <div class="content">
    <div id="klineAllResult"></div>
  </div>
</div>

<div id="tradePanel" class="panel">
  <div class="controls">
    <label>代码</label>
    <input id="tradeCode" value="sh600000" style="width:120px">
    <button onclick="loadTrade()">查询</button>
  </div>
  <div class="content">
    <div id="tradeResult"></div>
  </div>
</div>

<div id="xdxrPanel" class="panel">
  <div class="controls">
    <label>代码</label>
    <input id="xdxrCode" value="sh600000" style="width:120px">
    <button onclick="loadXdxr()">查询</button>
  </div>
  <div class="content">
    <div id="xdxrResult"></div>
  </div>
</div>

<div id="financePanel" class="panel">
  <div class="controls">
    <label>代码</label>
    <input id="financeCode" value="sh600000" style="width:120px">
    <button onclick="loadFinance()">查询</button>
  </div>
  <div class="content">
    <div id="financeResult"></div>
  </div>
</div>

<div id="codesPanel" class="panel">
  <div class="controls">
    <label>市场</label>
    <select id="codesMarket">
      <option value="0" selected>深圳 (0)</option>
      <option value="1">上海 (1)</option>
    </select>
    <button onclick="loadCodes()">查询</button>
  </div>
  <div class="content">
    <div id="codesResult"></div>
  </div>
</div>

<script>
// Tab switching
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
    tab.classList.add("active");
    const panelId = tab.dataset.tab + "Panel";
    document.getElementById(panelId).classList.add("active");
  });
});

function api(path, method="GET", body=null) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  let url = path;
  if (method === "GET" && body) {
    url += "?" + new URLSearchParams(body).toString();
  } else if (body) {
    opts.body = JSON.stringify(body);
  }
  return fetch(url, opts).then(r => r.json());
}

function el(id) { return document.getElementById(id); }

function fmtNum(n) {
  if (n == null) return "-";
  if (typeof n === "number") return n.toLocaleString("zh-CN", {maximumFractionDigits: 4});
  return String(n);
}

function fmtDate(d) {
  if (!d) return "-";
  const s = String(d);
  if (s.length === 8) return s.slice(0,4)+"-"+s.slice(4,6)+"-"+s.slice(6,8);
  return s;
}

function showLoading(containerId) {
  el(containerId).innerHTML = '<div class="loading">加载中...</div>';
}

function showError(containerId, msg) {
  el(containerId).innerHTML = '<div class="error">错误: ' + msg + '</div>';
}

function showTable(containerId, headers, rows) {
  let html = '<table><thead><tr>' + headers.map(h => '<th>'+h+'</th>').join('') + '</tr></thead><tbody>';
  for (const row of rows) {
    html += '<tr>' + row.map(v => '<td>' + fmtNum(v) + '</td>').join('') + '</tr>';
  }
  html += '</tbody></table>';
  el(containerId).innerHTML = html;
}

function showSummary(containerId, items) {
  let html = '<div class="summary"><div class="row">';
  for (const [k, v] of Object.entries(items)) {
    html += '<div class="item">' + k + ': <span>' + fmtNum(v) + '</span></div>';
  }
  html += '</div></div>';
  el(containerId).innerHTML = html;
}

function showQuoteDetail(containerId, q) {
  const fields = ["code","name","price","pre_close","open","high","low","volume","amount",
                  "bid1","ask1","bid_vol1","ask_vol1"];
  let html = '<div class="summary"><div class="row">';
  for (const f of fields) {
    if (q[f] !== undefined && q[f] !== null) {
      html += '<div class="item">' + f + ': <span>' + fmtNum(q[f]) + '</span></div>';
    }
  }
  html += '</div></div>';
  // 五档
  html += '<table><thead><tr><th>档位</th><th>买价</th><th>买量</th><th>卖价</th><th>卖量</th></tr></thead><tbody>';
  for (let i = 0; i < 5; i++) {
    const bp = q["bid" + (i+1)], bv = q["bid_vol" + (i+1)];
    const ap = q["ask" + (i+1)], av = q["ask_vol" + (i+1)];
    html += '<tr><td>' + (i+1) + '</td><td>' + fmtNum(bp) + '</td><td>' + fmtNum(bv) + '</td><td>' + fmtNum(ap) + '</td><td>' + fmtNum(av) + '</td></tr>';
  }
  html += '</tbody></table>';
  el(containerId).innerHTML = html;
}

async function loadOverview() {
  showLoading("overviewStats");
  try {
    const data = await api("/api/status");
    if (data.connected) {
      const sz = await api("/api/count");
      showSummary("overviewStats", {
        "连接状态": "正常",
        "深圳证券": sz.sz_count,
        "上海证券": sz.sh_count
      });
    } else {
      showError("overviewStats", "服务器未连接");
    }
  } catch(e) {
    showError("overviewStats", e.message);
  }
}

async function loadQuote() {
  const code = el("quoteCode").value.trim();
  if (!code) return;
  showLoading("quoteResult");
  try {
    const data = await api("/api/quote", "GET", {code});
    if (data.error) throw new Error(data.error);
    showQuoteDetail("quoteResult", data.quote);
  } catch(e) {
    showError("quoteResult", e.message);
  }
}

async function loadKline() {
  const code = el("klineCode").value.trim();
  const period = el("klinePeriod").value;
  const count = parseInt(el("klineCount").value) || 50;
  if (!code) return;
  showLoading("klineResult");
  try {
    const data = await api("/api/kline", "GET", {code, period, count});
    if (data.error) throw new Error(data.error);
    let html = '<div class="summary"><div class="row"><div class="item">代码: <span>' + data.code + '</span></div><div class="item">周期: <span>' + data.period + '</span></div><div class="item">数量: <span>' + data.count + '</span></div></div></div>';
    const headers = ["日期", "开盘", "最高", "最低", "收盘", "成交量", "成交额"];
    const rows = data.kline.map(k => [k.datetime, k.open, k.high, k.low, k.close, k.vol, k.amount]);
    html += '<table><thead><tr>' + headers.map(h => '<th>'+h+'</th>').join('') + '</tr></thead><tbody>';
    for (const r of rows.reverse()) {
      html += '<tr>' + r.map((v, i) => {
        if (i === 0) return '<td>' + v + '</td>';
        if (i === 6) return '<td>' + (v != null ? Math.round(v).toLocaleString() : '-') + '</td>';
        return '<td>' + fmtNum(v) + '</td>';
      }).join('') + '</tr>';
    }
    html += '</tbody></table>';
    el("klineResult").innerHTML = html;
  } catch(e) {
    showError("klineResult", e.message);
  }
}

async function loadKlineAll() {
  const code = el("klineAllCode").value.trim();
  const period = el("klineAllPeriod").value;
  if (!code) return;
  showLoading("klineAllResult");
  try {
    const data = await api("/api/kline-all", "POST", {code, period});
    if (data.error) throw new Error(data.error);
    let html = '<div class="summary"><div class="row"><div class="item">代码: <span>' + data.code + '</span></div><div class="item">周期: <span>' + data.period + '</span></div><div class="item">总条数: <span>' + data.count + '</span></div></div></div>';
    const headers = ["日期", "开盘", "最高", "最低", "收盘", "成交量", "成交额"];
    const rows = data.kline.slice(-100).map(k => [k.datetime, k.open, k.high, k.low, k.close, k.vol, k.amount]);
    html += '<p style="color:#8b949e;margin:8px 0;">显示最近 ' + rows.length + ' 条 (共 ' + data.count + ' 条)</p>';
    html += '<table><thead><tr>' + headers.map(h => '<th>'+h+'</th>').join('') + '</tr></thead><tbody>';
    for (const r of rows.reverse()) {
      html += '<tr>' + r.map((v, i) => {
        if (i === 0) return '<td>' + v + '</td>';
        if (i === 6) return '<td>' + (v != null ? Math.round(v).toLocaleString() : '-') + '</td>';
        return '<td>' + fmtNum(v) + '</td>';
      }).join('') + '</tr>';
    }
    html += '</tbody></table>';
    el("klineAllResult").innerHTML = html;
  } catch(e) {
    showError("klineAllResult", e.message);
  }
}

async function loadTrade() {
  const code = el("tradeCode").value.trim();
  if (!code) return;
  showLoading("tradeResult");
  try {
    const data = await api("/api/trade", "POST", {code});
    if (data.error) throw new Error(data.error);
    let html = '<div class="summary"><div class="row"><div class="item">代码: <span>' + data.code + '</span></div><div class="item">数量: <span>' + data.count + '</span></div></div></div>';
    const headers = ["时间", "价格", "成交量", "笔数", "买卖方向"];
    const rows = data.trade.map(t => [t.time, t.price, t.vol, t.num, t.buyorsell]);
    html += '<table><thead><tr>' + headers.map(h => '<th>'+h+'</th>').join('') + '</tr></thead><tbody>';
    for (const r of rows) {
      html += '<tr>' + r.map(v => '<td>' + fmtNum(v) + '</td>').join('') + '</tr>';
    }
    html += '</tbody></table>';
    el("tradeResult").innerHTML = html;
  } catch(e) {
    showError("tradeResult", e.message);
  }
}

async function loadXdxr() {
  const code = el("xdxrCode").value.trim();
  if (!code) return;
  showLoading("xdxrResult");
  try {
    const data = await api("/api/xdxr", "POST", {code});
    if (data.error) throw new Error(data.error);
    let html = '<div class="summary"><div class="row"><div class="item">代码: <span>' + data.code + '</span></div><div class="item">记录数: <span>' + data.count + '</span></div></div></div>';
    const headers = ["日期", "类型", "名称", "分红", "送转股", "流通股本", "总股本"];
    const rows = data.xdxr.map(e => [
      e.year ? e.year + "-" + String(e.month||1).padStart(2,"0") + "-" + String(e.day||1).padStart(2,"0") : "-",
      e.category, e.name, e.fenhong, e.songzhuangu, e.panhouliutong, e.houzongguben
    ]);
    html += '<table><thead><tr>' + headers.map(h => '<th>'+h+'</th>').join('') + '</tr></thead><tbody>';
    for (const r of rows) {
      html += '<tr>' + r.map(v => '<td>' + fmtNum(v) + '</td>').join('') + '</tr>';
    }
    html += '</tbody></table>';
    el("xdxrResult").innerHTML = html;
  } catch(e) {
    showError("xdxrResult", e.message);
  }
}

async function loadFinance() {
  const code = el("financeCode").value.trim();
  if (!code) return;
  showLoading("financeResult");
  try {
    const data = await api("/api/finance", "POST", {code});
    if (data.error) throw new Error(data.error);
    let html = '<div class="summary"><div class="row">';
    html += '<div class="item">代码: <span>' + data.code + '</span></div>';
    html += '<div class="item">总股本: <span>' + fmtNum(data.finance.zongguben) + '</span></div>';
    html += '<div class="item">流通股本: <span>' + fmtNum(data.finance.liutongguben) + '</span></div>';
    html += '<div class="item">每股收益: <span>' + fmtNum(data.finance.eps) + '</span></div>';
    html += '<div class="item">每股净资产: <span>' + fmtNum(data.finance.jingzichan) + '</span></div>';
    html += '<div class="item">主营业务收入: <span>' + fmtNum(data.finance.zhuyingshouru) + '</span></div>';
    html += '<div class="item">净利润: <span>' + fmtNum(data.finance.shuihoulirun) + '</span></div>';
    html += '<div class="item">行业: <span>' + data.finance.industry + '</span></div>';
    html += '<div class="item">省份: <span>' + data.finance.province + '</span></div>';
    html += '</div></div>';
    el("financeResult").innerHTML = html;
  } catch(e) {
    showError("financeResult", e.message);
  }
}

async function loadCodes() {
  const market = parseInt(el("codesMarket").value);
  showLoading("codesResult");
  try {
    const data = await api("/api/codes", "POST", {market});
    if (data.error) throw new Error(data.error);
    let html = '<div class="summary"><div class="row"><div class="item">市场: <span>' + market + '</span></div><div class="item">总数: <span>' + data.count + '</span></div><div class="item">显示: <span>' + data.codes.length + '</span></div></div></div>';
    const headers = ["代码", "名称", "volunit", "decimal_point"];
    const rows = data.codes.map(c => [c.code, c.name, c.volunit, c.decimal_point]);
    html += '<table><thead><tr>' + headers.map(h => '<th>'+h+'</th>').join('') + '</tr></thead><tbody>';
    for (const r of rows) {
      html += '<tr>' + r.map(v => '<td>' + fmtNum(v) + '</td>').join('') + '</tr>';
    }
    html += '</tbody></table>';
    el("codesResult").innerHTML = html;
  } catch(e) {
    showError("codesResult", e.message);
  }
}

// Init
loadOverview();
</script>
</body>
</html>
"""


def main():
    host = "0.0.0.0"
    port = 8080
    server = HTTPServer((host, port), Handler)
    print(f"Web 服务器启动于 http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        release_client()
        server.server_close()
        print("已关闭")


if __name__ == "__main__":
    main()
