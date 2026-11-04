# -*- coding: utf-8 -*-
"""授权转发代理

问题：添加账号要在浏览器里打开 OpenAI 授权页，而本机不开代理时打不开。
方案：在本机起一个 HTTP 代理，所有流量转给容器内的 mihomo（7890），
      用户浏览器设这个代理即可打开授权页 —— 本机全局代理不用开。

同时提供一个「一键授权」页面：
  /p/api/oauth/start  让容器后端生成授权 URL
  页面里用 iframe 打开（受 X-Frame 限制时改为新窗口）
  用户完成登录后，页面自动捕获回调 URL 并回传
"""
import json
import urllib.parse


OAUTH_PAGE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>添加账号</title>
<style>
:root{
  --c-bg:#ffffff; --c-bg2:#f5f5f4; --c-card:#ffffff;
  --c-line:#e7e5e4; --c-line2:#d6d3d1;
  --c-fg:#1c1917; --c-fg2:#57534e; --c-fg3:#78716c;
  --c-acc:#b45309; --c-acc2:#92400e; --c-accbg:#fef3c7;
  --c-btn2:#e7e5e4;
}
html[data-c2a="dark"]{
  --c-bg:#0b0d12; --c-bg2:#1a1d27; --c-card:#12151d;
  --c-line:#232634; --c-line2:#2a2d3a;
  --c-fg:#e2e8f0; --c-fg2:#94a3b8; --c-fg3:#64748b;
  --c-acc:#a5b4fc; --c-acc2:#c7d2fe; --c-accbg:#312e81;
  --c-btn2:#334155;
}

*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"SF Pro Display","SF Pro Text","PingFang SC","Microsoft YaHei",
     "Helvetica Neue",sans-serif;
     background:var(--c-bg);color:var(--c-fg);padding:26px;line-height:1.7}
:root{--c-bg:radial-gradient(circle at top left,rgba(255,255,255,0.92),rgba(245,239,231,0.96) 42%,rgba(240,235,227,0.99) 100%)}
html[data-c2a="dark"]{--c-bg:radial-gradient(circle at top left,rgba(55,48,43,0.72),rgba(28,25,23,0.98) 40%,rgba(12,10,9,1) 100%)}
.wrap{max-width:860px;margin:0 auto}
h2{font-size:17px;color:var(--c-acc);margin-bottom:8px}
.sub{color:var(--c-fg2);font-size:13px;margin-bottom:20px}
.card{background:var(--c-card);border:1px solid var(--c-line);border-radius:12px;padding:18px;margin-bottom:16px}
.step{display:flex;gap:12px;margin-bottom:14px}
.num{width:24px;height:24px;border-radius:50%;background:var(--c-accbg);color:var(--c-acc2);
     display:flex;align-items:center;justify-content:center;font-size:12px;
     font-weight:700;flex-shrink:0}
.body{flex:1;font-size:13.5px}
.body b{color:var(--c-acc2)}
button{background:#4f46e5;color:#fff;border:0;border-radius:8px;padding:10px 18px;
       font-size:13.5px;cursor:pointer;font-family:inherit;margin-top:8px}
