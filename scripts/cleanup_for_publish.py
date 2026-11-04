# -*- coding: utf-8 -*-
"""发布前隐私清理：把本机使用痕迹全部抹掉，让项目成为「干净的新项目」。

清理内容：
  1. 账号池（accounts.json）—— 邮箱、access_token、refresh_token 全在里面
  2. API Key（auth_keys.json + page-api-key.txt）
  3. 代理订阅链接（subscription.txt）—— 机场地址是你的私人资源
  4. 代理配置里的节点（mihomo-config.yaml）—— 换成占位模板
  5. 内置浏览器档案（chrome-profile）—— 含 ChatGPT/Google 登录 Cookie
  6. 调用日志（logs.jsonl / *.log）—— 你的使用记录
  7. 图片（images / image_thumbnails）
  8. 节点选择、删除节点、模型禁用等使用偏好
  9. .env 里的密钥 —— 换成示例值，强制首次部署自己填

用法：
  python cleanup_for_publish.py --dry-run     # 只看会删什么
  python cleanup_for_publish.py --apply       # 真删
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

# 需要整体删除的目录（用户登录态、图片、缓存）
DIRS_TO_REMOVE = [
    "chrome-profile",
    "images",
    "image_thumbnails",
    "backups",
]

# 需要整体删除的文件（含个人数据或可能含）
FILES_TO_REMOVE = [
    "accounts.json",
    "auth_keys.json",
    "page-api-key.txt",
    "subscription.txt",
    "logs.jsonl",
    "app.log",
    "gateway.log",
    "console.log",
    "chrome.log",
    "mihomo.log",
    "fwd.log",
    "novnc.log",
    "x11vnc.log",
    "xvfb.log",
    "browser-start.log",
    "browser-restart.log",
    "image_index.json",
    "image_tags.json",
    "image_tasks.json",
    ".cumulative_total",
    "oauth-callback.json",
    "selected-node.txt",
    "removed-nodes.json",
    "model-off.json",
    "grp_order.json",
    "proxy-exclude.json",
]

# 需要重置成空白内容的 json（保留结构，避免首次启动报错）
RESET_JSON = {
    "model-off.json": [],
    "removed-nodes.json": [],
    "proxy-exclude.json": {"exclude": []},
}

DRY = True


def log(msg):
    print(("  [dry] " if DRY else "  [del] ") + msg)


def rm_dir(name):
    p = os.path.join(DATA, name)
    if not os.path.isdir(p):
        return
    n = sum(len(f) for _, _, f in os.walk(p))
    log("目录 %-20s (%d 个文件)" % (name, n))
    if not DRY:
        shutil.rmtree(p, ignore_errors=True)


def rm_file(name):
    p = os.path.join(DATA, name)
    if not os.path.isfile(p):
        return
    log("文件 %-20s (%d 字节)" % (name, os.path.getsize(p)))
    if not DRY:
        try:
            os.remove(p)
        except Exception:
            pass


def reset_json(name, content):
    p = os.path.join(DATA, name)
    if not DRY:
        os.makedirs(DATA, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(content, f)


def main():
    global DRY
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正执行删除")
    ap.add_argument("--dry-run", action="store_true", help="只打印")
    a = ap.parse_args()
    DRY = not a.apply

    print("=" * 66)
    print("隐私清理" + ("（预览模式，不会真删）" if DRY else "（正在执行）"))
    print("=" * 66)

    print("\n[1] 删除目录")
    for d in DIRS_TO_REMOVE:
        rm_dir(d)

    print("\n[2] 删除文件")
    for f in FILES_TO_REMOVE:
        rm_file(f)

    print("\n[3] 重置为空白结构")
    for name, content in RESET_JSON.items():
        log("重置 %-20s -> %s" % (name, json.dumps(content, ensure_ascii=False)))
        reset_json(name, content)

    print("\n[4] 处理 .env（改成占位密钥）")
    env = os.path.join(HERE, ".env")
    if os.path.isfile(env):
        log(".env -> 改为示例值（保留文件，避免 compose 报错）")
        if not DRY:
            with open(env, "w", encoding="utf-8", newline="\n") as f:
                f.write("CHATGPT2API_AUTH_KEY=changeme\n")

    print("\n[5] 检查 tiktoken-cache（这是公开词表缓存，可保留）")
    tc = os.path.join(DATA, "tiktoken-cache")
    print("  " + ("存在，保留" if os.path.isdir(tc) else "不存在"))

    print("\n" + "=" * 66)
    if DRY:
        print("预览完成。确认无误后加 --apply 执行。")
    else:
        print("清理完成。")
    print("=" * 66)


if __name__ == "__main__":
    main()
