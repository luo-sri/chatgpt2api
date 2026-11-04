# -*- coding: utf-8 -*-
"""WebUI 后端 API

挂到网关上（同一个 3000 端口），提供：
  /                 外壳
  /p/proxy          代理设定页
  /p/chat           对话页
  /p/api/proxy      当前节点 / 延迟 / 出口
  /p/api/proxy/select
  /p/api/proxy/test 全部测速
  /p/api/subscription  读写订阅链接
  /p/stats          顶部状态条
  /auth             OAuth 登录桥（容器内浏览器完成授权，无需本机代理）
"""
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

MIHOMO = "http://127.0.0.1:9090"
PANEL = "http://127.0.0.1:3001"
def _default_config():
    """优先用本机项目里的配置，方便 Windows 上与容器共用"""
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (r"D:\ChatGPT2API\mihomo-config.yaml",
                 os.path.join(here, "mihomo-config.yaml")):
        if os.path.exists(cand):
            return cand
    return "/root/.config/mihomo/config.yaml"


def _default_sub_path():
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (r"D:\ChatGPT2API\data\subscription.txt",
                 os.path.join(here, "subscription.txt")):
        d = os.path.dirname(cand)
        if os.path.isdir(d):
            return cand
    return "/app/data/subscription.txt"


CONFIG_PATH = os.environ.get("MIHOMO_CONFIG") or _default_config()
SUB_PATH = os.environ.get("SUB_PATH") or _default_sub_path()


def _auth_key():
    k = os.environ.get("CHATGPT2API_AUTH_KEY", "")
    if k:
        return k
    try:
        import configparser
        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini"),
                 encoding="utf-8")
        return cfg.get("upstream", "auth_key", fallback="")
    except Exception:
        return ""


def op():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def jget(url, timeout=20):
    return json.loads(op().open(url, timeout=timeout).read().decode())


def jput(url, data, timeout=20):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), method="PUT")
    req.add_header("Content-Type", "application/json")
    return op().open(req, timeout=timeout).status


# ---------------------------------------------------------------- 代理状态
def proxy_groups():
    pr = jget(MIHOMO + "/proxies").get("proxies", {})
    out = []
    for name in ("ChatGPT", "优先线路", "节点选择", "自动选择"):
        g = pr.get(name)
        if g:
            out.append({"name": name, "type": g.get("type"),
                        "now": g.get("now"), "count": len(g.get("all") or [])})
    return out


SKIP_WORDS = ("剩余流量", "套餐到期", "距离下次", "官网", "过期")


REMOVED_PATH = "/app/data/removed-nodes.json"


def _load_removed():
    try:
        return set(json.loads(open(REMOVED_PATH, encoding="utf-8").read()))
    except Exception:
        return set()


def remove_node(name, undo=False):
    """从节点列表里「删除」节点（软删除，可撤销）。

    不直接改 mihomo 配置：订阅一更新就会覆盖，而且改错会导致整个代理挂掉。
    这里用「删除清单」过滤展示与实际可选范围，安全且随时可恢复。
    """
    import os
    s = _load_removed()
    if undo:
        s.discard(name)
    else:
        s.add(name)
    os.makedirs(os.path.dirname(REMOVED_PATH), exist_ok=True)
    open(REMOVED_PATH, "w", encoding="utf-8").write(
        json.dumps(sorted(s), ensure_ascii=False))
    return {"ok": True, "removed": sorted(s)}


def get_removed():
    return {"removed": sorted(_load_removed())}


def proxy_nodes():
    pr = jget(MIHOMO + "/proxies").get("proxies", {})
    removed = _load_removed()
    out = []
    for name, v in pr.items():
        t = v.get("type")
        if t in ("Shadowsocks", "Vmess", "Trojan", "Hysteria2", "Vless",
                 "ShadowsocksR", "WireGuard", "Snell", "Http"):
            if any(w in name for w in SKIP_WORDS):
                continue
            if name in removed:
                continue
            h = v.get("history") or []
            out.append({"name": name, "type": t,
                        "delay": h[-1].get("delay") if h else None,
                        "alive": bool(v.get("alive"))})
    return out


