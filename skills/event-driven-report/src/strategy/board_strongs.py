"""集合竞价强势股池 —— 三重过滤(竞价涨停倾向 + 最近多头 + 历史涨停)。

独立高风险池, 不混 watch_pool, 小仓位(10-20%)。只在集合竞价时算(9:15-9:25 有竞价数据)。
三重过滤缺一不可:
  1. 竞价涨停倾向: spot 涨跌幅 >= max(5%, 涨停线*0.5)
  2. 最近多头: aligned(MA5>MA10>MA20)
  3. 历史涨停: 过去一年涨停日 >=1
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

import pandas as pd

from src.auction.fetcher import fetch_recent
from src.strategy.scoring import compute_factors


def _limit_up_pct(code: str, name: str = "") -> float:
    """涨停线(按市场+ST)。主板10% / 创业(30)+科创(68)20% / 北交(4,8)30% / ST 5%。"""
    c = str(code)
    n = str(name)
    if "ST" in n or "*ST" in n:
        return 0.05
    if c[:2] in ("30", "68"):
        return 0.20
    if c[:1] in ("4", "8"):
        return 0.30
    return 0.10


def _limit_up_count(df, code: str, name: str = "") -> int:
    """过去一年涨停日数(涨幅 >= 涨停线*0.98, 容差)。"""
    if df is None or len(df) < 2:
        return 0
    pct = _limit_up_pct(code, name)
    closes = df["收盘"].astype(float)
    prev = closes.shift(1)
    chg = (closes - prev) / prev
    return int((chg >= pct * 0.98).sum())


def compute_strong_pool(codes: List[str], spot_df: pd.DataFrame,
                        fetch_fn=fetch_recent, max_workers: int = 6) -> List[Dict[str, Any]]:
    """三重过滤强势股: 竞价涨停倾向 + aligned 多头 + 历史涨停。

    第1筛(快, 用已拉 spot): 涨跌幅 >= max(5%, 涨停线*0.5)。
    第2筛(拉日K一年): aligned 且 历史涨停>=1。
    返回 [{code,name,bid_pct,limit_ups,aligned}], 按 bid_pct 降序。
    """
    if spot_df is None or len(spot_df) == 0 or "代码" not in spot_df:
        return []
    spot = spot_df[spot_df["代码"].isin(codes)].copy()
    if spot.empty:
        return []
    spot["涨跌幅"] = pd.to_numeric(spot["涨跌幅"], errors="coerce").fillna(0)

    # 第1筛: 竞价涨停倾向 + 买盘强(五档买卖比≥2)
    cands = []
    for _, r in spot.iterrows():
        code = str(r["代码"])
        name = str(r.get("名称", ""))
        thr = max(0.05, _limit_up_pct(code, name) * 0.5)
        bid_ratio = float(r.get("买卖比", 0) or 0)
        if r["涨跌幅"] >= thr * 100 and bid_ratio >= 2:  # 竞价涨幅 + 买盘堆积
            cands.append((code, name, float(r["涨跌幅"]), bid_ratio))
    if not cands:
        return []

    # 第2筛: 拉日K(一年) → aligned + 历史涨停
    def _check(t):
        code, name, bid_pct, bid_ratio = t
        try:
            df = fetch_fn(code, days=300)
            if df is None or len(df) < 60:
                return None
            i = len(df) - 1
            f = compute_factors(code, df, i)
            if not f.get("aligned"):
                return None
            lus = _limit_up_count(df, code, name)
            if lus < 1:
                return None
            return {"code": code, "name": name, "bid_pct": bid_pct,
                    "bid_ratio": round(bid_ratio, 2), "limit_ups": lus, "aligned": True}
        except Exception:
            return None

    out = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for r in ex.map(_check, cands):
            if r:
                out.append(r)
    out.sort(key=lambda x: x["bid_pct"], reverse=True)
    return out
