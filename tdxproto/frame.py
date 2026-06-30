"""二进制帧编解码 — 7709/7727 共用层。

对齐 pytdx/tdxpy:
  请求帧: [prefix:u8] [msg_id:u32 LE] [ctrl:u8] [data_len:u16 LE] [data_len:u16 LE] [msg_type:u16 LE] [payload]
  响应头: [type:u32 LE] [counter1:u32 LE] [counter2:u32 LE] [zip_len:u16 LE] [unzip_len:u16 LE] (16 bytes)
"""

import socket
import struct
import zlib
from dataclasses import dataclass
from typing import Optional

PREFIX_REQUEST = 0x0C
RSP_HEADER_LEN = 0x10  # 16 bytes


@dataclass(frozen=True, slots=True)
class Frame:
    msg_id: int
    msg_type: int
    payload: bytes
    prefix: int = 0x0C
    control: int = 0x01

    def wire(self) -> bytes:
        dl = len(self.payload) + 2
        return struct.pack("<BIBHHH", self.prefix, self.msg_id, self.control, dl, dl, self.msg_type) + self.payload


@dataclass(frozen=True, slots=True)
class Response:
    msg_type: int
    data: bytes          # 解压后的数据
    raw: bytes
    control: int = 0
    msg_id: int = 0


def sock_read(s: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("remote closed")
        buf.extend(chunk)
    return bytes(buf)


def read_response(s: socket.socket) -> Response:
    """读取 pytdx 格式的响应: <IIIHH (16 bytes) + body."""
    hdr = sock_read(s, RSP_HEADER_LEN)
    resp_type, c1, cmd_echo, zip_len, unzip_len = struct.unpack("<IIIHH", hdr)
    body_buf = sock_read(s, zip_len)
    if zip_len != unzip_len:
        data = zlib.decompress(body_buf)
    else:
        data = body_buf
    msg_id = (c1 >> 8) & 0xFFFF
    return Response(msg_type=cmd_echo, msg_id=msg_id, data=data, raw=hdr + body_buf)
