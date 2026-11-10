# -*- coding: utf-8 -*-
"""版本面板 + 内置更新 UI（所有页面共用）

为什么要单独抽一个模块：
  这套面板同时存在两类页面 ——
    1. 我们自己的页面（/p/chat、/p/proxy、/p/oauth），由 webui.native_shell 渲染
    2. 面板原生页面（/accounts、/logs、/settings…），由网关 inject_navbar 注入
  两类页面的顶栏结构不同，但「点版本号看更新内容 + 一键更新」的行为要一致，
  所以把这段 JS 抽出来，两边各自注入一次。

设计要点：
  · 弹窗常驻，不会像 toast 那样 2.6 秒就消失
  · 可反复打开，点右上角 × 或按 ESC 或点遮罩关闭
  · 面板原生页的版本按钮是 React 的，用「捕获阶段」拦下点击，
    我们的弹窗先弹出，并阻止 React 自己的 onClick
  · 有新版时可以直接在项目内更新（下载 → 校验 → 替换代码 → 自动重启），
    不碰 data/ 目录，用户配置不丢
"""

_TEMPLATE = r"""<script>
(function(){
  if (window.__c2aUpdateUI) return;
  window.__c2aUpdateUI = 1;

  var CUR = '__C2A_CUR__';
  var REPO_API = '__C2A_REPO_API__';
  var REPO_URL = '__C2A_REPO_URL__';
  var RAW_VER = '__C2A_RAW_VER__';
  var RAW_LOG = '__C2A_RAW_LOG__';

  var modal = null;

  /* ---------------- 样式 ---------------- */
  function ensureCss(){
    if (document.getElementById('c2a-up-css')) return;
    var st = document.createElement('style');
    st.id = 'c2a-up-css';
    st.textContent = ''
      + '.c2a-up-mask{position:fixed;inset:0;z-index:2147482000;background:rgba(15,12,10,.5);'
      + 'display:flex;align-items:center;justify-content:center;padding:20px;'
      + 'backdrop-filter:blur(2px)}'
      + '.c2a-up-card{width:min(580px,94vw);max-height:86vh;display:flex;flex-direction:column;'
      + 'background:#fff;border-radius:18px;overflow:hidden;'
      + 'box-shadow:0 30px 80px -20px rgba(0,0,0,.45);'
      + 'font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}'
      + '.c2a-up-head{display:flex;align-items:center;gap:10px;padding:18px 22px;'
      + 'border-bottom:1px solid #f0efed}'
      + '.c2a-up-title{font-size:15.5px;font-weight:650;color:#1c1917;flex:1}'
      + '.c2a-up-x{border:0;background:transparent;color:#a8a29e;font-size:20px;line-height:1;'
      + 'cursor:pointer;padding:2px 6px;border-radius:6px}'
      + '.c2a-up-x:hover{background:#f5f5f4;color:#1c1917}'
      + '.c2a-up-body{padding:18px 22px;overflow:auto;font-size:13px;line-height:1.75;color:#44403c}'
      + '.c2a-up-rows{display:flex;gap:22px;flex-wrap:wrap;margin-bottom:14px;'
      + 'padding:12px 14px;background:#fafaf9;border-radius:10px;font-size:12.5px}'
      + '.c2a-up-rows b{color:#1c1917;font-weight:600}'
      + '.c2a-up-tag{display:inline-block;padding:1px 8px;border-radius:999px;'
      + 'font-size:11.5px;background:#dcfce7;color:#15803d;margin-left:6px}'
      + '.c2a-up-tag.gray{background:#f5f5f4;color:#78716c}'
      + '.c2a-up-notes{white-space:pre-wrap;word-break:break-word;font-size:12.5px;'
      + 'line-height:1.85;color:#57534e;max-height:38vh;overflow:auto;'
      + 'background:#fafaf9;border-radius:10px;padding:12px 14px}'
      + '.c2a-up-foot{display:flex;align-items:center;gap:10px;padding:14px 22px;'
      + 'border-top:1px solid #f0efed;background:#fcfcfb}'
      + '.c2a-up-btn{border:0;border-radius:10px;padding:9px 16px;font-size:13px;'
      + 'cursor:pointer;font-family:inherit;transition:.15s}'
      + '.c2a-up-btn.primary{background:#1c1917;color:#fff}'
      + '.c2a-up-btn.primary:hover{background:#292524}'
      + '.c2a-up-btn.primary:disabled{background:#d6d3d1;cursor:not-allowed}'
      + '.c2a-up-btn.ghost{background:transparent;color:#78716c}'
      + '.c2a-up-btn.ghost:hover{background:#f5f5f4;color:#1c1917}'
      + '.c2a-up-msg{flex:1;font-size:12.5px;color:#78716c;min-height:18px}'
      + '.c2a-up-msg.ok{color:#16a34a}.c2a-up-msg.bad{color:#dc2626}'
      + '.dark .c2a-up-card{background:#1c1917}'
      + '.dark .c2a-up-head,.dark .c2a-up-foot{border-color:#292524;background:#171412}'
      + '.dark .c2a-up-title{color:#f5f5f4}'
      + '.dark .c2a-up-body{color:#d6d3d1}'
      + '.dark .c2a-up-rows,.dark .c2a-up-notes{background:#12100e;color:#a8a29e}'
      + '.dark .c2a-up-rows b{color:#e7e5e4}'
      + '.dark .c2a-up-btn.primary{background:#f5f5f4;color:#1c1917}'
      + '.dark .c2a-up-btn.primary:hover{background:#e7e5e4}'
      + '.dark .c2a-up-btn.ghost{color:#a8a29e}'
      + '.dark .c2a-up-btn.ghost:hover{background:#292524;color:#f5f5f4}'
      + '.dark .c2a-up-x{color:#78716c}'
      + '.dark .c2a-up-x:hover{background:#292524;color:#f5f5f4}'
      + '.dark .c2a-up-tag{background:rgba(34,197,94,.16);color:#86efac}'
      + '.dark .c2a-up-tag.gray{background:#292524;color:#a8a29e}';
    (document.head || document.documentElement).appendChild(st);
  }

  function esc(s){
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function cmp(a, b){
    a = String(a).replace(/^v/i, '').split('.').map(Number);
    b = String(b).replace(/^v/i, '').split('.').map(Number);
    for (var i = 0; i < Math.max(a.length, b.length); i++){
      var x = a[i] || 0, y = b[i] || 0;
      if (x > y) return 1;
      if (x < y) return -1;
    }
    return 0;
  }

  /* ---------------- 弹窗骨架 ---------------- */
  function build(info){
    ensureCss();
    close();
    var mask = document.createElement('div');
    mask.className = 'c2a-up-mask';
    mask.id = 'c2a-up-mask';
    mask.innerHTML = ''
      + '<div class="c2a-up-card" role="dialog" aria-modal="true">'
      + '  <div class="c2a-up-head">'
      + '    <div class="c2a-up-title">版本与更新</div>'
      + '    <button class="c2a-up-x" id="c2a-up-close" title="关闭">&#215;</button>'
      + '  </div>'
      + '  <div class="c2a-up-body">'
      + '    <div class="c2a-up-rows">'
      + '      <div>当前版本：<b>' + esc(CUR) + '</b></div>'
      + '      <div id="c2a-up-latest">最新版本：<b>检查中…</b></div>'
      + '    </div>'
      + '    <div id="c2a-up-notes" class="c2a-up-notes">正在获取更新说明…</div>'
      + '  </div>'
      + '  <div class="c2a-up-foot">'
      + '    <div class="c2a-up-msg" id="c2a-up-msg"></div>'
      + '    <button class="c2a-up-btn ghost" id="c2a-up-recheck">重新检查</button>'
      + '    <button class="c2a-up-btn primary" id="c2a-up-apply" style="display:none">'
      + '立即更新</button>'
      + '  </div>'
      + '</div>';
    document.body.appendChild(mask);
    modal = mask;

    mask.addEventListener('click', function(e){ if (e.target === mask) close(); });
    mask.querySelector('#c2a-up-close').onclick = close;
    mask.querySelector('#c2a-up-recheck').onclick = function(){
      var m = mask.querySelector('#c2a-up-msg');
      m.textContent = ''; m.className = 'c2a-up-msg';
      check(true);
    };

    if (info) render(info);
    else check(false);
  }

  function close(){
    if (modal){
      try { modal.remove(); } catch(e){}
      modal = null;
    }
  }

  function setMsg(t, kind){
    if (!modal) return;
    var m = modal.querySelector('#c2a-up-msg');
    if (!m) return;
    m.textContent = t || '';
    m.className = 'c2a-up-msg' + (kind ? ' ' + kind : '');
  }

  /* ---------------- 渲染检查结果 ---------------- */
  function render(info){
    if (!modal) return;
    var latest = (info && info.latest) || '';
    var notes = (info && info.notes) || '';
    var cur = (info && info.current) || CUR;

    var cell = modal.querySelector('#c2a-up-latest');
    if (cell){
      if (latest){
        var newer = cmp(latest, cur) > 0;
        cell.innerHTML = '最新版本：<b>' + esc(latest) + '</b>'
          + '<span class="c2a-up-tag' + (newer ? '' : ' gray') + '">'
          + (newer ? '有新版本' : '已是最新') + '</span>';
      } else {
        cell.innerHTML = '最新版本：<b>获取失败</b>';
      }
    }

    var nb = modal.querySelector('#c2a-up-notes');
    if (nb){
      nb.textContent = notes || (info && info.error) || '暂无更新说明';
    }

    var apply = modal.querySelector('#c2a-up-apply');
    if (apply){
      if (latest && cmp(latest, cur) > 0 && info && info.can_update){
        apply.style.display = '';
        apply.disabled = false;
        apply.textContent = '立即更新到 ' + latest;
        apply.onclick = function(){ doApply(latest); };
      } else {
        apply.style.display = 'none';
      }
    }
  }

  /* ---------------- 检查更新 ---------------- */
  function check(manual){
    if (!modal) return;
    if (manual) setMsg('正在检查…');

    // 兜底超时：网络不通时后端可能要等几十秒，不能让面板永远停在「检查中…」
    var done = false;
    var timer = setTimeout(function(){
      if (done) return;
      done = true;
      var cell = modal && modal.querySelector('#c2a-up-latest');
      if (cell) cell.innerHTML = '最新版本：<b>检查超时</b>';
      var nb = modal && modal.querySelector('#c2a-up-notes');
      if (nb) nb.textContent =
        '无法连接更新服务器（可能需要代理）。你的项目本身不受影响，'
        + '可以稍后点「重新检查」，或手动执行 git pull 更新。';
      setMsg('检查超时：网络不通', 'bad');
    }, 12000);

    // 优先走后端（后端能拿到更完整的信息，并且知道能不能就地更新）
    fetch('/p/api/update/info', {cache: 'no-store'})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (done) return;
        done = true; clearTimeout(timer);
        if (d && (d.latest || d.current)){
          render(d);
          if (manual) setMsg('');
          return;
        }
        throw new Error('bad response');
      })
      .catch(function(){
        if (done) return;
        done = true; clearTimeout(timer);
        // 后端不可用时退回直接读仓库文件
        Promise.all([
          fetch(RAW_VER, {cache: 'no-store'}).then(function(r){
            if (!r.ok) throw new Error('VERSION ' + r.status);
            return r.text();
          }),
          fetch(RAW_LOG, {cache: 'no-store'}).then(function(r){
            return r.ok ? r.text() : '';
          }).catch(function(){ return ''; })
        ]).then(function(a){
          var v = String(a[0] || '').trim().split(String.fromCharCode(10))[0].trim();
          if (v && v.charAt(0) !== 'v') v = 'v' + v;
          render({current: CUR, latest: v, notes: pickSection(a[1], v),
                  can_update: false});
          if (manual) setMsg('后端更新接口不可用，只能手动更新', 'bad');
        }).catch(function(e){
          if (manual) setMsg('检查失败：' + e.message, 'bad');
          var nb = modal && modal.querySelector('#c2a-up-notes');
          if (nb) nb.textContent = '检查更新失败：' + e.message;
        });
      });
  }

  function pickSection(md, ver){
    if (!md) return '';
    var tag = String(ver || '').replace(/^v/i, '');
    var re = new RegExp('^##\\s*v?' + tag.replace(/\./g, '\\.') + '[^\\n]*$', 'm');
    var m = re.exec(md);
    if (!m) {
      var m2 = /^##\s*v?[\d.]+[^\n]*$/m.exec(md);
      if (!m2) return '';
      var i2 = md.indexOf(m2[0]);
      var rest2 = md.slice(i2 + m2[0].length);
      var n2 = rest2.search(/^##\s/m);
      return (n2 >= 0 ? rest2.slice(0, n2) : rest2).trim();
    }
    var i = md.indexOf(m[0]);
    var rest = md.slice(i + m[0].length);
    var n = rest.search(/^##\s/m);
    return (n >= 0 ? rest.slice(0, n) : rest).trim();
  }

  /* ---------------- 执行更新 ---------------- */
  function doApply(ver){
    if (!modal) return;
    var apply = modal.querySelector('#c2a-up-apply');
    if (apply){ apply.disabled = true; apply.textContent = '更新中…'; }
    setMsg('正在下载并安装，请不要关闭页面…');

    // 更新是高危操作，后端要求鉴权。这里取当前登录凭证一起带上：
    //   自带页面用 __C2A_KEY__ 注入的 sk- key；
    //   面板原生页从 localStorage / IndexedDB 拿登录口令。
    getAuthKey().then(function(key){
      fetch('/p/api/update/apply', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + (key || '')
        },
        body: JSON.stringify({version: ver})
      }).then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok){
          setMsg('✅ 更新完成，正在重启服务（约 20-40 秒）…', 'ok');
          waitRestart(d.to || ver);
        } else {
          setMsg((d && d.error) || '更新失败', 'bad');
          if (apply){ apply.disabled = false; apply.textContent = '重试'; }
        }
      })
      .catch(function(e){
        setMsg('更新请求失败：' + e.message, 'bad');
        if (apply){ apply.disabled = false; apply.textContent = '重试'; }
      });
    });
  }

  /* 取当前登录凭证：优先用页面注入的 sk- key，其次 localStorage，最后 IndexedDB */
  function getAuthKey(){
    var injected = '__C2A_PAGE_KEY__';
    if (injected && injected.indexOf('C2A_PAGE_KEY') < 0) return Promise.resolve(injected);
    var ls = '';
    try { ls = localStorage.getItem('c2a_key') || ''; } catch(e){}
    if (ls) return Promise.resolve(ls);
    return new Promise(function(res){
      try {
        var r = indexedDB.open('chatgpt2api');
        r.onupgradeneeded = function(){ try { r.transaction.abort(); } catch(e){} res(''); };
        r.onerror = function(){ res(''); };
        r.onsuccess = function(){
          var db = r.result;
          try {
            if (!db.objectStoreNames.contains('auth')) { db.close(); return res(''); }
            var g = db.transaction('auth').objectStore('auth').get('chatgpt2api_auth_key');
            g.onsuccess = function(){
              var v = g.result;
              db.close();
              if (!v) return res('');
              res((v && v.key) || (typeof v === 'string' ? v : ''));
            };
            g.onerror = function(){ db.close(); res(''); };
          } catch(e){ try{db.close();}catch(e2){} res(''); }
        };
      } catch(e){ res(''); }
    });
  }

  /* 轮询健康检查，等新版本起来后自动刷新页面 */
  function waitRestart(newVer){
    var start = Date.now();
    var timer = setInterval(function(){
      if (Date.now() - start > 180000){
        clearInterval(timer);
        setMsg('重启超时，请手动执行 docker compose restart', 'bad');
        return;
      }
      fetch('/health', {cache: 'no-store'})
        .then(function(r){ return r.json(); })
        .then(function(d){
          if (d && d.status === 'ok'){
            var v = String(d.version || '').replace(/^v/i, '');
            if (!newVer || !v || v === String(newVer).replace(/^v/i, '')){
              clearInterval(timer);
              setMsg('✅ 已更新到 ' + (d.version || newVer) + '，正在刷新…', 'ok');
              setTimeout(function(){ location.reload(); }, 900);
            }
          }
        })
        .catch(function(){});
    }, 2000);
  }

  /* ---------------- 绑定入口 ---------------- */
  function bind(){
    // 1) 我们自己的页面：顶栏有 #c2a-ver
    var own = document.getElementById('c2a-ver');
    if (own && !own.__c2aBound){
      own.__c2aBound = 1;
      own.onclick = function(e){
        if (e) { e.preventDefault(); e.stopPropagation(); }
        build(null);
      };
    }
  }

  // 2) 面板原生页：版本号是 React 渲染的按钮，用捕获阶段抢在 React 之前处理
  document.addEventListener('click', function(e){
    var t = e.target;
    // 自有页面的 #c2a-ver 由 bind() 处理，这里跳过，避免弹两次
    if (t && t.id === 'c2a-ver') return;
    while (t && t !== document.body){
      var txt = (t.textContent || '').trim();
      if (/^v\d+\.\d+\.\d+$/.test(txt) && t.tagName === 'BUTTON'){
        e.preventDefault();
        e.stopPropagation();
        build(null);
        return;
      }
      t = t.parentElement;
    }
  }, true);

  // ESC 关闭
  document.addEventListener('keydown', function(e){
    if (e.key === 'Escape' && modal) close();
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
  // 面板是 React 渲染，按钮可能后出现，补几次
  [400, 1200, 3000].forEach(function(ms){ setTimeout(bind, ms); });
})();
</script>"""


def update_ui_script(version, repo_api, repo_url, raw_ver, raw_log):
    """生成版本面板脚本。

    用 replace 而不是 % 格式化：脚本里有大量 % 号（CSS 百分比），
    用 % 会炸掉。
    """
    s = _TEMPLATE
    s = s.replace("__C2A_CUR__", version)
    s = s.replace("__C2A_REPO_API__", repo_api)
    s = s.replace("__C2A_REPO_URL__", repo_url)
    s = s.replace("__C2A_RAW_VER__", raw_ver)
    s = s.replace("__C2A_RAW_LOG__", raw_log)
    return s
