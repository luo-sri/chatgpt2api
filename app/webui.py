# -*- coding: utf-8 -*-
"""对话页 / 代理设定页 —— 完全复用面板原生 Header 结构

关键设计：
  不自己画顶栏，而是渲染与面板相同的 DOM 结构和 class：
    <main class="面板同款 radial 背景">
      <div class="面板同款 max-w-[1440px] 容器">
        <header class="border-b border-stone-100/50 dark:border-white/10">
          <div class="flex min-h-12 ... sm:px-6">
            <nav class="hide-scrollbar ... sm:justify-center sm:gap-8">…</nav>
          </div>
        </header>
        <正文/>
  并引用面板自己的 CSS（0yvynf4qtqgia.css），
  主题切换用面板同一逻辑（documentElement.classList.toggle('dark')），
  因此布局、间距、暗色模式与面板 100% 一致。

/p/chat   GPT 网页版对话（侧栏会话、气泡、复制/重试、流式、打字点）
/p/proxy  代理设定（勾选排序、快捷切换、订阅）
"""
import json
import urllib.error
import urllib.parse
import urllib.request

MIHOMO = "http://127.0.0.1:9090"

# ---------------------------------------------------------------- 品牌信息
APP_NAME = "ChatGPT2API"
APP_VERSION = "v2.4.3"
REPO_OWNER = "luo-sri"
REPO_NAME = "chatgpt2api"
REPO_URL = "https://github.com/%s/%s" % (REPO_OWNER, REPO_NAME)
REPO_API = "https://api.github.com/repos/%s/%s" % (REPO_OWNER, REPO_NAME)

# ---- 面板原生 class（与 web_dist 完全一致）----
NATIVE_MAIN = ("min-h-screen overflow-x-hidden bg-[radial-gradient(circle_at_top_left,_rgba(255,255,255,0.92),"
               "rgba(245,239,231,0.96)_42%,rgba(240,235,227,0.99)_100%)] px-4 pt-0 pb-2 text-stone-900 "
               "transition-colors duration-300 dark:bg-[radial-gradient(circle_at_top_left,_rgba(55,48,43,0.72),"
               "rgba(28,25,23,0.98)_40%,rgba(12,10,9,1)_100%)] dark:text-stone-100 sm:px-6 sm:pt-2 lg:px-8")
NATIVE_INNER = ("mx-auto box-border flex min-h-screen max-w-[1440px] flex-col gap-2 "
                "pt-[env(safe-area-inset-top)] sm:gap-5 sm:pt-0")
NATIVE_HEADER_ROW = ("flex min-h-12 flex-col gap-1 px-3 py-2 sm:h-12 sm:flex-row sm:items-center "
                     "sm:justify-between sm:gap-3 sm:px-6 sm:py-0")
NATIVE_NAV_CLS = ("hide-scrollbar -mx-1 hidden min-w-0 flex-1 gap-1 overflow-x-auto px-1 sm:mx-0 "
                  "sm:flex sm:justify-center sm:gap-8 sm:overflow-visible sm:px-0")
NATIVE_NAV_ITEM = ("relative shrink-0 whitespace-nowrap rounded-full px-2.5 py-1 text-[13px] font-medium "
                   "transition sm:rounded-none sm:px-0 sm:text-[15px] text-stone-500 hover:text-stone-900 "
                   "dark:text-stone-400 dark:hover:text-stone-100")

NAV_ITEMS = [("/p/chat/", "对话"), ("/p/proxy/", "代理设定"),
             ("/image/", "生图"), ("/accounts/", "号池管理"), ("/image-manager/", "图片管理"),
             ("/logs/", "日志管理"), ("/debug/", "调试"), ("/settings/", "设置")]

# ---- 主题脚本：与面板同键同目标（html.dark）+ 顶栏主题切换按钮 ----
THEME_JS = """<script>
(function(){
  function cur(){ try{ return localStorage.getItem('chatgpt2api-theme')||'light'; }catch(e){ return 'light'; } }
  function apply(){
    document.documentElement.classList.toggle('dark', cur()==='dark');
    var b=document.getElementById('c2a-theme');
    if(b){ b.setAttribute('aria-label', cur()==='dark'?'切换浅色':'切换深色'); }
  }
  apply();
  document.addEventListener('visibilitychange',function(){ if(!document.hidden)apply(); });
  setInterval(apply,2000);
  // 顶栏主题切换（与面板同一存储键，两处切换即时同步）
  document.addEventListener('DOMContentLoaded',function(){
    var b=document.getElementById('c2a-theme');
    if(b) b.onclick=function(){
      var t=cur()==='dark'?'light':'dark';
      try{ localStorage.setItem('chatgpt2api-theme',t); }catch(e){}
      apply();
    };
  });
})();
</script>"""

def _update_ui_js():
    """版本面板脚本（自有页面用）。

    与原生页面共用 update_ui.py 里的同一份实现，
    保证「点版本号看更新内容 / 一键更新」在两类页面表现一致。
    """
    try:
        import update_ui
        return update_ui.update_ui_script(
            APP_VERSION, REPO_API, REPO_URL,
            "https://raw.githubusercontent.com/%s/%s/main/VERSION" % (REPO_OWNER, REPO_NAME),
            "https://raw.githubusercontent.com/%s/%s/main/CHANGELOG.md" % (REPO_OWNER, REPO_NAME),
        )
    except Exception:
        return ""