button:hover{background:#4338ca}
button:disabled{background:var(--c-btn2);color:var(--c-fg3);cursor:not-allowed}
button.gray{background:var(--c-btn2);color:var(--c-fg)}
button.gray:hover{background:var(--c-line2);color:var(--c-fg)}
input,textarea{width:100%;background:var(--c-bg);border:1px solid var(--c-line2);color:var(--c-fg);
               border-radius:8px;padding:10px;font-size:13px;
               font-family:ui-monospace,monospace;margin-top:8px}
.ok{color:#22c55e}.bad{color:#ef4444}.mut{color:var(--c-fg3)}
code{background:var(--c-bg2);padding:2px 6px;border-radius:4px;font-size:12.5px}
.proxybox{background:var(--c-bg2);border-radius:8px;padding:12px;font-family:ui-monospace,monospace;
          font-size:13px;margin-top:10px;color:#86efac}
#log{margin-top:12px;font-size:12.5px;color:var(--c-fg2);white-space:pre-wrap;
     max-height:180px;overflow:auto}
.c2a-bar{display:flex;align-items:center;gap:14px;padding:9px 18px;background:var(--c-card);
  border-bottom:1px solid var(--c-line);font-size:13px;flex-shrink:0}
.c2a-bar a{color:var(--c-fg2);text-decoration:none;white-space:nowrap}
.c2a-bar a:hover{color:var(--c-acc2);text-decoration:underline}
.c2a-bar .c2a-tip{font-size:11.5px;color:var(--c-fg3);white-space:nowrap}
</style></head><body><div class="c2a-bar">
  <a href="/">← 返回控制台</a>
  <a href="/p/chat">对话</a>
  <a href="/p/proxy">代理设定</a>
  <a href="/p/oauth">添加账号</a>
  <a href="/accounts">号池管理</a>
  <span style="flex:1"></span>
  <span class="c2a-tip">内置浏览器请开 http://localhost:6080</span>
</div>

<div class="wrap">
  <h2>添加 ChatGPT 账号</h2>
  <div class="sub">授权页会经过容器代理打开，你本机<b>不需要</b>开启任何代理。</div>

  <div class="card">
    <div class="step"><div class="num">1</div><div class="body">
      <b>打开内置浏览器</b>（在容器里运行，自带代理，本机无需开任何代理）
      <div style="margin-top:8px">
        <button onclick="openBuiltin()">打开内置浏览器</button>
        <button class="gray" onclick="copyProxy()">复制备用代理地址</button>
      </div>
      <div class="proxybox" style="display:none">HTTP 代理： <span id="proxyaddr">127.0.0.1:8888</span></div>
      <div class="mut" style="font-size:12px;margin-top:8px">
        内置浏览器打开的是容器里的 Chromium，它的流量走容器代理，<br>
        所以即使你本机完全不开代理，也能正常登录 OpenAI。
      </div>
    </div></div>

    <div class="step"><div class="num">2</div><div class="body">
      <b>点击生成授权链接并打开</b>
      <div class="mut" style="font-size:12px;margin:4px 0 2px">
        授权页会在<b>容器内置的浏览器</b>里打开，不会弹到你的本机浏览器。
      </div>
      <div style="margin-top:8px"><button id="startbtn" onclick="startAuth()">生成并打开授权页</button></div>
      <div id="startmsg" style="margin-top:8px"></div>
      <div id="urlline" style="display:none;margin-top:10px">
        <div class="mut" style="font-size:12px;margin-bottom:4px">授权链接（可在内置浏览器地址栏粘贴）：</div>
        <textarea id="authurl" rows="2" readonly onclick="this.select()"></textarea>
        <button class="gray" onclick="copyUrl()">复制链接</button>
      </div>
    </div></div>

    <div class="step"><div class="num">3</div><div class="body">
      <b>登录完成后，把浏览器地址栏的整条链接粘贴回来</b>
      <div class="mut" style="font-size:12px;margin-top:4px">
        地址应该以 <code>https://platform.openai.com/auth/callback?code=...</code> 开头。
        如果页面白屏或报错，直接复制地址栏内容即可。
      </div>
      <textarea id="callback" rows="3" placeholder="https://platform.openai.com/auth/callback?code=...&state=..."></textarea>
      <button onclick="autoFinish(0)">自动完成添加（推荐）</button>
      <button class="gray" onclick="autoFetchCallback()">仅获取回调地址</button>
      <button onclick="finishAuth()">提交并完成添加</button>
      <div class="mut" style="font-size:12px;margin-top:8px">
        内置浏览器的剪贴板和本机<b>不互通</b>，不需要复制粘贴：
        点「自动完成添加」，服务端会直接读浏览器里的回调地址并兑换 token。
        如果还在登录中，点它之后会等待约 8 秒。
      </div>
      <div id="finishmsg" style="margin-top:8px"></div>
    </div></div>
  </div>

  <div class="card">
    <h3 style="font-size:14px;color:var(--c-acc2);margin-bottom:10px">操作日志</h3>
    <div id="log" class="mut">等待操作…</div>
  </div>
</div>
<script>
let SESSION = '';

function log(s){
  const el = document.getElementById('log');
  el.textContent = s + '\\n' + el.textContent;
}

function openBuiltin(){
  // 优先用外壳里的内嵌弹窗（同一页面内打开，不新开标签页）
  if (window.parent && window.parent !== window && window.parent.__c2aOpenBrowser){
    window.parent.__c2aOpenBrowser('');
    return;
  }
  if (window.__c2aOpenBrowser){ window.__c2aOpenBrowser(''); return; }
  // 兜底：本页自己显示一个内嵌 iframe 弹窗
  const host = location.hostname || '127.0.0.1';
  let m = document.getElementById('vnc-modal');
  if (!m){
    m = document.createElement('div');
    m.id = 'vnc-modal';
    m.style.cssText = 'position:fixed;inset:0;z-index:99999;display:flex;'
      + 'align-items:center;justify-content:center;background:rgba(10,10,10,.55)';
    m.innerHTML = '<div style="width:min(1180px,94vw);height:min(800px,90vh);'
      + 'background:#0b0d12;border-radius:14px;overflow:hidden;display:flex;'
      + 'flex-direction:column">'
      + '<div style="display:flex;align-items:center;gap:12px;padding:10px 14px;'
      + 'background:#14161d;color:#e6e6e6;font-size:13px">'
      + '<span style="font-weight:600">内置浏览器（走容器代理）</span>'
      + '<span style="flex:1"></span>'
      + '<button id="vnc-close" style="background:#2a2d3a;color:#e6e6e6;border:0;'
      + 'border-radius:7px;padding:6px 12px;font-size:12.5px;cursor:pointer">关闭</button>'
      + '</div>'
      + '<div style="flex:1;background:#000">'
      + '<iframe id="vnc-frame" style="width:100%;height:100%;border:0" '
      + 'src="http://' + host + ':6080/vnc.html?autoconnect=1&resize=remote&reconnect=1">'
      + '</iframe></div></div>';
    document.body.appendChild(m);
    m.querySelector('#vnc-close').onclick = ()=>{ m.remove(); };
  }
}

async function copyProxy(){
  const t = document.getElementById('proxyaddr').textContent;
  try{ await navigator.clipboard.writeText(t); log('已复制代理地址: '+t); }
  catch(e){ log('复制失败，请手动选择复制'); }
}

async function startAuth(){
  const b = document.getElementById('startbtn');
  b.disabled = true; b.textContent = '生成中…';
  try{
    const r = await fetch('/p/api/oauth/start', {method:'POST',
      headers:{'Content-Type':'application/json'}, body:'{}'});
    const d = await r.json();
    if(d.authorize_url){
      SESSION = d.session_id || '';
      document.getElementById('startmsg').innerHTML =
        '<span class="ok">已生成</span> 正在内置浏览器里打开授权页…';
      log('授权链接已生成，session='+SESSION.slice(0,8)+'…');
      // 让容器里的 Chromium 直接打开授权页（它的流量走容器代理，
      // 你本机不用开任何代理，也不会弹到你的本机浏览器）
      try{
        const r2 = await fetch('/p/api/oauth/open', {method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({url: d.authorize_url})});
        const d2 = await r2.json();
        if(d2.ok){
          document.getElementById('startmsg').innerHTML =
            '<span class="ok">已在下方的内置浏览器弹窗中打开</span>';
          log('已在容器浏览器中打开');
          openBuiltin();   // 就地弹出，不用再点一次
        } else {
          document.getElementById('startmsg').innerHTML =
            '<span class="bad">内置浏览器打开失败</span> ' + (d2.error||'').slice(0,160)
            + '<br><span class="mut">可点「打开内置浏览器」后手动粘贴地址</span>';
          log('打开失败: ' + (d2.error||'').slice(0,120));
        }
      }catch(e){ log('打开异常: '+e.message); }
      document.getElementById('authurl').value = d.authorize_url;
      document.getElementById('urlline').style.display = 'block';
    } else {
      document.getElementById('startmsg').innerHTML =
        '<span class="bad">失败</span> '+(d.error||JSON.stringify(d)).slice(0,200);
      log('生成失败');
    }
  }catch(e){
    document.getElementById('startmsg').innerHTML = '<span class="bad">异常</span> '+e.message;
  }
  b.disabled = false; b.textContent = '生成并打开授权页';
}

async function copyUrl(){
  const v = document.getElementById('authurl').value;
  try{ await navigator.clipboard.writeText(v); log('授权链接已复制'); }
  catch(e){ log('复制失败，请手动选择复制'); }
}

async function autoFetchCallback(){
  const box = document.getElementById('finishmsg');
  box.innerHTML = '<span class="mut">正在读取内置浏览器…</span>';
  try{
    const r = await fetch('/p/api/oauth/callback');
    const d = await r.json();
    if(d.ok && d.url){
      document.getElementById('callback').value = d.url;
      box.innerHTML = '<span class="ok">已获取回调地址</span> 可直接点「提交并完成添加」。';
      log('已自动获取回调地址');
    }else{
      box.innerHTML = '<span class="bad">没找到</span> 内置浏览器里还没停在 callback 页面，'
        + '或者登录还没完成。请确认登录成功后重试，或手动复制地址栏。';
      log('自动获取失败：未发现 callback 标签');
    }
  }catch(e){
    box.innerHTML = '<span class="bad">异常</span> ' + e.message;
  }
}

/* 全自动：服务端读回调 → 直接换 token 入库，无需复制粘贴。
   noVNC 的剪贴板不和宿主机互通，手动复制这条路走不通。 */
async function autoFinish(wait){
  const box = document.getElementById('finishmsg');
  box.innerHTML = '<span class="mut">正在自动完成（读取内置浏览器回调并兑换）…</span>';
  try{
    const r = await fetch('/p/api/oauth/auto', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({session_id: SESSION, wait: wait || 0})});
    const d = await r.json();
    if(d.ok){
      if(d.url) document.getElementById('callback').value = d.url;
      box.innerHTML = '<span class="ok">添加成功</span> 新增 ' + (d.added ?? '?')
        + ' 个，已刷新 ' + (d.refreshed ?? 0) + ' 个，跳过 ' + (d.skipped ?? 0) + ' 个。';
      log('自动添加成功');
    } else {
      if(d.url) document.getElementById('callback').value = d.url;
      box.innerHTML = '<span class="bad">失败</span> ' + (d.error||'').slice(0,300);
      log('自动添加失败: ' + (d.error||'').slice(0,120));
    }
  }catch(e){
    box.innerHTML = '<span class="bad">异常</span> ' + e.message;
  }
}

async function finishAuth(){
  const cb = document.getElementById('callback').value.trim();
  if(!cb){ document.getElementById('finishmsg').innerHTML='<span class="bad">请先粘贴回调链接</span>'; return; }
  document.getElementById('finishmsg').innerHTML = '<span class="mut">提交中…</span>';
  try{
    const r = await fetch('/p/api/oauth/finish', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({session_id:SESSION, callback:cb})});
    const d = await r.json();
    if(d.ok){
      document.getElementById('finishmsg').innerHTML =
        '<span class="ok">添加成功</span> 可以回号池管理查看。';
      log('添加成功');
    } else {
      document.getElementById('finishmsg').innerHTML =
        '<span class="bad">失败</span> '+(d.error||'').slice(0,300);
      log('添加失败: '+(d.error||'').slice(0,120));
    }
  }catch(e){
    document.getElementById('finishmsg').innerHTML = '<span class="bad">异常</span> '+e.message;
  }
}

