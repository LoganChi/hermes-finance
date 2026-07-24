"""多因子评分体系（替代硬 AND 过滤）。

票型分类(超跌反弹/强势顺势/中间观望) → 按型加权评分 → 门槛 + 板块共振。
复用 trend.macd 的因子函数（detect_bar_turn/analyze/calc_macd）。
铁律：不预测股价，只用客观技术因子打分。
"""
from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from src.trend.macd import analyze, calc_macd, detect_bar_turn

# 票型判定阈值（从 settings.yaml 的 scoring 段读，可调）
def _load_scoring_cfg():
    try:
        import yaml as _yaml
        from pathlib import Path as _Path
        p = _Path(__file__).resolve().parents[2] / "config" / "settings.yaml"
        return (_yaml.safe_load(open(p, encoding="utf-8")) or {}).get("scoring") or {}
    except Exception:
        return {}
_SCORING_CFG = _load_scoring_cfg()
OVERSOLD_DRAWDOWN = float(_SCORING_CFG.get("oversold_drawdown", 0.35))
STRONG_DRAWDOWN = float(_SCORING_CFG.get("strong_drawdown", 0.15))

# 板块共振缓存（按 sector，事件级算一次）
_BOARD_CACHE: Dict[str, float] = {}


def classify_type(df: pd.DataFrame, i: int) -> Dict[str, Any]:
    """判定票型 + 位置/均线状态（基于到第i天的数据）。"""
    close = df["收盘"].astype(float)
    high = df["最高"].astype(float)
    lo = max(0, i - 252)
    high_1y = high.iloc[lo:i + 1].max() if i >= 0 else 0
    drawdown = (high_1y - close.iloc[i]) / high_1y if high_1y else 0
    ma5 = close.iloc[max(0, i - 4):i + 1].mean()
    ma20 = close.iloc[max(0, i - 19):i + 1].mean()
    ma60 = close.iloc[max(0, i - 59):i + 1].mean()
    bullish_ma = bool((ma5 > ma20) and (ma20 > ma60))
    if drawdown >= OVERSOLD_DRAWDOWN:
        t = "超跌"
    elif drawdown < STRONG_DRAWDOWN and bullish_ma:
        t = "强势"
    else:
        t = "中间"
    return {
        "type": t, "drawdown": round(float(drawdown), 3), "bullish_ma": bullish_ma,
        "ma5": round(float(ma5), 2), "ma20": round(float(ma20), 2), "ma60": round(float(ma60), 2),
    }


def compute_factors(code: str, df: pd.DataFrame, i: int, evt=None) -> Dict[str, Any]:
    """提取到第 i 天的所有因子（复用 detect_bar_turn / analyze）。"""
    sub = df.iloc[: i + 1]
    _, _, bar = calc_macd(sub)
    turn = detect_bar_turn(bar)
    try:
        ana = analyze(code, df=sub)
        zero_axis = ana.get("zero_axis", "")
        divergence = ana.get("divergence", "")
    except Exception:
        zero_axis = ""
        divergence = ""
    vol = df["成交量"].astype(float)
    avg_vol = vol.iloc[max(0, i - 20): i].mean()
    vol_ratio = float(vol.iloc[i]) / float(avg_vol) if (avg_vol and not pd.isna(avg_vol)) else 0
    new_high = bool(df["最高"].iloc[i] >= df["最高"].iloc[max(0, i - 20): i].max()) if i >= 1 else False
    sentiment = getattr(evt, "sentiment", "") if evt else ""
    # RPS(简化相对强度): 250日涨幅，强势型加分用
    close_all = df["收盘"].astype(float)
    rps_250 = (close_all.iloc[i] / close_all.iloc[max(0, i - 250)]) - 1 if i >= 1 else 0
    # RSI: 超买(>70)不追高
    from src.trend.rsi import latest_rsi
    rsi_val = latest_rsi(close_all.iloc[:i + 1])
    # 个股自身波动率(10日收益率std): 高波动=震荡股假信号多
    stock_vol = float(close_all.pct_change().iloc[max(0, i - 10): i + 1].std()) if i >= 10 else 0
    # 均线排列: MA5>MA10>MA20=完美短期多头排列(趋势确认)
    ma5 = close_all.iloc[max(0, i - 4): i + 1].mean()
    ma10 = close_all.iloc[max(0, i - 9): i + 1].mean()
    ma20 = close_all.iloc[max(0, i - 19): i + 1].mean()
    aligned = bool(ma5 > ma10 > ma20)
    above_ma5 = bool(close_all.iloc[i] > ma5)
    up_today = bool(close_all.iloc[i] > close_all.iloc[i - 1]) if i >= 1 else True
    return {
        "turn": turn, "zero_axis": zero_axis, "divergence": divergence,
        "vol_ratio": round(vol_ratio, 2), "new_high": new_high, "sentiment": sentiment,
        "rps_250": round(float(rps_250), 3), "rsi": round(rsi_val, 1),
        "stock_vol": round(stock_vol, 4), "aligned": aligned, "above_ma5": above_ma5,
        "up_today": up_today,
        **classify_type(df, i),
    }


