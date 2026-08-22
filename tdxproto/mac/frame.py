"""MAC 协议帧编解码 (request head_flag=0x1C, response head_flag=0xB1)."""

import struct

_MAC_HEAD_FLAG = 0x1C
_MAC_RESP_FLAGS = (0x1C, 0xB1)


def build_mac_frame(cmd: int, body: bytes, ctrl: int = 1) -> bytes:
    """构建 MAC 请求帧.

    格式: [10B 头][2B cmd][body]
    header: <BIBHH = head_flag(B) + counter(I) + ctrl(B) + data_len(H) + data_len(H)
    """
    inner = struct.pack("<H", cmd) + body
    header = struct.pack("<BIBHH", _MAC_HEAD_FLAG, 0, ctrl, len(inner), len(inner))
    return header + inner


def parse_mac_response(raw: bytes) -> tuple[int, bytes]:
    """解析 MAC 响应帧，返回 (cmd, body).

    响应帧结构: [10B 头][2B cmd][body]
    响应的 data_len 字段为 0，body 需从 offset 12 读取至末尾。
    """
    if len(raw) < 12:
        raise ValueError("mac response too short")
    head_flag = struct.unpack_from("<B", raw, 0)[0]
    if head_flag not in _MAC_RESP_FLAGS:
        raise ValueError(f"not a mac frame: head_flag={head_flag:#x}")
    cmd = struct.unpack_from("<H", raw, 10)[0]
    body = raw[12:]
    return cmd, body
