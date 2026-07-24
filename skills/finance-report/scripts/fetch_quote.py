#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""财经报导 · A 股实时行情抓取脚本（finance-report skill）

从腾讯财经批量接口抓取 A 股/指数实时行情，解析 `~` 分隔字段，输出结构化 JSON。
把"接口调用 + 字段解析"这件确定性活从 LLM 手里拿走，避免每次靠 prompt 教模型解析字段索引。

三种调用方：
  1. 报告管线 ReportOrchestrator 的「行情预取」步骤直接 subprocess 调用（推荐，LLM 不碰 shell）。
  2. LLM 通过 shell 工具调用：`python scripts/fetch_quote.py 600519`（仅当管线暴露 shell 时）。
  3. 人工 / 调试：命令行直接跑。

用法:
  python fetch_quote.py 600519 000001              # 6 位代码，自动识别市场
  python fetch_quote.py sh600519 sz399001           # 已带前缀
  python fetch_quote.py sh000001,sz399001,sh600519  # 逗号分隔批量
  python fetch_quote.py                             # 不带参数 → 默认指数+龙头

输出: JSON 数组，每项含 name/price/change_pct/volume/amount/pe 等。
数据源: https://qt.gtimg.cn/q=<symbols> （腾讯财经，返回 GBK 编码）。
依赖: 仅 Python 标准库。
"""
import sys
import json
import urllib.request

# Windows 控制台默认 GBK，强制 stdout UTF-8，保证中文（股票名、涨/跌方向）不乱码。
# 调用方 ShellTool 已按 UTF-8 读取 stdout（见 ShellTool.cs StandardOutputEncoding），链路对齐。
sys.stdout.reconfigure(encoding="utf-8")

# 腾讯接口 `~` 分隔字段索引（与 stock-data skill 对齐）
FIELDS = {
    1: "name",        # 股票名称
    2: "code",        # 代码
    3: "price",       # 当前价
    4: "prev_close",  # 昨收
    5: "open",        # 今开
    33: "high",       # 最高
    34: "low",        # 最低
    6: "volume",      # 成交量(手)
    37: "amount",     # 成交额(万)
    31: "change",     # 涨跌额
    32: "change_pct", # 涨跌幅
    38: "turnover",   # 换手率
    39: "pe",         # 市盈率
}

# 6 位纯数字 → 市场前缀（6→上交所, 0/3→深交所, 4/8→北交所）
PREFIX_BY_FIRST = {"6": "sh", "0": "sz", "3": "sz", "4": "bj", "8": "bj"}

DEFAULT_SYMBOLS = ["sh000001", "sz399001", "sz399006", "sh000688", "sh600519"]
TIMEOUT = 10


def normalize_symbol(code: str) -> str:
    """归一化代码：带前缀的原样返回；6 位纯数字按首位加市场前缀。"""
    code = code.strip().lower()
    if code[:2] in ("sh", "sz", "bj"):
        return code
    if code.isdigit() and len(code) == 6:
        return f"{PREFIX_BY_FIRST.get(code[0], 'sh')}{code}"
    return code  # 非法/未知，原样交接口


def fetch(symbols):
    """抓取并解析，返回结构化行情列表。"""
    query = ",".join(normalize_symbol(s) for s in symbols)
    url = f"https://qt.gtimg.cn/q={query}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("gbk", errors="replace")
    except Exception as ex:
        return [{"error": f"fetch failed: {ex}", "url": url}]

    results = []
    for chunk in body.split(";"):
        chunk = chunk.strip()
        if "=" not in chunk or "~" not in chunk:
            continue
        head = chunk.split("=", 1)[0]
        symbol = head.split("_")[-1] if "_" in head else head[1:]
        try:
            inner = chunk.split('"', 2)[1]
        except IndexError:
            continue
        parts = inner.split("~")
        if len(parts) < 40:
            continue
        row = {"symbol": symbol}
        for idx, name in FIELDS.items():
            if idx < len(parts) and parts[idx]:
                row[name] = parts[idx]
        # 涨跌方向（便于 LLM 直读，省得自己算）
        try:
            pct = float(row.get("change_pct", 0))
            row["trend"] = "涨" if pct > 0 else "跌" if pct < 0 else "平"
        except (ValueError, TypeError):
            row["trend"] = "?"
        results.append(row)
    return results


def main(argv):
    args = argv[1:]
    if not args:
        symbols = list(DEFAULT_SYMBOLS)
    else:
        symbols = []
        for a in args:
            symbols.extend(s.strip() for s in a.split(",") if s.strip())
    data = fetch(symbols)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
