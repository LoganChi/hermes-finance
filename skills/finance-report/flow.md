# 财经报导 → 飞书云文档 · 全流程

> 本文件供**维护者**阅读，描述 `finance-report` skill 所嵌入的完整报告管线。
> skill 正文（SKILL.md）只覆盖 Phase 1；本图覆盖全链路，方便排查与扩展。

## 一、完整链路

```mermaid
flowchart TD
    Trigger[触发入口<br/>飞书消息 / 定时任务] --> G1{Gate 1<br/>report-flow 模块命中?}
    G1 -->|否| Free[自由 LLM 循环<br/>skill 作为普通能力注入]
    G1 -->|是| G2{Gate 2<br/>消息含 reportKeywords?<br/>日报/周报/报告/摘要/brief/report}
    G2 -->|否| Free
    G2 -->|是| Pipeline[ReportOrchestrator<br/>确定性 4 阶段管线]

    Pipeline --> P1
    subgraph P1 [Phase 1 · 搜索提炼 ← finance-report 在此注入]
        P1a[SkillBlockBuilder<br/>按消息匹配 skill 正文] --> P1b[web_search 5-7 维度<br/>+ web_fetch 最多 3 页]
        P1b --> P1c[提炼 2000-4000 字笔记<br/>按财经 6 维度组织]
        P1c --> P1d[memory 存笔记<br/>代码剥离飞书 URL]
    end

    P1 --> P2
    subgraph P2 [Phase 2 · 建文档 + 封面]
        P2a[LLM 写正文 4000-8000 字<br/>正文禁任何 URL] --> P2b[feishu_cli create_doc]
        P2b --> P2c[image_gen 封面 1920x1080]
    end

    P2 --> P3
    subgraph P3 [Phase 3 · 插配图]
        P3a[feishu_cli read_doc 读章节] --> P3b[LLM 生成 2-3 配图 prompt]
        P3b --> P3c[逐张 image_gen 1024x1024<br/>+ feishu_cli insert_media]
    end

    P3 --> P4[Phase 4 · 自然语言总结<br/>LLM 150-300 字 · 30s 超时降级]
    P4 --> Done[飞书云文档链接<br/>+ 总结回传飞书]
```

## 二、Phase 1 财经数据源路由

```mermaid
flowchart LR
    Req[财经报导需求] --> Dim{内容维度}
    Dim -->|指数/个股/行情| QQ[腾讯批量接口<br/>1 次 web_fetch 拿全]
    Dim -->|政策/快讯/宏观| SR[web_search<br/>财联社/华尔街见闻/金十]
    Dim -->|汇率/商品/外围| SR2[web_search 专项]
    Dim -->|舆情/热点| MS[macro-sentinel<br/>NewsNow 多源]
    QQ --> Notes[6 维度财经笔记]
    SR --> Notes
    SR2 --> Notes
    MS --> Notes
    Notes --> P2[Phase 2 正文]
```

> web_fetch 全管线硬上限 3 次。**必须批量**（腾讯接口一次拿 N 只），否则会浪费在单只个股上、漏掉汇率与商品。

## 三、触发词与"进不了管线"的陷阱

skill 触发词只覆盖**能进报告管线**的说法（Gate 2 的 reportKeywords 含 `日报/周报/报告/摘要/report/brief`）：

```
财经日报 / 财经周报 / 市场日报 / 财经报告 / 财经分析报告 / 财经摘要 / finbrief / finance report
```

**以下高频说法目前进不了报告管线**（reportKeywords 不含它们，会落到自由 LLM，此时本 skill 的「Phase 1」声明不成立）：

```
财经早报 / 晨报 / 盘后总结 / 盘前参考 / 收盘总结 / 财经简报 / 财经报导
```

若要支持这些说法，需改 Claw 代码（不在本 skill 范围）：
- `FeishuWebhook.cs` 的 `reportKeywords` 数组加词：`早报 / 晨报 / 盘后 / 盘前 / 收盘 / 简报 / 报导`
- 同步在 `PromptModuleSelector.cs` 的 `report-flow` 关键词里加上对应词，保持两道 Gate 一致

## 四、与兄弟 skill 的边界

| Skill | 职责 | 触发词特征 |
|-------|------|-----------|
| **finance-report**（本 skill） | 维度编排 + web_fetch 预算 + 财经红线 | 财经日报 / 周报 / 报告 |
| stock-data | A 股个股行情接口（腾讯 / 新浪）字段与解析 | 股价 / 股票 / 行情 / A股 |
| macro-sentinel | 宏观舆情分析、行业热力图、方向判断 | 宏观 / 舆情 / 热点 / 行业 / 板块 |
| quant-analyst | 量化策略、回测、因子 | 量化 / 回测 / 策略 / 因子 |

> 多个 skill 可在 Phase 1 **同时注入**（SkillSelector 无优先级去重，各自独立打分 ≥5 即展开）。本 skill 正文已声明「行情细节用 stock-data、舆情用 macro-sentinel」，避免重复采集。

## 五、依赖

本 skill 仅在 **Hermes / Yubo.AI.Claw 报告管线**内有效，依赖：

- **工具**：`web_search` / `web_fetch` / `memory`（Phase 1 直接使用）；`feishu_cli` / `image_gen`（后续阶段，本 skill 不直接调用）
- **兄弟 skill**：`stock-data`（行情接口）、`macro-sentinel`（舆情源）
- **代码**：`ReportOrchestrator`（4 阶段管线）、`SkillBlockBuilder`（Phase 1 注入）、`FeishuWebhook`（Gate 2）

## 六、安装

在 Hermes / Yubo.AI.Claw 的 skill 商店安装，GitHub 源填：

```
LoganChi/hermes-finance/skills/finance-report
```

安装后位于 `Skills/store-finance-report/`，`meta.json` 的 `Enabled` 控制是否加载。
