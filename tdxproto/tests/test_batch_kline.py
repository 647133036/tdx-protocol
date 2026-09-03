"""batch_kline 模块单元测试."""
import pytest
from unittest.mock import patch, MagicMock

from tdxproto.stock.batch_kline import (
    collect_single_kline,
    collect_batch_kline,
    BatchResult,
    save_kline_to_file,
    benchmark_collect,
)
from tdxproto.models import Kline


def _make_kline(time_str: str, open_price: float = 10.0) -> Kline:
    return Kline(
        time=time_str, open=open_price, high=open_price + 0.5,
        low=open_price - 0.5, close=open_price + 0.1,
        volume=100000, amount=1000000.0, position=0, settlement=0.0,
    )


class TestCollectSingleKline:
    """collect_single_kline 单股采集."""

    def test_success(self):
        """正常返回 K 线数据."""
        mock_client = MagicMock()
        mock_client.kline_all.return_value = [_make_kline("20260901")]
        result = collect_single_kline("sz000001", "day", mock_client, max_retries=2)
        assert result.code == "sz000001"
        assert len(result.bars) == 1
        assert result.error is None

    def test_empty_data(self):
        """空数据返回空 bars，无错误."""
        mock_client = MagicMock()
        mock_client.kline_all.return_value = []
        result = collect_single_kline("sh999999", "day", mock_client)
        assert result.bars == []
        assert result.error is None

    def test_retry_on_failure(self):
        """失败时重试."""
        mock_client = MagicMock()
        mock_client.kline_all.side_effect = [
            ConnectionError("timeout"),
            [_make_kline("20260901")],
        ]
        result = collect_single_kline("sz000001", "day", mock_client, max_retries=2)
        assert len(result.bars) == 1
        assert result.error is None
        assert mock_client.kline_all.call_count == 2

    def test_max_retries_exceeded(self):
        """重试耗尽后返回错误."""
        mock_client = MagicMock()
        mock_client.kline_all.side_effect = ConnectionError("timeout")
        result = collect_single_kline("sz000001", "day", mock_client, max_retries=1)
        assert result.error is not None
        assert len(result.bars) == 0


class TestCollectBatchKline:
    """collect_batch_kline 批量采集."""

    def test_empty_codes(self):
        """空代码列表直接返回."""
        results = collect_batch_kline([], period="day")
        assert results == []

    def test_single_code(self):
        """单只股票正常采集."""
        with patch('tdxproto.stock.batch_kline.StockClient') as MockClient:
            mock_instance = MagicMock()
            mock_instance.kline_all.return_value = [_make_kline("20260901")]
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_instance._current_host = "1.2.3.4:7709"
            MockClient.return_value = mock_instance

            results = collect_batch_kline(
                ["sz000001"], max_workers=1, reuse_client=False,
                timeout_per_stock=5.0, failover=True,
            )
            assert len(results) == 1
            assert results[0].code == "sz000001"
            assert len(results[0].bars) == 1
            args, kwargs = mock_instance.kline_all.call_args
            assert kwargs.get("failover") is True or (len(args) >= 3 and args[2] is True)

    def test_o_not_n_squared(self):
        """验证不使用 codes.index() (O(n^2) bug 已修复)."""
        import inspect
        source = inspect.getsource(collect_batch_kline)
        assert "codes.index" not in source, "仍存在 O(n^2) 的 codes.index() 调用"


class TestSaveKlineToFile:
    """save_kline_to_file 文件保存."""

    def test_save_json_files(self, tmp_path):
        """保存为单独 JSON 文件."""
        results = [
            BatchResult(code="sz000001", bars=[_make_kline("20260901")], error=None),
            BatchResult(code="sh600000", bars=[], error=None),
            BatchResult(code="sh999999", bars=[], error="timeout"),
        ]
        output_dir = str(tmp_path / "kline_data")
        stats = save_kline_to_file(results, output_dir)
        assert stats["saved"] == 1
        assert stats["skipped"] == 2

        # 验证保存的文件
        json_file = tmp_path / "kline_data" / "sz000001.json"
        assert json_file.exists()

    def test_rejects_path_traversal_code(self, tmp_path):
        results = [
            BatchResult(code="../etc/passwd", bars=[_make_kline("20260901")], error=None),
        ]
        output_dir = str(tmp_path / "kline_data")
        stats = save_kline_to_file(results, output_dir)
        assert stats["saved"] == 1
        assert not (tmp_path / "etc" / "passwd.json").exists()
        assert (tmp_path / "kline_data" / "etcpasswd.json").exists()

    def test_save_empty_results(self, tmp_path):
        """空结果列表."""
        stats = save_kline_to_file([], str(tmp_path / "out"))
        assert stats["total"] == 0
        assert stats["saved"] == 0


class TestBenchmarkCollect:
    """benchmark_collect 基准测试."""

    def test_returns_stats(self):
        """返回性能统计字典."""
        with patch('tdxproto.stock.batch_kline.collect_batch_kline') as mock_collect:
            mock_collect.return_value = [
                BatchResult(code="sz000001", bars=[_make_kline("20260901")], error=None),
            ]
            stats = benchmark_collect(["sz000001"], max_workers=1)
            assert "elapsed_sec" in stats
            assert stats["stocks_total"] == 1
            assert stats["stocks_success"] == 1
