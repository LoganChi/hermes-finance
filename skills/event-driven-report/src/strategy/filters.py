"""策略三重过滤条件。

组合已有工具(trend.macd + 竞价分析 + 涨幅检查)，从 watch_pool 筛选高质量信号。
返回 (通过?, 原因)：True=通过，False=拒绝，None=数据不足(不卡，放过)。
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

import pandas as pd

from src.trend.macd import analyze as macd_analyze


def filter_macd_buy_point(code: str, df: pd.DataFrame) -> Tuple[Optional[bool], str]:
    """① MACD柱状图拐点过滤：只在"绿衰竭转红/二红启动"的动量反转拐点买。
    不追多头高位（那是延续非拐点），避空头下坡。比"零轴多头"更精准——抓启动点而非追涨。
    """
    from src.trend.macd import calc_macd, detect_bar_turn
    if df is None or len(df) < 35:
        return None, "MACD数据不足"
    try:
        _, _, bar = calc_macd(df)
        r = detect_bar_turn(bar)
    except Exception:
        return None, "MACD计算失败"
    sig = r["signal"]
    if "买点" in sig:
        return True, f"MACD{sig}"
    if "卖点" in sig:
        return False, f"MACD{sig}"
    return False, f"MACD{sig}"


def filter_auction_confirmed(
    code: str, df: pd.DataFrame, event_date: str,
    confirm_gap: float = 0.03, confirm_vol: float = 2.0,
    high_open_warn: float = 0.07, avg_n: int = 5,
) -> Tuple[Optional[bool], str]:
    """② 竞价资金确认：事件日后第一交易日开盘 高开+放量 才买。高开过多=接盘风险拒绝。"""
    if df is None or len(df) < avg_n + 2:
        return None, "竞价数据不足"
    df2 = df.copy()
    df2["d8"] = df2["日期"].astype(str).str.replace("-", "")
    ed = str(event_date).replace("-", "")
    after_idx = df2.index[df2["d8"] >= ed]
    if len(after_idx) == 0:
        return None, "事件日后无数据"
    i = after_idx[0]
    if i < 1:
        return None, "无前收"
    row = df2.iloc[i]
    prev = df2.iloc[i - 1]
    gap = (float(row["开盘"]) - float(prev["收盘"])) / float(prev["收盘"])
    avg_vol = float(df2["成交量"].iloc[max(0, i - avg_n):i].mean())
    vr = float(row["成交量"]) / avg_vol if avg_vol else 0.0
    if gap >= high_open_warn:
        return False, f"高开过多{gap*100:.0f}%(接盘)"
    if gap >= confirm_gap and vr >= confirm_vol:
        return True, f"资金确认(高开{gap*100:.0f}% 量比{vr:.1f})"
    if gap >= confirm_gap:
        return True, f"高开{gap*100:.0f}%(量一般)"
    return False, f"竞价未确认(高开{gap*100:.0f}%)"


def filter_not_overextended(
    code: str, df: pd.DataFrame, event_date: str,
    threshold: float = 0.20, lookback: int = 10,
) -> Tuple[Optional[bool], str]:
    """③ 避利好兑现：事件日前 lookback 日涨幅 < threshold。已大涨=price in，不追。"""
    if df is None:
        return None, "数据缺失"
    df2 = df.copy()
    df2["d8"] = df2["日期"].astype(str).str.replace("-", "")
    ed = str(event_date).replace("-", "")
    before = df2[df2["d8"] < ed]
    if len(before) < lookback + 1:
        return True, "历史不足(放过)"
    recent = before.iloc[-(lookback + 1):]
    runup = (float(recent.iloc[-1]["收盘"]) - float(recent.iloc[0]["收盘"])) / float(recent.iloc[0]["收盘"])
    if runup >= threshold:
        return False, f"事件前{lookback}日涨{runup*100:.0f}%(兑现)"
    return True, f"事件前未大涨({runup*100:.0f}%)"
