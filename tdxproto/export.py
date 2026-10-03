"""数据导出模块 — 支持 DataFrame / Parquet / CSV 格式。

可选依赖：pyarrow (parquet)、pandas (DataFrame)
安装：pip install tdxproto[parquet]
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, is_dataclass
from typing import Any


def _to_dict(obj: Any) -> Any:
    """将 dataclass / list / dict 递归转换为可序列化字典."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return _to_dict(asdict(obj))
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if isinstance(obj, bytes):
        return obj.hex()
    return obj


def to_dict(obj: Any) -> Any:
    """将对象转换为可序列化的字典（公开 API）."""
    return _to_dict(obj)


def to_json(obj: Any, indent: int = 2) -> str:
    """导出为 JSON 字符串."""
    return json.dumps(_to_dict(obj), indent=indent, ensure_ascii=False, default=str)


def to_csv_string(obj: Any) -> str:
    """导出为 CSV 字符串（适用于 list[dict] 或 list[dataclass]）."""
    data = _to_dict(obj)
    if not data:
        return ""
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        return ""
    if not isinstance(data[0], dict):
        raise TypeError("to_csv_string 需要 list[dict] 或 dataclass 序列")
    fieldnames = list(data[0].keys())
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in data:
        if isinstance(row, dict):
            writer.writerow(row)
    return output.getvalue()


def to_dataframe(obj: Any) -> "pd.DataFrame":
    """导出为 pandas.DataFrame（需要 pandas）."""
    try:
        import pandas as pd
    except ImportError as e:
        raise ImportError(
            "to_dataframe 需要 pandas，请安装：pip install pandas"
        ) from e
    data = _to_dict(obj)
    if isinstance(data, list):
        return pd.DataFrame(data)
    if isinstance(data, dict):
        return pd.DataFrame([data])
    return pd.DataFrame([_to_dict(obj)])


def _require_parquet():
    try:
        import pandas  # noqa: F401
        import pyarrow  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "parquet 导出需要 pandas 和 pyarrow，请安装：pip install tdxproto[parquet]"
        ) from e


def to_parquet(obj: Any, filepath: str) -> str:
    """导出为 Parquet 文件（需要 pyarrow + pandas）.

    Returns:
        文件路径
    """
    _require_parquet()
    df = to_dataframe(obj)
    df.to_parquet(filepath, index=False)
    return filepath


def to_parquet_string(obj: Any) -> bytes:
    """导出为 Parquet 字节流（需要 pyarrow + pandas）."""
    _require_parquet()
    df = to_dataframe(obj)
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    return buf.getvalue()