BASE_CSS = """
/* 注意：不要用 *{margin:0;padding:0} 这种非分层重置——
   它会压过面板 Tailwind @layer 的 .mx-auto/.flex 等工具类，
   导致 max-w 容器不再居中（截图里"整体偏左、右侧空白"的根因）。 */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;border:0;
     cursor:pointer;font-family:inherit;transition:.15s;text-decoration:none;white-space:nowrap}
.btn-dark{background:#1c1917;color:#fafaf9;border-radius:10px;padding:8px 16px;font-size:13px}
.btn-dark:hover{background:#44403c}
.dark .btn-dark{background:#fafaf9;color:#1c1917}
.btn-ghost{background:transparent;color:inherit;border:1px solid rgba(28,25,23,.15);
     border-radius:10px;padding:8px 14px;font-size:13px}
.btn-ghost:hover{background:rgba(28,25,23,.05)}
.dark .btn-ghost{border-color:rgba(245,245,244,.2)}
.dark .btn-ghost:hover{background:rgba(245,245,244,.08)}
.btn:disabled{opacity:.45;cursor:not-allowed}
.inp{background:rgba(255,255,255,.8);border:1px solid rgba(28,25,23,.12);color:#1c1917;
     border-radius:10px;padding:9px 12px;font-size:13px;font-family:inherit;width:100%}
.dark .inp{background:rgba(20,18,16,.8);border-color:rgba(245,245,244,.15);color:#f5f5f4}
.inp:focus{outline:none;border-color:#a8a29e}
.mut{color:#78716c;font-size:12.5px}
.dark .mut{color:#a8a29e}
.ok{color:#16a34a}.warn{color:#d97706}.bad{color:#dc2626}
.card{border-radius:16px;border:1px solid rgba(255,255,255,.7);background:rgba(255,255,255,.9);
      box-shadow:0 20px 60px -28px rgba(25,33,61,.18);padding:20px;margin-bottom:16px}
.dark .card{border-color:rgba(255,255,255,.1);background:rgba(28,25,23,.6);box-shadow:none}
"""


def native_shell(active_href, title, body_html, extra_css=""):
    links = []
    for href, label in NAV_ITEMS:
        marker = ""
        if href == active_href:
            marker = ('<span aria-hidden="true" class="absolute inset-x-1 -bottom-px h-0.5 '
                      'bg-stone-900 dark:bg-stone-100"></span>')
        links.append('<a class="%s" href="%s">%s%s</a>' % (NATIVE_NAV_ITEM, href, label, marker))
    nav = '<nav class="%s">%s</nav>' % (NATIVE_NAV_CLS, "".join(links))

    # 左侧组：与面板同款（移动端汉堡菜单 + chatgpt2api logo）
    left = (
        '<div class="flex items-center justify-between gap-2 sm:justify-start sm:gap-3">'
        '<button type="button" '
        'class="inline-flex size-8 items-center justify-center text-stone-700 transition '
        'hover:text-stone-950 sm:hidden dark:text-stone-200 dark:hover:text-white" '
        'aria-label="打开导航">'
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round" class="lucide lucide-menu size-4" aria-hidden="true">'
        '<path d="M4 5h16"></path><path d="M4 12h16"></path><path d="M4 19h16"></path></svg>'
        '<span class="sr-only">打开导航</span></button>'
        '<a class="shrink-0 py-1 text-[15px] font-bold tracking-tight text-stone-950 transition '
        'hover:text-stone-700 dark:text-stone-50 dark:hover:text-white" href="/image/">chatgpt2api</a>'
        '</div>')

    # 右侧组：与面板完全同款（主题 + GitHub + 版本 + 管理员徽章 + 退出）
    right = (
        '<div class="hidden items-center justify-end gap-2 sm:flex sm:gap-3">'
        '<div class="flex items-center gap-2 sm:gap-3">'
        '<button type="button" id="c2a-theme" '
        'class="inline-flex size-8 shrink-0 items-center justify-center text-stone-500 '
        'transition hover:text-stone-900 dark:text-stone-300 dark:hover:text-white" '
        'aria-label="切换主题" title="切换主题">'
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round" class="lucide lucide-moon size-4" aria-hidden="true">'
        '<path d="M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401"></path>'
        '</svg><span class="sr-only">Toggle theme</span></button>'
        '<a href="https://github.com/luo-sri/chatgpt2api" target="_blank" rel="noreferrer" '
        'class="inline-flex h-8 items-center justify-center gap-1.5 text-sm text-stone-500 '
        'transition hover:text-stone-900 dark:text-stone-300 dark:hover:text-white" '
        'aria-label="GitHub repository" title="GitHub 仓库">'
        '<img alt="" class="size-4" src="/github.svg"><span class="hidden sm:inline">GitHub</span></a>'
        '<button type="button" id="c2a-ver" class="relative px-1 py-1 text-[11px] font-medium '
        'text-stone-500 transition hover:text-stone-900 dark:text-stone-300 dark:hover:text-white" '
        'title="点击检查更新">' + APP_VERSION + '</button></div>'
        '<span class="hidden rounded-md bg-stone-100 px-2 py-1 text-[10px] font-medium text-stone-500 '
        'dark:bg-white/8 dark:text-stone-300 sm:inline-block sm:text-[11px]">管理员 · 管理员</span>'
        '<button type="button" class="py-1 text-xs text-stone-400 transition hover:text-stone-700 '
        'dark:text-stone-500 dark:hover:text-stone-200 sm:text-sm" '
        'onclick="location.href=&quot;/&quot;">退出</button></div>')

    header = ('<header class="border-b border-stone-100/50 dark:border-white/10">'
              '<div class="%s">%s%s%s</div></header>') % (NATIVE_HEADER_ROW, left, nav, right)

    html = (
        '<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<title>' + title + '</title>\n'
        '<link rel="icon" href="/favicon.ico">\n'
        '<link rel="stylesheet" href="/_next/static/chunks/0yvynf4qtqgia.css">\n'
        '<style>' + BASE_CSS + (extra_css or '') + '</style>\n'
        '</head><body>\n' + THEME_JS + _update_ui_js() +
        '<main class="' + NATIVE_MAIN + '">\n'
        '  <div class="' + NATIVE_INNER + '">\n'
        '    ' + header + '\n'
        '    ' + (body_html or '') + '\n'
        '  </div>\n'
        '</main>\n'
        '</body></html>')
    return html


