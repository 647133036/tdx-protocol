"""Scanner — 通达信主站可用性探测与测速。

两层探测:
  1. TCP 连通性 (快, 1.2s 超时)
  2. 协议握手验证 (慢, 需完成请求/响应往返)

并发扫描, 按握手延迟排序。7709 与 7727 分别扫描。

7709 股票: 3 步握手 (0x1893 → 0x1894 → 0x1899), 之后才能发业务命令
7727 期货: 1 步握手 (0x2454 + 80B magic)
"""

import socket
import struct
import time
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional, Callable


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


def _read_response_body(sock: socket.socket, zip_len: int, timeout: float) -> bytes:
    """读取响应 body (压缩或非压缩)."""
    sock.settimeout(timeout)
    zipped = bytearray()
    while len(zipped) < zip_len:
        remaining = zip_len - len(zipped)
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("remote closed")
        zipped.extend(chunk)
    
    # 需要判断是否解压: 尝试用 zlib，失败则返回原始数据
    try:
        data = zlib.decompress(bytes(zipped))
        return data
    except zlib.error:
        return bytes(zipped)


def _read_response_header(sock: socket.socket) -> tuple[int, int]:
    """读取 12 字节响应头 (跳过 8 字节魔术字), 返回 (zip_len, unzip_len)."""
    sock.settimeout(2.0)
    
    # 跳过 4 字节魔术字
    magic = bytearray()
    while len(magic) < 4:
        chunk = sock.recv(4 - len(magic))
        if not chunk:
            raise ConnectionError("remote closed")
        magic.extend(chunk)
    
    # 读取 8 字节头
    hdr = bytearray()
    while len(hdr) < 8:
        chunk = sock.recv(8 - len(hdr))
        if not chunk:
            raise ConnectionError("remote closed")
        hdr.extend(chunk)
    
    zip_len = struct.unpack_from("<H", hdr, 0)[0]
    unzip_len = struct.unpack_from("<H", hdr, 2)[0]
    
    return zip_len, unzip_len


def _handshake_7709(addr: str, port: int, timeout: float) -> tuple[bool, float, str | None]:
    """7709 股票协议握手: 快速验证(仅第1步+count命令, ~50ms)."""
    try:
        sock = socket.create_connection((addr, port), timeout=timeout)
        sock.settimeout(timeout)
    except OSError as e:
        return False, 0, type(e).__name__

    started = time.perf_counter()
    try:
        # 第 1 步握手 (快速验证)
        sock.sendall(bytes.fromhex("0c 02 18 93 00 01 03 00 03 00 0d 00 01"))
        
        # 消耗第1步响应
        try:
            magic = sock.recv(4)
            if not magic:
                raise ConnectionError("remote closed")
            hdr = sock.recv(8)
            zip_len = struct.unpack_from("<H", hdr, 0)[0]
            if zip_len > 0:
                body = sock.recv(zip_len)
        except Exception:
            pass
        
        # 发count命令验证服务器可用
        pkg = bytearray.fromhex("0c 0c 18 6c 00 01 08 00 08 00 4e 04")
        pkg.extend(struct.pack("<H", 1))  # market=1 (上海)
        pkg.extend(b"\x75\xc7\x33\x01")
        sock.sendall(bytes(pkg))
        
        # 读取count响应
        hdr = sock.recv(16)
        resp_type, c1, c2, zip_len, unzip_len = struct.unpack("<IIIHH", hdr)
        body = sock.recv(zip_len)
        
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        return True, elapsed, None
        
    except Exception as e:
        return False, 0, str(e)[:80]
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _handshake_7727(addr: str, port: int, timeout: float) -> tuple[bool, float, str | None]:
    """7727 期货协议握手: 1 步握手 (0x2454 + 80B magic)."""
    handshake_data = bytes.fromhex(
        "1f32c6e5d53dfb41" "1f32c6e5d53dfb41"
        "1f32c6e5d53dfb41" "1f32c6e5d53dfb41"
        "1f32c6e5d53dfb41" "1f32c6e5d53dfb41"
        "1f32c6e5d53dfb41" "1f32c6e5d53dfb41"
        "cce16dffd5ba3fb8" "cbc57a054f7748ea"
    )
    
    try:
        sock = socket.create_connection((addr, port), timeout=timeout)
        sock.settimeout(timeout)
    except OSError as e:
        return False, 0, type(e).__name__

    started = time.perf_counter()
    try:
        msg_id = 1
        control = 0x01
        dl = len(handshake_data) + 2
        frame = struct.pack("<BIBHHH", 0x01, msg_id, control, dl, dl, 0x2454) + handshake_data
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
        rejected = any(w in text for w in ("失败", "不允许", "演示", "登入", "版本不一致"))

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
    """扫描 7709 A股主站 (3步握手 + count验证)."""
    return _scan(hosts, handshake_fn=_handshake_7709,
                 workers=workers, timeout=timeout)


def scan_futures(hosts: list[str], *, workers: int = DEFAULT_WORKERS,
                 timeout: float = DEFAULT_TIMEOUT) -> list[ProbeResult]:
    """扫描 7727 期货主站 (1步握手)."""
    return _scan(hosts, handshake_fn=_handshake_7727,
                 workers=workers, timeout=timeout)


def _scan(hosts: list[str], *, handshake_fn: Callable,
          workers: int, timeout: float) -> list[ProbeResult]:
    candidates = list(dict.fromkeys(hosts))
    worker_count = min(max(1, workers), len(candidates))
    results: list[ProbeResult] = []

    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="tdxscan") as executor:
        futures: dict = {}
        for host in candidates:
            addr, port = _parse_host(host)
            f = executor.submit(_probe_one, addr, port, handshake_fn, timeout)
            futures[f] = host

        for f in as_completed(futures):
            results.append(f.result())

    # 按握手延迟排序
    results.sort(key=lambda r: (0 if r.ok else 1, r.latency_ms))
    return results


def _probe_one(addr: str, port: int, handshake_fn: Callable,
               timeout: float) -> ProbeResult:
    host = f"{addr}:{port}"

    tcp_ok, tcp_lat, tcp_err = _tcp_probe(addr, port, timeout)
    if not tcp_ok:
        return ProbeResult(host=host, port=port, error=tcp_err)

    hs_ok, hs_lat, hs_err = handshake_fn(addr, port, timeout)
    return ProbeResult(host=host, port=port,
                       tcp_ok=True, tcp_latency_ms=tcp_lat,
                       handshake_ok=hs_ok, handshake_latency_ms=hs_lat,
                       error=hs_err)
