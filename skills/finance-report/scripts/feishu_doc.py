#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""财经报导 · 飞书云文档操作脚本（finance-report skill）

封装飞书官方 @larksuite/cli (lark-cli)，提供报告管线所需的文档操作：
  create_doc    从 Markdown 创建云文档（标题嵌入 <title> 标签，content 走 stdin）
  read_doc      读取文档结构（章节），用于定位插图位置
  insert_media  插入本地图片到文档指定章节后

为什么封装 lark-cli 而不直连 OpenAPI：飞书 docx 创建接口只支持空文档+标题，
写入正文需把 Markdown 转成飞书 block 结构（极繁琐）；lark-cli 官方处理了
markdown→docx 转换，是最可靠路径（Hermes/Claw 的 FeishuCliTool 同样做法）。

前置依赖:
  npm install -g @larksuite/cli
  lark-cli auth login   （或配 LARKSUITE_CLI_* 环境变量）

用法:
  python feishu_doc.py create_doc --title "财经日报" --file report.md
  python feishu_doc.py create_doc --title "财经日报" --content "$(cat report.md)"
  python feishu_doc.py read_doc --doc <document_id>
  python feishu_doc.py insert_media --doc <id> --file cover.png --width 560 --align center --selection "第二章"

输出: JSON。create_doc 成功含 document_id；失败含 error + stderr。
依赖: 仅 Python 标准库 + lark-cli 二进制。
"""
import sys
import os
import json
import argparse
import subprocess

sys.stdout.reconfigure(encoding="utf-8")  # 对齐 lark-cli UTF-8 输出

CLI = "lark-cli"
TIMEOUT = 60


def run_cli(args, stdin_content=None, cwd=None):
    """执行 lark-cli，返回 dict。成功 ok=True + stdout；失败带 error/stderr。"""
    cmd = [CLI] + args
    env = dict(os.environ, LARK_CLI_NO_PROXY="1")
    try:
        r = subprocess.run(
            cmd, input=stdin_content, capture_output=True, text=True,
            encoding="utf-8", timeout=TIMEOUT, cwd=cwd, env=env,
        )
    except FileNotFoundError:
        return {"ok": False, "error": "lark-cli 未安装。请先 npm install -g @larksuite/cli 并 auth login。"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"lark-cli 超时 (>{TIMEOUT}s)"}
    if r.returncode != 0:
        return {"ok": False, "exit": r.returncode,
                "error": (r.stderr or "")[:1000], "stdout": (r.stdout or "")[:500]}
    return {"ok": True, "stdout": r.stdout}


def create_doc(title, content):
    """v2 API: docs +create --doc-format markdown；content 走 stdin (-)，标题用 <title> 标签嵌入。"""
    body = f"<title>{title}</title>\n\n{content or ''}".rstrip()
    res = run_cli(
        ["docs", "+create", "--doc-format", "markdown", "--as", "user", "--content", "-"],
        stdin_content=body,
    )
    if not res["ok"]:
        return res
    doc_id = _dig_json(res["stdout"], "document_id") or _dig_json(res["stdout"], "doc_token")
    return {"ok": True, "document_id": doc_id, "raw": res["stdout"][:300] if not doc_id else None}


def read_doc(doc_id):
    res = run_cli(["docs", "+fetch", "--doc", doc_id, "--as", "user", "--format", "pretty"])
    return res


def insert_media(doc_id, file_path, width=None, align="center", selection=None):
    if file_path.lower().startswith(("http://", "https://")):
        return {"ok": False, "error": f"file 必须本地路径，收到 URL: {file_path}"}
    if not os.path.exists(file_path):
        return {"ok": False, "error": f"图片不存在: {file_path}"}
    # lark-cli 要求 cwd-relative 路径，切到图片目录
    file_dir = os.path.dirname(os.path.abspath(file_path)) or "."
    rel = "./" + os.path.basename(file_path)
    args = ["docs", "+media-insert", "--doc", doc_id, "--file", rel,
            "--type", "image", "--as", "user"]
    if width:
        args += ["--width", str(width)]
    if align:
        args += ["--align", align]
    if selection:
        args += ["--selection-with-ellipsis", selection]
    return run_cli(args, cwd=file_dir)


def _dig_json(text, key):
    """从 lark-cli 输出（可能非纯 JSON）里递归找 key 对应值。"""
    s = text.strip()
    start = s.find("{")
    if start < 0:
        return None
    try:
        doc = json.loads(s[start:])
    except json.JSONDecodeError:
        return None
    return _find(doc, key)


def _find(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = _find(v, key)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find(v, key)
            if r:
                return r
    return None


def main(argv):
    p = argparse.ArgumentParser(description="飞书云文档操作（封装 lark-cli）")
    sub = p.add_subparsers(dest="action", required=True)

    pc = sub.add_parser("create_doc")
    pc.add_argument("--title", required=True)
    g = pc.add_mutually_exclusive_group()
    g.add_argument("--file", help="markdown 文件路径")
    g.add_argument("--content", help="markdown 内容字符串")

    pr = sub.add_parser("read_doc")
    pr.add_argument("--doc", required=True)

    pm = sub.add_parser("insert_media")
    pm.add_argument("--doc", required=True)
    pm.add_argument("--file", required=True)
    pm.add_argument("--width", type=int)
    pm.add_argument("--align", default="center")
    pm.add_argument("--selection")

    args = p.parse_args(argv)

    if args.action == "create_doc":
        content = args.content
        if args.file:
            with open(args.file, encoding="utf-8") as f:
                content = f.read()
        res = create_doc(args.title, content)
    elif args.action == "read_doc":
        res = read_doc(args.doc)
    elif args.action == "insert_media":
        res = insert_media(args.doc, args.file, args.width, args.align, args.selection)
    else:
        res = {"ok": False, "error": "unknown action"}

    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if (isinstance(res, dict) and res.get("ok")) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
