"""main.py / batch.py CLI 功能测试."""

import json
from unittest.mock import MagicMock, patch

from tdxproto.hk import HkQuote
from tdxproto.models import Quote


class TestJs:
    def test_js_recurses_dict_of_dataclass(self, capsys):
        from main import js

        q = HkQuote(
            code="00700", name="腾讯", price=445.2, pre_close=433.0,
            open=442.4, high=446.6, low=440.0, volume=1, amount=1.0,
            change_pct=2.82, change_amt=12.2, turnover_pct=0.0, time="t",
        )
        js({"hk00700": q, "items": [q]})
        out = json.loads(capsys.readouterr().out)
        assert out["hk00700"]["code"] == "00700"
        assert out["hk00700"]["price"] == 445.2
        assert out["items"][0]["name"] == "腾讯"

    def test_js_bytes_hex(self, capsys):
        from main import js

        js({"raw": b"\x01\xff"})
        out = json.loads(capsys.readouterr().out)
        assert out["raw"] == "01ff"

    def test_js_inner_dict(self):
        from main import js_inner

        nested = js_inner({"q": Quote(code="sz000001", price=10.0)})
        assert nested["q"]["code"] == "sz000001"
        assert nested["q"]["price"] == 10.0


class TestHkCli:
    def test_hk_quote_found(self, capsys):
        from main import hk_quote

        q = HkQuote(
            code="00700", name="腾讯", price=445.2, pre_close=433.0,
            open=442.4, high=446.6, low=440.0, volume=1, amount=1.0,
            change_pct=2.82, change_amt=12.2, turnover_pct=0.0, time="t",
        )
        c = MagicMock()
        c.quote.return_value = q
        hk_quote(c, MagicMock(code="00700"))
        out = json.loads(capsys.readouterr().out)
        assert out["code"] == "00700"
        assert out["price"] == 445.2

    def test_hk_quote_missing(self, capsys):
        from main import hk_quote

        c = MagicMock()
        c.quote.return_value = None
        hk_quote(c, MagicMock(code="99999"))
        out = json.loads(capsys.readouterr().out)
        assert out["error"] == "未找到数据"

    def test_hk_quote_batch_serializes_dataclass(self, capsys):
        from main import hk_quote_batch

        q = HkQuote(
            code="00700", name="腾讯", price=445.2, pre_close=433.0,
            open=442.4, high=446.6, low=440.0, volume=1, amount=1.0,
            change_pct=2.82, change_amt=12.2, turnover_pct=0.0, time="t",
        )
        c = MagicMock()
        c.quote_batch.return_value = {"hk00700": q}
        hk_quote_batch(c, MagicMock(codes="00700"))
        out = json.loads(capsys.readouterr().out)
        assert out["hk00700"]["code"] == "00700"
        assert isinstance(out["hk00700"], dict)


class TestBatchHelpers:
    def test_load_codes_from_string(self):
        from batch import _load_codes

        assert _load_codes("00700, 09988") == ["00700", "09988"]
        assert _load_codes("") == []
        assert _load_codes(None) == []

    def test_load_codes_from_file(self, tmp_path):
        from batch import _load_codes

        p = tmp_path / "codes.txt"
        p.write_text("00700\n09988\n\n", encoding="utf-8")
        assert _load_codes(str(p)) == ["00700", "09988"]

    def test_save_hk_json(self, tmp_path, capsys):
        from batch import _save_hk_json

        q = HkQuote(
            code="00700", name="腾讯", price=445.2, pre_close=433.0,
            open=442.4, high=446.6, low=440.0, volume=1, amount=1.0,
            change_pct=2.82, change_amt=12.2, turnover_pct=0.0, time="t",
        )
        _save_hk_json({"hk00700": q}, str(tmp_path))
        data = json.loads((tmp_path / "hk_results.json").read_text(encoding="utf-8"))
        assert data[0]["code"] == "00700"
        assert "已保存 1 条港股行情" in capsys.readouterr().out

    def test_cmd_hk_quote_empty(self, capsys):
        from batch import cmd_hk_quote

        cmd_hk_quote(MagicMock(codes=""))
        assert "代码列表为空" in capsys.readouterr().out

    def test_cmd_hk_quote_json(self, tmp_path, capsys):
        from batch import cmd_hk_quote

        q = HkQuote(
            code="00700", name="腾讯", price=445.2, pre_close=433.0,
            open=442.4, high=446.6, low=440.0, volume=1, amount=1.0,
            change_pct=2.82, change_amt=12.2, turnover_pct=0.0, time="t",
        )
        args = MagicMock(codes="00700", output=str(tmp_path), format="json")
        with patch("batch.HkClient") as cls:
            cls.return_value.quote_batch.return_value = {"hk00700": q}
            cmd_hk_quote(args)
        assert (tmp_path / "hk_results.json").exists()

    def test_cmd_futures_quote_json(self, tmp_path, capsys):
        from batch import cmd_futures_quote

        q = Quote(code="IFL0", price=3800.0, pre_close=3790.0, volume=100)
        client = MagicMock()
        client.quote_batch.return_value = [q]
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        args = MagicMock(
            market=47, start=0, count=1, timeout=1,
            output=str(tmp_path), format="json",
        )
        with patch("batch.FuturesClient", return_value=client):
            cmd_futures_quote(args)
        data = json.loads((tmp_path / "futures_results.json").read_text(encoding="utf-8"))
        assert data[0]["code"] == "IFL0"
        assert data[0]["pre_close"] == 3790.0
        assert "vol" not in data[0]
