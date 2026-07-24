"""竞价异动分析器（里程碑3）。

用日K"开盘价"(集合竞价9:25的结果) vs 昨收，判断事件逻辑是否被资金确认。
铁律：不预测股价。只输出客观异动指标 + 风险标记（高开过多=接盘风险）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd


def analyze_auction(
    code: str,
    df: pd.DataFrame,
    target_date: Optional[str] = None,
    avg_n: int = 5,
    confirm_gap: float = 0.03,
    confirm_vol_ratio: float = 2.0,
    high_open_warning: float = 0.07,
) -> Dict[str, Any]:
    """分析 target_date 的竞价异动。

    Args:
        code: 股票代码
        df: fetcher 拉的日K
        target_date: 目标交易日(YYYY-MM-DD)，默认最近交易日
        avg_n: 量比均量窗口
        confirm_gap/confirm_vol_ratio: 资金确认阈值(高开幅度/量比)
        high_open_warning: 高开警报阈值(接盘风险)
    Returns:
        dict: code/date/open/prev_close/gap_pct/vol_ratio/turnover/signal/risk_flag
    """
    missing = {"code": code, "signal": "无数据", "risk_flag": "data_missing",
               "gap_pct": None, "vol_ratio": None}
    if df is None or len(df) < 2:
        return missing

    df = df.reset_index(drop=True)
    if target_date:
        hits = df.index[df["日期"].astype(str) == target_date].tolist()
        i = hits[0] if hits else len(df) - 1
    else:
        i = len(df) - 1
    if i < 1:
        return missing

    row = df.loc[i]
    prev_close = float(df.loc[i - 1, "收盘"])
    open_p = float(row["开盘"])
    gap_pct = (open_p - prev_close) / prev_close if prev_close else 0.0
    vol = float(row["成交量"])
    avg_vol = float(df["成交量"].iloc[max(0, i - avg_n):i].mean())
    vol_ratio = vol / avg_vol if avg_vol else 0.0
    turnover = float(row.get("换手率", 0) or 0)

    risk = "normal"
    if gap_pct >= high_open_warning:
        signal = "高开过多（接盘风险）"
        risk = "high_open_warning"
    elif gap_pct >= confirm_gap and vol_ratio >= confirm_vol_ratio:
        signal = "资金确认（高开放量）"
    elif gap_pct >= confirm_gap:
        signal = "高开（量能一般）"
    elif gap_pct <= -confirm_gap:
        signal = "低开（未确认/利空）"
    else:
        signal = "无明显异动"

    return {
        "code": code,
        "date": str(row["日期"]),
        "open": round(open_p, 2),
        "prev_close": round(prev_close, 2),
        "gap_pct": round(gap_pct * 100, 2),
        "vol_ratio": round(vol_ratio, 2),
        "turnover": round(turnover, 2),
        "signal": signal,
        "risk_flag": risk,
    }


def analyze_pool(
    codes: List[str],
    fetch_fn,
    target_date: Optional[str] = None,
    avg_n: int = 5,
    confirm_gap: float = 0.03,
    confirm_vol_ratio: float = 2.0,
    high_open_warning: float = 0.07,
) -> List[Dict[str, Any]]:
    """对一批 code 做竞价验证（顺序，调用方可用并发包装）。"""
    out = []
    for code in codes:
        try:
            df = fetch_fn(code)
            out.append(analyze_auction(
                code, df, target_date, avg_n, confirm_gap, confirm_vol_ratio, high_open_warning))
        except Exception as e:
            out.append({"code": code, "signal": f"取数失败: {type(e).__name__}",
                        "risk_flag": "data_missing", "gap_pct": None, "vol_ratio": None})
    return out
