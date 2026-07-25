---
name: event-driven-report
description: A 股事件驱动盘前/盘后报告生成 skill。多源新闻(财联社/华尔街见闻/央视/东财)→事件抽取→标的映射→产业链扩散→[竞价验证]→多 tab HTML 报告。自包含 Python 包，确定性 pipeline，不预测股价。适用于盘前标的扫描、事件催化追踪、产业链扩散挖掘。
triggers: ["事件驱动", "盘前报告", "盘前扫描", "标的映射", "催化扫描", "catalyst scan", "event-driven report", "财联社快讯", "产业链扩散"]
tags: ["A股", "事件驱动", "盘前报告", "标的映射", "产业链", "竞价验证", "自包含", "重型"]
---

# event-driven-report · A 股事件驱动报告（端到端 pipeline）

把"新闻 → 事件归因 → 标的池 → 产业链扩散 → [竞价验证] → 多 tab HTML 报告"这条**确定性链路**封装成一个自包含 Python 包，clone 即跑。

与 [finance-report](../finance-report/) 互补并列：[finance-report](../finance-report/) 是"宏观综述/日报周报"导向（web_search + 笔记 6 维度 + 云文档）；本 skill 是"**事件驱动/标的映射**"导向——把每条新闻拆成「事件 + 受益板块 + 代表标的 + 产业链扩散 + 资金确认」，产出可直接扫描标的的 HTML 报告。

## 重型特例声明（务必先读）

本 skill **不是仅标准库的轻量指引**（如 finance-report），而是带完整 Python pipeline 的**重型 skill**：

- 需要 `pip install -r requirements.txt`（含 pandas/numpy/akshare/pydantic 等 6 个必需包）
- 需要 `DEEPSEEK_API_KEY`（缺失会**静默降级 mock**，结果仅 demo，不可当真）
- 不依赖 Hermes/Claw 工具管线，**独立可跑**

首次使用：`cd skills/event-driven-report && pip install -r requirements.txt`，配 `DEEPSEEK_API_KEY`，再 `python scripts/gen_weekend_report.py --today`。

## 两种运行模式

| 模式 | 入口 | 输出 | 适用 |
|------|------|------|------|
| **盘前/今日**（推荐起步） | `python scripts/gen_weekend_report.py --today` | `reports/daily_<日期>.html` | 每日开盘前扫描当日催化；跳过竞价验证（盘前无日K可验） |
| **完整 pipeline**（含竞价验证） | `python -c "from src.pipeline import run; run()"` | 控制台 Markdown 报告 | 盘后/复盘，用日K开盘价验证事件是否被资金确认 |

## 工作流（5 阶段，确定性）

### Stage 1 · 配置加载（`src/config.py`）
`Config.load()` 读 `config/settings.yaml` + 内容文件（sector_map/industry_chain/event_rules/prompts/report_templates/demo_news）。路径全部相对 `settings.yaml` 定位，`${ENV_VAR}` 占位符走环境变量（key 不落盘）。

### Stage 2 · 新闻采集（`src/news/`）
**数据源路由表**（关键设计）：

| 源 | 模块 | 用途 | 凭证 |
|----|------|------|------|
| newsnow 聚合 | `newsnow_source.py` | 财联社电报 + 华尔街见闻实时 + 金十数据（宏观/央行）+ 格隆汇（港股/A股），四源并发，财联社正文回填(~1.6k字) | 无（公开 API + 伪造 UA/Referer） |
| akshare cctv | `akshare_source.py` mode=cctv | 央视财经新闻（按日期，可回测） | 无 |
| akshare global | `akshare_source.py` mode=global | 东财全球实时快讯 | 无 |
| tushare | `tushare_source.py` | 备选（需付费 news 权限；中转站不支持 news） | `TUSHARE_TOKEN` |
| jsonl 快照 | `jsonl_news_source.py` | 周末累积模式历史回放 | 无 |

**财联社正文回填（关键设计）**：newsnow 返回的财联社电报**默认只有标题**，喂 LLM 信息量不足。`newsnow_source.py` 在拉到列表后，对每条 url 并发回抓财联社 detail 页正文（~1.6k 字），用 `apparent_encoding` 修 requests 把 UTF-8 当 latin-1 解的乱码，正则去标签。华尔街见闻是 SPA 抓不到正文，保持 None 由 extractor 兜底。失败/超时不阻断主流程。

> 为什么要回填：标题太短，LLM 只能靠一句标题做事件抽取+标的映射，信息量不够。正文回填让 LLM 拿到完整上下文。**注意：质量要看标的映射准确性，不是噪音率**——噪音率受新闻样本影响、跨天不可直接对比，不是质量指标。

### Stage 3 · 事件抽取（`src/analysis/extractor.py`）
DeepSeek（OpenAI 兼容）按 `config/prompts.yaml` 的 system+user 模板抽取 → 结构化事件。两条防幻觉铁律：
- **代码必须真实**：`representative_stocks` 的 code 只能取自 `sector_map.json`，LLM 编造的代码经 `_sanitize` 一律丢弃
- **噪音过滤**：与 A 股板块因果链无关的纯娱乐/八卦 → `is_noise=true`，下游跳过

