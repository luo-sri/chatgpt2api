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
# 目录结构（v2.0.0 起重组，根目录只留少数关键文件）
FILES = [
    # 根目录
    "Dockerfile",
    "docker-compose.yml",
    "deploy.sh",
    "config.ini",
    # 应用代码
    "app/gateway.py",
    "app/webui.py",
    "app/webapi.py",
    "app/console.py",
    "app/entry.py",
    "app/auth_proxy.py",
    "app/jsx_clean.py",
    "app/stream_clean.py",
    "app/cdpeval.py",
    "app/patch_webdist.py",
    "app/pages/chat_page.py",
    "app/pages/proxy_page.py",
    "app/pages/oauth_page.py",
    "app/pages/onboarding.py",
    # 脚本（容器内启动用）
    "scripts/start.sh",
    "scripts/browser.sh",
    "scripts/backup.sh",
    # 工具
    "scripts/selfcheck.py",
    "scripts/cleanup_for_publish.py",
    "scripts/privacy_scan.py",
    "scripts/build_release.py",
    # 资源
    "assets/mihomo-config.yaml",
    "assets/mihomo-config.template.yaml",
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
    "assets/mihomo-config.yaml": """# 占位文件：首次部署后请到「代理设定」页粘贴你的订阅链接，
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

    # 二进制资源（地理库 + 离线 wheel）
    import glob
    for rel in ("assets/mihomo/Country.mmdb", "assets/mihomo/geosite.dat"):
        sp = os.path.join(HERE, rel)
        if os.path.isfile(sp):
            cp(sp, os.path.join(OUT, rel))
            n += 1
        else:
            missing.append(rel)
    whl = glob.glob(os.path.join(HERE, "assets", "wheels", "*.whl"))
    if whl:
        for w in whl:
            cp(w, os.path.join(OUT, "assets", "wheels", os.path.basename(w)))
            n += 1
    else:
        missing.append("assets/wheels/*.whl")

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
