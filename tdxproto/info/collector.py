"""InfoCollector — 将 F10 接口统一封装为结构化可读数据。

每个方法返回的 dict 均使用可读字段名（T/N 编码已通过官方字段字典翻译），
数值保真（int/float 原样保留，无数据为 None），可直接入库或导出 JSON/CSV。

字段字典来源: 通达信官方「专业财务数据项」编号字典
  https://help.tdx.com.cn/gspt/docs/markdown/redword/Profinance/profinancedatalist.html
  规律: finance_report 的 T 编码 = 官方编号 - 1（已用 StockClient.finance() 交叉验证）

可用接口清单:
  news / announcements / research_reports / business_composition /
  northbound_holding / dividends / topics / score / topic_members /
  profile / balance_sheet / cashflow / diagnosis / shareholder_plans / roadshows
"""

from __future__ import annotations

from .client import InfoClient
from .field_dict import (
    balance_sheet_fields, income_statement_fields, cashflow_fields,
    profile_fields, translate_row,
)


def news_rows(items: list) -> list[dict]:
    """新闻列表 → 结构化行。"""
    return [
        {
            "rec_id": x.rec_id,
            "issue_date": x.issue_date,
            "redistime": x.redistime,
            "title": x.title,
            "source": x.source,
            "url": x.url,
        }
        for x in items
    ]


def announcement_rows(items: list) -> list[dict]:
    """公告列表 → 结构化行（含 PDF 直链）。"""
    return [
        {
            "rec_id": x.rec_id,
            "issue_date": x.issue_date,
            "redistime": x.redistime,
            "title": x.title,
            "typename": x.typename,
            "typecode": x.typecode,
            "source": x.source,
            "pdf_url": x.pdf_url,
        }
        for x in items
    ]


def report_rows(items: list) -> list[dict]:
    """研报列表 → 结构化行。"""
    return [
        {
            "report_id": int(x.report_id),
            "date": x.date,
            "title": x.title,
            "rating": x.rating,
            "analyst": x.analyst,
        }
        for x in items
    ]


def composition_rows(rows: list[dict]) -> list[dict]:
    """主营构成 → 结构化行。

    服务端原始列: N000=维度(按地区/按产品), N001=报告期代码,
    N002=名称, N003=营业收入, N004=营收占比%, N005=利润,
    N006=利润占比%, N007=主营利润, N008=主营利润占比%, N009=毛利率%。
    """
    out = []
    for r in rows:
        out.append({
            "dimension": r.get("N000"),
            "name": r.get("N002"),
            "revenue": r.get("N003"),
            "revenue_pct": r.get("N004"),
            "profit": r.get("N005"),
            "profit_pct": r.get("N006"),
            "main_profit": r.get("N007"),
            "main_profit_pct": r.get("N008"),
            "gross_margin_pct": r.get("N009"),
        })
    return out


def northbound_rows(rows: list[dict]) -> list[dict]:
    """沪深股通持股 → 结构化行（按报告期排序）。

    原始列: N001=日期, N002=持股比例%, N003=持股数量, N004=净买入(股),
    N005=净买入变动%, N006=持股占流通股本%(估)。
    """
    out = []
    for r in rows:
        out.append({
            "date": r.get("N001"),
            "holding_pct": r.get("N002"),
            "holding_shares": r.get("N003"),
            "net_buy_shares": r.get("N004"),
            "net_buy_pct": r.get("N005"),
            "holding_float_pct": r.get("N006"),
        })
    return out


def dividend_rows(rows: list[dict]) -> list[dict]:
    """分红方案 → 结构化行。

    原始列: rq=报告期, T003=公告日期, T004=方案文本, T006=每股派息(税后),
    T026=股息率%, T021=股权登记日, T023=除权除息日, T036=方案状态,
    aT036=状态代码, glzfl=分红比例(%), jdcode=股东范围。
    """
    out = []
    for r in rows:
        out.append({
            "period": r.get("rq"),
            "announce_date": r.get("T003"),
            "plan_text": r.get("T004"),
            "per_share_dividend": r.get("T006"),
            "yield_pct": r.get("T026"),
            "record_date": r.get("T021"),
            "ex_date": r.get("T023"),
            "status": r.get("T036"),
            "status_code": r.get("aT036"),
            "dividend_ratio_pct": r.get("glzfl"),
            "shareholder_scope": r.get("jdcode"),
        })
    return out


def topic_rows(rows: list[dict]) -> list[dict]:
    """题材标签 → 结构化行。t001 为数字题材 ID，可直接用于题材内对比。"""
    return [
        {
            "topic_id": str(r.get("t001")),
            "topic_name": r.get("t002"),
        }
        for r in rows
    ]


def score_rows(rows: list[dict]) -> list[dict]:
    """个股评分 → 结构化行。

    原始列: N001=综合评分, N002=排名, N003=同组总数, N004=市场排名,
    N005=市场总数, N006=分位%, N007=评分日期, N008=业绩, N009=估值,
    N010=题材, N011=资金, N012=行业, N013=成长, N014=盈利, N015=估值分,
    N016=机构, N017=综合修正, N018=股票名。
    """
    out = []
    for r in rows:
        out.append({
            "name": r.get("N018"),
            "industry": r.get("N012"),
            "score_date": r.get("N007"),
            "total_score": r.get("N001"),
            "rank": r.get("N002"),
            "group_total": r.get("N003"),
            "market_rank": r.get("N004"),
            "market_total": r.get("N005"),
            "percentile_pct": r.get("N006"),
            "performance": r.get("N008"),
            "valuation": r.get("N009"),
            "topic": r.get("N010"),
            "capital": r.get("N011"),
            "growth": r.get("N013"),
            "profitability": r.get("N014"),
            "valuation_score": r.get("N015"),
            "institution": r.get("N016"),
            "adjusted": r.get("N017"),
        })
    return out


