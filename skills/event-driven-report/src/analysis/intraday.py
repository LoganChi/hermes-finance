"""分钟级日内分析 —— 用分钟K线判断MACD拐点当天是"真资金进场"还是"假反弹"。

核心指标：
1. 早盘动量(09:30-10:00): 前30分钟涨幅, 正=真买盘
2. VWAP位置: 收盘 vs 日内VWAP, 上方=日内强势
3. 量价配合: 涨时均量 vs 跌时均量, 涨时放量=主力进场
4. 尾盘表现(14:30-15:00): 尾盘走强=次日大概率延续

铁律：不预测股价，只客观描述日内资金行为。
"""
from __future__ import annotations

from typing import Any, Dict

import pandas as pd


def analyze_intraday(min_df: pd.DataFrame) -> Dict[str, Any]:
    """分析一根日K的分钟数据 → 日内资金行为指标。

    Args:
        min_df: 分钟K线(trade_time/open/high/low/close/vol/amount)
    Returns:
        {morning_ret, vwap_pct, vol_up_ratio, tail_ret, intraday_score}
        intraday_score ∈ [-1,+1]: 正=真资金进场, 负=假反弹/出货
    """
    if min_df is None or len(min_df) < 10:
        return {"intraday_score": 0.0, "morning_ret": 0.0, "vwap_pct": 0.0,
                "vol_up_ratio": 1.0, "tail_ret": 0.0, "n_bars": 0}

    df = min_df.copy()
    df["trade_time"] = pd.to_datetime(df["trade_time"])
    df = df.sort_values("trade_time").reset_index(drop=True)
    n = len(df)

    # ① 早盘动量(前30分钟 ≈ 前3根1分钟或前6根5分钟)
    morning_n = min(6, n)  # 前6根分钟K(约30分钟)
    open_price = float(df.iloc[0]["open"])
    morning_close = float(df.iloc[morning_n - 1]["close"])
    morning_ret = (morning_close - open_price) / open_price if open_price else 0.0

    # ② VWAP位置
    total_amount = float(df["amount"].sum())
    total_vol = float(df["vol"].sum())
    vwap = total_amount / total_vol / 100 if total_vol > 0 else float(df.iloc[-1]["close"])
    day_close = float(df.iloc[-1]["close"])
    vwap_pct = (day_close - vwap) / vwap if vwap else 0.0

    # ③ 量价配合：涨时均量 vs 跌时均量
    df["ret"] = df["close"].diff()
    up_vol = df[df["ret"] > 0]["vol"].mean() if len(df[df["ret"] > 0]) > 0 else 0
    dn_vol = df[df["ret"] < 0]["vol"].mean() if len(df[df["ret"] < 0]) > 0 else 1
    vol_up_ratio = float(up_vol / dn_vol) if dn_vol > 0 else 1.0

    # ④ 尾盘表现(最后30分钟)
    tail_n = min(6, n)
    tail_start = float(df.iloc[n - tail_n]["open"])
    tail_end = float(df.iloc[-1]["close"])
    tail_ret = (tail_end - tail_start) / tail_start if tail_start else 0.0

    # 综合日内得分 [-1, +1]
    import numpy as np
    s_morning = float(np.clip(morning_ret / 0.02, -1, 1))    # ±2% 满档
    s_vwap = float(np.clip(vwap_pct / 0.01, -1, 1))          # ±1% 满档
    s_vol = float(np.clip((vol_up_ratio - 1) / 0.5, -1, 1))  # 1.5倍满档
    s_tail = float(np.clip(tail_ret / 0.01, -1, 1))          # ±1% 满档
    intraday_score = (s_morning + s_vwap + s_vol + s_tail) / 4

    return {
        "intraday_score": round(intraday_score, 3),
        "morning_ret": round(morning_ret, 4),
        "vwap_pct": round(vwap_pct, 4),
        "vol_up_ratio": round(vol_up_ratio, 2),
        "tail_ret": round(tail_ret, 4),
        "n_bars": n,
        "vwap": round(vwap, 2),
    }
