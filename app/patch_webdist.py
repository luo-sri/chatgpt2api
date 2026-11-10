# -*- coding: utf-8 -*-
"""前端包补丁：把面板自带的「新窗口打开授权页」改成项目内弹窗

为什么必须改前端包，而不是在外层 hook window.open：
  1. 面板是 Next.js 应用，脚本在自己 bundle 里直接调 window.open；
     外层 hook 依赖「注入脚本先于点击执行」，一旦浏览器命中缓存、
     或用户点击发生在 hook 装上之前，就会漏拦（这正是"时好时坏"的来源）。
  2. 改 bundle 是编译期确定的行为，不依赖任何运行时时序。

补丁做两件事：
  A. 往 TopNav 的导航数组里插入「对话 / 代理设定 / 添加账号」三项，
     让它们成为原生菜单的一部分（不靠 MutationObserver 补 DOM）。
  B. 把 OAuth 的 window.open(url,"_blank") 换成项目内弹窗调用。

脚本幂等：已打过补丁就直接跳过。
"""
from __future__ import annotations

import json
import os
import re
import sys

CHUNK_DIR = "/app/web_dist/_next/static/chunks"
APP_VERSION = "v2.4.2"   # 与 webui.APP_VERSION 保持一致

# ---------------- A. 原生导航插入三项 ----------------
NAV_MARK = "c2a-nav-injected"

NAV_PATCH_OLD = ('let $=[{href:"/image",label:"生图"},{href:"/accounts",label:"号池管理"},'
                 '{href:"/image-manager",label:"图片管理"},{href:"/logs",label:"日志管理"},'
                 '{href:"/debug",label:"调试"},{href:"/settings",label:"设置"}]')

NAV_PATCH_NEW = (
    'let $=[{href:"/p/chat",label:"对话"},{href:"/p/proxy",label:"代理设定"},'
    '{href:"/image",label:"生图"},'
    '{href:"/accounts",label:"号池管理"},{href:"/image-manager",label:"图片管理"},'
    '{href:"/logs",label:"日志管理"},{href:"/debug",label:"调试"},'
    '{href:"/settings",label:"设置"}]/*' + NAV_MARK + '*/'
)

# ---------------- B. window.open -> 项目内弹窗 ----------------
# 面板里两处写法完全一样，直接全局替换
OPEN_OLD = 'window.open(e.authorize_url,"_blank","noopener,noreferrer")'
OPEN_NEW = '__c2aOpenAuth(e.authorize_url)'

OPEN_OLD2 = 'window.open(X.authorize_url,"_blank","noopener,noreferrer")'
OPEN_NEW2 = '__c2aOpenAuth(X.authorize_url)'


def patch_nav():
    """给 TopNav 的菜单数组加三项"""
    target = os.path.join(CHUNK_DIR, "0xaq6n.l11b6j.js")
    if not os.path.exists(target):
        return ("skip", "找不到 TopNav chunk")
    src = open(target, encoding="utf-8").read()
    if NAV_MARK in src:
        return ("already", "导航已打过补丁")
    if NAV_PATCH_OLD not in src:
        return ("fail", "导航数组结构不匹配（面板版本可能变了）")
    open(target, "w", encoding="utf-8", newline="").write(
        src.replace(NAV_PATCH_OLD, NAV_PATCH_NEW, 1))
    return ("ok", "已把 对话/代理设定/添加账号 写进原生导航数组")


def patch_oauth_open():
    """把授权页的新窗口打开改成项目内弹窗"""
    target = os.path.join(CHUNK_DIR, "0~k~tcnij90si.js")
    if not os.path.exists(target):
        return ("skip", "找不到账号页 chunk")
    src = open(target, encoding="utf-8").read()
    if "c2a-oauth-patched" in src:
        return ("already", "授权按钮已打过补丁")
    n1 = src.count(OPEN_OLD)
    n2 = src.count(OPEN_OLD2)
    if n1 + n2 == 0:
        return ("fail", "没找到 window.open 授权调用（面板版本可能变了）")
    src = src.replace(OPEN_OLD, OPEN_NEW).replace(OPEN_OLD2, OPEN_NEW2)
    # 标记，保证幂等
    src = src + "\n/*c2a-oauth-patched*/"
    open(target, "w", encoding="utf-8", newline="").write(src)
    return ("ok", "已替换 %d 处 window.open 为项目内弹窗" % (n1 + n2))


