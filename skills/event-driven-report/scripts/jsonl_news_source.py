"""JsonlNewsSource —— 把本地 jsonl 历史新闻接入 pipeline。

每行一个 json dict，按字段映射成 NewsItem。用于 wallstreetcn_q1.jsonl 这类
已抓取的快照数据（项目无现成 jsonl→NewsItem 适配器）。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from src.news.base import NewsItem, NewsSource


class JsonlNewsSource(NewsSource):
    name = "jsonl"

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.path = self.config.get("path", "")
        self.source_tag = self.config.get("source_tag", "jsonl")
        self.title_key = self.config.get("title_key", "title")
        self.content_key = self.config.get("content_key", "content_text")
        self.ts_key = self.config.get("ts_key", "ts")  # unix 秒级时间戳

    def fetch(self, limit: int = 50) -> List[NewsItem]:
        if not self.path or not Path(self.path).exists():
            print(f"[warn] jsonl 文件不存在: {self.path}")
            return []
        out: List[NewsItem] = []
        seen: set = set()
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                if len(out) >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                title = str(d.get(self.title_key) or "").strip()
                if not title or title in seen:  # 跳过空标题 + 同标题去重
                    continue
                seen.add(title)
                content = d.get(self.content_key)
                ts = d.get(self.ts_key)
                published = None
                if ts:
                    try:
                        published = datetime.fromtimestamp(int(ts))
                    except Exception:
                        published = None
                out.append(NewsItem(
                    id=f"ws_{ts}" if ts else f"ws_{len(out)}",
                    source=self.source_tag,
                    fetched_at=datetime.now(),
                    published_at=published,
                    title=title,
                    content=str(content) if content else None,
                    url=None,
                ))
        return out
