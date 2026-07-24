"""市场风控：沪深300 vs MA250 → normal/warning/danger。

danger 时空仓（不买入），warning 谨慎，normal 正常。
借鉴 stock_datasource 的 MarketRisk 哨兵（大盘趋势决定仓位）。
铁律：不预测股价，只判大盘客观状态。
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

# 按 date 缓存大盘状态（事件级算一次）
_REGIME_CACHE: dict = {}


def market_regime(
    date: str, fetch_index_fn: Callable, lookback: int = 250,
    warn_dev: float = 0.0, danger_dev: float = -0.05,
) -> str:
    """沪深300 close vs MA250 的偏离 → normal/warning/danger。

    normal: close 在 MA250 上方（dev>=0）
    warning: close 略低于 MA250（-5%<=dev<0）
    danger: close 跌破 MA250 5%+（dev<-5%）→ 空仓
    """
    if date in _REGIME_CACHE:
        return _REGIME_CACHE[date]
    try:
        df = fetch_index_fn("000300")
        if df is None or len(df) < lookback + 1:
            _REGIME_CACHE[date] = "normal"
            return "normal"
        df = df.copy().reset_index(drop=True)
        df["d8"] = df["日期"].astype(str).str.replace("-", "")
        ed = str(date).replace("-", "")
        idx_arr = df.index[df["d8"] >= ed]
        if len(idx_arr) == 0:
            _REGIME_CACHE[date] = "normal"
            return "normal"
        i = idx_arr[0]
        close = df["收盘"].astype(float)
        ma = close.rolling(lookback).mean()
        if pd.isna(ma.iloc[i]):
            _REGIME_CACHE[date] = "normal"
            return "normal"
        dev = (close.iloc[i] - ma.iloc[i]) / ma.iloc[i]
        if dev >= warn_dev:
            r = "normal"
        elif dev >= danger_dev:
            r = "warning"
        else:
            r = "danger"
        _REGIME_CACHE[date] = r
        return r
    except Exception:
        return "normal"