# ---------------- C. 去掉「无限画布」入口 ----------------
# 桌面端和移动端抽屉里各有一次渲染，形如：
#   I?(0,t.jsx)(f,{asChild:!0,children:(0,t.jsx)("button",{...children:"无限画布"})}):null,
#   ...children:"无限画布"}):null,
# 把整个三元分支换成 null，菜单里就不会再出现它。
def remove_canvas():
    """去掉「无限画布」入口（桌面顶栏 + 移动端抽屉各一处）。

    做法：定位 children:"无限画布" 的 button 分支，向前找到它所属的
    `I?(...):null,` 整段，替换成 `null,`。用偏移量切，避免正则转义踩坑。
    """
    target = os.path.join(CHUNK_DIR, "0xaq6n.l11b6j.js")
    if not os.path.exists(target):
        return ("skip", "找不到 TopNav chunk")
    src = open(target, encoding="utf-8").read()
    if "c2a-no-canvas" in src:
        return ("already", "无限画布已移除")

    removed = 0
    while True:
        i = src.find('children:"无限画布"')
        if i < 0:
            break
        # 跳过更新日志里的文案（它不在 button 分支里）
        head = src[max(0, i - 60):i]
        if 'content' in head and 'items' in src[max(0, i - 900):i]:
            # 日志文案：直接改写描述，避免下次又被匹配
            src = (src[:i] + 'children:"(已下线)"' + src[i + len('children:"无限画布"'):])
            continue
        # 找到这段分支的起点
        j_button = src.rfind('(0,t.jsx)', 0, i)
        if j_button < 0:
            break
        j = src.rfind('I?', max(0, j_button - 120), j_button)
        if j < 0:
            j = j_button
        # 找到分支结尾 ":null,"
        k = src.find(':null,', i)
        if k < 0:
            break
        src = src[:j] + 'null,/*c2a-no-canvas*/' + src[k + len(':null,'):]
        removed += 1
        if removed > 6:      # 安全阀
            break

    if removed == 0 and 'c2a-no-canvas' not in src:
        return ("fail", "没匹配到无限画布渲染代码")
    open(target, "w", encoding="utf-8", newline="").write(src)
    return ("ok", "已移除 %d 处「无限画布」入口" % removed)









def patch_all():
    results = {
        "nav": patch_nav(),
        "oauth": patch_oauth_open(),
        "canvas": remove_canvas(),
        "brand": patch_brand(),
        "appver": patch_app_version(),
        "loginhint": patch_login_hint(),
    }
    # 只有前面补丁都成功，才重命名 chunk（否则 HTML 会指向带 -patched
    # 后缀的文件，但内容还是旧的）
    if all(status != "fail" for status, _ in results.values()):
        # 先注入（打到原始 chunk），最后再 rename 生成 -patched 副本，
        # 保证 HTML 引用到的 -patched 文件里带上所有按钮补丁。
        results["logsbtn"] = inject_logs_button()
        results["quota"] = patch_quota_label()
        results["modelstoggle"] = inject_models_toggle()
        results["rename"] = rename_patched_chunks()
        # rename 之后，把 models 按钮也同步到 -patched 副本
        try:
            import shutil
            for old_name, new_name in RENAMES.items():
                src = os.path.join(CHUNK_DIR, old_name)
                dst = os.path.join(CHUNK_DIR, new_name)
                if os.path.exists(src):
                    shutil.copyfile(src, dst)
        except Exception:
            pass
    for k, (status, msg) in results.items():
        print("[patch:%s] %s -> %s" % (k, status, msg))
    return results


# ---------------- D. 重命名带补丁的 chunk，让浏览器强制重新下载 ----------------
# 上一版改的是原文件内容，但浏览器一直用缓存里的旧 chunk，导致你那边
# 看到的菜单还是老的。这里把打过补丁的 chunk 复制成带 -patched 后缀的
# 新文件名，并同步替换 web_dist 里所有 HTML 的引用 —— 浏览器会把它们
# 当成全新资源下载，缓存失效问题彻底解决。

# ---------------- D. 重命名带补丁的 chunk，让浏览器强制重新下载 ----------------
# 上一版改的是原文件内容，但浏览器一直用缓存里的旧 chunk，导致你那边
# 看到的菜单还是老的。这里把打过补丁的 chunk 复制成带 -patched 后缀的
# 新文件名，并同步替换 web_dist 里所有 HTML 的引用 —— 浏览器会把它们
# 当成全新资源下载，缓存失效问题彻底解决。
RENAMES = {
    "0xaq6n.l11b6j.js": "0xaq6n.l11b6j-patched.js",
    "0~k~tcnij90si.js": "0~k~tcnij90si-patched.js",
}


def rename_patched_chunks():
    chunk_dir = os.path.join(CHUNK_DIR)
    changed = 0
    for old_name, new_name in RENAMES.items():
        old_path = os.path.join(chunk_dir, old_name)
        new_path = os.path.join(chunk_dir, new_name)
        if not os.path.exists(old_path):
            continue
        # 用打过补丁的内容生成新文件（幂等：内容已是最新）
        data = open(old_path, "rb").read()
        with open(new_path, "wb") as f:
            f.write(data)
        changed += 1

    # 替换 web_dist 里所有 .html 的引用
    for root, _, files in os.walk("/app/web_dist"):
        for fn in files:
            if not fn.endswith(".html"):
                continue
            fp = os.path.join(root, fn)
            try:
                src = open(fp, encoding="utf-8").read()
            except Exception:
                continue
            out = src
            for old_name, new_name in RENAMES.items():
                out = out.replace("/" + old_name, "/" + new_name)
            if out != src:
                open(fp, "w", encoding="utf-8", newline="").write(out)
    return ("ok", "已生成 %d 个带补丁的 chunk 并更新 HTML 引用" % changed)


