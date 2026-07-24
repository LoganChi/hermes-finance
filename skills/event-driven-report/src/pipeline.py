"""主流程：news → 归因 → 映射 → 产业链扩散 → 竞价验证 → 报告（并发）。

绝不预测股价。竞价验证用日K开盘价(集合竞价9:25结果)客观判断资金是否确认，不做方向预测。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Tuple

from src.config import Config
from src.news.base import NewsItem, NewsSource
from src.news.demo_source import DemoNewsSource
from src.news.newsnow_source import NewsnowSource
from src.analysis.extractor import EventExtractor
from src.analysis.mapper import map_to_pool
from src.report.renderer import render_report
from src.auction.fetcher import fetch_recent
from src.auction.analyzer import analyze_auction


def build_news_source(cfg: Config) -> NewsSource:
    """根据配置选择新闻源（可插拔：demo / newsnow / tushare / akshare）。"""
    news_cfg = cfg.news
    source = news_cfg.get("source", "demo")
    if source == "newsnow":
        from src.news.newsnow_source import NewsnowSource
        return NewsnowSource(config=news_cfg.get("newsnow", {}))
    if source == "tushare":
        from src.news.tushare_source import TushareNewsSource
        return TushareNewsSource(config=news_cfg.get("tushare", {}))
    if source == "akshare":
        from src.news.akshare_source import AkshareNewsSource
        return AkshareNewsSource(config=news_cfg.get("akshare", {}))
    return DemoNewsSource(samples=cfg.demo_news)


def _verify_auction(all_codes: List[str], auction_cfg: dict) -> Dict[str, Dict[str, Any]]:
    """对去重后的 code 池并发做竞价验证，返回 {code: result}。"""
    auction_map: Dict[str, Dict[str, Any]] = {}
    if not all_codes:
        return auction_map
    aw = int(auction_cfg.get("max_workers", 8) or 8)
    avg_n = int(auction_cfg.get("avg_n", 5) or 5)
    cg = float(auction_cfg.get("confirm_gap", 0.03) or 0.03)
    cvr = float(auction_cfg.get("confirm_vol_ratio", 2.0) or 2.0)
    hw = float(auction_cfg.get("high_open_warning", 0.07) or 0.07)

    def verify(code: str):
        try:
            df = fetch_recent(code)
            return code, analyze_auction(code, df, None, avg_n, cg, cvr, hw)
        except Exception as e:
            return code, {"code": code, "signal": f"取数失败:{type(e).__name__}",
                          "risk_flag": "data_missing", "gap_pct": None, "vol_ratio": None}

    with ThreadPoolExecutor(max_workers=aw) as ex:
        for code, res in ex.map(verify, all_codes):
            auction_map[code] = res
    return auction_map


def run(config_path: str = "config/settings.yaml", return_context: bool = False):
    """跑通全链路，返回每条新闻的可读报告列表（顺序与输入一致）。"""
    cfg = Config.load(config_path)

    source = build_news_source(cfg)
    extractor = EventExtractor(
        llm_config=cfg.llm,
        sector_map=cfg.sector_map,
        event_rules=cfg.event_rules,
        prompts=cfg.prompts,
    )

    limit = cfg.news.get("limit", 20)
    try:
        items = source.fetch(limit=limit)
    except RuntimeError as e:
        print(f"[warn] 新闻源 {source.name} 不可用：{e} → 降级使用 demo 源")
        source = DemoNewsSource(samples=cfg.demo_news)
        items = source.fetch(limit=limit)

    topn = cfg.mapper_topn

    def process(news: NewsItem) -> Tuple[Any, Any, Dict[str, Any]]:
        evt = extractor.extract_event(news)
        if evt is None or getattr(evt, "is_noise", False):
            mr: Dict[str, Any] = {
                "watch_pool": [], "representative": [],
                "sectors_hit": [], "missed_sectors": [], "victim_pool": [],
                "chain_sectors": [], "chain_pool": [],
            }
        else:
            mr = map_to_pool(evt, cfg.sector_map, topn=topn, industry_chain=cfg.industry_chain)
        return news, evt, mr

    max_workers = int((cfg.settings.get("pipeline") or {}).get("max_workers", 5) or 5)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        results = list(ex.map(process, items))

    # 竞价验证：收集所有 watch_pool + chain_pool 去重，统一验证
    auction_cfg = cfg.settings.get("auction") or {}
    auction_map: Dict[str, Dict[str, Any]] = {}
    if auction_cfg.get("enabled"):
        all_codes: List[str] = []
        for _, _, mr in results:
            for c in (mr.get("watch_pool") or []) + (mr.get("chain_pool") or []):
                if c not in all_codes:
                    all_codes.append(c)
        print(f"[info] 竞价验证 {len(all_codes)} 只标的（AKShare 拉日K，并发）...")
        auction_map = _verify_auction(all_codes, auction_cfg)

    reports: List[str] = []
    for news, evt, mr in results:
        reports.append(render_report(news, evt, mr, cfg.report_templates, auction_map))
    if return_context:
        return reports, {
            "auction_map": auction_map,
            "sector_map": cfg.sector_map,
            "industry_chain": cfg.industry_chain,
        }
    return reports
