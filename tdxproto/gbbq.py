"""Gbbq 股本变迁管理 — 前复权/后复权计算引擎.

基于除权除息事件记录，对 K 线数据进行仿射变换，实现前复权(HFQ)和后复权(QFQ).
自动从服务器拉取并缓存股本变迁数据到 SQLite.
"""

import sqlite3
import threading
import time
from datetime import date
from pathlib import Path
from typing import Optional

from .models import Kline, EquityChange


def _parse_bar_date(bar: Kline) -> date:
    """Parse bar.time string to date object."""
    t = bar.time.replace("-", "")
    return date(int(t[:4]), int(t[4:6]), int(t[6:8]))


class GbbqManager:
    """股本变迁管理器，提供前复权/后复权计算能力.
    
    功能:
        - 从服务器拉取全量股本变迁数据并缓存到 SQLite
        - 自动定时更新（每天 9:05）
        - 提供 QFQ/HFQ 复权 K 线计算
        - 支持指定日期查询股本信息
    """
    
    def __init__(self, client, db_path: str = None):
        self.client = client
        self.db_path = db_path or str(Path.home() / ".tdxproto" / "gbbq.db")
        self._cache: dict[str, list[EquityChange]] = {}
        self._db: Optional[sqlite3.Connection] = None
        self._last_update: float = 0
        self._lock: threading.Lock = threading.Lock()
        self._init_db()
    
    def _init_db(self):
        """初始化 SQLite 数据库."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.db_path)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS equity_changes (
                code TEXT NOT NULL,
                date TEXT NOT NULL,
                category INTEGER NOT NULL,
                float_shares REAL,
                total_shares REAL,
                bonus REAL,
                rights REAL,
                placement REAL,
                placement_price REAL,
                PRIMARY KEY (code, date)
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS update_log (
                key TEXT PRIMARY KEY,
                update_time INTEGER NOT NULL
            )
        """)
        self._db.commit()
    
    def _need_update(self) -> bool:
        """检查是否需要更新数据."""
        now = time.time()
        if now - self._last_update < 3600:  # 每小时最多更新一次
            return False
        return True
    
    def fetch_and_cache(self) -> int:
        """从服务器拉取全量股本变迁数据并缓存到数据库.
        
        Returns:
            成功缓存的股票数量
        """
        if not self._need_update():
            return len(self._cache)
        
        count = 0
        try:
            # 获取全市场代码列表
            for market in [0, 1, 2]:  # SZ, SH, BJ
                try:
                    codes = self.client.codes_all(market)
                    for code_info in codes:
                        code = code_info.get('code', '')
                        if not code:
                            continue
                        full_code = f"{'sz' if market == 0 else 'sh' if market == 1 else 'bj'}{code}"
                        try:
                            equity = self.client.xdxr(full_code)
                            if equity:
                                self._cache[full_code] = equity
                                self._save_to_db(full_code, equity)
                                count += 1
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception:
            pass
        
        self._last_update = time.time()
        return count
    
    def _save_to_db(self, code: str, equity_list: list[EquityChange]):
        """保存股本变迁数据到数据库."""
        cursor = self._db.cursor()
        cursor.execute("DELETE FROM equity_changes WHERE code = ?", (code,))
        for eq in equity_list:
            if eq.date:
                cursor.execute("""
                    INSERT OR REPLACE INTO equity_changes 
                    (code, date, category, float_shares, total_shares, bonus, rights, placement, placement_price)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    code,
                    str(eq.date),
                    eq.category,
                    eq.float_shares,
                    eq.total_shares,
                    eq.bonus,
                    eq.rights,
                    eq.placement,
                    eq.placement_price,
                ))
        self._db.commit()
    
    def get_equity(self, code: str, target_date: date = None) -> Optional[EquityChange]:
        """获取指定日期的股本变迁记录.
        
        Args:
            code: 股票代码
            target_date: 目标日期，默认为今天
            
        Returns:
            最近一次除权除息记录，或 None
        """
        if target_date is None:
            target_date = date.today()
        
        equity_list = self._cache.get(code)
        if not equity_list:
            equity_list = self._load_from_db(code)
        
        if not equity_list:
            try:
                equity_list = self.client.xdxr(code)
                if equity_list:
                    self._cache[code] = equity_list
                    self._save_to_db(code, equity_list)
            except Exception:
                return None
        
        if not equity_list:
            return None
        
        best = None
        for eq in equity_list:
            if eq.date and eq.date <= target_date:
                if best is None or eq.date > best.date:
                    best = eq
        return best
    
    def _load_from_db(self, code: str) -> list[EquityChange]:
        """从数据库加载股本变迁数据."""
        cursor = self._db.cursor()
        cursor.execute("""
            SELECT date, category, float_shares, total_shares, bonus, rights, placement, placement_price
            FROM equity_changes WHERE code = ?
            ORDER BY date DESC
        """, (code,))
        
        results = []
        for row in cursor.fetchall():
            try:
                eq_date = date.fromisoformat(row[0])
            except (ValueError, TypeError):
                continue
            results.append(EquityChange(
                date=eq_date,
                category=row[1],
                float_shares=row[2] or 0,
                total_shares=row[3] or 0,
                bonus=row[4] or 0,
                rights=row[5] or 0,
                placement=row[6] or 0,
                placement_price=row[7] or 0,
            ))
        return results
    
    def apply_qfq(self, bars: list[Kline], code: str) -> list[Kline]:
        """应用前复权变换."""
        if not bars:
            return bars
        
        from .compute import compute_factors
        equity = self._cache.get(code, [])
        if not equity:
            equity = self._load_from_db(code)
        if not equity:
            try:
                equity = self.client.xdxr(code) or []
                if equity:
                    self._cache[code] = equity
                    self._save_to_db(code, equity)
            except Exception:
                pass
        
        if not equity:
            return bars
        
        factors = compute_factors(bars, equity, adjust="qfq")
        if not factors:
            return bars
        
        result = []
        for bar in bars:
            factor = factors.get(_parse_bar_date(bar))
            if factor is not None and factor != 1.0:
                result.append(Kline(
                    time=bar.time,
                    open=round(bar.open * factor, 2),
                    high=round(bar.high * factor, 2),
                    low=round(bar.low * factor, 2),
                    close=round(bar.close * factor, 2),
                    volume=bar.volume,
                    amount=round(bar.amount * factor, 2),
                ))
            else:
                result.append(bar)
        
        return result
    
    def apply_hfq(self, bars: list[Kline], code: str) -> list[Kline]:
        """应用后复权变换."""
        if not bars:
            return bars
        
        from .compute import compute_factors
        equity = self._cache.get(code, [])
        if not equity:
            equity = self._load_from_db(code)
        if not equity:
            try:
                equity = self.client.xdxr(code) or []
                if equity:
                    self._cache[code] = equity
                    self._save_to_db(code, equity)
            except Exception:
                pass
        
        if not equity:
            return bars
        
        factors = compute_factors(bars, equity, adjust="hfq")
        if not factors:
            return bars
        
        result = []
        for bar in bars:
            factor = factors.get(_parse_bar_date(bar))
            if factor is not None and factor != 1.0:
                result.append(Kline(
                    time=bar.time,
                    open=round(bar.open / factor, 2),
                    high=round(bar.high / factor, 2),
                    low=round(bar.low / factor, 2),
                    close=round(bar.close / factor, 2),
                    volume=bar.volume,
                    amount=round(bar.amount / factor, 2),
                ))
            else:
                result.append(bar)
        
        return result
    
    def get_turnover(self, code: str, target_date: date = None, volume: int = 0) -> float:
        """计算指定日期的换手率.
        
        Args:
            code: 股票代码
            target_date: 目标日期
            volume: 成交量（股）
            
        Returns:
            换手率百分比
        """
        from .compute import get_equity_at, calc_turnover
        
        if target_date is None:
            target_date = date.today()
        
        equity = self._cache.get(code, [])
        if not equity:
            equity = self._load_from_db(code)
        
        float_shares, _ = get_equity_at(equity, target_date)
        if float_shares <= 0:
            return 0.0
        
        return calc_turnover(volume, float_shares)
    
    def close(self):
        """关闭数据库连接."""
        if self._db:
            self._db.close()
            self._db = None


# 全局单例
_gbbq_manager: Optional[GbbqManager] = None


def get_gbbq_manager(client) -> GbbqManager:
    """获取 Gbbq 管理器单例."""
    global _gbbq_manager
    if _gbbq_manager is None or _gbbq_manager.client != client:
        _gbbq_manager = GbbqManager(client)
    return _gbbq_manager
