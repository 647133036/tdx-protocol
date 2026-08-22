"""板块指数代码桥接 — 将板块简称映射到指数代码.

解决通达信 .dat 板块文件不含指数代码(id)的问题.
通过下载 tdxzs.cfg 和 tdxbk.cfg 完成桥接映射.
"""

import re
from typing import Optional
from dataclasses import dataclass, field
from datetime import date


@dataclass
class BlockWithIndex:
    """带指数代码的板块信息."""
    name: str
    category: int
    block_type: int
    count: int
    codes: list[str]
    index: str = ""          # 板块指数代码 (如 880001)
    index_name: str = ""     # 板块指数名称


class BlockBridge:
    """板块指数代码桥接器.
    
    功能:
        - 解析 tdxzs.cfg 获取板块全称与指数代码映射
        - 解析 tdxbk.cfg 获取板块简称与全称映射
        - 将 .dat 文件解析结果与指数代码关联
        - 提供板块列表和成分股查询
    """
    
    def __init__(self, client):
        self.client = client
        self._zs_map: dict[str, str] = {}      # 全称 -> 指数代码
        self._bk_map: dict[str, str] = {}      # 简称 -> 全称
        self._blocks: list[BlockWithIndex] = []
        self._loaded = False
    
    def _parse_zs_cfg(self, content: str) -> dict[str, str]:
        """解析 tdxzs.cfg 格式.
        
        格式: 全称<tab>指数代码<tab>类型...
        例如: 上证指数<tab>1A0001<tab>1
        """
        result = {}
        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 2:
                name = parts[0].strip()
                code = parts[1].strip()
                if name and code:
                    result[name] = code
        return result
    
    def _parse_bk_cfg(self, content: str) -> dict[str, str]:
        """解析 tdxbk.cfg 格式.
        
        格式: 简称<tab>全称
        例如: 银行<tab>银行板块
        """
        result = {}
        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 2:
                short = parts[0].strip()
                full = parts[1].strip()
                if short and full:
                    result[short] = full
        return result
    
    def _download_and_parse(self, filename: str) -> Optional[str]:
        """下载并解析配置文件.
        
        Args:
            filename: 文件名 (如 tdxzs.cfg)
            
        Returns:
            文件内容，失败返回 None
        """
        try:
            content = self.client.company_info_content("sh000001", filename, 0, 0)
            return content
        except Exception:
            return None
    
    def load_bridge_data(self) -> bool:
        """加载桥接数据.
        
        Returns:
            成功返回 True
        """
        try:
            # 下载 tdxzs.cfg
            zs_content = self._download_and_parse("tdxzs.cfg")
            if zs_content:
                self._zs_map = self._parse_zs_cfg(zs_content)
            
            # 下载 tdxbk.cfg
            bk_content = self._download_and_parse("tdxbk.cfg")
            if bk_content:
                self._bk_map = self._parse_bk_cfg(bk_content)
            
            self._loaded = True
            return True
        except Exception:
            return False
    
    def get_blocks_with_index(self, block_type: int = 0) -> list[BlockWithIndex]:
        """获取带指数代码的板块列表.
        
        Args:
            block_type: 板块类型 (0=行业, 2=概念, 3=风格)
            
        Returns:
            板块列表
        """
        if not self._loaded:
            self.load_bridge_data()
        
        # 根据类型获取板块文件
        if block_type == 0:
            filename = "block_zs.dat"
        elif block_type == 2:
            filename = "block_gn.dat"
        elif block_type == 3:
            filename = "block_fg.dat"
        else:
            filename = "block_zs.dat"
        
        try:
            from .block_reader import parse_block_dat
            raw_blocks = self.client.get_block_file_parsed(filename)
            
            self._blocks = []
            for block in raw_blocks:
                # 创建桥接对象
                bw = BlockWithIndex(
                    name=block['name'],
                    category=block['category'],
                    block_type=block['block_type'],
                    count=block['count'],
                    codes=block['codes'],
                )
                
                # 尝试桥接指数代码
                index_code = self._get_index_by_name(bw.name)
                if index_code:
                    bw.index = index_code
                    bw.index_name = self._get_index_name(index_code)
                
                self._blocks.append(bw)
            
            return self._blocks
        except Exception:
            return []
    
    def _get_index_by_name(self, block_name: str) -> str:
        """根据板块名称获取指数代码.
        
        先直接匹配，再通过简称映射匹配.
        """
        # 直接匹配
        if block_name in self._zs_map:
            return self._zs_map[block_name]
        
        # 通过简称映射
        if block_name in self._bk_map:
            full_name = self._bk_map[block_name]
            if full_name in self._zs_map:
                return self._zs_map[full_name]
        
        return ""
    
    def _get_index_name(self, code: str) -> str:
        """根据指数代码获取名称."""
        for name, c in self._zs_map.items():
            if c == code:
                return name
        return ""
    
    def get_block_members(self, block_code: str) -> list[dict]:
        """获取板块成分股.
        
        Args:
            block_code: 板块代码或名称
            
        Returns:
            成分股列表
        """
        # 查找板块
        target = None
        for b in self._blocks:
            if b.index == block_code or b.name == block_code:
                target = b
                break
        
        if not target:
            # 尝试通过指数代码查找
            for b in self._blocks:
                if b.index == block_code:
                    target = b
                    break
        
        if not target:
            return []
        
        # 获取行情数据
        result = []
        for code in target.codes[:50]:  # 限制数量
            try:
                quote = self.client.quote(code)
                if quote:
                    result.append({
                        'code': code,
                        'name': quote.name,
                        'price': quote.price,
                        'change_pct': quote.change_pct,
                    })
            except Exception:
                continue
        
        return result


# 全局桥接器
_block_bridge: Optional[BlockBridge] = None


def get_block_bridge(client) -> BlockBridge:
    """获取板块桥接器单例."""
    global _block_bridge
    if _block_bridge is None or _block_bridge.client != client:
        _block_bridge = BlockBridge(client)
    return _block_bridge
