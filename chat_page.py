# -*- coding: utf-8 -*-
"""对话页（对标 DeepSeek 网页版完整功能）

功能清单（全部可用）：
  侧栏：品牌 + 搜索会话 + 收起/展开 + 开启新对话 + 按时间分组的历史会话
        + 会话「…」菜单（重命名 / 删除）+ 底部账户区（清空全部）
  顶部：当前会话标题 + 分享
  消息：用户气泡（复制 / 编辑重发）、AI 回复（已思考可折叠展开、
        复制 / 重新生成 / 点赞 / 点踩 / 朗读 / 分享）
  输入区：深度思考、智能搜索、附件、发送；底部免责声明
  其他：多模型选择、Markdown 渲染（代码块/粗体/列表/行内代码）、
        流式输出、180 秒超时兜底、错误提示可重试
"""

CHAT_CSS = r"""
html,body{height:100%;overflow:hidden}   /* 视口内固定布局，页面不产生滚动条 */
body>main{height:100vh!important;min-height:0!important;padding-top:0!important;
  padding-bottom:0!important;overflow:hidden}
body>main>div{height:100%!important;min-height:0!important}
#chat-root{display:flex;flex:1;min-height:0;overflow:hidden}
/* ---------- 左侧栏 ---------- */
#sidebar{display:none;flex-direction:column;width:268px;flex-shrink:0;
  border-right:1px solid rgba(28,25,23,.07);background:rgba(250,249,247,.55)}
.dark #sidebar{border-color:rgba(245,245,244,.08);background:rgba(24,22,20,.45)}
@media(min-width:768px){#sidebar{display:flex}}
#sidebar.collapsed{display:none}
.sb-top{display:flex;align-items:center;gap:6px;padding:14px 12px 8px}
.sb-brand{display:flex;align-items:center;gap:7px;font-weight:700;font-size:15px;
  letter-spacing:-.2px;flex:1;min-width:0}
.sb-brand .dot{width:20px;height:20px;border-radius:6px;background:#1c1917;color:#fff;
  display:flex;align-items:center;justify-content:center;font-size:11px;flex-shrink:0}
.dark .sb-brand .dot{background:#fafaf9;color:#1c1917}
.sb-ico{width:30px;height:30px;border-radius:8px;border:0;background:transparent;
  color:#78716c;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;
  transition:.15s;flex-shrink:0}
.sb-ico:hover{background:rgba(28,25,23,.07);color:#1c1917}
.dark .sb-ico:hover{background:rgba(245,245,244,.1);color:#f5f5f4}
.sb-ico svg{width:17px;height:17px}
.sb-new{margin:4px 12px 8px;width:auto;justify-content:flex-start;gap:8px;
  border-radius:12px;padding:10px 13px;font-size:13.5px}
.sb-search{display:none;padding:0 12px 8px}
.sb-search.on{display:block}
.sb-search input{width:100%;font-size:13px;padding:8px 11px;border-radius:10px}
#conv-scroll{flex:1;overflow-y:auto;padding:2px 8px 10px}
.grp-date{font-size:11.5px;color:#a8a29e;padding:10px 8px 4px;font-weight:500}
.conv{display:flex;align-items:center;gap:6px;border-radius:10px;padding:8px 9px;
  font-size:13.5px;cursor:pointer;margin-bottom:1px;color:#3f3f46;position:relative}
.dark .conv{color:#d6d3d1}
.conv:hover{background:rgba(28,25,23,.055)}
.dark .conv:hover{background:rgba(245,245,244,.07)}
.conv.on{background:rgba(28,25,23,.09);font-weight:600}
.dark .conv.on{background:rgba(245,245,244,.11)}
.conv .t{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.conv .more{opacity:0;border:0;background:none;color:#a8a29e;cursor:pointer;
  font-size:15px;line-height:1;padding:2px 3px;border-radius:5px}
.conv:hover .more{opacity:1}
.conv .more:hover{background:rgba(28,25,23,.1);color:#1c1917}
.sb-foot{border-top:1px solid rgba(28,25,23,.07);padding:9px 10px;display:flex;
  align-items:center;gap:8px;font-size:13px}
.dark .sb-foot{border-color:rgba(245,245,244,.08)}
.sb-av{width:27px;height:27px;border-radius:50%;background:#1c1917;color:#fff;
  display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:600;flex-shrink:0}
.dark .sb-av{background:#fafaf9;color:#1c1917}
/* ---------- 右侧主区 ---------- */
#main-col{display:flex;flex-direction:column;flex:1;min-width:0}
#chat-head{display:flex;align-items:center;gap:10px;padding:10px 18px;
  border-bottom:1px solid rgba(28,25,23,.06);flex-shrink:0}
.dark #chat-head{border-color:rgba(245,245,244,.07)}
#chat-title{font-size:14px;font-weight:600;flex:1;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
#msgs{flex:1;overflow-y:auto;padding:14px 0 6px}
.b-u{display:flex;flex-direction:column;align-items:flex-end;padding:8px 24px}
.b-u .bub{max-width:74%;border-radius:22px 22px 6px 22px;background:#f4f4f1;
  padding:11px 17px;font-size:15.5px;line-height:1.75;white-space:pre-wrap;
  word-break:break-word;color:#0d0d0d}
.dark .b-u .bub{background:#303030;color:#ececec}
.b-u .acts{display:flex;gap:2px;margin-top:3px;opacity:0;transition:.15s}
.b-u:hover .acts{opacity:1}
.b-a{padding:8px 24px}
.b-a .inner{max-width:780px;margin:0 auto}
.b-a .hd{font-size:13px;font-weight:600;margin-bottom:6px;display:flex;gap:8px;align-items:center}
.think-btn{display:inline-flex;align-items:center;gap:5px;border:1px solid rgba(28,25,23,.1);
  background:rgba(28,25,23,.03);color:#78716c;border-radius:999px;padding:3px 10px;
  font-size:12px;cursor:pointer;margin-bottom:8px}
.think-btn:hover{background:rgba(28,25,23,.07)}
.dark .think-btn{border-color:rgba(245,245,244,.14);background:rgba(245,245,244,.06);color:#a8a29e}
.think-body{display:none;font-size:13px;color:#78716c;background:rgba(28,25,23,.035);
  border-left:2px solid #d6d3d1;padding:9px 13px;border-radius:0 8px 8px 0;
  margin-bottom:10px;white-space:pre-wrap;max-height:320px;overflow:auto}
.dark .think-body{color:#a8a29e;background:rgba(245,245,244,.05)}
.think-body.on{display:block}
.b-a .ct{font-size:15.5px;line-height:1.85;word-break:break-word;color:inherit}
.b-a .ct p{margin:0 0 10px}
.b-a .ct ul,.b-a .ct ol{margin:0 0 10px 22px}
.b-a .ct li{margin:3px 0}
.b-a .ct h1,.b-a .ct h2,.b-a .ct h3{margin:14px 0 8px;font-weight:650;line-height:1.4}
.b-a .ct h1{font-size:20px}.b-a .ct h2{font-size:18px}.b-a .ct h3{font-size:16px}
.b-a .ct code{background:rgba(28,25,23,.07);padding:1.5px 6px;border-radius:5px;font-size:13.5px}
.dark .b-a .ct code{background:rgba(245,245,244,.11)}
.b-a .ct pre{background:rgba(28,25,23,.045);border:1px solid rgba(28,25,23,.08);
  border-radius:12px;padding:13px 15px;overflow-x:auto;margin:10px 0;position:relative}
.dark .b-a .ct pre{background:rgba(20,18,16,.65);border-color:rgba(245,245,244,.1)}
.b-a .ct pre code{background:none;padding:0;font-size:13px;line-height:1.6}
.b-a .ct blockquote{border-left:3px solid #d6d3d1;padding-left:12px;color:#78716c;margin:10px 0}
.b-a .acts{display:flex;gap:1px;margin-top:8px; opacity:.55; transition:.15s}
.b-a:hover .acts{opacity:1}
.act{display:inline-flex;align-items:center;gap:4px;border:0;background:none;
  color:#a8a29e;cursor:pointer;font-size:11.5px;padding:5px 7px;border-radius:7px;transition:.15s}
.act:hover{background:rgba(28,25,23,.07);color:#1c1917}
.dark .act:hover{background:rgba(245,245,244,.1);color:#f5f5f4}
.act svg{width:14px;height:14px}
.act.on{color:#1c1917;font-weight:600}
.dark .act.on{color:#f5f5f4}
/* ---------- 输入区 ---------- */
#composer-wrap{padding:6px 16px 14px;flex-shrink:0}
#composer{max-width:780px;margin:0 auto;border-radius:26px;border:1px solid rgba(0,0,0,.1);
  background:#fff;box-shadow:0 4px 26px rgba(0,0,0,.08);padding:13px 16px 9px;position:relative}
.dark #composer{background:#303030;border-color:rgba(255,255,255,.1)}
#input{width:100%;background:none;border:0;outline:none;resize:none;font-size:15.5px;
  line-height:1.6;max-height:190px;font-family:inherit;color:inherit}
#input::placeholder{color:#a8a29e}
.crow{display:flex;align-items:center;gap:7px;margin-top:6px}
.pill{display:inline-flex;align-items:center;gap:5px;border:1px solid rgba(28,25,23,.14);
  background:transparent;color:#57534e;border-radius:999px;padding:5px 11px;
  font-size:12.5px;cursor:pointer;transition:.15s;white-space:nowrap}
.pill:hover{background:rgba(28,25,23,.05)}
.dark .pill{border-color:rgba(245,245,244,.18);color:#d6d3d1}
.dark .pill:hover{background:rgba(245,245,244,.08)}
.pill.on{background:#e0f2fe;border-color:#7dd3fc;color:#0369a1;font-weight:600}
.dark .pill.on{background:rgba(56,189,248,.18);border-color:rgba(56,189,248,.45);color:#7dd3fc}
.pill svg{width:14px;height:14px}
#attach{width:32px;height:32px;border-radius:50%;border:0;background:transparent;
  color:#78716c;cursor:pointer;display:inline-flex;align-items:center;justify-content:center}
#attach:hover{background:rgba(28,25,23,.07);color:#1c1917}
.dark #attach:hover{background:rgba(245,245,244,.1)}
#send{width:34px;height:34px;border-radius:50%;padding:0;border:0;cursor:pointer;
  background:#1c1917;color:#fafaf9;display:inline-flex;align-items:center;justify-content:center}
.dark #send{background:#fafaf9;color:#1c1917}
#send:disabled{background:rgba(28,25,23,.1);color:#a8a29e;cursor:not-allowed}
.dark #send:disabled{background:rgba(245,245,244,.12);color:#78716c}
#tip{max-width:780px;margin:7px auto 0;text-align:center;font-size:11.5px;color:#a8a29e}
#stat{font-size:11px;color:#a8a29e;margin-left:2px}
/* 居中：侧栏占 268px 会把对话主区挤右。给主区加等宽右内边距，
   使内部 780px 内容相对「面板容器」居中；不用负 margin / transform，
   避免把 sidebar 挤出可视区或让内容溢出被遮挡。 */
@media(min-width:1100px){
  #main-col{padding-right:268px}
  #chat-root:has(#sidebar.collapsed) #main-col{padding-right:0}
}
.grp-empty{color:#a8a29e;font-size:12px;padding:14px 10px;text-align:center}
"""

