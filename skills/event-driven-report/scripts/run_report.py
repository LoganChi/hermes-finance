#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""event-driven-report · 报告生成 thin wrapper（仅标准库）

把"跑 pipeline 生成报告"这件确定性活包装成结构化 JSON 输出，
供上层 agent 框架 subprocess 调用 + 解析。对齐 finance-report/scripts/fetch_quote.py 的定位
（把确定性活从 LLM 手里拿走，输出可解析的 JSON）。

用法:
  python scripts/run_report.py --today             # 今日盘前模式
  python scripts/run_report.py --today --open      # 跑完自动打开浏览器

输出 JSON:
  成功: {"ok": true,  "html_path": "...", "stdout_tail": "...", "stderr_tail": "..."}
  失败: {"ok": false, "html_path": null, "stdout_tail": "...", "stderr_tail": "..."}
  超时: {"ok": false, "error": "timeout", "hint": "..."}

依赖:
  本脚本仅 Python 标准库。但它 subprocess 调用的 gen_weekend_report.py
  需要全套依赖（见 requirements.txt）+ DEEPSEEK_API_KEY。

数据源: 见 SKILL.md 数据源路由表。
"""
import sys
import json
import subprocess
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
TARGET = SKILL_ROOT / "scripts" / "gen_weekend_report.py"
TIMEOUT = 300


def main():
    want_open = "--open" in sys.argv
    args = [sys.executable, str(TARGET)] + [a for a in sys.argv[1:] if a != "--open"]
    result = {"ok": False, "html_path": None, "stdout_tail": "", "stderr_tail": ""}

    try:
        proc = subprocess.run(args, cwd=SKILL_ROOT, capture_output=True,
                              text=True, encoding="utf-8", timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        result["error"] = "timeout"
        result["hint"] = f"{TIMEOUT}s 超时，可能是 akshare 限流或网络慢"
        print(json.dumps(result, ensure_ascii=False))
        return 1

    result["ok"] = proc.returncode == 0
    result["stdout_tail"] = proc.stdout[-800:]
    result["stderr_tail"] = proc.stderr[-800:]
    # 解析 stdout 里的 ✅ reports/daily_xxx.html 行
    for line in proc.stdout.splitlines():
        if "✅" in line and ".html" in line:
            result["html_path"] = line.split("✅", 1)[-1].strip()
            break

    print(json.dumps(result, ensure_ascii=False))
    if want_open and result["html_path"] and Path(result["html_path"]).exists():
        import webbrowser
        webbrowser.open(str(result["html_path"]))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
