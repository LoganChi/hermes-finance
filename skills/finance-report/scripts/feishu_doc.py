#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""财经报导 · 飞书云文档操作脚本（finance-report skill）

直连飞书 OpenAPI，提供报告管线所需的文档操作：
  create_doc    从 Markdown 创建云文档（标题 + 正文 blocks）
  read_doc      读取文档结构（章节），用于定位插图位置
  insert_media  插入本地图片到文档指定章节后

凭证通过环境变量或同目录 feishu 配置文件获取：
  FEISHU_APP_ID      飞书应用 App ID
  FEISHU_APP_SECRET  飞书应用 App Secret

用法:
  python feishu_doc.py create_doc --title "财经日报" --file report.md
  python feishu_doc.py create_doc --title "财经日报" --content "$(cat report.md)"
  python feishu_doc.py read_doc --doc <document_id>
  python feishu_doc.py insert_media --doc <id> --file cover.png --width 560 --align center --selection "第二章"

输出: JSON。create_doc 成功含 document_id；失败含 error。
依赖: 仅 Python 标准库 + requests（如无则 fallback urllib）。
"""
import sys
import os
import json
import re
import argparse
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "https://open.feishu.cn/open-apis"
TIMEOUT = 30

# 凭证缓存
_token_cache = {"token": None, "expires": 0}


def _load_config():
    """从环境变量或 ~/.hermes/configs/feishu.json 读取凭证。"""
    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    if app_id and app_secret:
        return app_id, app_secret
    # fallback: 配置文件
    config_path = os.path.expanduser("~/.hermes/configs/feishu.json")
    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
            return cfg.get("APP_ID", ""), cfg.get("APP_SECRET", "")
    return None, None


def _get_token():
    """获取 tenant_access_token，带简单缓存。"""
    import time
    if _token_cache["token"] and time.time() < _token_cache["expires"]:
        return _token_cache["token"]
    app_id, app_secret = _load_config()
    if not app_id or not app_secret:
        return None
    body = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/auth/v3/tenant_access_token/internal",
        data=body, method="POST",
    )
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    token = data.get("tenant_access_token")
    if token:
        _token_cache["token"] = token
        _token_cache["expires"] = time.time() + data.get("expire", 7200) - 300
    return token


def _api(method, path, body=None, params=None):
    """飞书 API 通用请求。"""
    token = _get_token()
    if not token:
        return {"ok": False, "error": "无法获取飞书 token，请检查 FEISHU_APP_ID / FEISHU_APP_SECRET"}
    url = f"{BASE_URL}{path}"
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", "replace")[:500]
        return {"ok": False, "error": f"HTTP {e.code}: {err_body}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    if result.get("code", 0) != 0:
        return {"ok": False, "error": result.get("msg", "unknown"), "code": result.get("code")}
    return {"ok": True, "data": result.get("data", {})}


# ── Markdown → 飞书 blocks 转换 ──────────────────────────────────────────

def _text_run(content, bold=False, italic=False):
    style = {}
    if bold:
        style["bold"] = True
    if italic:
        style["italic"] = True
    return {"text_run": {"content": content, "text_element_style": style}}


def _md_to_blocks(md_text):
    """简易 Markdown → 飞书 docx blocks。支持 #/##/### 标题、列表、段落、粗体/斜体。"""
    blocks = []
    lines = md_text.strip().split("\n")
    for line in lines:
        line = line.rstrip()
        if not line.strip():
            continue
        # 标题
        m = re.match(r'^(#{1,3})\s+(.*)', line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            bt = {1: 3, 2: 4, 3: 5}[level]  # heading1=3, heading2=4, heading3=5
            key = {1: "heading1", 2: "heading2", 3: "heading3"}[level]
            blocks.append({"block_type": bt, key: {"elements": [_text_run(text)]}})
            continue
        # 列表项 (-, *, •)
        m = re.match(r'^[\s]*[-*•]\s+(.*)', line)
        if m:
            content = _parse_inline(m.group(1))
            blocks.append({"block_type": 2, "text": {"elements": [{"text_run": {"content": "\u2022 " + _strip_md(content)}}]}})
            continue
        # 数字列表
        m = re.match(r'^[\s]*\d+\.\s+(.*)', line)
        if m:
            content = _strip_md(m.group(1))
            blocks.append({"block_type": 2, "text": {"elements": [_text_run(content)]}})
            continue
        # 普通段落
        content = _strip_md(line)
        blocks.append({"block_type": 2, "text": {"elements": [_text_run(content)]}})
    return blocks


def _strip_md(text):
    """移除 Markdown 格式符号，保留纯文本。"""
    # **bold** → bold
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    # *italic* → italic
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    # [text](url) → text（URL 不内联）
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # `code` → code
    text = re.sub(r'`(.+?)`', r'\1', text)
    return text.strip()


def _parse_inline(text):
    """占位，目前返回纯文本。"""
    return _strip_md(text)


# ── 公开接口 ──────────────────────────────────────────────────────────────

def create_doc(title, content):
    """创建云文档 + 写入正文。"""
    # 1. 创建空文档
    res = _api("POST", "/docx/v1/documents", body={"title": title})
    if not res["ok"]:
        return res
    doc_id = res["data"].get("document", {}).get("document_id", "")
    if not doc_id:
        return {"ok": False, "error": "创建文档成功但未返回 document_id", "raw": res["data"]}
    # 2. 写入正文
    if content and content.strip():
        blocks = _md_to_blocks(content)
        if blocks:
            res2 = _api("POST", f"/docx/v1/documents/{doc_id}/blocks/{doc_id}/children", body={"children": blocks})
            if not res2["ok"]:
                return {"ok": True, "document_id": doc_id, "warning": f"文档已创建但正文写入失败: {res2.get('error')}"}
    return {"ok": True, "document_id": doc_id, "url": f"https://bytedance.feishu.cn/docx/{doc_id}"}


def read_doc(doc_id):
    """读取文档的 block 列表（章节结构）。"""
    res = _api("GET", f"/docx/v1/documents/{doc_id}/blocks",
               params={"page_size": 500, "document_revision_id": -1})
    if not res["ok"]:
        return res
    items = res["data"].get("items", [])
    # 提取标题块作为章节结构
    sections = []
    for item in items:
        bt = item.get("block_type", 0)
        if bt in (3, 4, 5):  # heading 1/2/3
            key = {3: "heading1", 4: "heading2", 5: "heading3"}.get(bt)
            if key and item.get(key):
                elements = item[key].get("elements", [])
                text = "".join(e.get("text_run", {}).get("content", "") for e in elements)
                sections.append({"block_id": item.get("block_id"), "level": bt - 2, "title": text})
    return {"ok": True, "sections": sections, "total_blocks": len(items)}


def insert_media(doc_id, file_path, width=None, align="center", selection=None):
    """上传图片并插入文档。

    飞书 API 流程: 上传文件获取 file_token → 在目标 block 后插入 image block。
    selection 参数匹配章节标题，找到对应 block_id 后插入其后。
    """
    if not os.path.exists(file_path):
        return {"ok": False, "error": f"图片不存在: {file_path}"}
    # 1. 上传图片素材
    token = _get_token()
    if not token:
        return {"ok": False, "error": "无法获取飞书 token"}
    # 读取图片并上传
    with open(file_path, "rb") as f:
        img_data = f.read()
    import uuid
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image_type"\r\n\r\n'
        f"message\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + img_data + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/im/v1/images",
        data=body, method="POST",
    )
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            upload_res = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"上传图片失败 HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}"}
    except Exception as e:
        return {"ok": False, "error": f"上传图片失败: {e}"}
    if upload_res.get("code", 0) != 0:
        return {"ok": False, "error": upload_res.get("msg", "上传失败"), "raw": upload_res}
    file_key = upload_res.get("data", {}).get("image_key", "")
    if not file_key:
        return {"ok": False, "error": "上传成功但未返回 image_key", "raw": upload_res}

    # 2. 找到目标 block（通过 selection 匹配标题，或追加到文档末尾）
    target_block_id = doc_id  # 默认追加到文档根
    if selection:
        doc_info = read_doc(doc_id)
        if doc_info["ok"]:
            for sec in doc_info.get("sections", []):
                if selection in sec.get("title", ""):
                    target_block_id = sec["block_id"]
                    break

    # 3. 插入 image block
    img_block = {
        "block_type": 27,
        "image": {
            "token": file_key,
            "width": width or 560,
            "height": int((width or 560) * 0.6),
        }
    }
    res = _api("POST", f"/docx/v1/documents/{doc_id}/blocks/{target_block_id}/children",
               body={"children": [img_block], "index": 0})
    if not res["ok"]:
        return {"ok": False, "error": f"插入图片block失败: {res.get('error')}", "image_key": file_key}
    return {"ok": True, "image_key": file_key, "document_id": doc_id}


def main(argv):
    p = argparse.ArgumentParser(description="飞书云文档操作（直连 OpenAPI）")
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
