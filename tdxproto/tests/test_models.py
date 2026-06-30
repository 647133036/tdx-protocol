import pytest

from tdxproto.models import Quote, Kline, Minute, Trade, EquityChange, FinanceInfo, PriceLimit


class TestQuoteModel:
    def test_minimal(self):
        q = Quote(code="sz000001")
        assert q.code == "sz000001"
        assert q.market == ""
        assert q.name == ""
        assert q.price == 0.0
        assert q.bid_p == [0.0] * 5
        assert q.bid_v == [0] * 5
        assert q.ask_p == [0.0] * 5
        assert q.ask_v == [0] * 5
        assert q.open_interest == 0
        assert q.raw == b""

    def test_full(self):
        q = Quote(
            code="sh600000",
            market="sh",
            name="浦发银行",
            price=10.5,
            pre_close=10.3,
            open=10.4,
            high=10.8,
            low=10.2,
            volume=1000000,
            amount=10500000.0,
            change_pct=1.94,
            bid_p=[10.49, 10.48, 10.47, 10.46, 10.45],
            bid_v=[100, 200, 300, 400, 500],
            ask_p=[10.50, 10.51, 10.52, 10.53, 10.54],
            ask_v=[150, 250, 350, 450, 550],
            inner_vol=500000,
            outer_vol=500000,
        )
        assert q.code == "sh600000"
        assert len(q.bid_p) == 5
        assert len(q.ask_v) == 5

    def test_futures_fields(self):
        q = Quote(code="IF2506", market="futures")
        q.open_interest = 123456
        assert q.open_interest == 123456


class TestKlineModel:
    def test_minimal(self):
        k = Kline(time="20250101")
        assert k.time == "20250101"
        assert k.open == 0.0
        assert k.high == 0.0
        assert k.low == 0.0
        assert k.close == 0.0
        assert k.volume == 0
        assert k.amount == 0.0

    def test_full(self):
        k = Kline(
            time="20250101",
            open=10.0, high=11.0, low=9.5, close=10.5,
            volume=100000, amount=1050000.0,
            position=50000, settlement=10.3,
        )
        assert k.position == 50000
        assert k.settlement == 10.3


class TestMinuteModel:
    def test_minimal(self):
        m = Minute(time="09:31")
        assert m.time == "09:31"
        assert m.price == 0.0
        assert m.volume == 0
        assert m.avg_price == 0.0
        assert m.open_interest == 0

    def test_full(self):
        m = Minute(time="10:00", price=10.5, volume=5000, avg_price=10.4, open_interest=12345)
        assert m.price == 10.5
        assert m.open_interest == 12345


class TestTradeModel:
    def test_minimal(self):
        t = Trade(time="09:30")
        assert t.time == "09:30"
        assert t.price == 0.0
        assert t.direction == ""
        assert t.nature == ""

    def test_full_stock(self):
        t = Trade(time="10:00", price=10.5, volume=100, direction="B", order_count=5)
        assert t.direction == "B"
        assert t.order_count == 5

    def test_full_futures(self):
        t = Trade(
            time="10:00", price=3500.0, volume=10,
            direction="买入", nature="多开", zeng_cang=10,
        )
        assert t.nature == "多开"
        assert t.zeng_cang == 10


class TestEquityChangeModel:
    def test_minimal(self):
        e = EquityChange()
        assert e.date is None
        assert e.category == ""

    def test_full_dividend(self):
        from datetime import date as dt_date
        e = EquityChange(
            date=dt_date(2025, 6, 15),
            category="除权除息",
            bonus=0.5,
            rights=0.3,
            placement=0.1,
            placement_price=8.0,
        )
        assert e.bonus == 0.5
        assert e.rights == 0.3

    def test_full_share_change(self):
        from datetime import date as dt_date
        e = EquityChange(
            date=dt_date(2025, 1, 1),
            category="股本变化",
            float_shares=1000000.0,
            total_shares=5000000.0,
        )
        assert e.float_shares == 1000000.0
        assert e.total_shares == 5000000.0


class TestFinanceInfoModel:
    def test_minimal(self):
        f = FinanceInfo()
        assert f.code == ""
        assert f.eps == 0.0

    def test_full(self):
        from datetime import date as dt_date
        f = FinanceInfo(
            code="sz000001",
            exchange="sz",
            float_shares=1000000.0,
            total_shares=5000000.0,
            eps=2.5,
            bvps=8.0,
            revenue=10000000.0,
            profit=2500000.0,
            net_profit=2000000.0,
            total_assets=50000000.0,
            net_assets=25000000.0,
            ipo_date=dt_date(2000, 1, 1),
            updated=dt_date(2025, 1, 1),
        )
        assert f.eps == 2.5
        assert f.bvps == 8.0


class TestPriceLimitModel:
    def test_minimal(self):
        p = PriceLimit()
        assert p.code == ""
        assert p.upper == 0.0

    def test_full(self):
        p = PriceLimit(code="sz000001", exchange="sz", upper=11.0, lower=9.5)
        assert p.upper == 11.0
        assert p.lower == 9.5
