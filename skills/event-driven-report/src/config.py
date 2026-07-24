"""统一配置加载 —— 把所有"内容"配置集中加载，供各模块注入。

设计原则：
- 代码只含"逻辑"(匹配引擎/防幻觉清洗/pipeline流程)，所有"内容"(规则/prompt/文案/示例/板块表)
  都从 config/ 和 data/ 读取，做到"改配置不改代码"。
- 路径在 settings.yaml 的 paths 段统一管理，均相对项目根。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import yaml


def _load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_env(obj: Any) -> Any:
    """递归把字符串里的 ${ENV_VAR} 占位符替换为环境变量值（未设置则替换为空串）。

    用于 api_key 等敏感配置走环境变量，不落盘。
    """
    if isinstance(obj, str):
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), ""), obj)
    if isinstance(obj, dict):
        return {k: _expand_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env(v) for v in obj]
    return obj


@dataclass
class Config:
    """全局配置容器。各模块从对应字段取自己需要的内容。"""

    settings: Dict[str, Any]
    sector_map: Dict[str, list]
    event_rules: Dict[str, Any]
    prompts: Dict[str, Any]
    report_templates: Dict[str, Any]
    demo_news: List[Dict[str, Any]]
    industry_chain: Dict[str, Any]

    @classmethod
    def load(cls, settings_path: str = "config/settings.yaml") -> "Config":
        settings = _expand_env(_load_yaml(settings_path))
        # 项目根 = settings.yaml 所在 config/ 的上一级
        root = Path(settings_path).resolve().parent.parent
        paths = settings.get("paths") or {}

        def resolve(key: str, default: str) -> str:
            v = paths.get(key, default)
            return v if Path(v).is_absolute() else str(root / v)

        sector_map = _load_json(resolve("sector_map", "data/sector_map.json"))
        event_rules = _load_yaml(resolve("event_rules", "config/event_rules.yaml"))
        prompts = _load_yaml(resolve("prompts", "config/prompts.yaml"))
        report_templates = _load_yaml(resolve("report_templates", "config/report_templates.yaml"))
        demo_news = _load_json(resolve("demo_news", "data/demo_news.json"))
        industry_chain_raw = _load_json(resolve("industry_chain", "data/industry_chain.json"))

        # 过滤掉以 "_" 开头的说明键
        sector_map = {k: v for k, v in sector_map.items() if not str(k).startswith("_")}
        industry_chain = {k: v for k, v in industry_chain_raw.items() if not str(k).startswith("_")}

        return cls(
            settings=settings,
            sector_map=sector_map,
            event_rules=event_rules,
            prompts=prompts,
            report_templates=report_templates,
            demo_news=demo_news,
            industry_chain=industry_chain,
        )

    # —— 便捷访问 ——
    @property
    def llm(self) -> dict:
        return self.settings.get("llm") or {}

    @property
    def news(self) -> dict:
        return self.settings.get("news") or {}

    @property
    def mapper_topn(self) -> int:
        return int((self.settings.get("mapper") or {}).get("watch_pool_topn", 8))
