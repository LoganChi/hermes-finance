"""事件 -> 股票池映射器（里程碑2 + 产业链扩散）。

设计原则（铁律）：
- 本系统是"事件驱动映射"系统，**绝不预测股价**。
- 本模块做两件事：①根据事件归因的受益/受损板块，在 sector_map 查表收集成分股；
  ②沿 industry_chain 把命中板块扩散到上下游板块（精准扩散，替代"硬靠"）。
- 不输出任何涨跌 / 买卖 / 目标价判断。

为避免与 src/analysis/extractor.py 形成循环 import，这里用 TYPE_CHECKING 仅做类型提示，
运行期对 evt 采用 duck typing 访问字段（兼容 EventExtraction 与任意等价对象）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from src.analysis.extractor import EventExtraction


def _empty_result() -> Dict[str, Any]:
    """空结构。供 evt 缺失或噪音事件时返回，保证下游渲染始终拿到一致的字段集合。"""
    return {
        "watch_pool": [],
        "representative": [],
        "sectors_hit": [],
        "missed_sectors": [],
        "victim_pool": [],
        "chain_sectors": [],
        "chain_pool": [],
    }


def _collect_codes(
    sectors: List[str],
    sector_map: Dict[str, List[Dict[str, Any]]],
) -> tuple[List[str], List[str], List[str]]:
    """遍历板块名，在 sector_map 中查成分股 code。

    Returns:
        (hit_sectors, missed_sectors, codes) —— 命中板块名、缺失板块名、保序去重的 code 列表。
    """
    hit_sectors: List[str] = []
    missed_sectors: List[str] = []
    codes: List[str] = []
    seen: Set[str] = set()

    for sector in sectors:
        stocks = sector_map.get(sector)
        if stocks is None:
            # LLM 归因可能提到表外板块
            missed_sectors.append(sector)
            continue
        hit_sectors.append(sector)
        for stock in stocks:
            code = stock.get("code") if isinstance(stock, dict) else None
            if code and code not in seen:
                seen.add(code)
                codes.append(code)

    return hit_sectors, missed_sectors, codes


def map_to_pool(
    evt: "EventExtraction | None",
    sector_map: Dict[str, List[Dict[str, Any]]],
    topn: int = 8,
    industry_chain: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """将事件归因结果映射到"待竞价验证"股票池，并沿产业链扩散到上下游板块。

    纯函数，不预测股价。

    Args:
        evt: 事件抽取结果（EventExtraction 或等价对象），允许 None。
        sector_map: {"板块名": [{"code": "002460", "name": "赣锋锂业"}, ...]}。
        topn: watch_pool / chain_pool 截断长度。
        industry_chain: {"板块名": {"upstream":[...], "downstream":[...]}}，可选。

    Returns:
        dict，含 watch_pool/representative/sectors_hit/missed_sectors/victim_pool，
        以及 chain_sectors(产业链扩散板块)/chain_pool(扩散板块成分股)。
    """
    if evt is None:
        return _empty_result()
    if getattr(evt, "is_noise", False):
        return _empty_result()

    beneficiary_sectors: List[str] = list(getattr(evt, "beneficiary_sectors", []) or [])
    victim_sectors: List[str] = list(getattr(evt, "victim_sectors", []) or [])

    # 受益侧
    sectors_hit, missed_b, watch_codes = _collect_codes(beneficiary_sectors, sector_map)
    # 受损侧（独立收集，不进 watch_pool）
    _, missed_v, victim_codes = _collect_codes(victim_sectors, sector_map)

    # 合并缺失板块并去重（保留首次出现顺序）
    missed_sectors: List[str] = []
    missed_seen: Set[str] = set()
    for s in missed_b + missed_v:
        if s not in missed_seen:
            missed_seen.add(s)
            missed_sectors.append(s)

    # watch_pool 截断到前 topn 个
    watch_pool = watch_codes[:topn]

    # 产业链扩散：命中板块沿 industry_chain 找上下游板块(不重复、须在 sector_map 内)
    chain_sectors: List[str] = []
    if industry_chain:
        for s in sectors_hit:
            node = industry_chain.get(s) or {}
            for d in (node.get("downstream") or []):
                if d in sector_map and d not in sectors_hit and d not in chain_sectors:
                    chain_sectors.append(d)
            for u in (node.get("upstream") or []):
                if u in sector_map and u not in sectors_hit and u not in chain_sectors:
                    chain_sectors.append(u)

    # 扩散板块的成分股(参考池, 独立于主 watch_pool)
    chain_pool: List[str] = []
    seen_c: Set[str] = set()
    for s in chain_sectors:
        for st in sector_map.get(s, []):
            code = st.get("code") if isinstance(st, dict) else None
            if code and code not in seen_c:
                seen_c.add(code)
                chain_pool.append(code)
    chain_pool = chain_pool[:topn]

    return {
        "watch_pool": watch_pool,
        "representative": list(getattr(evt, "representative_stocks", []) or []),
        "sectors_hit": sectors_hit,
        "missed_sectors": missed_sectors,
        "victim_pool": victim_codes,
        "chain_sectors": chain_sectors,
        "chain_pool": chain_pool,
    }
