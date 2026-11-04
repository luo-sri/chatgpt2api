#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ChatGPT2API 一体化控制台（容器内运行）

功能：
  1. 代理状态：当前节点、延迟、切换节点
  2. 订阅管理：网页里改订阅链接，一键更新节点
  3. 服务总览：容器 / 账号 / 额度

监听 8080，路径 /console
"""

import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request

MIHOMO_API = "http://127.0.0.1:9090"
APP_API = "http://127.0.0.1:3001"
AUTH_KEY = os.environ.get("CHATGPT2API_AUTH_KEY", "")
CONFIG_PATH = "/root/.config/mihomo/config.yaml"
SUB_PATH = "/app/data/subscription.txt"
LOG_PATH = "/app/data/console.log"


def _get(url, timeout=15):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open(url, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _put(url, data, timeout=15):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), method="PUT")
    req.add_header("Content-Type", "application/json")
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open(req, timeout=timeout) as r:
        return r.status


def _post_json(url, data, timeout=60, headers=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with op.open(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


# ---------------------------------------------------------------- 代理操作
def proxy_groups():
    """返回 ChatGPT 相关分组与当前选择"""
    data = json.loads(_get(MIHOMO_API + "/proxies"))
    pr = data.get("proxies", {})
    out = []
    for name in ("ChatGPT", "优先线路", "节点选择", "自动选择"):
        g = pr.get(name)
        if not g:
            continue
        out.append({
            "name": name,
            "type": g.get("type"),
            "now": g.get("now"),
            "count": len(g.get("all") or []),
        })
    return out


def proxy_nodes():
    """列出所有可选节点（带延迟）"""
    data = json.loads(_get(MIHOMO_API + "/proxies"))
    pr = data.get("proxies", {})
    nodes = []
    for name, v in pr.items():
        t = v.get("type")
        if t in ("Shadowsocks", "Vmess", "Trojan", "Hysteria2", "Vless", "ShadowsocksR", "WireGuard"):
            hist = v.get("history") or []
            delay = hist[-1].get("delay") if hist else None
            nodes.append({"name": name, "type": t, "delay": delay, "alive": v.get("alive")})
    return nodes


def proxy_delay(group="ChatGPT", timeout=8000):
    url = (MIHOMO_API + "/proxies/" + urllib.parse.quote(group, safe="")
           + "/delay?timeout=" + str(timeout)
           + "&url=" + urllib.parse.quote("https://chatgpt.com/cdn-cgi/trace", safe=""))
    try:
        return json.loads(_get(url, timeout=timeout / 1000 + 10)).get("delay")
    except Exception:
        return None


def proxy_select(group, node):
    return _put(MIHOMO_API + "/proxies/" + urllib.parse.quote(group, safe=""), {"name": node})


# ---------------------------------------------------------------- 订阅更新
def _fetch_sub(url):
    req = urllib.request.Request(url, headers={"User-Agent": "clash-verge/v2.0.0"})
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open(req, timeout=60) as r:
        text = r.read().decode("utf-8", "replace")
    if "proxies:" not in text:
        raise RuntimeError("订阅内容不是 Clash 格式")
    return text


def _resolve(host):
    """用多个 DNS 解析，取多数一致结果（避开污染）"""
    import socket
    votes = {}
    for dns in ("223.5.5.5", "114.114.114.114"):
        try:
            out = subprocess.run(["nslookup", host, dns], capture_output=True,
                                 text=True, timeout=15).stdout
            ips = re.findall(r"^Address(?:es)?:\s+(\d+\.\d+\.\d+\.\d+)", out, re.M)
            ips = [i for i in ips if i != dns]
            if ips:
                votes.setdefault(ips[-1], 0)
                votes[ips[-1]] += 1
        except Exception:
            continue
    if not votes:
        return None
    return max(votes.items(), key=lambda kv: kv[1])[0]


HEAD = """mixed-port: 7890
allow-lan: false
bind-address: 127.0.0.1
mode: rule
log-level: warning
ipv6: false
unified-delay: true
tcp-concurrent: true
external-controller: 127.0.0.1:9090
dns:
  enable: true
  ipv6: false
  enhanced-mode: fake-ip
  fake-ip-range: 198.18.0.1/16
  nameserver:
    - 223.5.5.5
    - 114.114.114.114
  fallback:
    - https://1.1.1.1/dns-query
    - https://8.8.8.8/dns-query
