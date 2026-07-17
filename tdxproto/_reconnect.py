"""连接重连与空数据故障转移策略。

移植自 easy_tdx 的 ``_reconnect.py`` / ``client.py`` 模式。

核心概念：
  1. 同主机退避重连：连接丢失时按指数退避序列重试当前主机。
  2. 跨主机故障转移：同主机耗尽后，重新测速选另一台服务器。
  3. 空数据故障转移：连接成功但数据为空，按延迟顺序逐台实测。

所有函数均为纯函数，不依赖 client 状态，便于测试。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .exceptions import TdxError

# 连接断开时的指数退避序列（秒）
RETRY_DELAYS: tuple[float, ...] = (0.1, 0.5, 1.0, 2.0)

# 同一进程内两次全量测速的最小间隔（秒）
_FAILOVER_PING_THROTTLE_SEC: float = 30.0
_last_failover_ts: float = 0.0

# 空数据故障转移最多尝试多少台候选主机
WORKING_HOST_MAX_ATTEMPTS = 15


def _throttled() -> bool:
    global _last_failover_ts
    return (time.monotonic() - _last_failover_ts) < _FAILOVER_PING_THROTTLE_SEC


def _mark_failover_done() -> None:
    global _last_failover_ts
    _last_failover_ts = time.monotonic()


# 测速函数签名
PingFn = Callable[..., list[tuple[str, float]]]
# 持久化函数签名
SaveFn = Callable[[str], None]


def select_best_host(
    hosts: list[str],
    ping_fn: PingFn,
    save_fn: SaveFn,
    port: int,
    ping_timeout: float,
    current_host: str,
) -> str | None:
    """重新测速并选出与当前 host 不同的最优主机。

    节流：``_FAILOVER_PING_THROTTLE_SEC`` 秒内不重复测速。
    返回 None 表示无更优选择或处于节流窗口。
    """
    if _throttled():
        logging.getLogger(__name__).debug(
            "跨主机故障转移：处于 %ss 节流窗口内，跳过本次测速",
            _FAILOVER_PING_THROTTLE_SEC,
        )
        return None
    try:
        ranked = ping_fn(hosts, port, ping_timeout)
    finally:
        _mark_failover_done()
    for host, _latency in ranked:
        if host != current_host:
            save_fn(host)
            logging.getLogger(__name__).info(
                "跨主机故障转移：从 %s 切换到 %s", current_host, host
            )
            return host
    return None


# 验证函数签名：(host) -> True 表示该主机可用
TryFn = Callable[[str], bool]
AsyncTryFn = Callable[[str], Awaitable[bool]]


def find_working_host(
    ranked_hosts: list[tuple[str, float]],
    try_fn: TryFn,
    save_fn: SaveFn,
    current_host: str,
    max_attempts: int = WORKING_HOST_MAX_ATTEMPTS,
) -> str | None:
    """按延迟顺序逐台测试候选主机，返回第一台"可用"的。

    用于"连接成功但数据空"的场景。每台候选连接查询后会立即关闭，
    不污染 client 的当前连接状态。
    """
    log = logging.getLogger(__name__)
    tried = 0
    for host, _latency in ranked_hosts:
        if host == current_host:
            continue
        if tried >= max_attempts:
            break
        tried += 1
        try:
            if try_fn(host):
                save_fn(host)
                log.info(
                    "空数据故障转移：从 %s 切换到 %s（第 %d 台候选可用）",
                    current_host, host, tried,
                )
                return host
        except Exception:
            log.debug("空数据故障转移：%s 验证失败，尝试下一台", host, exc_info=True)
    return None