"""工作日管理 — 判断是否为交易日.

基于指数 sh000001 的日 K 线数据，自动判断当天是否为工作日.
支持定时更新和缓存机制.
"""

import sqlite3
import time
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional


class WorkdayManager:
    """工作日管理器.
    
    功能:
        - 基于 sh000001 日 K 线判断交易日
        - 缓存工作日数据到 SQLite
        - 自动定时更新（每天 9:05）
        - 支持工作日查询和遍历
    """
    
    def __init__(self, client, db_path: str = None):
        self.client = client
        self.db_path = db_path or str(Path.home() / ".tdxproto" / "workday.db")
        self._cache: dict[int, bool] = {}
        self._db: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        self._last_update = 0
        self._init_db()
    
    def _init_db(self):
        """初始化数据库."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.db_path)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS workdays (
                date TEXT PRIMARY KEY,
                unix_time INTEGER NOT NULL
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS update_log (
                key TEXT PRIMARY KEY,
                update_time INTEGER NOT NULL
            )
        """)
        self._db.commit()
        
        # 加载缓存
        self._load_cache()
    
    def _load_cache(self):
        """从数据库加载缓存."""
        cursor = self._db.cursor()
        cursor.execute("SELECT date, unix_time FROM workdays ORDER BY date")
        for row in cursor.fetchall():
            try:
                d = date.fromisoformat(row[0])
                self._cache[int(datetime(d.year, d.month, d.day).timestamp() // 86400 * 86400)] = True
            except (ValueError, TypeError):
                continue
    
    def _need_update(self) -> bool:
        """检查是否需要更新."""
        now = time.time()
        if now - self._last_update < 3600:  # 每小时最多更新一次
            return False
        return True
    
    def fetch_and_cache(self) -> int:
        """从服务器拉取 sh000001 的日 K 线并缓存工作日.
        
        Returns:
            新增的工作日数量
        """
        if not self._need_update():
            return len(self._cache)
        
        try:
            bars = self.client.kline("sh000001", "day", 0, 500)
            if not bars:
                return 0
            
            count = 0
            cursor = self._db.cursor()
            for bar in bars:
                try:
                    raw = bar.time.replace('-', '')[:8]
                    if not (raw.isdigit() and len(raw) == 8):
                        continue
                    y, m, d = int(raw[:4]), int(raw[4:6]), int(raw[6:8])
                    if not (1990 <= y <= 2030 and 1 <= m <= 12 and 1 <= d <= 31):
                        continue
                    unix_day = int(datetime(y, m, d).timestamp() // 86400 * 86400)
                    if unix_day not in self._cache:
                        self._cache[unix_day] = True
                        cursor.execute(
                            "INSERT INTO workdays (date, unix_time) VALUES (?, ?)",
                            (str(d), unix_day)
                        )
                        count += 1
                except (ValueError, TypeError):
                    continue
            
            self._db.commit()
            self._last_update = time.time()
            return count
        except Exception:
            return 0
    
    def is_workday(self, d: date = None) -> bool:
        """判断指定日期是否为工作日.
        
        Args:
            d: 目标日期，默认为今天
            
        Returns:
            True 如果是工作日，False 否则
        """
        if d is None:
            d = date.today()
        
        unix_day = int(datetime(d.year, d.month, d.day).timestamp() // 86400 * 86400)
        
        with self._lock:
            # 先查缓存
            if unix_day in self._cache:
                return self._cache[unix_day]
        
        # 缓存未命中，尝试更新
        self.fetch_and_cache()
        
        with self._lock:
            return self._cache.get(unix_day, False)
    
    def today_is(self) -> bool:
        """今天是否为工作日."""
        return self.is_workday(date.today())
    
    def range_year(self, year: int):
        """遍历指定年份的所有工作日.
        
        Yields:
            date 对象
        """
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        
        current = start
        while current <= end:
            if self.is_workday(current):
                yield current
            current += timedelta(days=1)
    
    def close(self):
        """关闭数据库连接."""
        if self._db:
            self._db.close()
            self._db = None


# 全局单例
_workday_manager: Optional[WorkdayManager] = None


def get_workday_manager(client) -> WorkdayManager:
    """获取 Workday 管理器单例."""
    global _workday_manager
    if _workday_manager is None or _workday_manager.client != client:
        _workday_manager = WorkdayManager(client)
    return _workday_manager
