"""HTML 报告渲染器 v4 —— 单文件多tab，按新闻源切换。"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass

def _esc(t): return (t or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")
def _safe(v, d="-"): return d if v is None else (str(v) if str(v) else d)
def _symbol(code) -> str:
    """6位代码 → 腾讯行情符号(市场前缀+代码)。6→sh, 0/3→sz, 4/8→bj。"""
    c = str(code).strip()
    if c[:1] == "6": return "sh" + c
    if c[:1] in ("4", "8"): return "bj" + c
    return "sz" + c
def _stock_url(code) -> str:
    """股票代码 → 腾讯股票页(gu.qq.com, 浏览器/移动端友好)。"""
    return f"https://gu.qq.com/{_symbol(code)}"


def render_event_card_simple(parsed: dict, auction_map: dict, idx: int, source_tag: str = "",
                             trends_map: dict = None, resonance_map: dict = None) -> str:
    """从 parse_md_report 的结果渲染单张卡片。trends_map/resonance_map 可选(趋势标签)。"""
    if parsed["is_noise"]:
        return f'<div class="card noise" data-sentiment="噪音"><span class="badge dim">噪音</span> {_esc(parsed["title"])}</div>'

    title = parsed["title"]
    evt_type = parsed["event_type"]
    sentiment = parsed["sentiment"]
    conf = parsed["confidence"]
    conf_str = f"{conf:.0%}" if isinstance(conf, (int,float)) else _safe(conf)
    sc = {"利好":"#22c55e","利空":"#ef4444"}.get(sentiment, "#eab308")

    sec_html = ""
    for s in parsed["beneficiary_sectors"][:6]:
        sec_html += f'<span class="pill pos">{_esc(s)}</span>'
    for s in parsed["victim_sectors"][:3]:
        sec_html += f'<span class="pill neg">{_esc(s)}</span>'
    for s in parsed["chain_sectors"][:3]:
        sec_html += f'<span class="pill chain">🔗{_esc(s)}</span>'

    # 趋势标签(取 representative 最优趋势) + 板块共振 —— 数据源拉不到时为空, 优雅降级
    trend_label = ""
    if trends_map:
        best = None
        for r in parsed["representative_stocks"]:
            info = trends_map.get(r.get("code"))
            if info and info.get("trend") and info["trend"] != "无数据":
                if not best or (info.get("score", 0) or 0) > (best.get("score", 0) or 0):
                    best = info
        if best:
            trend_label = best["trend"]
    best_res = 0.0
    if resonance_map:
        for s in parsed["beneficiary_sectors"]:
            v = resonance_map.get(s, 0) or 0
            if v > best_res:
                best_res = v
    resonance_flag = "1" if best_res >= 0.5 else "0"
    if trend_label:
        tc = {"强": "pos", "中": "chain", "弱": "neg"}.get(trend_label, "")
        sec_html += f'<span class="pill {tc}">📈{trend_label}</span>'
    if best_res > 0:  # 板块共振显示数值(不只是布尔), 个股与板块分层都看
        rcls = "pos" if best_res >= 0.5 else "chain"
        sec_html += f'<span class="pill {rcls}">🎯板块{best_res:.2f}</span>'

    rep_html = ""
    for r in parsed["representative_stocks"][:5]:
        role_cls = "lead" if "龙头" in r.get("role","") else "elastic"
        rep_html += f'<span class="stk"><a class="code" href="{_stock_url(r.get("code"))}" target="_blank">{_safe(r.get("code"))}</a> {_esc(r.get("name",""))} <span class="role {role_cls}">{_safe(r.get("role"),"—")}</span></span>'

    # 竞价摘要
    n_conf = n_low = n_total = 0
    auc_html = ""
    if parsed["watch_pool"] and auction_map:
        for c in parsed["watch_pool"][:12]:
            a = auction_map.get(c,{})
            gap = a.get("gap_pct"); vr = a.get("vol_ratio"); sig = a.get("signal","-")
            n_total += 1
            if "资金确认" in str(sig): n_conf += 1
            if "低开" in str(sig): n_low += 1
            gc = "neg" if (gap is not None and gap<0) else ("pos" if gap and gap>0 else "")
            gap_s = f"{gap:+.1f}%" if gap is not None else "-"
            vr_s = f"{vr:.1f}" if vr is not None else "-"
            sig_s = str(sig).replace("资金确认","✅").replace("无明显异动","—").replace("低开（未确认/利空）","❌低开").replace("资金是否确认)","").replace("（","(")
            nm = next((r.get("name","") for r in parsed["representative_stocks"] if r.get("code")==c), "")
            auc_html += f'<tr><td class="code">{c}</td><td class="nm">{_esc(nm)}</td><td class="{gc}">{gap_s}</td><td>{vr_s}</td><td>{sig_s}</td></tr>'

    auc_sum = ""
    if n_total:
        parts = []
        if n_conf: parts.append(f'<span class="ok">{n_conf}确认</span>')
        if n_low: parts.append(f'<span class="bad">{n_low}低开</span>')
        parts.append(f'<span class="dim">{n_total}只</span>')
        auc_sum = " ".join(parts)

    did = f"d-{source_tag}-{idx}"
    detail = ""
    if auc_html:
        detail += f'<div class="detail-block"><table class="auc-tbl"><tr><th>代码</th><th>名称</th><th>高开</th><th>量比</th><th>信号</th></tr>{auc_html}</table></div>'
    if parsed["chain_reasoning"] and parsed["chain_reasoning"] != "-":
        detail += f'<div class="reason">{_esc(parsed["chain_reasoning"])}</div>'
    if parsed["url"]:
        detail += f'<a href="{parsed["url"]}" target="_blank" class="src-link">原文</a>'

    border = {"利好":"bull","利空":"bear"}.get(sentiment, "neutral")
    data_attrs = f'data-sentiment="{_esc(sentiment)}" data-etype="{_esc(evt_type)}" data-trend="{trend_label}" data-resonance="{resonance_flag}"'
    return f'''<div class="card {border}" {data_attrs} onclick="tog('{did}')">
  <div class="card-head" style="border-left:3px solid {sc};">
    <span class="tag">{_esc(evt_type)}</span>
    <span class="sent" style="color:{sc};">{_esc(sentiment)} {conf_str}</span>
    <span class="auc-sum">{auc_sum}</span>
  </div>
  <div class="card-body">
    <div class="ctitle">{_esc(title)}</div>
    <div class="pills">{sec_html}</div>
    <div class="stk-list">{rep_html}</div>
  </div>
  <div id="{did}" class="detail" style="display:none;">{detail}</div>
</div>'''


def render_html_tabbed(date: str, sources_data: list, sector_map: dict = None) -> str:
    """sources_data = [{source, reports_md, auction_map, diff, stats, trends_map, resonance_map, regime}, ...]
    sector_map 可选, 用于排行榜 code→name 反查。"""
    import re

    # 为每个源解析卡片
    tabs_html = []
    contents_html = []
    rank_panes = []
    all_sentiments = set()
    all_etypes = set()
    # code→name 反查(个股榜用)
    code2name = {}
    if sector_map:
        for stocks in sector_map.values():
            for s in stocks:
                c = s.get("code") if isinstance(s, dict) else None
                if c and c not in code2name:
                    code2name[c] = s.get("name", c)

    def _srow(c, i, msg):
        t = i.get("trend", "")
        tc = {"强": "pos", "中": "chain", "弱": "neg"}.get(t, "")
        nm = code2name.get(c, c)
        mb = msg.get(c, {}).get("利好", 0)
        ml = msg.get(c, {}).get("利空", 0)
        return f'<div class="rank-item {tc}"><a class="rcode" href="{_stock_url(c)}" target="_blank">{c}</a><span class="rname">{_esc(nm[:8])}</span><span class="rmsg ok">+{mb}</span><span class="rmsg bad">-{ml}</span><span class="rtag">{t}</span></div>'

    for si, sd in enumerate(sources_data):
        sname = sd["source"]
        reports = sd["reports_md"]
        auction_map = sd["auction_map"]
        diff = sd["diff"]
        stats = sd.get("stats", {})
        trends_map = sd.get("trends_map") or {}
        resonance_map = sd.get("resonance_map") or {}
        regime = sd.get("regime") or {}
        active = "active" if si == 0 else ""
        display = "block" if si == 0 else "none"

        # 解析卡片
        cards = []
        n_bull = n_bear = n_neu = 0
        stock_msg = {}   # {code: {利好:x, 利空:y, 中性:z}} 提及该标的的消息情绪
        board_msg = {}
        for idx, r in enumerate(reports):
            parsed = _parse_md(r)
            if parsed.get("sentiment"): all_sentiments.add(parsed["sentiment"])
            if parsed.get("event_type"): all_etypes.add(parsed["event_type"])
            s = parsed.get("sentiment", "")
            if s == "利好": n_bull += 1
            elif s == "利空": n_bear += 1
            elif s == "中性": n_neu += 1
            if s in ("利好", "利空", "中性"):
                for rst in parsed.get("representative_stocks", []):
                    c = rst.get("code")
                    if c: stock_msg.setdefault(c, {"利好": 0, "利空": 0, "中性": 0})[s] += 1
                for sec in parsed.get("beneficiary_sectors", []):
                    board_msg.setdefault(sec, {"利好": 0, "利空": 0, "中性": 0})[s] += 1
            cards.append(render_event_card_simple(parsed, auction_map, idx, sname, trends_map, resonance_map))

        # 扩散
        if diff.get("confirmed"):
            diff_html = '<div class="diff-box ok">确认: ' + ", ".join(f'<span class="code">{c}</span>' for c in diff["confirmed"]) + '</div>'
        else:
            diff_html = '<div class="diff-box empty">本期无资金确认标的</div>'

        n_news = stats.get("n_news", len(reports))
        n_conf = stats.get("n_confirmed", len(diff.get("confirmed",[])))
        n_pool = stats.get("n_pool", len(auction_map))

        # tab按钮
        tabs_html.append(f'<button class="tab {active}" onclick="showTab(\'{sname}\')">{sname} <span class="tab-num">{n_news}</span></button>')

        # tab内容
        contents_html.append(f'''<div id="tab-{sname}" class="tab-pane" style="display:{display};">
  <div class="mini-stats">
    <span><b>{n_news}</b> 新闻</span>
    <span><b class="{"ok" if n_conf else "bad"}">{n_conf}</b> 确认</span>
    <span><b>{n_pool}</b> 标的</span>
    {('<span>大盘 <b>' + str(regime.get('regime','-')) + '</b></span>') if regime else ''}
  </div>
  {diff_html}
  <div class="cards-grid">{"".join(cards)}</div>
</div>''')

        # 该 tab 排行榜(消息情绪 + 板块榜 + 个股榜), 顺序: 板块→个股
        br = sorted((resonance_map or {}).items(), key=lambda x: x[1] or 0, reverse=True)
        brows = "".join(
            f'<div class="rank-item {"pos" if v >= 0.5 else "chain"}"><span class="rname">{_esc(s[:10])}</span><span class="rmsg ok">+{board_msg.get(s,{}).get("利好",0)}</span><span class="rmsg bad">-{board_msg.get(s,{}).get("利空",0)}</span><span class="rscore">{v:.2f}</span></div>'
            for s, v in br[:12] if v)
        sr = sorted(
            [(c, i) for c, i in (trends_map or {}).items() if i.get("trend") not in ("无数据",)],
            key=lambda x: x[1].get("score", 0) or 0, reverse=True)
        srows = "".join(_srow(c, i, stock_msg) for c, i in sr[:20])
        rank_panes.append(
            f'<div id="rank-{sname}" class="rank-pane" style="display:{display};">'
            f'<div class="stat-box"><div class="stat-title">{_esc(sname)} · 消息情绪</div>'
            f'<div class="stat-row"><span class="ok">利好 {n_bull}</span><span class="bad">利空 {n_bear}</span><span class="dim">中性 {n_neu}</span></div></div>'
            f'<div class="rank-sec"><div class="rank-h">🎯 板块共振榜</div>{brows}</div>'
            f'<div class="rank-sec"><div class="rank-h">📈 个股趋势榜</div>{srows}</div>'
            '</div>')

    tabs = "".join(tabs_html)
    contents = "".join(contents_html)

    # 筛选栏(点击标签筛卡片, 多维 AND)
    def _chips(dim, vals):
        return "".join(
            f'<button class="chip" data-dim="{dim}" data-val="{_esc(v)}" onclick="toggleFilter(\'{dim}\',\'{_esc(v)}\')">{_esc(v)}</button>'
            for v in vals if v
        )
    fb = []
    if all_sentiments:
        fb.append('<span class="fg">情绪</span>' + _chips("sentiment", sorted(all_sentiments)))
    if all_etypes:
        fb.append('<span class="fg">类型</span>' + _chips("etype", sorted(all_etypes)))
    fb.append('<span class="fg">趋势</span>' + _chips("trend", ["强", "中", "弱"]))
    fb.append('<span class="fg">共振</span><button class="chip" data-dim="resonance" data-val="1" onclick="toggleFilter(\'resonance\',\'1\')">共振</button>')
    fb.append('<button class="chip reset" onclick="resetFilters()">✕ 清除</button>')
    filter_bar = '<div class="filter-bar">' + "".join(fb) + '</div>'

    # sidebar 按 tab 分(每天各自排行), 切 tab 联动切换
    sidebar_html = '<div class="sidebar">' + "".join(rank_panes) + '</div>'

    # JS/CSS 的花括号不能放进 f-string，单独拎成普通字符串再用占位符注入
    _SCRIPT = """<script>