"""


def update_subscription(url):
    text = _fetch_sub(url)
    pi, gi, ri = text.find("proxies:"), text.find("proxy-groups:"), text.find("rules:")
    if min(pi, gi, ri) < 0:
        raise RuntimeError("订阅缺少 proxies / proxy-groups / rules")
    proxies = text[pi:gi].rstrip()
    groups = text[gi:ri].rstrip()
    rules = text[ri:].rstrip()

    hosts = set(re.findall(
        r"type:\s*ss.*?server:\s*([a-zA-Z0-9][a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})", proxies))
    hosts = {h for h in hosts if not re.match(r"^\d+\.\d+\.\d+\.\d+$", h)}
    mapping = {}
    for h in hosts:
        ip = _resolve(h)
        if ip:
            mapping[h] = ip
    for h, ip in mapping.items():
        proxies = re.sub(r"(server:\s*)" + re.escape(h) + r"\b", r"\1" + ip, proxies)

    # 在 rules 最前面加 Azure CDN 直连
    inject = ("rules:\n"
              "  - 'DOMAIN-SUFFIX,blob.core.windows.net,DIRECT'\n"
              "  - 'DOMAIN-SUFFIX,azureedge.net,DIRECT'\n")
    tail = rules.split("\n", 1)[1] if "\n" in rules else ""
    conf = HEAD + "\n" + proxies + "\n\n" + groups + "\n\n" + inject + tail + "\n"

    if os.path.exists(CONFIG_PATH):
        try:
            os.replace(CONFIG_PATH, CONFIG_PATH + ".bak")
        except Exception:
            pass
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(conf)

    try:
        with open(SUB_PATH, "w", encoding="utf-8") as f:
            f.write(url)
    except Exception:
        pass

    # 通知 mihomo 重载
    try:
        _put(MIHOMO_API + "/configs?force=true", {"path": CONFIG_PATH})
    except Exception:
        pass

    return {"resolved": mapping, "nodes": len(hosts)}


# ---------------------------------------------------------------- 应用信息
def app_status():
    out = {}
    try:
        out["version"] = json.loads(_get(APP_API + "/version", 10)).get("version")
    except Exception:
        out["version"] = None
    try:
        req = urllib.request.Request(APP_API + "/api/accounts")
        req.add_header("Authorization", "Bearer " + AUTH_KEY)
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with op.open(req, timeout=15) as r:
            d = json.loads(r.read().decode())
        items = d.get("items", [])
        out["accounts"] = len(items)
        out["account_detail"] = [{
            "email": a.get("email"),
            "type": a.get("type"),
            "status": a.get("status"),
            "quota": a.get("quota"),
            "limits": {lp.get("feature_name"): lp.get("remaining")
                       for lp in (a.get("limits_progress") or [])},
        } for a in items]
    except Exception as e:
        out["accounts"] = None
        out["account_error"] = str(e)[:100]
    return out


# ---------------------------------------------------------------- 页面
PAGE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ChatGPT2API 控制台</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#0f1117;color:#e2e8f0;padding:20px}
.wrap{max-width:900px;margin:0 auto}
h1{font-size:20px;margin-bottom:4px}
.sub{color:#64748b;font-size:13px;margin-bottom:20px}
.card{background:#1a1d27;border:1px solid #2a2d3a;border-radius:12px;padding:18px;margin-bottom:16px}
.card h2{font-size:15px;margin-bottom:14px;color:#a5b4fc}
.row{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #232634;font-size:14px}
.row:last-child{border:none}
.k{color:#94a3b8}
.v{font-weight:600}
.ok{color:#22c55e}.warn{color:#f59e0b}.bad{color:#ef4444}
button{background:#4f46e5;color:#fff;border:0;border-radius:8px;padding:10px 18px;font-size:14px;cursor:pointer}
button:hover{background:#4338ca}
button:disabled{background:#374151;cursor:not-allowed}
input{width:100%;background:#0f1117;border:1px solid #2a2d3a;color:#e2e8f0;border-radius:8px;padding:10px;font-size:13px}
select{background:#0f1117;border:1px solid #2a2d3a;color:#e2e8f0;border-radius:8px;padding:8px;font-size:13px;max-width:320px}
.tag{display:inline-block;padding:2px 8px;border-radius:6px;font-size:12px;background:#312e81;color:#c7d2fe}
#msg{margin-top:12px;font-size:13px;min-height:18px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:#94a3b8;font-weight:500;padding:6px 8px;border-bottom:1px solid #2a2d3a}
td{padding:6px 8px;border-bottom:1px solid #232634}
</style></head><body>
<div class="wrap">
<h1>ChatGPT2API 控制台</h1>
<div class="sub">代理节点 · 订阅管理 · 服务总览</div>

<div class="card">
  <h2>当前代理状态</h2>
  <div id="proxy">加载中…</div>
</div>

<div class="card">
  <h2>切换节点</h2>
  <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
    <select id="group"></select>
    <select id="node" style="flex:1;min-width:220px"></select>
    <button onclick="applyNode()">应用</button>
  </div>
  <div id="msg"></div>
</div>

<div class="card">
  <h2>更新订阅</h2>
  <div style="font-size:13px;color:#94a3b8;margin-bottom:10px">粘贴机场订阅链接，自动解析节点、处理 DNS 污染、重载配置。</div>
  <input id="suburl" placeholder="https://xxx/api/v1/client/subscribe?token=...">
  <div style="margin-top:12px"><button id="subbtn" onclick="updateSub()">更新订阅</button></div>
  <div id="submsg" style="margin-top:10px;font-size:13px"></div>
</div>

<div class="card">
  <h2>服务与账号</h2>
  <div id="app">加载中…</div>
</div>

</div>
<script>
let NODES=[];

function el(id){return document.getElementById(id)}
function color(d){return d==null?'':(d<400?'ok':(d<900?'warn':'bad'))}

async function loadProxy(){
  const r = await fetch('/api/proxy');
  const d = await r.json();
  let h = '';
  (d.groups||[]).forEach(g=>{
    h += `<div class="row"><span class="k">${g.name}</span><span class="v">${g.now||'-'} <span class="tag">${g.type}</span></span></div>`;
  });
  h += `<div class="row"><span class="k">ChatGPT 延迟</span><span class="v ${color(d.delay)}">${d.delay==null?'测不出':d.delay+' ms'}</span></div>`;
  el('proxy').innerHTML = h;

  const gs = el('group'); gs.innerHTML='';
  (d.groups||[]).forEach(g=>{
    const o=document.createElement('option'); o.value=g.name; o.textContent=g.name+' ('+g.type+')'; gs.appendChild(o);
  });
  if(d.groups && d.groups.length) gs.value = d.groups[0].name;

  NODES = d.nodes||[];
  fillNodes();
}

function fillNodes(){
  const s = el('node'); s.innerHTML='';
  NODES.forEach(n=>{
    const o=document.createElement('option'); o.value=n.name;
    o.textContent = n.name + (n.delay?`  (${n.delay}ms)`:'');
    s.appendChild(o);
  });
}

async function applyNode(){
  const g = el('group').value, n = el('node').value;
  el('msg').textContent = '正在切换…';
  const r = await fetch('/api/proxy/select', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({group:g,node:n})});
  const d = await r.json();
  el('msg').textContent = d.ok ? '已切换到 '+n : ('失败: '+(d.error||''));
  setTimeout(loadProxy, 1200);
}

async function updateSub(){
  const u = el('suburl').value.trim();
  if(!u){ el('submsg').textContent='请先填写订阅链接'; return; }
  const b = el('subbtn'); b.disabled=true; b.textContent='更新中…';
  el('submsg').textContent='正在拉取订阅并解析节点…';
  try{
    const r = await fetch('/api/subscription', {method:'POST',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:u})});
    const d = await r.json();
    if(d.ok){
      el('submsg').innerHTML = `<span class="ok">更新成功</span>：解析 ${d.nodes} 个域名，已写入配置并重载。`;
      setTimeout(loadProxy, 2000);
    } else {
      el('submsg').innerHTML = `<span class="bad">失败</span>：${d.error}`;
    }
  }catch(e){ el('submsg').innerHTML = '<span class="bad">请求异常</span>'; }
  b.disabled=false; b.textContent='更新订阅';
}

async function loadApp(){
  const r = await fetch('/api/app');
  const d = await r.json();
  let h = `<div class="row"><span class="k">ChatGPT2API 版本</span><span class="v">${d.version||'未就绪'}</span></div>`;
  h += `<div class="row"><span class="k">账号数</span><span class="v">${d.accounts==null?'查询失败':d.accounts}</span></div>`;
  if(d.account_detail && d.account_detail.length){
    h += '<table style="margin-top:12px"><tr><th>账号</th><th>状态</th><th>生图余额</th><th>各额度</th></tr>';
    d.account_detail.forEach(a=>{
      const lim = Object.entries(a.limits||{}).map(([k,v])=>k+':'+v).join(' · ');
      h += `<tr><td>${a.email||'-'}</td><td>${a.status||'-'}</td><td>${a.quota??'-'}</td><td style="color:#94a3b8">${lim}</td></tr>`;
    });
    h += '</table>';
  }
  el('app').innerHTML = h;
}

loadProxy(); loadApp();
setInterval(loadProxy, 30000);
</script></body></html>
"""


