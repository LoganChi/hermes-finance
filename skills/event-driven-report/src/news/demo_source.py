"""演示用内置新闻源 —— 从 data/demo_news.json 读取示例新闻。

设计原则：
- 本系统绝不预测股价。示例 title 仅描述事件事实本身，不含涨跌/买卖/目标价判断。
- 样本放在配置文件里，便于不改代码增删/修改示例新闻。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from .base import NewsItem, NewsSource


class DemoNewsSource(NewsSource):
    """内置示例新闻源。样本来自配置(data/demo_news.json)。"""

    name = "demo"

    def __init__(self, samples: List[Dict[str, Any]]):
        """
        Args:
            samples: 示例新闻列表，每项 {id, title, content, [url]}
        """
        self._samples: List[Dict[str, Any]] = samples or []

    def fetch(self, limit: int = 20) -> List[NewsItem]:
        now = datetime.now()
        items = self._samples if not limit else self._samples[:limit]
        out: List[NewsItem] = []
        for d in items:
            out.append(NewsItem(
                id=str(d.get("id", "")),
                source="demo",
                fetched_at=now,
                published_at=now,
                title=str(d.get("title", "")),
                content=d.get("content"),
                url=d.get("url"),
            ))
        return out
