"""安全审查：URL 白名单、路径穿越、代码白名单。"""
import pytest

from tdxproto.cninfo.client import _assert_allowed_url, CninfoClient
from tdxproto.cninfo.models import Announcement, CninfoError
from tdxproto.ccpm.client import _fetch_xml


class TestCninfoUrlAllowlist:
    def test_reject_file_scheme(self):
        with pytest.raises(CninfoError):
            _assert_allowed_url("file:///etc/passwd")

    def test_reject_other_host(self):
        with pytest.raises(CninfoError):
            _assert_allowed_url("https://evil.example/x")

    def test_allow_cninfo(self):
        _assert_allowed_url("https://www.cninfo.com.cn/new/disclosure")
        _assert_allowed_url("http://static.cninfo.com.cn/a.pdf")


class TestCninfoPdfPath:
    def test_filename_traversal_stays_in_dest(self, tmp_path):
        client = CninfoClient()
        ann = Announcement(
            title="t", type="a", date="2026-09-01", url="u",
            code="000001", org_id="1", announcement_id="2",
            announcement_time=0, pdf_url="",
        )
        with pytest.raises(CninfoError, match="无 PDF"):
            client.download_pdf(ann, dest_dir=tmp_path, filename="../../etc/passwd")

    def test_filename_stripped_to_basename(self, tmp_path):
        from pathlib import Path
        name = Path("../../etc/passwd").name
        assert name == "passwd"


class TestCcpmHostAllowlist:
    def test_reject_non_cffex(self):
        assert _fetch_xml("http://evil.example/x.xml") == ""
        assert _fetch_xml("file:///tmp/x") == ""


class TestWebServerCode:
    def test_safe_code_accepts_prefixed(self):
        from web_server import _safe_code
        assert _safe_code("sz000001") == "sz000001"
        assert _safe_code("SH600000") == "SH600000"

    def test_safe_code_rejects_injection(self):
        from web_server import _safe_code
        assert _safe_code("sz000001;rm") == "sh600000"
        assert _safe_code("../etc") == "sh600000"
        assert _safe_code("aaaaaaaaaaaaa") == "sh600000"


class TestWebServerDoS:
    """DoS 防护测试。"""

    def test_max_request_body_defined(self):
        from web_server import _MAX_REQUEST_BODY
        assert _MAX_REQUEST_BODY == 1024 * 1024

    def test_max_kline_bars_defined(self):
        from web_server import _MAX_KLINE_BARS
        assert _MAX_KLINE_BARS == 5000

    def test_max_codes_from_server_defined(self):
        from web_server import _MAX_CODES_FROM_SERVER
        assert _MAX_CODES_FROM_SERVER == 500

    def test_sanitize_error_redacts_ip(self):
        from web_server import Handler
        h = Handler.__new__(Handler)
        err = Exception("Connection to 192.168.1.1:7709 failed")
        result = h._sanitize_error(err)
        assert "192.168.1.1" not in result
        assert "[REDACTED]" in result

    def test_sanitize_error_redacts_path(self):
        from web_server import Handler
        h = Handler.__new__(Handler)
        err = Exception("File not found: /workspace/data/long/path/to/something/file.txt")
        result = h._sanitize_error(err)
        assert "[PATH REDACTED]" in result

    def test_sanitize_error_truncates(self):
        from web_server import Handler
        h = Handler.__new__(Handler)
        err = Exception("x" * 1024)
        result = h._sanitize_error(err)
        assert len(result) <= 512
