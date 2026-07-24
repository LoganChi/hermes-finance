---
name: finance-report
description: 端到端财经报导生成 skill。复刻 Hermes/Yubo.AI.Claw 的 ReportOrchestrator 报告管线：话题→多源数据采集→结构化分析→图文云文档→交付。自包含、可移植，工具按职能匹配、数据接口可替换。适用于财经日报/周报/市场综述/盘后总结。
triggers: ["财经日报", "财经周报", "市场日报", "财经报告", "财经分析报告", "财经摘要", "finbrief", "finance report"]
tags: ["财经", "报导", "日报", "周报", "市场综述", "云文档", "可移植"]
---

# finance-report · 财经报导生成（端到端）

把一份完整财经报导从「话题」做到「图文云文档」，拆成 **5 个确定性步骤**，复刻自 Hermes / Yubo.AI.Claw 的 `ReportOrchestrator` 报告管线。自包含、可移植到任意 agent 框架。

## 两种使用模式

| 模式 | 适用 | 行为 |
|------|------|------|
| **独立使用** | 其他 agent 框架 / 手动 | 照 Step 0→4 全跑，产出云文档 |
| **Hermes/Claw 管线内** | 已装在 Claw 报告管线 | 你只做 Step 0-1（搜索提炼）；Step 2-4 由管线其他阶段的独立 LLM 处理，**不要越权建文档/生图** |

> 怎么判断你在哪种模式：若上方 prompt 出现「你处于报告生成流程的第1阶段」字样 → 你在 Claw 管线内，只做 Step 0-1。

## 工具与脚本（自包含 + 框架能力）

**本 skill 自带脚本**（覆盖管线的全部平台集成，clone 即用）：

| 职能 | 脚本 | 凭证 | 实测 |
|------|------|------|------|
| 行情抓取 | `scripts/fetch_quote.py` | 无（公开接口） | ✅ 真实行情 |
| 飞书云文档（建/读/插图） | `scripts/feishu_doc.py` | `FEISHU_APP_ID` + `FEISHU_APP_SECRET` | 直连 OpenAPI，无 lark-cli 依赖 |
| 图像生成（封面/配图） | `scripts/gen_image.py` | `SENSENOVA_API_KEY` | ✅ 真实生图 |

> `feishu_doc.py` 直连飞书 OpenAPI（需 `FEISHU_APP_ID` + `FEISHU_APP_SECRET` 环境变量）。内置 Markdown→docx blocks 转换，支持标题/列表/段落。若用其他文档平台（Notion/Google Docs），替换此脚本即可。

**框架能力**（用你 agent 框架自带的，不在 skill 内重造）：

| 职能 | Hermes/Claw 里的工具 | 说明 |
|------|---------------------|------|
| 网页搜索 | web_search | 接搜索 API |
| 网页抓取 | web_fetch | HTTP 抓取 |
| 执行脚本 | shell | 跑上面的 python 脚本 |
| 持久笔记 | memory | 可选，跨会话 |

> ⚠️ **数据接口需自行验证**：财联社、华尔街见闻、金十等新闻源可能受网络/区域/反爬限制，访问失败请替换为等价源。

## 工作流（5 步）

### Step 0 · 行情预取（脚本，确定性）

把"接口调用 + 字段解析"这件活从 LLM 手里拿走，交给自包含脚本：

```bash
python scripts/fetch_quote.py                    # 默认: 上证/深证/创业板/科创50/茅台
python scripts/fetch_quote.py 600519 000001       # 指定代码（自动识别市场前缀）
python scripts/fetch_quote.py sh000001,sz399001   # 批量，逗号分隔
```

输出结构化 JSON（name / price / change_pct / volume / amount / pe / trend）。仅 Python 标准库，无第三方依赖。
> Claw 管线模式下，这步由 `ReportOrchestrator` 代码自动调用并注入「已预取的实时行情」区块，你直接引用、不要再调腾讯接口。

### Step 1 · 搜索与提炼

并行 `web_search` 5-7 个维度查询 + `web_fetch` 深读最多 3 个关键页面，提炼 **2000-4000 字笔记**，按下方 6 维度组织，存入 `memory`（key: `report-notes-{日期}`）。

**web_fetch 3 次预算**：第 1 次 深度要闻、第 2 次 汇率/商品/外围、第 3 次 兜底。行情已由 Step 0 预取时，省下的预算全留给要闻。

