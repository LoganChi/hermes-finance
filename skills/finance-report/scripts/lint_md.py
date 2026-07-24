#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""财经报导 · 报告 Markdown 校验/规范化脚本（finance-report skill）

针对飞书 lark-cli 的 markdown 解析限制，校验并规范化报告 md：
  1. [text](url) 行内超链接 → lark-cli 不支持转飞书超链接（FeishuCliTool 源码注释原话），
     改为纯 URL（飞书会自动识别为可点击链接）
  2. 飞书/lark 文档 URL → 移除（历史会话残留的空文档链接，呼应 ReportOrchestrator.StripFeishuUrls）
  3. HTML 标签（<title> 除外）→ 警告（lark-cli 可能不解析）
  4. 标题层级跳跃（如 ## → #### 跳过 ###）→ 警告
  5. 未配对代码块 ``` → 警告
  6. 空链接 / 空标题 → 警告

这是 report 管线缺失的一环：Claw 里 reportContent 从 LLM 出来只过 StripFeishuUrls
就喂给 feishu_cli，无任何 md 校验。本脚本补上，建议 create_doc 前必跑。

用法:
  python lint_md.py report.md                      # 校验，输出问题清单
  python lint_md.py report.md --fix                # 校验 + 自动修复（超链接/飞书URL），写回原文件
  python lint_md.py report.md --fix --out fixed.md # 修复后写到指定文件
  python lint_md.py report.md --check              # 只检查，有问题 exit 1（可接入流程 gating）

退出码: 0=无问题或已修复; 1=检查发现问题（--check）或出错
依赖: 仅 Python 标准库。
"""
import sys
import os
import re
import json
import argparse

sys.stdout.reconfigure(encoding="utf-8")

# 飞书/lark 文档 URL（与 ReportOrchestrator.StripFeishuUrls 对齐）
FEISHU_URL_RE = re.compile(
    r"https?://(?:[a-z0-9-]+\.)*(?:feishu\.cn|feishu\.net|larksuite\.com|bytedance\.net)/"
    r"(?:docx|wiki|sheets|base|drive|docs)/[A-Za-z0-9]+[^\s)\]]*",
    re.IGNORECASE,
)
# 行内超链接 [text](url)，排除图片 ![alt](url)
INLINE_LINK_RE = re.compile(r"(?<!\!)\[([^\]]+)\]\((https?://[^)\s]+)\)")
# HTML 标签，排除 <title>（create_doc 用它传标题）
HTML_TAG_RE = re.compile(r"</?(?!title\b)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>")


def lint(content):
    """返回 (issues 列表, 修复后的内容)。issues: [(type, msg), ...]"""
    issues = []
    fixed = content

    # 1. 行内超链接 → 纯 URL（lark-cli 不支持 [text](url) 转飞书超链接）
    def repl_link(m):
        text, url = m.group(1), m.group(2)
        issues.append(("inline_link", f"行内超链接 [{text}]({url[:50]}) → lark-cli 不支持，改为纯 URL"))
        return url
    fixed = INLINE_LINK_RE.sub(repl_link, fixed)

    # 2. 飞书/lark 文档 URL → 移除
    for m in FEISHU_URL_RE.finditer(fixed):
        issues.append(("feishu_url", f"飞书文档链接 {m.group(0)[:60]}… → 移除（历史残留）"))
    fixed = FEISHU_URL_RE.sub("[已移除飞书文档链接]", fixed)

    # 3. HTML 标签（除 title）→ 警告（不自动移除，避免破坏 create_doc 的 <title>）
    for m in HTML_TAG_RE.finditer(fixed):
        issues.append(("html_tag", f"HTML 标签 <{m.group(1)}> → lark-cli 可能不解析，建议移除"))

    # 4. 标题层级跳跃
    prev_level = 0
    for line in fixed.split("\n"):
        m = re.match(r"^(#{1,6})\s+\S", line)
        if m:
            level = len(m.group(1))
            if prev_level and level > prev_level + 1:
                issues.append(("heading_jump", f"标题层级跳跃 H{prev_level}→H{level}: {line.strip()[:40]}"))
            prev_level = level

    # 5. 未配对代码块
    fences = fixed.count("```")
    if fences % 2 != 0:
        issues.append(("codeblock_unpaired", f"代码块 ``` 未配对（共 {fences} 个）"))

    # 6. 空链接 / 空标题
    for m in re.finditer(r"\[(.*?)\]\(\s*\)", fixed):
        issues.append(("empty_link", f"空链接 [{m.group(1)}]()"))
    for line in fixed.split("\n"):
        if re.match(r"^#{1,6}\s*$", line):
            issues.append(("empty_heading", f"空标题: {line.strip()}"))

    return issues, fixed


def main(argv):
    p = argparse.ArgumentParser(description="报告 Markdown 校验/规范化（针对飞书 lark-cli 限制）")
    p.add_argument("file", help="markdown 文件路径")
    p.add_argument("--fix", action="store_true", help="自动修复可修复项（行内超链接/飞书URL），写回")
    p.add_argument("--out", help="修复后写到此文件（默认 --fix 写回原文件）")
    p.add_argument("--check", action="store_true", help="只检查不修复，发现问题 exit 1")
    args = p.parse_args(argv)

    if not os.path.exists(args.file):
        print(json.dumps({"ok": False, "error": f"文件不存在: {args.file}"}))
        return 1

    with open(args.file, encoding="utf-8") as f:
        content = f.read()

    issues, fixed = lint(content)
    result = {
        "ok": True,
        "file": args.file,
        "issue_count": len(issues),
        "issues": [{"type": t, "msg": m} for t, m in issues],
    }

    if args.fix and fixed != content:
        out_path = args.out or args.file
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(fixed)
        result["fixed"] = True
        result["written_to"] = out_path

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
