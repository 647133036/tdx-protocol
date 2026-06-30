"""Tube — 可插拔协议传输管道。

核心创新: 
  将"传输"与"协议"解耦。Tube 只管 TCP 收发 + 请求/响应配对，
  协议细节 (握手、心跳、数据编解码) 由上层 Pipeline 注入。
  
  支持:
    - 多主站自动 failover
    - 背景 reader 线程 + 零锁消息路由
    - 可配置的心跳间隔
"""

import socket
import threading
import time
from queue import Empty, Queue

from .frame import Frame, read_response, Response


class TubeError(Exception):
    pass


class Tube:
    def __init__(self, hosts: list[str], timeout: float = 8.0,
                 heartbeat_cmd: int = 0, heartbeat_data: bytes = b"",
                 heartbeat_interval: float = 30.0):
        self.hosts = hosts
        self.timeout = timeout
        self._heartbeat_cmd = heartbeat_cmd
        self._heartbeat_data = heartbeat_data
        self._heartbeat_interval = heartbeat_interval
        self._sock: socket.socket | None = None
        self._host: str | None = None
        self._mid = 1
        self._slock = threading.Lock()
        self._pending: dict[int, Queue] = {}
        self._plock = threading.Lock()
        self._stop = threading.Event()
        self._reader: threading.Thread | None = None
        self._heartbeater: threading.Thread | None = None

    @property
    def host(self) -> str | None:
        return self._host

    def open(self, prefix: int, handshake_cmd: int, handshake_data: bytes = b"",
             scalar_hosts: list[str] | None = None,
             scanner_timeout: float = 2.0) -> str:
        """连接并握手。若提供 scalar_hosts 则先并发扫描测速择优。"""
        candidates = self._resolve_hosts(scalar_hosts, prefix, handshake_cmd,
                                          handshake_data, scanner_timeout)
        last_err = None
        for host in candidates:
            try:
                addr, port = host.rsplit(":", 1)
                sock = socket.create_connection((addr, int(port)), self.timeout)
                sock.settimeout(self.timeout)
                self._sock = sock
                self._host = host
                self._stop.clear()
                self._start_reader()
                self._start_heartbeater(prefix)
                self.call(handshake_cmd, handshake_data, prefix)
                return host
            except (OSError, TubeError) as e:
                if self._sock:
                    try: self._sock.close()
                    except Exception: pass
                    self._sock = None
                last_err = e
                continue
        raise TubeError(f"all hosts failed, last: {last_err}")

    def _resolve_hosts(self, scanner_hosts: list[str] | None,
                        prefix: int, cmd: int, data: bytes,
                        timeout: float) -> list[str]:
        if not scanner_hosts:
            return list(self.hosts)
        if prefix == 0x01 and cmd == 0x2454:
            # 7727 期货
            from .scanner import scan_futures
            results = scan_futures(scanner_hosts, workers=64, timeout=timeout)
        else:
            # 7709 股票
            from .scanner import scan_stock
            results = scan_stock(scanner_hosts, workers=64, timeout=timeout)
        alive = [r.host for r in results if r.ok]
        return alive or list(self.hosts)

    def close(self):
        self._stop.set()
        if self._sock:
            try: self._sock.close()
            except Exception: pass
            self._sock = None
        for t in (self._reader, self._heartbeater):
            if t and t.is_alive() and t is not threading.current_thread():
                t.join(timeout=0.3)
        self._fail_all(TubeError("closed"))

    def call(self, cmd: int, payload: bytes, prefix: int) -> Response:
        mid = self._next_mid()
        f = Frame(prefix=prefix, msg_id=mid, msg_type=cmd, payload=payload)
        q: Queue = Queue(maxsize=1)
        with self._plock:
            self._pending[mid] = q
        try:
            with self._slock:
                if self._sock is None:
                    raise TubeError("socket gone")
                self._sock.sendall(f.wire())
            try:
                r = q.get(timeout=self.timeout)
            except Empty:
                raise TubeError(f"timeout cmd=0x{cmd:04X}")
            if isinstance(r, Exception):
                raise r
            return r
        finally:
            with self._plock:
                self._pending.pop(mid, None)

    def _next_mid(self) -> int:
        v = self._mid
        self._mid = 1 if v >= 0xFFFF else v + 1
        return v

    def _start_reader(self):
        if self._reader and self._reader.is_alive():
            return
        t = threading.Thread(target=self._loop, daemon=True)
        self._reader = t
        t.start()

    def _start_heartbeater(self, prefix: int):
        if not self._heartbeat_cmd or self._heartbeat_interval <= 0:
            return
        t = threading.Thread(target=self._hb_loop, args=(prefix,), daemon=True)
        self._heartbeater = t
        t.start()

    def _hb_loop(self, prefix: int):
        while not self._stop.wait(self._heartbeat_interval):
            try:
                self.call(self._heartbeat_cmd, self._heartbeat_data, prefix)
            except Exception:
                pass

    def _loop(self):
        while not self._stop.is_set():
            try:
                r = read_response(self._sock)
            except (socket.timeout, TimeoutError):
                continue
            except Exception:
                if not self._stop.is_set():
                    self._fail_all(TubeError("reader died"))
                return
            with self._plock:
                q = self._pending.get(r.msg_id)
            if q is not None:
                q.put(r)

    def _fail_all(self, exc: Exception):
        with self._plock:
            qs = list(self._pending.values())
            self._pending.clear()
        for q in qs:
            try: q.put_nowait(exc)
            except Exception: pass