CHAT_BODY = """
<div id="chat-root">
  <aside id="sidebar">
    <div class="sb-top">
      <div class="sb-brand"><span class="dot">C</span><span>ChatGPT2API</span></div>
      <button class="sb-ico" id="btn-search" title="搜索会话">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"></circle><path d="M20 20l-3.5-3.5"></path></svg>
      </button>
      <button class="sb-ico" id="btn-collapse" title="收起侧栏">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"></rect><path d="M9 4v16"></path></svg>
      </button>
    </div>
    <button class="btn btn-dark sb-new" id="btn-new">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 5v14M5 12h14"></path></svg>
      开启新对话
    </button>
    <div class="sb-search" id="search-wrap">
      <input id="search-input" placeholder="搜索历史对话…">
    </div>
    <div id="conv-scroll"></div>
    <div class="sb-foot">
      <span class="sb-av">管</span>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">管理员</span>
      <button class="sb-ico" id="btn-clear-all" title="清空全部对话" style="width:26px;height:26px">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"></path></svg>
      </button>
    </div>
  </aside>

  <div id="main-col">
    <div id="chat-head">
      <button class="sb-ico" id="btn-open-side" title="展开侧栏" style="display:none">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"></rect><path d="M9 4v16"></path></svg>
      </button>
      <span id="chat-title">新对话</span>
      <span id="stat"></span>
      <button class="sb-ico" id="btn-share" title="分享对话（复制全文）">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4"></path></svg>
      </button>
    </div>

    <div id="msgs"></div>

    <div id="composer-wrap">
      <div id="composer">
        <textarea id="input" rows="1" placeholder="给 ChatGPT2API 发送消息"></textarea>
        <div class="crow">
          <button class="pill" id="pill-think" title="深度思考">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="3"></circle><path d="M12 2v4M12 18v4M2 12h4M18 12h4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M19.1 4.9l-2.8 2.8M7.7 16.3l-2.8 2.8"></path></svg>
            深度思考
          </button>
          <button class="pill" id="pill-search" title="智能搜索（让模型联网检索提示）">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"></circle><path d="M3 12h18M12 3c2.5 2.7 2.5 15.3 0 18M12 3c-2.5 2.7-2.5 15.3 0 18"></path></svg>
            智能搜索
          </button>
          <select id="model" class="inp" style="width:auto;max-width:170px;font-size:12px;padding:5px 9px;border-radius:999px"></select>
          <span style="flex:1"></span>
          <button id="attach" title="添加附件（文本文件）">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="17" height="17"><path d="M21.4 11.05l-8.5 8.5a5.5 5.5 0 01-7.78-7.78l8.5-8.5a3.7 3.7 0 015.23 5.23l-8.5 8.5a1.85 1.85 0 01-2.62-2.62l7.8-7.8"></path></svg>
          </button>
          <button id="send" title="发送 (Enter)">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"></path></svg>
          </button>
        </div>
      </div>
      <div id="tip">内容由 AI 生成，请仔细甄别</div>
      <input type="file" id="file-input" accept=".txt,.md,.json,.csv,.log,.py,.js,.html" style="display:none">
    </div>
  </div>
</div>
"""

