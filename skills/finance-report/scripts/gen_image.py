#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""财经报导 · 图像生成脚本（finance-report skill）

直连商汤 SenseNova 图像生成 API（OpenAI 兼容接口），用于报告封面与配图。
复刻自 Hermes/Claw 的 ImageGenTool.cs，把图像生成能力从私有工具里拿出来自包含。

凭证: SENSENOVA_API_KEY 环境变量（与 Claw 一致）。
可配: SENSENOVA_MODEL（默认 sensenova-u1-fast）、SENSENOVA_ENDPOINT、IMAGE_OUTPUT_DIR。

注意: SenseNova 对同一 Key 有速率限制，连续生成多张需间隔 ≥15s（由调用方控制）。
      封面建议 size=1920x1080，配图建议 1024x1024。

用法:
  python gen_image.py --prompt "..." --size 1920x1080
  python gen_image.py --prompt "..." --size 1024x1024 --negative "blurry, low quality"
输出: JSON，含 image_url 与 saved_path（下载到 IMAGE_OUTPUT_DIR，默认 ./output）。
依赖: 仅 Python 标准库。
"""
import sys
import os
import json
import time
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_ENDPOINT = "https://token.sensenova.cn/v1/images/generations"
DEFAULT_MODEL = os.environ.get("SENSENOVA_MODEL", "sensenova-u1-fast")
DEFAULT_SIZE = "2048x2048"
DEFAULT_NEGATIVE = "blurry, low quality, distorted, watermark, deformed"
TIMEOUT = 120


def gen_image(prompt, size=DEFAULT_SIZE, negative=DEFAULT_NEGATIVE):
    key = os.environ.get("SENSENOVA_API_KEY")
    if not key:
        return {"ok": False, "error": "SENSENOVA_API_KEY 未配置"}
    endpoint = os.environ.get("SENSENOVA_ENDPOINT", DEFAULT_ENDPOINT)

    body = json.dumps({
        "model": DEFAULT_MODEL,
        "prompt": prompt,
        "image_size": size,
        "negative_prompt": negative,
        "n": 1,
    }).encode("utf-8")

    req = urllib.request.Request(endpoint, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}"}
    except Exception as e:
        return {"ok": False, "error": f"request failed: {e}"}

    items = data.get("data") or []
    if not items:
        return {"ok": False, "error": "API 未返回图片数据", "raw": data}
    image_url = items[0].get("url")
    if not image_url:
        return {"ok": False, "error": "响应无 url 字段", "raw": data}

    saved = download(image_url)
    return {"ok": True, "image_url": image_url, "saved_path": saved}


def download(url):
    out_dir = os.environ.get("IMAGE_OUTPUT_DIR", "./output")
    try:
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"img-{int(time.time() * 1000)}.png")
        urllib.request.urlretrieve(url, path)
        return path
    except Exception as e:
        return f"<download failed: {e}>"


def main(argv):
    import argparse
    p = argparse.ArgumentParser(description="SenseNova 图像生成")
    p.add_argument("--prompt", required=True)
    p.add_argument("--size", default=DEFAULT_SIZE, help="1920x1080 / 1024x1024 / 2048x2048")
    p.add_argument("--negative", default=DEFAULT_NEGATIVE)
    args = p.parse_args(argv)
    res = gen_image(args.prompt, args.size, args.negative)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
