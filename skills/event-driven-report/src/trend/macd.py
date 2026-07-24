"""MACD 趋势分析（独立通用工具）。

DIF = EMA(close,12) - EMA(close,26)
DEA = EMA(DIF,9)
MACD柱 = (DIF - DEA) * 2

信号：零轴多空 / 金叉死叉 / 顶底背离 / 柱状动能。

⚠️ 铁律：MACD 是滞后指标，本模块只输出客观趋势状态，不预测股价精确点位，
不应单独作为进出场理由——应与事件信号/基本面结合使用。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


def calc_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9):
    """计算 DIF / DEA / MACD柱。df 需含 '收盘' 列。"""
    close = df["收盘"].astype(float)
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd_bar = (dif - dea) * 2
    return dif, dea, macd_bar


def detect_bar_turn(macd_bar: pd.Series, deep_green: float = -0.3) -> Dict[str, Any]:
    """柱状图波段拐点检测（动量反转视角）。

    把 BAR 当"小山坡"：绿柱=下坡(空方动量)，红柱=上坡(多方动量)。
    - 买点①：绿柱衰竭转红（前续≥2根绿柱 或 1根深绿=下跌释放充分，最新BAR由负转正）→ 下跌末端拐点
    - 买点②：二红（红柱中再次放大，且之前已有过红柱段=第一波）→ 第二波启动
    - 卖点：红柱转绿（下坡，上涨动量衰竭）

    Args:
        macd_bar: MACD柱状图序列
        deep_green: 深绿阈值(BAR≤此值视为深绿，可按标的波动调)
    """
    n = len(macd_bar)
    if n < 5:
        return {"signal": "数据不足"}
    last = float(macd_bar.iloc[-1])
    prev = float(macd_bar.iloc[-2])

    # 买点①：绿衰竭转红
    if prev <= 0 and last > 0:
        greens = []
        i = n - 2
        while i >= 0 and float(macd_bar.iloc[i]) <= 0:
            greens.append(float(macd_bar.iloc[i]))
            i -= 1
        deep = any(g <= deep_green for g in greens)
        if len(greens) >= 2 or deep:
            return {"signal": "买点(绿衰竭转红)", "greens": len(greens), "deep_green": deep}
        return {"signal": "转红但绿柱不足(弱信号)", "greens": len(greens)}

    # 卖点：红转绿（下坡）
    if prev >= 0 and last < 0:
        return {"signal": "卖点(红转绿·下坡)"}

    # 买点②：二红（红柱中再次放大 + 之前已有红柱段）
    if last > 0 and prev > 0 and n >= 7:
        cur = 0
        i = n - 1
        while i >= 0 and float(macd_bar.iloc[i]) > 0:
            cur += 1
            i -= 1
        # i 指向当前红柱段前的绿柱；再往前找是否还有更早的红柱段(第一波)
        j = i
        while j >= 0 and float(macd_bar.iloc[j]) <= 0:
            j -= 1
        had_prev_red = j >= 0
        recent_max = float(macd_bar.iloc[max(0, n - 6):n - 1].max())
        if had_prev_red and last > prev and last >= recent_max:
            return {"signal": "买点(二红启动)", "cur_red": cur}
        return {"signal": f"红柱延续(第{cur}根,未确认二红)"}

    # 趋势延续/减弱
    if last > 0:
        return {"signal": "红柱延续" if last > prev else "红柱缩小(动能减弱)"}
    return {"signal": "绿柱延续" if last < prev else "绿柱缩小(动能减弱)"}


def _detect_cross(dif: pd.Series, dea: pd.Series, dates: pd.Series) -> Dict[str, Any]:
    """最近一次金叉/死叉。"""
    for i in range(len(dif) - 1, 0, -1):
        if dif.iloc[i] > dea.iloc[i] and dif.iloc[i - 1] <= dea.iloc[i - 1]:
            return {"type": "金叉", "date": str(dates.iloc[i]), "days_ago": len(dif) - 1 - i}
        if dif.iloc[i] < dea.iloc[i] and dif.iloc[i - 1] >= dea.iloc[i - 1]:
            return {"type": "死叉", "date": str(dates.iloc[i]), "days_ago": len(dif) - 1 - i}
    return {"type": "近期无明显交叉", "date": None, "days_ago": None}


def _detect_divergence(price: pd.Series, dif: pd.Series, window: int = 30) -> str:
    """简化背离检测：window 内价格创新低/高但 DIF 未同步。"""
    if len(price) < window:
        return "无"
    p_win = price.iloc[-window:]
    d_win = dif.iloc[-window:]
    p_min_idx = p_win.idxmin()
    p_max_idx = p_win.idxmax()
    last_p, last_d = price.iloc[-1], dif.iloc[-1]
    # 底背离：期间有比最近更低的低点，但该点 DIF 高于最近 DIF（动能未新低）
    if p_min_idx != price.index[-1] and last_p <= p_win.min() * 1.01 and d_win.loc[p_min_idx] < last_d:
        return "底背离（潜在反弹）"
    if p_max_idx != price.index[-1] and last_p >= p_win.max() * 0.99 and d_win.loc[p_max_idx] > last_d:
        return "顶背离（潜在见顶）"
    return "无"


def analyze(code: str, df: Optional[pd.DataFrame] = None, fetch_fn=None) -> Dict[str, Any]:
    """对单标的做 MACD 趋势分析。

    Args:
        code: 股票代码
        df: 已有日K（含'收盘'列）；为 None 则用 fetch_fn 拉取
        fetch_fn: 拉日K的函数，默认 src.auction.fetcher.fetch_recent
    Returns:
        {code, last_date, dif, dea, macd_bar, zero_axis, cross, divergence, momentum, summary}
    """
    if df is None:
        if fetch_fn is None:
            from src.auction.fetcher import fetch_recent
            fetch_fn = fetch_recent
        import time
        last = None
        for _ in range(3):
            try:
                df = fetch_fn(code)
                break
            except Exception as e:  # noqa: PERF203 东财限流/断连重试
                last = e
                time.sleep(1.5)
        else:
            return {"code": code, "error": f"取数失败:{type(last).__name__}"}
    if df is None or len(df) < 35:
        return {"code": code, "error": "日K不足（需≥35根）"}

    df = df.reset_index(drop=True)
    dif, dea, macd_bar = calc_macd(df)
    dates = df["日期"]
    last_i = len(df) - 1
    last_dif, last_dea = float(dif.iloc[last_i]), float(dea.iloc[last_i])
    last_bar = float(macd_bar.iloc[last_i])
    last_date = str(dates.iloc[last_i])

    # 零轴
    if last_dif > 0 and last_dea > 0:
        zero_axis = "多头（零轴上方）"
    elif last_dif < 0 and last_dea < 0:
        zero_axis = "空头（零轴下方）"
    else:
        zero_axis = "零轴附近（多空转换中）"

    cross = _detect_cross(dif, dea, dates)
    divergence = _detect_divergence(df["收盘"].astype(float), dif)

    # 柱状动能
    if last_bar > 0 and last_bar > float(macd_bar.iloc[last_i - 1]):
        momentum = "红柱放大（多头动能增强）"
    elif last_bar > 0:
        momentum = "红柱缩小（多头动能减弱）"
    elif last_bar < 0 and last_bar < float(macd_bar.iloc[last_i - 1]):
        momentum = "绿柱放大（空头动能增强）"
    else:
        momentum = "绿柱缩小（空头动能减弱）"

    summary = f"{zero_axis}｜{cross['type']}｜{momentum}"
    if divergence != "无":
        summary += f"｜⚠️{divergence}"

    return {
        "code": code,
        "last_date": last_date,
        "dif": round(last_dif, 3),
        "dea": round(last_dea, 3),
        "macd_bar": round(last_bar, 3),
        "zero_axis": zero_axis,
        "cross": cross,
        "divergence": divergence,
        "momentum": momentum,
        "summary": summary,
    }
