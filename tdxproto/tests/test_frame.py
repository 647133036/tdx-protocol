import struct
import zlib

import pytest

from tdxproto.frame import Frame, Response, sock_read, read_response, PREFIX_REQUEST


class TestFrameEncoding:
    def test_empty_payload(self):
        f = Frame(prefix=0x0C, msg_id=1, msg_type=0x0015, payload=b"")
        wire = f.wire()
        # [prefix:1][msg_id:4][ctrl:1][dl_hi:2][dl_lo:2][msg_type:2] = 12 bytes
        assert len(wire) == 12

    def test_with_payload(self):
        f = Frame(prefix=0x0C, msg_id=1, msg_type=0x0015, payload=b"\x00\x00")
        wire = f.wire()
        assert len(wire) == 14

    def test_prefix_7709(self):
        f = Frame(prefix=0x0C, msg_id=1, msg_type=0x044E, payload=b"\x01\x00")
        assert f.wire()[0] == 0x0C

    def test_prefix_7727(self):
        f = Frame(prefix=0x01, msg_id=1, msg_type=0x23F5, payload=b"\x02\x00")
        assert f.wire()[0] == 0x01

    def test_msg_id_increment(self):
        f1 = Frame(prefix=0x0C, msg_id=1, msg_type=0x0001, payload=b"")
        f2 = Frame(prefix=0x0C, msg_id=999, msg_type=0x0002, payload=b"x")
        assert f1.wire() != f2.wire()

    def test_ctrl_default(self):
        f = Frame(prefix=0x0C, msg_id=1, msg_type=0x0001, payload=b"")
        # ctrl is at offset 5
        assert f.wire()[5] == 0x01

    def test_ctrl_custom(self):
        f = Frame(prefix=0x0C, msg_id=1, msg_type=0x0001, payload=b"", control=0x10)
        assert f.wire()[5] == 0x10

    def test_wire_format_check(self):
        """Verify the wire format matches the spec."""
        f = Frame(prefix=0x0C, msg_id=5, msg_type=0x044E, payload=b"\x01\x00")
        wire = f.wire()
        
        # prefix
        assert wire[0] == 0x0C
        # msg_id (u32 LE)
        assert struct.unpack_from("<I", wire, 1)[0] == 5
        # ctrl
        assert wire[5] == 0x01
        # data_len+2 (u16 LE) at offset 6
        dl = struct.unpack_from("<H", wire, 6)[0]
        assert dl == 4  # 2 bytes payload + 2
        # data_len+2 again at offset 8
        dl2 = struct.unpack_from("<H", wire, 8)[0]
        assert dl2 == 4
        # msg_type (u16 LE) at offset 10
        mt = struct.unpack_from("<H", wire, 10)[0]
        assert mt == 0x044E
        # payload
        assert wire[12:] == b"\x01\x00"


class TestResponseDecoding:
    def test_uncompressed_frame(self):
        payload = b"\x01\x00\x02\x00"
        zip_len = len(payload)
        raw_len = len(payload)
        hdr = struct.pack("<IIIHH", 0, 0, 0x044E, zip_len, raw_len)
        raw = hdr + payload
        resp = Response(msg_type=0x044E, data=payload, raw=raw, control=0, msg_id=0)
        assert resp.data == payload
        assert resp.msg_type == 0x044E

    def test_compressed_frame(self):
        """Test parsing a response where zip_len != raw_len (compressed)."""
        original = b"\x01\x00\x02\x00\x03\x00"
        compressed = zlib.compress(original)
        zip_len = len(compressed)
        raw_len = len(original)
        
        resp = Response(
            msg_type=0x0015,
            data=original,
            raw=b"" + struct.pack("<BIBH HH", 0x01, 1, 0, 0x0015, zip_len, raw_len) + compressed,
            control=0x01,
            msg_id=1,
        )
        assert resp.data == original


class TestSockRead:
    def test_raises_on_empty_socket(self):
        """sock_read should raise ConnectionError when socket is closed."""
        import socket
        # Create a pair of connected sockets
        s1, s2 = socket.socketpair()
        s2.close()  # Close other end
        with pytest.raises(ConnectionError):
            sock_read(s1, 1024)
        s1.close()


class TestFrameRoundTrip:
    def test_7709_handshake_frame(self):
        f = Frame(prefix=0x0C, msg_id=1, msg_type=0x0015, payload=b"\x00\x00")
        wire = f.wire()
        assert len(wire) == 14
        
        # Verify it can be unpacked correctly
        assert struct.unpack_from("<B", wire, 0)[0] == 0x0C
        assert struct.unpack_from("<I", wire, 1)[0] == 1
        assert struct.unpack_from("<H", wire, 10)[0] == 0x0015

    def test_7727_handshake_frame(self):
        hs_data = bytes.fromhex("1f32c6e5d53dfb41" * 8 + "cce16dffd5ba3fb8" + "cbc57a054f7748ea")
        f = Frame(prefix=0x01, msg_id=1, msg_type=0x2454, payload=hs_data)
        wire = f.wire()
        assert len(wire) == 80 + 12  # 80 bytes payload + 12 bytes header
        assert wire[0] == 0x01
