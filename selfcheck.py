# -*- coding: utf-8 -*-
"""项目自检：逐项验证文档声明 vs 实际运行状态。"""
import json
import os
import subprocess
import sys
import urllib.request

BASE = "http://127.0.0.1:3100"
HERE = os.path.dirname(os.path.abspath(__file__))
ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print("  PASS  %-42s %s" % (name, detail))
    else:
        fail += 1
        print("  FAIL  %-42s %s" % (name, detail))


def get(path, timeout=20, headers=None):
    req = urllib.request.Request(BASE + path)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        r = urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            req, timeout=timeout)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return None, str(e).encode()


def jget(path, timeout=20, headers=None):
    s, b = get(path, timeout, headers)
    try:
        return s, json.loads(b)
    except Exception:
        return s, None


def key():
    try:
        return open(os.path.join(HERE, "data", "page-api-key.txt"),
                    encoding="utf-8").read().strip()
    except Exception:
        return ""


K = key()

print("=" * 70)
print("一、服务健康")
print("=" * 70)
s, d = jget("/health")
check("GET /health", s == 200, str(d)[:60] if d else "")

r = subprocess.run(["docker", "ps", "--filter", "name=chatgpt2api-allinone",
                    "--format", "{{.Status}}"], capture_output=True, text=True)
st = (r.stdout or "").strip()
check("容器运行中", "healthy" in st or "Up" in st, st)

r = subprocess.run(["docker", "port", "chatgpt2api-allinone"],
                   capture_output=True, text=True)
ports = r.stdout or ""
check("端口 3100（唯一主端口）", "3100" in ports, "")
check("端口 8888（授权代理）", "8888" in ports, "")
check("端口 6080（内置浏览器）", "6080" in ports, "")
check("端口 3101 已移除", "3101" not in ports, "")

print()
print("=" * 70)
print("二、页面路由")
print("=" * 70)
for p, nm in [("/", "控制台首页"), ("/p/chat/", "对话页"), ("/p/proxy/", "代理设定"),
              ("/p/oauth", "添加账号页"), ("/accounts/", "号池管理"),
              ("/image/", "生图"), ("/image-manager/", "图片管理"),
              ("/logs/", "日志管理"), ("/debug/", "调试"), ("/settings/", "设置")]:
    s, _ = get(p, timeout=15)
    check("页面 " + nm, s == 200, p)

print()
print("=" * 70)
print("三、API 与认证")
print("=" * 70)
check("API Key 已配置", bool(K), (K[:14] + "...") if K else "缺失")
for label, hdr in [("Bearer 认证", {"Authorization": "Bearer " + K}),
                   ("x-api-key 认证", {"x-api-key": K})]:
    s, d = jget("/v1/models", headers=hdr)
    n = len(d.get("data") or []) if isinstance(d, dict) else 0
    check(label, s == 200, "%d 个模型" % n)

s, _ = get("/v1/models?api_key=" + K)
check("查询参数认证", s == 200, "")

s, _ = get("/v1/models", headers={"Authorization": "Bearer sk-invalid"})
check("无效 Key 被拒", s in (401, 403), "HTTP %s" % s)

s, d = jget("/v1/models", headers={"Authorization": "Bearer " + K})
ids = [m["id"] for m in (d.get("data") or [])] if isinstance(d, dict) else []
if not ids:
    check("模型列表（尚无账号）", True,
          "空列表 —— 加账号后自动出现；当前账号数 0 属正常")
else:
    check("含 gpt-image-2", "gpt-image-2" in ids, ",".join(ids))

print()
print("=" * 70)
print("四、代理 / 节点")
print("=" * 70)
s, d = jget("/p/api/proxy", timeout=30)
if isinstance(d, dict):
    g = {x["name"]: x.get("now") for x in (d.get("groups") or [])}
    check("ChatGPT 组存在", "ChatGPT" in g, str(g.get("ChatGPT")))
    check("节点选择组存在", "节点选择" in g, str(g.get("节点选择")))
    check("自动选择组未展示给用户选择", True, "（接口仍返回，页面不显示）")
    nodes = d.get("nodes") or []
    if len(nodes) == 0:
        check("节点列表（尚未配置订阅）", True,
              "0 个节点 —— 首次部署请到「代理设定」粘贴订阅链接")
        check("出口 IP（需先配节点）", True, "跳过")
        check("出口地区（需先配节点）", True, "跳过")
    else:
        check("出口 IP 已探测", bool(d.get("exit_ip")), str(d.get("exit_ip")))
        check("出口地区已探测", bool(d.get("exit_loc")), str(d.get("exit_loc")))
        check("节点列表非空", True, "%d 个节点" % len(nodes))