class InfoCollector:
    """基于 InfoClient 的结构化采集器。"""

    def __init__(self, client: InfoClient | None = None, *, timeout: float = 10.0):
        self.client = client or InfoClient(timeout=timeout)

    def news(self, market: int, code: str) -> list[dict]:
        return news_rows(self.client.news(market, code))

    def announcements(self, market: int, code: str) -> list[dict]:
        return announcement_rows(self.client.announcements(market, code))

    def research_reports(self, code: str, page: int = 1, page_size: int = 20) -> list[dict]:
        return report_rows(self.client.research_reports(code, page=page, page_size=page_size))

    def business_composition(self, code: str, report_date: str | None = None) -> list[dict]:
        resp = self.client.business_composition(code, report_date)
        return composition_rows(resp.rows)

    def northbound_holding(self, code: str) -> list[dict]:
        resp = self.client.northbound_holding(code)
        return northbound_rows(resp.rows)

    def dividends(self, code: str, section: str = "fh") -> list[dict]:
        resp = self.client.dividend_financing(code, section)
        return dividend_rows(resp.rows)

    def topics(self, code: str) -> list[dict]:
        resp = self.client.topic_ids(code)
        return topic_rows(resp.rows)

    def score(self, code: str) -> list[dict]:
        resp = self.client.stock_score(code)
        return score_rows(resp.rows)

    def balance_sheet(self, code: str) -> list[dict]:
        """资产负债表 → 可读字段名行（多报告期）。利润表端点无数据，仅返回资产负债表。"""
        resp = self.client.finance_report(code, "zcfzb")
        fmap = balance_sheet_fields()
        return [translate_row(r, fmap) for r in resp.rows]

    def cashflow(self, code: str) -> list[dict]:
        """现金流量表 → 可读字段名行（多报告期）。"""
        resp = self.client.finance_report(code, "xjllb")
        fmap = cashflow_fields()
        return [translate_row(r, fmap) for r in resp.rows]

    def profile(self, code: str) -> dict:
        """公司概况 → 可读字段名单行。"""
        resp = self.client.company_profile(code)
        rows = resp.rows
        if not rows:
            return {}
        return translate_row(rows[0], profile_fields())

    def diagnosis(self, code: str, section: str = "yynl") -> list[dict]:
        """财务诊断 → 原始行（N 编码含义随 section 变化，保留原名）。

        section: yynl 营运能力, cznl 成长能力, ylnl 盈利能力。
        返回多行：第 1 行个股自身，其余为同行业对比公司。
        """
        resp = self.client.finance_diagnosis(code, section)
        return list(resp.rows)

    def shareholder_plans(self, code: str) -> list[dict]:
        """股东增减持计划 → 可读字段名行。

        原始列: N001=公告日期, N002=变动类型, N003=股东名称, N004=股东身份,
        N005=拟减持股数, N006=减持比例%, N007=变动金额下限, N008=变动金额上限,
        N009=起始日, N010=截止日, N011=状态, N012=记录ID。
        """
        resp = self.client.shareholder_change_plans(code)
        out = []
        for r in resp.rows:
            out.append({
                "announce_date": r.get("N001"),
                "action": r.get("N002"),
                "shareholder": r.get("N003"),
                "shareholder_type": r.get("N004"),
                "planned_shares": r.get("N005"),
                "planned_pct": r.get("N006"),
                "amount_min": r.get("N007"),
                "amount_max": r.get("N008"),
                "start_date": r.get("N009"),
                "end_date": r.get("N010"),
                "status": r.get("N011"),
                "record_id": r.get("N012"),
            })
        return out

    def roadshows(self, market: int, code: str) -> list[dict]:
        """路演列表 → 结构化行（含详情页链接 url）。"""
        items = self.client.roadshows(market, code)
        return [
            {
                "title": x.title,
                "type": x.source,
                "date": x.issue_date,
                "time": x.redistime,
                "url": x.url,
            }
            for x in items
        ]

    def topic_members(self, code: str, topic_id: str | None = None,
                      sort_by: str = "zdf") -> list[dict]:
        """题材内成分股排名。topic_id 取数字 ID（topics() 的 topic_id 字段）。"""
        if topic_id is None:
            topics = self.topics(code)
            if not topics:
                return []
            topic_id = topics[0]["topic_id"]
        resp = self.client.topic_compare(code, topic_id, sort_by=sort_by)
        rows = []
        for r in resp.rows:
            rows.append({
                "rank": r.get("pm"),
                "code": r.get("zqdm"),
                "name": r.get("zqjc"),
                "market": r.get("sc"),
                "change_pct": r.get("zdf"),
                "change_3d": r.get("zdf_3d"),
                "change_5d": r.get("zdf_5d"),
                "change_20d": r.get("zdf_20d"),
                "change_60d": r.get("zdf_60d"),
                "change_ys": r.get("zdf_ys"),
                "stat_date": r.get("tjdate"),
            })
        return rows

    def snapshot(self, market: int, code: str) -> dict:
        """一次调用采集全部干净数据。"""
        return {
            "code": code[-6:],
            "news": self.news(market, code),
            "announcements": self.announcements(market, code),
            "research_reports": self.research_reports(code),
            "business_composition": self.business_composition(code),
            "northbound_holding": self.northbound_holding(code),
            "dividends": self.dividends(code),
            "topics": self.topics(code),
            "score": self.score(code),
            "profile": self.profile(code),
            "balance_sheet": self.balance_sheet(code),
            "cashflow": self.cashflow(code),
            "diagnosis": self.diagnosis(code),
            "shareholder_plans": self.shareholder_plans(code),
            "roadshows": self.roadshows(market, code),
        }
