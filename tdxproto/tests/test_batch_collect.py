"""batch_collect 采集管线与 batch.py 新命令测试."""

import json
from unittest.mock import MagicMock, patch

from tdxproto.batch_collect import (
    ItemResult,
    _code6,
    _code_market,
    _safe_stem,
    _split_market_code,
    _us_code,
    collect_ccpm,
    collect_cninfo,
    collect_futures_kline,
    collect_info_snapshot,
    collect_mac_boards,
    collect_mac_flow,
    collect_parallel,
    collect_stock_minute,
    collect_stock_trade,
    collect_us_kline,
    collect_us_minute,
    collect_us_quote,
    collect_us_trade,
    dump_results,
    results_payload,
)
from tdxproto.models import Kline, Minute, Quote, Trade


class TestHelpers:
    def test_code_market_and_code6(self):
        assert _code_market("sz000001") == 0
        assert _code_market("sh600000") == 1
        assert _code_market("bj430047") == 2
        assert _code_market("000001") == 0
        assert _code6("sz000001") == "000001"
        assert _code6("600000") == "600000"

    def test_safe_stem_strips_path(self):
        assert _safe_stem("../etc/passwd") == "..etcpasswd"
        assert _safe_stem("IFL0") == "IFL0"
        assert _safe_stem("") == "item"

    def test_us_code_and_split(self):
        assert _us_code("AAPL") == "AAPL"
        assert _us_code("usAAPL") == "AAPL"
        assert _us_code("USB") == "USB"
        assert _split_market_code("AAPL", 74) == (74, "AAPL")
        assert _split_market_code("74:usMSFT", 74) == (74, "MSFT")


class TestCollectParallel:
    def test_empty(self):
        assert collect_parallel([], lambda x: x) == []

    def test_success_and_error(self):
        def worker(key):
            if key == "bad":
                raise ValueError("boom")
            return {"ok": key}

        results = collect_parallel(["a", "bad", "c"], worker, max_workers=2, timeout=5)
        assert [r.key for r in results] == ["a", "bad", "c"]
        assert results[0].data == {"ok": "a"}
        assert results[1].error == "boom"
        assert results[2].data == {"ok": "c"}


class TestPayloadAndDump:
    def test_nested_and_flatten(self):
        results = [
            ItemResult(key="sz000001", data=[{"time": "0930", "price": 10.0}]),
            ItemResult(key="sh600000", error="timeout"),
        ]
        nested = results_payload(results, flatten=False)
        assert nested[0]["code"] == "sz000001"
        assert nested[0]["data"][0]["price"] == 10.0
        assert nested[1]["error"] == "timeout"

        flat = results_payload(results, flatten=True)
        assert flat[0]["code"] == "sz000001"
        assert flat[0]["price"] == 10.0
        assert flat[1]["error"] == "timeout"

    def test_dump_json_csv_and_per_file(self, tmp_path):
        results = [
            ItemResult(key="sz000001", data=[Minute(time="0930", price=10.1, volume=1)]),
            ItemResult(key="bad", error="timeout"),
        ]
        info = dump_results(results, str(tmp_path), "minute_results", fmt="json", flatten=True, per_file=True)
        assert (tmp_path / "minute_results.json").exists()
        assert (tmp_path / "sz000001.json").exists()
        assert info["saved"] == 1
        assert info["skipped"] == 1
        data = json.loads((tmp_path / "minute_results.json").read_text(encoding="utf-8"))
        assert data[0]["code"] == "sz000001"

        csv_info = dump_results(results[:1], str(tmp_path), "minute_csv", fmt="csv", flatten=True)
        assert csv_info["path"].endswith("minute_csv.csv")
        text = (tmp_path / "minute_csv.csv").read_text(encoding="utf-8")
        assert "sz000001" in text


