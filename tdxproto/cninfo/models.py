"""巨潮资讯网（cninfo）数据模型。"""

from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import TdxError

_PDF_BASE = "http://static.cninfo.com.cn/"


@dataclass(frozen=True)
class Announcement:
    """单条公告记录。

    Attributes:
        title: 公告标题。
        type: 公告类型。
        date: 公告日期 ``YYYY-MM-DD``。
        url: 公告详情页 URL。
        code: 6 位股票代码。
        org_id: 巨潮 orgId。
        announcement_id: 巨潮公告 ID。
        announcement_time: 原始 Unix 毫秒时间戳。
        pdf_url: PDF 附件直链。
        body: 公告正文文本（HTML 提取纯文本）。
    """

    title: str
    type: str
    date: str
    url: str
    code: str
    org_id: str
    announcement_id: str
    announcement_time: int
    pdf_url: str
    body: str = ""


def build_detail_url(code: str, announcement_id: str, org_id: str, announcement_time: int) -> str:
    """构造公告详情页 URL。"""
    return (
        "https://www.cninfo.com.cn/new/disclosure/detail?"
        f"stockCode={code}&announcementId={announcement_id}"
        f"&orgId={org_id}&announcementTime={announcement_time}"
    )


def build_pdf_url(adjunct_url: str) -> str:
    """adjunctUrl 拼成 PDF 直链。"""
    if not adjunct_url:
        return ""
    return f"{_PDF_BASE}{adjunct_url}"


class CninfoError(TdxError):
    """巨潮数据请求或解析失败。"""