function showTab(name){document.querySelectorAll('.tab-pane').forEach(p=>p.style.display='none');document.querySelectorAll('.rank-pane').forEach(r=>r.style.display='none');document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.getElementById('tab-'+name).style.display='block';var rp=document.getElementById('rank-'+name);if(rp)rp.style.display='block';event.target.closest('.tab').classList.add('active');applyFilters()}
function tog(id){var e=document.getElementById(id);if(e)e.style.display=e.style.display==='none'?'block':'none'}
var FILT={sentiment:[],etype:[],trend:[],resonance:[]};
function toggleFilter(dim,val){var a=FILT[dim],i=a.indexOf(val);if(i>=0)a.splice(i,1);else a.push(val);applyFilters()}
function applyFilters(){
  document.querySelectorAll('.tab-pane').forEach(function(pane){
    if(pane.style.display==='none')return;
    pane.querySelectorAll('.card').forEach(function(card){
      var show=true;
      for(var dim in FILT){var sel=FILT[dim];if(!sel.length)continue;var v=card.getAttribute('data-'+dim)||'';if(sel.indexOf(v)<0){show=false;break;}}
      card.style.display=show?'':'none';
    });
  });
  document.querySelectorAll('.chip[data-dim]').forEach(function(c){
    var d=c.getAttribute('data-dim'),v=c.getAttribute('data-val');
    if(FILT[d]&&FILT[d].indexOf(v)>=0)c.classList.add('active');else c.classList.remove('active');
  });
}
function resetFilters(){for(var d in FILT)FILT[d]=[];applyFilters()}
</script>"""

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>盘前报告 {date}</title>
<style>
  :root{{--bg:#0a0d14;--card:#141821;--c2:#1a1f2e;--bd:#252b3d;--hv:#1e2436;--tx:#c8d0dc;--dim:#5a6378;--grn:#22c55e;--red:#ef4444;--ylw:#eab308;--blu:#3b82f6;--pur:#a855f7}}
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{background:var(--bg);color:var(--tx);font-family:-apple-system,'Segoe UI','Noto Sans SC',sans-serif;line-height:1.6}}
  .top{{position:sticky;top:0;z-index:100;background:rgba(10,13,20,.92);backdrop-filter:blur(10px);border-bottom:1px solid var(--bd);padding:10px 16px}}
  .top-in{{max-width:1100px;margin:0 auto;display:flex;align-items:center;gap:12px;flex-wrap:wrap}}
  .top h1{{font-size:1.1em;white-space:nowrap}}
  .date-tag{{background:var(--blu);color:#fff;padding:2px 8px;border-radius:4px;font-size:.8em}}
  .tabs{{display:flex;gap:2px;margin-top:6px}}
  .tab{{background:var(--card);border:1px solid var(--bd);color:var(--dim);padding:4px 14px;border-radius:6px 6px 0 0;cursor:pointer;font-size:.85em;border-bottom:none}}
  .tab:hover{{background:var(--hv);color:var(--tx)}}
  .tab.active{{background:var(--c2);color:var(--blu);border-color:var(--blu)}}
  .tab-num{{background:var(--bd);padding:0 5px;border-radius:8px;font-size:.8em;margin-left:2px}}
  .toolbar{{max-width:1100px;margin:0 auto;padding:6px 16px;display:flex;gap:6px}}
  .toolbar button{{background:var(--card);border:1px solid var(--bd);color:var(--dim);padding:3px 10px;border-radius:4px;cursor:pointer;font-size:.8em}}
  .toolbar button:hover{{background:var(--hv);color:var(--tx)}}
  .filter-bar{{max-width:1100px;margin:0 auto;padding:4px 16px 8px;display:flex;flex-wrap:wrap;gap:4px;align-items:center;border-bottom:1px solid var(--bd)}}
  .filter-bar .fg{{font-size:.74em;color:var(--dim);margin-left:8px}}
  .filter-bar .fg:first-of-type{{margin-left:0}}
  .chip{{background:var(--card);border:1px solid var(--bd);color:var(--dim);padding:2px 9px;border-radius:10px;cursor:pointer;font-size:.76em}}
  .chip:hover{{background:var(--hv);color:var(--tx)}}
  .chip.active{{background:var(--blu);border-color:var(--blu);color:#fff}}
  .chip.reset{{margin-left:auto;border-color:rgba(239,68,68,.4);color:var(--red)}}
  .layout{{max-width:1400px;margin:0 auto;display:flex;gap:12px;padding:8px 16px 40px;align-items:flex-start}}
  .wrap{{flex:1;min-width:0}}
  .sidebar{{width:280px;flex-shrink:0;position:sticky;top:64px;max-height:calc(100vh - 72px);overflow-y:auto}}
  .stat-box{{background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:10px;margin-bottom:8px}}
  .stat-title{{font-size:.8em;color:var(--dim);margin-bottom:6px}}
  .stat-row{{display:flex;gap:10px;align-items:baseline;font-size:.92em}}
  .stat-tot{{font-size:.74em;margin-top:4px}}
  .rank-sec{{background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:8px 10px;margin-bottom:8px}}
  .rank-h{{font-size:.8em;color:var(--dim);margin-bottom:4px;padding-bottom:4px;border-bottom:1px solid var(--bd)}}
  .rank-item{{display:flex;gap:6px;align-items:center;font-size:.78em;padding:3px 0}}
  .rank-item .rcode{{font-family:'JetBrains Mono',monospace;color:var(--grn);width:52px;flex-shrink:0}}
  .rank-item .rname{{flex:1;color:var(--tx);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  .rank-item .rtag{{font-size:.74em;padding:0 5px;border-radius:6px;background:var(--c2);flex-shrink:0}}
  .rank-item .rscore{{color:var(--dim);font-size:.76em;flex-shrink:0}}
  .rank-item .rmsg{{font-size:.72em;width:22px;text-align:right;flex-shrink:0;font-family:'JetBrains Mono',monospace}}
  .rank-item.pos .rtag{{color:var(--grn)}} .rank-item.chain .rtag{{color:var(--pur)}} .rank-item.neg .rtag{{color:var(--red)}}
  .wrap-old{{max-width:1100px;margin:0 auto;padding:8px 16px 40px}}
  .mini-stats{{display:flex;gap:16px;padding:8px 0;font-size:.85em;color:var(--dim)}}
  .mini-stats b{{color:var(--tx);font-size:1.2em}}
  .ok{{color:var(--grn)!important}} .bad{{color:var(--red)!important}}
  .diff-box{{padding:8px 12px;border-radius:6px;margin:4px 0 8px;font-size:.9em}}
  .diff-box.ok{{background:rgba(34,197,94,.08);border:1px solid rgba(34,197,94,.2)}}
  .diff-box.empty{{color:var(--dim);text-align:center}}
  .cards-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(520px,1fr));gap:6px}}
  .card{{background:var(--card);border:1px solid var(--bd);border-radius:8px;cursor:pointer;transition:.15s;overflow:hidden}}
  .card:hover{{border-color:#3a4055;background:var(--c2)}}
  .card.bull{{border-left:3px solid var(--grn)}} .card.bear{{border-left:3px solid var(--red)}} .card.neutral{{border-left:3px solid var(--ylw)}}
  .card.noise{{padding:4px 12px;opacity:.4;display:flex;gap:6px;align-items:center;cursor:default;font-size:.85em}}
  .card-head{{display:flex;align-items:center;gap:6px;padding:5px 12px;border-bottom:1px solid var(--bd)}}
  .tag{{font-size:.75em;font-weight:600;padding:1px 6px;border-radius:3px;background:var(--c2);color:var(--tx)}}
  .sent{{font-size:.8em;font-weight:600}}
  .auc-sum{{margin-left:auto;font-size:.8em}}
  .card-body{{padding:6px 12px}}
  .ctitle{{font-size:.92em;margin-bottom:4px}}
  .pills{{display:flex;flex-wrap:wrap;gap:3px;margin-bottom:4px}}
  .pill{{font-size:.75em;padding:1px 7px;border-radius:8px}}
  .pill.pos{{background:rgba(34,197,94,.12);color:var(--grn)}}
  .pill.neg{{background:rgba(239,68,68,.12);color:var(--red)}}
  .pill.chain{{background:rgba(168,85,247,.1);color:var(--pur)}}
  .stk-list{{display:flex;flex-wrap:wrap;gap:3px 10px}}
  .stk{{font-size:.85em}}
  .code{{font-family:'JetBrains Mono',monospace;color:var(--grn)}}
  .role{{font-size:.75em;color:var(--dim)}} .role.lead{{color:var(--ylw)}} .role.elastic{{color:var(--blu)}}
  .detail{{padding:6px 12px;border-top:1px solid var(--bd);background:rgba(0,0,0,.2)}}
  .auc-tbl{{width:100%;border-collapse:collapse;font-size:.8em}}
  .auc-tbl th{{text-align:left;padding:3px 6px;color:var(--dim);border-bottom:1px solid var(--bd)}}
  .auc-tbl td{{padding:2px 6px;border-bottom:1px solid var(--card)}}
  .nm{{color:var(--dim);font-size:.9em}}
  .reason{{font-size:.85em;color:var(--dim);padding:4px 0;border-top:1px solid var(--bd);margin-top:4px}}
  .src-link{{font-size:.8em;color:var(--blu);text-decoration:none;display:inline-block;margin-top:4px}}
  .dim{{color:var(--dim)}} .disclaimer{{text-align:center;color:var(--dim);font-size:.8em;padding:20px}}
  a.code,a.rcode{{text-decoration:none;-webkit-tap-highlight-color:transparent}}
  a.code:hover,a.rcode:hover{{text-decoration:underline}}
  @media (max-width:768px){{
    .top{{padding:6px 8px}}
    .top-in h1{{font-size:1em}}
    .top-in{{gap:6px}}
    .toolbar{{padding:4px 8px;flex-wrap:wrap}}
    .layout{{flex-direction:column;max-width:100%;padding:6px}}
    .wrap{{order:1}}
    .sidebar{{width:100%;position:static;max-height:none;order:2;margin-top:8px}}
    .cards-grid{{grid-template-columns:1fr}}
    .card{{min-width:0}}
    .filter-bar{{font-size:.82em;gap:3px;padding:4px 8px}}
    .filter-bar .fg{{margin-left:4px}}
    .mini-stats{{gap:10px;font-size:.78em;flex-wrap:wrap}}
    .rank-item{{font-size:.82em}}
    .stk{{font-size:.82em}}
  }}
</style>
</head>
<body>
<div class="top">
  <div class="top-in">
    <h1>📊 盘前报告 <span class="date-tag">{date}</span></h1>
    <span class="dim" style="font-size:.8em">⚠️ 不预测股价，不构成投资建议</span>
  </div>
  <div style="max-width:1100px;margin:4px auto 0;padding:0 16px"><div class="tabs">{tabs}</div></div>
</div>
<div class="toolbar">
  <button onclick="document.querySelectorAll('.detail').forEach(d=>d.style.display='block')">展开全部</button>
  <button onclick="document.querySelectorAll('.detail').forEach(d=>d.style.display='none')">折叠全部</button>
</div>
{filter_bar}
<div class="layout">
<div class="wrap">
{contents}
</div>
{sidebar_html}
</div>
<div class="disclaimer">⚠️ 不预测股价，不构成投资建议。</div>
__SCRIPT__
</body>
</html>'''.replace("__SCRIPT__", _SCRIPT)


def _parse_md(md: str) -> dict:
    """从 markdown 报告解析结构化数据。"""
    title_m = re.search(r'^# 📰 (.+)$', md, re.M)
    title = title_m.group(1).strip() if title_m else "（无标题）"
    is_noise = "判定为噪音" in md
    type_m = re.search(r'\| 事件类型 \| (.+?) \|', md)
    sent_m = re.search(r'\| 情绪 \| (.+?) \|', md)
    conf_m = re.search(r'\| 置信度 \| (.+?) \|', md)
    try: conf = float(conf_m.group(1).replace('%',''))/100
    except: conf = None
    ben_m = re.search(r'\*\*受益板块\*\*：(.+)', md)
    vic_m = re.search(r'\*\*受损板块\*\*：(.+)', md)
    reps = [{"code":m.group(1),"name":m.group(2).strip(),"role":m.group(3).strip()} for m in re.finditer(r'\| (\d{6}) \| (.+?) \| (.+?) \|', md)]
    pool_m = re.search(r'待竞价验证 watch_pool.*?`([^`]+)`', md, re.S)
    wp = pool_m.group(1).replace('`','').split(', ') if pool_m else re.findall(r'`(\d{6})`', md.split('watch_pool')[-1] if 'watch_pool' in md else md.split('待竞价')[-1] if '待竞价' in md else "")
    chain_m = re.search(r'\*\*扩散板块\*\*：(.+)', md)
    chain_s = [s.strip() for s in chain_m.group(1).split(",")] if chain_m else []
    reason_m = re.search(r'> (.+)', md)
    url_m = re.search(r'\*\*链接\*\*：(https?://\S+)', md)
    return {
        "title":title,"is_noise":is_noise,"event_type":type_m.group(1).strip() if type_m else "",
        "sentiment":sent_m.group(1).strip() if sent_m else "","confidence":conf,
        "beneficiary_sectors":[s.strip() for s in ben_m.group(1).split(",")] if ben_m else [],
        "victim_sectors":[s.strip() for s in vic_m.group(1).split(",")] if vic_m and vic_m.group(1).strip()!="无" else [],
        "representative_stocks":reps,"watch_pool":wp,"chain_sectors":chain_s,
        "chain_reasoning":reason_m.group(1).strip() if reason_m else "",
        "url":url_m.group(1) if url_m else None,
    }

import re as re