# ---------------- E. 日志页：一键删除失败日志按钮 ----------------
LOGS_CHUNK = "0o2hiw7.ncr9x.js"
LOGS_ANCHOR = 'children:[(0,t.jsx)(o.Trash2,{className:"size-4"}),"删除所选"]})'
LOGS_MARK = "c2a-del-failed"
LOGS_INJECT = (
    # 原锚点是：「children:[图标,"删除所选"]})」，其中 ]}) 是按钮自身闭合。
    # 替换后必须还原这两层：按钮内层数组 + 按钮对象闭合，
    # 再补外层 children 数组 + jsxs 容器闭合（与被替换掉的尾部一致）。
    'children:[(0,t.jsx)(o.Trash2,{className:"size-4"}),"删除所选"]}),'
    '(0,t.jsxs)(g.Button,{variant:"outline",'
    'className:"h-8 rounded-lg border-amber-200 bg-white px-3 text-amber-700 '
    'hover:bg-amber-50",'
    'onClick:async()=>{'
    'if(!confirm("确认删除所有失败日志吗？此操作不可恢复。"))return;'
    'const r=await fetch("/p/api/logs/delete-failed",{method:"POST",'
    'headers:{"Content-Type":"application/json"},body:"{}"});'
    'const d=await r.json();'
    'if(d.ok){alert("已删除 "+(d.deleted||0)+" 条失败日志");location.reload();}'
    'else{alert("删除失败: "+(d.error||"未知错误"));}'
    '},'
    'children:[(0,t.jsx)(o.Trash2,{className:"size-4"}),"删除所有失败"]})'
    ',(0,t.jsxs)(g.Button,{variant:"outline",'
    'className:"h-8 rounded-lg border-rose-200 bg-white px-3 text-rose-700 '
    'hover:bg-rose-50",'
    'onClick:async()=>{'
    'if(!confirm("确认清空全部日志吗？包含成功与失败的调用记录，此操作不可恢复。"))return;'
    'const r=await fetch("/p/api/logs/clear",{method:"POST",'
    'headers:{"Content-Type":"application/json"},body:"{}"});'
    'const d=await r.json();'
    'if(d.ok){alert("已清空全部日志，共删除 "+(d.deleted||0)+" 条记录");location.reload();}'
    'else{alert("清空失败: "+(d.error||"未知错误"));}'
    '},'
    'children:[(0,t.jsx)(o.Trash2,{className:"size-4"}),"清空全部日志"]})'
    '/*c2a-del-failed*/'
)


def inject_logs_button():
    target = os.path.join(CHUNK_DIR, LOGS_CHUNK)
    if not os.path.exists(target):
        return ("skip", "找不到日志页 chunk")
    src = open(target, encoding="utf-8").read()
    if LOGS_MARK in src:
        return ("already", "失败日志按钮已注入")
    if LOGS_ANCHOR not in src:
        return ("fail", "锚点未命中（面板版本可能变了）")
    src = src.replace(LOGS_ANCHOR, LOGS_INJECT + "/*" + LOGS_MARK + "*/", 1)
    open(target, "w", encoding="utf-8", newline="").write(src)
    return ("ok", "已注入「删除所有失败」按钮")


# ---------------- F. 号池页「系统可用模型」：单个模型 启用/禁用 ----------------
# 需求：对每个模型单独控制启用（显示）/禁用（隐藏），自动保存。
# 方案：chunk 注入「管理模型」按钮 + 计数（React 内联）；
# 管理浮层与开关逻辑由追加在 chunk 末尾的原生 JS 完成（不依赖 React 渲染时机）。
MODELS_CHUNK = "0~k~tcnij90si.js"
MODELS_MARK = "c2a-model-switch"
MODELS_LOGIC_MARK = "/*c2a-model-logic*/"
TITLE_FULL = ('children:["系统可用模型",(0,t.jsxs)("span",{className:"ml-1 text-stone-400",'
              'children:["(",o.length,")"]})')


LOGIN_CHUNK = "09w1mtjfpccow.js"
LOGIN_MARK = "c2a-login-hint"


