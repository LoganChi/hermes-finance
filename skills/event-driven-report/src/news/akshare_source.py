"""AkshareNewsSource —— 可插拔真实新闻源（akshare 免费接口）。

- news_cctv(date): 央视财经新闻(按日期, 可回测历史)
- stock_info_global_em(): 东财全球财经快讯(实时)

免费 Python 可调，不需代理。替代 tushare news（代理不支持 news/需付费权限）。
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List

from .base import NewsItem, NewsSource


class AkshareNewsSource(NewsSource):
    name = "akshare"

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.mode = self.config.get("mode", "global")  # cctv(按日期历史) | global(实时快讯)
        self.date = self.config.get("date")             # cctv 模式日期 YYYYMMDD

    def fetch(self, limit: int = 50) -> List[NewsItem]:
        os.environ.setdefault("NO_PROXY", "*")  # akshare 东财国内直连，不走系统代理
        import akshare as ak
        out: List[NewsItem] = []
        if self.mode == "cctv":
            date = self.date or datetime.now().strftime("%Y%m%d")
            df = ak.news_cctv(date=date)
            for _, r in df.iterrows():
                out.append(NewsItem(
                    id=f"cctv_{date}_{str(r.get('title', ''))[:8]}",
                    source="akshare_cctv", fetched_at=datetime.now(),
                    title=str(r.get("title", "")), content=r.get("content"), url=None,
                ))
        else:
            df = ak.stock_info_global_em()
            for _, r in df.head(limit).iterrows():
                out.append(NewsItem(
                    id=f"gl_{str(r.get('标题', ''))[:8]}",
                    source="akshare_global", fetched_at=datetime.now(),
                    title=str(r.get("标题", "")), content=r.get("摘要"), url=r.get("链接"),
                ))
        return out[:limit]
