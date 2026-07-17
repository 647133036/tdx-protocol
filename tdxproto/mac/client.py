"""MAC 协议客户端 — 板块/成分股/排行等高级功能."""

import socket
import struct
import threading
from typing import Optional

from .._reconnect import RETRY_DELAYS
from ..hosts import MAC_HOSTS
from ..mac.frame import build_mac_frame, parse_mac_response
from ..mac.commands import (
    _b_board_list, _p_board_list,
    _b_board_members_quotes, _p_board_members_quotes,
    _b_stock_blocks, _p_stock_blocks,
    _b_board_summary, _p_board_summary,
    _b_board_change_ranking, _p_board_change_ranking,
    _b_category_quotes, _p_category_quotes,
    _b_capital_flow, _p_capital_flow,
    _b_server_info, _p_server_info,
    _b_symbol_info, _p_symbol_info,
    Category, FilterType,
)


class MacClient:
    """MAC 协议客户端，用于板块列表、成分股、个股所属板块、板块汇总/排行."""

    def __init__(self, hosts: Optional[list] = None, timeout: float = 8.0):
        self.hosts = hosts or MAC_HOSTS
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._msg_id = 0

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

    def connect(self):
        """连接到最佳 MAC 主机."""
        for host_str in self.hosts:
            try:
                host, port = host_str.rsplit(":", 1)
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                sock.connect((host, int(port)))
                # 发送握手命令（与标准协议相同）
                sock.send(b"\x0c\x02\x18\x93\x00\x01\x03\x00\x03\x00\x0d\x00\x01")
                self._recv_pass(sock)
                sock.send(b"\x0c\x02\x18\x94\x00\x01\x03\x00\x03\x00\x0d\x00\x02")
                self._recv_pass(sock)
                sock.send(
                    b"\x0c\x03\x18\x99\x00\x01\x20\x00\x20\x00\xdb\x0f"
                    b"\xd5\xd0\xc9\xcc\xd6\xa4\xa8\x00\x00\x00\x8f\xc2\x25"
                    b"\x40\x13\x00\x00\xd5\x00\xc9\xcc\xbd\xf0\xd7\xea"
                    b"\x00\x00\x00\x02"
                )
                self._recv_pass(sock)
                self.sock = sock
                self._current_host = host_str
                return
            except Exception:
                if sock:
                    sock.close()
        raise ConnectionError("all mac hosts failed")

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def _next_msg_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def _send_recv_mac(self, body: bytes) -> bytes:
        """发送 MAC 请求并接收响应."""
        if not self.sock:
            raise ConnectionError("not connected")
        msg_id = self._next_msg_id()
        frame = build_mac_frame(msg_id, body)
        self.sock.send(frame)
        raw = self._recv_response()
        _, response_body = parse_mac_response(raw)
        return response_body

    def _recv_response(self) -> bytes:
        """接收 MAC 响应帧."""
        buf = bytearray()
        while len(buf) < 12:
            chunk = self.sock.recv(12 - len(buf))
            if not chunk:
                raise ConnectionError("connection lost")
            buf.extend(chunk)
        head_flag, _, _, body_len = struct.unpack_from("<BIBH", buf, 0)
        if head_flag != 0x1C:
            raise ValueError(f"not a mac frame: head_flag={head_flag:#x}")
        total = 12 + body_len
        while len(buf) < total:
            chunk = self.sock.recv(min(65536, total - len(buf)))
            if not chunk:
                raise ConnectionError("connection lost")
            buf.extend(chunk)
        return bytes(buf)

    def _recv_pass(self, s: socket.socket):
        """丢弃握手响应 — 解析标准 7709 响应头并完整消费 body."""
        try:
            hdr = b""
            while len(hdr) < 16:
                chunk = s.recv(16 - len(hdr))
                if not chunk:
                    return
                hdr += chunk
            _, _, _, zip_len, unzip_len = struct.unpack("<IIIHH", hdr[:16])
            body = b""
            while len(body) < zip_len:
                chunk = s.recv(min(4096, zip_len - len(body)))
                if not chunk:
                    return
                body += chunk
        except Exception:
            pass

    # ---- 公开方法 ----

    def board_list(
        self,
        page_size: int = 150,
        board_type: int = 0,
        sort_column: int = 0,
        sort_order: int = 1,
        start: int = 0,
    ) -> list[dict]:
        """获取板块列表."""
        body = _b_board_list(page_size, board_type, sort_column, sort_order, start)
        raw = self._send_recv_mac(body)
        return _p_board_list(raw)

    def board_members(
        self,
        board_code: str | int,
        page_size: int = 80,
        start: int = 0,
        sort_type: int = 0,
        sort_order: int = 1,
    ) -> list[dict]:
        """获取板块成分股."""
        body = _b_board_members_quotes(board_code, page_size, start, sort_type, sort_order)
        raw = self._send_recv_mac(body)
        return _p_board_members_quotes(raw)

    def stock_blocks(self, market: int, code: str) -> list[dict]:
        """获取个股所属板块."""
        body = _b_stock_blocks(market, code)
        raw = self._send_recv_mac(body)
        return _p_stock_blocks(raw)

    def board_summary(self, board_code: str | int) -> dict:
        """获取板块汇总（成交额/主力净流入/涨跌家数）."""
        body = _b_board_summary(board_code)
        raw = self._send_recv_mac(body)
        return _p_board_summary(raw)

    def board_change_ranking(
        self,
        board_type: int = 0,
        days: int = 5,
        top_n: int = 100,
        sort_order: int = 1,
    ) -> list[dict]:
        """获取板块 N 日涨跌幅排行."""
        body = _b_board_change_ranking(board_type, days, sort_order, top_n)
        raw = self._send_recv_mac(body)
        return _p_board_change_ranking(raw)

    def category_quotes(
        self,
        category: int,
        page_size: int = 80,
        start: int = 0,
        sort_type: int = 0,
        sort_order: int = 1,
        exclude_flags: int = 0,
    ) -> list[dict]:
        """市场分类批量报价（quote-list）.

        category: Category 枚举值（Category.A=全部A股, Category.KCB=科创板, Category.CYB=创业板）
        exclude_flags: FilterType 组合（如 FilterType.ST | FilterType.NEW）
        """
        body = _b_category_quotes(category, page_size, start, sort_type, sort_order, exclude_flags)
        raw = self._send_recv_mac(body)
        return _p_category_quotes(raw)

    def capital_flow(self, market: int, code: str) -> dict:
        """个股资金流向（capital-flow）."""
        body = _b_capital_flow(market, code)
        raw = self._send_recv_mac(body)
        return _p_capital_flow(raw)

    def server_info(self) -> dict:
        """服务器信息（server-info）."""
        body = _b_server_info()
        raw = self._send_recv_mac(body)
        return _p_server_info(raw)

    def symbol_info(self, market: int, code: str) -> dict:
        """个股详细信息（symbol-info）."""
        body = _b_symbol_info(market, code)
        raw = self._send_recv_mac(body)
        return _p_symbol_info(raw)
