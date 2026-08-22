"""TQLEX / 7615 HTTP 网关响应模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class TqlexError(Exception):
    """TQLEX 网关错误。"""


@dataclass
class TqlexResultSet:
    key: str | None
    columns: list[str]
    rows: list[dict[str, Any]]

    @property
    def count(self) -> int:
        return len(self.rows)


@dataclass
class TqlexResponse:
    entry: str
    error_code: int | None
    result_sets: list[TqlexResultSet]
    raw: dict[str, Any] = field(repr=False)

    @property
    def ok(self) -> bool:
        return self.error_code in (None, 0)

    @property
    def rows(self) -> list[dict[str, Any]]:
        if self.result_sets:
            return self.result_sets[0].rows
        return []


@dataclass
class NewsItem:
    issue_date: str
    title: str
    source: str
    redistime: str
    rec_id: str
    url: str = ""


@dataclass
class AnnouncementItem:
    issue_date: str
    title: str
    typecode: str
    typename: str
    rec_id: str
    pdf_url: str
    source: str
    redistime: str


@dataclass
class ResearchReport:
    title: str
    rating: str
    analyst: str
    date: str
    report_id: int


@dataclass
class CompanyProfile:
    stock_type: str
    list_date: str
    ipo_method: str
    board: str
    issue_price: float
    first_day_return: str
    sponsor: str
    total_shares: int
    circulating_shares: int