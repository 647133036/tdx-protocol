"""通达信 F10 资讯客户端（7615 HTTP 网关）。

独立数据源，不依赖 TDX 行情服务器。

用法::

    from tdxproto.info import InfoClient

    client = InfoClient()
    news = client.news(0, "000001")
    for item in news:
        print(item.title, item.issue_date)
"""

from .client import InfoClient
from .models import (
    TqlexError, TqlexResponse, TqlexResultSet,
    NewsItem, AnnouncementItem, ResearchReport,
)

__all__ = [
    "InfoClient",
    "TqlexError", "TqlexResponse", "TqlexResultSet",
    "NewsItem", "AnnouncementItem", "ResearchReport",
]