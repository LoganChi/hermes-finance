"""市场状态识别 + 动态策略建议（regime-switching 自适应）。

多层识别：
- 中期(20-60天): 沪深300 趋势(MA20/MA60) + 动量(20日涨幅) + 波动率(20日std)
- 当日: 量比 + 竞价(开盘 vs 昨收)
→ 状态(bull/range/bear) → 三维建议(仓位上限/评分门槛/卖点模式)

让策略动态适配市场：
- bull  满仓激进(门槛低、追踪止盈让利润跑)
- range 半仓快进快出(门槛中、红转绿快卖)
- bear  空仓回避(门槛高/不买、不入场)

铁律：不预测股价，只识别客观市场状态。
"""
from __future__ import annotations

from typing import Any, Callable, Dict

import pandas as pd

# 按 date 缓存市场状态（事件级算一次）
_STATE_CACHE: Dict[str, dict] = {}


def assess_market(
    date: str, fetch_index_fn: Callable,
    lookback_mom: int = 20, lookback_trend: int = 60,
) -> Dict[str, Any]:
    """识别市场状态 → 三维建议(仓位/门槛/卖点)。缓存按 date。"""
    if date in _STATE_CACHE:
        return _STATE_CACHE[date]
    default = {
        "state": "unknown", "position_cap": 0.5, "threshold": 7, "sell_mode": "fast",
        "trend_up": None, "mom_20": None, "vol_ratio": None, "vol_std": None, "gap": None,
    }
    try:
        df = fetch_index_fn("000300")
        if df is None or len(df) < lookback_trend + 5:
            _STATE_CACHE[date] = default
            return default
        df = df.copy().reset_index(drop=True)
        df["d8"] = df["日期"].astype(str).str.replace("-", "")
        ed = str(date).replace("-", "")
        idx_arr = df.index[df["d8"] >= ed]
        if len(idx_arr) == 0:
            _STATE_CACHE[date] = default
            return default
        i = idx_arr[0]
        close = df["收盘"].astype(float)
        vol = df["成交量"].astype(float)

        # ① 中期趋势：MA20 vs MA60
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(lookback_trend).mean()
        if pd.isna(ma20.iloc[i]) or pd.isna(ma60.iloc[i]):
            _STATE_CACHE[date] = default
            return default
        trend_up = bool(ma20.iloc[i] > ma60.iloc[i])

        # ② 动量：近 20 日涨幅
        mom_20 = close.iloc[i] / close.iloc[max(0, i - lookback_mom)] - 1

        # ③ 波动率：近 20 日收益率 std
        rets = close.pct_change().iloc[max(0, i - 20): i + 1]
        vol_std = rets.std()
        vol_std = float(vol_std) if not pd.isna(vol_std) else None

        # ④ 当日量比
        avg_vol = vol.iloc[max(0, i - 20): i].mean()
        vol_ratio = float(vol.iloc[i]) / float(avg_vol) if avg_vol else 0.0

        # ⑤ 当日竞价（沪深300 开盘 vs 昨收）
        gap = 0.0
        if "开盘" in df.columns and i >= 1:
            prev_close = close.iloc[i - 1]
            if prev_close:
                gap = (float(df["开盘"].iloc[i]) - float(prev_close)) / float(prev_close)

        # 状态判定
        if trend_up and mom_20 > 0.02 and (vol_std is None or vol_std < 0.025):
            state = "bull"
        elif (not trend_up) and mom_20 < -0.02:
            state = "bear"
        else:
            state = "range"
        # 高波动牛市 → 降级震荡（不稳）
        if state == "bull" and vol_std is not None and vol_std > 0.03:
            state = "range"
        # 放量跳水（当日大跌+放量）→ bear 警报
        if gap < -0.02 and vol_ratio > 1.5 and state != "bear":
            state = "range"

        # 三维建议
        cfg = {
            "bull":  {"position_cap": 1.0, "threshold": 5,  "sell_mode": "trailing", "max_hold": 15, "only_type": None},
            "range": {"position_cap": 0.5, "threshold": 7,  "sell_mode": "fast",    "max_hold": 5,  "only_type": "超跌"},
            "bear":  {"position_cap": 0.0, "threshold": 10, "sell_mode": "fast",   "max_hold": 3,  "only_type": None},
        }[state]
        result = {
            "state": state,
            "trend_up": trend_up,
            "mom_20": round(float(mom_20), 3),
            "vol_ratio": round(vol_ratio, 2),
            "vol_std": round(vol_std, 4) if vol_std is not None else None,
            "gap": round(gap, 4),
            **cfg,
        }
        _STATE_CACHE[date] = result
        return result
    except Exception:
        return default