class TestCollectors:
    def test_futures_kline(self):
        bar = Kline(time="20260101", open=1, high=2, low=1, close=1.5, volume=10)
        client = MagicMock()
        client.kline.return_value = [bar]
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        with patch("tdxproto.futures.FuturesClient", return_value=client):
            results = collect_futures_kline(["IFL0", "47:IHL0"], market=47, max_workers=2, timeout=1)
        assert results[0].key == "IFL0"
        assert results[0].data[0].close == 1.5
        assert client.kline.call_count == 2

    def test_us_quote_kline_minute_trade(self):
        client = MagicMock()
        client.quote.return_value = Quote(code="AAPL", price=180.0, pre_close=179.0, volume=100)
        client.kline.return_value = [Kline(time="20260101", open=1, high=2, low=1, close=1.5, volume=10)]
        client.today_minute.return_value = [Minute(time="0930", price=180.0)]
        client.history_minute.return_value = [Minute(time="0940", price=181.0)]
        client.today_trade.return_value = [Trade(time="0930", price=180.0, volume=10)]
        client.history_trade.return_value = [Trade(time="0940", price=181.0, volume=5)]
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        with patch("tdxproto.futures.FuturesClient", return_value=client):
            quotes = collect_us_quote(["usAAPL", "74:MSFT"], market=74, max_workers=2, timeout=1)
            bars = collect_us_kline(["AAPL"], market=74, max_workers=1, timeout=1)
            m1 = collect_us_minute(["AAPL"], date=None, max_workers=1, timeout=1)
            m2 = collect_us_minute(["AAPL"], date="20260620", max_workers=1, timeout=1)
            t1 = collect_us_trade(["AAPL"], date=None, max_workers=1, timeout=1)
            t2 = collect_us_trade(["AAPL"], date="20260620", count=20, max_workers=1, timeout=1)
        assert quotes[0].data.code == "AAPL"
        assert quotes[0].data.pre_close == 179.0
        client.quote.assert_any_call(74, "AAPL")
        client.quote.assert_any_call(74, "MSFT")
        assert bars[0].data[0].close == 1.5
        assert m1[0].data[0].time == "0930"
        assert m2[0].data[0].time == "0940"
        assert t1[0].data[0].volume == 10
        client.history_trade.assert_called()

    def test_stock_minute_and_trade(self):
        client = MagicMock()
        client.recent_minute.return_value = [Minute(time="0930", price=10.0)]
        client.history_minute.return_value = [Minute(time="0940", price=10.1)]
        client.today_trade.return_value = [Trade(time="0930", price=10.0, volume=100)]
        client.history_trade.return_value = [Trade(time="0940", price=10.1, volume=50)]
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        with patch("tdxproto.stock.StockClient", return_value=client):
            m1 = collect_stock_minute(["sz000001"], date=None, max_workers=1, timeout=1)
            m2 = collect_stock_minute(["sz000001"], date="20260620", max_workers=1, timeout=1)
            t1 = collect_stock_trade(["sz000001"], date=None, max_workers=1, timeout=1)
            t2 = collect_stock_trade(["sz000001"], date="20260620", count=20, max_workers=1, timeout=1)
        assert m1[0].data[0].time == "0930"
        assert m2[0].data[0].time == "0940"
        assert t1[0].data[0].volume == 100
        client.history_trade.assert_called()

    def test_info_snapshot(self):
        col = MagicMock()
        col.snapshot.return_value = {"code": "000001", "news": []}
        with patch("tdxproto.info.InfoCollector", return_value=col):
            results = collect_info_snapshot(["sz000001"], max_workers=1, timeout=1)
        assert results[0].data["code"] == "000001"
        col.snapshot.assert_called_once_with(0, "000001")

    def test_cninfo(self):
        client = MagicMock()
        client.get_announcements.return_value = [{"title": "年报", "code": "000001"}]
        with patch("tdxproto.cninfo.CninfoClient", return_value=client):
            results = collect_cninfo(["sz000001"], count=5, max_workers=1, timeout=1)
        assert results[0].data[0]["title"] == "年报"
        client.get_announcements.assert_called_once()

    def test_ccpm_all_and_latest(self):
        client = MagicMock()
        client.latest_rank.return_value = {"product": "IF", "date": "2026-01-01"}
        client.get_rank.return_value = {"product": "IF", "date": "2026-01-02"}
        with patch("tdxproto.ccpm.CcpmClient", return_value=client):
            latest = collect_ccpm(["IF"], latest=True, max_workers=1, timeout=1)
            dated = collect_ccpm(["IF"], date="2026-01-02", latest=False, max_workers=1, timeout=1)
        assert latest[0].data["date"] == "2026-01-01"
        assert dated[0].data["date"] == "2026-01-02"

    def test_mac_boards_and_flow(self):
        client = MagicMock()
        client.board_list.return_value = [{"code": "881001", "name": "银行"}]
        client.capital_flow.return_value = {"code": "000001", "main_net_amount": 1.2}
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        with patch("tdxproto.mac.client.MacClient", return_value=client):
            boards = collect_mac_boards(board_type=0, page_size=10, timeout=1)
            flow = collect_mac_flow(["sz000001"], max_workers=1, timeout=1)
        assert boards[0].data[0]["name"] == "银行"
        assert flow[0].data["main_net_amount"] == 1.2


