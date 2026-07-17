"""通达信 .dat 板块文件解析器."""

import struct


def parse_block_dat(data: bytes, filename: str = "") -> list[dict]:
    """解析通达信 .dat 板块文件内容.

    格式：
      Header: 384 字节（跳过）
      Count:  2 字节 (uint16 LE)
      Body:   每条记录 2813 字节
              ├── 板块名称: 9 字节 (GBK 编码)
              ├── 股票数量: 2 字节 (uint16 LE)
              ├── 板块类型: 2 字节 (uint16 LE)
              └── 股票代码区: 2800 字节 (每只股票 7 字节，ASCII 编码)
                  最大支持 400 只股票 (2800 / 7 = 400)
    """
    if len(data) < 386:
        return []

    pos = 384
    (count,) = struct.unpack("<H", data[pos : pos + 2])
    pos += 2

    # 推断板块分类
    category = 0
    if "zs" in filename:
        category = 0  # 行业/指数
    elif "gn" in filename:
        category = 2  # 概念
    elif "fg" in filename:
        category = 3  # 风格

    results = []
    for _ in range(count):
        if len(data) < pos + 2813:
            break

        name_b = data[pos : pos + 9]
        stock_count, _type = struct.unpack("<HH", data[pos + 9 : pos + 13])
        name = name_b.decode("gbk", errors="replace").strip("\x00")

        # 股票代码区
        codes = []
        codes_start = pos + 13
        actual_count = min(stock_count, 400)
        for i in range(actual_count):
            c_start = codes_start + i * 7
            c_raw = data[c_start : c_start + 7]
            code = c_raw.decode("ascii", errors="replace").strip("\x00")
            if code:
                codes.append(code)

        results.append({
            "name": name,
            "category": category,
            "block_type": _type,
            "count": stock_count,
            "codes": codes,
        })

        pos += 2813

    return results
