# -*- coding: utf-8 -*-
"""首次使用新手引导

设计目标：
  用户第一次打开控制台时，不要面对一堆陌生菜单发呆。
  用 5 步引导把「能跑起来」的最短路径讲清楚：
    欢迎 → 确认代理节点 → 添加账号 → 拿 API Key → 接客户端

实现方式：
  纯前端浮层 + localStorage 记忆，不侵入面板代码。
  注入到所有页面（跟在 VERSION_JS 后面），
  只在「从未完成过引导」且「当前在首页/对话页」时弹出。
  用户可以随时点「跳过」，也可以在设置页手动重看（localStorage 清 key）。

为什么不做成后端状态：
  引导是「这台浏览器有没有看过」，不是「这个服务有没有被配置过」。
  用后端状态会导致同一台机器换个浏览器又弹一次，体验更差。
"""
import json

ONBOARDING_JS = """<script>
(function(){
  var LS_KEY = 'c2a_onboarding_done_v2';
  var LS_STEP = 'c2a_onboarding_step';

  /* 「是否看过引导」以后端为准（/app/data/onboarding.json）。
     原因：localStorage 按「源」隔离，192.168.x.x / 域名 / 127.0.0.1 各算一个源，
     同一台服务器换地址访问就会又弹一次。后端记一次就够了。
     localStorage 仅作旧版本兼容缓存。 */
  var serverDone = null;      // null=还没查过

  function lsDone(){
    try{ return localStorage.getItem(LS_KEY) === '1'; }catch(e){ return false; }
  }

  function done(){ return serverDone === null ? lsDone() : serverDone; }

  function fetchServer(){
    return fetch('/p/api/onboarding', {cache:'no-store'})
      .then(function(r){ return r.json(); })
      .then(function(d){
        serverDone = !!(d && d.done);
        // 老用户：后端没记但本地标记过 → 视为已完成，并补写后端
        if (!serverDone && lsDone()){
          serverDone = true;
          fetch('/p/api/onboarding', {method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({done:true})}).catch(function(){});
        }
        return serverDone;
      })
      .catch(function(){ serverDone = lsDone(); return serverDone; });
  }

  function markDone(){
    serverDone = true;
    try{ localStorage.setItem(LS_KEY, '1'); }catch(e){}
    fetch('/p/api/onboarding', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({done:true})}).catch(function(){});
  }
  function getStep(){ try{ return parseInt(localStorage.getItem(LS_STEP) || '0', 10) || 0; }catch(e){ return 0; } }
  function setStep(n){ try{ localStorage.setItem(LS_STEP, String(n)); }catch(e){} }

  var STEPS = [
    {
      icon: '👋',
      title: '欢迎使用 ChatGPT2API',
      body: '这个面板把 ChatGPT 网页版账号，变成任何客户端都能用的标准 OpenAI 接口。<br><br>'
          + '接下来用 4 步带你跑通：<b>确认节点 → 添加账号 → 拿 API Key → 接客户端</b>。<br>'
          + '全程大约 3 分钟，随时可以点「跳过」。'
    },
    {
      icon: '🌐',
      title: '第 1 步：确认代理节点',
      body: '项目内置代理内核，所有对 ChatGPT 的请求都走代理。<br><br>'
          + '打开左侧「<b>代理设定</b>」，确认当前节点是<b>美国</b>或<b>日本</b>，'
          + '下方能看到出口 IP 和地区就说明代理正常。<br><br>'
          + '<span style="color:#78716c">节点是纯手动选择的，选完就会锁定，不会自己跳来跳去。</span>',
      action: {href: '/p/proxy/', label: '去代理设定页'}
    },
    {
      icon: '👤',
      title: '第 2 步：添加一个账号',
      body: '没有账号，API 就没有「人」可以借用，调用会失败。<br><br>'
          + '打开「<b>号池管理</b>」→ 右上角「<b>导入</b>」→「<b>OAuth 登录已有账号</b>」→ '
          + '点「打开授权页面」。<br><br>'
          + '会弹出一个内置浏览器窗口，在里面正常登录 ChatGPT 就行。'
          + '<b>登录成功后什么都不用做</b>，账号会自动加进来。',
      action: {href: '/accounts/', label: '去号池管理'}
    },
    {
      icon: '🔑',
      title: '第 3 步：拿到你的 API Key',
      body: '第三方客户端需要一个 <code>sk-<</code>code> 开头的密钥。<br><br>'
          + '打开「<b>设置</b>」页面，找到 <b>API Key</b> 那一项，复制它。<br><br>'
          + '<span style="color:#b45309">注意：登录面板用的密码和这个 API Key 是两回事，'
          + '客户端里要填的是 sk- 开头的这个。</span>',
      action: {href: '/settings/', label: '去设置页拿 Key'}
    },
    {
      icon: '🚀',
      title: '第 4 步：接上你的客户端',
      body: '在任意支持 OpenAI 的客户端里填两项：<br><br>'
          + '<div style="background:#f5f5f4;border-radius:8px;padding:10px 12px;'
          + 'font-family:ui-monospace,monospace;font-size:12.5px;line-height:1.9">'
          + 'Base URL：<b>http://' + (location.hostname || '127.0.0.1') + ':3100/v1</b><br>'
          + 'API Key：<b>sk-</b> 开头的那一串' + DIV_END + '<br>'
          + '推荐的客户端：Cherry Studio、ChatBox、Cline、Dify 等。<br><br>'
          + '想先验证通不通？直接用左侧「<b>对话</b>」页发一句话试试。',
      action: {href: '/p/chat/', label: '去对话页试试'}
    }
  ];

  var DIV_END = '</' + 'div>';
  var CODE_END = '</' + 'code>';
  var cur = 0, mask = null;

  function css(){
    if (document.getElementById('c2a-onb-css')) return;
    var st = document.createElement('style');
    st.id = 'c2a-onb-css';
    st.textContent = ''
      + '.c2a-onb-mask{position:fixed;inset:0;z-index:2147483001;background:rgba(15,12,10,.55);'
      + 'display:flex;align-items:center;justify-content:center;padding:20px;'
      + 'backdrop-filter:blur(2px)}'
      + '.c2a-onb-card{width:min(560px,94vw);background:#fff;border-radius:18px;'
      + 'box-shadow:0 30px 80px -20px rgba(0,0,0,.45);overflow:hidden;'
      + 'font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}'
      + '.c2a-onb-head{display:flex;align-items:center;gap:12px;padding:22px 26px 0}'
      + '.c2a-onb-ico{width:44px;height:44px;border-radius:14px;background:#f5f5f4;'
      + 'display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0}'
      + '.c2a-onb-title{font-size:17px;font-weight:650;color:#1c1917;letter-spacing:-.01em}'
      + '.c2a-onb-body{padding:14px 26px 6px;font-size:13.5px;line-height:1.75;color:#44403c}'
      + '.c2a-onb-body code{background:#f5f5f4;padding:2px 5px;border-radius:4px;'
      + 'font-size:12.5px;font-family:ui-monospace,monospace}'
      + '.c2a-onb-foot{display:flex;align-items:center;gap:10px;padding:16px 26px 22px}'
      + '.c2a-onb-dots{display:flex;gap:6px;flex:1}'
      + '.c2a-onb-dot{width:6px;height:6px;border-radius:50%;background:#e7e5e4}'
      + '.c2a-onb-dot.on{background:#1c1917;width:18px;border-radius:3px}'
      + '.c2a-onb-btn{border:0;border-radius:10px;padding:9px 16px;font-size:13px;'
      + 'cursor:pointer;font-family:inherit;transition:all .15s}'
      + '.c2a-onb-primary{background:#1c1917;color:#fff}'
      + '.c2a-onb-primary:hover{background:#292524}'
      + '.c2a-onb-ghost{background:transparent;color:#78716c}'
      + '.c2a-onb-ghost:hover{color:#1c1917;background:#f5f5f4}'
      + '.c2a-onb-link{background:#f5f5f4;color:#1c1917;text-decoration:none;'
      + 'border-radius:10px;padding:9px 14px;font-size:13px;display:inline-block}'
      + '.c2a-onb-link:hover{background:#e7e5e4}'
      + '.dark .c2a-onb-card{background:#1c1917}'
      + '.dark .c2a-onb-title{color:#f5f5f4}'
      + '.dark .c2a-onb-body{color:#d6d3d1}'
      + '.dark .c2a-onb-ico{background:#292524}'
      + '.dark .c2a-onb-body code{background:#292524;color:#e7e5e4}'
      + '.dark .c2a-onb-primary{background:#f5f5f4;color:#1c1917}'
      + '.dark .c2a-onb-ghost{color:#a8a29e}'
      + '.dark .c2a-onb-ghost:hover{background:#292524;color:#f5f5f4}'
      + '.dark .c2a-onb-link{background:#292524;color:#f5f5f4}'
      + '.dark .c2a-onb-dot{background:#44403c}'
      + '.dark .c2a-onb-dot.on{background:#f5f5f4}';
    (document.head || document.documentElement).appendChild(st);
  }

  function render(){
    css();
    if (!mask){
      mask = document.createElement('div');
      mask.className = 'c2a-onb-mask';
      document.body.appendChild(mask);
    }
    var s = STEPS[cur];
    var dots = '';
    for (var i = 0; i < STEPS.length; i++){
      dots += '<span class="c2a-onb-dot' + (i === cur ? ' on' : '') + '"></span>';
    }
    var last = cur === STEPS.length - 1;
    mask.innerHTML = '<div class="c2a-onb-card">'
      + '<div class="c2a-onb-head"><div class="c2a-onb-ico">' + s.icon + DIV_END
      + '<div class="c2a-onb-title">' + s.title + '' + DIV_END + '' + DIV_END + ''
      + '<div class="c2a-onb-body">' + s.body + DIV_END
      + '<div class="c2a-onb-foot">'
      + '<div class="c2a-onb-dots">' + dots + DIV_END
      + (cur > 0 ? '<button class="c2a-onb-btn c2a-onb-ghost" data-nav="prev">上一步</button>' : '')
      + (s.action && !last ? '<a class="c2a-onb-link" href="' + s.action.href + '" data-nav="go">'
         + s.action.label + '</a>' : '')
      + (last ? '<button class="c2a-onb-btn c2a-onb-ghost" data-nav="first">从头再看</button>' : '')
      + '<button class="c2a-onb-btn c2a-onb-primary" data-nav="next">'
      + (last ? '开始使用' : '下一步') + '</button>'
      + '' + DIV_END + '' + DIV_END + '';

    var nav = mask.querySelectorAll('[data-nav]');
    for (var k = 0; k < nav.length; k++){
      nav[k].onclick = function(e){
        var a = this.getAttribute('data-nav');
        if (a === 'next'){
          if (last){ close(); }
          else { cur++; setStep(cur); render(); }
        } else if (a === 'prev'){
          if (cur > 0){ cur--; setStep(cur); render(); }
        } else if (a === 'first'){
          cur = 0; setStep(0); render();
        } else if (a === 'go'){
          // 跳页面前记下进度，回来还能接着看
          setStep(cur);
        }
      };
    }
    // 点遮罩空白处也关闭
    mask.onclick = function(e){ if (e.target === mask) close(); };
  }

  function close(){
    markDone();
    try{ localStorage.removeItem(LS_STEP); }catch(e){}
    if (mask){ try{ mask.remove(); }catch(e){} mask = null; }
  }

  function start(force){
    if (!force && done()) return;
    cur = force ? 0 : Math.min(getStep(), STEPS.length - 1);
    render();
  }

  // 给「重新查看引导」留个入口
  window.__c2aOnboarding = function(){ start(true); };

  /* 判断是否已登录：面板把登录态存在 IndexedDB 的 chatgpt2api/auth 库。
     未登录时打开项目，应该只看登录页，不该弹引导。 */
  function loggedIn(cb){
    var path = location.pathname;
    // 登录相关页面一律不弹
    if (path.indexOf('/login') === 0) { cb(false); return; }
    try {
      var req = indexedDB.open('chatgpt2api');
      req.onupgradeneeded = function(){ try { req.transaction.abort(); } catch(e){} cb(false); };
      req.onerror = function(){ cb(false); };
      req.onsuccess = function(){
        var db = req.result;
        try {
          if (!db.objectStoreNames.contains('auth')) { db.close(); cb(false); return; }
          var g = db.transaction('auth').objectStore('auth').get('chatgpt2api_auth_key');
          g.onsuccess = function(){
            var v = g.result;
            db.close();
            // 有 key 且非空才算登录
            cb(!!(v && (v.key || (typeof v === 'string' ? v : ''))));
          };
          g.onerror = function(){ db.close(); cb(false); };
        } catch (e) { try { db.close(); } catch(e2){} cb(false); }
      };
    } catch (e) { cb(false); }
  }

  function maybeAutoStart(tries){
    tries = tries || 0;
    loggedIn(function(ok){
      if (ok) {
        fetchServer().then(function(isDone){
          if (!isDone) setTimeout(function(){ start(false); }, 600);
        });
        return;
      }
      // 未登录：等用户登录完（最多等 60 秒，每 1.5 秒看一次）
      if (tries < 40) setTimeout(function(){ maybeAutoStart(tries + 1); }, 1500);
    });
  }

  document.addEventListener('DOMContentLoaded', function(){
    // 只在首页和对话页自动弹，避免在设置/日志页打断操作
    var p = location.pathname;
    var auto = (p === '/' || p === '/p/chat' || p === '/p/chat/');
    if (auto){
      maybeAutoStart(0);
    }
  });
})();
</script>"""


def onboarding_script():
    return ONBOARDING_JS
