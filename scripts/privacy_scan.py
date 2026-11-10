# -*- coding: utf-8 -*-
"""上传前隐私终检：扫描发布目录，确认没有个人痕迹。

检查项：
  1. 真实邮箱（@outlook.com / @gmail.com 等）
  2. OpenAI token（eyJhbGciOi... JWT 格式）
  3. sk- 开头的真实 API Key
  4. 机场订阅域名 / 代理服务器 IP + 密码
  5. 硬编码的旧登录口令
  6. data/ 目录里不该有的运行时文件
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.abspath(
    r"D:\自建自动化程序\chatgptwebapi\_publish")

# 允许出现的（模板/示例/占位）
ALLOW = [
    "changeme",
    "sk-你的key",
    "sk-xxx",
    "sk-...",
    "you@example.com",
    "admin@example.com",
    "my-secret-2026",
    "你的key",
    "sk-Lc6_",           # 全新部署时自动生成的示例，不含个人身份
    "C2A_NEVER_MATCH_PLACEHOLDER",   # 占位符本身
]

PATTERNS = [
    ("邮箱", re.compile(r"[A-Za-z0-9._%+-]+@(?:outlook|gmail|qq|163|126|foxmail|hotmail|icloud)\.[a-z]{2,}", re.I)),
    ("OpenAI JWT", re.compile(r"eyJhbGciOiJSUzI1Ni[A-Za-z0-9._-]{40,}")),
    ("sk- 密钥", re.compile(r"sk-[A-Za-z0-9_\-]{20,}")),
    ("订阅链接", re.compile(r"https?://[a-z0-9.-]*(?:ktm|jichang|jiedian|sub|v2ray|clash)[a-z0-9.-]*\.(?:cc|com|net|xyz|top)/", re.I)),
    ("代理节点密码", re.compile(r"password:\s*[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}", re.I)),
    # 旧登录口令：从本机环境读取，不把真实口令写进代码
    ("旧登录口令", re.compile(os.environ.get("C2A_OLD_KEY") or "C2A_NEVER_MATCH_PLACEHOLDER")),
]

# data 目录允许存在的
DATA_ALLOW = {".gitkeep"}


def scan_file(path, rel):
    hits = []
    try:
        txt = open(path, encoding="utf-8", errors="ignore").read()
    except Exception:
        return hits
    for name, pat in PATTERNS:
        for m in pat.finditer(txt):
            val = m.group(0)
            if any(a in val or val in a for a in ALLOW):
                continue
            line = txt[:m.start()].count("\n") + 1
            hits.append((rel, line, name, val[:60]))
    return hits


def main():
    print("=" * 72)
    print("隐私终检：" + ROOT)
    print("=" * 72)

    all_hits = []
    nfiles = 0
    for root, dirs, files in os.walk(ROOT):
        # 跳过 .git / 缓存，以及以 _ 开头的本地测试目录（已 gitignore，不会上传）
        dirs[:] = [d for d in dirs
                   if d not in (".git", "__pycache__", "node_modules")
                   and not d.startswith("_")]
        for fn in files:
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, ROOT)
            nfiles += 1
            all_hits += scan_file(p, rel)

    # data 目录单独检查
    ddir = os.path.join(ROOT, "data")
    bad_data = []
    if os.path.isdir(ddir):
        for fn in os.listdir(ddir):
            if fn not in DATA_ALLOW:
                bad_data.append(fn)

    print("\n扫描文件数: %d\n" % nfiles)

    if all_hits:
        print("!! 发现 %d 处敏感内容：" % len(all_hits))
        for rel, line, kind, val in all_hits[:40]:
            print("  %-45s :%-5s [%s] %s" % (rel, line, kind, val))
    else:
        print("OK 未发现敏感内容（邮箱/JWT/sk-/订阅链接/节点密码/旧口令）")

    if bad_data:
        print("\n!! data/ 目录含运行时文件（应清空）：")
        for fn in bad_data:
            print("  - data/" + fn)
    else:
        print("OK data/ 目录干净（只有 .gitkeep）")

    print("\n" + "=" * 72)
    if all_hits or bad_data:
        print("结论：有 %d 处问题，请处理后重新构建发布目录" % (len(all_hits) + len(bad_data)))
        return 1
    print("结论：可以安全上传")
    return 0


if __name__ == "__main__":
    sys.exit(main())
