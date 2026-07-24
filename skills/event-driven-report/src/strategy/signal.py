"""组合三重过滤，产出高质量买入信号。"""
from __future__ import annotations

import time
from typing import Callable, List, Tuple

from src.strategy.filters import (
    filter_auction_confirmed,
    filter_macd_buy_point,
    filter_not_overextended,
)


def build_signals(
    codes: List[str],
    event_date: str,
    fetch_fn: Callable = None,
    retries: int = 3,
) -> Tuple[List[Tuple[str, dict]], List[Tuple[str, dict]]]:
    """对 watch_pool 做三重过滤，返回 (passed, rejected)，每项 (code, 原因dict)。

    通过规则：三重都非 False（True 或 None[数据不足放过]）。
    """
    if fetch_fn is None:
        from src.auction.fetcher import fetch_recent
        fetch_fn = fetch_recent

    passed: List[Tuple[str, dict]] = []
    rejected: List[Tuple[str, dict]] = []
    for code in codes:
        df = None
        for _ in range(retries):
            try:
                df = fetch_fn(code)
                break
            except Exception:  # noqa: PERF203 东财限流重试
                time.sleep(1.0)
        if df is None:
            rejected.append((code, {"error": "取数失败"}))
            continue
        m, mw = filter_macd_buy_point(code, df)
        a, aw = filter_auction_confirmed(code, df, event_date)
        o, ow = filter_not_overextended(code, df, event_date)
        rec = {"macd": mw, "auction": aw, "overext": ow}
        ok = (m is not False) and (a is not False) and (o is not False)
        (passed if ok else rejected).append((code, rec))
    return passed, rejected
