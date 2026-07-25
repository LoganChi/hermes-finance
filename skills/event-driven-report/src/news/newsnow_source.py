"""NewsnowSource —— 通过 newsnow.busiyi.world API 拉取多源财经新闻。

newsnow 是开源项目(ourongxing/newsnow)，提供聚合的多平台热点新闻。
API: https://newsnow.busiyi.world/api/s?id={source_id}
需要 User-Agent + Referer 头才能访问(裸 curl 被403)。

支持的数据源:
  cls-telegraph    财联社电报
  wallstreetcn-news 华尔街见闻
  jin10            金十数据（宏观经济/央行/外汇商品）
  gelonghui        格隆汇（港股/A股视角）
  36kr-quick       36氪快讯（newsnow 已失效）
  ithome           IT之家

正文回填: cls-telegraph 的 detail 页有正文(~1.6k字)，补上喂 LLM 提升事件抽取信息量(噪音率受样本影响、跨天不可比，质量看标的映射准确性)。
          wallstreetcn-news 是 SPA，requests 抓不到正文，保持 None(由 extractor 兜底)。
          36kr-quick 源在 newsnow 已失效(返回0条)，默认不再拉。
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from .base import NewsItem, NewsSource

_NEWSNOW_URL = "https://newsnow.busiyi.world/api/s"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://newsnow.busiyi.world/",
    "Accept": "application/json",
}

# 抓正文用的浏览器头（newsnow 的 url 指向财联社等原站）
_FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
}

# newsnow 数据源ID → 中文名
SOURCES = {
    "cls-telegraph": "财联社",
    "wallstreetcn-news": "华尔街见闻",
    "jin10": "金十数据",
    "gelonghui": "格隆汇",
    "36kr-quick": "36氪",
    "ithome": "IT之家",
}


class NewsnowSource(NewsSource):
    """newsnow 多源新闻聚合。可拉多个平台，每源20-30条热点。"""

    name = "newsnow"

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        # 财联社(A股事件) + 华尔街见闻(全球宏观) + 金十(经济数据/央行) + 格隆汇(港股/A股视角)
        self.sources = self.config.get("sources") or ["cls-telegraph", "wallstreetcn-news", "jin10", "gelonghui"]
        self.limit_per_source = int(self.config.get("limit_per_source", 20))

    def fetch(self, limit: int = 50) -> List[NewsItem]:
        all_items = []
        for sid in self.sources:
            source_name = SOURCES.get(sid, sid)
            try:
                resp = requests.get(
                    _NEWSNOW_URL,
                    params={"id": sid},
                    headers=_HEADERS,
                    timeout=10,
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
                items = data.get("items") or data.get("data") or []
                for it in items[:self.limit_per_source]:
                    title = it.get("title", "")
                    if not title:
                        continue
                    pub_ts = it.get("pubDate") or it.get("publish_time")
                    published = None
                    if pub_ts:
                        try:
                            published = datetime.fromtimestamp(pub_ts / 1000)
                        except Exception:
                            published = None
                    all_items.append(NewsItem(
                        id=f"nw_{sid}_{it.get('id', title[:10])}",
                        source=source_name,
                        fetched_at=datetime.now(),
                        published_at=published,
                        title=title,
                        content=None,
                        url=it.get("url") or it.get("mobileUrl"),
                    ))
            except Exception:
                continue
        # 回填正文：财联社 detail 页有正文(~1.6k字)；华尔街见闻等 SPA 抓不到则保持 None
        if all_items:
            urls = [it.url for it in all_items]
            with ThreadPoolExecutor(max_workers=8) as ex:
                bodies = list(ex.map(self._fetch_body, urls))
            for it, body in zip(all_items, bodies):
                if body:
                    it.content = body
        return all_items[:limit]

    def _fetch_body(self, url: Optional[str], timeout: int = 12) -> Optional[str]:
        """抓单条新闻正文。失败/超时返回 None，不阻断主流程。

        apparent_encoding 修 requests 把 UTF-8 当 latin-1 解出的乱码（财联社响应头没带 charset）。
        """
        if not url:
            return None
        try:
            resp = requests.get(url, headers=_FETCH_HEADERS, timeout=timeout)
            if resp.status_code != 200:
                return None
            resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
            text = resp.text
            text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.S | re.I)
            text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.S | re.I)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text or None
        except Exception:
            return None