def score_stock(factors: Dict[str, Any]) -> Dict[str, Any]:
    """按票型加权评分。返回 {type, total, detail}。"""
    t = factors["type"]
    s = 0
    detail = []
    turn_sig = factors["turn"].get("signal", "")

    if t == "超跌":
        if "绿衰竭转红" in turn_sig:
            if factors["turn"].get("deep_green"):
                s += 3; detail.append("底拐点深绿+3")
            else:
                s += 2; detail.append("底拐点+2")
        if "二红" in turn_sig:
            s += 2; detail.append("二红+2")
        if "底背离" in factors["divergence"]:
            s += 2; detail.append("底背离+2")
        if factors["drawdown"] >= OVERSOLD_DRAWDOWN:
            s += 2; detail.append("跌透+2")
        if factors["bullish_ma"]:
            s += 1; detail.append("均线多头+1")
        if factors["vol_ratio"] > 1.5:
            s += 1; detail.append("放量+1")
        if factors["sentiment"] == "利好":
            s += 1; detail.append("事件利好+1")
    elif t == "强势":
        # 均线排列否决: 强势型必须 MA5>MA10>MA20(趋势确认), 震荡市排列散乱直接否决
        if not factors.get("aligned", False):
            return {"type": t, "total": 0, "detail": ["均线未排列否决"]}
        if "二红" in turn_sig:
            s += 3; detail.append("二红+3")
        if "多头" in factors["zero_axis"]:
            s += 2; detail.append("零轴上方+2")
        if factors["drawdown"] < STRONG_DRAWDOWN:
            s += 2; detail.append("强势未破+2")
        if factors["bullish_ma"]:
            s += 2; detail.append("均线多头+2")
        if factors["vol_ratio"] > 1.5:
            s += 1; detail.append("放量+1")
        if factors["new_high"]:
            s += 1; detail.append("创新高+1")
        if factors["sentiment"] == "利好":
            s += 1; detail.append("事件利好+1")
        # RPS 相对强度（250日涨幅，强势型加分）
        rps = factors.get("rps_250", 0)
        if rps > 0.5:
            s += 2; detail.append("RPS强势+2")
        elif rps > 0.2:
            s += 1; detail.append("RPS+1")
    # 个股波动率过滤: 10日收益率std>0.06(6%日波动=纯赌博)一票否决
    sv = factors.get("stock_vol", 0)
    if sv > 0.06:
        return {"type": t, "total": 0, "detail": [f"波动过高否决({sv:.1%})"]}
    # "中间"型：不评分（观望）
    return {"type": t, "total": s, "detail": detail}


def build_code2sector(sector_map: dict) -> Dict[str, str]:
    """标的代码 → 所属板块（反查表）。"""
    c2s: Dict[str, str] = {}
    for sector, stocks in sector_map.items():
        for s in stocks:
            c = s.get("code") if isinstance(s, dict) else None
            if c and c not in c2s:
                c2s[c] = sector
    return c2s


def board_resonance(sector: str, sector_map: dict, fetch_fn) -> float:
    """板块成分股 MACD 多头比例(0~1) × 板块20日动量正负。

    返回值含义：
    >0: 板块多头且动量为正(趋势向上)
    =0: 板块弱或动量为负
    """
    if sector in _BOARD_CACHE:
        return _BOARD_CACHE[sector]
    stocks = sector_map.get(sector, [])
    if not stocks:
        return 0.0
    bull = 0
    n = 0
    sector_rets = []
    for s in stocks:
        code = s.get("code") if isinstance(s, dict) else None
        if not code:
            continue
        try:
            df = fetch_fn(code)
            if df is None or len(df) < 35:
                continue
            ana = analyze(code, df=df)
            if "多头" in ana.get("zero_axis", ""):
                bull += 1
            # 板块动量：个股20日涨幅
            close = df["收盘"].astype(float)
            if len(close) >= 21:
                sector_rets.append(close.iloc[-1] / close.iloc[-21] - 1)
            n += 1
        except Exception:
            continue
    bull_ratio = bull / n if n else 0.0
    # 板块平均20日动量：正=板块在上行，负=板块在跌
    sector_mom = sum(sector_rets) / len(sector_rets) if sector_rets else -0.01
    # 综合：多头比例 × (动量为正？1 : 0.5) —— 板块在跌时减半
    if sector_mom < 0:
        bull_ratio *= 0.5  # 板块下跌，即使多头比例高也打折
    _BOARD_CACHE[sector] = bull_ratio
    return bull_ratio