# ============================================================ 对话页（1:1 GPT 网页版）
CHAT_CSS = """
#chat-root{display:flex;flex:1;min-height:calc(100vh - 3rem)}
#sidebar{display:none}
@media(min-width:768px){#sidebar{display:flex;flex-direction:column;width:260px;flex-shrink:0;
  border-right:1px solid rgba(28,25,23,.06)}}
.dark #sidebar{border-color:rgba(245,245,244,.08)}
.conv{display:flex;align-items:center;gap:8px;border-radius:10px;padding:8px 12px;font-size:13.5px;
  cursor:pointer;margin-bottom:2px;color:#44403c}
.dark .conv{color:#d6d3d1}
.conv:hover{background:rgba(28,25,23,.05)}
.dark .conv:hover{background:rgba(245,245,244,.06)}
.conv.on{background:rgba(28,25,23,.09);font-weight:600}
.dark .conv.on{background:rgba(245,245,244,.1)}
.conv .del{opacity:0;border:0;background:none;color:#a8a29e;cursor:pointer;font-size:12px}
.conv:hover .del{opacity:1}
.conv .del:hover{color:#dc2626}
#msgs{flex:1;overflow-y:auto;padding:12px 0 8px}
/* GPT 同款：用户消息浅灰气泡右对齐（不是深色） */
.b-u{display:flex;justify-content:flex-end;padding:6px 24px}
.b-u>div{max-width:76%;border-radius:24px 24px 6px 24px;background:rgba(244,244,241,1);
  padding:11px 18px;font-size:15.5px;line-height:1.75;white-space:pre-wrap;word-break:break-word;
  color:#0d0d0d}
.dark .b-u>div{background:rgba(48,48,48,1);color:#ececec}
/* GPT 同款：AI 消息通栏、顶部标题居中左，内容 48px 标题带无头像 */
.b-a{padding:6px 24px}
.b-a .inner{max-width:760px;margin:0 auto}
.b-a .hd{font-size:13px;font-weight:600;margin-bottom:6px;display:flex;gap:10px;align-items:center;
  color:inherit}
.b-a .act{opacity:0;font-size:11.5px;color:#a8a29e;border:0;background:none;cursor:pointer}
.b-a:hover .act{opacity:1}
.b-a .act:hover{color:#1c1917}
.dark .b-a .act:hover{color:#f5f5f4}
.b-a .ct{white-space:pre-wrap;word-break:break-word;font-size:15.5px;line-height:1.85;
  max-width:760px;margin:0 auto;color:inherit}
.b-a .th{font-size:13px;color:#78716c;background:rgba(28,25,23,.04);border-left:2px solid #d6d3d1;
  padding:8px 12px;border-radius:0 8px 8px 0;margin-bottom:8px}
.dark .b-a .th{color:#a8a29e;background:rgba(245,245,244,.05)}
/* GPT 欢迎页：大标题居中 */
#welcome{display:flex;align-items:center;justify-content:center;padding:10vh 20px 0}
#welcome .in{text-align:center}
#welcome h1{font-size:28px;font-weight:600;letter-spacing:-.5px;margin-bottom:10px;color:inherit}
#welcome p{color:#a8a29e;font-size:14px}
.dots{display:inline-flex;gap:5px;padding:10px 0}
.dots i{width:8px;height:8px;border-radius:50%;background:#0d0d0d;opacity:.25;animation:tp 1.2s infinite}
.dark .dots i{background:#ececec}
.dots i:nth-child(2){animation-delay:.2s}.dots i:nth-child(3){animation-delay:.4s}
@keyframes tp{0%,60%,100%{opacity:.25}30%{opacity:.8}}
/* GPT 同款输入区：圆角悬浮、底部渐隐 */
#composer-wrap{padding:4px 16px 14px;background:transparent}
#composer{max-width:768px;margin:0 auto;border-radius:28px;border:1px solid rgba(0,0,0,.1);
  background:#ffffff;box-shadow:0 4px 28px rgba(0,0,0,.09);padding:14px 18px 10px;position:relative}
.dark #composer{background:#303030;border-color:rgba(255,255,255,.1)}
#composer textarea{width:100%;background:none;border:0;outline:none;resize:none;font-size:16px;
  line-height:1.6;max-height:200px;font-family:inherit;color:inherit}
#composer textarea::placeholder{color:#a8a29e}
#crow{display:flex;align-items:center;gap:8px;margin-top:6px}
#crow .sp{flex:1}
#send{width:34px;height:34px;border-radius:50%;padding:0}
#send:disabled{background:rgba(0,0,0,.08);color:#a8a29e}
.dark #send:disabled{background:rgba(255,255,255,.08)}
#tip{max-width:768px;margin:8px auto 0;text-align:center;font-size:11.5px;color:#a8a29e}
/* 与面板容器对齐：右侧栏占 260px，会把内容中心挤右 130px。
   平移回来后，消息列与输入框的中心 = 面板容器中心（和号池管理一致）。 */
@media(min-width:768px){
  #msgs, #composer-wrap{margin-left:-130px;margin-right:130px}
}
#stat{font-size:11px;color:#a8a29e}
"""