_DELAY_CACHE = {"v": None, "ts": 0.0}
_DELAY_LOCK = None


def _delay_probe(group, timeout):
    try:
        u = (MIHOMO + "/proxies/" + urllib.parse.quote(group, safe="")
             + "/delay?timeout=" + str(timeout)
             + "&url=" + urllib.parse.quote("https://chatgpt.com/cdn-cgi/trace", safe=""))
        return jget(u, timeout=timeout / 1000 + 10).get("delay")
    except Exception:
        return None


def delay_of(group="ChatGPT", timeout=8000, max_age=20.0):
    """返回 ChatGPT 组延迟（纯缓存，永不阻塞）。测速在后台做。"""
    global _DELAY_LOCK
    import time as _t
    import threading as _th

    now = _t.time()
    fresh = _DELAY_CACHE["v"] is not None and (now - _DELAY_CACHE["ts"] < max_age)

    if not fresh and _DELAY_LOCK is None:
        _DELAY_LOCK = True

        def _run():
            global _DELAY_LOCK
            try:
                v = _delay_probe(group, timeout)
                if v is not None:
                    _DELAY_CACHE["v"] = v
                    _DELAY_CACHE["ts"] = _t.time()
            finally:
                _DELAY_LOCK = None

        _th.Thread(target=_run, daemon=True).start()

    return _DELAY_CACHE["v"]


_EXIT_CACHE = {"ip": None, "loc": None, "ts": 0.0}
_EXIT_LOCK = None


def _exit_probe():
    """真正去探测出口 IP（内部使用，可能耗时几秒）。

    首选 Cloudflare trace：走 mihomo 代理，与测速/ChatGPT 实际出口同一条路径，
    一次请求同时给出 ip 和地区；ipify 系列作兜底（该域名经此线路偶发握手超时）。
    """
    proxies = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxies))
    direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    # 1) CF trace（首选：ip + loc 一次拿全）
    #    只接受 IPv4：拿到 IPv6 说明这条请求没走 mihomo（代理只提供 IPv4 出口），
    #    得到的是本机宽带地址，地区和所选节点毫无关系，必须丢弃重试。
    for tmo in (5, 8):
        try:
            txt = opener.open("https://chatgpt.com/cdn-cgi/trace", timeout=tmo).read().decode()
            d = dict(l.split("=", 1) for l in txt.splitlines() if "=" in l)
            ip = d.get("ip") or ""
            if ip and ":" not in ip:
                return ip, d.get("loc") or ""
        except Exception:
            pass

    # 2) 兜底：ipify（api4 只解析 A 记录，强制 IPv4，避免本机 IPv6 优先造成误判）
    ip = ""
    for host in ("https://api4.ipify.org", "https://api.ipify.org"):
        try:
            ip = opener.open(host, timeout=6).read().decode().strip()
            if ip:
                break
        except Exception:
            ip = ""
    if not ip:
        return "", ""

    loc = ""
    try:
        j = json.loads(direct.open(
            "http://ip-api.com/json/%s?fields=status,countryCode" % ip,
            timeout=4).read().decode())
        if j.get("status") == "success":
            loc = (j.get("countryCode") or "").upper()
    except Exception:
        pass
    return ip, loc


def _exit_refresh():
    """后台线程里刷新缓存（不阻塞请求）。"""
    global _EXIT_LOCK
    try:
        ip, loc = _exit_probe()
        if ip:
            import time as _t
            # 只接受 IPv4 结果：IPv6 说明这条请求绕过了 mihomo（代理只提供 IPv4 出口），
            # 拿到的是本机宽带地址，地区和节点完全无关，写进缓存会一直显示错的。
            if ":" in ip:
                return
            _EXIT_CACHE["ip"] = ip
            _EXIT_CACHE["loc"] = loc
            _EXIT_CACHE["ts"] = _t.time()
    except Exception:
        pass
    finally:
        _EXIT_LOCK = None


