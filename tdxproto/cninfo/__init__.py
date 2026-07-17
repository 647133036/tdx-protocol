"""巨潮资讯网（cninfo）公告检索——独立数据源，不依赖 TDX 行情服务器。

用法::

    from tdxproto.cninfo import CninfoClient

    client = CninfoClient()
    df = client.get_announcements("688017", count=5)
    print(df.to_dict("records"))
"""

from .client import CninfoClient
from .models import Announcement, CninfoError

__all__ = ["CninfoClient", "Announcement", "CninfoError"]