def start_console_server():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            raw = body.encode("utf-8") if isinstance(body, str) else body
            try:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except Exception:
                pass

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False))

        def do_GET(self):
            p = self.path.split("?")[0].rstrip("/")
            if p in ("/console", ""):
                self._send(200, PAGE, "text/html; charset=utf-8"); return
            if p == "/api/proxy":
                try:
                    self._json({"groups": proxy_groups(), "nodes": proxy_nodes(),
                                "delay": proxy_delay()})
                except Exception as e:
                    self._json({"groups": [], "nodes": [], "delay": None, "error": str(e)[:120]})
                return
            if p == "/api/app":
                self._json(app_status()); return
            if p == "/health":
                self._json({"status": "ok"}); return
            self._json({"error": "not found"}, 404)

        def do_POST(self):
            p = self.path.split("?")[0].rstrip("/")
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except Exception:
                body = {}
            if p == "/api/proxy/select":
                try:
                    proxy_select(body.get("group") or "ChatGPT", body.get("node") or "")
                    self._json({"ok": True})
                except Exception as e:
                    self._json({"ok": False, "error": str(e)[:150]})
                return
            if p == "/api/subscription":
                try:
                    r = update_subscription(body.get("url") or "")
                    self._json({"ok": True, **r})
                except Exception as e:
                    self._json({"ok": False, "error": str(e)[:200]})
                return
            self._json({"error": "not found"}, 404)

    srv = ThreadingHTTPServer(("0.0.0.0", 8080), H)
    srv.serve_forever()


if __name__ == "__main__":
    print("console listening on 0.0.0.0:8080/console", flush=True)
    start_console_server()
