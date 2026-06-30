import socket
import threading
import struct
import zlib
import time

import pytest

from tdxproto.tube import Tube, TubeError
from tdxproto.frame import Frame, Response, read_response


class MockServer:
    """模拟TDX服务器，用于测试Tube传输层。"""
    
    def __init__(self, handler_fn):
        """
        handler_fn: (socket, msg_id, cmd, payload) -> bytes
        返回要发送的响应数据（解压后的payload）。
        """
        self.handler_fn = handler_fn
        self.sock = None
        self.threads = []
        self._stop = threading.Event()
    
    def start(self, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", port))
        self.sock.listen(10)
        self.sock.settimeout(1)
        
        for _ in range(4):  # 4 worker threads
            t = threading.Thread(target=self._accept_loop, daemon=True)
            t.start()
            self.threads.append(t)
    
    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                conn, addr = self.sock.accept()
                t = threading.Thread(target=self._handle, args=(conn,), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except Exception:
                break
    
    def _handle(self, conn):
        conn.settimeout(5)
        try:
            while not self._stop.is_set():
                # Read request frame
                raw = b""
                while len(raw) < 12:
                    chunk = conn.recv(12 - len(raw))
                    if not chunk:
                        return
                    raw += chunk
                
                # Parse frame header
                prefix = raw[0]
                msg_id = struct.unpack_from("<I", raw, 1)[0]
                ctrl = raw[5]
                dl = struct.unpack_from("<H", raw, 6)[0]
                msg_type = struct.unpack_from("<H", raw, 10)[0]
                
                # Read payload
                payload = b""
                while len(payload) < dl - 2:
                    chunk = conn.recv(dl - 2 - len(payload))
                    if not chunk:
                        return
                    payload += chunk
                
                # Call handler
                response_data = self.handler_fn(conn, msg_id, msg_type, payload)
                
                if response_data is None:
                    return
                
                # Build response frame (header <IIIHH = 16 bytes, then body)
                zip_data = zlib.compress(response_data)
                hdr = struct.pack("<IIIHH", 0, (msg_id << 8), msg_type, len(zip_data), len(response_data))
                conn.sendall(hdr + zip_data)
                
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
    
    def stop(self):
        self._stop.set()
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        for t in self.threads:
            t.join(timeout=1)


class TestTubeBasic:
    """Tube传输层基本功能测试。"""
    
    @pytest.fixture
    def mock_server(self, request):
        handler = request.param if hasattr(request, 'param') else None
        server = MockServer(handler or _default_handler)
        port = 19700 + hash(request.node.name) % 1000
        server.start(port)
        yield server, port
        server.stop()
    
    def test_open_and_close(self, mock_server):
        server, port = mock_server
        tube = Tube(hosts=[f"127.0.0.1:{port}"], timeout=2.0)
        host = tube.open(prefix=0x0C, handshake_cmd=0x0015, handshake_data=b"\x00\x00")
        assert host is not None
        assert tube.host is not None
        tube.close()
    
    def test_call_response(self, mock_server):
        server, port = mock_server
        tube = Tube(hosts=[f"127.0.0.1:{port}"], timeout=2.0)
        host = tube.open(prefix=0x0C, handshake_cmd=0x0015, handshake_data=b"\x00\x00")
        
        resp = tube.call(0x044E, b"\x01\x00", 0x0C)
        assert resp.msg_type == 0x044E
        assert isinstance(resp.data, bytes)
        
        tube.close()
    
    def test_timeout_raises(self):
        tube = Tube(hosts=["127.0.0.1:1"], timeout=0.5)
        with pytest.raises((TubeError, OSError)):
            tube.open(prefix=0x0C, handshake_cmd=0x0015, handshake_data=b"\x00\x00")


class TestTubeFailover:
    """Tube多主机failover测试。"""
    
    def test_failover_to_second_host(self):
        tube = Tube(
            hosts=["127.0.0.1:1", "127.0.0.1:2"],
            timeout=0.5,
        )
        # Both hosts are unreachable, should raise
        with pytest.raises(TubeError):
            tube.open(prefix=0x0C, handshake_cmd=0x0015, handshake_data=b"\x00\x00")


class TestTubeHeartbeat:
    """Tube心跳机制测试。"""
    
    def test_heartbeat_disabled(self):
        # Create a simple mock server for heartbeat test
        server = MockServer(_default_handler)
        port = 19800 + hash("heartbeat_test") % 1000
        server.start(port)
        try:
            tube = Tube(
                hosts=[f"127.0.0.1:{port}"],
                timeout=2.0,
                heartbeat_cmd=0,  # disabled
            )
            host = tube.open(prefix=0x0C, handshake_cmd=0x0015, handshake_data=b"\x00\x00")
            assert host is not None
            tube.close()
        finally:
            server.stop()


def _default_handler(conn, msg_id, cmd, payload):
    """默认处理器：返回payload的反转。"""
    return payload[::-1]


class TestTubeMultipleCalls:
    """多次调用测试。"""
    
    def test_sequential_calls(self):
        server = MockServer(_default_handler)
        port = 19800 + hash("multi_call_test") % 1000
        server.start(port)
        try:
            tube = Tube(hosts=[f"127.0.0.1:{port}"], timeout=2.0)
            tube.open(prefix=0x0C, handshake_cmd=0x0015, handshake_data=b"\x00\x00")
            
            for i in range(5):
                resp = tube.call(0x044E, i.to_bytes(1, "little"), 0x0C)
                assert resp.data == bytes([i])
            
            tube.close()
        finally:
            server.stop()