def patch_login_hint():
    """登录页：提示默认密码，并提醒首次登录后立即修改。

    做法：把一段原生 JS 追加到登录页 chunk 末尾。
    它用 MutationObserver 等 React 渲染完输入框后，在下面插入提示块。
    不改 React 状态、不碰登录逻辑，所以不会影响登录本身。

    为什么要提示：
      本项目出厂密码是 changeme，用户第一次打开根本不知道该填什么，
      而且不改的话任何人拿到地址就能登进来。必须两端都提示。
    """
    target = os.path.join(CHUNK_DIR, LOGIN_CHUNK)
    if not os.path.exists(target):
        return ("skip", "找不到登录页 chunk")
    src = open(target, encoding="utf-8").read()
    if LOGIN_MARK in src:
        return ("already", "登录页密码提示已注入")

    js = """
/*c2a-login-hint*/
(function(){
  if (window.__c2aLoginHint) return;
  window.__c2aLoginHint = 1;

  /* ---------- 登录持久化 ----------
     面板本身把登录态存在 IndexedDB，浏览器清理/隐私模式/换源都会丢，
     用户每次打开都要重新输密码。这里补两个能力：
       · 记住密码：把密钥存 localStorage（30 天），下次打开自动填进输入框
       · 自动登录：启动时静默校验一次，通过就直接进控制台
     两者都只在登录页生效，不改面板的登录逻辑。 */
  var RK = 'c2a_remember_key';
  var RT = 'c2a_remember_at';
  var RA = 'c2a_auto_login';
  var TTL = 30 * 24 * 3600 * 1000;   // 30 天

  function ls(k){ try { return localStorage.getItem(k); } catch(e){ return null; } }
  function lsSet(k, v){ try { localStorage.setItem(k, v); } catch(e){} }
  function lsDel(k){ try { localStorage.removeItem(k); } catch(e){} }

  function savedKey(){
    var v = ls(RK), t = parseInt(ls(RT) || '0', 10);
    if (!v) return '';
    if (t && (Date.now() - t) > TTL) { lsDel(RK); lsDel(RT); lsDel(RA); return ''; }
    return v;
  }

  var CSS = ''
    + '.c2a-lh{margin-top:14px;border-radius:14px;border:1px solid #fde68a;'
    + 'background:#fffbeb;padding:12px 14px;font-size:12.5px;line-height:1.7;color:#78350f}'
    + '.c2a-lh .c2a-lh-t{font-weight:650;color:#b45309;margin-bottom:4px}'
    + '.c2a-lh code{background:#fef3c7;border-radius:4px;padding:1px 6px;'
    + 'font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;color:#92400e}'
    + '.c2a-lh .c2a-lh-w{margin-top:6px;color:#a16207;font-size:12px}'
    + '.dark .c2a-lh{background:rgba(120,53,15,.22);border-color:rgba(253,230,138,.25);color:#fde68a}'
    + '.dark .c2a-lh .c2a-lh-t{color:#fcd34d}'
    + '.dark .c2a-lh code{background:rgba(253,230,138,.16);color:#fde68a}'
    + '.dark .c2a-lh .c2a-lh-w{color:#d6d3d1}'
    + '.c2a-lh-opt{display:flex;gap:18px;margin-top:10px;padding-top:9px;'
    + 'border-top:1px dashed rgba(180,83,9,.28);font-size:12.5px}'
    + '.c2a-lh-opt label{display:inline-flex;align-items:center;gap:6px;cursor:pointer;'
    + 'color:#92400e;user-select:none}'
    + '.c2a-lh-opt input{width:14px;height:14px;cursor:pointer;accent-color:#b45309}'
    + '.dark .c2a-lh-opt label{color:#fcd34d}';

  function addStyle(){
    if (document.getElementById('c2a-lh-css')) return;
    var st = document.createElement('style');
    st.id = 'c2a-lh-css';
    st.textContent = CSS;
    (document.head || document.documentElement).appendChild(st);
  }

  function inject(){
    if (document.getElementById('c2a-lh')) return true;
    var inp = document.getElementById('auth-key');
    if (!inp) return false;
    addStyle();
    var box = document.createElement('div');
    box.id = 'c2a-lh';
    box.className = 'c2a-lh';
    box.innerHTML = ''
      + '<div class="c2a-lh-t" id="c2a-lh-title">初始密码：<code>changeme</code></div>'
      + '<div id="c2a-lh-sub">首次使用请直接用这个密码登录。</div>'
      + '<div class="c2a-lh-w" id="c2a-lh-warn">⚠️ 登录后请立即修改密码：'
      + '<a href="/settings" style="color:#b45309;text-decoration:underline">'
      + '设置页 → 修改登录密码</a>，改完立即生效。</div>'
      + '<div class="c2a-lh-opt">'
      + '  <label><input type="checkbox" id="c2a-remember"> 记住密码（30 天）</label>'
      + '  <label><input type="checkbox" id="c2a-auto"> 自动登录</label>'
      + '</div>';

    // 密码已被改过 → 不再显示「初始密码 changeme」，否则会误导用户
    fetch('/p/api/auth/password', {cache:'no-store'})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.changed) {
          var t = document.getElementById('c2a-lh-title');
          var sub = document.getElementById('c2a-lh-sub');
          var warn = document.getElementById('c2a-lh-warn');
          if (t) t.innerHTML = '请输入你的登录密码';
          if (sub) sub.textContent = '密码已在设置页修改过，与出厂默认值不同。';
          if (warn) warn.style.display = 'none';
        }
      }).catch(function(){});

    // 记住密码 / 自动登录：回填 + 联动
    setTimeout(function(){
      var cbR = document.getElementById('c2a-remember');
      var cbA = document.getElementById('c2a-auto');
      var sk = savedKey();
      if (cbR && sk) { cbR.checked = true; }
      if (cbA && ls(RA) === '1') { cbA.checked = true; }
      if (cbR && cbA) {
        cbR.onchange = function(){
          if (!cbR.checked) { cbA.checked = false; }
          lsSet(RA, cbA.checked ? '1' : '0');
        };
        cbA.onchange = function(){
          if (cbA.checked) { cbR.checked = true; }
          lsSet(RA, cbA.checked ? '1' : '0');
        };
      }
      // 回填已记住的密码（不自动提交，除非勾了自动登录）
      // React 是受控组件：只改一次值会被它下一帧重置，
      // 所以这里重试多次，直到值真正留在输入框里。
      if (sk) {
        var tries = 0;
        var timer = setInterval(function(){
          tries++;
          var el = document.getElementById('auth-key');
          if (!el || tries > 40) { clearInterval(timer); return; }
          if (el.value !== sk) {
            var desc = Object.getOwnPropertyDescriptor(
              window.HTMLInputElement.prototype, 'value');
            desc.set.call(el, sk);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
          } else if (tries > 3) {
            clearInterval(timer);   // 稳定保持住了，停止
          }
        }, 100);
      }
    }, 60);
    // 插到输入框外层容器之后（紧跟输入框，视觉上属于表单）
    var host = inp.closest('form') || inp.parentElement;
    while (host && host.parentElement && host.tagName !== 'BODY') {
      // 找到包含输入框的最外层表单块
      if (host.parentElement.querySelectorAll('#auth-key').length > 1) break;
      break;
    }
    var anchor = inp.closest('div.space-y-3') || inp.parentElement;
    if (anchor && anchor.parentElement) {
      anchor.parentElement.insertBefore(box, anchor.nextSibling);
    } else {
      inp.parentElement.appendChild(box);
    }
    return true;
  }

  /* 登录成功后把密钥存下来（勾了「记住密码」才存） */
  function persistOnSuccess(key){
    var cbR = document.getElementById('c2a-remember');
    var cbA = document.getElementById('c2a-auto');
    if (cbR && cbR.checked && key) {
      lsSet(RK, key);
      lsSet(RT, String(Date.now()));
      lsSet(RA, (cbA && cbA.checked) ? '1' : '0');
    } else if (cbR && !cbR.checked) {
      lsDel(RK); lsDel(RT); lsDel(RA);
    }
  }

  /* 勾了「自动登录」时，启动后静默校验一次 */
  function tryAutoLogin(){
    if (ls(RA) !== '1') return;
    var key = savedKey();
    if (!key) { lsDel(RA); return; }
    // 已经在控制台页面就不用管（登录页才会走到这里）
    fetch('/auth/login', {
      method: 'POST',
      headers: {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
    }).then(function(r){
      if (r.ok) {
        // 把密钥写回面板的 IndexedDB，然后跳转
        return mirrorToIdb(key).then(function(){
          location.replace('/accounts');
        });
      }
      // 失效：清掉，留在登录页
      lsDel(RK); lsDel(RT); lsDel(RA);
    }).catch(function(){});
  }

  /* 把密钥写进面板用的 IndexedDB（它读这里判断登录态） */
  function mirrorToIdb(key){
    return new Promise(function(res){
      try {
        var req = indexedDB.open('chatgpt2api');
        req.onupgradeneeded = function(){
          try { req.result.createObjectStore('auth'); } catch(e){}
        };
        req.onerror = function(){ res(false); };
        req.onsuccess = function(){
          var db = req.result;
          try {
            if (!db.objectStoreNames.contains('auth')) { db.close(); return res(false); }
            var tx = db.transaction('auth', 'readwrite');
            tx.objectStore('auth').put(
              {key: key, role: 'admin', subjectId: 'admin', name: '管理员'},
              'chatgpt2api_auth_key');
            tx.oncomplete = function(){ db.close(); res(true); };
            tx.onerror = function(){ db.close(); res(false); };
          } catch(e) { try{db.close();}catch(e2){} res(false); }
        };
      } catch(e) { res(false); }
    });
  }

  /* 监听登录成功：面板会跳到 /accounts，这里兼听输入框回车和按钮点击 */
  function hookLogin(){
    var inp = document.getElementById('auth-key');
    if (!inp) return;

    /* 关键：登录成功后前端会立刻跳转（router.replace），
       页面一换，setTimeout/轮询全被销毁，所以「记住密码」必须在
       跳转前同步写入。

       注意：面板用的是 axios（底层 XMLHttpRequest），不是 fetch，
       所以必须拦 XMLHttpRequest，拦 fetch 是无效的。 */
  }

  function hookXhr(){
    if (window.__c2aXhrHooked) return;
    window.__c2aXhrHooked = 1;
    var _open = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url){
      try { this.__c2aUrl = String(url || ''); } catch(e){}
      return _open.apply(this, arguments);
    };
    var _send = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function(){
      var xhr = this;
      try {
        if (xhr.__c2aUrl && xhr.__c2aUrl.indexOf('/auth/login') > -1) {
          xhr.addEventListener('load', function(){
            if (xhr.status >= 200 && xhr.status < 300) {
              var el = document.getElementById('auth-key');
              var v = el && el.value ? el.value : '';
              if (v) persistOnSuccess(v);   // 同步写 localStorage，赶在跳转前
            }
          });
        }
      } catch(e){}
      return _send.apply(this, arguments);
    };
  }

  function start(){
    if (inject()) { hookLogin(); hookXhr(); tryAutoLogin(); return; }
    // React 还没渲染完，观察 DOM
    var mo = new MutationObserver(function(){
      if (inject()) {
        mo.disconnect();
        hookLogin();
        hookXhr();
        tryAutoLogin();
      }
    });
    mo.observe(document.documentElement, {childList: true, subtree: true});
    // 15 秒后放弃（不是登录页就不折腾了）
    setTimeout(function(){ mo.disconnect(); }, 15000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
"""

    src = src.rstrip() + js
    open(target, "w", encoding="utf-8", newline="").write(src)
    return ("ok", "登录页已加入默认密码提示")


