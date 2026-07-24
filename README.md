# hermes-finance

Hermes / Yubo.AI.Claw 的 **财经投资** skill 仓库。

通过 Hermes（Yubo.AI.Claw）的 skill 商店安装，传入 GitHub 源即可：

```
LoganChi/hermes-finance/skills/<skill-name>
```

## Skills

| Skill | 说明 |
|-------|------|
| [finance-report](skills/finance-report/) | 端到端财经报导生成（复刻 Hermes/Claw 报告管线 5 步）。**自带 3 个脚本**：行情抓取 / 飞书云文档 / 图像生成。完整流程图见 [flow.md](skills/finance-report/flow.md) |

> finance-report 的 `scripts/`（行情 / 飞书 / 生图）自包含，可在任意 agent 框架使用；仅需 `SENSENOVA_API_KEY` 与 lark-cli 认证。web_search / web_fetch / memory 用你框架自带的。
