"""周末累积 → 周一(7-20)盘前多 tab 报告。

按日期分 tab（7-18 周六 / 7-19 周日），汇总周末新闻，为周一开盘做准备。
复刻 pipeline.run 的核心循环（fetch → 并发 extract+map → render_report），
**竞价验证跳过**（周末休市，无日K可验）。

数据：
  7-18 周六：wallstreetcn_q1.jsonl（最新 ~65）+ akshare cctv 20260718
  7-19 周日：newsnow 实时（~65）+ akshare cctv 20260719

⚠️ 必须注入 DEEPSEEK_API_KEY 防静默降级 mock：
  $env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY','User')
  python scripts/gen_weekend_report.py
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
os.chdir(ROOT)  # Config.load 与 data/reports 相对路径都基于项目根
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from src.config import Config  # noqa: E402
from src.analysis.extractor import EventExtractor  # noqa: E402
from src.analysis.mapper import map_to_pool  # noqa: E402
from src.news.base import NewsItem  # noqa: E402
from src.news.newsnow_source import NewsnowSource  # noqa: E402
from src.news.akshare_source import AkshareNewsSource  # noqa: E402
from src.report.renderer import render_report  # noqa: E402
from src.report.html_renderer import render_html_tabbed  # noqa: E402
from src.report.trend_tags import compute_trend_tags, compute_resonance, compute_regime  # noqa: E402
from src.discovery.miner import mine_diffusion  # noqa: E402

from jsonl_news_source import JsonlNewsSource  # noqa: E402

# ===== 配置 =====
PER_DAY = 80
WSC_PATH = str(ROOT / "data" / "wallstreetcn_q1.jsonl")
OUT_HTML = ROOT / "reports" / "daily_2026-07-20_rank.html"
REPORT_TITLE = "2026-07-20 周一盘前（周末累积）"


def _process_batch(extractor: EventExtractor, cfg: Config, items: List[NewsItem]) -> List[str]:
    """复刻 pipeline.process：并发 extract+map → render_report（auction_map={}，周末跳过竞价）。"""
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

    reports: List[str] = []
    rep_codes: List[str] = []
    sectors: List[str] = []
    for news, evt, mr in results:
        reports.append(render_report(news, evt, mr, cfg.report_templates, {}))
        if evt and not getattr(evt, "is_noise", False):
            for r in (mr.get("representative") or [])[:2]:
                c = r.get("code") if isinstance(r, dict) else None
                if c:
                    rep_codes.append(c)
            for s in (getattr(evt, "beneficiary_sectors", None) or [])[:2]:
                if s:
                    sectors.append(s)
    return reports, list(dict.fromkeys(rep_codes)), list(dict.fromkeys(sectors))


def _dedup(items: List[NewsItem]) -> List[NewsItem]:
    seen: set = set()
    out: List[NewsItem] = []
    for it in items:
        if it.title and it.title not in seen:
            seen.add(it.title)
            out.append(it)
    return out


def _fetch_day(day: str, cfg: Config) -> List[NewsItem]:
    """组装某天的新闻。day ∈ {'7-18', '7-19', '7-20'}。
    7-18: wallstreetcn_q1(历史快照) + cctv; 7-19: cctv按日期(历史, newsnow实时抓不到昨天);
    7-20: newsnow实时 + 东财global实时 + cctv当天."""
    items: List[NewsItem] = []
    if day == "7-18":
        items += JsonlNewsSource(config={
            "path": WSC_PATH, "source_tag": "华尔街见闻(7-18)",
            "title_key": "title", "content_key": "content_text", "ts_key": "ts",
        }).fetch(limit=PER_DAY - 15)
        try:
            items += AkshareNewsSource(config={"mode": "cctv", "date": "20260718"}).fetch(limit=15)
        except Exception as e:
            print(f"[warn] cctv 7-18 抓取失败: {e}")
    elif day == "7-19":
        # 7-19 历史: newsnow 实时抓不到昨天(会抓到7-20早上), 只用 cctv 按日期
        try:
            items += AkshareNewsSource(config={"mode": "cctv", "date": "20260719"}).fetch(limit=PER_DAY)
        except Exception as e:
            print(f"[warn] cctv 7-19 抓取失败: {e}")
    else:  # 实时(今天/7-20): newsnow + 东财global + cctv当天
        stamp = day.replace("-", "")  # 2026-07-21 → 20260721
        try:
            items += NewsnowSource(config=cfg.news.get("newsnow") or {}).fetch(limit=PER_DAY - 30)
        except Exception as e:
            print(f"[warn] newsnow 实时抓取失败: {e}")
        try:
            items += AkshareNewsSource(config={"mode": "global"}).fetch(limit=20)
        except Exception as e:
            print(f"[warn] akshare global 抓取失败: {e}")
        try:
            items += AkshareNewsSource(config={"mode": "cctv", "date": stamp}).fetch(limit=10)
        except Exception as e:
            print(f"[warn] cctv {day} 抓取失败: {e}")
    return _dedup(items)[:PER_DAY]


def main():
    import datetime
    today_mode = "--today" in sys.argv
    today = datetime.date.today()
    if today_mode:
        days = [(today.isoformat(), f"{today.isoformat()} 今天")]
        title = f"{today.isoformat()} 盘前"
        out_html = ROOT / "reports" / f"daily_{today.isoformat()}.html"
        print(f">>> 今天模式: {today.isoformat()} (单 tab, 实时新闻)")
    else:
        days = [("7-18", "7-18 周六"), ("7-19", "7-19 周日"), ("7-20", "7-20 早上")]
        title = REPORT_TITLE
        out_html = OUT_HTML
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("⚠️⚠️ DEEPSEEK_API_KEY 未设置 → 将静默降级 mock，结果仅 demo！")
        print("   PowerShell: $env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY','User')")

    cfg = Config.load()
    extractor = EventExtractor(
        llm_config=cfg.llm, sector_map=cfg.sector_map,
        event_rules=cfg.event_rules, prompts=cfg.prompts,
    )

    print(">>> 算大盘 regime（拉沪深300日K，最近交易日）...")
    regime = compute_regime(today.isoformat() if today_mode else "2026-07-17")
    print(f"   大盘: {regime.get('regime')} (仓位上限 {regime.get('total_cap')})")

    import json
    CACHE_DIR = ROOT / "reports" / "_cache"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    sources_data = []
    for day, label in days:
        cpath = CACHE_DIR / f"{day}.json"
        cached = None
        if not today_mode and day != "7-20" and cpath.exists():  # 周末缓存; today 不缓存
            try:
                cached = json.loads(cpath.read_text(encoding="utf-8"))
            except Exception:
                cached = None
        if cached:
            reports = cached["reports"]; rep_codes = cached["rep_codes"]; sectors = cached["sectors"]
            trends_map = cached["trends_map"]; resonance_map = cached["resonance_map"]
            print(f">>> {label}: 命中缓存(跳过 LLM + 趋势)")
        else:
            print(f">>> 抓取 {label} 新闻 ...")
            items = _fetch_day(day, cfg)
            print(f"   {label}: {len(items)} 条 → LLM 抽取 ...")
            reports, rep_codes, sectors = _process_batch(extractor, cfg, items)
            trends_map = compute_trend_tags(rep_codes[:40]) if rep_codes else {}
            resonance_map = compute_resonance(sectors[:8], cfg.sector_map) if sectors else {}
            if not today_mode and day != "7-20":  # 存缓存(today/7-20 实时不缓存)
                cpath.write_text(json.dumps({"reports": reports, "rep_codes": rep_codes,
                    "sectors": sectors, "trends_map": trends_map, "resonance_map": resonance_map},
                    ensure_ascii=False), encoding="utf-8")
        n_news = len(reports)
        n_noise = sum(1 for r in reports if "判定为噪音" in r)
        n_td = sum(1 for v in trends_map.values() if v.get("trend") != "无数据")
        print(f"   {label}: {n_news} 条(噪音{n_noise}/正常{n_news-n_noise}) | 趋势 {n_td}/{len(trends_map)}")
        diff = mine_diffusion({}, cfg.sector_map)  # 周末/盘前无 auction → confirmed=[]
        sources_data.append({
            "source": label, "reports_md": reports, "auction_map": {}, "diff": diff,
            "stats": {"n_news": n_news, "n_confirmed": 0, "n_pool": len(rep_codes)},
            "trends_map": trends_map, "resonance_map": resonance_map, "regime": regime,
        })

    print(">>> 渲染多 tab HTML ...")
    html = render_html_tabbed(title, sources_data, cfg.sector_map)
    out_html.parent.mkdir(exist_ok=True)
    out_html.write_text(html, encoding="utf-8")
    print(f"\n✅ {out_html}")


if __name__ == "__main__":
    raise SystemExit(main())
