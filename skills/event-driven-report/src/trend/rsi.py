"""RSI(相对强弱指数)—— 借鉴 stock_datasource 的 _calc_rsi 实现。

RSI>70 超买(短期可能回调, 不追); RSI<30 超卖(可能反弹)。
用于买入过滤: 超买时不追高, 提升胜率。
"""
from __future__ import annotations
import pandas as pd


def calc_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """计算RSI。边界处理完善(全涨/全跌场景)。"""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    import numpy as np
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def latest_rsi(prices: pd.Series, period: int = 14) -> float:
    """取最新RSI值。"""
    rsi = calc_rsi(prices, period)
    val = rsi.iloc[-1]
    return float(val) if not pd.isna(val) else 50.0
