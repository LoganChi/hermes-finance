"""Markdown 报告渲染器 —— 文案全部来自 config/report_templates.yaml。

设计原则（铁律）：
- 只渲染"事件归因 + 产业链映射"的客观事实，绝不预测股价，不构成任何投资建议。
- 输出严禁出现涨跌 / 买卖 / 目标价 / 方向性判断的字眼。
- 纯函数：render_report 不持有状态、不产生副作用，输入决定输出。
"""
from __future__ import annotations

from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from src.analysis.extractor import EventExtraction
    from src.news.base import NewsItem


def _safe(value: Any, default: str = "-") -> str:
    """安全取展示字符串：None / 空值 -> default。"""
    if value is None:
        return default
    s = str(value)
    return s if s else default


def _format_confidence(confidence: Any) -> str:
    """置信度格式化：float(0~1) -> 百分比；其余原样字符串化。"""
    if isinstance(confidence, bool):
        return _safe(confidence)
    if isinstance(confidence, (int, float)):
        return f"{float(confidence):.0%}"
    return _safe(confidence)


def _join_sectors(sectors: List[str], no_value: str) -> str:
    return ", ".join(sectors) if sectors else no_value


def render_report(
    news: "NewsItem | None",
    evt: "EventExtraction | None",
    map_result: Dict[str, Any],
    templates: Dict[str, Any],
    auction_map: Dict[str, Any] | None = None,
) -> str:
    """渲染事件映射报告为 Markdown 字符串。纯函数，不预测股价。

    Args:
        news: 新闻条目，允许 None。
        evt: 事件抽取结果，允许 None。
        map_result: mapper.map_to_pool 的返回 dict。
        templates: 来自 config/report_templates.yaml 的文案配置。
    """
    t = templates or {}
    sec = t.get("sections") or {}
    lbl = t.get("labels") or {}
    ph = t.get("placeholders") or {}
    th = t.get("table_headers") or {}
    disclaimer = t.get("disclaimer", "")
    no_value = lbl.get("no_value", "无")
    news_prefix = sec.get("news_title_prefix", "# 📰 ")

    lines: List[str] = [disclaimer, ""]

    # 噪音 / 空事件：仅渲染简短过滤说明
    if evt is None or getattr(evt, "is_noise", False):
        if news is not None:
            title = _safe(getattr(news, "title", None), ph.get("no_news", "（无新闻）"))
        else:
            title = ph.get("no_news", "（无新闻）")
        lines.append(f"{news_prefix}{title}")
        lines.append("")
        lines.append(t.get("noise_message", "> 判定为噪音，已过滤。"))
        lines.append("")
        lines.append(disclaimer)
        return "\n".join(lines)

    # —— 新闻信息 ——
    if news is not None:
        title = _safe(getattr(news, "title", None), ph.get("no_title", "（无标题）"))
        source = _safe(getattr(news, "source", None), ph.get("unknown_source", "未知来源"))
        url = getattr(news, "url", None)
        published_at = getattr(news, "published_at", None)
        lines.append(f"{news_prefix}{title}")
        meta = f"**{lbl.get('source', '来源')}**：{source}"
        if published_at:
            meta += f" ｜ **{lbl.get('published_at', '发布时间')}**：{published_at}"
        lines.append(meta)
        if url:
            lines.append(f"**{lbl.get('link', '链接')}**：{url}")
        lines.append("")

    # —— 事件归因 ——
    eh = th.get("event", ["字段", "值"])
    lines.append(sec.get("event_analysis", "## 🎯 事件归因"))
    lines.append("")
    lines.append(f"| {eh[0]} | {eh[1]} |")
    lines.append("| --- | --- |")
    lines.append(f"| 事件类型 | {_safe(getattr(evt, 'event_type', None))} |")
    lines.append(f"| 情绪 | {_safe(getattr(evt, 'sentiment', None))} |")
    lines.append(f"| 置信度 | {_format_confidence(getattr(evt, 'confidence', None))} |")
    lines.append(f"| 时效 | {_safe(getattr(evt, 'time_horizon', None))} |")
    lines.append("")

    # —— 产业链映射 ——
    beneficiary_sectors = list(getattr(evt, "beneficiary_sectors", []) or [])
    victim_sectors = list(getattr(evt, "victim_sectors", []) or [])
    sectors_hit = list(map_result.get("sectors_hit", []) or [])
    lines.append(sec.get("chain_mapping", "## 🧩 产业链映射"))
    lines.append("")
    lines.append(f"**{lbl.get('beneficiary', '受益板块')}**：{_join_sectors(beneficiary_sectors, no_value)}")
    lines.append(f"**{lbl.get('victim', '受损板块')}**：{_join_sectors(victim_sectors, no_value)}")
    lines.append(f"**{lbl.get('sectors_hit', '命中映射表的板块')}**：{_join_sectors(sectors_hit, no_value)}")
    lines.append("")

    # —— 代表标的 ——
    representative = list(map_result.get("representative", []) or [])
    rh = th.get("representative", ["代码", "名称", "角色"])
    lines.append(sec.get("representative", "## 🏷️ 代表标的"))
    lines.append("")
    if representative:
        lines.append(f"| {rh[0]} | {rh[1]} | {rh[2]} |")
        lines.append("| --- | --- | --- |")
        for item in representative:
            if isinstance(item, dict):
                lines.append(
                    f"| {_safe(item.get('code'))} | {_safe(item.get('name'))} | {_safe(item.get('role'), '—')} |"
                )
        lines.append("")
    else:
        lines.append(no_value)
        lines.append("")

    # —— 待竞价验证 watch_pool ——
    watch_pool = list(map_result.get("watch_pool", []) or [])
    victim_pool = list(map_result.get("victim_pool", []) or [])
    lines.append(sec.get("watch_pool", "## ⏰ 待竞价验证 watch_pool"))
    lines.append("")
    if watch_pool:
        lines.append(", ".join(f"`{c}`" for c in watch_pool))
        lines.append("")
    else:
        lines.append(no_value)
        lines.append("")
    if victim_pool:
        lines.append(f"**{lbl.get('victim_pool_ref', '受损池（仅参考，独立列出）')}**：")
        lines.append(", ".join(f"`{c}`" for c in victim_pool))
        lines.append("")

    # —— 产业链扩散（沿 industry_chain 的上下游板块） ——
    chain_sectors = list(map_result.get("chain_sectors", []) or [])
    chain_pool = list(map_result.get("chain_pool", []) or [])
    if chain_sectors:
        lines.append(sec.get("chain_diffusion", "## 🔗 产业链扩散（上下游板块）"))
        lines.append("")
        lines.append(f"**扩散板块**：{', '.join(chain_sectors)}")
        if chain_pool:
            lines.append("**扩散标的（参考）**：" + ", ".join(f"`{c}`" for c in chain_pool))
        lines.append("")

    # —— 竞价验证（watch_pool 各标的是否被资金确认） ——
    if watch_pool and auction_map:
        lines.append(sec.get("auction", "## 📊 竞价验证（资金是否确认）"))
        lines.append("")
        lines.append("| 代码 | 高开% | 量比 | 换手% | 信号 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for c in watch_pool:
            a = auction_map.get(c) or {}
            gap = a.get("gap_pct")
            vr = a.get("vol_ratio")
            to = a.get("turnover")
            sig = a.get("signal", "(未验证)")
            lines.append(
                f"| {c} | {gap if gap is not None else '-'} | "
                f"{vr if vr is not None else '-'} | {to if to is not None else '-'} | {sig} |"
            )
        lines.append("")

    # —— 缺失板块提示 ——
    missed_sectors = list(map_result.get("missed_sectors", []) or [])
    if missed_sectors:
        lines.append(sec.get("missed_sectors", "## ⚠️ 映射表缺失板块"))
        lines.append("")
        lines.append(t.get("missed_sectors_hint", "以下板块在映射表中缺失，建议补表："))
        for s in missed_sectors:
            lines.append(f"- {s}")
        lines.append("")

    # —— 归因链路 ——
    chain_reasoning = getattr(evt, "chain_reasoning", None)
    if chain_reasoning:
        lines.append(sec.get("chain_reasoning", "## 🔗 归因链路"))
        lines.append("")
        lines.append(f"> {chain_reasoning}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(disclaimer)
    return "\n".join(lines)
