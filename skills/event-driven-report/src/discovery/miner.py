"""扩散挖掘器（里程碑4）。

从竞价"资金确认"的标的, 挖同板块(横向)还没异动的扩散候选。
（纵向产业链扩散已在 mapper.chain_sectors；这里补横向同板块扩散。）
铁律：不预测股价，只挖"同板块未异动标的"作为观察候选。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Tuple


def build_code2sectors(sector_map: Dict[str, list]) -> Dict[str, List[str]]:
    """标的代码 → 所属板块列表（反查表）。"""
    code2sec: Dict[str, List[str]] = defaultdict(list)
    for sector, stocks in sector_map.items():
        for s in stocks:
            code = s.get("code") if isinstance(s, dict) else None
            if code:
                code2sec[code].append(sector)
    return code2sec


def find_confirmed(
    auction_map: Dict[str, Dict[str, Any]],
    signals: Tuple[str, ...] = ("资金确认（高开放量）",),
) -> List[str]:
    """找出竞价信号命中的标的（默认只要"资金确认"）。"""
    return [c for c, a in auction_map.items() if a.get("signal") in signals]


def mine_diffusion(
    auction_map: Dict[str, Dict[str, Any]],
    sector_map: Dict[str, list],
    confirmed_signals: Tuple[str, ...] = ("资金确认（高开放量）",),
    topn_per_code: int = 5,
) -> Dict[str, Any]:
    """从竞价确认标的挖同板块其他未确认标的（横向扩散）。

    Returns:
        {"confirmed":[code...], "peers":{code:[同板块候选...]}, "all_peer_codes":[...]}
    """
    code2sec = build_code2sectors(sector_map)
    confirmed = find_confirmed(auction_map, confirmed_signals)
    confirmed_set = set(confirmed)
    peers: Dict[str, List[str]] = {}
    seen_all: set = set()

    for c in confirmed:
        cand: List[str] = []
        for sector in code2sec.get(c, []):
            for s in sector_map.get(sector, []):
                pc = s.get("code") if isinstance(s, dict) else None
                if pc and pc != c and pc not in confirmed_set and pc not in cand:
                    cand.append(pc)
        peers[c] = cand[:topn_per_code]
        for p in peers[c]:
            seen_all.add(p)

    return {
        "confirmed": confirmed,
        "peers": peers,
        "all_peer_codes": sorted(seen_all),
    }
