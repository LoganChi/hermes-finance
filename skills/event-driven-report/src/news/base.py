"""新闻层基础数据结构与抽象基类 —— 全系统的接口地基。

设计原则：
- 本系统是"事件驱动映射"系统，绝不预测股价。本文件只负责新闻数据标准化，不做任何涨跌判断。
- 适配器模式：所有新闻源（demo / newsnow / 未来真实API）最终都产出统一的 NewsItem。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    """标准化新闻条目。"""

    id: str = Field(..., description="唯一ID，用于去重")
    source: str = Field("unknown", description="来源标识，如 demo/newsnow")
    fetched_at: datetime = Field(..., description="抓取时间")
    published_at: Optional[datetime] = Field(None, description="新闻发布时间")
    title: str = Field(..., description="标题")
    content: Optional[str] = Field(None, description="正文（可选）")
    url: Optional[str] = Field(None, description="链接")


class NewsSource(ABC):
    """新闻源抽象基类。子类实现 fetch()。"""

    name: str = "base"

    @abstractmethod
    def fetch(self, limit: int = 20) -> List[NewsItem]:
        """拉取最多 limit 条新闻，返回标准化的 NewsItem 列表。"""
        raise NotImplementedError
