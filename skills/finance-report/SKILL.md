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
| 飞书云文档（建/读/插图） | `scripts/feishu_doc.py` | lark-cli 已认证 | 逻辑移植自 Claw |
| 图像生成（封面/配图） | `scripts/gen_image.py` | `SENSENOVA_API_KEY` | ✅ 真实生图 |
| 网页搜索+深读 | `scripts/search.py` | `TAVILY_API_KEY`（可逗号分隔多 key） | ✅ 真实搜索（search + extract 两模式） |
| md 校验/规范化 | `scripts/lint_md.py` | 无 | ✅ 实测（7 类问题） |

> `feishu_doc.py` 封装飞书官方 lark-cli（`npm i -g @larksuite/cli` + `lark-cli auth login`）。原因：飞书 docx 创建接口不支持带正文，lark-cli 官方处理了 markdown→docx 转换，最可靠。若用其他文档平台（Notion/Google Docs），替换此脚本即可。

**框架能力**（用你 agent 框架自带的，不在 skill 内重造）：

| 职能 | Hermes/Claw 里的工具 | 说明 |
|------|---------------------|------|
| 网页抓取 | web_fetch | HTTP 抓取（深读搜索结果的全文） |
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

并行搜索 5-7 个维度 + `web_fetch`/`search.py extract` 深读关键页面：
```bash
python scripts/search.py search "财联社 今日财经要闻" --max 5
python scripts/search.py search "央行 LPR 调整 {月份}" --max 5
python scripts/search.py extract "https://finance.eastmoney.com/..."  # 深读页面正文
```

**web_fetch 3 次预算**：第 1 次 深度要闻、第 2 次 汇率/商品/外围、第 3 次 兜底。行情已由 Step 0 预取时，省下的预算全留给要闻。

### Step 2 · 创建文档 + 封面图

- 基于笔记撰写报告正文（Markdown，4000-8000 字，结构：摘要 → 分章节正文 → 总结），存为 `report.md`
- **校验 + 规范化 md**（create_doc 前必跑；lark-cli 不支持 `[text](url)` 超链接等）：
  ```bash
  python scripts/lint_md.py report.md --fix        # 自动修复：超链接→纯URL / 移除飞书URL
  python scripts/lint_md.py report.md --check      # 或只检查，有问题 exit 1（可 gating）
  ```
- 创建云文档：
  ```bash
  python scripts/feishu_doc.py create_doc --title "财经日报" --file report.md
  ```
  从返回 JSON 取 `document_id`（→ Step 3 要用）
- 生成封面图：
  ```bash
  python scripts/gen_image.py --prompt "..." --size 1920x1080
  ```
  从返回 JSON 取 `saved_path`（→ Step 3 要用）
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

## 阶段间状态传递

脚本输出 JSON，阶段间靠它传递状态（Hermes/Claw 里由 `ReportStateCollectorHook` 自动收集；独立使用时手动从 JSON 取）：

| 状态 | 来源 | 下一步用途 |
|------|------|-----------|
| `document_id` | `feishu_doc.py create_doc` 返回 | Step 3 `read_doc` / `insert_media` 的 `--doc` |
| `saved_path` | `gen_image.py` 返回 | Step 3 `insert_media` 的 `--file` |
| 来源链接 | `search.py` 的 `results[].url` | 报告「## 参考来源」章节 |
| 行情 JSON | `fetch_quote.py` 返回 | 笔记「市场总览」「数据看板」维度 |

> Hermes/Claw 还有个 `ReportStateCollectorHook`：在 `web_search` 执行后悄悄解析 `[N] Title / URL` 收集成 SourceLinks，喂给 Phase 2 参考来源章节。独立使用时，从 `search.py` 的 `results[].url` 手动收集即可。

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
| `scripts/feishu_doc.py` | 飞书云文档（create_doc / read_doc / insert_media，封装 lark-cli） | lark-cli | lark-cli auth |
| `scripts/gen_image.py` | 图像生成（直连 SenseNova，封面 + 配图，下载到本地） | Python 标准库 | `SENSENOVA_API_KEY` |
| `scripts/search.py` | 网页搜索+页面深读（Tavily search + extract，多 key 轮换，429 自动换 key） | Python 标准库 | `TAVILY_API_KEY` |
| `scripts/lint_md.py` | 报告 md 校验/规范化（行内超链接/飞书URL/标题跳级/代码块，针对 lark-cli 限制） | Python 标准库 | 无 |

每个脚本 `python <script>.py --help` 查看用法，输出均为 JSON（`ok` / `error` / 结果字段）。

## 完整流程图

见同目录 `flow.md`：两张 mermaid（端到端完整链路 + Step 0 行情预取路由）+ 触发词约束 + 兄弟 skill 边界。
