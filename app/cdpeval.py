# -*- coding: utf-8 -*-
"""极简 Chrome DevTools Protocol 调用

容器里的 Chromium 开了 --remote-debugging-port=9222，
这里只做两件事：
  1. 在已有标签页里执行一段 JS（Runtime.evaluate）
  2. 新建标签打开网址

不依赖 websocket-client 之类的第三方库，直接用 socket 手写最小帧。

另含一个常驻监听：订阅 Target 事件，把每一次导航都过一遍，
一旦出现 OAuth 回调地址就立刻记下来。
（授权成功后的 callback 页会瞬间自动跳走，靠定时轮询根本抓不到。）
"""
from __future__ import annotations

import base64
import json
import os
import re
import socket
import struct
import threading
import time
import urllib.parse
import urllib.request

CDP = "http://127.0.0.1:9222"

# 回调地址落盘位置（容器内）
CB_FILE = "/app/data/oauth-callback.json"

_CB_PAT = re.compile(
    r"^https://(platform\.openai\.com/auth/callback|auth\.openai\.com/[^?]*callback)",
    re.I)

_seen = {}
_seen_lock = threading.Lock()
_monitor_started = False


def _record(url):
    """记下一个 OAuth 回调地址（内存 + 落盘，重启也能读到）。"""
    if not url or not _CB_PAT.match(url) or "code=" not in url:
        return False
    if url in _seen:
        return False
    with _seen_lock:
        _seen[url] = time.time()
    try:
        tmp = CB_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"url": url, "ts": time.time()}, f)
        os.replace(tmp, CB_FILE)
    except Exception:
        pass
    return True


