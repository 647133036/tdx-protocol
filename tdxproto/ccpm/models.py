"""中金所持仓排名数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


class CcpmError(Exception):
    """网络/解析错误。"""


class CcpmNoDataError(CcpmError):
    """该日期无数据（非交易日 / 数据未发布）。"""


@dataclass
class MemberRank:
    """单个会员排名。"""
    rank: int
    member: str
    volume: Optional[int] = field(default=None)
    long_pos: Optional[int] = field(default=None)
    short_pos: Optional[int] = field(default=None)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CcpmProductMeta:
    """品种元数据。"""
    code: str
    name: str
    underlying: str
    contract_size: int
    description: str

    def to_dict(self) -> dict:
        return asdict(self)
