# hermes-finance

Hermes / Yubo.AI.Claw 的 **财经投资** skill 仓库。

通过 Hermes（Yubo.AI.Claw）的 skill 商店安装，传入 GitHub 源即可：

```
LoganChi/hermes-finance/skills/<skill-name>
```

## Skills

### [finance-report](skills/finance-report/)

端到端财经报导生成（复刻 Hermes/Claw 报告管线 5 步）。适用于财经日报、周报、个股投资分析报告。

**自带 5 个脚本：**

| 脚本 | 功能 | 用法 | 凭证 |
|------|------|------|------|
| [`fetch_quote.py`](skills/finance-report/scripts/fetch_quote.py) | A股实时行情抓取（腾讯接口，代码自动识别+字段解析+涨跌方向） | `python fetch_quote.py 600519` / `python fetch_quote.py sh000001,sz399001` | 无 |
| [`search.py`](skills/finance-report/scripts/search.py) | 网页搜索 + 页面深读（Tavily search + extract 双模式，多 key 轮换，429 自动切换） | `python search.py search "财联社 今日" --max 5` / `python search.py extract "https://..."` | `TAVILY_API_KEY` |
| [`feishu_doc.py`](skills/finance-report/scripts/feishu_doc.py) | 飞书云文档操作（直连 OpenAPI：create_doc 建文档+分批写正文 / read_doc 读章节 / insert_media 插图） | `python feishu_doc.py create_doc --title "报告" --file report.md` | `FEISHU_APP_ID` + `FEISHU_APP_SECRET` |
| [`gen_image.py`](skills/finance-report/scripts/gen_image.py) | 图像生成（直连 SenseNova，封面 1920x1080 / 配图 1024x1024，下载到本地） | `python gen_image.py --prompt "..." --size 1920x1080` | `SENSENOVA_API_KEY` |
| [`lint_md.py`](skills/finance-report/scripts/lint_md.py) | Markdown 校验/规范化（7类检查：超链接/飞书URL/标题跳级/代码块/空链接，`--fix` 自动修复） | `python lint_md.py report.md --fix` / `python lint_md.py report.md --check` | 无 |

完整流程图见 [flow.md](skills/finance-report/flow.md)

---

### [event-driven-report](skills/event-driven-report/)

A 股事件驱动盘前报告的 **端到端自包含 pipeline**：多源新闻 → 事件抽取 → 标的映射 → 产业链扩散 → [竞价验证] → 多 tab HTML 报告。不预测股价，防幻觉，防未来函数。

**自带 3 个脚本：**

| 脚本 | 功能 | 用法 | 凭证 |
|------|------|------|------|
| [`gen_weekend_report.py`](skills/event-driven-report/scripts/gen_weekend_report.py) | 今日/盘前主入口，`--today` 输出多 tab HTML（四源新闻：财联社+华尔街见闻+金十+格隆汇） | `python gen_weekend_report.py --today` | `DEEPSEEK_API_KEY` |
| [`run_report.py`](skills/event-driven-report/scripts/run_report.py) | 仅标准库 thin wrapper，subprocess 调 gen_weekend_report，输出结构化 JSON（供程序调用） | `python run_report.py --today` | 同上 |
| [`jsonl_news_source.py`](skills/event-driven-report/scripts/jsonl_news_source.py) | jsonl 历史新闻适配器（把本地 jsonl 快照接入 pipeline，用于回测/回放） | 被 pipeline 内部调用 | 无 |

**内置 Python 包（`src/`）：**

| 模块 | 功能 |
|------|------|
| `src/news/` | 多源新闻采集（newsnow/akshare/tushare/demo/jsonl 五源，正文回填） |
| `src/analysis/extractor.py` | DeepSeek LLM 事件抽取（防幻觉清洗，code 必须 ∈ sector_map） |
| `src/analysis/mapper.py` | 标的映射 + 产业链扩散（sector_map + industry_chain） |
| `src/auction/` | 竞价验证（日K开盘价 vs 昨收 + 量比，判断资金确认） |
| `src/strategy/` | 市场风控 + 评分体系（HS300 七指标合成分 + RPS + 板块共振） |
| `src/trend/` | 技术指标（MACD/RSI/ATR/择时） |
| `src/report/` | 报告渲染（多 tab HTML + Markdown + 趋势标签） |
| `src/pipeline.py` | 完整 pipeline 编排（Stage 1-6 确定性链路） |

**配置文件（`config/`）：**

| 文件 | 作用 |
|------|------|
| `settings.yaml` | 数据源/LLM/新闻源/路径/竞价参数（key 走 `${ENV_VAR}` 占位） |
| `event_rules.yaml` | mock 归因规则（无 key 时用）+ 合法事件类型白名单 |
| `prompts.yaml` | LLM 抽取的 system+user 模板 |
| `report_templates.yaml` | 报告文案（章节标题/标签/免责声明） |

完整流程图见 [flow.md](skills/event-driven-report/flow.md)

---

## Skill 类型对比

两个 skill 互补并列，不是替代——[finance-report](skills/finance-report/) 回答"今天市场发生了什么"，[event-driven-report](skills/event-driven-report/) 回答"这条新闻利好哪些标的、资金确认了没有"。

| 维度 | [finance-report](skills/finance-report/) | [event-driven-report](skills/event-driven-report/) |
|------|----------------|---------------------|
| 定位 | 宏观综述 / 日报周报 / 投资分析 | 事件驱动 / 标的映射 / 盘前扫描 |
| 形态 | 轻量（方法论 + 自包含脚本） | **重型自包含包**（完整 Python pipeline） |
| 依赖 | Python 标准库 | `pip install -r requirements.txt`（pandas/akshare/pydantic 等 6 个） |
| 凭证 | `TAVILY_API_KEY` + `FEISHU_APP_ID/SECRET` + `SENSENOVA_API_KEY` | `DEEPSEEK_API_KEY`（缺失静默降级 mock）+ `TUSHARE_TOKEN`（可选） |
| 数据采集 | Tavily search + extract | newsnow/akshare 直采 + DeepSeek LLM 抽取 |
| 产出 | 飞书云文档 | 本地 HTML（`reports/daily_<日期>.html`） |
| 触发词 | 财经日报/周报/投资分析报告 | 事件驱动/盘前扫描/催化扫描 |

---

## 快速开始

### finance-report

```bash
cd skills/finance-report
export TAVILY_API_KEY="your-key"
export FEISHU_APP_ID="your-app-id"
export FEISHU_APP_SECRET="your-app-secret"
export SENSENOVA_API_KEY="your-key"

# 完整流程（agent 调用）
python scripts/fetch_quote.py 600519              # 行情预取
python scripts/search.py search "财经要闻" --max 5  # 维度搜索
python scripts/search.py extract "https://..."    # 深读页面
python scripts/lint_md.py report.md --fix          # 校验
python scripts/feishu_doc.py create_doc --title "财经日报" --file report.md
```

### event-driven-report

```bash
cd skills/event-driven-report
pip install -r requirements.txt
export DEEPSEEK_API_KEY=sk-xxx

python scripts/gen_weekend_report.py --today
# → reports/daily_2026-07-25.html
```
