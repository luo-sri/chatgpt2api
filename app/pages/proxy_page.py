# -*- coding: utf-8 -*-
"""代理设定页（纯手动模式）

按用户要求：
  · 取消「自动选择（URLTest）」——不再有任何自动挑节点的行为
  · 只能手动选择出口节点；切换后以手动选择为准，不会自己变
  · 默认节点：🇺🇸 IEPL-美国-03；用户切过就以最后一次为准（落盘持久化）
  · 只展示真正生效的链路（ChatGPT → 节点选择 → 具体节点），不再显示
    与手动选择无关的 URLTest 组（之前它显示香港，造成"换了 IP 还显示香港"）
"""

PROXY_BODY = """
<div style="flex:1;padding-top:4px">
  <div style="max-width:900px;margin:0 auto;padding:0 8px">

    <div class="card">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
        <b style="font-size:14px">当前代理状态</b>
        <button class="btn btn-ghost" style="padding:5px 12px;font-size:12px" onclick="load()">刷新</button>
      </div>
      <div id="status"><span class="mut">加载中…</span></div>
      <div class="mut" style="font-size:11.5px;padding-top:10px;border-top:1px solid rgba(28,25,23,.06);margin-top:10px">
        当前为<b>纯手动模式</b>：出口节点只在下方手动切换，切换后不会被自动更改。
      </div>
    </div>

    <div class="card">
      <b style="font-size:14px">选择出口节点</b>
      <p class="mut" style="margin:4px 0 12px">
        点节点名立即切换；可拖动调整显示顺序（仅影响这里的排列，不影响你的选择）。
      </p>
      <div id="groups"><span class="mut">加载中…</span></div>
    </div>

    <div class="card">
      <div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:12px">
        <b style="font-size:14px">节点列表</b><span style="flex:1"></span>
        <button class="btn btn-ghost" style="padding:7px 14px;font-size:12.5px" onclick="__restore()">恢复已删除</button>
        <button class="btn btn-dark" style="padding:7px 14px;font-size:12.5px" onclick="testAll()">全部测速</button>
      </div>
      <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead><tr style="text-align:left;font-size:11.5px;color:#a8a29e;
            border-bottom:1px solid rgba(28,25,23,.08)">
            <th style="padding:8px 10px 8px 0">节点</th>
            <th style="padding:8px">延迟</th>
            <th style="padding:8px">状态</th>
            <th style="padding:8px;text-align:right">操作</th>
          </tr></thead>
          <tbody id="nodes"><tr><td colspan="4" class="mut" style="padding:14px 0">加载中…</td></tr></tbody>
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
  var GROUPS=[], NODES=[], CURRENT='';
  var KEY='__C2A_KEY__';
  function key(){
    var k=null; try{ k=localStorage.getItem('c2a_key'); }catch(e){}
    if(k) return k;
    return (KEY && KEY.indexOf('__C2A_KEY')!==0) ? KEY : '';
  }
  function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function isNode(n){ return !/剩余流量|套餐到期|距离下次|官网|过期/.test(n.name); }
  async function api(p,o){
    var r=await fetch(p,Object.assign({cache:'no-store'},o||{}));
    return r.json();
  }
  function show(s){ document.getElementById('msg').textContent=s||''; }

  async function load(){
    var d=await api('/p/api/proxy');
    GROUPS=d.groups||[]; NODES=(d.nodes||[]).filter(isNode);
    // 只认「节点选择」组的 now —— 这才是真正生效的出口；
    // 不再读取「自动选择」(URLTest)，它和手动选择无关。
    CURRENT='';
    GROUPS.forEach(function(g){ if(g.name==='节点选择') CURRENT=g.now||''; });
    renderStatus(d); renderGroups(); renderNodes();
  }

  function renderStatus(d){
    var h='';
    // ChatGPT 组（固定指向 节点选择）
    var chatG=null, selG=null;
    GROUPS.forEach(function(g){ if(g.name==='ChatGPT') chatG=g; if(g.name==='节点选择') selG=g; });
    h+='<div class="prow"><span class="mut">代理链路</span>'
      +'<b>'+(chatG?esc(chatG.now):'—')+' → 手动指定</b></div>';

    h+='<div class="prow" style="align-items:center">'
      +'<span class="mut">出口节点</span>'
      +'<select class="inp" style="width:auto;max-width:280px;font-size:12.5px;padding:6px 10px"'
      +' onchange="window.__pick(this.value)" title="选择后立即生效，且不会被自动更改">'
      + NODES.map(function(n){
          return '<option value="'+esc(n.name)+'"'+(n.name===CURRENT?' selected':'')+'>'
            + esc(n.name)+(n.delay?(' · '+n.delay+'ms'):'')+'</option>';
        }).join('')
      +'</select></div>';

    var cls=d.delay==null?'warn':(d.delay<400?'ok':(d.delay<900?'warn':'bad'));
    h+='<div class="prow"><span class="mut">ChatGPT 延迟</span>'
      +'<b class="'+cls+'">'+(d.delay==null?'测不出':d.delay+' ms')+'</b></div>';
    if(d.exit_ip){
      h+='<div class="prow"><span class="mut">出口 IP / 地区</span>'
        +'<b>'+esc(d.exit_ip)+' '+esc(d.exit_loc||'')+'</b></div>';
    }
    document.getElementById('status').innerHTML=h;
  }

  var order=[];
  try{ order=JSON.parse(localStorage.getItem('c2a_grp_order')||'[]'); }catch(e){}

  function renderGroups(){
    var list=NODES.slice();
    if(order.length){
      list.sort(function(a,b){
        var ia=order.indexOf(a.name), ib=order.indexOf(b.name);
        return (ia<0?9e9:ia)-(ib<0?9e9:ib);
      });
    }
    var box=document.getElementById('groups');
    var h='<div id="grpOrder" style="display:flex;flex-wrap:wrap;gap:8px">';
    if(!list.length){
      h+='<span class="mut">没有可用节点（请检查订阅）</span>';
    }else{
      list.forEach(function(n){
        var cls=n.delay==null?'mut':(n.delay<400?'ok':(n.delay<900?'warn':'bad'));
        h+='<button class="btn '+(n.name===CURRENT?'btn-dark':'btn-ghost')
          +' grp-item" draggable="true" data-name="'+esc(n.name)+'"'
          +' style="padding:6px 13px;font-size:12.5px;cursor:grab"'
          +' onclick="if(!window.__dragLock)window.__pick(\''+esc(n.name)+'\')"'
          +' title="点击切换 · 可拖动调整顺序">'
          + esc(n.name)+' <span class="'+cls+'" style="font-size:11px">'
          + (n.delay==null?'—':n.delay+'ms')+'</span></button>';
      });
    }
    h+='</div>';
    box.innerHTML=h;
    bindDrag();
  }

  function bindDrag(){
    var box=document.getElementById('grpOrder');
    if(!box||box.dataset.bound) return;
    box.dataset.bound='1';
    var dragged=null;
    box.addEventListener('dragstart',function(e){
      var b=e.target.closest('.grp-item'); if(!b) return;
      dragged=b; e.dataTransfer.effectAllowed='move';
      setTimeout(function(){ b.style.opacity='.4'; },0);
      window.__dragLock=false;
    });
    box.addEventListener('dragover',function(e){
      e.preventDefault();
      if(!dragged) return;
      var els=[].slice.call(box.querySelectorAll('.grp-item')).filter(function(x){ return x!==dragged; });
      var after=null;
      for(var i=0;i<els.length;i++){
        var r=els[i].getBoundingClientRect();
        if(e.clientY < r.top + r.height/2){ after=els[i]; break; }
      }
      if(after) box.insertBefore(dragged, after); else box.appendChild(dragged);
    });
    box.addEventListener('drop',function(e){
      e.preventDefault();
      window.__dragLock=true;
      setTimeout(function(){ window.__dragLock=false; },200);
    });
    box.addEventListener('dragend',function(){
      if(!dragged) return;
      dragged.style.opacity='';
      var names=[].slice.call(box.querySelectorAll('.grp-item')).map(function(b){ return b.dataset.name; });
      try{ localStorage.setItem('c2a_grp_order', JSON.stringify(names)); }catch(e){}
      try{
        fetch('/p/api/proxy/grp-order',{method:'POST',cache:'no-store',
          headers:{'Content-Type':'application/json'},body:JSON.stringify({order:names})});
      }catch(e){}
      dragged=null;
    });
  }

  function renderNodes(){
    var tb=document.getElementById('nodes');
    if(!NODES.length){ tb.innerHTML='<tr><td colspan="4" class="mut" style="padding:14px 0">无节点</td></tr>'; return; }
    tb.innerHTML=NODES.map(function(n){
      var sel=(n.name===CURRENT);
      var cls=n.delay==null?'mut':(n.delay<400?'ok':(n.delay<900?'warn':'bad'));
      return '<tr style="'+(sel?'background:rgba(28,25,23,.05);':'')
        +'border-bottom:1px solid rgba(28,25,23,.05)">'
        +'<td style="padding:9px 10px 9px 0"><b'+(sel?' class="ok"':'')+'>'+esc(n.name)+'</b>'
        +(sel?' <span class="ok" style="font-size:11px">当前</span>':'')+'</td>'
        +'<td class="'+cls+'" style="padding:9px 8px">'+(n.delay==null?'—':n.delay+' ms')+'</td>'
        +'<td style="padding:9px 8px">'+(n.alive?'<span class="ok">可用</span>':'<span class="bad">不可用</span>')+'</td>'
        +'<td style="padding:9px 8px;text-align:right;white-space:nowrap">'
        +'<button class="btn btn-ghost" style="padding:4px 11px;font-size:12px"'
        +' onclick="window.__pick(\''+esc(n.name)+'\')">'+(sel?'使用中':'使用')+'</button> '
        +'<button class="btn btn-ghost" style="padding:4px 9px;font-size:12px;color:#b91c1c;'
        +'border-color:rgba(185,28,28,.25)" title="从列表删除该节点（可恢复）"'
        +' onclick="window.__del(\''+esc(n.name)+'\')">删除</button></td></tr>';
    }).join('');
  }

  window.__del=async function(name){
    if(!name) return;
    if(!confirm('从列表移除节点：'+name+'\n（不会影响订阅，可随时恢复）')) return;
    var r=await api('/p/api/proxy/remove-node',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({node:name})});
    if(r.ok){ show('已移除 '+name+'（可在「已删除节点」里恢复）'); await load(); }
    else show('移除失败：'+(r.error||''));
  };

  window.__restore=async function(){
    var r=await api('/p/api/proxy/removed');
    var list=(r&&r.removed)||[];
    if(!list.length){ show('没有已删除的节点'); return; }
    var pick=prompt('已删除的节点（输入名称恢复，输入 all 全部恢复）：\n\n'+list.join('\n'), 'all');
    if(pick===null) return;
    if(pick.trim().toLowerCase()==='all'){
      for(var i=0;i<list.length;i++){
        await api('/p/api/proxy/remove-node',{method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({node:list[i],undo:true})});
      }
      show('已恢复全部 '+list.length+' 个节点'); await load(); return;
    }
    if(list.indexOf(pick.trim())<0){ show('没有这个节点'); return; }
    var r2=await api('/p/api/proxy/remove-node',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({node:pick.trim(),undo:true})});
    if(r2.ok){ show('已恢复 '+pick.trim()); await load(); }
    else show('恢复失败：'+(r2.error||''));
  };

  window.__pick=async function(name){
    if(!name) return;
    show('切换中…');
    var r=await api('/p/api/proxy/select',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({node:name})});
    if(r.ok){ show('已切换到 '+name+'（已记住，不会被自动更改）'); await load(); }
    else show('切换失败：'+(r.error||'未知错误'));
  };

  window.testAll=async function(){
    show('测速中，请稍候…');
    var r=await api('/p/api/proxy/test',{method:'POST',
      headers:{'Content-Type':'application/json'},body:'{}'});
    if(r.ok){ show('测速完成'); await load(); }
    else show('测速失败：'+(r.error||''));
  };

  window.updateSub=async function(){
    var u=document.getElementById('suburl').value.trim();
    if(!u){ show('请先填订阅链接'); return; }
    var b=document.getElementById('subbtn');
    b.disabled=true; b.textContent='更新中…';
    var r=await api('/p/api/subscription',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({url:u})});
    b.disabled=false; b.textContent='更新订阅';
    show(r.ok?('更新成功，解析 '+(r.nodes||0)+' 个节点'):('失败：'+(r.error||'')));
    if(r.ok) setTimeout(load,1200);
  };

  window.loadSub=async function(){
    var d=await api('/p/api/subscription');
    if(d.url){ document.getElementById('suburl').value=d.url; show('已读取上次保存的链接'); }
    else show('尚未保存过订阅链接');
  };

  load();
})();
</script>
"""
