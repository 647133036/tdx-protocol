"""包导出与 Quote 字段对齐测试."""

import tdxproto
from tdxproto.models import Quote


class TestAll:
    def test_star_import_names_exist(self):
        for name in tdxproto.__all__:
            assert hasattr(tdxproto, name), name

    def test_star_import_does_not_nameerror(self):
        ns = {}
        exec("from tdxproto import *", ns)
        assert "StockClient" in ns
        assert "to_parquet" in ns
        if tdxproto._HAS_MAC:
            assert "MacClient" in ns
        else:
            assert "MacClient" not in ns

    def test_mac_symbols_conditional(self):
        if tdxproto._HAS_MAC:
            assert "MacClient" in tdxproto.__all__
            assert tdxproto.MacClient is not None
        else:
            assert "MacClient" not in tdxproto.__all__


class TestQuoteFields:
    def test_no_legacy_aliases(self):
        q = Quote(code="IFL0", price=10.0, pre_close=9.0, volume=1)
        assert not hasattr(q, "bid1")
        assert not hasattr(q, "vol")
        assert not hasattr(q, "pre_settle")
        assert not hasattr(q, "last_close")
        assert q.pre_close == 9.0
        assert q.volume == 1
        assert len(q.bid_p) == 5
