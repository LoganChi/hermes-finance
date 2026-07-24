"""多维度择时打分系统（替代 market_state 的 bull/range/bear 三态）。

7指标等权合成分 → [-1,+1] → 仓位矩阵 → 总仓位/进攻/防御/现金。
借鉴华泰证券十指标框架，简化为日线可计算的7项。

核心解决：5月震荡市被旧系统误判为 bull(满仓)，新系统用多维度打分正确识别为"中性"(50%仓位,15%进攻)。
"""
from __future__ import annotations

from typing import Any, Callable, Dict

import numpy as np
import pandas as pd

from src.trend.timing import (
    amount_bias,
    bias,
    calc_adx,
    new_high_ratio,
    ret_vol,
)

# 按 date 缓存
_TIMING_CACHE: Dict[str, dict] = {}

# 仓位矩阵：(score_min, total, attack, defense, cash, regime)
_POSITION_MATRIX = [
    (0.40, 0.80, 0.24, 0.56, 0.20, "强势"),
    (0.14, 0.65, 0.20, 0.45, 0.35, "偏多"),
    (-0.14, 0.50, 0.15, 0.35, 0.50, "中性"),
    (-0.40, 0.30, 0.05, 0.25, 0.70, "偏空"),
    (-9.99, 0.20, 0.00, 0.20, 0.80, "弱势"),
]


def calc_timing_score(date: str, fetch_index_fn: Callable) -> Dict[str, Any]:
    """7指标择时打分 → 仓位矩阵。按 date 缓存。

    返回:
        {"score": float, "regime": str, "total_cap": float, "attack": float,
         "defense": float, "cash": float, "signals": {各指标z分}}
    """
    if date in _TIMING_CACHE:
        return _TIMING_CACHE[date]

    default = {"score": 0.0, "regime": "中性", "total_cap": 0.50,
               "attack": 0.15, "defense": 0.35, "cash": 0.50,
               "signals": {}, "state": "range", "position_cap": 0.50,
               "threshold": 7, "sell_mode": "fast", "max_hold": 10, "only_type": None}

    try:
        df = fetch_index_fn("000300")
        if df is None or len(df) < 65:
            _TIMING_CACHE[date] = default
            return default
        df = df.copy().reset_index(drop=True)
        df["d8"] = df["日期"].astype(str).str.replace("-", "")
        ed = str(date).replace("-", "")
        idx_arr = df.index[df["d8"] >= ed]
        if len(idx_arr) == 0:
            _TIMING_CACHE[date] = default
            return default
        i = idx_arr[0]
        sub = df.iloc[: i + 1]
        close = sub["收盘"].astype(float)

        # ① 价格：BIAS20
        b = float(bias(close, 20).iloc[-1]) if len(close) >= 20 else 0.0
        z_bias = float(np.clip(b / 0.05, -1, 1))  # ±5% 满档

        # ② 趋势：ADX
        adx_val, plus_di, minus_di = calc_adx(sub, 14)
        adx_last = float(adx_val.iloc[-1]) if not pd.isna(adx_val.iloc[-1]) else 15.0
        pdi = float(plus_di.iloc[-1]) if not pd.isna(plus_di.iloc[-1]) else 20.0
        mdi = float(minus_di.iloc[-1]) if not pd.isna(minus_di.iloc[-1]) else 20.0
        di_sign = 1.0 if pdi > mdi else -1.0
        z_adx = float(np.clip((adx_last - 20) / 15, -1, 1)) * di_sign  # ADX>20 有趋势, 方向看DI

        # ③ 创新高占比
        nh = new_high_ratio(close, 20, 20)
        z_nh = float(np.clip((nh - 0.15) / 0.20, -1, 1))  # 15% 中性

        # ④ 波动率（反向：低波=稳=看多）
        v60 = ret_vol(close, 60)
        z_vol = float(np.clip(-(v60 - 0.012) / 0.008, -1, 1))  # 1.2% 基准

        # ⑤ 动量
        mom_20 = float(close.iloc[-1] / close.iloc[-21] - 1) if len(close) >= 21 else 0.0
        z_mom = float(np.clip(mom_20 / 0.05, -1, 1))  # ±5% 满档

        # ⑥ 量能趋势
        ab = amount_bias(sub, 20)
        z_amt = float(np.clip(ab / 0.30, -1, 1))  # ±30% 满档

        # ⑦ 均线趋势（MA20 vs MA60，保留旧逻辑兼容）
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean()
        z_ma = 0.0
        if not pd.isna(ma20.iloc[-1]) and not pd.isna(ma60.iloc[-1]):
            z_ma = 1.0 if ma20.iloc[-1] > ma60.iloc[-1] else -1.0

        # 合成分（等权）
        signals = {"bias": z_bias, "adx": z_adx, "nh": z_nh, "vol": z_vol,
                   "mom": z_mom, "amt": z_amt, "ma": z_ma}
        valid_zs = [v for v in signals.values() if not np.isnan(v)]
        score = sum(valid_zs) / len(valid_zs) if valid_zs else 0.0
        score = float(np.clip(score, -1, 1))

        # 仓位矩阵
        result = _score_to_position(score)
        result["score"] = round(score, 3)
        result["signals"] = {k: round(v, 2) for k, v in signals.items()}
        # 兼容旧字段
        result["state"] = result["regime"]
        result["position_cap"] = result["attack"]  # 用 attack 作为 position_cap
        result["mom_20"] = round(mom_20, 3)
        result["vol_ratio"] = round(ab, 2)

        _TIMING_CACHE[date] = result
        return result
    except Exception:
        _TIMING_CACHE[date] = default
        return default


def _score_to_position(score: float) -> Dict[str, Any]:
    """得分 → 仓位矩阵档位。"""
    for lo, tot, att, de, cash, name in _POSITION_MATRIX:
        if score >= lo:
            threshold = 5 if score > 0.40 else (7 if score > 0.14 else (9 if score > -0.14 else 12))
            sell_mode = "trailing" if score > 0.14 else "fast"
            max_hold = 15 if score > 0.40 else (10 if score > 0.14 else 7)
            only_type = None  # 不限制票型，用 threshold 控制
            return {"regime": name, "total_cap": tot, "attack": att,
                    "defense": de, "cash": cash,
                    "threshold": threshold, "sell_mode": sell_mode,
                    "max_hold": max_hold, "only_type": only_type}
    return {"regime": "弱势", "total_cap": 0.20, "attack": 0.0,
            "defense": 0.20, "cash": 0.80,
            "threshold": 12, "sell_mode": "fast", "max_hold": 3, "only_type": None}