def recent_callback(max_age=900):
    """取最近一次抓到的回调地址（默认 15 分钟内有效）。"""
    try:
        with open(CB_FILE, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("url") and (time.time() - float(d.get("ts") or 0) < max_age):
            return d["url"]
    except Exception:
        pass
    return ""


def clear_callback():
    try:
        os.remove(CB_FILE)
    except Exception:
        pass



def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def alive():
    """调试端口是否可用"""
    try:
        _opener().open(CDP + "/json/version", timeout=5).read()
        return True
    except Exception:
        return False


def tabs():
    """列出所有 page 类型标签"""
    try:
        raw = _opener().open(CDP + "/json/list", timeout=8).read().decode()
        return [t for t in json.loads(raw) if t.get("type") == "page"]
    except Exception:
        return []


class _WS:
    """够用就行的 websocket 客户端（只处理文本帧、无分片）"""

    def __init__(self, url, timeout=20):
        u = urllib.parse.urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port or 80), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        path = u.path + (("?" + u.query) if u.query else "")
        req = (
            "GET %s HTTP/1.1\r\nHost: %s:%s\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
            % (path, u.hostname, u.port, key)
        )
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise IOError("websocket 握手失败")
            buf += chunk

    def send(self, obj):
        data = json.dumps(obj).encode()
        mask = os.urandom(4)
        header = bytearray([0x81])
        n = len(data)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.sock.sendall(bytes(header) + masked)

    def recv(self):
        head = self.sock.recv(2)
        if len(head) < 2:
            return None
        n = head[1] & 0x7F
        if n == 126:
            n = struct.unpack(">H", self.sock.recv(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", self.sock.recv(8))[0]
        data = b""
        while len(data) < n:
            part = self.sock.recv(n - len(data))
            if not part:
                return None
            data += part
        try:
            return json.loads(data)
        except Exception:
            return None

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def evaluate(tab, expression, timeout=25):
    """在指定标签执行 JS（支持 await），返回结果值"""
    ws_url = tab.get("webSocketDebuggerUrl")
    if not ws_url:
        raise IOError("标签页没有调试地址")
    ws = _WS(ws_url, timeout=timeout)
    try:
        ws.send({"id": 1, "method": "Runtime.evaluate",
                 "params": {"expression": expression,
                            "awaitPromise": True,
                            "returnByValue": True}})
        for _ in range(120):
            msg = ws.recv()
            if msg and msg.get("id") == 1:
                try:
                    return msg["result"]["result"]["value"]
                except Exception:
                    return None
        return None
    finally:
        ws.close()


def open_url(url, timeout=15):
    """新建标签打开网址，返回标签 id"""
    body = b"{}"
    req = urllib.request.Request(
        CDP + "/json/new?" + urllib.parse.quote(url, safe=""),
        data=body, method="PUT")
    info = json.loads(_opener().open(req, timeout=timeout).read().decode())
    return info.get("id", "")


def close_tab(tab_id):
    try:
        _opener().open(CDP + "/json/close/" + tab_id, timeout=10).read()
        return True
    except Exception:
        return False


def exit_ip(timeout=30):
    pages = tabs()
    if not pages:
        return {"ok": False, "error": "内置浏览器没有可用标签页"}

    expr = (
        "fetch('https://chatgpt.com/cdn-cgi/trace',{cache:'no-store'})"
        ".then(function(r){return r.text()}).then(function(t){"
        "var o={};t.split('\\n').forEach(function(l){"
        "var i=l.indexOf('=');if(i>0){o[l.slice(0,i)]=l.slice(i+1);}});"
        "return JSON.stringify({ip:o.ip||'',loc:o.loc||'',colo:o.colo||''});})"
        ".catch(function(e){return JSON.stringify({ip:'',loc:'',err:String(e).slice(0,60)});})"
    )
    last = ""
    # 依次尝试每个标签（有的标签可能在报错页，换一个更稳）
    for page in pages:
        try:
            val = evaluate(page, expr, timeout=timeout)
        except Exception as e:
            last = str(e)[:100]
            continue
        if not val:
            continue
        try:
            d = json.loads(val)
        except Exception:
            continue
        if d.get("ip"):
            return {"ok": True, "ip": d["ip"], "loc": d.get("loc", ""),
                    "colo": d.get("colo", "")}
        last = d.get("err") or "没有取到 IP"
    return {"ok": False, "error": last or "取不到出口 IP"}


# ---------------------------------------------------------------- 回调监听
def _browser_ws_url():
    try:
        d = json.loads(_opener().open(CDP + "/json/version", timeout=5).read().decode())
        return d.get("webSocketDebuggerUrl") or ""
    except Exception:
        return ""


def _scan_existing():
    """把当前所有标签的地址过一遍（补上监听启动前就已经打开的）。"""
    for t in tabs():
        _record(t.get("url") or "")


def start_monitor():
    """启动常驻监听线程（幂等）。

    订阅浏览器级 Target 事件：
      Target.targetCreated / targetInfoChanged / targetNavigated
    任何标签一旦导航到 OAuth 回调地址，立刻记录 —— 回调页会自己跳走，
    靠 3 秒轮询一定漏。
    """
    global _monitor_started
    if _monitor_started:
        return True
    _monitor_started = True

    def loop():
        while True:
            try:
                ws_url = _browser_ws_url()
                if not ws_url:
                    time.sleep(5)
                    continue
                ws = _WS(ws_url, timeout=600)
                ws.send({"id": 1, "method": "Target.setDiscoverTargets",
                         "params": {"discover": True}})
                _scan_existing()
                while True:
                    msg = ws.recv()
                    if not msg:
                        break
                    info = ((msg.get("params") or {}).get("targetInfo")
                            or (msg.get("params") or {}).get("targetInfo"))
                    if isinstance(info, dict):
                        _record(info.get("url") or "")
                    # 有些 Chrome 版本走 targetNavigated
                    p = msg.get("params") or {}
                    if p.get("url"):
                        _record(p.get("url"))
            except Exception:
                pass
            time.sleep(3)

    th = threading.Thread(target=loop, daemon=True, name="c2a-cb-monitor")
    th.start()
    return True