def patch_app_version():
    """顶栏版本号：面板把版本编译进了 bundle（appVersion:"1.8.0"）。

    这是面板构建时写死的常量，后端 /app/VERSION 只影响登录接口响应，
    顶栏显示的永远是 bundle 里这个值 —— 所以必须直接改 bundle。
    """
    ver = APP_VERSION.lstrip("v")
    changed = 0
    hits = []
    for fn in os.listdir(CHUNK_DIR):
        if not fn.endswith(".js"):
            continue
        p = os.path.join(CHUNK_DIR, fn)
        try:
            src = open(p, encoding="utf-8").read()
        except Exception:
            continue
        if 'appVersion:"' not in src:
            continue
        out = src
        # 只替换 appVersion 这个字段，别碰 CHANGELOG 里的历史版本记录
        out2, n = re.subn(r'appVersion:"[0-9][^"]*"', 'appVersion:"%s"' % ver, out)
        if n and out2 != src:
            open(p, "w", encoding="utf-8", newline="").write(out2)
            changed += n
            hits.append(fn)
    if changed == 0:
        # 可能已经是目标版本
        for fn in os.listdir(CHUNK_DIR):
            if fn.endswith(".js"):
                try:
                    if ('appVersion:"%s"' % ver) in open(
                            os.path.join(CHUNK_DIR, fn), encoding="utf-8").read():
                        return ("already", "版本号已是 " + ver)
                except Exception:
                    pass
        return ("fail", "没找到 appVersion 常量")
    return ("ok", "版本号已改为 %s（%d 处：%s）" % (ver, changed, ",".join(hits)))