无 `DEEPSEEK_API_KEY` 时降级 `_mock_extract`（基于 `event_rules.yaml` 关键词规则），**结果仅 demo**。

### Stage 4 · 标的映射 + 产业链扩散（`src/analysis/mapper.py`）
- 受益板块 → `sector_map.json` 查表 → `watch_pool`（前 topn=8 只）
- 沿 `industry_chain.json` 扩散到上下游板块 → `chain_pool`（独立于 watch_pool）
- 受损板块独立收集 → `victim_pool`（不进 watch_pool）

### Stage 5 · [可选] 竞价验证（`src/auction/`）
仅在 `pipeline.run()` 且 `settings.auction.enabled=true` 时跑。用日K开盘价（集合竞价 9:25 结果）vs 昨收 + 量比，判断"资金确认/高开过多/无明显异动"。**`--today` 模式跳过**（盘前无日K）。akshare 易限流，失败有兜底。

### Stage 6 · 报告渲染（`src/report/`）
- `html_renderer.render_html_tabbed`：单文件多 tab（按新闻源切 tab），事件卡片 + 趋势标签 + 板块共振
- `renderer.render_report`：Markdown 单条报告（pipeline.run 用）
- 文案全部来自 `config/report_templates.yaml`

## 红线（不可违反）

- **不预测股价**：sentiment(利好/利空/中性) 描述的是"事件对板块的因果方向"，属事件归因，**不是股价预测**。系统绝不输出买卖信号/目标价。
- **防未来函数**（竞价验证阶段）：只用事件日**之前**已公开的日K数据，绝不偷看事件后涨跌做归因
- **防幻觉**：标的代码必须来自 `sector_map.json` 真实代码，LLM 输出经清洗，编造代码一律丢弃
- **不编造数据**：行情/新闻接口失败时写"数据暂缺"或返回 None，不填估数

## 报告结构（HTML 多 tab）
每个 tab = 一个新闻源，含：
- **大盘 regime 标签**（强/偏多/中性/偏空/弱，基于 HS300 七指标合成分；akshare 限流时显示"未知"）
- **事件卡片**：标题 + 来源 + 事件类型/情绪/置信度 + 受益板块 pill + 代表标的表 + watch_pool + 产业链扩散板块 + [竞价验证结果] + 趋势标签
- 噪音事件折叠为一行 badge
- 缺失板块提示（LLM 归因提到但 sector_map 没有的板块，建议补表）

## 配置文件说明
| 文件 | 作用 |
|------|------|
| `config/settings.yaml` | 数据源/LLM/新闻源/路径/竞价参数；key 走 `${ENV_VAR}` 占位 |
| `config/event_rules.yaml` | mock 归因规则（无 key 时用）+ 合法事件类型白名单 |
| `config/prompts.yaml` | LLM 抽取的 system+user 模板，防幻觉约束写死在 system |
| `config/report_templates.yaml` | 报告文案（章节标题/标签/免责声明） |
| `data/sector_map.json` | 板块→成分股映射（防幻觉根基） |
| `data/industry_chain.json` | 板块上下游图谱（产业链扩散） |

## 脚本总览
| 脚本 | 作用 | 用法 | 标准库? | 凭证 |
|------|------|------|--------|------|
| `scripts/gen_weekend_report.py` | 今日/盘前主入口。`--today` 模式拉四源新闻（财联社+华尔街见闻+金十+格隆汇）→ DeepSeek 抽取 → 标的映射 → HTML。跳过竞价验证（盘前无日K） | `python gen_weekend_report.py --today` | ✗（全套依赖） | `DEEPSEEK_API_KEY` |
| `scripts/run_report.py` | 仅标准库 thin wrapper，subprocess 调 gen_weekend_report，输出结构化 JSON（`ok/error/html_path/news_count`），供上层 agent 框架程序化调用 | `python run_report.py --today` / `--today --open`（自动打开浏览器） | ✓ | 无（自身） |
| `scripts/jsonl_news_source.py` | jsonl 历史新闻适配器。把本地 jsonl 快照（每行一个 json dict）映射成 NewsItem，接入 pipeline。用于周末累积模式或历史回放 | 被 pipeline 内部调用（`news.source=jsonl`） | ✓ | 无 |

## 完整流程图
见同目录 `flow.md`：mermaid 画 news→extract→map→chain→auction→render 全链路 + 数据源路由。

## 安装

```bash
cd skills/event-driven-report
pip install -r requirements.txt
export DEEPSEEK_API_KEY=sk-xxx        # Linux/macOS
# Windows PowerShell: $env:DEEPSEEK_API_KEY = 'sk-xxx'
python scripts/gen_weekend_report.py --today
```

> 本 skill 的开发正本在 `Earn` 仓库，此处为发布镜像。pipeline 改动先在 Earn 验证、稳定后同步过来。
