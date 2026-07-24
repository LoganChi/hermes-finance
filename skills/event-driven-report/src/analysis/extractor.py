"""事件抽取层 —— 把一条 NewsItem 映射成结构化事件 EventExtraction。

设计原则（铁律）：
- 本系统是"事件驱动映射"系统，绝不预测股价、不输出买卖/目标价判断。
  sentiment(利好/利空/中性) 描述的是"事件对板块的因果方向"，属于事件归因，不是股价预测。
- 防幻觉：无论 mock 还是真实 LLM，representative_stocks 的 code 只能取自 sector_map 的真实代码，
  绝不编造任何股票代码。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from src.news.base import NewsItem

logger = logging.getLogger(__name__)


# ===================== 数据结构 =====================

class EventExtraction(BaseModel):
    """单条新闻抽取出的结构化事件。"""

    source_news_id: str = Field(..., description="关联的 NewsItem.id")
    event_type: str = Field(
        ...,
        description="事件类型：供给收缩|政策利好|技术突破|业绩|并购重组|黑天鹅|需求变化|中性|噪音",
    )
    sentiment: str = Field(..., description="事件方向：利好|利空|中性（事件对板块的因果方向，非股价预测）")
    confidence: float = Field(..., description="置信度 0.0~1.0")
    time_horizon: str = Field(..., description="影响周期：短期|中期")
    beneficiary_sectors: list[str] = Field(default_factory=list, description="受益板块（必须是 sector_map 里的板块名）")
    victim_sectors: list[str] = Field(default_factory=list, description="受损板块（必须是 sector_map 里的板块名）")
    key_entities: list[str] = Field(default_factory=list, description="关键实体/关键词")
    representative_stocks: list[dict] = Field(
        default_factory=list,
        description='代表性股票 [{"code","name","role"}]，code 必须来自 sector_map 真实代码',
    )
    chain_reasoning: str = Field(..., description="因果链，必填：事件→板块 的逻辑推理过程")
    llm_watch_hint: list[str] = Field(default_factory=list, description="LLM/mock 提示池(仅供参考)；下游待竞价验证池一律以 mapper.map_to_pool() 返回的 map_result['watch_pool'] 为准")
    is_noise: bool = Field(False, description="True 则视为噪音，extract_event 将返回 None")

    @field_validator("confidence")
    @classmethod
    def _check_confidence(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence 必须在 0.0~1.0 之间，收到 {v}")
        return v


# ===================== 抽取器 =====================

class EventExtractor:
    """把 NewsItem 抽取为 EventExtraction。

    provider=="mock" 或无 api_key → 走内置规则 _mock_extract（保证 demo 跑通）；
    否则 → 走真实 LLM _llm_extract，失败回退 _mock_extract。
    """

    def __init__(self, llm_config: dict, sector_map: dict, event_rules: dict, prompts: dict):
        self.llm_config = llm_config or {}
        self.event_rules: dict = event_rules or {}
        self.prompts: dict = prompts or {}
        # sector_map 形如 {"锂矿":[{"code":"002460","name":"赣锋锂业"}, ...], ...}
        # 过滤掉以 "_" 开头的说明键（如 "_说明"）
        self.sector_map: dict[str, list[dict]] = {
            k: v for k, v in sector_map.items() if not str(k).startswith("_")
        }
        # 合法事件类型白名单（来自 event_rules，真实/mock 共用）
        self._valid_event_types: set[str] = set(self.event_rules.get("valid_event_types") or [])
        # 预计算合法板块名 / 合法代码集合 —— 防幻觉的根基
        self._valid_sectors: set[str] = set(self.sector_map.keys())
        self._valid_codes: set[str] = {
            item["code"] for stocks in self.sector_map.values() for item in stocks
        }
        # code → name 反查表
        self._code2name: dict[str, str] = {
            item["code"]: item["name"]
            for stocks in self.sector_map.values()
            for item in stocks
        }

    # ---------------- 公共入口 ----------------

    def extract_event(self, news: NewsItem) -> Optional[EventExtraction]:
        """抽取入口：噪音返回 None，否则返回 EventExtraction。"""
        provider = self.llm_config.get("provider", "mock")
        api_key = self.llm_config.get("api_key", "")

        if provider == "mock" or not api_key:
            event = self._mock_extract(news)
        else:
            event = self._llm_extract(news)

        # 铁律：无论哪条路径，都做一次代码防幻觉清洗
        event = self._sanitize(event)

        if event.is_noise:
            return None
        return event

    # ---------------- Mock 规则归因 ----------------

    def _mock_extract(self, news: NewsItem) -> EventExtraction:
        """基于 news.title 关键词规则归因，保证 demo 跑通。命中即用，不命中→噪音。"""
        title = news.title or ""
        # key_entities：从 title 里挑出已知板块名 / 已知股票名
        entities = self._extract_entities(title)

        # 规则引擎：按 event_rules.rules 顺序匹配，命中即用；否则用 default
        matched = None
        for rule in self.event_rules.get("rules") or []:
            if self._match_rule(title, rule):
                matched = rule
                break

        if matched:
            event_type = str(matched.get("event_type", "噪音"))
            sentiment = str(matched.get("sentiment", "中性"))
            beneficiary = list(matched.get("beneficiary_sectors") or [])
            victim = list(matched.get("victim_sectors") or [])
            chain = str(matched.get("chain_reasoning") or "")
            confidence = float(matched.get("confidence", 0.5) or 0.5)
        else:
            d = self.event_rules.get("default") or {}
            event_type = str(d.get("event_type", "噪音"))
            sentiment = str(d.get("sentiment", "中性"))
            beneficiary = []
            victim = []
            chain = str(d.get("chain_reasoning") or "")
            confidence = float(d.get("confidence", 0.5) or 0.5)

        is_noise = event_type == "噪音"

        # representative_stocks / llm_watch_hint：只从 sector_map 真实代码取
        rep_stocks = self._pick_representative_stocks(beneficiary)
        watch_pool = self._build_watch_pool(beneficiary)

        mock_cfg = self.event_rules.get("mock") or {}
        return EventExtraction(
            source_news_id=news.id,
            event_type=event_type,
            sentiment=sentiment,
            confidence=confidence,
            time_horizon=str(mock_cfg.get("time_horizon", "短期")),
            beneficiary_sectors=beneficiary,
            victim_sectors=victim,
            key_entities=entities,
            representative_stocks=rep_stocks,
            chain_reasoning=chain,
            llm_watch_hint=watch_pool,
            is_noise=is_noise,
        )

    # ---------------- Prompt 构造（真实 LLM 用） ----------------

    def build_prompt(self, news: NewsItem, candidate_info: str) -> str:
        """从 config/prompts.yaml 读取模板构造 prompt（system + user 合并为单段文本）。

        防幻觉约束写在 prompts.yaml 的 system 模板里；占位符在此填充。
        """
        pe = (self.prompts.get("event_extraction") or {})
        system = pe.get("system") or ""
        user_tpl = pe.get("user_template") or ""
        fallback = pe.get("content_fallback", "(无正文)")
        max_chars = int(pe.get("content_max_chars", 800) or 800)
        content = (news.content or fallback)[:max_chars]
        user_block = user_tpl.format(
            candidate_info=candidate_info,
            title=news.title,
            content=content,
        )
        return system + "\n" + user_block

    def _build_candidate_info(self) -> str:
        """把 sector_map 的 板块名→代码列表 序列化成文本，供 prompt 注入。"""
        lines = []
        for sector, stocks in self.sector_map.items():
            codes = ", ".join(f"{s['code']}({s['name']})" for s in stocks)
            lines.append(f"- {sector}: {codes}")
        return "\n".join(lines)

    # ---------------- 真实 LLM 抽取 ----------------

    def _llm_extract(self, news: NewsItem) -> EventExtraction:
        """调用真实 LLM 抽取，失败则回退 _mock_extract。"""
        candidate_info = self._build_candidate_info()
        prompt_text = self.build_prompt(news, candidate_info)

        max_retries = int(self.llm_config.get("max_retries", 2) or 2)

        try:
            # 真实 HTTP 调用点：依赖 openai 库（兼容 deepseek/智谱/kimi 等 openai 接口）
            from openai import OpenAI  # noqa: WPS433 故意延迟导入，避免强依赖
        except ImportError:
            logger.warning("openai 库未安装，回退 mock 抽取。news_id=%s", news.id)
            return self._mock_extract(news)

        base_url = self.llm_config.get("base_url") or None
        api_key = self.llm_config.get("api_key") or ""
        model = self.llm_config.get("model") or ""
        temperature = float(self.llm_config.get("temperature", 0.2) or 0.2)
        timeout = float(self.llm_config.get("timeout", 60) or 60)
        skip_ssl = bool(self.llm_config.get("skip_ssl", False))

        try:
            if skip_ssl:
                import httpx  # noqa: WPS433 自签证书需跳过SSL验证
                client = OpenAI(
                    base_url=base_url, api_key=api_key, timeout=timeout,
                    http_client=httpx.Client(verify=False),
                )
            else:
                client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        except Exception as exc:  # 客户端构造失败
            logger.warning("OpenAI 客户端构造失败(%s)，回退 mock 抽取。news_id=%s", exc, news.id)
            return self._mock_extract(news)

        last_err: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = client.chat.completions.create(
                    model=model,
                    temperature=temperature,
                    messages=[{"role": "user", "content": prompt_text}],
                )
                raw = resp.choices[0].message.content or ""
                data = self._parse_json(raw)
                event = self._dict_to_event(data, news)
                logger.info("LLM 抽取成功(news_id=%s, attempt=%d)", news.id, attempt)
                return event
            except Exception as exc:
                last_err = exc
                logger.warning(
                    "LLM 抽取失败 attempt=%d/%d news_id=%s err=%s",
                    attempt, max_retries, news.id, exc,
                )

        logger.warning(
            "LLM 抽取 %d 次均失败(最后一次 err=%s)，回退 mock 抽取。news_id=%s",
            max_retries, last_err, news.id,
        )
        return self._mock_extract(news)

    # ---------------- 防幻觉清洗 ----------------

    def _sanitize(self, event: EventExtraction) -> EventExtraction:
        """对 LLM 或 mock 产出的 event 做防幻觉清洗（只清洗、不归因）。"""
        # 噪音直接放行（无板块/股票需要校验）
        if event.is_noise:
            event.beneficiary_sectors = []
            event.victim_sectors = []
            event.representative_stocks = []
            event.llm_watch_hint = []
            return event

        # 板块名：只保留 sector_map 中真实存在的
        event.beneficiary_sectors = [
            s for s in event.beneficiary_sectors if s in self._valid_sectors
        ]
        event.victim_sectors = [
            s for s in event.victim_sectors if s in self._valid_sectors
        ]

        # representative_stocks：code 必须在合法集合内，否则丢弃该条；name 用 sector_map 真实名回填
        cleaned: list[dict] = []
        seen: set[str] = set()
        for st in event.representative_stocks:
            code = str(st.get("code", "")).strip()
            if code in self._valid_codes and code not in seen:
                seen.add(code)
                cleaned.append({
                    "code": code,
                    "name": self._code2name.get(code, st.get("name", "")),
                    "role": st.get("role", "龙头"),
                })
        event.representative_stocks = cleaned

        # llm_watch_hint：只保留合法代码并去重
        seen_wp: set[str] = set()
        wp: list[str] = []
        for code in event.llm_watch_hint:
            code = str(code).strip()
            if code in self._valid_codes and code not in seen_wp:
                seen_wp.add(code)
                wp.append(code)
        event.llm_watch_hint = wp

        return event

    # ---------------- 辅助方法 ----------------

    @staticmethod
    def _has(text: str, keywords: tuple[str, ...]) -> bool:
        """title 是否包含 keywords 中任一词。"""
        return any(k in text for k in keywords)

    @staticmethod
    def _match_rule(title: str, rule: dict) -> bool:
        """规则匹配：match 的多个关键词组，组内任一命中(OR)，组间全部命中(AND)。"""
        for group in rule.get("match") or []:
            if not any(str(kw) in title for kw in group):
                return False
        return True

    def _extract_entities(self, title: str) -> list[str]:
        """从 title 里挑出已知板块名 / 已知股票名作为 key_entities。"""
        ents: list[str] = []
        for sector in self._valid_sectors:
            if sector in title:
                ents.append(sector)
        for code, name in self._code2name.items():
            if name and name in title:
                ents.append(name)
        # 去重保序
        seen: set[str] = set()
        out: list[str] = []
        for e in ents:
            if e not in seen:
                seen.add(e)
                out.append(e)
        return out

    def _pick_representative_stocks(self, beneficiary: list[str]) -> list[dict]:
        """从每个 beneficiary 板块取前 2 只真实股票，role 给 龙头/弹性，跨板块去重。"""
        result: list[dict] = []
        seen: set[str] = set()
        for sector in beneficiary:
            stocks = self.sector_map.get(sector, [])
            for idx, st in enumerate(stocks[:2]):
                code = st["code"]
                if code in seen:
                    continue
                seen.add(code)
                result.append({
                    "code": code,
                    "name": st["name"],
                    "role": "龙头" if idx == 0 else "弹性",
                })
        return result

    def _build_watch_pool(self, beneficiary: list[str]) -> list[str]:
        """所有 beneficiary 板块的 code 去重列表。"""
        pool: list[str] = []
        seen: set[str] = set()
        for sector in beneficiary:
            for st in self.sector_map.get(sector, []):
                code = st["code"]
                if code not in seen:
                    seen.add(code)
                    pool.append(code)
        return pool

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """从 LLM 输出里解析 JSON（容忍 ```json``` 包裹与前后杂字）。"""
        text = raw.strip()
        # 去除可能的 markdown 代码块
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text)
            text = re.sub(r"```$", "", text).strip()
        # 截取第一个 { 到最后一个 }
        lo = text.find("{")
        hi = text.rfind("}")
        if lo != -1 and hi != -1 and hi > lo:
            text = text[lo:hi + 1]
        return json.loads(text)

    def _dict_to_event(self, data: dict, news: NewsItem) -> EventExtraction:
        """把 LLM 返回的 dict 组装成 EventExtraction（source_news_id/time_horizon 兜底）。"""
        # event_type 兜底
        etype = str(data.get("event_type", "中性"))
        if etype not in self._valid_event_types:
            etype = "中性"
        is_noise = bool(data.get("is_noise", etype == "噪音"))

        return EventExtraction(
            source_news_id=news.id,
            event_type=etype if not is_noise else "噪音",
            sentiment=str(data.get("sentiment", "中性")) or "中性",
            confidence=float(data.get("confidence", 0.5) or 0.5),
            time_horizon=str(data.get("time_horizon", "短期")) or "短期",
            beneficiary_sectors=list(data.get("beneficiary_sectors", []) or []),
            victim_sectors=list(data.get("victim_sectors", []) or []),
            key_entities=list(data.get("key_entities", []) or []),
            representative_stocks=list(data.get("representative_stocks", []) or []),
            chain_reasoning=str(data.get("chain_reasoning") or "LLM 未给出因果链。"),
            llm_watch_hint=list(data.get("watch_pool", []) or []),
            is_noise=is_noise,
        )