CHAT_JS = r"""
<script>
(function(){
  var M=document.getElementById('msgs'), IN=document.getElementById('input');
  var KEY='__C2A_KEY__';
  var CONVS=[], CUR=null, BUSY=false, FILTER='', COLLAPSED=false;
  var ATTACH=null;   // {name, text}

  function getKey(){
    var k=null; try{ k=localStorage.getItem('c2a_key'); }catch(e){}
    if(k) return k;
    return (KEY && KEY.indexOf('__C2A_KEY')!==0) ? KEY : '';
  }
  function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }

  /* ---------------- Markdown 轻量渲染（代码块/粗体/列表/行内码/标题） --------------- */
  function md(src){
    var s=esc(src);
    // 代码块
    var blocks=[];
    s=s.replace(/```(\w*)\n?([\s\S]*?)```/g,function(_,lang,code){
      blocks.push('<pre><code>'+code.replace(/\n$/,'')+'</code></pre>');
      return '\u0000B'+(blocks.length-1)+'\u0000';
    });
    // 标题
    s=s.replace(/^### (.+)$/gm,'<h3>$1</h3>')
       .replace(/^## (.+)$/gm,'<h2>$1</h2>')
       .replace(/^# (.+)$/gm,'<h1>$1</h1>');
    // 引用
    s=s.replace(/^&gt; (.+)$/gm,'<blockquote>$1</blockquote>');
    // 列表
    s=s.replace(/^\s*[-*+] (.+)$/gm,'<li>$1</li>')
       .replace(/^\s*\d+\. (.+)$/gm,'<li>$1</li>');
    s=s.replace(/(<li>[\s\S]*?<\/li>)(?!\s*<li>)/g,'<ul>$1</ul>');
    // 行内代码、粗体、斜体
    s=s.replace(/`([^`\n]+)`/g,'<code>$1</code>')
       .replace(/\*\*([^*\n]+)\*\*/g,'<b>$1</b>')
       .replace(/(^|[^*])\*([^*\n]+)\*/g,'$1<i>$2</i>');
    // 段落
    s=s.split(/\n{2,}/).map(function(p){
      if(/^\s*<(h[123]|ul|ol|pre|blockquote)/.test(p)) return p;
      return '<p>'+p.replace(/\n/g,'<br>')+'</p>';
    }).join('');
    // 还原代码块
    s=s.replace(/\u0000B(\d+)\u0000/g,function(_,i){ return blocks[+i]; });
    return s;
  }

  /* ---------------- 会话存储 ---------------- */
  function load(){
    try{ CONVS=JSON.parse(localStorage.getItem('c2a_convs')||'[]'); }catch(e){ CONVS=[]; }
    if(!CONVS.length){ newConv(true); }
    else{
      CUR = (localStorage.getItem('c2a_cur') && CONVS.some(function(c){return c.id===localStorage.getItem('c2a_cur');}))
        ? localStorage.getItem('c2a_cur') : CONVS[0].id;
    }
    COLLAPSED = localStorage.getItem('c2a_sb_collapsed')==='1';
    applyCollapse();
    renderConvs(); renderMsgs(); loadModels();
  }
  function save(){
    try{
      localStorage.setItem('c2a_convs', JSON.stringify(CONVS.slice(0,60)));
      if(CUR) localStorage.setItem('c2a_cur', CUR);
    }catch(e){}
  }
  function curConv(){ for(var i=0;i<CONVS.length;i++) if(CONVS[i].id===CUR) return CONVS[i]; return null; }

  function newConv(silent){
    var c={id:''+Date.now()+Math.floor(Math.random()*999),title:'新对话',msgs:[],ts:Date.now()};
    CONVS.unshift(c); CUR=c.id; save();
    if(!silent){
      renderConvs(); renderMsgs();
      // 新会话时确保模型下拉可用（否则发送时取到空值导致请求失败）
      var sel=document.getElementById('model');
      if(sel && !sel.options.length) loadModels();
      IN.focus();
    }
    return c;
  }

  function applyCollapse(){
    var sb=document.getElementById('sidebar'), open=document.getElementById('btn-open-side');
    if(COLLAPSED){ sb.classList.add('collapsed'); open.style.display='inline-flex'; }
    else{ sb.classList.remove('collapsed'); open.style.display='none'; }
  }

  /* ---------------- 侧栏渲染（按时间分组） ---------------- */
  function dayKey(ts){
    var d=new Date(ts), n=new Date();
    var sameDay = d.toDateString()===n.toDateString();
    if(sameDay) return '今天';
    var y=new Date(n.getTime()-86400000);
    if(d.toDateString()===y.toDateString()) return '昨天';
    if(n-d < 7*86400000) return '7天内';
    return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0');
  }
  function renderConvs(){
    var box=document.getElementById('conv-scroll');
    var list=CONVS.slice();
    if(FILTER) list=list.filter(function(c){ return (c.title||'').indexOf(FILTER)>=0; });
    if(!list.length){
      box.innerHTML='<div class="grp-empty">'+(FILTER?'没有匹配的对话':'还没有对话')+'</div>';
      return;
    }
    var groups={}, order=[];
    list.forEach(function(c){
      var k=dayKey(c.ts||Date.now());
      if(!groups[k]){ groups[k]=[]; order.push(k); }
      groups[k].push(c);
    });
    var h='';
    order.forEach(function(k){
      h+='<div class="grp-date">'+esc(k)+'</div>';
      groups[k].forEach(function(c){
        h+='<div class="conv '+(c.id===CUR?'on':'')+'" data-id="'+c.id+'">'
          +'<span class="t">'+esc(c.title||'新对话')+'</span>'
          +'<button class="more" title="更多" data-menu="'+c.id+'">⋯</button></div>';
      });
    });
    box.innerHTML=h;
    box.querySelectorAll('.conv').forEach(function(el){
      el.onclick=function(e){
        if(e.target.dataset.menu) return;
        CUR=el.dataset.id; save(); renderConvs(); renderMsgs();
        document.getElementById('chat-title').textContent=(curConv()||{}).title||'新对话';
      };
    });
    box.querySelectorAll('.more').forEach(function(b){
      b.onclick=function(e){ e.stopPropagation(); convMenu(b.dataset.menu, b); };
    });
  }

  function convMenu(id){
    var c=null; CONVS.forEach(function(x){ if(x.id===id) c=x; });
    if(!c) return;
    var cur=c.title;
    var act=prompt('重命名对话（留空则删除该对话）', cur);
    if(act===null) return;
    if(act.trim()===''){ delConv(id); return; }
    c.title=act.trim().slice(0,40); save(); renderConvs();
    if(id===CUR) document.getElementById('chat-title').textContent=c.title;
  }
  function delConv(id){
    if(!confirm('删除该对话？')) return;
    CONVS=CONVS.filter(function(c){ return c.id!==id; });
    if(CUR===id) CUR=CONVS.length?CONVS[0].id:null;
    if(!CONVS.length) newConv(true);
    save(); renderConvs(); renderMsgs();
  }

  /* ---------------- 消息渲染 ---------------- */
  function welcome(){
    M.innerHTML='<div id="welcome" style="display:flex;align-items:center;justify-content:center;'
      +'padding:12vh 20px 0"><div style="text-align:center">'
      +'<div style="font-size:26px;font-weight:600;letter-spacing:-.5px;margin-bottom:10px">'
      +'有什么可以帮忙的？</div>'
      +'<div style="color:#a8a29e;font-size:13.5px">在下方输入框发送消息，Enter 发送，Shift+Enter 换行</div>'
      +'</div></div>';
  }

  function actions(role, idx, content, liked){
    var h='<div class="acts">';
    h+='<button class="act" data-do="copy" data-i="'+idx+'" title="复制">'
      +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"></rect><path d="M5 15V5a2 2 0 012-2h10"></path></svg></button>';
    if(role==='user'){
      h+='<button class="act" data-do="edit" data-i="'+idx+'" title="编辑并重新发送">'
        +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4L20 8l-4-4L4 16v4z"></path></svg></button>';
    }else{
      h+='<button class="act" data-do="regen" data-i="'+idx+'" title="重新生成">'
        +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 11-3-6.7"></path><path d="M21 3v6h-6"></path></svg></button>';
      h+='<button class="act '+(liked===1?'on':'')+'" data-do="like" data-i="'+idx+'" title="赞">'
        +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 10v10H4V10h3zm0 0l4-7a2 2 0 013 2v3h5a2 2 0 012 2.3l-1.2 7A2 2 0 0117 21H7"></path></svg></button>';
      h+='<button class="act '+(liked===-1?'on':'')+'" data-do="dislike" data-i="'+idx+'" title="踩">'
        +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 14V4h3v10h-3zm0 0l-4 7a2 2 0 01-3-2v-3H5a2 2 0 01-2-2.3l1.2-7A2 2 0 016 3h11"></path></svg></button>';
      h+='<button class="act" data-do="tts" data-i="'+idx+'" title="朗读">'
        +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5L6 9H3v6h3l5 4V5z"></path><path d="M16 9a4 4 0 010 6"></path></svg></button>';
      h+='<button class="act" data-do="share" data-i="'+idx+'" title="分享（复制该回复）">'
        +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4"></path></svg></button>';
    }
    h+='</div>';
    return h;
  }

  function renderMsgs(){
    var c=curConv();
    document.getElementById('chat-title').textContent=(c&&c.title)||'新对话';
    if(!c||!c.msgs.length){ welcome(); return; }
    var h='';
    c.msgs.forEach(function(m,i){
      if(m.role==='user'){
        h+='<div class="b-u"><div class="bub">'+esc(m.content)+'</div>'
          +actions('user',i,m.content)+'</div>';
      }else{
        h+='<div class="b-a"><div class="inner">';
        if(m.think){
          h+='<button class="think-btn" data-think="'+i+'">'
            +'<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M9 6l6 6-6 6"></path></svg>'
            +'已思考'+(m.secs?('（用时 '+m.secs+' 秒）'):'')+'</button>'
            +'<div class="think-body" id="think-'+i+'">'+esc(m.think)+'</div>';
        }
        h+='<div class="hd">ChatGPT</div>'
          +'<div class="ct">'+(m.err?esc(m.content):md(m.content))+'</div>'
          +actions('assistant',i,m.content,m.liked)+'</div></div>';
      }
    });
    M.innerHTML=h;
    M.querySelectorAll('.think-btn').forEach(function(b){
      b.onclick=function(){
        var el=document.getElementById('think-'+b.dataset.think);
        if(el) el.classList.toggle('on');
      };
    });
    M.querySelectorAll('.act').forEach(function(b){
      b.onclick=function(){ doAct(b.dataset.do, +b.dataset.i); };
    });
    M.scrollTop=M.scrollHeight;
  }

  function doAct(kind, i){
    var c=curConv(); if(!c) return;
    var m=c.msgs[i]; if(!m) return;
    if(kind==='copy'||kind==='share'){
      navigator.clipboard.writeText(m.content).then(function(){
        toast(kind==='share'?'已复制该回复':'已复制');
      }).catch(function(){ toast('复制失败'); });
      return;
    }
    if(kind==='like'||kind==='dislike'){
      m.liked = (kind==='like') ? (m.liked===1?0:1) : (m.liked===-1?0:-1);
      save(); renderMsgs(); return;
    }
    if(kind==='tts'){
      try{
        speechSynthesis.cancel();
        var u=new SpeechSynthesisUtterance(m.content.slice(0,1200));
        u.lang='zh-CN'; speechSynthesis.speak(u);
        toast('正在朗读…');
      }catch(e){ toast('当前浏览器不支持朗读'); }
      return;
    }
    if(kind==='regen'){
      if(BUSY) return;
      // 删掉这条 assistant 及其后所有消息，用最后一条 user 重发
      var lastUser=-1;
      for(var k=i;k>=0;k--){ if(c.msgs[k].role==='user'){ lastUser=k; break; } }
      if(lastUser<0) return;
      c.msgs=c.msgs.slice(0,lastUser+1);
      save(); renderMsgs();
      send(true);
      return;
    }
    if(kind==='edit'){
      if(BUSY) return;
      var nv=prompt('编辑后重新发送：', m.content);
      if(nv===null||!nv.trim()) return;
      c.msgs=c.msgs.slice(0,i);
      c.msgs.push({role:'user',content:nv.trim()});
      if(c.title==='新对话') c.title=nv.trim().slice(0,24);
      save(); renderMsgs(); renderConvs();
      send(true);
      return;
    }
  }

  function toast(t){
    var d=document.createElement('div');
    d.textContent=t;
    d.style.cssText='position:fixed;left:50%;bottom:90px;transform:translateX(-50%);'
      +'background:rgba(28,25,23,.92);color:#fff;padding:8px 16px;border-radius:10px;'
      +'font-size:13px;z-index:99999;pointer-events:none';
    document.body.appendChild(d);
    setTimeout(function(){ d.remove(); },1500);
  }

  function typing(on){
    var t=document.getElementById('typing');
    if(on&&!t){
      t=document.createElement('div'); t.id='typing';
      t.innerHTML='<div class="b-a"><div class="inner"><div class="hd">ChatGPT</div>'
        +'<div style="display:inline-flex;gap:5px;padding:8px 0">'
        +'<i style="width:8px;height:8px;border-radius:50%;background:#0d0d0d;opacity:.25;animation:tp 1.2s infinite"></i>'
        +'<i style="width:8px;height:8px;border-radius:50%;background:#0d0d0d;opacity:.25;animation:tp 1.2s infinite;animation-delay:.2s"></i>'
        +'<i style="width:8px;height:8px;border-radius:50%;background:#0d0d0d;opacity:.25;animation:tp 1.2s infinite;animation-delay:.4s"></i>'
        +'</div></div></div>';
      if(!document.getElementById('tpkf')){
        var st=document.createElement('style'); st.id='tpkf';
        st.textContent='@keyframes tp{0%,60%,100%{opacity:.25}30%{opacity:.85}}'; document.head.appendChild(st);
      }
      M.appendChild(t); M.scrollTop=M.scrollHeight;
    }
    if(!on&&t) t.remove();
  }

  /* ---------------- 模型 ---------------- */
  async function loadModels(retry){
    retry = retry || 0;
    try{
      var r=await fetch('/v1/models',{headers:{'Authorization':'Bearer '+getKey()},cache:'no-store'});
      if(!r.ok) throw new Error('HTTP '+r.status);
      var j=await r.json();
      var off=[];
      try{ off=JSON.parse(localStorage.getItem('c2a-model-off')||'[]'); }catch(e){}
      var ids=(j.data||[]).map(function(m){return m.id;})
        .filter(function(i){ return off.indexOf(i)<0; });
      if(!ids.length) throw new Error('空列表');
      var sel=document.getElementById('model');
      var prev=sel.value;
      sel.innerHTML=ids.map(function(i){return '<option value="'+esc(i)+'">'+esc(i)+'</option>';}).join('');
      // 保留用户上次选择；没有就优先 auto
      if(prev && ids.indexOf(prev)>=0) sel.value=prev;
      else sel.value = ids.indexOf('auto')>=0 ? 'auto' : ids[0];
      sel.dataset.ready='1';
    }catch(e){
      // 失败时至少给一个可用项，绝不让下拉为空（否则发送时字串为空导致请求失败）
      var sel2=document.getElementById('model');
      if(!sel2.options.length || !sel2.value){
        sel2.innerHTML='<option value="auto">auto</option>';
        sel2.value='auto';
      }
      sel2.dataset.ready='1';
      if(retry < 3) setTimeout(function(){ loadModels(retry+1); }, 1500*(retry+1));
    }
  }
  // 保证 model 取值永远有效
  function modelValue(){
    var sel=document.getElementById('model');
    var v=(sel&&sel.value||'').trim();
    if(v) return v;
    // 兜底：从 DOM 里挑第一个可用的
    if(sel&&sel.options.length) return sel.options[0].value;
    return 'auto';
  }

  /* ---------------- 发送 ---------------- */
  async function send(isRetry){
    if(BUSY) return;
    var c=curConv();
    if(!c){ c=newConv(true); CUR=c.id; }   // 没有会话就现建一个，避免静默失败
    var q=IN.value.trim();
    if(!q && !isRetry) return;
    if(q){
      var payload=q;
      if(ATTACH){
        payload = q + '\n\n【附件 '+ATTACH.name+'】\n' + ATTACH.text.slice(0,12000);
        ATTACH=null;
      }
      c.msgs.push({role:'user',content:payload});
      IN.value=''; IN.style.height='auto';
      if(c.title==='新对话') c.title=q.slice(0,24);
      save(); renderConvs();
    }
    renderMsgs();
    BUSY=true;
    document.getElementById('send').disabled=true;
    typing(true);
    var model=modelValue();
    var deep=document.getElementById('pill-think').classList.contains('on');
    var search=document.getElementById('pill-search').classList.contains('on');
    var t0=Date.now();
    var ctl=new AbortController();
    var timer=setTimeout(function(){ ctl.abort(); }, 180000);
    var text='', think2='';
    try{
      var msgs=c.msgs.map(function(m){ return {role:m.role,content:m.content}; });
      if(search){
        msgs.unshift({role:'system',content:
          '你可以使用联网检索的思路回答：先给出结论，再补充关键信息来源与时效性说明。'});
      }
      var r=await fetch('/v1/chat/completions',{method:'POST',signal:ctl.signal,
        headers:{'Content-Type':'application/json','Authorization':'Bearer '+getKey()},
        body:JSON.stringify({model:model,stream:true,
          thinking: deep?'detailed':'auto', messages:msgs})});
      if(!r.ok){
        var msg='HTTP '+r.status;
        try{ var j0=await r.json(); msg=(j0.error&&j0.error.message)||msg; }catch(e){}
        throw new Error(msg);
      }
      var rd=r.body.getReader(), dec=new TextDecoder(), buf='';
      for(;;){
        var ch=await rd.read();
        if(ch.done) break;
        buf+=dec.decode(ch.value,{stream:true});
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
        throw new Error('上游返回空内容——当前出口节点可能被风控，请到「代理设定」换节点后点重新生成');
      }
      var secs=Math.max(1, Math.round((Date.now()-t0)/1000));
      c.msgs.push({role:'assistant',content:text,think:think2||null,secs:secs,liked:0});
      document.getElementById('stat').textContent=secs+'s · '+text.length+' 字';
    }catch(e){
      var tip=(e.name==='AbortError')
        ? '请求超时（180 秒）——出口节点可能被风控，请换节点后点重新生成'
        : e.message;
      c.msgs.push({role:'assistant',content:'⚠ '+tip,err:true});
    }finally{
      clearTimeout(timer);
      BUSY=false;
      document.getElementById('send').disabled=false;
      typing(false);
      save(); renderMsgs(); renderConvs();
      IN.focus();
    }
  }

  /* ---------------- 事件 ---------------- */
  document.getElementById('send').onclick=function(){ send(); };
  document.getElementById('btn-new').onclick=function(){ newConv(); };
  document.getElementById('btn-collapse').onclick=function(){
    COLLAPSED=true; try{localStorage.setItem('c2a_sb_collapsed','1');}catch(e){} applyCollapse();
    window.dispatchEvent(new Event('resize'));
  };
  document.getElementById('btn-open-side').onclick=function(){
    COLLAPSED=false; try{localStorage.setItem('c2a_sb_collapsed','0');}catch(e){} applyCollapse();
    window.dispatchEvent(new Event('resize'));
  };
  document.getElementById('btn-search').onclick=function(){
    var w=document.getElementById('search-wrap');
    w.classList.toggle('on');
    if(w.classList.contains('on')) document.getElementById('search-input').focus();
    else { FILTER=''; document.getElementById('search-input').value=''; renderConvs(); }
  };
  document.getElementById('search-input').oninput=function(e){
    FILTER=e.target.value.trim(); renderConvs();
  };
  document.getElementById('btn-clear-all').onclick=function(){
    if(!confirm('清空全部对话记录？此操作不可恢复。')) return;
    CONVS=[]; try{localStorage.removeItem('c2a_convs');localStorage.removeItem('c2a_cur');}catch(e){}
    newConv(true); CUR=CONVS[0].id; save(); renderConvs(); renderMsgs();
  };
  document.getElementById('btn-share').onclick=function(){
    var c=curConv(); if(!c||!c.msgs.length){ toast('还没有内容可分享'); return; }
    var txt=c.msgs.map(function(m){ return (m.role==='user'?'我：':'ChatGPT：')+m.content; }).join('\n\n');
    navigator.clipboard.writeText(txt).then(function(){ toast('对话全文已复制'); })
      .catch(function(){ toast('复制失败'); });
  };
  document.getElementById('pill-think').onclick=function(){
    this.classList.toggle('on');
    toast(this.classList.contains('on')?'已开启深度思考':'已关闭深度思考');
  };
  document.getElementById('pill-search').onclick=function(){
    this.classList.toggle('on');
    toast(this.classList.contains('on')?'已开启智能搜索':'已关闭智能搜索');
  };
  document.getElementById('attach').onclick=function(){
    document.getElementById('file-input').click();
  };
  document.getElementById('file-input').onchange=function(e){
    var f=e.target.files&&e.target.files[0];
    if(!f) return;
    var rd=new FileReader();
    rd.onload=function(){
      ATTACH={name:f.name,text:String(rd.result||'')};
      toast('已添加附件：'+f.name+'（随下条消息发送）');
      var t=document.getElementById('tip');
      t.textContent='附件：'+f.name+'　内容由 AI 生成，请仔细甄别';
    };
    rd.readAsText(f);
    e.target.value='';
  };
  IN.addEventListener('keydown',function(e){
    if(e.key==='Enter'&&!e.shiftKey){ e.preventDefault(); send(); }
  });
  IN.addEventListener('input',function(){
    IN.style.height='auto';
    IN.style.height=Math.min(IN.scrollHeight,190)+'px';
  });

  load();
})();
</script>
"""