class TestBatchCliCommands:
    def test_cmd_minute_empty(self, capsys):
        from batch import cmd_minute

        cmd_minute(MagicMock(codes=""))
        assert "代码列表为空" in capsys.readouterr().out

    def test_cmd_minute_saves(self, tmp_path, capsys):
        from batch import cmd_minute

        args = MagicMock(
            codes="sz000001", date=None, output=str(tmp_path),
            format="json", workers=1, timeout=1, per_file=False,
        )
        with patch("batch.collect_stock_minute") as mock_collect:
            mock_collect.return_value = [
                ItemResult(key="sz000001", data=[Minute(time="0930", price=10.0, volume=1)]),
            ]
            cmd_minute(args)
        assert (tmp_path / "minute_results.json").exists()
        data = json.loads((tmp_path / "minute_results.json").read_text(encoding="utf-8"))
        assert data[0]["code"] == "sz000001"

    def test_cmd_futures_kline(self, tmp_path):
        from batch import cmd_futures_kline

        args = MagicMock(
            codes="IFL0", market=47, period="day", start=0, count=10,
            output=str(tmp_path), format="json", workers=1, timeout=1, per_file=False,
        )
        with patch("batch.collect_futures_kline") as mock_collect:
            mock_collect.return_value = [
                ItemResult(key="IFL0", data=[Kline(time="20260101", close=3800.0)]),
            ]
            cmd_futures_kline(args)
        data = json.loads((tmp_path / "futures_kline_results.json").read_text(encoding="utf-8"))
        assert data[0]["code"] == "IFL0"
        assert data[0]["close"] == 3800.0

    def test_cmd_us_quote_and_kline(self, tmp_path):
        from batch import cmd_us_kline, cmd_us_quote

        quote_args = MagicMock(
            codes="AAPL", market=74, output=str(tmp_path),
            format="json", workers=1, timeout=1, per_file=False,
        )
        with patch("batch.collect_us_quote") as mock_quote:
            mock_quote.return_value = [
                ItemResult(key="AAPL", data=Quote(code="AAPL", price=180.0, pre_close=179.0, volume=100)),
            ]
            cmd_us_quote(quote_args)
        data = json.loads((tmp_path / "us_quote_results.json").read_text(encoding="utf-8"))
        assert data[0]["code"] == "AAPL"
        assert data[0]["pre_close"] == 179.0

        kline_args = MagicMock(
            codes="AAPL", market=74, period="day", start=0, count=10,
            output=str(tmp_path), format="json", workers=1, timeout=1, per_file=False,
        )
        with patch("batch.collect_us_kline") as mock_kline:
            mock_kline.return_value = [
                ItemResult(key="AAPL", data=[Kline(time="20260101", close=180.0)]),
            ]
            cmd_us_kline(kline_args)
        data = json.loads((tmp_path / "us_kline_results.json").read_text(encoding="utf-8"))
        assert data[0]["code"] == "AAPL"
        assert data[0]["close"] == 180.0

    def test_cmd_info_cninfo_ccpm_mac(self, tmp_path):
        from batch import cmd_ccpm, cmd_cninfo, cmd_info_snapshot, cmd_mac_boards, cmd_mac_flow

        snap_args = MagicMock(
            codes="sz000001", output=str(tmp_path), format="json",
            workers=1, timeout=1, per_file=False,
        )
        with patch("batch.collect_info_snapshot") as mock_snap:
            mock_snap.return_value = [ItemResult(key="sz000001", data={"news": []})]
            cmd_info_snapshot(snap_args)
        assert (tmp_path / "info_snapshot_results.json").exists()

        cn_args = MagicMock(
            codes="000001", count=5, page=1, keyword="",
            output=str(tmp_path), format="json", workers=1, timeout=1, per_file=False,
        )
        with patch("batch.collect_cninfo") as mock_cn:
            mock_cn.return_value = [ItemResult(key="000001", data=[{"title": "年报"}])]
            cmd_cninfo(cn_args)
        data = json.loads((tmp_path / "cninfo_results.json").read_text(encoding="utf-8"))
        assert data[0]["title"] == "年报"

        ccpm_args = MagicMock(
            products="IF", date=None, refresh=False,
            output=str(tmp_path), format="json", workers=1, timeout=1, per_file=False,
        )
        with patch("batch.collect_ccpm") as mock_ccpm:
            mock_ccpm.return_value = [ItemResult(key="IF", data={"product": "IF"})]
            cmd_ccpm(ccpm_args)
        assert (tmp_path / "ccpm_results.json").exists()

        board_args = MagicMock(
            type=0, page_size=10, output=str(tmp_path), format="json", timeout=1, per_file=False,
        )
        with patch("batch.collect_mac_boards") as mock_boards:
            mock_boards.return_value = [ItemResult(key="boards-0", data=[{"name": "银行"}])]
            cmd_mac_boards(board_args)
        assert (tmp_path / "mac_boards_results.json").exists()

        flow_args = MagicMock(
            codes="sz000001", output=str(tmp_path), format="json",
            workers=1, timeout=1, per_file=False,
        )
        with patch("batch.collect_mac_flow") as mock_flow:
            mock_flow.return_value = [ItemResult(key="sz000001", data={"main_net_amount": 1})]
            cmd_mac_flow(flow_args)
        assert (tmp_path / "mac_flow_results.json").exists()
