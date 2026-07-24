"""ATR (Average True Range) 真实波幅 —— 动态止损止盈的基础。

ATR 反映个股自身波动率：高波动股 ATR 大（止损止盈给宽，不被正常波动震飞），
低波动股 ATR 小（给窄，快速离场）。替代固定百分比止损(-8%/+15%/回撤10%)。

借鉴 stock_datasource 文档批评的"固定阈值"问题 —— ATR 让阈值自适应个股。
"""
from __future__ import annotations

import pandas as pd


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """计算 ATR（简单移动平均真实波幅）。df 需含 最高/最低/收盘。"""
    high = df["最高"].astype(float)
    low = df["最低"].astype(float)
    close = df["收盘"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def atr_stop_price(buy_price: float, atr: float, multiplier: float = 2.0) -> float:
    """ATR 动态止损价 = 买入价 - multiplier × ATR。
    高波动股 atr 大 → 止损宽（不被震飞）；低波动股 atr 小 → 止损窄。
    """
    return buy_price - multiplier * atr if atr and not pd.isna(atr) else buy_price * 0.92


def atr_trailing_exit(high_since_buy: float, atr: float, multiplier: float = 3.0) -> float:
    """ATR 追踪止盈价 = 持有期高点 - multiplier × ATR（跌破则卖，让利润跑）。
    multiplier=3：给趋势足够空间，只在真正破位时离场。
    """
    return high_since_buy - multiplier * atr if atr and not pd.isna(atr) else high_since_buy * 0.90