def build_chat_body():
    return """
<div id="chat-root">
  <aside id="sidebar">
    <div style="padding:10px 12px">
      <button class="btn btn-dark" style="width:100%" id="btn-new">＋ 新对话</button>
    </div>
    <div style="flex:1;overflow-y:auto;padding:0 12px 12px" id="conv-list"></div>
    <div class="mut" style="border-top:1px solid rgba(28,25,23,.06);padding:10px 14px;font-size:11.5px" id="conv-count"></div>
  </aside>
  <div style="display:flex;flex-direction:column;flex:1;min-width:0">
    <div style="display:flex;align-items:center;gap:8px;padding:8px 16px">
      <button class="btn btn-ghost" style="padding:6px 12px;font-size:12.5px" id="btn-new-m">＋</button>
      <select id="conv-sel-m" class="inp" style="width:auto;min-width:120px;max-width:40%;font-size:12px;padding:6px 8px"></select>
      <span class="sp"></span>
      <select id="model" class="inp" style="width:auto;max-width:190px;font-size:12px;padding:6px 8px"></select>
      <label class="mut" style="display:flex;align-items:center;gap:5px;cursor:pointer;user-select:none">
        <input type="checkbox" id="think" style="width:auto;cursor:pointer"> 思考</label>
    </div>
    <div id="msgs"></div>
    <div id="composer-wrap">
      <div id="composer">
        <textarea id="input" rows="1" placeholder="发送消息"></textarea>
        <div id="crow">
          <span class="mut" id="stat" style="font-size:11px"></span>
          <span class="sp"></span>
          <button class="btn btn-dark" id="send" title="发送 (Enter)">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
          </button>
        </div>
      </div>
      <div id="tip">回复由 AI 生成，请核实重要信息</div>
    </div>
  </div>
</div>
"""


