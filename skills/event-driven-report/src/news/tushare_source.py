"""TushareNewsSource —— 可插拔新闻源之一（tushare news 接口）。

⚠️ 已知限制：tushare `news` 接口需独立付费权限；`news_fast` 在第三方代理(stockai888)下返回空。
当前若不可用会抛清晰错误，建议：换官方 tushare token(开通 news 权限) 或用 newsnow/file/demo 源。

设计：继承 NewsSource，与 DemoNewsSource/NewsnowSource 并列，通过 settings.news.source 切换。
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, List

from .base import NewsItem, NewsSource


class TushareNewsSource(NewsSource):
    name = "tushare"

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self._pro = None
        try:
            import tushare as ts
            token = str(self.config.get("token", ""))
            token = re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), token)
            if not token:
                token = os.environ.get("TUSHARE_TOKEN", "")
            if token:
                ts.set_token(token)
                self._pro = ts.pro_api()
                srv = self.config.get("api_server", "")
                if srv:
                    try:
                        self._pro._DataApi__http_url = srv
                    except Exception:
                        pass
        except Exception:
            self._pro = None

    def fetch(self, limit: int = 20) -> List[NewsItem]:
        if self._pro is None:
            raise RuntimeError("tushare 未配置 token (设 TUSHARE_TOKEN)")
        last = "无可用接口"
        for api, kw in [("news_fast", {}), ("news", {"src": "sina"})]:
            try:
                df = getattr(self._pro, api)(**kw)
                if df is not None and len(df) > 0:
                    return [self._row_to_item(r) for r in df.head(limit).to_dict("records")]
                last = f"{api} 返回空"
            except Exception as e:
                last = f"{api}: {str(e)[:80]}"
        raise RuntimeError(
            f"tushare news 不可用({last})。需官方 token + news 付费权限，或换 newsnow/file/demo 源。"
        )

    @staticmethod
    def _row_to_item(row: Dict[str, Any]) -> NewsItem:
        return NewsItem(
            id=str(row.get("title", ""))[:30] or str(row.get("datetime", "")),
            source="tushare",
            fetched_at=datetime.now(),
            title=str(row.get("title", "")),
            content=row.get("content"),
            url=row.get("url"),
        )
