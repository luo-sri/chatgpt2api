# -*- coding: utf-8 -*-
"""项目内一键更新（无需借助外部工具）

背景：
  用户在控制台点「版本号 → 立即更新」，就能把项目更新到最新版，
  不需要登录 NAS / 服务器执行 git pull 或 docker build。
  用户已有的数据（账号、代理、密码等）全部保留。

实现要点（为什么这么设计）：

1. **代码放两份**
   镜像里的 /opt/gateway/ 是「镜像自带的代码」，容器重建就回去。
   所以更新后的代码必须先落到持久化的 /app/data/code/，
   再由 start.sh 在容器启动时覆盖回 /opt/gateway/。
   这样「点更新」和「docker compose up --build」都不会丢更新。

2. **只更新 .py，不碰资源与配置**
   只下载 app/ 下的 Python 文件。mihomo 配置、wheels、GEO 库、
   data/ 一律不碰 —— 这些要么是用户数据，要么是二进制大文件。

3. **先校验再落盘**
   下载后先用 ast.parse 校验语法，通过才写入。
   任何一个文件语法坏了就整体放弃，不把服务搞成起不来的状态。

4. **先备份再替换**
   备份到 /app/data/code-backup-<时间戳>/，出问题可以手工回滚。

5. **重启方式**
   网关自己没法重启自己，所以更新完成后直接 os._exit()，
   由 start.sh 的保活循环发现 health 不通 → 退出 → docker 重启容器。
   容器带了 restart: unless-stopped，会自动起来，约 20-40 秒。
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import time
import urllib.parse
import urllib.request

CODE_DIR = "/opt/gateway"          # 运行目录（镜像自带）
PERSIST_DIR = "/app/data/code"     # 持久化目录（挂载卷，重建容器不丢）
BACKUP_ROOT = "/app/data"          # 备份根目录

# 需要更新的文件（相对仓库路径 -> 容器内文件名）
FILES = [
    "app/gateway.py",
    "app/webui.py",
    "app/webapi.py",
    "app/update_ui.py",
    "app/patch_webdist.py",
    "app/stream_clean.py",
    "app/jsx_clean.py",
    "app/cdpeval.py",
    "app/auth_proxy.py",
    "app/console.py",
    "app/entry.py",
    "app/pages/chat_page.py",
    "app/pages/proxy_page.py",
    "app/pages/oauth_page.py",
    "app/pages/onboarding.py",
]


def raw_base():
    """更新源地址。

    默认走 GitHub raw。允许用环境变量覆盖，方便：
      · 官方源被墙时换成镜像加速地址
      · 内网 / 离线环境指向自己搭的静态目录
    例：C2A_UPDATE_SOURCE=https://cdn.jsdelivr.net/gh/luo-sri/chatgpt2api@main
    """
    v = (os.environ.get("C2A_UPDATE_SOURCE") or "").strip().rstrip("/")
    if v:
        return v
    return ("https://raw.githubusercontent.com/%s/%s/main"
            % (os.environ.get("C2A_REPO_OWNER", "luo-sri"),
               os.environ.get("C2A_REPO_NAME", "chatgpt2api")))


def _opener():
    # 直连优先（容器内访问 GitHub 通常走代理，但 raw 域名有时直连更快）
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _opener_proxy():
    h = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}
    return urllib.request.build_opener(urllib.request.ProxyHandler(h))


def _fetch(url, timeout=20):
    """拉一个文件。

    顺序很关键：容器内访问 raw.githubusercontent.com 直连经常被墙，
    等直连超时要十几秒，用户点了按钮会以为卡死。
    所以先走容器代理（mihomo 7890，通常已配好节点），失败再试直连。
    """
    req = urllib.request.Request(url, headers={"User-Agent": "chatgpt2api-updater"})

    # 内网/本机地址不要走代理：否则 "从内网镜像更新" 会被 mihomo 兜一圈甚至直接失败。
    # （urllib 的 ProxyHandler 不认 NO_PROXY 环境变量，只能自己判断）
    try:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
    except Exception:
        host = ""
    local = (host in ("127.0.0.1", "localhost", "::1", "0.0.0.0")
             or host.startswith("10.")
             or host.startswith("192.168.")
             or (host.startswith("172.") and 16 <= int(
                 (host.split(".") + ["0", "0"])[1] or 0) <= 31))
    ops = (_opener(),) if local else (_opener_proxy(), _opener())

    last = None
    for op in ops:
        try:
            with op.open(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e
    raise last if last else RuntimeError("fetch failed")


def _target_name(rel):
    """app/pages/chat_page.py -> chat_page.py（容器内都在 /opt/gateway 平铺）"""
    return os.path.basename(rel)


def current_version():
    try:
        with open("/app/VERSION", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def _read_text(path, limit=400000):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except Exception:
        return ""


def _pick_section(md, ver):
    """从 CHANGELOG 里截出指定版本那一节。"""
    import re
    tag = str(ver or "").replace("v", "").strip()
    if not md:
        return ""
    if tag:
        m = re.search(r"^##\s*v?" + re.escape(tag) + r"[^\n]*$", md, re.M)
        if m:
            rest = md[m.end():]
            n = re.search(r"^##\s", rest, re.M)
            return (rest[:n.start()] if n else rest).strip()
    # 找不到这个版本的标题（比如 CHANGELOG 还没写这一版），
    # 退回展示「第一个版本章节」—— 总比给用户一片空白好
    first = re.search(r"^##\s*v?[\d.]+[^\n]*$", md, re.M)
    if not first:
        return ""
    rest0 = md[first.end():]
    n0 = re.search(r"^##\s", rest0, re.M)
    return (rest0[:n0.start()] if n0 else rest0).strip()


_CACHE = {"v": None, "ts": 0.0}
_CACHE_TTL = 60.0


def check(repo, raw_base, timeout=25, use_cache=True):
    """检查是否有新版本，返回给前端的结构。

    带 60 秒缓存：用户反复点版本号时不必每次都请求 GitHub，
    首次检查后再次打开面板是秒开的。
    """
    import time as _t
    now = _t.time()
    if use_cache and _CACHE["v"] and (now - _CACHE["ts"] < _CACHE_TTL):
        return _CACHE["v"]

    cur = current_version()
    latest, notes, err = "", "", ""

    # 1) 最新版本号
    try:
        raw = _fetch(raw_base + "/VERSION", timeout=timeout).decode("utf-8", "replace").strip()
        latest = raw.splitlines()[0].strip() if raw else ""
        if latest and not latest.startswith("v"):
            latest = "v" + latest
    except Exception as e:
        err = "获取版本号失败: " + str(e)[:100]

    # 2) 更新说明
    if latest:
        try:
            md = _fetch(raw_base + "/CHANGELOG.md", timeout=timeout).decode("utf-8", "replace")
            notes = _pick_section(md, latest) or _pick_section(md, "")
        except Exception:
            notes = ""

    out = {
        "current": ("v" + cur) if cur and not cur.startswith("v") else (cur or ""),
        "latest": latest,
        "notes": notes[:8000],
        "can_update": bool(latest) and _newer(latest, cur),
        "error": err,
    }
    # 只有真正拿到版本号才缓存，失败的结果不缓存（否则要等 60 秒才能重试）
    if latest:
        _CACHE["v"] = out
        _CACHE["ts"] = now
    return out


def _newer(latest, cur):
    def parts(v):
        v = str(v or "").replace("v", "").replace("V", "").strip()
        out = []
        for x in v.split("."):
            try:
                out.append(int("".join(ch for ch in x if ch.isdigit()) or 0))
            except Exception:
                out.append(0)
        return out
    a, b = parts(latest), parts(cur)
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else 0
        y = b[i] if i < len(b) else 0
        if x > y:
            return True
        if x < y:
            return False
    return False


def apply_update(repo, raw_base, version, timeout=60):
    """下载 → 校验 → 备份 → 落盘（持久化 + 运行目录）。

    返回 {"ok": bool, "to": version, "files": n, "error": str}
    """
    try:
        os.makedirs(PERSIST_DIR, exist_ok=True)
    except Exception as e:
        return {"ok": False, "error": "无法创建持久化目录: " + str(e)[:120]}

    # ---------- 1. 先全部下载到内存并校验 ----------
    blobs = {}
    errors = []
    for rel in FILES:
        url = "%s/%s" % (raw_base.rstrip("/"), rel)
        try:
            raw = _fetch(url, timeout=timeout)
        except Exception as e:
            # 老版本可能没有某个文件（比如 update_ui.py），跳过而不失败
            errors.append("%s: %s" % (rel, str(e)[:60]))
            continue
        try:
            text = raw.decode("utf-8")
        except Exception:
            errors.append("%s: 非 UTF-8" % rel)
            continue
        # 语法校验：坏一个就整体放弃，避免把服务搞成起不来
        try:
            ast.parse(text)
        except SyntaxError as e:
            return {"ok": False,
                    "error": "下载的 %s 语法错误（第 %s 行）：%s" % (
                        rel, getattr(e, "lineno", "?"), str(e)[:120])}
        blobs[rel] = text

    if not blobs:
        return {"ok": False,
                "error": "一个文件都没下载成功，请检查网络。首个错误：" + (errors[0] if errors else "未知")}

    # 关键文件必须有，否则更新后起不来
    must = ["app/gateway.py", "app/webui.py", "app/webapi.py"]
    missing = [m for m in must if m not in blobs]
    if missing:
        return {"ok": False,
                "error": "缺少必要文件，已放弃更新：" + ", ".join(missing)}

    # ---------- 2. 备份当前代码 ----------
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bdir = os.path.join(BACKUP_ROOT, "code-backup-" + stamp)
    try:
        os.makedirs(bdir, exist_ok=True)
        for rel in blobs:
            src = os.path.join(CODE_DIR, _target_name(rel))
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(bdir, _target_name(rel)))
        with open(os.path.join(bdir, "VERSION"), "w", encoding="utf-8") as f:
            f.write(current_version())
    except Exception as e:
        return {"ok": False, "error": "备份失败，已放弃更新: " + str(e)[:120]}

    # ---------- 3. 写持久化目录 + 运行目录 ----------
    written = 0
    try:
        for rel, text in blobs.items():
            name = _target_name(rel)
            for d in (PERSIST_DIR, CODE_DIR):
                dst = os.path.join(d, name)
                tmp = dst + ".new"
                with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
                os.replace(tmp, dst)
            written += 1
    except Exception as e:
        return {"ok": False, "error": "写入失败: " + str(e)[:150]}

    # ---------- 4. 记录已更新到的版本 ----------
    try:
        with open(os.path.join(PERSIST_DIR, "VERSION"), "w", encoding="utf-8") as f:
            f.write(str(version).replace("v", ""))
    except Exception:
        pass

    return {"ok": True, "to": version, "files": written,
            "skipped": errors[:10], "backup": os.path.basename(bdir)}


def updated_version():
    """持久化目录里记录的目标版本（供启动脚本 / 前端展示）。"""
    try:
        with open(os.path.join(PERSIST_DIR, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""