CHAT_JS = r"""
<script>
(function(){
  var M=document.getElementById('msgs'), IN=document.getElementById('input');
  var KEY='__C2A_KEY__';
  var CONVS=[], CUR=null, BUSY=false;

  function getKey(){
    var k=null; try{ k=localStorage.getItem('c2a_key'); }catch(e){}
    if(k) return k;
    return (KEY && KEY.indexOf('__C2A_KEY')!==0) ? KEY : '';
  }
  function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];}); }

  function loadConvs(){
    try{ CONVS=JSON.parse(localStorage.getItem('c2a_convs')||'[]'); }catch(e){ CONVS=[]; }
    CUR=CONVS.length?CONVS[0].id:null;
    renderConvs();
    renderMsgs();
  }
  function saveConvs(){ try{ localStorage.setItem('c2a_convs',JSON.stringify(CONVS.slice(0,30))); }catch(e){} }
  function curConv(){ for(var i=0;i<CONVS.length;i++) if(CONVS[i].id===CUR) return CONVS[i]; return null; }
  function newConv(silent){
    var c={id:''+Date.now()+Math.floor(Math.random()*999),title:'新对话',msgs:[],ts:Date.now()};
    CONVS.unshift(c); CUR=c.id; saveConvs(); renderConvs(); renderMsgs();
    if(!silent) IN.focus();
  }
  window.__pick=function(id){ CUR=id; renderConvs(); renderMsgs(); };
  window.__del=function(id,ev){ if(ev)ev.stopPropagation();
    CONVS=CONVS.filter(function(c){return c.id!==id;});
    if(CUR===id) CUR=CONVS.length?CONVS[0].id:null;
    if(!CONVS.length) newConv(true);
    saveConvs(); renderConvs(); renderMsgs();
  };

  function renderConvs(){
    var list=document.getElementById('conv-list'), selM=document.getElementById('conv-sel-m');
    list.innerHTML=CONVS.map(function(c){
      return '<div class="conv '+(c.id===CUR?'on':'')+'" onclick="window.__pick(\''+c.id+'\')">'
        +'<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(c.title)+'</span>'
        +'<button class="del" onclick="window.__del(\''+c.id+'\',event)" title="删除">✕</button></div>';
    }).join('');
    document.getElementById('conv-count').textContent=CONVS.length+' 个会话';
    selM.innerHTML=CONVS.map(function(c){
      return '<option value="'+c.id+'"'+(c.id===CUR?' selected':'')+'>'+esc(c.title.slice(0,14))+'</option>';
    }).join('');
  }

  function welcome(){
    M.innerHTML='<div id="welcome"><div class="in">'
      +'<h1>有什么可以帮忙的？</h1>'
      +'<p>在下方输入框发送消息</p></div></div>';
  }
  function renderMsgs(){
    var c=curConv();
    if(!c||!c.msgs.length){ welcome(); return; }
    var h='';
    for(var i=0;i<c.msgs.length;i++){
      var m=c.msgs[i];
      if(m.role==='user'){
        h+='<div class="b-u"><div>'+esc(m.content)+'</div></div>';
      }else{
        h+='<div class="b-a"><div class="inner">'
          +'<div class="hd">ChatGPT'
          +'<button class="act" onclick="window.__copy(this)" data-t="'+esc(m.content).replace(/"/g,'&quot;')+'">复制</button>'
          +(i===c.msgs.length-1?'<button class="act" onclick="window.__retry()">重试</button>':'')
          +'</div>'
          +(m.think?'<div class="th">'+esc(m.think)+'</div>':'')
          +'<div class="ct">'+esc(m.content)+'</div></div></div>';
      }
    }
    M.innerHTML=h;
    M.scrollTop=M.scrollHeight;
  }
  window.__copy=function(btn){
    try{
      navigator.clipboard.writeText(btn.dataset.t).then(function(){
        btn.textContent='已复制'; setTimeout(function(){btn.textContent='复制';},1200);
      });
    }catch(e){}
  };
  window.__retry=function(){
    var c=curConv(); if(!c||BUSY) return;
    if(c.msgs.length&&c.msgs[c.msgs.length-1].role==='assistant') c.msgs.pop();
    if(!c.msgs.length){ renderMsgs(); return; }
    renderMsgs(); send(true);
  };

  function typing(on){
    var t=document.getElementById('typing');
    if(on&&!t){
      t=document.createElement('div'); t.id='typing';
      t.innerHTML='<div class="b-a"><div class="hd">ChatGPT</div><div class="dots"><i></i><i></i><i></i></div></div>';
      M.appendChild(t); M.scrollTop=M.scrollHeight;
    }
    if(!on&&t) t.remove();
  }

  async function loadModels(){
    try{
      var r=await fetch('/v1/models',{headers:{'Authorization':'Bearer '+getKey()}});
      var j=await r.json();
      // 与号池页「管理模型」的启用/禁用保持一致（网关已过滤，这里再兜底）
      var off=[];
      try{ off=JSON.parse(localStorage.getItem('c2a-model-off')||'[]'); }catch(e){}
      var ids=(j.data||[]).map(function(m){return m.id;})
        .filter(function(i){ return off.indexOf(i)<0; });
      if(!ids.length) ids=['auto'];
      var sel=document.getElementById('model');
      sel.innerHTML=ids.map(function(i){return '<option value="'+esc(i)+'">'+esc(i)+'</option>';}).join('');
      sel.value=ids.indexOf('auto')>=0?'auto':ids[0];
    }catch(e){
      document.getElementById('model').innerHTML='<option value="auto">auto</option>';
    }
  }

  async function send(isRetry){
    if(BUSY) return;
    var q=IN.value.trim();
    if(!q&&!isRetry) return;
    if(!curConv()) newConv(true);
    var c=curConv();
    if(q){
      c.msgs.push({role:'user',content:q});
      IN.value=''; IN.style.height='auto';
      if(c.title==='新对话') c.title=q.slice(0,24);
    }
    renderMsgs(); renderConvs(); saveConvs();
    BUSY=true; document.getElementById('send').disabled=true; typing(true);
    var model=document.getElementById('model').value||'auto';
    var think=document.getElementById('think').checked?'detailed':'auto';
    var text='', think2='';
    var t0=Date.now();
    // 超时兜底：上游被节点风控挂住时，180 秒强制中断，
    // 避免"一直在回复中"永远转圈（可点重试换节点再来）
    var ctl=new AbortController();
    var timer=setTimeout(function(){ ctl.abort(); }, 180000);
    try{
      var r=await fetch('/v1/chat/completions',{method:'POST',
        signal:ctl.signal,
        headers:{'Content-Type':'application/json','Authorization':'Bearer '+getKey()},
        body:JSON.stringify({model:model,stream:true,thinking:think,
          messages:c.msgs.map(function(m){return {role:m.role,content:m.content};})})});
      if(!r.ok){
        var msg='HTTP '+r.status;
        try{ var j0=await r.json(); msg=(j0.error&&j0.error.message)||msg; }catch(e){}
        throw new Error(msg);
      }
      var rd=r.body.getReader(), dec=new TextDecoder(), buf='';
      for(;;){
        var chunk=await rd.read();
        if(chunk.done) break;
        buf+=dec.decode(chunk.value,{stream:true});
        var lines=buf.split('\n'); buf=lines.pop();
        for(var li=0;li<lines.length;li++){
          var ln=lines[li];
          if(ln.indexOf('data:')!==0) continue;
          var d=ln.slice(5).trim();
          if(!d||d==='[DONE]') continue;
          var j=null; try{ j=JSON.parse(d); }catch(e){ continue; }
          if(j.error) throw new Error(j.error.message||'上游错误');
          var dl=(j.choices&&j.choices[0]&&j.choices[0].delta)||{};
          if(dl.reasoning_content||dl.thinking) think2+=(dl.reasoning_content||dl.thinking);
          if(dl.content) text+=dl.content;
        }
      }
      if(!text && !think2){
        // 流式结束但全程空内容：多半是出口节点被 ChatGPT 风控拦了
        throw new Error('上游返回空内容——当前出口节点可能被风控，请到「代理设定」换节点后点重试');
      }
      c.msgs.push({role:'assistant',content:text,think:think2||null});
      document.getElementById('stat').textContent=((Date.now()-t0)/1000).toFixed(1)+'s · '+text.length+' 字';
    }catch(e){
      var tip=(e.name==='AbortError')
        ? '请求超时（180 秒无响应）——出口节点可能被风控，请换节点后重试'
        : e.message;
      c.msgs.push({role:'assistant',content:'⚠ '+tip});
    }finally{
      clearTimeout(timer);
      BUSY=false; document.getElementById('send').disabled=false; typing(false);
      saveConvs(); renderMsgs(); renderConvs();
    }
  }

  document.getElementById('send').onclick=function(){ send(); };
  document.getElementById('btn-new').onclick=function(){ newConv(); };
  document.getElementById('btn-new-m').onclick=function(){ newConv(); };
  document.getElementById('conv-sel-m').onchange=function(e){ window.__pick(e.target.value); };
  IN.addEventListener('keydown',function(e){
    if(e.key==='Enter'&&!e.shiftKey){ e.preventDefault(); send(); }
  });
  IN.addEventListener('input',function(){
    IN.style.height='auto';
    IN.style.height=Math.min(IN.scrollHeight,176)+'px';
  });

  loadModels(); loadConvs();
})();
</script>
"""


