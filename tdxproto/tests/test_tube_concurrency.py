"""Tube 线程安全单元测试."""
import threading
import pytest

from tdxproto.tube import Tube, TubeError


class TestTubeMsgId:
    """验证 msg_id 生成是线程安全的."""

    def test_next_mid_is_sequential(self):
        """顺序调用 msg_id 递增."""
        tube = Tube(hosts=["127.0.0.1:7709"], timeout=0.1)
        mids = [tube._next_mid() for _ in range(10)]
        assert mids == list(range(1, 11))

    def test_next_mid_wraps(self):
        """msg_id 超过 0xFFFF 后回绕."""
        tube = Tube(hosts=["127.0.0.1:7709"], timeout=0.1)
        tube._mid = 0xFFFF
        m1 = tube._next_mid()
        m2 = tube._next_mid()
        assert m1 == 0xFFFF
        assert m2 == 1

    def test_next_mid_thread_safe(self):
        """多线程下 msg_id 不重复."""
        tube = Tube(hosts=["127.0.0.1:7709"], timeout=0.1)
        mids = []
        lock = threading.Lock()

        def collect_mid():
            mid = tube._next_mid()
            with lock:
                mids.append(mid)

        threads = [threading.Thread(target=collect_mid) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(mids) == 100
        assert len(set(mids)) == 100, f"存在重复 msg_id: {mids}"


class TestTubeCallTimeout:
    """Tube.call 超时行为."""

    def test_call_timeout_raises_tube_error(self):
        """socket 无响应时抛出 TubeError."""
        tube = Tube(hosts=["127.0.0.1:1"], timeout=0.01)
        try:
            tube.open(prefix=0x0C, handshake_cmd=0, handshake_data=b"")
        except (TubeError, OSError):
            pass  # 连接失败是正常的
        # 如果连接成功但无响应，应超时
        if tube._sock:
            with pytest.raises(TubeError):
                tube.call(0x052D, b"\x00" * 26, 0x0C)
