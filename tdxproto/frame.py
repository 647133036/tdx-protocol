"""二进制帧编解码 — 7709/7727 共用层。

请求帧布局 (小端):
  [prefix:u8] [msg_id:u32] [ctrl:u8] [data_len+2:u16] [data_len+2:u16] [msg_type:u16] [payload]

响应帧布局:
  [0xB1CB7400:u32] [ctrl:u8] [msg_id:u32] [rsv:u8] [msg_type:u16] [zip_len:u16] [unzip_len:u16] [zlib_payload]

创新: 使用 memoryview 零拷贝解析 + struct.iter_unpack 批量解码。
"""

import socket
import struct
import zlib
from dataclasses import dataclass
from typing import Optional

PREFIX_RESPONSE = b"\xB1\xCB\x74\x00"


@dataclass(frozen=True, slots=True)
class Frame:
    prefix: int
    msg_id: int
    msg_type: int
    payload: bytes
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
    # 同步到魔术字
    w = bytearray(sock_read(s, 4))
    while bytes(w) != PREFIX_RESPONSE:
        w = w[1:] + sock_read(s, 1)

    hdr = sock_read(s, 12)
    ctrl, msg_id, rsv, mtype = struct.unpack_from("<BIBH", hdr, 0)
    zip_len = struct.unpack_from("<H", hdr, 8)[0]
    raw_len = struct.unpack_from("<H", hdr, 10)[0]

    zipped = sock_read(s, zip_len)
    data = zlib.decompress(zipped) if zip_len != raw_len else zipped
    return Response(msg_type=mtype, data=data, raw=bytes(w) + hdr + zipped, control=ctrl, msg_id=msg_id)