def exit_info(max_age=25.0):
    """返回出口 IP / 地区（纯缓存，永不阻塞）。

    探测（约 4~6 秒）全部在后台线程做；页面请求只读缓存，
    没有缓存就先返回空值，下一轮刷新就能看到。
    """
    global _EXIT_LOCK
    import time as _t
    import threading as _th

    now = _t.time()
    fresh = _EXIT_CACHE["ip"] and (now - _EXIT_CACHE["ts"] < max_age)

    if not fresh and _EXIT_LOCK is None:
        _EXIT_LOCK = True
        _th.Thread(target=_exit_refresh, daemon=True).start()

    return _EXIT_CACHE["ip"], _EXIT_CACHE["loc"]


def exit_info_warm():
    """启动时预热一次缓存（后台线程调用）。"""
    global _EXIT_LOCK
    import threading as _th
    if _EXIT_LOCK is None:
        _EXIT_LOCK = True
        _th.Thread(target=_exit_refresh, daemon=True).start()


def test_all_nodes():
    """并发测速所有节点"""
    nodes = proxy_nodes()
    import concurrent.futures as cf

    def one(n):
        try:
            u = (MIHOMO + "/proxies/" + urllib.parse.quote(n["name"], safe="")
                 + "/delay?timeout=6000&url="
                 + urllib.parse.quote("https://chatgpt.com/cdn-cgi/trace", safe=""))
            return n["name"], jget(u, timeout=15).get("delay")
        except Exception:
            return n["name"], None

    result = {}
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        for name, dly in ex.map(one, nodes):
            result[name] = dly
    for n in nodes:
        n["delay"] = result.get(n["name"])
        n["alive"] = result.get(n["name"]) is not None
    return nodes


# ---------------------------------------------------------------- 订阅
def _reload(inner_path):
    """让 mihomo 重新加载配置。PATCH /configs 最稳（实测 204）"""
    req = urllib.request.Request(MIHOMO + "/configs?force=true",
                                 data=json.dumps({"path": inner_path}).encode(),
                                 method="PATCH")
    req.add_header("Content-Type", "application/json")
    with op().open(req, timeout=25) as r:
        return r.status


def _fetch_sub(url):
    """拉取订阅。宿主机可能直连不通，依次尝试：直连 → 经本地代理"""
    req = urllib.request.Request(url, headers={"User-Agent": "clash-verge/v2.0.0"})
    last = None
    # 1) 直连
    try:
        text = op().open(req, timeout=45).read().decode("utf-8", "replace")
        if "proxies:" in text:
            return text
        last = "返回内容不是 Clash 格式"
    except Exception as e:
        last = str(e)[:120]

    # 2) 经 mihomo 代理（7890）
    try:
        h = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}
        proxy_op = urllib.request.build_opener(urllib.request.ProxyHandler(h))
        text = proxy_op.open(req, timeout=60).read().decode("utf-8", "replace")
        if "proxies:" in text:
            return text
        last = "经代理返回非 Clash 格式"
    except Exception as e:
        last = f"{last} / 经代理: {str(e)[:100]}"

    raise RuntimeError(f"拉取订阅失败：{last}")


def _resolve(host):
    votes = {}
    for dns in ("223.5.5.5", "114.114.114.114"):
        try:
            out = subprocess.run(["nslookup", host, dns], capture_output=True,
                                 text=True, timeout=12).stdout
            ips = [i for i in re.findall(r"^Address(?:es)?:\s+(\d+\.\d+\.\d+\.\d+)", out, re.M)
                   if i != dns]
            if ips:
                votes[ips[-1]] = votes.get(ips[-1], 0) + 1
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

