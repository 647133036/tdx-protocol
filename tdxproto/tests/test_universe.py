"""核心龙头池 universe 单元测试."""

import re

from tdxproto import CORE_LEADERS, CORE_LEADERS_DESC, core_leader_codes


class TestCoreLeaders:
    def test_count_and_format(self):
        assert len(CORE_LEADERS) == 159
        codes = core_leader_codes()
        assert len(codes) == 159
        assert len(set(codes)) == 159  # 无重复
        for code in codes:
            assert re.fullmatch(r"(sz|sh)\d{6}", code), code
        # 前缀与市场规则一致
        for code in codes:
            raw = code[2:]
            if code.startswith("sh"):
                assert raw[0] == "6", code
            else:
                assert raw[0] in ("0", "3"), code

    def test_names_nonempty(self):
        for code, name in CORE_LEADERS.items():
            assert name.strip(), code

    def test_desc(self):
        assert "159" in CORE_LEADERS_DESC

    def test_spot_members(self):
        assert CORE_LEADERS["sh600519"] == "贵州茅台"
        assert CORE_LEADERS["sz300750"] == "宁德时代"