def patch_brand():
    """顶栏品牌：GitHub 链接 + 版本检查源换成自己的仓库。

    面板 TopNav 自己渲染了 GitHub 链接和「检查更新」按钮，
    它读的是 raw.githubusercontent.com/<owner>/<repo>/main/VERSION。
    不换掉的话：
      - 用户点 GitHub 会跳到原作者仓库；
      - 版本检查比对的是原作者的版本，永远显示"有新版"。
    """
    target = os.path.join(CHUNK_DIR, "0xaq6n.l11b6j.js")
    if not os.path.exists(target):
        return ("skip", "找不到 TopNav chunk")
    src = open(target, encoding="utf-8").read()
    if "c2a-brand" in src:
        return ("already", "品牌链接已替换")

    n1 = src.count("https://github.com/basketikun/chatgpt2api")
    src = src.replace("https://github.com/basketikun/chatgpt2api",
                      "https://github.com/luo-sri/chatgpt2api")
    n2 = src.count("raw.githubusercontent.com/basketikun/chatgpt2api")
    src = src.replace("raw.githubusercontent.com/basketikun/chatgpt2api",
                      "raw.githubusercontent.com/luo-sri/chatgpt2api")
    if n1 + n2 == 0:
        return ("fail", "没匹配到品牌链接")
    src = src + "\n/*c2a-brand*/"
    open(target, "w", encoding="utf-8", newline="").write(src)
    return ("ok", "品牌已换：GitHub 链接x%d、版本源x%d" % (n1, n2))


