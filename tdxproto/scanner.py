"""Scanner — 通达信主站可用性探测与测速。

两层探测:
  1. TCP 连通性 (快, 1.2s 超时)
  2. 协议握手验证 (慢, 需完成请求/响应往返)

并发扫描, 按握手延迟排序。7709 与 7727 分别扫描。
"""

import socket
import struct
import time
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional


DEFAULT_TIMEOUT = 2.0
DEFAULT_WORKERS = 64

RESPONSE_MAGIC = b"\xB1\xCB\x74\x00"


@dataclass(frozen=True, slots=True)
class ProbeResult:
    host: str
    port: int
    tcp_ok: bool = False
    tcp_latency_ms: float = 0
    handshake_ok: bool = False
    handshake_latency_ms: float = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.handshake_ok

    @property
    def latency_ms(self) -> float:
        return self.handshake_latency_ms if self.handshake_ok else float("inf")


def _tcp_probe(addr: str, port: int, timeout: float) -> tuple[bool, float, str | None]:
    started = time.perf_counter()
    try:
        with socket.create_connection((addr, int(port)), timeout=timeout):
            pass
        return True, round((time.perf_counter() - started) * 1000, 2), None
    except OSError as e:
        return False, 0.0, type(e).__name__


def _handshake_one(addr: str, port: int, prefix: int, cmd: int, payload: bytes,
                   timeout: float) -> tuple[bool, float, str | None]:
    try:
        sock = socket.create_connection((addr, port), timeout=timeout)
        sock.settimeout(timeout)
    except OSError as e:
        return False, 0, type(e).__name__

    started = time.perf_counter()
    try:
        msg_id = 1
        control = 0x01
        dl = len(payload) + 2
        frame = struct.pack("<BIBHHH", prefix, msg_id, control, dl, dl, cmd) + payload
        sock.sendall(frame)

        w = bytearray()
        while len(w) < 4:
            chunk = sock.recv(4 - len(w))
            if not chunk:
                raise ConnectionError("remote closed")
            w.extend(chunk)
        while bytes(w) != RESPONSE_MAGIC:
            w = w[1:] + sock.recv(1)

        hdr = bytearray()
        while len(hdr) < 12:
            chunk = sock.recv(12 - len(hdr))
            if not chunk:
                raise ConnectionError("remote closed")
            hdr.extend(chunk)

        zip_len = struct.unpack_from("<H", hdr, 8)[0]
        raw_len = struct.unpack_from("<H", hdr, 10)[0]

        zipped = bytearray()
        while len(zipped) < zip_len:
            chunk = sock.recv(zip_len - len(zipped))
            if not chunk:
                raise ConnectionError("remote closed")
            zipped.extend(chunk)

        if zip_len != raw_len:
            data = zlib.decompress(bytes(zipped))
        else:
            data = bytes(zipped)

        # 校验响应内容: 错误码/拒绝信息
        text = data.decode("gbk", errors="replace")
        rejected = any(w in text for w in ("失败", "不允许", "演示", "登入"))

        elapsed = round((time.perf_counter() - started) * 1000, 2)
        if rejected:
            return False, elapsed, text[:60].strip()
        return True, elapsed, None

    except Exception as e:
        return False, 0, str(e)[:80]
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _parse_host(host: str) -> tuple[str, int]:
    """从 'ip:port' 字符串解析。"""
    addr, port_str = host.rsplit(":", 1)
    return addr, int(port_str)


def scan_stock(hosts: list[str], *, workers: int = DEFAULT_WORKERS,
               timeout: float = DEFAULT_TIMEOUT) -> list[ProbeResult]:
    """扫描 7709 A股主站 (prefix=0x0C, handshake=0x000D)。"""
    return _scan(hosts, prefix=0x0C, handshake_cmd=0x000D, handshake_data=b"",
                 workers=workers, timeout=timeout)


def scan_futures(hosts: list[str], *, workers: int = DEFAULT_WORKERS,
                 timeout: float = DEFAULT_TIMEOUT) -> list[ProbeResult]:
    """扫描 7727 期货主站 (prefix=0x01, handshake=0x2454, 80B magic)。"""
    handshake_data = bytes.fromhex(
        "1f32c6e5d53dfb41" "1f32c6e5d53dfb41"
        "1f32c6e5d53dfb41" "1f32c6e5d53dfb41"
        "1f32c6e5d53dfb41" "1f32c6e5d53dfb41"
        "1f32c6e5d53dfb41" "1f32c6e5d53dfb41"
        "cce16dffd5ba3fb8" "cbc57a054f7748ea"
    )
    return _scan(hosts, prefix=0x01, handshake_cmd=0x2454, handshake_data=handshake_data,
                 workers=workers, timeout=timeout)


def _scan(hosts: list[str], *, prefix: int, handshake_cmd: int, handshake_data: bytes,
          workers: int, timeout: float) -> list[ProbeResult]:
    candidates = list(dict.fromkeys(hosts))
    worker_count = min(max(1, workers), len(candidates))
    results: list[ProbeResult] = []

    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="tdxscan") as executor:
        futures: dict = {}
        for host in candidates:
            addr, port = _parse_host(host)
            f = executor.submit(_probe_one, addr, port, prefix, handshake_cmd,
                                handshake_data, timeout)
            futures[f] = host

        for f in as_completed(futures):
            results.append(f.result())

    # 按握手延迟排序
    results.sort(key=lambda r: (0 if r.ok else 1, r.latency_ms))
    return results


def _probe_one(addr: str, port: int, prefix: int, cmd: int, payload: bytes,
               timeout: float) -> ProbeResult:
    host = f"{addr}:{port}"

    tcp_ok, tcp_lat, tcp_err = _tcp_probe(addr, port, timeout)
    if not tcp_ok:
        return ProbeResult(host=host, port=port, error=tcp_err)

    hs_ok, hs_lat, hs_err = _handshake_one(addr, port, prefix, cmd, payload, timeout)
    return ProbeResult(host=host, port=port,
                       tcp_ok=True, tcp_latency_ms=tcp_lat,
                       handshake_ok=hs_ok, handshake_latency_ms=hs_lat,
                       error=hs_err)


def best_host(hosts: list[str], *, prefix: int, handshake_cmd: int,
              handshake_data: bytes, workers: int = DEFAULT_WORKERS,
              timeout: float = DEFAULT_TIMEOUT) -> tuple[str, float]:
    """快速找到最快可用主站，失败抛异常。"""
    results = _scan(hosts, prefix=prefix, handshake_cmd=handshake_cmd,
                    handshake_data=handshake_data, workers=workers, timeout=timeout)
    alive = [r for r in results if r.ok]
    if not alive:
        raise ConnectionError(f"no host reachable out of {len(hosts)} candidates")
    return alive[0].host, alive[0].handshake_latency_ms