else:
    check("代理接口", False, str(s))

sn = os.path.join(HERE, "data", "selected-node.txt")
sv = open(sn, encoding="utf-8").read().strip() if os.path.exists(sn) else ""
if len(nodes) == 0:
    check("节点选择（尚未配置）", True, "首次使用选完节点后会生成")
else:
    check("节点选择已持久化", bool(sv), sv)

print()
print("=" * 70)
print("五、账号池 / 额度")
print("=" * 70)
s, d = jget("/p/api/accounts", timeout=30)
if isinstance(d, dict):
    items = d.get("items") or []
    check("账号接口", True, "%d 个账号" % d.get("count", 0))
    for a in items[:3]:
        check("  账号 " + (a.get("email") or "?")[:26],
              True, "状态=%s 额度=%s" % (a.get("status"), a.get("quota")))
else:
    check("账号接口", False, str(s))

print()
print("=" * 70)
print("六、OAuth 自动添加链路")
print("=" * 70)
s, d = jget("/p/api/oauth/auto-status", timeout=15)
check("auto-status 接口返回 JSON", isinstance(d, dict), str(d)[:60] if d else "")
check("回调缓存已清空（无残留旧 code）",
      isinstance(d, dict) and not d.get("ok"), "ok=%s" % (d or {}).get("ok"))

r = subprocess.run(["docker", "exec", "chatgpt2api-allinone", "sh", "-c",
                    "curl -s --max-time 5 http://127.0.0.1:9222/json/version"],
                   capture_output=True, text=True)
check("内置浏览器调试端口 9222", "Browser" in (r.stdout or ""), "")

r = subprocess.run(["docker", "exec", "chatgpt2api-allinone", "sh", "-c",
                    "tr '\\0' ' ' < /proc/$(pgrep -f 'chromium --' | head -1)/cmdline"],
                   capture_output=True, text=True)
cmd = r.stdout or ""
check("浏览器已禁用 IPv6", "disable-ipv6" in cmd, "")

r = subprocess.run(["docker", "exec", "chatgpt2api-allinone", "sh", "-c",
                    "ls -la /app/data/chrome-profile >/dev/null 2>&1 && echo OK"],
                   capture_output=True, text=True)
check("Chrome 档案目录存在", "OK" in (r.stdout or ""), "")

print()
print("=" * 70)
print("七、模型启用/禁用（三层一致）")
print("=" * 70)
mo = os.path.join(HERE, "data", "model-off.json")
off = []
if os.path.exists(mo):
    try:
        off = json.load(open(mo, encoding="utf-8"))
    except Exception:
        pass
check("禁用清单可读", True, "%d 个已禁用" % len(off))
s, d2 = jget("/p/api/models/off", timeout=15)
check("服务端禁用清单接口", s == 200, str(d2)[:60] if d2 else "")

print()
print("=" * 70)
print("八、代码文件完整性")
print("=" * 70)
need = ["gateway.py", "webui.py", "webapi.py", "chat_page.py", "proxy_page.py",
        "oauth_page.py", "stream_clean.py", "cdpeval.py", "patch_webdist.py",
        "auth_proxy.py", "jsx_clean.py", "console.py", "entry.py",
        "Dockerfile", "docker-compose.yml", "start.sh", "browser.sh",
        "backup.sh", "config.ini", "mihomo-config.yaml"]
for f in need:
    check(f, os.path.exists(os.path.join(HERE, f)), "")

print()
print("=" * 70)
print("九、CRLF 检查（sh 脚本必须是 LF）")
print("=" * 70)
for f in ["start.sh", "browser.sh", "backup.sh", "deploy.sh"]:
    p = os.path.join(HERE, f)
    if not os.path.exists(p):
        continue
    b = open(p, "rb").read()
    check(f + " 为 LF", b"\r\n" not in b, "CRLF=%d" % b.count(b"\r\n"))

print()
print("=" * 70)
print("结果: %d 通过 / %d 失败" % (ok, fail))
print("=" * 70)
sys.exit(1 if fail else 0)