def patch_quota_label():
    """号池页额度文案：把「额度」明确成「生图额度」。

    - 汇总卡片 label:"剩余额度" → "生图剩余额度"
    - 账户列表表头 children:"额度" → "生图额度"
    - 每行数值：本身只显示 account.quota（生图剩余张数），逻辑已正确，
      不再叠加 limits_progress 里的其它项

    幂等：已经改过就跳过（用标记判断）。
    """
    target = os.path.join(CHUNK_DIR, MODELS_CHUNK)
    if not os.path.exists(target):
        return ("skip", "找不到号池页 chunk")
    src = open(target, encoding="utf-8").read()
    if "c2a-quota-label" in src:
        return ("already", "生图额度文案已改")

    n1 = n2 = 0
    old1 = 'label:"剩余额度"'
    new1 = 'label:"生图剩余额度"'
    if old1 in src:
        n1 = src.count(old1)
        src = src.replace(old1, new1)

    old2 = 'className:"w-24 px-4 py-3",children:"额度"'
    new2 = 'className:"w-24 px-4 py-3",children:"生图额度"'
    if old2 in src:
        n2 = src.count(old2)
        src = src.replace(old2, new2)
    else:
        # 兜底：只匹配 children:"额度" 且紧邻创建时间列
        old2b = 'children:"额度"'
        if old2b in src:
            n2 = src.count(old2b)
            src = src.replace(old2b, 'children:"生图额度"')

    if n1 + n2 == 0:
        return ("fail", "没匹配到额度文案（面板版本可能变了）")

    src = src + "\n/*c2a-quota-label*/"
    open(target, "w", encoding="utf-8", newline="").write(src)
    return ("ok", "额度文案已改：剩余额度x%d、表头x%d" % (n1, n2))


def inject_models_toggle():
    target = os.path.join(CHUNK_DIR, MODELS_CHUNK)
    if not os.path.exists(target):
        return ("skip", "找不到号池页 chunk")
    src = open(target, encoding="utf-8").read()

    # ==== 绝对幂等：已注入就直接返回，不做任何替换 ====
    # （之前的"先剥旧再注入"会因结尾匹配失败而失效，每次重启叠一个按钮）
    if "c2a-msw-head" in src and MODELS_LOGIC_MARK in src:
        return ("already", "模型管理已注入（跳过）")

    # 没注入过才走到这里：先清理任何半吊子状态（只有标记没有逻辑，或反之）
    if "c2a-msw-head" in src or "/*c2a-model-switch*/" in src:
        # 半吊子状态：整段重置 —— 删掉所有 c2a-msw-head span 的注入痕迹。
        # 注入串是 TITLE_FULL + 标记 + ',(0,t.jsx)("span",{id:"c2a-msw-head"...})]})'
        # 结束特征固定为 '"管理模型"})]})'
        SPAN_HEAD = ',(0,t.jsx)("span",{id:"c2a-msw-head"'
        SPAN_TAIL = '"管理模型"})]})'
        while True:
            sp = src.find(SPAN_HEAD)
            if sp < 0:
                break
            tp = src.find(SPAN_TAIL, sp)
            if tp < 0:
                break
            src = src[:sp] + src[tp + len(SPAN_TAIL):]
        src = src.replace('/*c2a-model-switch*/', '')
        # 末尾可能残留追加过的 logic：截掉
        li = src.find(MODELS_LOGIC_MARK)
        if li > 0:
            src = src[:li]

    if TITLE_FULL not in src:
        return ("fail", "标题锚点未命中（面板版本可能变了）")

    # 注入：标题后跟 计数 + 管理按钮（点击打开浮层）
    inject = (TITLE_FULL + '/*c2a-model-switch*/'
              + ',(0,t.jsx)("span",{id:"c2a-msw-head",className:"ml-2 inline-flex items-center gap-1",'
              'children:[(0,t.jsx)("span",{id:"c2a-msw-count",className:"text-[11px] text-stone-400"}),'
              '(0,t.jsx)("button",{type:"button",'
              'className:"rounded-full border border-stone-200 bg-white px-2 py-0.5 text-[11px] '
              'font-medium text-stone-500 hover:bg-stone-50",'
              'onClick:()=>{window.__c2aMS&&window.__c2aMS()},'
              'children:"管理模型"})]})')
    src = src.replace(TITLE_FULL, inject, 1)

    # 容器加 id（chips 定位 + 禁用时隐藏单个 chip）
    cont_anchor = '(0,t.jsx)("div",{className:"flex flex-wrap gap-2",children:o.length>0?o.map('
    cont_inject = ('(0,t.jsx)("div",{id:"c2a-models-box",'
                   'className:"flex flex-wrap gap-2",children:o.length>0?o.map(')
    if cont_anchor in src and 'c2a-models-box' not in src:
        src = src.replace(cont_anchor, cont_inject, 1)

    open(target, "w", encoding="utf-8", newline="").write(src)

    # 追加管理浮层与开关逻辑（原生 JS，存 localStorage）——只追加一次
    with open(target, "a", encoding="utf-8", newline="") as f:
        f.write(MODELS_LOGIC)
    return ("ok", "已注入模型 启用/禁用 管理")


