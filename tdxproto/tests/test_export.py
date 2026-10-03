"""export 模块单元测试."""

from dataclasses import dataclass
from unittest.mock import patch

import pytest

from tdxproto.export import (
    to_csv_string,
    to_dict,
    to_dataframe,
    to_json,
    to_parquet,
    to_parquet_string,
)
from tdxproto.models import Quote


@dataclass
class _Item:
    code: str
    price: float
    raw: bytes = b""


class TestToDict:
    def test_dataclass(self):
        q = Quote(code="sz000001", price=10.5, pre_close=10.0)
        d = to_dict(q)
        assert d["code"] == "sz000001"
        assert d["price"] == 10.5
        assert d["pre_close"] == 10.0
        assert isinstance(d["raw"], str)

    def test_nested_dict_of_dataclass(self):
        q = Quote(code="00700", price=445.2)
        d = to_dict({"hk00700": q})
        assert d["hk00700"]["code"] == "00700"
        assert d["hk00700"]["price"] == 445.2

    def test_list(self):
        data = to_dict([_Item("a", 1.0), _Item("b", 2.0)])
        assert data == [
            {"code": "a", "price": 1.0, "raw": ""},
            {"code": "b", "price": 2.0, "raw": ""},
        ]

    def test_bytes_to_hex(self):
        assert to_dict(b"\x01\xff") == "01ff"

    def test_empty(self):
        assert to_dict([]) == []
        assert to_dict({}) == {}


class TestToJson:
    def test_quote_json(self):
        q = Quote(code="sz000001", price=10.5)
        text = to_json(q)
        assert '"code": "sz000001"' in text
        assert '"price": 10.5' in text

    def test_dict_of_quotes(self):
        text = to_json({"hk00700": Quote(code="00700", name="腾讯")})
        assert "00700" in text
        assert "腾讯" in text


class TestToCsv:
    def test_list_of_dataclass(self):
        csv_text = to_csv_string([_Item("a", 1.0), _Item("b", 2.0)])
        lines = [ln for ln in csv_text.strip().splitlines() if ln]
        assert lines[0] == "code,price,raw"
        assert "a,1.0," in lines[1]
        assert "b,2.0," in lines[2]

    def test_single_dict(self):
        csv_text = to_csv_string({"code": "sz000001", "price": 10.5})
        assert "code,price" in csv_text
        assert "sz000001,10.5" in csv_text

    def test_empty(self):
        assert to_csv_string([]) == ""
        assert to_csv_string({}) == ""

    def test_non_dict_rows(self):
        with pytest.raises(TypeError):
            to_csv_string([1, 2, 3])


class TestToDataframe:
    def test_requires_pandas(self):
        with patch.dict("sys.modules", {"pandas": None}):
            with pytest.raises(ImportError, match="pandas"):
                to_dataframe([{"a": 1}])

    def test_list_and_dict(self):
        pytest.importorskip("pandas")
        df = to_dataframe([{"code": "a", "price": 1.0}, {"code": "b", "price": 2.0}])
        assert list(df["code"]) == ["a", "b"]
        df2 = to_dataframe({"code": "a", "price": 1.0})
        assert len(df2) == 1
        assert df2.iloc[0]["code"] == "a"


class TestToParquet:
    def test_requires_deps(self):
        with patch.dict("sys.modules", {"pandas": None, "pyarrow": None}):
            with pytest.raises(ImportError, match="tdxproto\\[parquet\\]"):
                to_parquet([{"a": 1}], "out.parquet")
            with pytest.raises(ImportError, match="tdxproto\\[parquet\\]"):
                to_parquet_string([{"a": 1}])

    def test_write_file_and_bytes(self, tmp_path):
        pytest.importorskip("pandas")
        pytest.importorskip("pyarrow")
        rows = [{"code": "sz000001", "price": 10.5}, {"code": "sh600000", "price": 11.0}]
        path = tmp_path / "q.parquet"
        assert to_parquet(rows, str(path)) == str(path)
        assert path.exists()
        blob = to_parquet_string(rows)
        assert isinstance(blob, bytes)
        assert len(blob) > 0
