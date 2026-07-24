# hermes-finance

Hermes / Yubo.AI.Claw 的 **财经投资** skill 仓库。

通过 Hermes（Yubo.AI.Claw）的 skill 商店安装，传入 GitHub 源即可：

```
LoganChi/hermes-finance/skills/<skill-name>
```

## Skills

| Skill | 说明 |
|-------|------|
| [finance-report](skills/finance-report/) | 端到端财经报导生成（复刻 Hermes/Claw 报告管线 5 步）。**自带 5 个脚本**：行情 / 搜索 / 飞书云文档 / 图像生成 / md校验。完整流程图见 [flow.md](skills/finance-report/flow.md) |
| [event-driven-report](skills/event-driven-report/) | A 股事件驱动盘前报告的 **端到端自包含 pipeline**：多源新闻（财联社/华尔街见闻/央视）→ 事件抽取 → 标的映射 → 产业链扩散 → [竞价验证] → 多 tab HTML 报告。不预测股价，防幻觉，防未来函数。完整流程图见 [flow.md](skills/event-driven-report/flow.md) |

> finance-report 的 `scripts/`（行情 / 搜索 / 飞书 / 生图 / md校验）自包含，可在任意 agent 框架使用；需 `TAVILY_API_KEY` + `SENSENOVA_API_KEY` + lark-cli 认证。web_fetch / memory 用框架自带的。

## Skill 类型对比

两个 skill 互补并列，不是替代——`finance-report` 回答"今天市场发生了什么"，`event-driven-report` 回答"这条新闻利好哪些标的、资金确认了没有"。

| 维度 | finance-report | event-driven-report |
|------|----------------|---------------------|
| 定位 | 宏观综述 / 日报周报 | 事件驱动 / 标的映射 |
| 形态 | 轻量（方法论 + 自包含脚本） | **重型自包含包**（完整 Python pipeline） |
| 依赖 | Python 标准库 + lark-cli | `pip install -r requirements.txt`（pandas/akshare/pydantic 等 6 个） |
| 凭证 | `SENSENOVA_API_KEY` + lark-cli | `DEEPSEEK_API_KEY`（缺失静默降级 mock） |
| 产出 | 飞书云文档 | 本地 HTML（`reports/daily_<日期>.html`） |
| 触发词 | 财经日报/周报/市场综述 | 事件驱动/盘前扫描/标的映射/催化扫描 |

**重型特例声明**：`event-driven-report` 是本仓库目前唯一的"重型 skill"——首次使用需：

```bash
cd skills/event-driven-report
pip install -r requirements.txt
export DEEPSEEK_API_KEY=sk-xxx        # PowerShell: $env:DEEPSEEK_API_KEY = 'sk-xxx'
python scripts/gen_weekend_report.py --today
```
