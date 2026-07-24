"""大盘择时指标族（十指标可计算子集）。

纯 OHLCV+成交额，不依赖期权/分钟。
借鉴华泰证券《A股择时之技术打分体系》+ stock_datasource 实现。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------- 价格维度 ----------
def bias(close: pd.Series, n: int = 20) -> pd.Series:
    """n日乖离率 = (close - MA_n) / MA_n"""
    ma = close.rolling(n).mean()
    return (close - ma) / ma


def bollinger_pctb(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.Series:
    """布林带 %B（>1 破上轨, <0 破下轨）。"""
    ma = close.rolling(n).mean()
    sd = close.rolling(n).std()
    upper, lower = ma + k * sd, ma - k * sd
    return (close - lower) / (upper - lower)


# ---------- 趋势维度 ----------
def calc_adx(df: pd.DataFrame, period: int = 14) -> tuple:
    """Wilder ADX。返回 (adx_series, plus_di, minus_di)。

    df 需含 最高/最低/收盘 列。
    """
    high = df["最高"].astype(float)
    low = df["最低"].astype(float)
    close = df["收盘"].astype(float)
    up = high.diff()
    dn = -low.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    s_plus = pd.Series(plus_dm, index=close.index).ewm(alpha=1 / period, adjust=False).mean()
    s_minus = pd.Series(minus_dm, index=close.index).ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * s_plus / atr.replace(0, np.nan)
    minus_di = 100 * s_minus / atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_val = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx_val, plus_di, minus_di


def new_high_ratio(close: pd.Series, lookback: int = 20, win: int = 20) -> float:
    """过去 lookback 日中收盘创 win 日新高的天数占比 ∈ [0,1]。"""
    cnt = 0
    total = 0
    for i in range(max(win, len(close) - lookback), len(close)):
        total += 1
        if close.iloc[i] >= close.iloc[i - win: i].max():
            cnt += 1
    return cnt / total if total > 0 else 0.0


# ---------- 波动维度 ----------
def ret_vol(close: pd.Series, n: int = 60) -> float:
    """n日收益率标准差。"""
    val = close.pct_change().rolling(n).std().iloc[-1]
    return float(val) if not pd.isna(val) else 0.02


# ---------- 量能维度（换手率替代） ----------
def amount_bias(df: pd.DataFrame, n: int = 20) -> float:
    """成交额乖离 = 今日成交额 / MA(成交额, n) - 1。"""
    col = "成交额" if "成交额" in df.columns else "成交量"
    a = df[col].astype(float)
    ma = a.iloc[-n - 1: -1].mean()
    return float(a.iloc[-1] / ma - 1) if ma else 0.0
