# hermes-finance

Hermes / Yubo.AI.Claw 的 **财经投资** skill 仓库。

通过 Hermes（Yubo.AI.Claw）的 skill 商店安装，传入 GitHub 源即可：

```
LoganChi/hermes-finance/skills/<skill-name>
```

## Skills

| Skill | 说明 |
|-------|------|
| [finance-report](skills/finance-report/) | 财经日报 / 周报 / 市场综述的 **Phase 1 搜索提炼指引**：财经数据源路由 + 笔记 6 维度结构 + 财经红线。完整流程图见 [skills/finance-report/flow.md](skills/finance-report/flow.md) |

> ⚠️ 这些 skill **紧耦合 Hermes / Yubo.AI.Claw 报告管线**（依赖 `feishu_cli` / `image_gen` / `web_search` 等工具与 `ReportOrchestrator` 管线）。独立使用需自行适配工具依赖。
