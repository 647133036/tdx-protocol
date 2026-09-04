"""MAC 协议客户端 — 板块/成分股/排行等高级功能."""

import socket
import struct
import threading
from typing import Optional

from .._reconnect import RETRY_DELAYS
from ..hosts import MAC_HOSTS
from ..mac.frame import build_mac_frame, parse_mac_response
from ..stock.commands import setup_cmd1, setup_cmd2, setup_cmd3
from ..mac.commands import (
    _b_board_list, _p_board_list,
    _b_board_members_quotes, _p_board_members_quotes,
    _b_stock_blocks, _p_stock_blocks,
    _b_board_summary, _p_board_summary,
    _b_category_quotes, _p_category_quotes,
    _b_capital_flow, _p_capital_flow,
    _b_server_info, _p_server_info,
    _b_symbol_info, _p_symbol_info,
    Category, FilterType, SortOrder, SortColumn,
)

_MAC_RESP_FLAGS = (0x1C, 0xB1)


class MacClient:
    """MAC 协议客户端，用于板块列表、成分股、个股所属板块、板块汇总/排行."""

    def __init__(self, hosts: Optional[list] = None, timeout: float = 8.0):
        self.hosts = hosts or MAC_HOSTS
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._current_host: Optional[str] = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

    def connect(self):
        """连接到最佳 MAC 主机."""
        for host_str in self.hosts:
            sock = None
            try:
                host, port = host_str.rsplit(":", 1)
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                sock.connect((host, int(port)))
                sock.send(setup_cmd1())
                self._recv_pass(sock)
                sock.send(setup_cmd2())
                self._recv_pass(sock)
                sock.send(setup_cmd3())
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

    def _send_recv_mac(self, cmd: int, body: bytes, ctrl: int = 1) -> bytes:
        """发送 MAC 请求并接收响应."""
        if not self.sock:
            raise ConnectionError("not connected")
        frame = build_mac_frame(cmd, body, ctrl=ctrl)
        with self._lock:
            self.sock.send(frame)
            raw = self._recv_response()
        _, response_body = parse_mac_response(raw)
        return response_body

    def _recv_response(self) -> bytes:
        """接收 MAC 响应帧.

        响应的 data_len 字段为 0，无法预知 body 长度。
        先读 12 字节头+cmd，再以短超时读取剩余 body。
        """
        buf = bytearray()
        while len(buf) < 12:
            chunk = self.sock.recv(8192)
            if not chunk:
                raise ConnectionError("connection lost")
            buf.extend(chunk)

        head_flag = buf[0]
        if head_flag not in _MAC_RESP_FLAGS:
            raise ValueError(f"not a mac frame: head_flag={head_flag:#x}")

        orig_timeout = self.sock.gettimeout()
        self.sock.settimeout(1.0)
        try:
            while True:
                try:
                    chunk = self.sock.recv(8192)
                    if not chunk:
                        break
                    buf.extend(chunk)
                except socket.timeout:
                    break
        finally:
            self.sock.settimeout(orig_timeout)
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
        raw = self._send_recv_mac(0x1231, body)
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
        raw = self._send_recv_mac(0x122C, body)
        return _p_board_members_quotes(raw)

    def stock_blocks(self, market: int, code: str) -> list[dict]:
        """获取个股所属板块."""
        body = _b_stock_blocks(market, code)
        raw = self._send_recv_mac(0x1218, body, ctrl=1)
        return _p_stock_blocks(raw)

    def board_summary(self, board_code: str | int) -> dict:
        """获取板块汇总（成交额/主力净流入/涨跌家数）."""
        body = _b_board_summary(board_code)
        raw = self._send_recv_mac(0x122C, body)
        return _p_board_summary(raw)

    def board_change_ranking(
        self,
        board_type: int = 0,
        days: int = 5,
        top_n: int = 100,
        sort_order: int = 1,
    ) -> list[dict]:
        """获取板块涨跌幅排行.

        通过 board_list 获取板块数据后客户端排序，
        按 rise_speed（涨跌幅）排序返回 top_n 条.
        """
        boards = self.board_list(
            page_size=300,
            board_type=board_type,
            sort_column=3,
            sort_order=sort_order,
        )
        if not boards:
            return []
        for b in boards:
            b["change_pct"] = b.get("rise_speed", 0)
        boards.sort(
            key=lambda x: x.get("change_pct", 0),
            reverse=(sort_order == SortOrder.DESC),
        )
        return boards[:top_n]

    def board_amount_ranking(
        self,
        board_type: int = 0,
        top_n: int = 100,
        sort_order: int = SortOrder.DESC,
    ) -> list[dict]:
        """按成交额获取板块排行.

        通过 board_list + board_summary 组合获取完整数据，
        客户端按 amount 排序返回 top_n 条.
        """
        boards = self._board_ranking_by(
            board_type=board_type,
            sort_field="amount",
            top_n=top_n,
            sort_order=sort_order,
        )
        return boards

    def board_volume_ranking(
        self,
        board_type: int = 0,
        top_n: int = 100,
        sort_order: int = SortOrder.DESC,
    ) -> list[dict]:
        """按成交量获取板块排行."""
        return self._board_ranking_by(
            board_type=board_type,
            sort_field="vol",
            top_n=top_n,
            sort_order=sort_order,
        )

    def board_main_net_amount_ranking(
        self,
        board_type: int = 0,
        top_n: int = 100,
        sort_order: int = SortOrder.DESC,
    ) -> list[dict]:
        """按主力净流入获取板块排行.

        正值 = 主力净流入，负值 = 主力净流出。
        DESC = 净流入最多在前，ASC = 净流出最多在前。
        """
        return self._board_ranking_by(
            board_type=board_type,
            sort_field="main_net_amount",
            top_n=top_n,
            sort_order=sort_order,
        )

    def _board_ranking_by(
        self,
        board_type: int = 0,
        sort_field: str = "amount",
        top_n: int = 100,
        sort_order: int = SortOrder.DESC,
    ) -> list[dict]:
        """通用板块排行：board_list 获取代码，board_summary 获取资金数据，客户端排序.

        为控制请求量，最多查询 100 个板块的 board_summary。
        """
        boards = self.board_list(
            page_size=100,
            board_type=board_type,
        )
        enriched: list[dict] = []
        for b in boards:
            code = b.get("code")
            if not code:
                continue
            try:
                summary = self.board_summary(code)
                enriched.append({
                    "code": code,
                    "name": b.get("name", ""),
                    "price": b.get("price", 0),
                    "change_pct": b.get("rise_speed", 0),
                    "amount": summary.get("amount", 0),
                    "vol": summary.get("vol", 0),
                    "main_net_amount": summary.get("main_net_amount", 0),
                    "up_count": summary.get("up_count", 0),
                    "down_count": summary.get("down_count", 0),
                    "member_count": summary.get("member_count", 0),
                })
            except Exception:
                continue
        reverse = (sort_order == SortOrder.DESC)
        enriched.sort(key=lambda x: x.get(sort_field, 0) or 0, reverse=reverse)
        return enriched[:top_n]

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
        raw = self._send_recv_mac(0x122C, body)
        return _p_category_quotes(raw)

    def capital_flow(self, market: int, code: str) -> dict:
        """个股资金流向（capital-flow）."""
        body = _b_capital_flow(market, code)
        raw = self._send_recv_mac(0x1218, body, ctrl=2)
        return _p_capital_flow(raw)

    def server_info(self) -> dict:
        """服务器信息（server-info）."""
        body = _b_server_info()
        raw = self._send_recv_mac(0x120F, body)
        return _p_server_info(raw)

    def symbol_info(self, market: int, code: str) -> dict:
        """个股详细信息（symbol-info）."""
        body = _b_symbol_info(market, code)
        raw = self._send_recv_mac(0x122A, body)
        return _p_symbol_info(raw)
