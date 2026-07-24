"""批量趋势标签入口 —— 给事件报告的标的/板块/大盘打多维趋势标签。

复用 compute_factors / score_stock / board_resonance / calc_timing_score，不重写。
定位：趋势是事件标的的**辅助评估维度**（"没竞价时看趋势"的 fallback），
绝不替代事件归因、不独立成趋势选股（见 strategy-engine-v1 回测教训）。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from src.auction.fetcher import fetch_recent, fetch_index
from src.strategy.scoring import compute_factors, score_stock, board_resonance
from src.strategy.timing_score import calc_timing_score


# 趋势分档阈值（可调）
STRONG_TOTAL = 5  # type=强势 且 total≥5 → "强"


def _trend_label(score_result: Dict[str, Any]) -> str:
    """score_stock 结果 → 强/中/弱 标签。纯技术面(不结合事件情绪)。"""
    t = score_result.get("type", "中间")
    total = score_result.get("total", 0) or 0
    if t == "强势" and total >= STRONG_TOTAL:
        return "强"
    if total > 0:  # 有反转/加分信号(含超跌出现拐点) → 中
        return "中"
    return "弱"  # 含: 强势但排列散、超跌无拐点(下跌中)、中间型


def _score_one(code: str) -> tuple[str, Dict[str, Any]]:
    """单标的算趋势标签。返回 (code, tag_info)。"""
    try:
        df = fetch_recent(code)
        if df is None or len(df) < 35:
            return code, _empty("数据不足")
        i = len(df) - 1
        factors = compute_factors(code, df, i)
        sc = score_stock(factors)
        return code, {
            "trend": _trend_label(sc),
            "score": sc.get("total", 0),
            "type": sc.get("type", "中间"),
            "bullish_ma": bool(factors.get("bullish_ma")),
            "aligned": bool(factors.get("aligned")),
            "new_high": bool(factors.get("new_high")),
            "detail": "；".join(sc.get("detail", []))[:60],
        }
    except Exception as e:
        return code, _empty(f"err:{type(e).__name__}")


def _empty(note: str = "") -> Dict[str, Any]:
    return {"trend": "无数据", "score": 0, "type": "-", "bullish_ma": False,
            "aligned": False, "new_high": False, "detail": note}


def compute_trend_tags(codes: List[str], max_workers: int = 8) -> Dict[str, Dict[str, Any]]:
    """对一批标的并发算趋势标签。返回 {code: tag_info}。"""
    codes = list(dict.fromkeys(c for c in codes if c))  # 去重保序
    out: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for code, info in ex.map(_score_one, codes):
            out[code] = info
    return out


def compute_resonance(sectors: List[str], sector_map: dict, top_n: int = 10,
                      max_workers: int = 4) -> Dict[str, float]:
    """对受益板块算共振。board_resonance 内部全量遍历成分股（慢），
    这里传**限量版 sector_map**（每板块前 top_n 只）绕过，不改原函数。返回 {sector: float 0~1}。"""
    sectors = [s for s in sectors if s]
    limited = {s: (sector_map.get(s, []) or [])[:top_n] for s in sectors}
    out: Dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        fut_to_sec = {ex.submit(board_resonance, s, limited, fetch_recent): s for s in sectors}
        for fut, s in fut_to_sec.items():
            try:
                out[s] = float(fut.result())
            except Exception:
                out[s] = 0.0
    return out


def compute_regime(date: str) -> Dict[str, Any]:
    """大盘 regime（tab 级，算一次）。date: 报告日期 YYYY-MM-DD。"""
    try:
        r = calc_timing_score(date, lambda c: fetch_index(c, days=400))
        return {
            "regime": r.get("regime", "中性"),
            "score": r.get("score", 0),
            "total_cap": r.get("total_cap", 0),
        }
    except Exception as e:
        return {"regime": "未知", "score": 0, "total_cap": 0, "err": type(e).__name__}