### Step 2 · 创建文档 + 封面图

- 基于笔记撰写报告正文（Markdown，4000-8000 字，结构：摘要 → 分章节正文 → 总结），存为 `report.md`
- 创建云文档：
  ```bash
  python scripts/feishu_doc.py create_doc --title "财经日报" --file report.md
  ```
  从返回 JSON 取 `document_id`
- 生成封面图：
  ```bash
  python scripts/gen_image.py --prompt "..." --size 1920x1080
  ```
  从返回 JSON 取 `saved_path`
- **正文禁止任何 URL**；外部链接只放在文末「## 参考来源」章节

### Step 3 · 插入配图

- 读文档章节结构：`python scripts/feishu_doc.py read_doc --doc <document_id>`
- 为 2-3 个核心章节生成配图 prompt（具体描述画面/色调/构图）
- 逐张生成 + 插入：
  ```bash
  python scripts/gen_image.py --prompt "..." --size 1024x1024                          # 拿 saved_path
  python scripts/feishu_doc.py insert_media --doc <id> --file <saved_path> --width 560 --align center --selection "章节标题"
  ```
- 图片**串行**生成（SenseNova 速率限制，间隔 ≥15s），单张失败跳过、不阻塞

### Step 4 · 总结交付

用 150-300 字自然语言告诉用户：做了什么、关键结论、文档链接。不要堆砌「已生成 / 已上传」执行回执式播报。

## 财经笔记 6 维度结构

每个维度 3-5 条要点，**必须带具体数字与时点**：

1. **市场总览**：上证 / 深证 / 创业板 / 科创50 收盘点位与涨跌幅、两市成交额、北向资金净流入
2. **要闻速递**：政策监管、宏观数据（CPI / PMI / 社融 / LPR）、重大公司事件（标日期）
3. **板块异动**：领涨 / 领跌板块及龙头、驱动事件（参照申万一级行业分类）
4. **数据看板**：人民币汇率（在岸/离岸）、原油 / 黄金 / 铜、外围市场（美股 / 纳指 / 恒生）
5. **后市展望**：机构观点与共识方向（标机构名），**不预测具体点位**
6. **风险提示**：地缘、政策、流动性、黑天鹅信号

## 数据源路由

| 维度 | 采集方式 |
|------|----------|
| 实时行情 / 指数 / 个股 | **Step 0 脚本预取**；无脚本时 `web_fetch` 腾讯批量 `qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688,sh600519` |
| 财经快讯 / 政策 / 宏观 | `web_search`：财联社 / 华尔街见闻 / 金十 / 「{日期} 财经要闻」 |
| 汇率 / 商品 / 外围 | `web_search` 专项 |
| 舆情 / 热点 | 若有 macro-sentinel 类 skill，用其多源采集补充 |

## 财经红线（不可违反）

- **数据标注时点**：行情写「收盘 / 盘中 HH:MM」，宏观数据写发布日期
- **URL 不内联正文**：写「据财联社 X 月 X 日报道」，URL 只列笔记末尾「候选来源」区（文档平台通常只允许在参考来源章节放链接）
- **不预测具体股价 / 点位**：展望只转述机构观点，不给「目标价 XX」
- **不编造数据**：接口失败或搜不到，该维度写「数据暂缺」，不填估数
- 笔记末尾附免责声明：「本报导仅供研究参考，不构成投资建议。」

## 脚本总览

| 脚本 | 作用 | 依赖 | 凭证 |
|------|------|------|------|
| `scripts/fetch_quote.py` | A 股行情抓取（腾讯 `qt.gtimg.cn`，代码识别 + 字段解析 + 涨跌方向） | Python 标准库 | 无 |
| `scripts/feishu_doc.py` | 飞书云文档（create_doc / read_doc / insert_media，直连 OpenAPI） | Python 标准库 | `FEISHU_APP_ID` + `FEISHU_APP_SECRET` |
| `scripts/gen_image.py` | 图像生成（直连 SenseNova，封面 + 配图，下载到本地） | Python 标准库 | `SENSENOVA_API_KEY` |

每个脚本 `python <script>.py --help` 查看用法，输出均为 JSON（`ok` / `error` / 结果字段）。

## 完整流程图

见同目录 `flow.md`：两张 mermaid（端到端完整链路 + Step 0 行情预取路由）+ 触发词约束 + 兄弟 skill 边界。
