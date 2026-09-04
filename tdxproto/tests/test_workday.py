"""WorkdayManager 日期写入修复。"""
from datetime import date
from unittest.mock import MagicMock

from tdxproto.models import Kline
from tdxproto.workday import WorkdayManager


class TestWorkdayIsoDate:
    def test_inserts_iso_date(self, tmp_path):
        client = MagicMock()
        client.kline.return_value = [
            Kline(time="20260901", open=1, high=1, low=1, close=1),
            Kline(time="2026-09-02", open=1, high=1, low=1, close=1),
        ]
        db = tmp_path / "workday.db"
        mgr = WorkdayManager(client, db_path=str(db))
        added = mgr.fetch_and_cache()
        assert added == 2
        rows = list(mgr._db.execute("SELECT date FROM workdays ORDER BY date"))
        assert rows[0][0] == "2026-09-01"
        assert rows[1][0] == "2026-09-02"
        mgr.close()
