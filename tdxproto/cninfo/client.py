"""CninfoClient — 巨潮资讯网公告检索客户端（零外部依赖，stdlib 仅 urllib + html.parser）。

提供三个核心功能：
  1. ``get_announcements()`` — 公告列表检索（支持关键词/类别/板块/日期过滤）
  2. ``get_announcements_batch()`` — 批量多股票检索
  3. ``get_announcement_detail()`` — 公告正文（HTML 转纯文本）
  4. ``download_pdf()`` — 公告 PDF 附件下载
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib import parse
from urllib import request as urlrequest

from .models import Announcement, CninfoError, build_detail_url, build_pdf_url

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_STOCK_MAP_URL = "http://www.cninfo.com.cn/new/data/szse_stock.json"
_QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
_DETAIL_URL = "https://www.cninfo.com.cn/new/disclosure/detail"

_ORGID_MAP: dict[str, str] = {}


def _http_get_json(url: str, timeout: float = 15.0) -> Any:
    req = urlrequest.Request(url, headers={"User-Agent": _UA})
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_text(url: str, timeout: float = 15.0) -> str:
    req = urlrequest.Request(url, headers={"User-Agent": _UA})
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _http_post_form(url: str, payload: dict[str, str], timeout: float = 15.0) -> Any:
    data = parse.urlencode(payload).encode("utf-8")
    req = urlrequest.Request(
        url,
        data=data,
        headers={
            "User-Agent": _UA,
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://www.cninfo.com.cn/new/disclosure",
            "Origin": "https://www.cninfo.com.cn",
        },
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class _HtmlTextExtractor(HTMLParser):
    """stdlib HTML 转纯文本。"""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = False
        if tag in ("p", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "li"):
            self._parts.append("")

    def text(self) -> str:
        raw = "\n".join(self._parts)
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


def _extract_html_text(html: str) -> str:
    parser = _HtmlTextExtractor()
    parser.feed(html)
    return parser.text()


def _ts_to_date(ts: Any) -> str:
    if not ts:
        return ""
    if isinstance(ts, str):
        return ts[:10]
    if isinstance(ts, (int, float)):
        try:
            dt = datetime.fromtimestamp(ts / 1000)
            return dt.strftime("%Y-%m-%d")
        except (OSError, ValueError, OverflowError):
            return ""
    return ""


def _fetch_stock_map(timeout: float = 15.0) -> dict[str, str]:
    """拉取 szse_stock.json 返回 {code: orgId} 映射。"""
    try:
        data = _http_get_json(_STOCK_MAP_URL, timeout=timeout)
        return {item["code"]: item["orgId"] for item in data.get("stockList", [])}
    except Exception:
        return {}


def _resolve_orgid(code: str, timeout: float = 15.0) -> str:
    """解析股票代码对应的 orgId。"""
    if not _ORGID_MAP:
        _ORGID_MAP.update(_fetch_stock_map(timeout))
    if code in _ORGID_MAP:
        return _ORGID_MAP[code]
    pfx = code[0]
    if pfx == "6":
        return f"gssh0{code}"
    if pfx in ("8", "4"):
        return f"gsbj0{code}"
    return f"gssz0{code}"


def _query_announcements(
    code: str,
    *,
    count: int,
    page: int,
    searchkey: str = "",
    category: str = "",
    plate: str = "",
    se_date: str = "",
    column: str = "",
    timeout: float = 15.0,
) -> list[Announcement]:
    """POST 公告检索接口，解析为 Announcement 列表。"""
    org_id = _resolve_orgid(code, timeout)
    payload = {
        "stock": f"{code},{org_id}",
        "tabName": "fulltext",
        "pageSize": str(count),
        "pageNum": str(page),
        "column": column,
        "category": category,
        "plate": plate,
        "seDate": se_date,
        "searchkey": searchkey,
        "secid": "",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    try:
        resp = _http_post_form(_QUERY_URL, payload, timeout=timeout)
    except Exception as e:
        raise CninfoError(f"公告检索请求失败: {e}") from e

    if not isinstance(resp, dict):
        return []
    raw_list = resp.get("announcements", [])
    if not isinstance(raw_list, list):
        return []

    results: list[Announcement] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        try:
            title = item.get("announcementTitle", "") or ""
            ann_type = item.get("announcementTypeName") or item.get("adjunctType") or ""
            ann_time = item.get("announcementTime", 0)
            dt = _ts_to_date(ann_time)
            if not dt and ann_time:
                raise CninfoError(
                    f"公告时间戳解析失败: {ann_time} (code={code})"
                )
            ann_id = item.get("announcementId", "")
            adjunct_url = item.get("adjunctUrl", "") or ""
            url = build_detail_url(code, ann_id, org_id, ann_time)
            pdf_url = build_pdf_url(adjunct_url)
            results.append(
                Announcement(
                    title=title,
                    type=ann_type,
                    date=dt,
                    url=url,
                    code=code,
                    org_id=org_id,
                    announcement_id=ann_id,
                    announcement_time=ann_time,
                    pdf_url=pdf_url,
                )
            )
        except Exception as e:
            raise CninfoError(
                f"公告数据解析失败: {e} (code={code})"
            ) from e
    return results


class CninfoClient:
    """巨潮资讯网公告检索客户端。

    所有方法零外部依赖（仅 stdlib urllib + html.parser）。
    """

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    def get_announcements(
        self,
        code: str,
        *,
        count: int = 30,
        page: int = 1,
        searchkey: str = "",
        category: str = "",
        plate: str = "",
        se_date: str = "",
        column: str = "",
    ) -> list[dict]:
        """检索指定股票的公告列表。

        Args:
            code: 6 位股票代码，如 ``688017``。
            count: 每页数量。
            page: 页码（1 起始）。
            searchkey: 关键词搜索。
            category: 公告类别过滤。
            plate: 板块过滤（szse/sse/bj）。
            se_date: 日期范围 ``YYYY-MM-DD~YYYY-MM-DD``。
            column: 栏目过滤。

        Returns:
            ``list[dict]``，每项含 title/type/date/url/code/org_id/announcement_id/announcement_time/pdf_url/body。
        """
        rows = _query_announcements(
            code,
            count=count,
            page=page,
            searchkey=searchkey,
            category=category,
            plate=plate,
            se_date=se_date,
            column=column,
            timeout=self.timeout,
        )
        return [a.__dict__ for a in rows]

    def get_announcements_batch(
        self,
        codes: list[str],
        *,
        count: int = 10,
        page: int = 1,
        searchkey: str = "",
        category: str = "",
        plate: str = "",
        se_date: str = "",
        column: str = "",
    ) -> list[dict]:
        """批量查询多只股票公告。

        Returns:
            各股票公告合并列表，含 ``code`` 字段标识来源。
        """
        all_rows: list[Announcement] = []
        for code in codes:
            rows = _query_announcements(
                code,
                count=count,
                page=page,
                searchkey=searchkey,
                category=category,
                plate=plate,
                se_date=se_date,
                column=column,
                timeout=self.timeout,
            )
            all_rows.extend(rows)
        return [a.__dict__ for a in all_rows]

    def get_announcement_detail(self, announcement: Announcement) -> Announcement:
        """获取单条公告正文（HTML 详情页提取纯文本）。

        Returns:
            带 ``body`` 字段的新 ``Announcement`` 对象。
        """
        if announcement.body:
            return announcement
        try:
            html = _http_get_text(announcement.url, timeout=self.timeout)
            body = _extract_html_text(html)
        except Exception as e:
            raise CninfoError(f"公告正文获取失败: {e}") from e
        return Announcement(
            title=announcement.title,
            type=announcement.type,
            date=announcement.date,
            url=announcement.url,
            code=announcement.code,
            org_id=announcement.org_id,
            announcement_id=announcement.announcement_id,
            announcement_time=announcement.announcement_time,
            pdf_url=announcement.pdf_url,
            body=body,
        )

    def download_pdf(
        self,
        announcement: Announcement,
        dest_dir: str | os.PathLike = ".",
        filename: str | None = None,
    ) -> str:
        """下载公告 PDF 附件到本地。"""
        pdf_url = announcement.pdf_url
        if not pdf_url:
            raise CninfoError("该公告无 PDF 附件")
        if filename is None:
            filename = f"{announcement.date}_{announcement.announcement_id}.PDF"
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / filename
        try:
            req = urlrequest.Request(pdf_url, headers={"User-Agent": _UA})
            with urlrequest.urlopen(req, timeout=self.timeout) as resp:
                path.write_bytes(resp.read())
        except Exception as e:
            raise CninfoError(f"PDF 下载失败: {e}") from e
        return str(path.resolve())