CDN_RULES = """  - 'DOMAIN-SUFFIX,blob.core.windows.net,DIRECT'
  - 'DOMAIN-SUFFIX,azureedge.net,DIRECT'
  - 'DOMAIN-SUFFIX,azurefd.net,DIRECT'
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
        # 精确匹配 server 字段：后面必须紧跟逗号或行尾，
        # 不能只用 \b（域名末尾是字母，IP 开头是数字，\b 会错位吞字符）
        proxies = re.sub(r"(server:\s*)" + re.escape(h) + r"(?=\s*[,}\n])",
                         r"\g<1>" + ip, proxies)

    # rules 段：把我们自己的直连规则放最前，并把所有规则行统一成 2 空格缩进
    # （订阅原始缩进可能是 4 空格，混着写会让 YAML 解析失败）
    raw_rules = rules.split("\n", 1)[1] if "\n" in rules else ""
    norm = []
    for ln in raw_rules.split("\n"):
        st = ln.strip()
        if st:
            norm.append("  " + st)
    body = "\n".join(norm)
    conf = (HEAD + "\n" + proxies + "\n\n" + groups
            + "\n\nrules:\n" + CDN_RULES + body + "\n")

    # 订阅里可能混入控制字符（0x00-0x08、0x0B、0x0C、0x0E-0x1F、0x7F），
    # YAML 解析会直接拒绝，必须先清掉
    conf = "".join(ch for ch in conf
                   if ch in ("\n", "\t") or (ord(ch) >= 32 and ord(ch) != 127))

    try:
        if os.path.exists(CONFIG_PATH):
            os.replace(CONFIG_PATH, CONFIG_PATH + ".bak")
    except Exception:
        pass
    with open(CONFIG_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(conf)
    try:
        with open(SUB_PATH, "w", encoding="utf-8") as f:
            f.write(url)
    except Exception:
        pass

    # 热重载：mihomo 在容器里，只认容器内路径。
    # 因此先把配置同步进容器，再用容器路径重载。
    reloaded = False
    C_INNER = "/root/.config/mihomo/config.yaml"

    # 方式一：容器内是 bind mount（宿主改动即时可见）
    try:
        _reload(C_INNER)
        reloaded = True
    except Exception:
        pass

    # 方式二：用 docker cp 推一份进去再重载
    if not reloaded:
        try:
            subprocess.run(["docker", "cp", CONFIG_PATH,
                            "chatgpt2api-proxy:" + C_INNER],
                           capture_output=True, timeout=60)
            _reload(C_INNER)
            reloaded = True
        except Exception:
            pass

    return {"nodes": len(hosts), "resolved": len(mapping),
            "reloaded": reloaded, "config": CONFIG_PATH}


def saved_sub():
    try:
        with open(SUB_PATH, encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


# ---------------------------------------------------------------- 账号
def accounts_info():
    try:
        req = urllib.request.Request(PANEL + "/api/accounts")
        req.add_header("Authorization", "Bearer " + _auth_key())
        d = json.loads(op().open(req, timeout=15).read().decode())
        items = d.get("items", [])
        return len(items), [{
            "email": a.get("email"), "type": a.get("type"),
            "status": a.get("status"), "quota": a.get("quota"),
        } for a in items]
    except Exception:
        return None, []


# ---------------------------------------------------------------- OAuth 桥
def start_oauth(email_hint=""):
    """在容器内部发起 OAuth，返回可打开的授权 URL"""
    req = urllib.request.Request(PANEL + "/api/accounts/oauth/start",
                                 data=json.dumps({"email_hint": email_hint}).encode(),
                                 method="POST")
    req.add_header("Authorization", "Bearer " + _auth_key())
    req.add_header("Content-Type", "application/json")
    try:
        return json.loads(op().open(req, timeout=60).read().decode())
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode("utf-8", "replace")[:300]}


def finish_oauth(session_id, callback):
    req = urllib.request.Request(PANEL + "/api/accounts/oauth/finish",
                                 data=json.dumps({"session_id": session_id,
                                                  "callback": callback}).encode(),
                                 method="POST")
    req.add_header("Authorization", "Bearer " + _auth_key())
    req.add_header("Content-Type", "application/json")
    try:
        return {"ok": True,
                "result": json.loads(op().open(req, timeout=120).read().decode())}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": e.read().decode("utf-8", "replace")[:400]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def select_node(node):
    """手动切换出口节点（唯一方式，不再有自动选择）。

    直接写 节点选择 组 + 让 ChatGPT 组固定指向它，
    并把这个选择落盘，容器重启后仍以用户最后一次手动选择为准。
    """
    jput(MIHOMO + "/proxies/" + urllib.parse.quote("节点选择", safe=""),
         {"name": node})
    try:
        jput(MIHOMO + "/proxies/" + urllib.parse.quote("ChatGPT", safe=""),
             {"name": "节点选择"})
    except Exception:
        pass
    # 记住用户的手动选择（重启后恢复）
    try:
        import os
        os.makedirs("/app/data", exist_ok=True)
        open("/app/data/selected-node.txt", "w", encoding="utf-8").write(node)
    except Exception:
        pass
    # 关键：切换节点后立刻作废出口/延迟缓存，否则页面还显示旧地区
    try:
        _EXIT_CACHE["ip"] = None
        _EXIT_CACHE["loc"] = None
        _EXIT_CACHE["ts"] = 0.0
        _DELAY_CACHE["v"] = None
        _DELAY_CACHE["ts"] = 0.0
        import time as _t, threading as _th
        _t.sleep(0.5)
        exit_info_warm()      # 后台重新探测
        delay_of()            # 后台重新测速
    except Exception:
        pass
    return True


DEFAULT_NODE = "🇺🇸 IEPL-美国-03"


def saved_node():
    """读取用户上次手动选择的节点；没有就返回默认美国-03。"""
    try:
        v = open("/app/data/selected-node.txt", encoding="utf-8").read().strip()
        if v:
            return v
    except Exception:
        pass
    return DEFAULT_NODE


def apply_saved_node():
    """启动时套用已保存的节点（默认美国-03），保证不会自动漂移。"""
    node = saved_node()
    try:
        jput(MIHOMO + "/proxies/" + urllib.parse.quote("节点选择", safe=""),
             {"name": node})
        jput(MIHOMO + "/proxies/" + urllib.parse.quote("ChatGPT", safe=""),
             {"name": "节点选择"})
        return {"ok": True, "node": node}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def restore_auto():
    """兼容旧接口：现在语义改为"回到默认美国-03"，不再走自动选择。"""
    return apply_saved_node()

# ---------------------------------------------------------------- 内置浏览器
CDP = "http://127.0.0.1:9222"


def browser_alive():
    """容器内置 Chromium 是否已开调试端口"""
    try:
        op().open(CDP + "/json/version", timeout=5).read()
        return True
    except Exception:
        return False


def browser_open(url):
    """让容器里的 Chromium 打开指定网址（返回标签 id）"""
    if not url:
        return {"ok": False, "error": "url 为空"}
    try:
        import cdpeval
    except Exception as e:
        return {"ok": False, "error": "cdpeval 不可用: " + str(e)[:80]}
    if not cdpeval.alive():
        return {"ok": False,
                "error": "内置浏览器未运行：调试端口 9222 未监听"}
    try:
        tid = cdpeval.open_url(url, timeout=15)
        return {"ok": True, "tab": tid}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def browser_tabs():
    """列出内置浏览器的标签页"""
    try:
        import cdpeval
        return [{"id": t.get("id"), "url": t.get("url"), "title": t.get("title")}
                for t in cdpeval.tabs()]
    except Exception:
        return []


def current_node():
    """返回当前真正生效的出口节点名与所属分组。

    链路是 ChatGPT(Selector) -> 节点选择(Selector) -> 具体节点。
    订阅里没有「优先线路」这个分组，所以不能写死名字，要顺着 now 往下跟。
    """
    try:
        pr = jget(MIHOMO + "/proxies").get("proxies", {})
    except Exception:
        return None, None
    name = "ChatGPT" if "ChatGPT" in pr else "节点选择"
    seen = set()
    while name in pr and name not in seen:
        seen.add(name)
        v = pr[name]
        if v.get("type") not in ("Selector", "URLTest", "Fallback", "LoadBalance"):
            break
        nxt = v.get("now")
        if not nxt or nxt == name:
            break
        # 已经是具体节点（不在 proxies 里或者是普通代理类型）就停
        if nxt not in pr or pr[nxt].get("type") not in (
                "Selector", "URLTest", "Fallback", "LoadBalance"):
            return nxt, name
        name = nxt
    return pr.get(name, {}).get("now"), name


# 最近一次在内置浏览器里看到的 OAuth 回调地址。
# 登录成功后浏览器可能马上跳走（platform 回调页会自行再跳），
# 或者标签被关掉；缓存一份就不怕错失。
_LAST_CB = {"url": "", "ts": 0.0}


def _scan_cb():
    """扫描内置浏览器所有标签，返回 (callback_url, 是否是错误页)。

    先看常驻监听器抓到的记录（回调页会自己跳走，轮询一定漏），
    再补扫一遍当前标签。
    """
    import re
    ok_pat = re.compile(r"^https://(platform\.openai\.com/auth/callback|"
                        r"auth\.openai\.com/[^?]*callback)", re.I)
    try:
        import cdpeval
        cdpeval.start_monitor()
        hit = cdpeval.recent_callback(900)
        if hit:
            return hit, False
    except Exception:
        pass
    for t in browser_tabs():
        u = t.get("url") or ""
        if not u.startswith("http"):
            continue
        if ok_pat.match(u) and "code=" in u:
            return u, False
        # 有些流程会停在 auth.openai.com 的错误回调（code 已被消耗之类）
        if ok_pat.match(u):
            return u, True
    return "", False


def browser_callback():
    """扫描内置浏览器标签，找 OAuth 回调地址。

    用户在内置浏览器里登录完，浏览器会停在
    https://platform.openai.com/auth/callback?code=...&state=...
    这里把它捞出来，省掉手动复制。
    """
    import time as _t
    url, _bad = _scan_cb()
    if url and "code=" in url:
        _LAST_CB["url"] = url
        _LAST_CB["ts"] = _t.time()
        return {"ok": True, "url": url}
    # 标签已经跳走/关掉时，回退到最近缓存（10 分钟内有效）
    if _LAST_CB["url"] and (_t.time() - _LAST_CB["ts"] < 600):
        return {"ok": True, "url": _LAST_CB["url"], "cached": True}
    return {"ok": False, "url": ""}


def reset_callback_cache():
    """清空已抓到的回调（内存 + 落盘）。

    开始新一轮授权时必须清，否则会把上一轮的旧 code 填进来 ——
    code 是一次性的，重复使用只会报 state 不匹配。
    """
    _LAST_CB["url"] = ""
    _LAST_CB["ts"] = 0.0
    try:
        import cdpeval
        cdpeval.clear_callback()
    except Exception:
        pass
    return True


def oauth_auto_finish(session_id="", wait=0.0, email_hint=""):
    """全自动完成账号添加：从内置浏览器读 callback → 直接换 token → 入库。
    noVNC 的剪贴板不和宿主机互通，手动「复制 callback URL 粘回来」
    这条路本身就走不通，所以这里改成服务端代劳。

    wait > 0 时会在 wait 秒内轮询等待 callback 出现（用户可能还在登录）。
    """
    import time as _t
    deadline = _t.time() + max(0.0, float(wait or 0))
    url = ""
    while True:
        found, bad = _scan_cb()
        if found and "code=" in found:
            url = found
            break
        if found and bad and not wait:
            return {"ok": False,
                    "error": "授权回调里没有 code（大概率这条链接已被用过）。"
                             "请回号池管理点「重新生成」再登录一次。"}
        if _t.time() >= deadline:
            break
        _t.sleep(1.5)

    if not url:
        # 回退最近缓存
        cached = browser_callback()
        if cached.get("ok") and cached.get("url"):
            url = cached["url"]
    if not url:
        return {"ok": False,
                "error": "没在内置浏览器里找到授权回调页。请确认已登录成功"
                         "（地址栏出现 platform.openai.com/auth/callback?code=...），"
                         "再点「自动完成添加」。"}

    _LAST_CB["url"] = url
    _LAST_CB["ts"] = _t.time()

    # session_id 留空也能跑：面板会从 callback 的 state 里解析出 session
    r = finish_oauth(session_id or "", url)
    if r.get("ok"):
        res = r.get("result") or {}
        # 兑换成功后立即清理：内存 + 落盘 + 关掉回调标签。
        # 否则下次打开 OAuth 窗口会把这条「已用过的 code」填进去，
        # 必然报「state 不匹配」，用户会以为功能坏了。
        try:
            _LAST_CB["url"] = ""
            _LAST_CB["ts"] = 0.0
            import cdpeval
            cdpeval.clear_callback()
            for t in cdpeval.tabs():
                tu = t.get("url") or ""
                if tu == url or (tu.startswith("https://platform.openai.com/auth/callback")
                                 and url.split("code=")[-1][:20] in tu):
                    cdpeval.close_tab(t.get("id"))
        except Exception:
            pass
        return {"ok": True, "url": url,
                "added": res.get("added"), "refreshed": res.get("refreshed"),
                "skipped": res.get("skipped"), "errors": res.get("errors") or [],
                "items": res.get("items") or []}
    return {"ok": False, "url": url, "error": r.get("error") or "换 token 失败"}

# ---------------------------------------------------------------- 内置浏览器（CDP）
def browser_exit_ip():
    """容器内 Chromium 的真实出口 IP"""
    try:
        import cdpeval
        return cdpeval.exit_ip()
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}

# ---------------------------------------------------------------- 自动选择定向
EXCLUDE_PATH = "/app/data/proxy-exclude.json"


def _load_exclude():
    try:
        return json.loads(open(EXCLUDE_PATH, encoding="utf-8").read())
    except Exception:
        return {"exclude": []}


# ---------------------------------------------------------------- 模型启用/禁用
MODEL_OFF_PATH = "/app/data/model-off.json"


def _read_model_off():
    try:
        return set(json.loads(open(MODEL_OFF_PATH, encoding="utf-8").read()))
    except Exception:
        return set()


def set_model_off(models):
    """号池页「管理模型」的禁用清单。

    只写服务端持久化文件（不再依赖浏览器 localStorage），
    这样网关 /v1/models 过滤后，agent 应用连接项目 API 也读不到被禁用的模型。
    """
    import os
    os.makedirs(os.path.dirname(MODEL_OFF_PATH), exist_ok=True)
    open(MODEL_OFF_PATH, "w", encoding="utf-8").write(
        json.dumps(sorted(models), ensure_ascii=False))
    return {"ok": True, "off": sorted(models)}


def get_model_off():
    return {"off": sorted(_read_model_off())}


def save_auto_exclude(node, include):
    """记录某节点是否参与自动选择的候选。

    mihomo 的 URLTest 组不支持运行时排除成员，所以这里的语义是：
    「自动选择」按钮在挑节点时跳过被排除的节点（由 current_node /
    自动切换逻辑读取这份列表）。用户取消勾选 = 定向排除。
    """
    d = _load_exclude()
    ex = set(d.get("exclude", []))
    if include:
        ex.discard(node)
    else:
        ex.add(node)
    d["exclude"] = sorted(ex)
    import os
    os.makedirs(os.path.dirname(EXCLUDE_PATH), exist_ok=True)
    open(EXCLUDE_PATH, "w", encoding="utf-8").write(
        json.dumps(d, ensure_ascii=False, indent=1))
    return {"ok": True, "exclude": d["exclude"]}


def get_auto_exclude():
    return {"exclude": _load_exclude().get("exclude", [])}


def save_auto_order(order):
    """保存「分组与节点」的拖拽排序（自动选择按这个顺序取节点）。"""
    d = {"order": [str(x) for x in (order or [])]}
    import os
    os.makedirs(os.path.dirname("/app/data/grp_order.json"), exist_ok=True)
    open("/app/data/grp_order.json", "w", encoding="utf-8").write(
        json.dumps(d["order"], ensure_ascii=False))
    return {"ok": True, "order": d["order"]}


def auto_pick_best():
    """按「分组排序」挑第一个可用且未被排除的节点；没有排序就按延迟。

    前端在「分组与节点」里拖拽会写 localStorage('c2a_grp_order')，
    网关读到这个顺序后，自动选择会严格按用户排的优先级取，
    不再是"点按自动换到任意延迟低的节点"。
    """
    ex = set(get_auto_exclude()["exclude"])
    order = []
    try:
        order = json.loads(open("/app/data/grp_order.json", encoding="utf-8").read())
    except Exception:
        pass
    nodes = [n for n in proxy_nodes()
             if n.get("name") not in ex and n.get("alive") and n.get("delay")]
    if order:
        # 按手动排序找第一个可用的
        by_name = {n["name"]: n for n in nodes}
        for name in order:
            if name in by_name:
                select_node(name)
                return {"ok": True, "node": name, "delay": by_name[name].get("delay")}
        # 排序里没有可用就退到按延迟
    best, best_d = None, None
    for n in nodes:
        d = n.get("delay")
        if d and (best_d is None or d < best_d):
            best, best_d = n["name"], d
    if best:
        select_node(best)
        return {"ok": True, "node": best, "delay": best_d}
    return {"ok": False, "error": "没有可用的未排除节点"}


# ---------------------------------------------------------------- 失败日志清理
def delete_failed_logs():
    """删除所有失败日志（detail.status == "failed" 的 call 记录）

    走面板自己的 /api/logs/delete 接口，保证删除计数和面板显示一致。
    """
    # 1) 从面板拉全量日志，筛出失败记录的 id
    req = urllib.request.Request(PANEL + "/api/logs")
    req.add_header("Authorization", "Bearer " + _auth_key())
    try:
        items = json.loads(
            op().open(req, timeout=30).read().decode()).get("items", [])
    except Exception as e:
        return {"ok": False, "error": "读取日志失败: " + str(e)[:120]}
    failed = []
    for it in items:
        det = it.get("detail") or {}
        if det.get("status") == "failed":
            failed.append(it.get("id"))
    if not failed:
        return {"ok": True, "deleted": 0, "message": "没有失败日志"}
    # 2) 调面板删除接口
    req2 = urllib.request.Request(
        PANEL + "/api/logs/delete",
        data=json.dumps({"ids": failed}).encode(),
        method="POST")
    req2.add_header("Authorization", "Bearer " + _auth_key())
    req2.add_header("Content-Type", "application/json")
    try:
        r = json.loads(op().open(req2, timeout=60).read().decode())
        return {"ok": True, "deleted": len(failed), "result": r}
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}


def clear_all_logs():
    """清空全部日志：面板日志 + 网关日志文件。

    分两步：
      1. 拉全量日志 id，调面板 /api/logs/delete 全删（保证面板计数同步）
      2. 顺带把 data 目录下网关自己写的日志文件清空（不删文件，只截断，
         避免正在写入的句柄报错）
    """
    total = 0
    err = ""
    # 1) 面板日志
    try:
        req = urllib.request.Request(PANEL + "/api/logs")
        req.add_header("Authorization", "Bearer " + _auth_key())
        items = json.loads(
            op().open(req, timeout=60).read().decode()).get("items", [])
        ids = [it.get("id") for it in items if it.get("id")]
        if ids:
            # 分批删，避免单次 body 过大或上游超时
            for i in range(0, len(ids), 200):
                chunk = ids[i:i + 200]
                req2 = urllib.request.Request(
                    PANEL + "/api/logs/delete",
                    data=json.dumps({"ids": chunk}).encode(),
                    method="POST")
                req2.add_header("Authorization", "Bearer " + _auth_key())
                req2.add_header("Content-Type", "application/json")
                try:
                    op().open(req2, timeout=60).read()
                    total += len(chunk)
                except Exception as e:
                    err = str(e)[:120]
    except Exception as e:
        err = "读取日志失败: " + str(e)[:120]

    # 2) 网关/浏览器自己写的日志文件（截断，不删除）
    files = []
    for d in ("/app/data",):
        try:
            for fn in os.listdir(d):
                if fn.endswith(".log") or fn.endswith(".jsonl"):
                    files.append(os.path.join(d, fn))
        except Exception:
            pass
    cleared = []
    for p in files:
        try:
            # 只清空内容，保留文件本身（有进程正在往里写）
            open(p, "w", encoding="utf-8").close()
            cleared.append(os.path.basename(p))
        except Exception:
            pass

    return {"ok": err == "" or total > 0, "deleted": total,
            "files_cleared": cleared,
            "error": err}