# ============================================================ 代理设定页
def build_proxy_body():
    return """
<div style="flex:1;padding-top:4px">
  <div style="max-width:900px;margin:0 auto;padding:0 8px">
  <div class="card">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <b style="font-size:14px">当前代理状态</b>
      <button class="btn btn-ghost" style="padding:5px 12px;font-size:12px" onclick="load()">刷新</button>
    </div>
    <div id="status"><span class="mut">加载中…</span></div>
  </div>

  <div class="card">
    <b style="font-size:14px">分组与节点</b>
    <p class="mut" style="margin:4px 0 12px">按住节点拖动可排序（序号=你的偏好顺序）；<b>点节点名即手动切换，切换后不会自动更换</b>。</p>
    <div id="groups"><span class="mut">加载中…</span></div>
  </div>

  <div class="card">
    <div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:12px">
      <b style="font-size:14px">节点列表</b><span style="flex:1"></span>
      <button class="btn btn-ghost" style="padding:6px 12px;font-size:12px" onclick="selectAllAuto(true)">全部启用</button>
      <button class="btn btn-ghost" style="padding:6px 12px;font-size:12px" onclick="selectAllAuto(false)">全部禁用</button>
      <button class="btn btn-dark" style="padding:7px 14px;font-size:12.5px" onclick="testAll()">全部测速</button>
      <button class="btn btn-ghost" style="padding:7px 14px;font-size:12.5px" onclick="pickBest()">用当前最快</button>
    </div>
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;font-size:11.5px;color:#a8a29e;border-bottom:1px solid rgba(28,25,23,.08)">
          <th style="padding:8px 10px 8px 0">节点</th><th style="padding:8px">延迟</th><th style="padding:8px">状态</th>
          <th style="padding:8px">启用</th><th style="padding:8px;text-align:right">操作</th>
        </tr></thead>
        <tbody id="nodes"><tr><td colspan="5" class="mut" style="padding:14px 0">加载中…</td></tr></tbody>
      </table>
    </div>
    <div id="msg" class="mut" style="padding-top:8px"></div>
  </div>

  <div class="card">
    <b style="font-size:14px">更新订阅</b>
    <p class="mut" style="margin:4px 0 10px">粘贴机场订阅链接，自动解析节点并热重载。</p>
    <input id="suburl" class="inp" placeholder="https://xxx/api/v1/client/subscribe?token=...">
    <div style="display:flex;gap:8px;padding-top:12px">
      <button class="btn btn-dark" id="subbtn" onclick="updateSub()">更新订阅</button>
      <button class="btn btn-ghost" onclick="loadSub()">读取已保存</button>
    </div>
  </div>
  </div>
</div>
"""