(async ()=>{
  try{
    const r = await fetch('/p/api/proxyaddr');
    const d = await r.json();
    if(d.addr) document.getElementById('proxyaddr').textContent = d.addr;
  }catch(e){}
})();
</script><script>
(function(){
  // 跟随面板自己的主题设置（localStorage: chatgpt2api-theme），
  // 让 /p/chat、/p/proxy、/p/oauth 与原生页面同色，不再是一块突兀的深色。
  function apply(){
    var t = 'light';
    try{ t = localStorage.getItem('chatgpt2api-theme') || 'light'; }catch(e){}
    document.documentElement.setAttribute('data-c2a', t === 'dark' ? 'dark' : 'light');
  }
  apply();
  window.addEventListener('storage', function(e){
    if(e.key === 'chatgpt2api-theme') apply();
  });
  setInterval(apply, 1500);
})();
</script><script>
(function(){
  // 被嵌进外层弹层时，隐藏自带的返回条（外层已有原生导航，避免重复）
  try{
    if (window.parent && window.parent !== window){
      var bars = document.querySelectorAll('.c2a-bar');
      for (var i=0;i<bars.length;i++) bars[i].style.display = 'none';
      document.documentElement.setAttribute('data-embedded','1');
    }
  }catch(e){}
})();
</script></body></html>
"""
