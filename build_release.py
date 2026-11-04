# -*- coding: utf-8 -*-
"""构建 GitHub 发布目录：只复制白名单文件，绝不带本机数据。

原则：白名单（显式列出要发布什么），而不是黑名单（列出不发布什么）。
黑名单容易漏，白名单不可能漏。

用法： python build_release.py
输出： D:\\自建自动化程序\\chatgptwebapi\\_publish
"""
from __future__ import annotations

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "_publish"))

# ---- 要发布的源码文件（根目录）----
FILES = [
    "Dockerfile",
    "docker-compose.yml",
    "start.sh",
    "browser.sh",
    "backup.sh",
    "deploy.sh",
    "gateway.py",
    "webui.py",
    "webapi.py",
    "chat_page.py",
    "proxy_page.py",
    "oauth_page.py",
    "onboarding.py",
    "stream_clean.py",
    "jsx_clean.py",
    "cdpeval.py",
    "patch_webdist.py",
    "auth_proxy.py",
    "console.py",
    "entry.py",
    "config.ini",
    "selfcheck.py",
    "cleanup_for_publish.py",
    "privacy_scan.py",
    "build_release.py",
    "mihomo-config.template.yaml",
]

# ---- 配置文件示例（不能带真实值）----
TEMPLATES = {
    "config.json": """{
  "auth-key": "changeme"
}
""",
    ".env.example": """# 登录控制台的密钥（首次部署后请改掉）
# 建议：字母+数字，8 位以上
CHATGPT2API_AUTH_KEY=changeme

# 时区
TZ=Asia/Shanghai
""",
    "mihomo-config.yaml": """# 占位文件：首次部署后请到「代理设定」页粘贴你的订阅链接，
# 系统会自动填充节点。详见 mihomo-config.template.yaml
mixed-port: 7890
allow-lan: false
bind-address: 127.0.0.1
mode: rule
log-level: warning
ipv6: false
external-controller: 127.0.0.1:9090
proxy-groups:
  - name: ChatGPT
    type: select
    proxies:
      - 节点选择
  - name: 节点选择
    type: select
    proxies:
      - DIRECT
rules:
  - MATCH,DIRECT
""",
    "data/.gitkeep": "",
}

# ---- 文档与许可证 ----
DOCS = [
    "README.md",
    "LICENSE",
    "VERSION",
    ".gitignore",
    "docs/DEPLOY-WINDOWS.md",
    "docs/DEPLOY-DOCKER.md",
    "docs/DEPLOY-NAS.md",
    "docs/DEPLOY-LINUX.md",
    "docs/API.md",
    "docs/ARCHITECTURE.md",
    "docs/FAQ.md",
]

# ---- 截图 ----
SHOTS = "docs/screenshots"


def cp(src, dst):
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    shutil.copy2(src, dst)


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    os.makedirs(os.path.join(OUT, "data"))

    missing = []
    n = 0
    for f in FILES:
        s = os.path.join(HERE, f)
        if not os.path.isfile(s):
            missing.append(f)
            continue
        cp(s, os.path.join(OUT, f))
        n += 1

    for name, content in TEMPLATES.items():
        p = os.path.join(OUT, name.replace("/", os.sep))
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        n += 1

    for d in DOCS:
        s = os.path.join(HERE, d)
        if not os.path.isfile(s):
            missing.append(d)
            continue
        cp(s, os.path.join(OUT, d))
        n += 1

    sd = os.path.join(HERE, SHOTS)
    if os.path.isdir(sd):
        for fn in os.listdir(sd):
            if fn.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")):
                cp(os.path.join(sd, fn), os.path.join(OUT, SHOTS, fn))
                n += 1

    print("已复制 %d 个文件 -> %s" % (n, OUT))
    if missing:
        print("\n以下文件缺失（需要先创建）:")
        for m in missing:
            print("  - " + m)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