PROXY_JS = r"""
<script>
(function(){
  var GROUPS=[], NODES=[], EXCLUDE={};
  var KEY='__C2A_KEY__';
  function getKey(){
    var k=null; try{ k=localStorage.getItem('c2a_key'); }catch(e){}
    if(k) return k;
    return (KEY && KEY.indexOf('__C2A_KEY')!==0) ? KEY : '';
  }
  function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];}); }
  async function api(p,o){ var r=await fetch(p,Object.assign({cache:'no-store'},o||{})); return r.json(); }

  async function load(){
    var d=await api('/p/api/proxy');
    GROUPS=d.groups||[]; NODES=d.nodes||[];
    renderStatus(d); renderGroups(); renderNodes();
  }

  function renderStatus(d){
    var h='';
    GROUPS.forEach(function(g){
      var cur=g.now||'-', auto=(g.type==='URLTest');
      if(g.name==='节点选择'){
        var list=NODES.filter(function(n){return !/剩余流量|套餐到期|距离下次|官网|过期/.test(n.name);});
        h+='<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid rgba(28,25,23,.06)">'
          +'<span class="mut" style="font-size:13px">'+esc(g.name)+' <span style="font-size:11px">'+g.type+'·'+g.count+'</span></span>'
          +'<select class="inp" style="width:auto;max-width:280px;font-size:12.5px;padding:6px 10px" onchange="window.__pickNode(this.value)" title="选择节点立即切换">'
          +list.map(function(n){return '<option value="'+esc(n.name)+'"'+(n.name===cur?' selected':'')+'>'+esc(n.name)+(n.delay?' · '+n.delay+'ms':'')+'</option>';}).join('')
          +'</select></div>';
      }else if(g.name==='自动选择'){
        // 已按用户要求取消「自动选择」：不展示 URLTest 组。
        // 之前它会显示 mihomo 自己测速挑出的节点（如香港-05），
        // 与用户手动选择的美国-03 不一致，造成"换了IP还显示香港"的误解。
        return;
      }else{
        h+='<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(28,25,23,.06)">'
          +'<span class="mut" style="font-size:13px">'+esc(g.name)+' <span style="font-size:11px">'+g.type+'·'+g.count+'</span></span>'
          +'<b style="font-size:13px" class="'+(auto?'ok':'')+'">'+esc(cur)+'</b></div>';
      }
    });
    var cls=d.delay==null?'warn':(d.delay<400?'ok':(d.delay<900?'warn':'bad'));
    h+='<div style="display:flex;justify-content:space-between;padding:8px 0;font-size:13px"><span class="mut">ChatGPT 延迟</span><b class="'+cls+'">'+(d.delay==null?'测不出':d.delay+' ms')+'</b></div>';
    if(d.exit_ip) h+='<div style="display:flex;justify-content:space-between;padding:8px 0;font-size:13px"><span class="mut">出口 IP / 地区</span><b>'+esc(d.exit_ip)+' '+esc(d.exit_loc||'')+'</b></div>';
    document.getElementById('status').innerHTML=h;
  }

  function renderGroups(){
    // 「分组与节点」：可拖拽排序（HTML5 drag），顺序本地持久化；
    // 纯手动模式：点节点名即切换，不做任何自动挑节点。
    var list=NODES.filter(function(n){return !/剩余流量|套餐到期|距离下次|官网|过期/.test(n.name);});
    var chosen=list.filter(function(n){return !EXCLUDE[n.name]&&n.alive;});
    // 应用手动排序（localStorage 里存孩子组键），没存就按延迟
    var order=readOrder();
    if(order.length){
      chosen.sort(function(a,b){
        var ia=order.indexOf(a.name), ib=order.indexOf(b.name);
        return (ia<0?9e9:ia)-(ib<0?9e9:ib);
      });
    } else {
      chosen.sort(function(a,b){return (a.delay==null?9e9:a.delay)-(b.delay==null?9e9:b.delay);});
    }
    var sel=null; GROUPS.forEach(function(g){if(g.name==='节点选择')sel=g;});
    var cur=sel?sel.now:'';
    var h='<div id="grpOrder" style="display:flex;flex-wrap:wrap;gap:8px">';
    if(!chosen.length){
      h+='<span class="mut">没有可用节点（请检查订阅）</span>';
    }else{
      chosen.forEach(function(n,i){
        var cls=n.delay==null?'mut':(n.delay<400?'ok':(n.delay<900?'warn':'bad'));
        h+='<button class="btn grp-item '+(n.name===cur?'btn-dark':'btn-ghost')+'" '
          +'draggable="true" data-name="'+esc(n.name)+'" '
          +'style="padding:6px 13px;font-size:12.5px;cursor:grab" '
          +'onclick="if(!window.__dragLock)window.__pickNode(\''+esc(n.name)+'\')" '
          +'title="拖到排序 · '+(n.delay==null?'未测速':n.delay+' ms')+'（点按=手动切换）">'
          +(i+1)+'. '+esc(n.name)+' <span class="'+cls+'" style="font-size:11px">'+(n.delay==null?'—':n.delay+'ms')+'</span></button>';
      });
    }
    h+='</div>';
    document.getElementById('groups').innerHTML=h;
    bindSortDrag();
  }

  function readOrder(){
    try{ return JSON.parse(localStorage.getItem('c2a_grp_order')||'[]'); }catch(e){ return []; }
  }
  function saveOrder(a){
    try{ localStorage.setItem('c2a_grp_order',JSON.stringify(a)); }catch(e){}
    // 同步到服务端：自动选择接 deliberate read 的是服务端顺序，
    // 不是浏览器 localStorage（那样换新浏览器就丢序列）。
    try{
      fetch('/p/api/proxy/grp-order',{method:'POST',cache:'no-store',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({order:a})});
    }catch(e){}
  }
  function bindSortDrag(){
    var box=document.getElementById('grpOrder');
    if(!box||box.dataset.bound) return;
    box.dataset.bound='1';
    var dragged=null;
    box.addEventListener('dragstart',function(e){
      var b=e.target.closest('.grp-item'); if(!b)return;
      dragged=b; e.dataTransfer.effectAllowed='move';
      setTimeout(function(){b.style.opacity='.4';},0);
      window.__dragLock=false;
    });
    box.addEventListener('dragover',function(e){
      e.preventDefault();
      var after=getAfter(box,e.clientX,e.clientY);
      if(!dragged)return;
      if(after==null) box.appendChild(dragged);
      else box.insertBefore(dragged,after);
    });
    box.addEventListener('drop',function(e){
      e.preventDefault();
      window.__dragLock=true;
      setTimeout(function(){window.__dragLock=false;},200);
    });
    box.addEventListener('dragend',function(){
      if(!dragged)return;
      dragged.style.opacity='';
      var names=[].slice.call(box.querySelectorAll('.grp-item')).map(function(b){return b.dataset.name;});
      saveOrder(names);
      dragged=null;
    });
    function getAfter(container,x,y){
      var els=[].slice.call(container.querySelectorAll('.grp-item:not([style*="opacity: .4"])'));
      for(var i=0;i<els.length;i++){
        var r=els[i].getBoundingClientRect();
        if(y<r.top+r.height/2 && x<r.right+8) return els[i];
        if(x<r.right+r.width/2 && y<r.bottom+8 && y>=r.top-8) return els[i];
      }
      return null;
    }
  }

  function renderNodes(){
    var cur=''; GROUPS.forEach(function(g){if(g.name==='节点选择')cur=g.now||'';});
    var list=NODES.filter(function(n){return !/剩余流量|套餐到期|距离下次|官网|过期/.test(n.name);});
    var tb=document.getElementById('nodes');
    if(!list.length){ tb.innerHTML='<tr><td colspan="5" class="mut" style="padding:14px 0">无节点</td></tr>'; return; }
    tb.innerHTML=list.map(function(n){
      var sel=(n.name===cur);
      var cls=n.delay==null?'mut':(n.delay<400?'ok':(n.delay<900?'warn':'bad'));
      var inAuto=!EXCLUDE[n.name];
      return '<tr style="'+(sel?'background:rgba(28,25,23,.05);':'')+'border-bottom:1px solid rgba(28,25,23,.05)">'
        +'<td style="padding:9px 10px 9px 0"><b'+(sel?' class="ok"':'')+'>'+esc(n.name)+'</b>'+(sel?' <span class="ok" style="font-size:11px">当前</span>':'')+'</td>'
        +'<td class="'+cls+'" style="padding:9px 8px">'+(n.delay==null?'—':n.delay+' ms')+'</td>'
        +'<td style="padding:9px 8px">'+(n.alive?'<span class="ok">可用</span>':'<span class="bad">不可用</span>')+'</td>'
        +'<td style="padding:9px 8px"><input type="checkbox"'+(inAuto?' checked':'')+' style="width:auto;cursor:pointer" '
        +'onchange="window.__toggleAuto(\''+esc(n.name)+'\',this.checked)" title="勾选=参与自动选择"></td>'
        +'<td style="padding:9px 8px;text-align:right"><button class="btn btn-ghost" style="padding:4px 11px;font-size:12px" '
        +'onclick="window.__pickNode(\''+esc(n.name)+'\')">使用</button></td></tr>';
    }).join('');
  }

  // 批量勾选/取消（只影响"参与自动选择"这一列，不影响当前使用节点）
  window.selectAllAuto=async function(include){
    var rows=[].slice.call(document.querySelectorAll('#nodes tr'));
    var names=rows.map(function(r){
      var b=r.querySelector('b'); return b?b.textContent.trim():null;
    }).filter(function(x){return x;});
    if(!names.length) return;
    // 逐个提交，保证与服务端保存的一致
    for(var i=0;i<names.length;i++){
      await api('/p/api/proxy/auto-exclude',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({node:names[i],include:include})});
    }
    load();
  };

  window.__pickNode=async function(name){
    var r=await api('/p/api/proxy/select',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({node:name})});
    if(r.ok) load(); else show(r.error||'切换失败');
  };
  window.__toggleAuto=async function(name,on){
    var r=await api('/p/api/proxy/auto-exclude',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({node:name,include:on})});
    if(r.ok){ EXCLUDE={}; (r.exclude||[]).forEach(function(x){EXCLUDE[x]=1;}); renderGroups(); }
    else show(r.error||'操作失败');
  };
  window.pickBest=async function(){
    var r=await api('/p/api/proxy/auto-pick',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    if(r.ok){ show('已切换到: '+(r.node||'')); load(); } else show(r.error||'没有可用节点');
  };
  window.load=load;
  window.testAll=async function(){
    show('测速中…');
    var r=await api('/p/api/proxy/test',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    if(r.ok){ show('测速完成'); load(); } else show(r.error||'测速失败');
  };
  function show(s){ document.getElementById('msg').textContent=s; }
  window.updateSub=async function(){
    var u=document.getElementById('suburl').value.trim();
    if(!u){ show('请先填订阅链接'); return; }
    var b=document.getElementById('subbtn'); b.disabled=true; b.textContent='更新中…';
    var r=await api('/p/api/subscription',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:u})});
    b.disabled=false; b.textContent='更新订阅';
    show(r.ok?('更新成功，解析 '+r.nodes+' 个节点'):('失败: '+(r.error||'')));
    if(r.ok) setTimeout(load,1500);
  };
  window.loadSub=async function(){
    var d=await api('/p/api/subscription');
    if(d.url){ document.getElementById('suburl').value=d.url; show('已读取上次保存的链接'); }
    else show('尚未保存过订阅链接');
  };

  (async function(){
    try{ var d=await api('/p/api/proxy/auto-exclude'); (d.exclude||[]).forEach(function(x){EXCLUDE[x]=1;}); }catch(e){}
    load();
  })();
  setInterval(load,30000);
})();
</script>
"""


