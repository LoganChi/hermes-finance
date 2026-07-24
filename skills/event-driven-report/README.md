# event-driven-report

A 股事件驱动盘前报告生成 skill —— 多源新闻 → 事件抽取 → 标的映射 → 产业链扩散 → [竞价验证] → HTML 报告。自包含 Python pipeline，clone 即跑。

> 这是 hermes-finance 仓库里唯一的**重型 skill**（需 `pip install` + API key），与轻量指引型的 [finance-report](../finance-report/) 不同。完整方法论见 [SKILL.md](SKILL.md)，内部流程图见 [flow.md](flow.md)。

## 快速上手

```bash
# 1. 装依赖（6 个必需包）
pip install -r requirements.txt

# 2. 配 LLM key（缺失会静默降级 mock，结果仅 demo）
export DEEPSEEK_API_KEY=sk-xxx        # PowerShell: $env:DEEPSEEK_API_KEY = 'sk-xxx'

# 3. 生成今日盘前报告
python scripts/gen_weekend_report.py --today
# → reports/daily_<日期>.html
```

## 目录
- `src/` — 核心 pipeline（news / analysis / report / auction / trend / strategy / discovery）
- `config/` — settings + event_rules + prompts + report_templates
- `data/` — sector_map（防幻觉根基）+ industry_chain（产业链扩散）+ demo_news
- `scripts/` — gen_weekend_report（主入口）+ jsonl_news_source + run_report（wrapper）

## 验证安装
```bash
python -c "from src.config import Config; c=Config.load(); print('sectors', len(c.sector_map))"
# 不报 FileNotFoundError = 路径结构正确
```

## 数据源
财联社电报 + 华尔街见闻（经 newsnow 聚合，财联社会回填正文）+ 央视 / 东财（akshare）。全部免费、无需 token。

## 维护说明
本 skill 的开发正本在 `Earn` 仓库，此处为**发布镜像**。pipeline 改动先在 Earn 验证、稳定后手动同步过来。同步时整目录复制 `src/ config/ data/ scripts/`（路径全 `Path(__file__)` 相对，零代码改动）。

## 红线
不预测股价 / 防未来函数 / 防幻觉（标的代码必须来自 sector_map）/ 不编造数据。详见 [SKILL.md](SKILL.md)。
