#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""OpenAI 兼容网关 v1 —— 为 chatgpt2api 提供真正的 function calling

设计目标：
  /v1/chat/completions  支持 tools / tool_choice / stream / usage
  自动把 OpenAI tools 格式翻译成 chatgpt2api 能识别的 XML 工具协议
  多轮 tool 结果回传
  清理模型输出里的 <badge>/<escape> 等网页版残留标签
  统计真实 token 用量

运行：python gateway.py  （监听 8000）
"""
import json
import os
import re
import select
import socket
import threading
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# noVNC 静态资源目录（容器内），用于 /vnc/* 同源代理
NOVNC_ROOT = "/usr/share/novnc"
NOVNC_HOST = "127.0.0.1"
NOVNC_PORT = 6080

from jsx_clean import strip_jsx
try:
    import webui
    import webapi
    import oauth_page
    import auth_proxy
    from onboarding import onboarding_script
    ONBOARDING_JS = onboarding_script()
    _PAGES = webui.render_pages()
except Exception:
    webui = None
    webapi = None
    ONBOARDING_JS = ""
    _PAGES = {}

NAVBAR = r"""
<script>
(function(){
  if (window.__c2aNav) return;
  window.__c2aNav = 1;

  var HOST = (location.hostname && location.hostname !== '') ? location.hostname : '127.0.0.1';
  var VNC_URL = '/vnc/vnc.html?autoconnect=1&resize=scale&reconnect=1&path=websockify';

  function styleOnce(){
    if (document.getElementById('c2a-css')) return;
    var st = document.createElement('style');
    st.id = 'c2a-css';
    st.textContent = ''
      + '.c2a-mask{position:fixed;left:0;right:0;bottom:0;top:56px;z-index:2147482000;pointer-events:auto !important;'
      + 'display:flex;align-items:center;justify-content:center;background:rgba(10,10,10,.45)}'
      + '.c2a-mask *{pointer-events:auto}'      + '.c2a-win{background:#0b0d12;border-radius:14px;overflow:hidden;display:flex;'
      + 'flex-direction:column;box-shadow:0 24px 70px rgba(0,0,0,.5)}'
      + '.c2a-head{display:flex;align-items:center;gap:12px;padding:10px 14px;'
      + 'background:#14161d;color:#e6e6e6;font-size:13px;flex-shrink:0}'
      + '.c2a-head b{font-weight:600}'
      + '.c2a-ip{color:#8ee6a4;font-family:ui-monospace,monospace;font-size:12.5px}'
      + '.c2a-body{flex:1;background:#000;position:relative;min-height:0}'
      + '.c2a-body iframe{width:100%;height:100%;border:0;display:block}'
      + '.c2a-btn{background:#2a2d3a;color:#e6e6e6;border:0;border-radius:7px;'
      + 'padding:6px 12px;font-size:12.5px;cursor:pointer}'
      + '.c2a-btn:hover{background:#3a3f52}'
      + '.c2a-link{color:#93c5fd;text-decoration:none;font-size:12px}'
      + '.c2a-sp{flex:1}';
    (document.head || document.documentElement).appendChild(st);
  }

  // ---------- 通用窗口 ----------
  function makeWin(opts){
    styleOnce();
    var mask = document.createElement('div');
    mask.className = 'c2a-mask';
    mask.id = opts.id;
    var head = '<div class="c2a-head"><b>' + opts.title + '</b>'
      + (opts.extra || '')
      + '<span class="c2a-sp"></span>'
      + (opts.link ? '<a class="c2a-link" href="' + opts.link + '" target="_blank">单独打开</a>' : '')
      + '<button class="c2a-btn" data-close="1">关闭</button></div>';
    mask.innerHTML = '<div class="c2a-win" style="width:' + opts.w + ';height:' + opts.h + '">'
      + head + '<div class="c2a-body"></div></div>';
    mask.addEventListener('click', function(e){
      if (e.target === mask) close();
    });
    mask.querySelector('[data-close]').addEventListener('click', close);
    document.body.appendChild(mask);

    var frame = document.createElement('iframe');
    frame.setAttribute('allow', 'clipboard-read; clipboard-write');
    mask.querySelector('.c2a-body').appendChild(frame);

    function close(){
      try{ frame.src = 'about:blank'; }catch(e){}
      try{ mask.remove(); }catch(e){}
    }
    return {mask: mask, frame: frame, close: close,
            titleEl: mask.querySelector('.c2a-head b'),
            linkEl: mask.querySelector('.c2a-link'),
            box: mask.querySelector('.c2a-win')};
  }

  // ---------- 内置浏览器弹窗 ----------
  var browserWin = null;
  var autoTimer = null;      // 自动完成轮询
  var autoDone = false;      // 本次授权是否已自动完成

  /* 授权成功后自动收尾：轮询服务端从内置 Chromium 里读到的 callback，
     读到就直接换 token 入库。
     起因：noVNC 的剪贴板不和宿主机互通，手动「复制 URL 粘回来」根本走不通。 */
  function startAutoFinish(){
    if (autoTimer || autoDone) return;
    autoDone = false;
    var el = document.getElementById('c2a-browser-ip');
    var mark = function(txt, color){
      var e2 = document.getElementById('c2a-browser-ip');
      if (!e2) return;
      e2.textContent = txt;
      e2.style.color = color || '#8ee6a4';
    };
    var tick = 0;
    autoTimer = setInterval(function(){
      tick++;
      if (autoDone){ clearInterval(autoTimer); autoTimer = null; return; }
      if (tick > 200){          // 约 10 分钟后放弃
        clearInterval(autoTimer); autoTimer = null;
        mark('未检测到授权回调，可点「手动完成」', '#fca5a5');
        return;
      }
      fetch('/p/api/oauth/auto', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({wait: 0})})
        .then(function(r){ return r.json(); })
        .then(function(d){
          if (d && d.ok){
            autoDone = true;
            clearInterval(autoTimer); autoTimer = null;
            mark('✅ 账号已自动添加（新增 ' + (d.added != null ? d.added : '?')
                 + ' 个）', '#8ee6a4');
            try{ if (window.parent && window.parent !== window) window.parent.location.reload(); }catch(e){}
          }
        }).catch(function(){});
    }, 3000);
    mark('已打开授权页，登录完成后会自动添加…', '#93c5fd');
  }

  function openBrowser(url){
    // 已经开着就直接复用，避免叠层
    if (browserWin && document.body.contains(browserWin.mask)){
      if (url){
        fetch('/p/api/oauth/open', {method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({url: url})}).catch(function(){});
      }
      return browserWin;
    }
    {
      browserWin = makeWin({
        id: 'c2a-browser-modal',
        title: '内置浏览器（容器内运行，走容器代理）',
        extra: '<span class="c2a-ip" id="c2a-browser-ip">出口检查中…</span>'
             + '<button class="c2a-btn" id="c2a-manual-finish" style="display:none">手动完成</button>',
        link: VNC_URL,
        w: 'min(1420px,96vw)',
        h: 'min(900px,94vh)'
      });
      var mf = document.getElementById('c2a-manual-finish');
      if (mf){
        mf.onclick = function(){
          mf.disabled = true; mf.textContent = '提交中…';
          fetch('/p/api/oauth/auto', {method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({wait: 6})})
            .then(function(r){ return r.json(); })
            .then(function(d){
              if (d && d.ok){
                autoDone = true;
                if (autoTimer){ clearInterval(autoTimer); autoTimer = null; }
                alert('账号已添加成功（新增 ' + (d.added != null ? d.added : '?') + ' 个）');
                location.reload();
              }else{
                mf.disabled = false; mf.textContent = '手动完成';
                alert((d && d.error) || '没找到授权回调');
              }
            }).catch(function(){ mf.disabled = false; mf.textContent = '手动完成'; });
        };
      }
      browserWin.frame.src = VNC_URL;
      // 出口信息用服务端探测（走 mihomo、强制 IPv4），
      // 不用浏览器自测 —— Chromium 会优先 IPv6 直连，地区会误判成别的国家
      fetch('/p/api/proxy').then(function(r){ return r.json(); }).then(function(d){
        var el = document.getElementById('c2a-browser-ip');
        if (!el) return;
        el.textContent = (d && d.exit_ip)
          ? ('出口 ' + d.exit_ip + (d.exit_loc ? ' · ' + d.exit_loc : ''))
          : '出口探测中…';
        el.style.color = (d && d.exit_ip) ? '#8ee6a4' : '#fcd34d';
      }).catch(function(){});
    }
    if (url){
      fetch('/p/api/oauth/open', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url: url})
      }).catch(function(){});
      startAutoFinish();       // 打开授权页后自动等回调 → 自动入库
    }
    return browserWin;
  }
  window.__c2aOpenBrowser = openBrowser;

  // 前端包补丁里调用的入口：授权页 -> 内置浏览器弹窗
  window.__c2aOpenAuth = function(url){
    autoDone = false;
    openBrowser(url);
    startAutoFinish();
    return {closed:false, focus:function(){}, blur:function(){},
            close:function(){ if(browserWin) browserWin.close(); },
            postMessage:function(){}, location:{href:url}};
  };

  // ---------- 兜底：万一前端包没打上补丁，也拦住 window.open ----------
  var AUTH_RE = /auth\.openai\.com|platform\.openai\.com\/auth|chatgpt\.com\/auth/i;
  var _open = window.open;
  window.open = function(u, name, feat){
    try{
      if (typeof u === 'string' && AUTH_RE.test(u)){
        return window.__c2aOpenAuth(u);
      }
      if (typeof u === 'string' && (u.indexOf(':6080') > -1 || u.indexOf('/vnc/') > -1)){
        openBrowser('');
        return {closed:false, focus:function(){}, blur:function(){},
                close:function(){}, postMessage:function(){}, location:{href:u}};
      }
    }catch(e){}
    return _open.apply(window, arguments);
  };

  // ---------- 号池页 OAuth 弹窗：自动回填 callback ----------
  // 面板自带的 OAuth 弹窗要用户把内置浏览器地址栏的 URL 粘回来，
  // 但 noVNC 的剪贴板不和宿主机互通，这条路走不通。
  // 这里在号池页轮询服务端抓到的 callback，自动填进那个 textarea，
  // 并把「完成导入」按钮高亮，用户点一下就好（也可全自动）。
  var oauthFillTimer = null;
  var lastFilled = '';
  function fillOauthBox(){
    // 只在弹窗里存在 OAuth 的 callback 输入框时才干活
    var ta = document.querySelector('textarea[placeholder*="callback URL"]')
          || document.querySelector('textarea[placeholder*="platform.openai.com/auth/callback"]');
    if (!ta) { lastFilled = ''; return false; }
    fetch('/p/api/oauth/auto-status').then(function(r){ return r.json(); })
      .then(function(d){
        if (!d || !d.ok || !d.url) return;
        if (d.url === lastFilled) return;
        lastFilled = d.url;
        // 用原生 setter 写值，React 的受控组件才会收到变更
        var desc = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');
        desc.set.call(ta, d.url);
        ta.dispatchEvent(new Event('input', {bubbles: true}));
        ta.dispatchEvent(new Event('change', {bubbles: true}));
        ta.style.borderColor = '#22c55e';
        ta.style.boxShadow = '0 0 0 3px rgba(34,197,94,.15)';
        var tip = document.getElementById('c2a-oauth-tip');
        if (!tip){
          tip = document.createElement('div');
          tip.id = 'c2a-oauth-tip';
          tip.style.cssText = 'margin-top:6px;font-size:12px;color:#16a34a';
          ta.parentNode.appendChild(tip);
        }
        tip.textContent = '✅ 已自动从内置浏览器读取到回调地址，点「完成导入」即可';
      }).catch(function(){});
    return true;
  }
  function watchOauth(){
    if (oauthFillTimer) return;
    oauthFillTimer = setInterval(function(){
      if (!fillOauthBox()){
        // 弹窗关了就不用继续轮询
        if (!document.querySelector('textarea[placeholder*="callback"]')){
          clearInterval(oauthFillTimer); oauthFillTimer = null;
        }
      }
    }, 2500);
  }
  // 弹窗是动态挂载的，用 MutationObserver 发现它
  try{
    var mo = new MutationObserver(function(){ if (fillOauthBox()) watchOauth(); });
    mo.observe(document.documentElement, {childList: true, subtree: true});
  }catch(e){}

  // ---------- 设置页：修改登录密码 ----------
  // 面板把密码放在环境变量里，UI 改不了。这里加一个表单，
  // 调 /p/api/auth/password 写入 auth-override.json，网关鉴权会优先认它，立即生效。
  var pwdInjected = false;
  function injectPwdPanel(){
    if (pwdInjected) return;
    if (location.pathname.indexOf('/settings') !== 0) return;
    // 必须挂到 body 末尾，不能挂进 <main>：
    // <main> 归 React 管，插入子节点会触发 hydration 报错（#418）并被清除。
    var host = document.body;
    if (!host) return;
    if (document.getElementById('c2a-pwd-card')) { pwdInjected = true; return; }

    var card = document.createElement('div');
    card.id = 'c2a-pwd-card';
    card.style.cssText = 'position:fixed;right:24px;bottom:24px;z-index:2147482000;'
      + 'width:380px;max-width:calc(100vw - 32px);border-radius:16px;'
      + 'border:1px solid #e7e5e4;background:#fff;padding:20px;font-family:inherit;'
      + 'box-shadow:0 20px 60px -12px rgba(0,0,0,.25)';
    // 可折叠：默认展开，点标题收起
    card.setAttribute('data-open', '1');
    card.innerHTML = ''
      + '<div style="font-size:15px;font-weight:650;color:#1c1917;margin-bottom:4px">修改登录密码</div>'
      + '<div style="font-size:12.5px;color:#78716c;line-height:1.7;margin-bottom:14px">'
      + '改完立即生效，不需要重启容器。新密码至少 8 位，需同时包含字母和数字。'
      + '<br>注意：这是登录控制台的密码，不是给 AI 客户端用的 <code style="background:#f5f5f4;'
      + 'padding:1px 5px;border-radius:4px">sk-</code> 开头的 API Key。</div>'
      + '<div style="display:flex;flex-direction:column;gap:10px;max-width:420px">'
      + '<input id="c2a-pwd-cur" type="password" placeholder="当前密码" autocomplete="current-password" '
      + 'style="height:40px;border:1px solid #d6d3d1;border-radius:10px;padding:0 12px;font-size:13px">'
      + '<input id="c2a-pwd-new" type="password" placeholder="新密码（≥8 位，含字母和数字）" '
      + 'autocomplete="new-password" style="height:40px;border:1px solid #d6d3d1;border-radius:10px;'
      + 'padding:0 12px;font-size:13px">'
      + '<input id="c2a-pwd-new2" type="password" placeholder="再次输入新密码" '
      + 'autocomplete="new-password" style="height:40px;border:1px solid #d6d3d1;border-radius:10px;'
      + 'padding:0 12px;font-size:13px">'
      + '<div id="c2a-pwd-msg" style="font-size:12.5px;min-height:18px"></div>'
      + '<div style="display:flex;gap:10px">'
      + '<button id="c2a-pwd-save" style="height:40px;padding:0 18px;border:0;border-radius:10px;'
      + 'background:#1c1917;color:#fff;font-size:13px;cursor:pointer">保存新密码</button>'
      + '<button id="c2a-pwd-reset" style="height:40px;padding:0 16px;border:1px solid #e7e5e4;'
      + 'border-radius:10px;background:#fff;color:#78716c;font-size:13px;cursor:pointer">'
      + '恢复环境变量密码</button>'
      + '</div></div>';

    host.appendChild(card);

    var msg = card.querySelector('#c2a-pwd-msg');
    function say(t, ok){
      msg.textContent = t;
      msg.style.color = ok ? '#16a34a' : '#dc2626';
    }

    card.querySelector('#c2a-pwd-save').onclick = function(){
      var cur = card.querySelector('#c2a-pwd-cur').value;
      var n1 = card.querySelector('#c2a-pwd-new').value;
      var n2 = card.querySelector('#c2a-pwd-new2').value;
      if (!cur || !n1) { say('请填写完整'); return; }
      if (n1 !== n2) { say('两次输入的新密码不一致'); return; }
      say('提交中…', true);
      fetch('/p/api/auth/password', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({current: cur, new: n1})})
        .then(function(r){ return r.json(); })
        .then(function(d){
          if (d && d.ok) {
            say('✅ 密码已更新，请用新密码重新登录（3 秒后跳转）', true);
            // 清掉记住的旧密码，避免自动登录用旧密码反复失败
            try {
              localStorage.removeItem('c2a_remember_key');
              localStorage.removeItem('c2a_remember_at');
              localStorage.removeItem('c2a_auto_login');
            } catch(e){}
            // 给足时间让用户看到结果，再跳转
            setTimeout(function(){ location.href = '/login'; }, 3000);
          } else {
            say((d && d.error) || '修改失败');
          }
        })
        .catch(function(e){ say('请求失败: ' + e.message); });
    };

    card.querySelector('#c2a-pwd-reset').onclick = function(){
      if (!confirm('恢复为 .env / 环境变量里的密码？当前设置的新密码将失效。')) return;
      fetch('/p/api/auth/password/reset', {method:'POST',
        headers:{'Content-Type':'application/json'}, body:'{}'})
        .then(function(r){ return r.json(); })
        .then(function(d){
          if (d && d.ok) say('✅ 已恢复环境变量密码，请重新登录', true);
          else say((d && d.error) || '恢复失败');
        })
        .catch(function(e){ say('请求失败: ' + e.message); });
    };

    pwdInjected = true;
  }
  try{
    var mo2 = new MutationObserver(function(){ injectPwdPanel(); });
    mo2.observe(document.documentElement, {childList: true, subtree: true});
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', injectPwdPanel);
    } else { injectPwdPanel(); }
  }catch(e){}

  // ---------- 复用面板登录态 ----------
  function mirrorKey(){
    if (localStorage.getItem('c2a_key')) return;
    try{
      var probe = indexedDB.databases ? indexedDB.databases() : null;
      if (!probe) return;
      probe.then(function(list){
        var exists = (list || []).some(function(d){ return d && d.name === 'chatgpt2api'; });
        if (!exists) return;
        var r = indexedDB.open('chatgpt2api');
        r.onupgradeneeded = function(){ try{ r.transaction.abort(); }catch(e){} };
        r.onerror = function(){ try{ r.result && r.result.close(); }catch(e){} };
        r.onsuccess = function(){
          var db = r.result;
          try{
            if (!db.objectStoreNames.contains('auth')) { db.close(); return; }
            var g = db.transaction('auth').objectStore('auth').get('chatgpt2api_auth_key');
            g.onsuccess = function(){
              var v = g.result;
              if (v) localStorage.setItem('c2a_key', String(v));
              try{ db.close(); }catch(e){}
            };
          }catch(e){ try{ db.close(); }catch(e2){} }
        };
      }).catch(function(){});
    }catch(e){}
  }

  // 面板登录后会写 IndexedDB；这里持续跟随，保证 /p/* 页面读 localStorage 也能拿到。
  // （首屏之外再补几次，覆盖「登录跳转完成后」的时机）
  function scheduleMirror(){
    mirrorKey();
    [600, 1800, 3500, 6000].forEach(function(ms){ setTimeout(mirrorKey, ms); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', scheduleMirror);
  else scheduleMirror();
  // 页面重新可见时（切回标签页）再补一次
  document.addEventListener('visibilitychange', function(){
    if (!document.hidden) mirrorKey();
  });

  // ===== 关键：清理 Service Worker 并强刷 =====
  // 你那边一直显示旧菜单，最可能的原因是浏览器注册了 Service Worker，
  // 它把旧 chunk 从本地缓存吐给你 —— 普通「强制刷新」根本绕不过它。
  // 这里主动注销 + 清缓存 + 刷新，拿到干净页面。
  try{
    if ('serviceWorker' in navigator){
      navigator.serviceWorker.getRegistrations().then(function(regs){
        regs.forEach(function(r){ r.unregister().catch(function(){}); });
      }).catch(function(){});
      setTimeout(function(){
        try{
          // 清掉 caches 里的旧 chunk
          if ('caches' in window){
            caches.keys().then(function(names){
              names.forEach(function(n){ caches.delete(n).catch(function(){}); });
            });
          }
          // 只要还有 SW controller 就刷新；同时给 SW 注销留一点时间
          setTimeout(function(){
            if (navigator.serviceWorker.controller || window.__c2aNeedsReload){
              location.reload();
            }
          }, 900);
        }catch(e){}
      }, 400);
    }
  }catch(e){}
})();
</script>
"""


BUILD_STAMP = str(int(time.time()))


def stamp_static(html):
    """给 /_next/static/... 的引用追加 ?v=<构建时间>

    面板的 chunk 文件名是固定的（不带 content hash），浏览器的
    「启发式缓存」会直接复用旧文件。加一个版本参数后，每次部署
    URL 都变，浏览器必然重新拉取，改动立刻生效。
    """
    if not html:
        return html
    out = []
    i = 0
    key = "/_next/static/"
    while True:
        j = html.find(key, i)
        if j < 0:
            out.append(html[i:])
            break
        out.append(html[i:j])
        # 找到这段 URL 的结尾（引号/空白/>）
        k = j
        while k < len(html) and html[k] not in (chr(34), chr(39), " ", ">", ")"):
            k += 1
        url = html[j:k]
        sep = "&" if "?" in url else "?"
        out.append(url + sep + "v=" + BUILD_STAMP)
        i = k
    return "".join(out)


def inject_navbar(html):
    """在 </body> 前插入导航条脚本（幂等）

    放在文档末尾，React 的 root 渲染不会连带清掉它；同时脚本自身
    带 MutationObserver 守护，被移除会立刻补回。
    同时追加「首次使用引导」脚本（只在没看过时弹一次）。
    """
    if not html or "__c2aNav" in html:
        return html
    pay = NAVBAR + ONBOARDING_JS
    low = html.lower()
    i = low.rfind("</body>")
    if i < 0:
        return html + pay
    return html[:i] + pay + html[i:]


def _load_config():
    import configparser, os
    cfg = configparser.ConfigParser()
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")
    cfg.read(path, encoding="utf-8")
    return {
        "upstream": cfg.get("upstream", "base_url", fallback="http://localhost:3000"),
        "key": cfg.get("upstream", "auth_key", fallback=""),
        "timeout": cfg.getint("upstream", "timeout", fallback=300),
        "retries": cfg.getint("upstream", "retries", fallback=4),
        "host": cfg.get("listen", "host", fallback="127.0.0.1"),
        "port": cfg.getint("listen", "port", fallback=8000),
        "default_model": cfg.get("behavior", "default_model", fallback="auto"),
    }


CFG = _load_config()
UPSTREAM = CFG["upstream"].rstrip("/")
# 面板密钥优先取环境变量（.env 里的 CHATGPT2API_AUTH_KEY），
# 没有再回退 config.ini —— 否则用户改了 .env 却发现登录/鉴权还是旧密码。
UPSTREAM_KEY = (os.environ.get("CHATGPT2API_AUTH_KEY") or CFG["key"] or "").strip()
# 原生面板地址（和上游同一个服务）
PANEL = UPSTREAM
LISTEN = (CFG["host"], CFG["port"])
TIMEOUT = CFG["timeout"]
RETRIES = CFG["retries"]
DEFAULT_MODEL = CFG["default_model"]


# ---------------------------------------------------------------- 图片地址改写
# 面板生成图片时，URL 是由 resolve_image_base_url() 用 request.headers['host']
# 拼出来的。请求经网关转发到 127.0.0.1:3001 时，host 就是 127.0.0.1:3001，
# 于是面板返回的是**容器内部地址**，宿主机没映射 3001，浏览器打不开。
#
# 之前的实现只在 /v1/images/generations 里做前缀匹配改写，覆盖不到：
#   · /v1/images/edits（图生图）
#   · /api/images（图片管理页）
#   · /api/logs（日志详情里的图片）
# 而且前缀匹配漏掉了历史数据里的 https://127.0.0.1:3001。
#
# 现在统一收口成下面这组函数，所有涉及图片的响应都走它。
_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "0.0.0.0", "::1", "[::1]")


def _public_base(headers):
    """从请求头推出对外可访问的 base（如 https://nas.example.com）。"""
    host = (headers.get("Host") or "").strip()
    if not host:
        return ""
    scheme = "https" if (headers.get("X-Forwarded-Proto") or "").lower() == "https" else "http"
    return scheme + "://" + host


def _rewrite_one_url(u, base):
    """把一条图片地址从容器内部换成对外地址。

    用 URL 结构解析而不是字符串前缀匹配，这样：
      · http:// 和 https:// 都能覆盖（历史日志里有 https 的旧记录）
      · 端口是 3001 / 3000 / 随便什么都能覆盖
      · 已是对外地址的（如 CDN 直链）原样保留
    """
    if not isinstance(u, str) or not base:
        return u, False
    s = u.strip()
    if not s:
        return u, False
    try:
        pr = urllib.parse.urlsplit(s)
    except Exception:
        return u, False
    host = (pr.hostname or "").lower()
    if host not in _LOOPBACK_HOSTS:
        return u, False
    # 只改图片相关路径，避免误伤 /login 之类的内部链接。
    # 注意缩略图走的是 /image-thumbnails/...，不是 /images，
    # 漏掉它会导致图片管理页缩略图仍然打不开。
    path = pr.path or "/"
    if not (path.startswith("/images")
            or path.startswith("/image-thumbnails")):
        return u, False
    out = base + path
    if pr.query:
        out += "?" + pr.query
    return out, True


def rewrite_image_urls(node, base, depth=0):
    """递归改写响应里所有图片地址（原地修改），返回改了几处。

    不按接口硬编码结构，而是递归遍历：不管外面套了几层
    （data[] / items[] / groups[].items[] / detail.urls[]），都能覆盖到。
    """
    if not base or depth > 10:
        return 0
    changed = 0
    if isinstance(node, dict):
        for k, v in list(node.items()):
            if k in ("url", "thumbnail_url", "image_url", "src") and isinstance(v, str):
                nv, hit = _rewrite_one_url(v, base)
                if hit:
                    node[k] = nv
                    changed += 1
            elif k in ("urls", "images", "image_urls") and isinstance(v, list):
                for i, x in enumerate(v):
                    if isinstance(x, str):
                        nv, hit = _rewrite_one_url(x, base)
                        if hit:
                            v[i] = nv
                            changed += 1
                    elif isinstance(x, (dict, list)):
                        changed += rewrite_image_urls(x, base, depth + 1)
            elif isinstance(v, (dict, list)):
                changed += rewrite_image_urls(v, base, depth + 1)
    elif isinstance(node, list):
        for i, it in enumerate(node):
            if isinstance(it, str):
                nv, hit = _rewrite_one_url(it, base)
                if hit:
                    node[i] = nv
                    changed += 1
            elif isinstance(it, (dict, list)):
                changed += rewrite_image_urls(it, base, depth + 1)
    return changed


def rewrite_image_urls_in_bytes(raw, headers):
    """给一段 JSON 响应做改写。命中返回 (新字节, True)，否则原样返回。"""
    try:
        obj = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return raw, False
    base = _public_base(headers)
    if not base or not isinstance(obj, (dict, list)):
        return raw, False
    n = rewrite_image_urls(obj, base)
    if not n:
        return raw, False
    return json.dumps(obj, ensure_ascii=False).encode(), True


# ---------------------------------------------------------------- 工具协议
# chatgpt2api 的 /v1/messages 用 XML 协议描述工具，这里改写成更明确的形式
TOOL_RULES = """You are a tool-calling engine attached to an API. You do not chat idly.

# Available tools
{tools}

# Examples of correct behaviour

Example 1
User: 北京天气怎么样
You: <tool_calls><tool_call><tool_name>TOOL_NAME_FROM_LIST</tool_name><parameters><ARG><![CDATA[VALUE]]></ARG></parameters></tool_call></tool_calls>

Example 2
User: 你好
You: 你好，有什么可以帮你？

# Rules
1. When the user's request can be served by one of the tools above, output ONLY the XML block.
   Start with <tool_calls>, end with </tool_calls>. No text before, none after.
2. Copy the tool name and argument names EXACTLY from the list above.
3. Argument values go inside CDATA. Object/list values: put JSON inside the CDATA.
4. Tool with no arguments: still emit <parameters></parameters>.
5. Several tools: repeat <tool_call> inside the same <tool_calls> wrapper.
6. Never apologise. Never say you lack access. Never explain that you are calling a tool.
7. After you receive <tool_result>, reply to the user in natural language using that data.
8. Do NOT output UI markup: no <badge>, <escape>, <box>, <row>, <col>, <text>, <card>, <divider>.
9. Plain text only in normal replies. No markdown tables unless the user asks for a table."""

CJK_RE = re.compile(r"[\u4e00-\u9fff]")

# ChatGPT 网页版会在回复里塞 React 组件，纯文本客户端会把它们原样显示成“乱码”。
# 自闭合组件（图片/引用）整段删除；成对组件（grid/caption）只删标签保留内容。
SELF_CLOSING = (
    "AsyncImage", "AsyncImageGroup", "Entity", "Cite", "Image", "ImageGroup",
    "Video", "Audio", "MapEmbed", "SearchResult", "Reference", "File",
    "Chart", "Table", "Embed", "Link", "Source",
)
PAIRED = (
    "grid", "caption", "badge", "escape", "row", "col", "box", "text",
    "divider", "card", "span", "code_block", "quote",
)
SELF_TAG_RE = re.compile(
    r"<(" + "|".join(SELF_CLOSING) + r")\b(?:[^>]*/>|[^>]*>.*?</\1>|[^>]*>)",
    re.I | re.S,
)
PAIR_TAG_RE = re.compile(r"</?(?:" + "|".join(PAIRED) + r")\b[^>]*>", re.I)
GENERIC_SELF_RE = re.compile(r"<[A-Z][A-Za-z0-9_.]*\b[^>]*/>")


def strip_ui_markup(text):
    """清掉 ChatGPT 网页版残留的 React/GenUI 组件。

    先用状态机处理 JSX（能正确跳过 onClick={()=>...} 里的 > ），
    再用正则兜底清理零散标签。
    重要：若清洗后为空但原文有内容，说明模型整段输出了组件/纯标签，
    此时返回空串会让用户看到"什么都没回"，因此保留原文更稳妥。
    """
    if not text:
        return ""
    original = text
    text = strip_jsx(text)
    prev = None
    while prev != text:
        prev = text
        text = SELF_TAG_RE.sub("", text)
        text = GENERIC_SELF_RE.sub("", text)
        text = PAIR_TAG_RE.sub("", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    if not text and original.strip():
        # 整段都是组件/标签，清洗后为空 —— 返回空会让客户端显示"无回复"
        return ""
    return text


def to_tool_prompt(tools):
    """OpenAI tools -> 可读的工具清单文本"""
    if not tools:
        return ""
    lines = []
    for t in tools:
        fn = (t or {}).get("function") or {}
        name = fn.get("name")
        if not name:
            continue
        desc = (fn.get("description") or "").strip().replace("\n", " ")
        params = fn.get("parameters") or {}
        props = params.get("properties") or {}
        required = set(params.get("required") or [])
        ps = []
        for pname, pmeta in props.items():
            ptype = (pmeta or {}).get("type", "string")
            pdesc = ((pmeta or {}).get("description") or "").strip().replace("\n", " ")
            mark = " (required)" if pname in required else ""
            ps.append(f"    - {pname}: {ptype}{mark} — {pdesc}")
        lines.append(f"- {name}: {desc}")
        if ps:
            lines.append("  parameters:")
            lines.extend(ps)
    return TOOL_RULES.format(tools="\n".join(lines))


OUTPUT_RULE = """# Output format (this is an API, not a web page)

You are answering through a plain-text API. The client renders plain Markdown only.

STRICT rules:
1. Output Markdown only. No JSX, no React components, no HTML.
2. NEVER output: <box>, <radio>, <radio-group>, <button>, <badge>, <escape>,
   <grid>, <caption>, <row>, <col>, <divider>, <card>, <AsyncImage>,
   <AsyncImageGroup>, <Entity>, <Cite>, or any PascalCase tag.
3. NEVER output: {@body ...}, useState, useEffect, onClick, GenUI, DIL.,
   or any JavaScript expression block. Do not offer clickable options.
4. Tables must be a single GitHub Markdown table:
   | 项目 | 内容 |
   |---|---|
   | 省会 | 浙江 |
   Do NOT emit a table as loose indented lines.
5. Lists use "- " or "1. ". No bare indented blocks.
6. If you would normally show a widget or form, write the options as a plain
   numbered list instead, and say the user can reply with a number."""


# 工具模式专用：必须显式允许 <tool_calls>，否则与工具协议冲突，
# 模型会陷入矛盾指令而拒绝调用工具（实测会导致工具调用完全失效）。
OUTPUT_RULE_TOOLS = """# Output format (this is an API, not a web page)

You are answering through a plain-text API. The client renders plain Markdown only.

STRICT rules:
1. If the user asks for real data (CPU, disk, files, order state, weather, anything
   that requires a tool), you MUST call the tool. Output ONLY the <tool_calls> XML.
   Do NOT reply with text like "无法获取" or "请自行查看" — call the tool instead.
   This is the ONE exception to the no-tag rule; it is required for tools to work.
2. Apart from <tool_calls>/<tool_call>/<tool_name>/<parameters>, output Markdown only.
   NEVER output: <box>, <radio>, <radio-group>, <button>, <badge>, <escape>,
   <grid>, <caption>, <row>, <col>, <divider>, <card>, <AsyncImage>,
   <AsyncImageGroup>, <Entity>, <Cite>, or any other PascalCase tag.
3. NEVER output: {@body ...}, useState, useEffect, onClick, GenUI, DIL.,
   or any JavaScript expression block. Do not offer clickable options.
4. Tables must be a single GitHub Markdown table:
   | 项目 | 内容 |
   |---|---|
   | 省会 | 浙江 |
   Do NOT emit a table as loose indented lines.
5. Lists use "- " or "1. ". No bare indented blocks.
6. When the tool result is available, answer with plain Markdown.
   Do not claim you cannot access data — you already have the tool result."""


def openai_msgs_to_anthropic(messages, tools):
    """把 OpenAI messages 转成 Anthropic 结构，tool 结果转成 tool_result 文本"""
    system_parts = []
    if tools:
        system_parts.append(to_tool_prompt(tools))
        system_parts.append(OUTPUT_RULE_TOOLS)
    else:
        system_parts.append(OUTPUT_RULE)
    out = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if role == "system":
            if isinstance(content, str) and content.strip():
                system_parts.append(content.strip())
            continue
        if role == "tool":
            # OpenAI 的 tool 消息 -> 以 user 身份回传结果
            payload = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            out.append({"role": "user",
                        "content": f"<tool_result>{payload}</tool_result>\n请基于以上工具结果回答用户。"})
            continue
        if role == "assistant" and m.get("tool_calls"):
            calls = []
            for tc in m.get("tool_calls") or []:
                fn = (tc or {}).get("function") or {}
                calls.append(
                    f"<tool_call><tool_name>{fn.get('name','')}</tool_name>"
                    f"<parameters>{fn.get('arguments','{}')}</parameters></tool_call>"
                )
            text = "".join(calls)
            if isinstance(content, str) and content.strip():
                text = content.strip() + "\n" + text
            out.append({"role": "assistant", "content": text})
            continue
        if isinstance(content, list):
            # 多模态：只保留文本部分
            buf = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    buf.append(part.get("text") or "")
            content = "\n".join(buf)
        out.append({"role": role or "user", "content": content or ""})
    return "\n\n".join(system_parts), out


def parse_xml_calls(text):
    """从模型输出里提取 <tool_call> 块（兼容单层/双层、CDATA、JSON、子标签）"""
    if not text:
        return []
    body = re.sub(r"(?is)```.*?```", "", text)
    calls = []
    for blk in re.findall(r"(?is)<tool_call\b[^>]*>(.*?)</tool_call>", body):
        name = _tag(blk, "tool_name") or _tag(blk, "name") or _tag(blk, "function")
        raw = (_tag(blk, "parameters") or _tag(blk, "input")
               or _tag(blk, "arguments") or "{}")
        if name:
            calls.append({"name": name.strip(), "arguments": _to_json(raw)})
    return calls


def _tag(text, tag):
    """取标签内容，自动解开 CDATA"""
    m = re.search(r"(?is)<" + tag + r"\b[^>]*>(.*?)</" + tag + ">", text)
    if not m:
        return ""
    v = m.group(1).strip()
    cd = re.fullmatch(r"(?is)<!\[CDATA\[(.*?)]]>", v)
    return (cd.group(1) if cd else v).strip()


def _to_json(raw):
    """把参数文本转成 JSON 字符串"""
    raw = (raw or "").strip()
    try:
        obj = json.loads(raw)
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        pass
    pairs = re.findall(r"(?is)<([\w.\-]+)\b[^>]*>(.*?)</\1>", raw)
    if pairs:
        obj = {}
        for k, v in pairs:
            v = v.strip()
            cd = re.fullmatch(r"(?is)<!\[CDATA\[(.*?)]]>", v)
            if cd:
                v = cd.group(1).strip()
            try:
                obj[k] = json.loads(v)
            except Exception:
                obj[k] = v
        return json.dumps(obj, ensure_ascii=False)
    return "{}"


def count_tokens(text):
    """粗略估算：中文按字，英文按 4 字符 1 token"""
    if not text:
        return 0
    s = str(text)
    cjk = len(CJK_RE.findall(s))
    other = len(s) - cjk
    return int(cjk * 1.0 + other / 4.0) + 1


# ---------------------------------------------------------------- 上游调用
RETRYABLE = ("TLS connect error", "SSLError", "Connection reset", "502 Bad Gateway")
# 上游在网络抖动时常见的临时故障，值得重试
RETRY_HINTS = ("TLS", "SSL", "reset", "timeout", "429", "502", "503", "curl: (35)", "curl: (56)")


class UpstreamError(Exception):
    """上游返回非 2xx 时抛出，保留原始报文与状态码"""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message or ""


# 单次请求的总时间预算（秒）。agent 客户端通常在 60 秒左右超时，
# 这里必须留出余量，否则重试会把客户端拖死。
# 首轮给足时间（agent 多轮本来就慢，掐太死会误杀正常请求）
FIRST_TIMEOUT = 90.0
# 首轮失败后，重试总共最多再等这么久
BUDGET = 52.0


def _fetch_with_deadline(req, deadline):
    """在硬性截止时间内完成请求。

    urllib 的 timeout 只约束单次 socket 操作，慢速长响应仍可能耗时数十秒，
    因此用一个工作线程 + join(deadline) 实现真正的总时长上限。
    """
    box = {}

    def worker():
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=max(5, deadline)) as r:
                box["data"] = r.read()
        except urllib.error.HTTPError as e:
            try:
                box["httperror"] = (e.code, e.read().decode("utf-8", "replace"))
            except Exception:
                box["httperror"] = (e.code, "")
        except Exception as e:
            box["error"] = e

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    th.join(deadline)
    if th.is_alive():
        raise TimeoutError(f"upstream exceeded {deadline:.0f}s")
    if "httperror" in box:
        code, msg = box["httperror"]
        raise UpstreamError(code, msg)
    if "error" in box:
        raise box["error"]
    return box.get("data", b"")


def call_upstream_raw(path, payload, timeout=None, attempts=None):
    """原样转发到上游指定路径，返回解析后的 JSON。

    重试受总时间预算约束：剩余时间不足就不再重试，
    避免把客户端拖到它自己的超时线（典型 60s）。
    """
    timeout = timeout or TIMEOUT
    attempts = attempts or RETRIES
    body = json.dumps(payload, ensure_ascii=False).encode()
    started = time.time()
    last = None

    for i in range(attempts):
        elapsed = time.time() - started
        remain = FIRST_TIMEOUT + BUDGET - elapsed
        if i > 0 and remain <= 8:
            break
        # 单次超时不超过剩余预算
        if i == 0:
            this_timeout = FIRST_TIMEOUT
        else:
            this_timeout = max(20, min(timeout, remain))
        req = urllib.request.Request(UPSTREAM + path, data=body, method="POST")
        req.add_header("Authorization", "Bearer " + UPSTREAM_KEY)
        req.add_header("Content-Type", "application/json")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            _raw = _fetch_with_deadline(req, this_timeout)
            return json.loads(_raw.decode())
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")
            last = msg
            # 限流类错误不重试，立即返回（重试也没用，还浪费时间）
            if e.code == 429 and "quota" in msg.lower():
                raise UpstreamError(e.code, msg)
            if i < attempts - 1 and any(k in msg for k in RETRY_HINTS):
                back = min(2.0 * (i + 1), max(0, BUDGET - (time.time() - started) - 5))
                if back > 0:
                    time.sleep(back)
                continue
            raise UpstreamError(e.code, msg)
        except Exception as e:
            last = str(e)
            if i < attempts - 1:
                back = min(2.0 * (i + 1), max(0, BUDGET - (time.time() - started) - 5))
                if back > 0:
                    time.sleep(back)
                continue
            raise
    raise RuntimeError(last or "upstream timeout")


def call_upstream_stream(payload, on_delta, timeout=None):
    """流式调用上游，边收边回调 on_delta(text)。

    返回 (full_text, tool_use_blocks)。
    这样客户端能在几秒内看到首字，不必干等上游整段完成。
    """
    timeout = timeout or FIRST_TIMEOUT
    body = json.loads(json.dumps(payload))
    body["stream"] = True
    raw = json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(UPSTREAM + "/v1/messages", data=raw, method="POST")
    req.add_header("Authorization", "Bearer " + UPSTREAM_KEY)
    req.add_header("Content-Type", "application/json")
    req.add_header("anthropic-version", "2023-06-01")

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    text_parts = []
    tool_blocks = []
    cur_tool = None
    deadline = time.time() + timeout

    def guarded_read(resp):
        """带截止时间的按行读取"""
        while True:
            if time.time() > deadline:
                raise TimeoutError("upstream stream timeout")
            line = resp.readline()
            if not line:
                return None
            yield line

    with opener.open(req, timeout=timeout) as resp:
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "event-stream" not in ctype:
            # 上游没走流式，退化为整包读取
            data = json.loads(resp.read().decode())
            for b in data.get("content", []) or []:
                if b.get("type") == "text":
                    t = b.get("text") or ""
                    text_parts.append(t)
                    on_delta(t)
                elif b.get("type") == "tool_use":
                    tool_blocks.append({"name": b.get("name"),
                                        "arguments": json.dumps(b.get("input") or {},
                                                                ensure_ascii=False)})
            return "".join(text_parts), tool_blocks

        for line in guarded_read(resp):
            s = line.decode("utf-8", "replace").strip()
            if not s or s.startswith("event:"):
                continue
            if not s.startswith("data:"):
                continue
            payload_str = s[5:].strip()
            if payload_str in ("[DONE]", ""):
                continue
            try:
                ev = json.loads(payload_str)
            except Exception:
                continue

            et = ev.get("type")
            if et == "content_block_start":
                blk = ev.get("content_block") or {}
                if blk.get("type") == "tool_use":
                    cur_tool = {"name": blk.get("name"), "buf": ""}
            elif et == "content_block_delta":
                d = ev.get("delta") or {}
                if d.get("type") == "text_delta":
                    t = d.get("text") or ""
                    if t:
                        text_parts.append(t)
                        on_delta(t)
                elif d.get("type") == "input_json_delta":
                    if cur_tool is not None:
                        cur_tool["buf"] += d.get("partial_json") or ""
            elif et == "content_block_stop":
                if cur_tool is not None:
                    try:
                        args = json.loads(cur_tool["buf"]) if cur_tool["buf"].strip() else {}
                    except Exception:
                        args = {}
                    tool_blocks.append({"name": cur_tool["name"],
                                        "arguments": json.dumps(args, ensure_ascii=False)})
                    cur_tool = None
            elif et == "message_stop":
                break

    return "".join(text_parts), tool_blocks


def call_upstream(payload, timeout=None, attempts=None):
    """调用上游 /v1/messages。带总时长硬上限与必要重试。"""
    attempts = attempts or RETRIES
    body = json.dumps(payload, ensure_ascii=False).encode()
    started = time.time()
    last = None

    for i in range(attempts):
        elapsed = time.time() - started
        remain = FIRST_TIMEOUT + BUDGET - elapsed
        if i > 0 and remain <= 8:
            break
        if i == 0:
            this_timeout = FIRST_TIMEOUT
        else:
            this_timeout = max(20, min(timeout or FIRST_TIMEOUT, remain))
        req = urllib.request.Request(UPSTREAM + "/v1/messages", data=body, method="POST")
        req.add_header("Authorization", "Bearer " + UPSTREAM_KEY)
        req.add_header("Content-Type", "application/json")
        req.add_header("anthropic-version", "2023-06-01")
        try:
            raw = _fetch_with_deadline(req, this_timeout)
            return json.loads(raw.decode())
        except UpstreamError as e:
            last = e.message
            if e.code == 429 and "quota" in (e.message or "").lower():
                raise
            if i < attempts - 1 and any(k in (e.message or "") for k in RETRY_HINTS):
                back = min(2.0 * (i + 1), max(0, BUDGET - (time.time() - started) - 5))
                if back > 0:
                    time.sleep(back)
                continue
            raise
        except Exception as e:
            last = str(e)
            if i < attempts - 1:
                back = min(2.0 * (i + 1), max(0, BUDGET - (time.time() - started) - 5))
                if back > 0:
                    time.sleep(back)
                continue
            raise TimeoutError(last or "upstream timeout")
    raise TimeoutError(last or "upstream timeout")



def extract_tool_use(data):
    """读取上游已标准化的 tool_use 块"""
    out = []
    for b in data.get("content", []) or []:
        if b.get("type") == "tool_use" and b.get("name"):
            args = b.get("input")
            out.append({
                "name": b["name"],
                "arguments": json.dumps(args or {}, ensure_ascii=False),
            })
    return out


def extract_text(data):
    parts = []
    for b in data.get("content", []) or []:
        if b.get("type") == "text":
            parts.append(b.get("text") or "")
    return "".join(parts)


import time as _time


class ReqLog:
    """把每个请求的关键信息写入文件，便于诊断客户端到底发了什么"""

    def __init__(self, path):
        self.path = path

    def write(self, line):
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(_time.strftime("[%m-%d %H:%M:%S] ") + line + "\n")
        except Exception:
            pass

# ---------------------------------------------------------------- HTTP 服务
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _log(self, line):
        if not hasattr(self, "_reqlog"):
            import os as _os
            self._reqlog = ReqLog(_os.path.join(
                _os.path.dirname(_os.path.abspath(__file__)), "requests.log"))
        self._reqlog.write(line)

    def _html(self, body, code=200):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        try:
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(raw)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            self.close_connection = True

    _raw_mode = False

    # ================================================================
    # 同源 noVNC 反向代理  /vnc/*
    #
    # 为什么需要：前端原来把内置浏览器地址硬编码成 http://<host>:6080/vnc.html。
    # 三个问题叠加导致黑屏：
    #   1. 面板走 HTTPS/反代时，iframe 指向 http://...:6080 是混合内容，被浏览器直接拦掉
    #   2. 6080 通常没有对外映射，即使 http 也连不上
    #   3. 容器内 Chromium 的 loopback 也走代理，容器内访问 127.0.0.1:xxxx 不一定通
    # 改成同源相对路径 /vnc/* 后：自动继承页面协议、不需要额外开端口、不受混合内容限制。
    #
    # 关键：WebSocket 与静态资源必须分开处理（详见 _proxy_to_novnc 注释）。
    # ================================================================
    def _proxy_to_novnc(self, path):
        """把 /vnc/* 转发到容器内 6080 的 noVNC。"""
        # ---------- WebSocket：裸字节中继 ----------
        if path == "/vnc/websockify":
            try:
                up = socket.create_connection((NOVNC_HOST, NOVNC_PORT), timeout=15)
            except Exception:
                self._json(502, {"error": "noVNC 未就绪（6080 连不上）"})
                return
            try:
                lines = ["%s /websockify HTTP/1.1" % self.command]
                for k, v in self.headers.items():
                    lk = k.lower()
                    if lk in ("connection", "keep-alive", "transfer-encoding",
                              "host", "upgrade"):
                        continue
                    lines.append("%s: %s" % (k, v))
                lines.append("Host: %s:%d" % (NOVNC_HOST, NOVNC_PORT))
                lines.append("Connection: Upgrade")
                if self.headers.get("Upgrade"):
                    lines.append("Upgrade: " + self.headers.get("Upgrade"))
                up.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())

                up.settimeout(30)
                first = up.recv(65536)
                if not first:
                    self.close_connection = True
                    return
                self.wfile.write(first)
                self.wfile.flush()

                client_sock = self.connection
                client_sock.setblocking(False)
                up.setblocking(False)
                idle = 0
                while True:
                    try:
                        r, _, _ = select.select([client_sock, up], [], [], 5)
                    except Exception:
                        break
                    if not r:
                        idle += 5
                        if idle >= 300:
                            break
                        continue
                    idle = 0
                    if client_sock in r:
                        data = client_sock.recv(65536)
                        if not data:
                            break
                        up.sendall(data)
                    if up in r:
                        data = up.recv(65536)
                        if not data:
                            break
                        client_sock.sendall(data)
            except Exception:
                pass
            finally:
                try:
                    up.close()
                except Exception:
                    pass
                self.close_connection = True
            return

        # ---------- 静态资源：按文件直读，不用裸字节中继 ----------
        # 注意：绝不能和 WebSocket 共用裸字节中继 —— 连接关闭时机不可控，
        # 浏览器会报 net::ERR_ABORTED Script，noVNC 的 ES module 加载失败，
        # 页面停在白/黑屏。
        sub = path[len("/vnc"):] or "/"
        if not sub.startswith("/"):
            sub = "/" + sub
        # 目录访问给 index
        if sub.endswith("/"):
            sub += "vnc.html"

        # 防目录穿越
        safe = os.path.normpath(sub).lstrip("/")
        if safe.startswith(".."):
            self._json(400, {"error": "bad path"})
            return

        cand = os.path.join(NOVNC_ROOT, safe)
        if not os.path.isfile(cand):
            # 有些部署 noVNC 在 /usr/share/novnc/ 之外，兜底走 HTTP 转发
            try:
                op2 = urllib.request.build_opener(
                    urllib.request.ProxyHandler({}))
                req = urllib.request.Request(
                    "http://%s:%d%s" % (NOVNC_HOST, NOVNC_PORT, sub))
                with op2.open(req, timeout=20) as r:
                    body = r.read()
                    self.send_response(r.status)
                    self.send_header("Content-Type",
                                     r.headers.get("Content-Type") or
                                     "application/octet-stream")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(body)
                return
            except Exception as e:
                self._json(404, {"error": "noVNC 资源不存在: %s" % safe,
                                 "detail": str(e)[:120]})
                return

        # 按扩展名给 Content-Type
        ext = os.path.splitext(cand)[1].lower()
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".mjs": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
            ".woff": "font/woff",
            ".woff2": "font/woff2",
            ".ttf": "font/ttf",
            ".map": "application/json; charset=utf-8",
        }.get(ext, "application/octet-stream")

        try:
            with open(cand, "rb") as f:
                body = f.read()
        except Exception as e:
            self._json(500, {"error": "读取 noVNC 资源失败", "detail": str(e)[:120]})
            return

        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except Exception:
                pass

    def _proxy_to_panel(self):
        """把请求原样转发给容器内的 chatgpt2api 面板（3001）

        这样 /accounts /login /api/* 等所有原生页面都能正常用，
        不用在网关里逐个实现。
        """
        try:
            body = b""
            n = int(self.headers.get("Content-Length") or 0)
            if n:
                body = self.rfile.read(n)

            url = PANEL + self.path
            req = urllib.request.Request(url, data=body if body else None,
                                         method=self.command)
            # 透传关键请求头（跳过 hop-by-hop）
            skip = {"host", "connection", "keep-alive", "transfer-encoding",
                    "proxy-authenticate", "proxy-authorization", "te",
                    "trailers", "upgrade", "content-length"}

            # 密码翻译层：
            #   面板只认环境变量里的原始密码（UPSTREAM_KEY），
            #   但用户在设置页改过密码后，客户端带的是新密码（override）。
            #   这里把「新密码」换成面板真实密钥再转发，同时让「旧密码」彻底失效。
            try:
                _ov = webapi.auth_override_key()
            except Exception:
                _ov = ""
            _auth_in = (self.headers.get("Authorization") or "").strip()
            _xkey_in = (self.headers.get("x-api-key") or "").strip()
            _reject = False
            if _ov:
                if _auth_in == "Bearer " + _ov:
                    _auth_in = "Bearer " + UPSTREAM_KEY
                elif _auth_in == "Bearer " + UPSTREAM_KEY:
                    _reject = True
                if _xkey_in == _ov:
                    _xkey_in = UPSTREAM_KEY
                elif _xkey_in == UPSTREAM_KEY:
                    _reject = True
            if _reject:
                # 旧密码已作废，别把它转给面板（否则面板会放行）
                self._json(401, {"error": {"message": "密钥无效或已失效，请重新登录",
                                           "type": "authentication_error",
                                           "code": "invalid_api_key"}})
                return

            for k, v in self.headers.items():
                lk = k.lower()
                if lk in skip:
                    continue
                if lk == "authorization":
                    v = _auth_in or v
                elif lk == "x-api-key":
                    v = _xkey_in or v
                req.add_header(k, v)

            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            hdrs = None
            try:
                with opener.open(req, timeout=120) as r:
                    status = r.status
                    data = r.read()
                    hdrs = r.headers
                    ctype = r.headers.get("Content-Type", "text/html; charset=utf-8")
            except urllib.error.HTTPError as e:
                status = e.code
                data = e.read()
                hdrs = e.headers
                ctype = (e.headers.get("Content-Type") if e.headers
                         else "text/html; charset=utf-8") or "text/html; charset=utf-8"

            # /raw/* 场景：面板若返回 302 到 /login，要改写成 /raw/login，
            # 否则 iframe 会跳出 /raw 前缀，整页又变成嵌套外壳（菜单套菜单）。
            if self._raw_mode and status in (301, 302, 303, 307, 308):
                loc = (hdrs.get("Location") if hdrs else "") or ""
                if loc.startswith("/") and not loc.startswith("/raw/"):
                    self.send_response(status)
                    self.send_header("Location", "/raw" + loc)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return

            # 给原生面板的 HTML 注入顶部导航条，保证任何页面都能切回「对话/代理设定」
            if "text/html" in (ctype or "") and status == 200 and not self._raw_mode:
                try:
                    html = data.decode("utf-8", "replace")
                    html = inject_navbar(html)
                    data = html.encode("utf-8")
                    ctype = "text/html; charset=utf-8"
                except Exception:
                    pass

            # 图片地址统一改写：把面板返回的容器内部地址（127.0.0.1:3001 等）
            # 换成对外的 Host，否则浏览器打不开 —— 表现为「页面只显示一串路径」。
            # 覆盖 /v1/images/edits（图生图）、/api/images（图片管理页）、
            # /api/logs（日志详情里的图片）等所有经此转发的 JSON 接口。
            if status == 200 and "application/json" in (ctype or ""):
                try:
                    new_data, hit = rewrite_image_urls_in_bytes(data, self.headers)
                    if hit:
                        data = new_data
                        ctype = "application/json; charset=utf-8"
                except Exception:
                    pass

            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            # 关键：面板是 Next.js，chunk 文件名带 hash 时才适合长缓存；
            # 但它这里的 chunk 名是固定的（如 0xaq6n.l11b6j.js），一旦被浏览器
            # 按「启发式缓存」存下来，改过的 bundle 就永远拿不到 ——
            # 这正是「菜单一直不出现、授权页还是弹新窗口」的真正原因。
            # 所以静态资源也用 no-store，保证每次都拿到最新文件。
            self.send_header("Cache-Control",
                             "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("ETag", '"%d"' % len(data))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            self.close_connection = True
        except Exception as e:
            self._log("PROXY PANEL ERR %s" % str(e)[:150])
            try:
                self._json(502, {"error": {"message": "panel unreachable: " + str(e)[:100]}})
            except Exception:
                pass

    def _client_key(self):
        """取客户端提供的 Key。支持三种常见写法：

          1. Authorization: Bearer <key>     （OpenAI 标准，推荐）
          2. x-api-key: <key>                （Anthropic/部分客户端）
          3. ?api_key=<key> / ?key=<key>     （浏览器 / 简易客户端）
        """
        h = self.headers.get("Authorization") or ""
        if h.lower().startswith("bearer "):
            k = h[7:].strip()
            if k:
                return k
        k = (self.headers.get("x-api-key") or "").strip()
        if k:
            return k
        # 查询参数兜底（很多人把 key 拼在 URL 上，之前会 401）
        try:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            for name in ("api_key", "key", "token", "access_token"):
                v = (qs.get(name) or [""])[0].strip()
                if v:
                    return v
        except Exception:
            pass
        return ""

    _key_cache = {"keys": None, "ts": 0.0}

    def _panel_api_keys(self):
        """从面板取「设置页」里生成的 API Key（role=user）。

        面板有独立的 API Key 体系（/api/auth/users），
        和登录口令（auth-key）是两回事 —— 用户要求 API 连接用前者。
        这里带 30 秒缓存，避免每次请求都打面板。
        """
        import time as _t
        now = _t.time()
        if self._key_cache["keys"] is not None and (now - self._key_cache["ts"] < 30):
            return self._key_cache["keys"]
        try:
            _op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            req = urllib.request.Request(PANEL + "/api/auth/users")
            req.add_header("Authorization", "Bearer " + UPSTREAM_KEY)
            raw = _op.open(req, timeout=10).read().decode()
            items = json.loads(raw).get("items") or []
            # 只取 enabled 的；面板不返回明文，仅返回 id/name，
            # 所以这里缓存的是「指纹」，实际校验交给面板 /auth/login。
            self._key_cache["keys"] = items
            self._key_cache["ts"] = now
            return items
        except Exception:
            self._key_cache["keys"] = []
            self._key_cache["ts"] = now
            return []

    def _panel_key_valid(self, key):
        """拿面板校验一个 API Key 是否有效（走 /auth/login）。"""
        if not key:
            return False
        try:
            _op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            req = urllib.request.Request(PANEL + "/auth/login", data=b"{}", method="POST")
            req.add_header("Authorization", "Bearer " + key)
            req.add_header("Content-Type", "application/json")
            _op.open(req, timeout=10).read()
            return True
        except urllib.error.HTTPError:
            return False
        except Exception:
            return False

    def _auth_ok(self):
        """校验 Key。接受三类：

          1. 登录口令（config.ini / 环境变量）—— 管理面板用
          2. 用户在设置页改过的新密码（auth-override.json）—— 立即生效
          3. 设置页生成的 API Key（/api/auth/users）—— 第三方应用用
        未配置任何 Key 时放行。
        """
        got = self._client_key()

        # 用户在设置页改过密码 → 只有新密码有效，环境变量里的旧密码立即作废。
        # （必须放在最前面判断，否则旧密码会一直被放行）
        try:
            ov = webapi.auth_override_key()
        except Exception:
            ov = ""
        if ov:
            if got == ov:
                return True
            # sk- 开头的 API Key 仍然有效（第三方客户端用）
            if got.startswith("sk-"):
                return self._panel_key_valid(got)
            return False

        expect = UPSTREAM_KEY
        if not expect:
            return True
        if got == expect:
            return True
        if got.startswith("sk-"):
            # 面板 API Key 形如 sk-xxxx，交给面板校验
            return self._panel_key_valid(got)
        return False

    def _deny(self):
        self._json(401, {"error": {"message": "密钥无效或已失效",
                                   "type": "authentication_error",
                                   "code": "invalid_api_key"}})

    _page_key = {"v": None, "ts": 0.0}

    def _page_api_key(self):
        """取一个可用的「设置页 API Key」用于内置页面。

        用户要求：连接项目/调用 API 要用设置页生成的 key，
        而不是进入面板的登录口令。这里自动取一个 role=user 的 key。
        面板只在创建时返回明文，所以要把明文存在
        data/page-api-key.txt 里复用。

        重要：如果这个文件不存在（全新部署 / 刚清理过），
        必须自动创建一个 —— 否则页面上的 /v1/models 会返回 401，
        前端收到 401 会立刻跳回登录页，用户会以为"登录不了"。
        """
        import time as _t
        now = _t.time()
        if self._page_key["v"] and (now - self._page_key["ts"] < 60):
            return self._page_key["v"]
        v = ""
        try:
            v = open("/app/data/page-api-key.txt", encoding="utf-8").read().strip()
        except Exception:
            v = ""
        if not v:
            v = self._create_page_key()
        if not v:
            v = (UPSTREAM_KEY or "").strip()
        self._page_key["v"] = v
        self._page_key["ts"] = now
        return v

    def _create_page_key(self):
        """创建一个页面专用的 API Key，并把明文存到 data/page-api-key.txt。"""
        try:
            import os as _os
            body = json.dumps({
                "name": "内置页面",
                "role": "user",
            }).encode()
            req = urllib.request.Request(PANEL + "/api/auth/users",
                                         data=body, method="POST")
            req.add_header("Authorization", "Bearer " + str(UPSTREAM_KEY or ""))
            req.add_header("Content-Type", "application/json")
            raw = urllib.request.build_opener(
                urllib.request.ProxyHandler({})).open(req, timeout=20).read()
            d = json.loads(raw.decode())
            # 面板返回格式：{"key": "sk-...", "item": {...}}
            k = (d.get("key") or (d.get("item") or {}).get("key") or "").strip()
            if not k:
                return ""
            _os.makedirs("/app/data", exist_ok=True)
            with open("/app/data/page-api-key.txt", "w", encoding="utf-8") as f:
                f.write(k)
            print("[page-key] 已自动创建页面 API Key", flush=True)
            return k
        except Exception as e:
            print("[page-key] 创建失败（回退登录口令）:", str(e)[:100], flush=True)
            return ""

    def _with_key(self, html):
        """把页面里的 __C2A_KEY__ 占位替换成真实密钥。

        优先用「设置页生成的 API Key」（sk- 开头），
        没有配置时回退到登录口令，保证页面始终能用。
        """
        try:
            key = self._page_api_key().replace("'", "").replace('"', "")
            return html.replace("__C2A_KEY__", key)
        except Exception:
            return html

    def _json(self, code, obj):
        raw = json.dumps(obj, ensure_ascii=False).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # 客户端已超时断开（agent 客户端常见）。静默忽略，
            # 避免异常冒泡到外层再次写 socket 造成二次报错。
            self.close_connection = True

    # ---------------- HEAD / OPTIONS ----------------
    # BaseHTTPRequestHandler 不会自动处理 HEAD/OPTIONS；缺这两个方法时
    # 所有 HEAD/OPTIONS 都会落到 "501 Unsupported method"。
    # 而 Next.js 的 <Link prefetch> 会发 HEAD，浏览器跨域/预检会发 OPTIONS，
    # 结果就是控制台刷一片 501，偶尔还会拖慢首屏。
    def do_HEAD(self):
        # HEAD 只回头、不回体：复用 GET 的头部逻辑最省事，
        # 这里直接按路径给一个合理状态码即可。
        path = self.path.split("?")[0].rstrip("/") or "/"
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.end_headers()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            self.close_connection = True

    def do_OPTIONS(self):
        path = self.path.split("?")[0]
        is_api = path.startswith("/v1/") or path.startswith("/api") or path.startswith("/p/api/")
        try:
            self.send_response(200)
            if is_api:
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods",
                                 "GET, POST, PUT, DELETE, OPTIONS")
                self.send_header("Access-Control-Allow-Headers",
                                 "Authorization, Content-Type, x-api-key, "
                                 "anthropic-version, anthropic-beta")
                self.send_header("Access-Control-Max-Age", "86400")
            self.send_header("Content-Length", "0")
            self.end_headers()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            self.close_connection = True

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        qs = urllib.parse.parse_qs(self.path.split("?")[1]) if "?" in self.path else {}

        if path in ("/v1/models", "/models"):
            if not self._auth_ok():
                self._deny()
                return
            # 代理面板的动态模型目录（各账号类型 + 匿名 + 生图模型都在里面）。
            # 应用层按「号池页 → 管理模型」的禁用清单过滤：被禁用的模型
            # 在对话页下拉和 API 层（agent 应用连接）都不再出现。
            try:
                _op = urllib.request.build_opener(
                    urllib.request.ProxyHandler({}))
                req = urllib.request.Request(PANEL + "/v1/models")
                # 注意：这里必须用面板的真实密钥，不能透传客户端提供的密码。
                # 用户改过密码后，客户端带的是新密码，面板不认 → 会 502。
                req.add_header("Authorization", "Bearer " + UPSTREAM_KEY)
                raw = _op.open(req, timeout=60).read()
                try:
                    data = json.loads(raw)
                    off = set(webapi.get_auto_exclude()["exclude"]) if False else None
                    # 模型禁用清单存在浏览器 localStorage 不可读，
                    # 读的是面板同款的 data/model-off.json（由号池页"管理模型"写入）。
                    try:
                        off = set(json.loads(open("/app/data/model-off.json", encoding="utf-8").read()))
                    except Exception:
                        off = set()
                    # 禁用模型要同时从生图允许的模型目录里也删掉，
                    # 否则生图面板的模型下拉还能看到被禁用的 gpt-image-2 等。
                    if off:
                        data["data"] = [m for m in data.get("data", [])
                                        if m.get("id") not in off]
                    raw = json.dumps(data, ensure_ascii=False).encode()
                except Exception:
                    pass
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(raw)
            except Exception as e:
                self._json(502, {"error": {"message": str(e)[:150]}})
            return

        if path == "/health":
            # 带上依赖状态，方便编排层/监控判断是否真的就绪
            mihomo_ok = False
            try:
                op_h = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                op_h.open("http://127.0.0.1:9090/version", timeout=3).read()
                mihomo_ok = True
            except Exception:
                pass
            novnc_ok = os.path.isfile(os.path.join(NOVNC_ROOT, "vnc.html"))
            node_cnt = 0
            try:
                node_cnt = len(webapi.proxy_nodes()) if webapi else 0
            except Exception:
                pass
            self._json(200, {"status": "ok", "mihomo": mihomo_ok,
                             "novnc": novnc_ok, "nodes": node_cnt,
                             "version": getattr(webui, "APP_VERSION", "")})
            return

        # 同源 noVNC 代理：/vnc/* 直接转发到容器内 6080，
        # 自动继承页面协议（http/https），不用额外开端口、不受混合内容限制。
        if path == "/vnc" or path == "/novnc":
            self.send_response(302)
            self.send_header(
                "Location", "/vnc/vnc.html?autoconnect=1&resize=remote&path=websockify")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/vnc/websockify" or path.startswith("/vnc/"):
            self._proxy_to_novnc(self.path.split("?")[0].rstrip("/") or "/")
            return

        # 常见误访问：/login 等，统一回到控制台
        # 注意：path 已经 rstrip("/")，所以 /login/ 会变成 /login。
        # 这里绝不能重定向到 /login/，否则形成死循环（浏览器不停刷新）。
        # 登录页由下面的面板转发统一处理。

        # ---------------- WebUI ----------------
        if webui is not None:
            # 首页直接用面板自己的页面（原生导航栏、原生配色），
            # 不再套那层自建的深色外壳。
            if path in ("/", "/accounts", "/image", "/image-manager", "/logs",
                        "/settings", "/debug"):
                self._proxy_to_panel()
                return
            if path in ("/p/proxy", "/p/proxy/"):
                self._html(self._with_key(_PAGES["proxy"]))
                return
            if path in ("/p/chat", "/p/chat/"):
                self._html(self._with_key(_PAGES["chat"]))
                return
            if path == "/p/stats":
                try:
                    # 节点名要按实际链路取：ChatGPT 组 -> 节点选择 -> 具体节点。
                    # 订阅里根本没有「优先线路」这个分组，写死它会永远拿到 None。
                    node, _loc = webapi.current_node()
                    cnt, _ = webapi.accounts_info()
                    self._json(200, {"node": node, "delay": webapi.delay_of(),
                                "accounts": cnt})
                except Exception as e:
                    self._json(200, {"node": None, "delay": None, "accounts": None,
                                "error": str(e)[:100]})
                return
            if path == "/p/api/proxy/auto-exclude":
                self._json(200, webapi.get_auto_exclude())
                return
            if path == "/p/api/proxy/removed":
                self._json(200, webapi.get_removed())
                return
            if path == "/p/api/models/off":
                self._json(200, webapi.get_model_off())
                return
            if path == "/p/api/onboarding":
                self._json(200, webapi.get_onboarding())
                return
            if path == "/p/api/auth/password":
                self._json(200, {"changed": bool(webapi.auth_override_key())})
                return
            if path == "/p/api/proxy":
                try:
                    ip, loc = webapi.exit_info()
                    self._json(200, {"groups": webapi.proxy_groups(),
                                "nodes": webapi.proxy_nodes(),
                                "delay": webapi.delay_of(),
                                "exit_ip": ip, "exit_loc": loc})
                except Exception as e:
                    self._json(200, {"groups": [], "nodes": [], "delay": None,
                                "error": str(e)[:150]})
                return
            if path == "/p/api/subscription":
                self._json(200, {"url": webapi.saved_sub()})
                return
            if path in ("/p/oauth", "/p/oauth/"):
                self._html(self._with_key(oauth_page.OAUTH_PAGE))
                return
            if path == "/p/api/proxyaddr":
                self._json(200, {"addr": "127.0.0.1:8888"})
                return

            if path == "/p/api/browser/ip":
                self._json(200, webapi.browser_exit_ip())
                return

            if path == "/p/api/oauth/auto-status":
                self._json(200, webapi.browser_callback())
                return
            if path == "/p/api/oauth/callback":
                # GET 也要能取（前端用 fetch 默认 GET）
                self._json(200, webapi.browser_callback())
                return
            if path == "/p/api/accounts":
                cnt, lst = webapi.accounts_info()
                self._json(200, {"count": cnt, "items": lst})
                return
            # OAuth 桥：/auth 打开授权页
            if path == "/auth":
                sid = (qs.get("sid") or [""])[0]
                cb = (qs.get("cb") or [""])[0]
                if cb:
                    r = webapi.finish_oauth(sid, cb)
                    if r.get("ok"):
                        self._html("<h2 style='font-family:system-ui;padding:40px'>"
                                   "<span style='color:#22c55e'>授权成功</span><br><br>"
                                   "账号已添加，可以关闭此页。</h2>")
                    else:
                        self._html("<h2 style='font-family:system-ui;padding:40px'>"
                                   "<span style='color:#ef4444'>授权失败</span><br><br>"
                                   "<pre style='white-space:pre-wrap'>"
                                   + (r.get("error") or "")[:800] + "</pre></h2>")
                    return
                self._json(400, {"error": "missing cb"})
                return

        # /raw/* 原样转发给面板，不做任何 HTML 注入或改写
        if path.startswith("/raw/"):
            self._raw_mode = True
            self.path = self.path.replace("/raw/", "/", 1)
            self._proxy_to_panel()
            return

        # 其余所有路径：转发给原生面板（/accounts /login /api/* 等）
        self._proxy_to_panel()

    def do_POST(self):
        path = self.path.rstrip("/").split("?")[0]

        # ---------------- WebUI POST ----------------
        if webui is not None and path.startswith("/p/api/"):
            try:
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n)
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("gbk", "replace")
                body = json.loads(text or "{}")
            except Exception:
                body = {}

            if path == "/p/api/models/off":
                self._json(200, webapi.set_model_off(body.get("models") or []))
                return

            if path == "/p/api/onboarding":
                self._json(200, webapi.set_onboarding(bool(body.get("done", True))))
                return

            # 设置页改登录密码（立即生效，不用重建容器）
            if path == "/p/api/auth/password":
                self._json(200, webapi.change_auth_password(
                    body.get("current") or "", body.get("new") or ""))
                return
            if path == "/p/api/auth/password/reset":
                self._json(200, webapi.reset_auth_password())
                return

            if path == "/p/api/proxy/remove-node":
                name = (body.get("node") or "").strip()
                undo = bool(body.get("undo"))
                if not name:
                    self._json(200, {"ok": False, "error": "node 为空"})
                else:
                    self._json(200, webapi.remove_node(name, undo))
                return

            if path == "/p/api/proxy/grp-order":
                self._json(200, webapi.save_auto_order(body.get("order") or []))
                return

            if path == "/p/api/proxy/select":
                try:
                    node = body.get("node") or ""
                    if node in ("__auto__", "自动选择", "优先线路"):
                        webapi.restore_auto()
                    else:
                        webapi.select_node(node)
                    self._json(200, {"ok": True})
                except Exception as e:
                    self._json(200, {"ok": False, "error": str(e)[:200]})
                return

            if path == "/p/api/proxy/auto-exclude":
                node = body.get("node") or ""
                include = bool(body.get("include", True))
                if not node:
                    self._json(200, {"ok": False, "error": "node 为空"})
                else:
                    self._json(200, webapi.save_auto_exclude(node, include))
                return

            if path == "/p/api/proxy/auto-pick":
                self._json(200, webapi.auto_pick_best())
                return

            if path == "/p/api/logs/delete-failed":
                self._json(200, webapi.delete_failed_logs())
                return
            if path == "/p/api/logs/clear":
                self._json(200, webapi.clear_all_logs())
                return

            if path == "/p/api/proxy/test":
                try:
                    nodes = webapi.test_all_nodes()
                    self._json(200, {"ok": True, "nodes": nodes})
                except Exception as e:
                    self._json(200, {"ok": False, "error": str(e)[:200]})
                return

            if path == "/p/api/subscription":
                try:
                    r = webapi.update_subscription(body.get("url") or "")
                    self._json(200, {"ok": True, **r})
                except Exception as e:
                    self._json(200, {"ok": False, "error": str(e)[:300]})
                return

            if path == "/p/api/auth/check":
                # 供外壳校验密钥并取回身份（role/name），用于给面板预置登录态
                k = (body.get("key") or "").strip()
                try:
                    req = urllib.request.Request(PANEL + "/auth/login", data=b"{}",
                                                 method="POST")
                    req.add_header("Authorization", "Bearer " + k)
                    req.add_header("Content-Type", "application/json")
                    _op = urllib.request.build_opener(
                        urllib.request.ProxyHandler({}))
                    r = json.loads(_op.open(req, timeout=15).read().decode())
                    self._json(200, {"ok": True, "role": r.get("role"),
                                     "subject_id": r.get("subject_id"),
                                     "name": r.get("name")})
                except urllib.error.HTTPError as e:
                    self._json(200, {"ok": False, "error": "密钥无效或已失效",
                                     "status": e.code})
                except Exception as e:
                    self._json(200, {"ok": False, "error": str(e)[:150]})
                return

            if path == "/p/api/oauth/open":
                r = webapi.browser_open(body.get("url") or "")
                self._json(200, r)
                return

            if path == "/p/api/browser/tabs":
                self._json(200, {"tabs": webapi.browser_tabs()})
                return

            if path == "/p/api/oauth/callback":
                # 自动从内置浏览器标签里捞回调地址，省掉手动复制
                self._json(200, webapi.browser_callback())
                return

            if path == "/p/api/oauth/start":
                # 新一轮授权：先清掉上一轮抓到的回调，
                # 否则会把旧 code 填进来（code 一次性，重用必然报 state 不匹配）
                try:
                    webapi.reset_callback_cache()
                except Exception:
                    pass
                r = webapi.start_oauth(body.get("email") or "")
                self._json(200, r if isinstance(r, dict) else {"error": "bad response"})
                return

            if path == "/p/api/oauth/reset":
                try:
                    webapi.reset_callback_cache()
                except Exception:
                    pass
                self._json(200, {"ok": True})
                return

            if path == "/p/api/oauth/finish":
                r = webapi.finish_oauth(body.get("session_id") or "",
                                        body.get("callback") or "")
                self._json(200, r if isinstance(r, dict) else {"error": "bad response"})
                return

            # 全自动完成：服务端从内置浏览器读 callback 并直接换 token 入库，
            # 用户不用复制粘贴（noVNC 的剪贴板本来就和宿主机不通）。
            if path == "/p/api/oauth/auto":
                r = webapi.oauth_auto_finish(body.get("session_id") or "",
                                             body.get("wait") or 0,
                                             body.get("email_hint") or "")
                self._json(200, r if isinstance(r, dict) else {"ok": False,
                                                               "error": "bad response"})
                return
            if path == "/p/api/oauth/auto-status":
                self._json(200, webapi.browser_callback())
                return

        if path.endswith("/images/generations"):
            try:
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n)
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("gbk", "replace")
                body = json.loads(text or "{}")
            except Exception as e:
                self._json(400, {"error": {"message": f"bad json: {e}"}})
                return
            try:
                self.image_generations_path(body)
            except UpstreamError as e:
                raw = e.message or ""
                try:
                    inner = json.loads(raw)
                    detail = (inner.get("error") or {}).get("message") or raw
                except Exception:
                    detail = raw
                msg = detail or "上游返回空错误体"
                if "no available image quota" in raw:
                    msg = ("生图额度已用完（no available image quota）。"
                           "免费账号每天 5 张；可在面板 http://127.0.0.1:3001/accounts "
                           "查看 remaining 与重置时间。")
                self._json(e.code if 400 <= e.code < 600 else 502,
                           {"error": {"message": msg, "type": "upstream_error"}})
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", "replace")
                # 把上游的 JSON 错误体原样透出，客户端能看到真实原因
                try:
                    inner = json.loads(raw)
                    detail = (inner.get("error") or {}).get("message") or raw
                except Exception:
                    detail = raw
                msg = detail
                if "no available image quota" in raw:
                    msg = ("no available image quota — 生图额度已用完。"
                           "免费账号每天 5 张，额度耗尽后需等次日重置；"
                           "可到面板 /accounts 查看 remaining 与 reset 时间。")
                self._json(e.code, {"error": {"message": msg, "type": "upstream_error"}})
            except Exception as e:
                self._json(500, {"error": {"message": str(e)[:300]}})
            return
        # 非对话类 POST：全部转发给原生面板（登录 /api/auth/* /api/accounts 等）
        if not path.endswith("/chat/completions"):
            self._proxy_to_panel()
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n)
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("gbk", "replace")
            body = json.loads(text or "{}")
        except Exception as e:
            self._json(400, {"error": {"message": f"bad json: {e}"}})
            return
        try:
            self._handle(body)
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:400]
            self._json(502, {"error": {"message": msg, "type": "upstream_error"}})
        except TimeoutError as e:
            msg = str(e)[:200]
            self._json(502, {"error": {
                "message": ("上游响应超时（" + msg + "）。"
                            "常见原因：账号额度紧张被限流、网络抖动。"
                            "可稍后重试，或到控制台查看 reason 剩余额度。"),
                "type": "upstream_timeout"}})
        except Exception as e:
            self._json(500, {"error": {"message": str(e)[:300]}})

    def image_generations_path(self, body):
        """POST /v1/images/generations —— 转发到上游"""
        payload = {
            "model": body.get("model") or "gpt-image-2",
            "prompt": body.get("prompt") or "",
            "n": body.get("n") or 1,
        }
        # 透传上游支持的其它参数
        for k in ("size", "quality", "response_format", "style", "background"):
            if body.get(k) is not None:
                payload[k] = body[k]

        if not payload["prompt"].strip():
            self._json(400, {"error": {"message": "prompt is required",
                                       "type": "invalid_request_error"}})
            return

        data = call_upstream_raw("/v1/images/generations", payload)
        # 上游返回的图片 URL 指向容器内部地址（127.0.0.1:3001），
        # 宿主机没映射该端口，客户端根本打不开 —— 统一改写成对外地址。
        # 用公共函数而不是前缀匹配：http/https、任意端口都能覆盖，
        # 历史数据里的 https://127.0.0.1:3001 也不会漏。
        try:
            base = _public_base(self.headers)
            if base:
                rewrite_image_urls(data, base)
        except Exception:
            pass
        self._json(200, data)

    def _handle(self, body):
        if not self._auth_ok():
            self._log("DENY bad key")
            self._deny()
            return
        self._log("REQ model=%s stream=%s tools=%d msgs=%d" % (
            body.get("model"), bool(body.get("stream")),
            len(body.get("tools") or []), len(body.get("messages") or [])))
        model = body.get("model") or DEFAULT_MODEL
        messages = body.get("messages") or []
        tools = body.get("tools") or []
        stream = bool(body.get("stream"))
        tool_choice = body.get("tool_choice")

        system, msgs = openai_msgs_to_anthropic(messages, tools)

        payload = {"model": model, "max_tokens": body.get("max_tokens") or 4096,
                   "messages": msgs}
        if system:
            payload["system"] = system
        # 关键：必须把 tools 传给上游（Anthropic 格式）。
        # 上游 content_blocks() 只有在 tools 非空时才会解析 <tool_call>，
        # 否则会剥离 XML 却返回空文本（output_tokens 有值但 content 为空）。
        if tools:
            payload["tools"] = [{
                "name": f.get("function", {}).get("name"),
                "description": f.get("function", {}).get("description") or "",
                "input_schema": f.get("function", {}).get("parameters")
                                or {"type": "object", "properties": {}},
            } for f in tools if (f or {}).get("function", {}).get("name")]

        t0 = time.time()
        # 两个分支都要用，统一在这里算一次
        prompt_text = json.dumps(messages, ensure_ascii=False) + system
        cid = "chatcmpl-" + uuid.uuid4().hex[:24]
        created = int(t0)

        # ---------------- 流式：真透传 ----------------
        if stream:
            self._gone = False
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                self.close_connection = True
                return

            base = {"id": cid, "object": "chat.completion.chunk",
                    "created": created, "model": model}
            state = {"started": False}

            def emit(obj):
                if self._gone:
                    return
                try:
                    self.wfile.write(("data: " + json.dumps(obj, ensure_ascii=False)
                                      + chr(10) + chr(10)).encode())
                    self.wfile.flush()
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    self._gone = True

            # 流式清洗器：上游 chunk 是任意切片，UI 组件会被切断。
            # 必须缓冲-清洗-推送，否则客户端会看到残缺的 JSX/代码
            #（这正是"API 回复里混着项目代码"的根因）。
            try:
                from stream_clean import StreamCleaner
                _sc = StreamCleaner()
            except Exception:
                _sc = None

            def on_delta(txt):
                # 首个增量到达时补发 role 帧，客户端可立即渲染
                if not state["started"]:
                    state["started"] = True
                    emit({**base, "choices": [{"index": 0,
                                               "delta": {"role": "assistant"},
                                               "finish_reason": None}]})
                out = _sc.feed(txt) if _sc else txt
                if not out:
                    return
                emit({**base, "choices": [{"index": 0,
                                           "delta": {"content": out},
                                           "finish_reason": None}]})

            # 上游偶发返回空内容（无文本、无工具）。此时尚未向客户端推送
            # 任何正文，可以安全重试，不会造成重复输出。
            full_text, tool_blocks = "", []
            last_err = ""
            # 单次空响应重试有总时长上限，避免"重试反而把请求拖到客户端超时"
            RETRY_DEADLINE = 45.0
            retry_started = time.time()
            for attempt in range(3):
                try:
                    full_text, tool_blocks = call_upstream_stream(payload, on_delta)
                    last_err = ""
                except Exception as e:
                    last_err = str(e)[:200]
                    self._log("STREAM ERROR(attempt %d) %s" % (attempt + 1, last_err))

                got_content = bool((full_text or "").strip()) or bool(tool_blocks)
                if got_content or state["started"] or self._gone:
                    break
                if attempt < 2:
                    elapsed = time.time() - retry_started
                    if elapsed >= RETRY_DEADLINE:
                        self._log("EMPTY response, give up（已用 %.0fs）" % elapsed)
                        break
                    self._log("EMPTY response, retry %d（已用 %.0fs）" % (attempt + 1, elapsed))
                    time.sleep(1.0)

            if last_err and not full_text and not tool_blocks:
                self._log("STREAM GAVE UP %s" % last_err)
                if not state["started"]:
                    emit({**base, "choices": [{"index": 0, "delta": {},
                                               "finish_reason": "stop"}]})
                if not self._gone:
                    try:
                        self.wfile.write(("data: " + json.dumps(
                            {"error": {"message": "上游多次返回空内容，请稍后重试（"
                                                  + last_err + "）"}},
                            ensure_ascii=False) + chr(10) + chr(10)).encode())
                        self.wfile.flush()
                    except Exception:
                        pass
                return

            if not state["started"]:
                emit({**base, "choices": [{"index": 0,
                                           "delta": {"role": "assistant"},
                                           "finish_reason": None}]})

            # 流结束：把缓冲里残余的（已确认不是残缺标签的）内容放出来
            if _sc is not None:
                tail = _sc.flush()
                if tail:
                    emit({**base, "choices": [{"index": 0,
                                               "delta": {"content": tail},
                                               "finish_reason": None}]})

            calls = tool_blocks or (parse_xml_calls(full_text) if tools else [])
            finish = "stop"
            if calls:
                finish = "tool_calls"
                for idx, c in enumerate(calls):
                    emit({**base, "choices": [{"index": 0, "delta": {"tool_calls": [{
                        "index": idx, "id": "call_" + uuid.uuid4().hex[:24],
                        "type": "function",
                        "function": {"name": c["name"], "arguments": ""}}]},
                        "finish_reason": None}]})
                    emit({**base, "choices": [{"index": 0, "delta": {"tool_calls": [{
                        "index": idx,
                        "function": {"arguments": c["arguments"]}}]},
                        "finish_reason": None}]})

            prompt_text = json.dumps(messages, ensure_ascii=False) + system
            u = {"prompt_tokens": count_tokens(prompt_text),
                 "completion_tokens": count_tokens(full_text),
                 "total_tokens": count_tokens(prompt_text) + count_tokens(full_text)}
            emit({**base, "choices": [{"index": 0, "delta": {},
                                       "finish_reason": finish}], "usage": u})
            if not self._gone:
                try:
                    self.wfile.write(b"data: [DONE]" + bytes([10, 10]))
                    self.wfile.flush()
                except Exception:
                    self._gone = True
            self._log("STREAM done stop=%s calls=%d %.1fs" % (
                finish, len(calls), time.time() - t0))
            return

        # ---------------- 非流式 ----------------
        data = call_upstream(payload)
        try:
            self._log("UPSTREAM stop=%s blocks=%s" % (
                data.get("stop_reason"),
                [b.get("type") for b in (data.get("content") or [])]))
        except Exception:
            pass

        # 上游已标准化的 tool_use 优先，否则从文本里的 XML 解析
        block_calls = extract_tool_use(data)
        raw_text = extract_text(data)
        if block_calls:
            clean = strip_ui_markup(raw_text)
            calls = block_calls
        else:
            clean = strip_ui_markup(raw_text)
            calls = parse_xml_calls(raw_text) if tools else []

        # 模型没调工具但也没输出正文时，给一句可读提示，避免"空回复"
        if not calls and not clean.strip():
            clean = "（模型本次未返回内容，请重试）"


        usage = {"prompt_tokens": count_tokens(prompt_text),
                 "completion_tokens": count_tokens(clean),
                 "total_tokens": count_tokens(prompt_text) + count_tokens(clean)}

        msg = {"role": "assistant", "content": None if calls else (clean or "")}
        finish = "stop"
        if calls:
            msg["tool_calls"] = [{
                "id": "call_" + uuid.uuid4().hex[:24],
                "type": "function",
                "function": {"name": c["name"], "arguments": c["arguments"]},
            } for c in calls]
            finish = "tool_calls"

        cid = "chatcmpl-" + uuid.uuid4().hex[:24]
        created = int(t0)

        if not stream:
            self._json(200, {
                "id": cid, "object": "chat.completion", "created": created, "model": model,
                "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
                "usage": usage,
            })
            return