def render_pages():
    """生成两页最终 HTML。

    对话页/代理页各自使用独立模块（chat_page.py / proxy_page.py），
    任一模块缺失时回退到本文件的旧实现，保证不会启动失败。
    """
    try:
        import chat_page
        chat = native_shell("/p/chat/", "对话", chat_page.CHAT_BODY, chat_page.CHAT_CSS)
        chat = chat.replace("</body></html>", chat_page.CHAT_JS + "</body></html>")
    except Exception:
        chat = native_shell("/p/chat/", "对话", build_chat_body(), CHAT_CSS)
        chat = chat.replace("</body></html>", CHAT_JS + "</body></html>")

    try:
        import proxy_page
        proxy = native_shell("/p/proxy/", "代理设定", proxy_page.PROXY_BODY,
                             ".prow{display:flex;justify-content:space-between;"
                             "align-items:center;gap:12px;padding:8px 0;"
                             "border-bottom:1px solid rgba(28,25,23,.06);font-size:13px}"
                             ".dark .prow{border-color:rgba(245,245,244,.07)}"
                             ".prow:last-child{border-bottom:0}")
        proxy = proxy.replace("</body></html>", proxy_page.PROXY_JS + "</body></html>")
    except Exception:
        proxy = native_shell("/p/proxy/", "代理设定", build_proxy_body())
        proxy = proxy.replace("</body></html>", PROXY_JS + "</body></html>")

    # 首次使用新手引导（对话页/代理页也要，否则新用户第一眼在这两页看不到引导）
    try:
        from onboarding import onboarding_script
        _onb = onboarding_script()
        chat = chat.replace("</body></html>", _onb + "</body></html>")
        proxy = proxy.replace("</body></html>", _onb + "</body></html>")
    except Exception:
        pass

    return {"chat": chat, "proxy": proxy}