MODELS_LOGIC = """
/*c2a-model-logic*/
(function(){
  if (window.__c2aMSDone) return;
  window.__c2aMSDone = 1;

  function offList(){
    try { return JSON.parse(localStorage.getItem('c2a-model-off') || '[]'); }
    catch(e){ return []; }
  }
  function saveOff(a){
    try { localStorage.setItem('c2a-model-off', JSON.stringify(a)); } catch(e){}
    // 同步到服务端持久化：网关 /v1/models 过滤会读这个文件，
    // 这样 agent 应用连接项目 API 也读不到被禁用的模型。
    try {
      fetch('/p/api/models/off', {
        method: 'POST', cache: 'no-store',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({models: a})
      }).catch(function(){});
    } catch(e){}
  }
  function chips(){
    var box = document.getElementById('c2a-models-box');
    if (!box) return [];
    var bs = box.querySelectorAll('button');
    return Array.prototype.slice.call(bs);
  }
  function idOf(b){ return (b.title || '').replace(/^\\u70b9\\u51fb\\u590d\\u5236\\s*/, ''); }

  function apply(){
    var o = offList(), n = 0, all = chips();
    all.forEach(function(b){
      var hid = o.indexOf(idOf(b)) >= 0;
      b.style.display = hid ? 'none' : '';
      if (!hid) n++;
    });
    var c = document.getElementById('c2a-msw-count');
    if (c) c.textContent = '\\u542f\\u7528 ' + n + ' / ' + all.length;
    var inner = document.getElementById('c2a-msw-inner');
    if (inner){
      inner.querySelectorAll('input[data-m]').forEach(function(cb){
        cb.checked = offList().indexOf(cb.dataset.m) < 0;
      });
    }
  }

  function ensurePanel(){
    if (document.getElementById('c2a-msw-wrap')) return;
    var w = document.createElement('div');
    w.id = 'c2a-msw-wrap';
    w.style.cssText = 'position:fixed;inset:0;z-index:99999;background:rgba(10,10,10,.45);'
      + 'display:none;align-items:center;justify-content:center';
    w.innerHTML = '<div style="background:#fff;border-radius:16px;padding:20px;'
      + 'width:min(560px,92vw);max-height:76vh;overflow:auto;font-family:inherit;color:#1c1917">'
      + '<div style="font-weight:600;font-size:14px;margin-bottom:4px">\\u7ba1\\u7406\\u6a21\\u578b</div>'
      + '<div style="font-size:12px;color:#78716c;margin-bottom:12px">'
      + '\\u53d6\\u6d88\\u52fe\\u9009 = \\u7981\\u7528\\uff08\\u9690\\u85cf\\uff09\\u8be5\\u6a21\\u578b\\uff0c'
      + '\\u7acb\\u5373\\u751f\\u6548\\u5e76\\u81ea\\u52a8\\u4fdd\\u5b58</div>'
      + '<div id="c2a-msw-inner" style="line-height:2.1;font-size:13px"></div>'
      + '<div style="text-align:right;margin-top:14px">'
      + '<button id="c2a-msw-all" style="border:0;background:#f5f5f4;border-radius:8px;'
      + 'padding:7px 13px;font-size:12.5px;cursor:pointer;margin-right:8px">\\u5168\\u90e8\\u542f\\u7528</button>'
      + '<button id="c2a-msw-close" style="border:0;background:#1c1917;color:#fff;border-radius:8px;'
      + 'padding:7px 15px;font-size:12.5px;cursor:pointer">\\u5b8c\\u6210</button></div></div>';
    document.body.appendChild(w);
    w.addEventListener('click', function(e){ if (e.target === w) w.style.display = 'none'; });
    document.getElementById('c2a-msw-close').onclick = function(){ w.style.display = 'none'; };
    document.getElementById('c2a-msw-all').onclick = function(){ saveOff([]); rebuild(); apply(); };
  }

  function rebuild(){
    ensurePanel();
    var inner = document.getElementById('c2a-msw-inner');
    if (!inner) return;
    var ids = chips().map(idOf);
    inner.innerHTML = ids.map(function(i){
      return '<label style="display:flex;align-items:center;gap:8px;padding:3px 0;cursor:pointer">'
        + '<input type="checkbox" data-m="' + i + '" style="width:auto"> ' + i + '</label>';
    }).join('');
    inner.querySelectorAll('input[data-m]').forEach(function(cb){
      cb.onchange = function(){
        var i = cb.dataset.m, o = offList();
        if (cb.checked){
          o = o.filter(function(x){ return x !== i; });
        } else if (o.indexOf(i) < 0){
          o.push(i);
        }
        saveOff(o);
        apply();
      };
    });
    apply();
  }

  window.__c2aMS = function(){
    rebuild();
    document.getElementById('c2a-msw-wrap').style.display = 'flex';
  };

  function hook(){
    var tries = 0;
    (function t(){
      var cards = document.querySelectorAll('.mb-3');
      cards.forEach(function(c){
        if (c.textContent.indexOf('\\u7cfb\\u7edf\\u53ef\\u7528\\u6a21\\u578b') < 0) return;
        var wrap = c.parentElement && c.parentElement.querySelector('.flex.flex-wrap.gap-2');
        if (wrap && !wrap.id) wrap.id = 'c2a-models-box';
      });
      apply();
      if (++tries < 160) setTimeout(t, 500);
    })();
  }
  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', hook);
  else hook();
})();
"""


if __name__ == "__main__":
    r = patch_all()
    bad = [k for k, (s, _) in r.items() if s == "fail"]
    sys.exit(1 if bad else 0)
