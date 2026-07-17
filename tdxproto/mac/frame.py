"""MAC 协议帧编解码 (head_flag=0x1C)."""

import struct

_MAC_HEAD_FLAG = 0x1C


def build_mac_frame(msg_id: int, body: bytes) -> bytes:
    """构建 MAC 请求帧.

    格式: [10B 头][2B msg_id][body]
    """
    inner = struct.pack("<H", msg_id) + body
    header = struct.pack("<BIBHH", _MAC_HEAD_FLAG, 0, 1, len(inner), len(inner))
    return header + inner


def parse_mac_response(raw: bytes) -> tuple[int, bytes]:
    """解析 MAC 响应帧，返回 (msg_id, body).

    帧结构: [10B 头][2B msg_id][body]
    """
    if len(raw) < 12:
        raise ValueError("mac response too short")
    head_flag, _, _, body_len = struct.unpack_from("<BIBH", raw, 0)
    if head_flag != _MAC_HEAD_FLAG:
        raise ValueError(f"not a mac frame: head_flag={head_flag:#x}")
    msg_id = struct.unpack_from("<H", raw, 10)[0]
    body = raw[12 : 12 + body_len]
    return msg_id, body
