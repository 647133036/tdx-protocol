"""InfoClient — 通达信 F10 资讯 HTTP 客户端（7615 端口 / TQLEX 网关）。

零外部依赖（stdlib 仅 urllib.request）。
"""

from __future__ import annotations

import json
from typing import Any
from urllib import request as urlrequest
from urllib.parse import urlencode

from .models import (
    TqlexError, TqlexResponse, TqlexResultSet,
    NewsItem, AnnouncementItem, ResearchReport,
)

_BASE_URL = "http://static.tdx.com.cn:7615/TQLEX"
_UA = "eltdx/1.0"


def _post(entry: str, body: Any, timeout: float) -> TqlexResponse:
    url = f"{_BASE_URL}?{urlencode({'Entry': entry})}"
    data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = urlrequest.Request(
        url, data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": _UA,
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            raw_bytes = resp.read()
    except Exception as e:
        raise TqlexError(f"TQLEX 请求失败 [{entry}]: {e}") from e

    try:
        raw = json.loads(raw_bytes.decode("utf-8-sig"))
    except Exception as e:
        raise TqlexError(f"TQLEX 返回非 JSON [{entry}]: {e}") from e

    if not isinstance(raw, dict):
        raise TqlexError(f"TQLEX 返回非对象 [{entry}]")

    result_sets: list[TqlexResultSet] = []
    for rs in (raw.get("ResultSets") or ()):
        if not isinstance(rs, dict):
            continue
        cols = [str(c) for c in (rs.get("ColName") or ())]
        content = rs.get("Content") or ()
        rows = []
        for row in content:
            if isinstance(row, (list, tuple)):
                rows.append(dict(zip(cols, row)))
            elif isinstance(row, dict):
                rows.append(row)
        result_sets.append(TqlexResultSet(
            key=rs.get("ResultSetKey"),
            columns=cols,
            rows=rows,
        ))

    error_code = raw.get("ErrorCode")
    if error_code is not None:
        error_code = int(error_code)

    return TqlexResponse(
        entry=entry,
        error_code=error_code,
        result_sets=result_sets,
        raw=raw,
    )


def _params(entry: str, *params: Any, timeout: float = 8.0) -> TqlexResponse:
    return _post(entry, {"Params": list(params)}, timeout=timeout)


def _code6(market: int, code: str) -> str:
    return code[-6:]


def _cache_list(market: int, code: str, kind: str, timeout: float) -> TqlexResponse:
    code6 = _code6(market, code)
    body = {"action": "get", "key": f"{kind}:{market}_{code6}", "bin": "1", "qsid": "tdx"}
    return _post("CWSearch.tzx_rcache", body, timeout=timeout)


class InfoClient:
    """通达信 F10 资讯客户端（7615 HTTP 网关）。

    用法::

        from tdxproto.info import InfoClient

        client = InfoClient()
        news = client.news(0, "000001")
        for item in news:
            print(item.title, item.issue_date)
    """

    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout

    # ---- 缓存列表（新闻/公告/路演） ----

    def news(self, market: int, code: str) -> list[NewsItem]:
        """实时新闻列表。"""
        resp = _cache_list(market, code, "xw", self.timeout)
        return [
            NewsItem(
                issue_date=r.get("issue_date", ""),
                title=r.get("title", ""),
                source=r.get("source", ""),
                redistime=r.get("redistime", ""),
                rec_id=r.get("rec_id", ""),
            )
            for r in resp.rows
        ]

    def announcements(self, market: int, code: str) -> list[AnnouncementItem]:
        """公告列表（含 PDF 下载链接）。"""
        resp = _cache_list(market, code, "gg", self.timeout)
        return [
            AnnouncementItem(
                issue_date=r.get("issue_date", ""),
                title=r.get("title", ""),
                typecode=r.get("typecode", ""),
                typename=r.get("typename", ""),
                rec_id=r.get("rec_id", ""),
                pdf_url=r.get("url", ""),
                source=r.get("source", ""),
                redistime=r.get("redistime", ""),
            )
            for r in resp.rows
        ]

    def roadshows(self, market: int, code: str) -> list[NewsItem]:
        """路演列表。"""
        resp = _cache_list(market, code, "ly", self.timeout)
        return [
            NewsItem(
                issue_date=r.get("issue_date", ""),
                title=r.get("title", ""),
                source=r.get("source", ""),
                redistime=r.get("redistime", ""),
                rec_id=r.get("rec_id", ""),
            )
            for r in resp.rows
        ]

    # ---- 公司资讯 ----

    def research_reports(self, code: str, page: int = 1, page_size: int = 20) -> list[ResearchReport]:
        """研报列表。"""
        resp = _params("CWServ.tdxf10_gg_gszx", _code6(0, code), "gsyj", "", "0", str(page), str(page_size), timeout=self.timeout)
        return [
            ResearchReport(
                title=r.get("T039", ""),
                rating=r.get("T004", ""),
                analyst=r.get("T009", ""),
                date=r.get("T012", ""),
                report_id=r.get("T011", 0),
            )
            for r in resp.rows
        ]

    def company_news(self, code: str, section: str = "gsyj", keyword: str = "", rating: str = "0",
                     page: int = 1, page_size: int = 20) -> TqlexResponse:
        """公司资讯。section=gsyj 研报, jgcs 监管措施, xw 新闻。"""
        return _params("CWServ.tdxf10_gg_gszx", _code6(0, code), section, keyword, rating, str(page), str(page_size), timeout=self.timeout)

    def stock_info(self, code: str) -> TqlexResponse:
        """股票基础信息查询。"""
        return _params("CWServ.tdxf10_gg_comreq", "gpquery", _code6(0, code), timeout=self.timeout)

    def company_profile(self, code: str, section: str = "8") -> TqlexResponse:
        """公司概况。section=8 发行上市, 9 指数调出调入。"""
        return _params("CWServ.tdxf10_gg_gsgk", section, _code6(0, code), "", timeout=self.timeout)

    def business_periods(self, code: str) -> TqlexResponse:
        """主营构成可选报告期。"""
        return _params("CWServ.tdxf10_gg_comreq", "zygcfx", _code6(0, code), timeout=self.timeout)

    def business_composition(self, code: str, report_date: str | None = None) -> TqlexResponse:
        """主营构成。不传 report_date 时自动取最新报告期。"""
        code6 = _code6(0, code)
        if report_date is None:
            periods = self.business_periods(code)
            for row in periods.rows:
                rd = row.get("T002")
                if rd:
                    report_date = str(rd)
                    break
        return _params("CWServ.tdxf10_gg_jyfx", code6, "zygc", str(report_date or ""), timeout=self.timeout)

    # ---- 财务数据 ----

    def finance_report(self, code: str, report_type: str = "zcfzb") -> TqlexResponse:
        """财务报表。report_type=zcfzb 资产负债表, lrb 利润表, xjllb 现金流量表。"""
        return _params("CWServ.tdxf10_gg_cwfx", _code6(0, code), report_type, "", timeout=self.timeout)

    def finance_diagnosis(self, code: str, section: str = "yynl", scope: str = "") -> TqlexResponse:
        """财务诊断。section=yynl 营运能力, chnl 偿还能力, cznl 成长能力, ylnl 盈利能力。"""
        return _params("CWServ.tdxf10_gg_cwzd", section, _code6(0, code), scope, timeout=self.timeout)

    def dividend_financing(self, code: str, section: str = "fh") -> TqlexResponse:
        """分红融资。section=fh 分红方案, zf 增发, pz 配股。"""
        return _params("CWServ.tdxf10_gg_fhrz", _code6(0, code), section, timeout=self.timeout)

    # ---- 评分与排名 ----

    def stock_score(self, code: str, section: str = "pf", arg: str = "") -> TqlexResponse:
        """个股总评。section=pf 综合评分。"""
        return _params("CWServ.tdxf10_gg_ggzp", section, _code6(0, code), arg, "", timeout=self.timeout)

    def profit_forecast(self, code: str) -> TqlexResponse:
        """盈利预测评级统计。"""
        return _params("CWServ.tdxf10_gg_ybpj", _code6(0, code), "ylyctj", timeout=self.timeout)

    # ---- 股东与资本运作 ----

    def shareholder_change_plans(self, code: str, page: int = 1, page_size: int = 20,
                                 filter1: str = "", filter2: str = "") -> TqlexResponse:
        """股东增减持计划。"""
        return _params("CWServ.tdxf10_gg_gdyj", _code6(0, code), "gdzjcjh", filter1, filter2,
                       str(page), str(page), str(page_size), timeout=self.timeout)

    def northbound_holding(self, code: str, section: str = "bszj",
                           filter_value: str = "", page: int = 1, page_size: int = 20) -> TqlexResponse:
        """沪深股通持股变化。"""
        return _params("CWServ.tdxf10_gg_zlcc", _code6(0, code), section, filter_value,
                       str(page), str(page), str(page_size), timeout=self.timeout)

    def governance(self, code: str, section: str = "wgcl", arg: str = "") -> TqlexResponse:
        """资本运作治理。section=wgcl 违规处理, dbmx 担保明细。"""
        return _params("CWServ.tdxf10_gg_zbyz", section, _code6(0, code), arg, timeout=self.timeout)

    # ---- 题材热点 ----

    def hot_topics(self, code: str, section: str = "zttzbkz") -> TqlexResponse:
        """热点题材。section=zttzbkz 板块题材。"""
        return _params("CWServ.tdxf10_gg_rdtc", _code6(0, code), section, timeout=self.timeout)

    def topic_ids(self, code: str) -> TqlexResponse:
        """股票关联题材 ID 列表。"""
        return _params("CWServ.tdxf10_gg_comreq", "rdtcgn", _code6(0, code), timeout=self.timeout)

    def topic_compare(self, code: str, topic_id: str, section: str = "gndbzfsj", sort_by: str = "zdf") -> TqlexResponse:
        """题材内对比排名。"""
        return _params("CWServ.tdxf10_gg_rdtc_gndb", section, _code6(0, code), topic_id, sort_by, timeout=self.timeout)

    # ---- 低层接口 ----

    def call(self, entry: str, body: Any | None = None, *, params: list[Any] | None = None) -> TqlexResponse:
        """调用任意 TQLEX Entry。"""
        if body is not None and params is not None:
            raise ValueError("body 和 params 只能传一个")
        payload = {"Params": list(params)} if params is not None else (body if body is not None else {})
        return _post(entry, payload, timeout=self.timeout)