def main():
    # 启动授权转发代理（浏览器设 127.0.0.1:8888 即可打开 OpenAI 授权页）
    try:
        import auth_proxy
        auth_proxy.start_in_thread()
    except Exception as e:
        print("auth_proxy 启动失败:", e, flush=True)

    # 启动后立即套用「用户上次手动选择的节点」（默认 🇺🇸 IEPL-美国-03）。
    # 目的：容器重启后不会漂到别的节点，也不会回到任何自动选择行为。
    def _apply_node():
        try:
            import time as _t
            _t.sleep(12)          # 等 mihomo 就绪
            r = webapi.apply_saved_node()
            print("[startup] 出口节点:", r, flush=True)
            # 预热出口 IP / 延迟缓存，保证首次打开代理页秒开
            _t.sleep(2)
            webapi.exit_info_warm()
            webapi.delay_of()
            print("[startup] 已预热出口/延迟缓存", flush=True)
        except Exception as e:
            print("[startup] 套用节点失败:", str(e)[:120], flush=True)

    try:
        import threading as _th
        _th.Thread(target=_apply_node, daemon=True).start()
    except Exception:
        pass

    # 常驻监听内置浏览器的导航事件，自动记录 OAuth 回调地址。
    # 授权成功后的 callback 页会瞬间跳走，必须靠事件监听而不是定时轮询。
    def _start_cb_monitor():
        try:
            import time as _t
            import cdpeval
            for _ in range(30):
                if cdpeval.alive():
                    cdpeval.start_monitor()
                    print("[startup] OAuth 回调监听已启动", flush=True)
                    return
                _t.sleep(2)
            print("[startup] 内置浏览器未就绪，回调监听未启动", flush=True)
        except Exception as e:
            print("[startup] 回调监听启动失败:", str(e)[:120], flush=True)

    try:
        import threading as _th2
        _th2.Thread(target=_start_cb_monitor, daemon=True).start()
    except Exception:
        pass

    srv = ThreadingHTTPServer(LISTEN, Handler)
    print(f"gateway listening on http://{LISTEN[0]}:{LISTEN[1]}")
    print(f"  Base URL : http://{LISTEN[0]}:{LISTEN[1]}/v1")
    srv.serve_forever()


if __name__ == "__main__":
    main()
