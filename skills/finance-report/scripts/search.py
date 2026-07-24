#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""财经报导 · 网页搜索脚本（finance-report skill）

直连 Tavily 搜索 API，复刻 Hermes/Claw 的 WebSearchTool。
把搜索能力从私有工具里拿出来自包含，让别人 clone 就能搜。

凭证: TAVILY_API_KEY 环境变量（支持逗号分隔多 key，429/401/403 自动换下一个）。
      与 Claw 的 WebSearch.ApiKeys 一致。
可替换: 若用 Brave/SearXNG/Google 等，替换本脚本的 search() 即可。

用法:
  python search.py "财联社 今日财经要闻"
  python search.py "央行 LPR 调整" --max 8
输出: JSON，results 数组（n/title/url/snippet）。
依赖: 仅 Python 标准库。
"""
import sys
import os
import json
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8")

ENDPOINT = "https://api.tavily.com/search"
TIMEOUT = 30


def get_keys():
    """从 TAVILY_API_KEY 读 key 列表（逗号分隔）。"""
    raw = os.environ.get("TAVILY_API_KEY", "")
    return [k.strip() for k in raw.split(",") if k.strip()]


def search(query, max_results=5):
    keys = get_keys()
    if not keys:
        return {"ok": False, "error": "TAVILY_API_KEY 未配置（可逗号分隔多个 key）"}

    body = json.dumps({
        "query": query,
        "max_results": max_results,
        "include_answer": False,
    }).encode("utf-8")

    last_err = None
    for key in keys:
        req = urllib.request.Request(ENDPOINT, data=body, method="POST")
        req.add_header("Authorization", f"Bearer {key}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results") or []
            return {
                "ok": True,
                "count": len(results),
                "results": [
                    {
                        "n": i,
                        "title": item.get("title", "(no title)"),
                        "url": item.get("url", ""),
                        "snippet": item.get("content", ""),
                    }
                    for i, item in enumerate(results, 1)
                ],
            }
        except urllib.error.HTTPError as e:
            code = e.code
            msg = e.read().decode("utf-8", "replace")[:300]
            last_err = f"HTTP {code}: {msg}"
            # 429 限流 / 401,403 key 无效 / 402 配额 → 换下一个 key
            if code in (429, 401, 403, 402):
                continue
            return {"ok": False, "error": last_err}
        except Exception as e:
            last_err = f"request failed: {e}"
            continue
    return {"ok": False, "error": f"所有 key 均失败，最后错误: {last_err}"}


def main(argv):
    import argparse
    p = argparse.ArgumentParser(description="Tavily 网页搜索")
    p.add_argument("query", help="搜索词")
    p.add_argument("--max", type=int, default=5, help="最大结果数（1-20）")
    args = p.parse_args(argv)
    args.max = max(1, min(20, args.max))
    res = search(args.query, args.max)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
