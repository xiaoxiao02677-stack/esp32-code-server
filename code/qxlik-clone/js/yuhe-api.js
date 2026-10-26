/* yuhe-api.js —— yuhe 主站桥前端层（全站加载，auth.js 之后 crud.js 之前）
 *
 * 职责：
 *   1. QXYuhe.proxy(method, path, body) 统一代理：POST /api/yuhe/proxy，
 *      解包 {data:{status, body}}；401（需重新绑定）弹提示
 *   2. 顶栏注入「主站绑定」chip：未绑定橙色 → 点击弹绑定弹窗（用户名+密码）；
 *      已绑定绿色显示主站账号
 *   3. 绑定状态缓存（QXYuhe.me()）：页面加载时拉一次，避免每页重复请求
 *   4. 页面接管钩子：device.html / config-agent.html 数据源从主站代理
 *      （QXYuhe.overrideDeviceList / QXYuhe.overrideAgentList）
 *
 * 约定：所有主站接口经 /api/yuhe/proxy 转发（后端 A 先 C 后 + 401 自动重登录）
 */
(function () {
  'use strict';

  var LINKED_KEY = 'qx-yuhe-link';

  function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /* ---------- 代理调用 ---------- */
  function proxy(method, path, body) {
    return QXAuth.api('/api/yuhe/proxy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ server: '', method: method, path: path, body: body || null })
    }).then(function (j) {
      if (!j || j.code !== 200) {
        throw { code: (j && j.code) || 500, message: (j && j.message) || '主站请求失败' };
      }
      var d = j.data || {};
      return d;  // {status, body|rawBody|binary, contentType}
    });
  }

  /* 主站响应 → 业务数据（body 是主站 Result{code,msg,data} 契约） */
  function proxied(method, path, body) {
    return proxy(method, path, body).then(function (d) {
      var b = d.body;
      if (!b) throw { code: 502, message: '主站响应为空' };
      if (b.code !== 0) throw { code: b.code, message: b.msg || '主站业务错误' };
      return b.data;
    });
  }

  /* ---------- 绑定状态 ---------- */
  var linkCache = null;

  function me(force) {
    if (linkCache && !force) return Promise.resolve(linkCache);
    return QXAuth.api('/api/yuhe/me').then(function (j) {
      linkCache = (j && j.data) || { linked: false };
      return linkCache;
    }).catch(function () {
      return { linked: false };
    });
  }

  function saveLinkCache(linked) {
    linkCache = linked;
    try { localStorage.setItem(LINKED_KEY, JSON.stringify(linked)); } catch (e) {}
  }

  /* ---------- 绑定弹窗 ---------- */
  function openLinkModal() {
    var wrap = document.createElement('div');
    wrap.className = 'ant-modal-wrap';
    var modal = document.createElement('div');
    modal.className = 'ant-modal';
    modal.style.cssText = 'width:460px;margin:0 auto;';
    modal.innerHTML =
      '<div tabindex="0"><div class="ant-modal-content">' +
      '<button type="button" aria-label="Close" class="ant-modal-close"><span class="ant-modal-close-x">✕</span></button>' +
      '<div class="ant-modal-header"><div class="ant-modal-title">绑定主站账号</div></div>' +
      '<div class="ant-modal-body" style="max-height:62vh;overflow-y:auto;">' +
      '<p style="margin:0 0 14px;font-size:13px;color:var(--ant-color-text-secondary);">' +
      '输入屿禾主站（sandyun.top:8001 控制台）的账号密码，绑定后即可在此管理主站设备与智能体。</p>' +
      '<div style="display:flex;flex-direction:column;gap:6px;margin-bottom:12px;">' +
      '<label style="font-size:13px;font-weight:600;">主站用户名</label>' +
      '<input id="qx-yuhe-username" type="text" placeholder="请输入主站用户名" style="padding:9px 12px;border:1.5px solid var(--ant-color-border);border-radius:10px;font-size:14px;outline:none;">' +
      '</div>' +
      '<div style="display:flex;flex-direction:column;gap:6px;">' +
      '<label style="font-size:13px;font-weight:600;">主站密码</label>' +
      '<input id="qx-yuhe-password" type="password" placeholder="请输入主站密码" style="padding:9px 12px;border:1.5px solid var(--ant-color-border);border-radius:10px;font-size:14px;outline:none;">' +
      '</div>' +
      '<p id="qx-yuhe-err" style="display:none;margin:12px 0 0;padding:8px 12px;border-radius:8px;font-size:13px;background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.35);color:#EF4444;"></p>' +
      '<p style="margin:14px 0 0;font-size:12px;color:var(--ant-color-text-quaternary);">密码将加密存储于站点后端，用于主站会话过期时自动续期。</p>' +
      '</div>' +
      '<div class="ant-modal-footer"><div class="ant-modal-footer-buttons">' +
      '<button type="button" class="ant-btn qx-lk-close"><span>取 消</span></button>' +
      '<button type="button" class="ant-btn ant-btn-primary qx-lk-ok"><span>绑 定</span></button>' +
      '</div></div></div></div>';
    var mask = document.createElement('div');
    mask.className = 'ant-modal-mask';
    document.body.appendChild(mask);
    document.body.appendChild(wrap);

    function close() { wrap.remove(); mask.remove(); }
    function showErr(msg) {
      var el = modal.querySelector('#qx-yuhe-err');
      el.textContent = msg;
      el.style.display = 'block';
    }

    modal.querySelector('.ant-modal-close').addEventListener('click', close);
    modal.querySelector('.qx-lk-close').addEventListener('click', close);
    mask.addEventListener('click', close);
    modal.querySelector('.qx-lk-ok').addEventListener('click', function () {
      var u = modal.querySelector('#qx-yuhe-username').value.trim();
      var p = modal.querySelector('#qx-yuhe-password').value;
      if (!u || !p) { showErr('用户名和密码不能为空'); return; }
      var btn = modal.querySelector('.qx-lk-ok');
      btn.disabled = true;
      btn.textContent = '绑定中...';
      QXAuth.api('/api/yuhe/link', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ serverTag: '', username: u, password: p })
      }).then(function (j) {
        if (j && j.code === 200) {
          saveLinkCache({ linked: true, username: u, serverTag: (j.data || {}).serverTag || '' });
          QXCrud.toast('主站账号绑定成功', true);
          close();
          renderChip();
          // 通知页面接管层（yuhe-device.js / yuhe-agent.js 等）
          document.dispatchEvent(new CustomEvent('qx-yuhe-linked', { detail: { username: u } }));
        } else {
          showErr((j && j.message) || '绑定失败');
          btn.disabled = false;
          btn.textContent = '绑 定';
        }
      }).catch(function () {
        showErr('网络异常，请稍后重试');
        btn.disabled = false;
        btn.textContent = '绑 定';
      });
    });
  }

  /* ---------- 顶栏 chip ---------- */
  function chipHtml() {
    var l = linkCache || { linked: false };
    if (l.linked) {
      return '<span class="qx-yuhe-chip qx-yuhe-chip-ok" title="已绑定主站账号（' + esc(l.username) + '）">' +
        '<span class="qx-yuhe-dot"></span>主站已绑定 · ' + esc(l.username) + '</span>';
    }
    return '<span class="qx-yuhe-chip qx-yuhe-chip-warn" title="点击绑定主站账号，解锁真实设备管理">' +
      '<span class="qx-yuhe-dot"></span>绑定主站</span>';
  }

  var chipEl = null;

  function renderChip() {
    if (chipEl) {
      chipEl.innerHTML = chipHtml();
      return;
    }
    var host = document.querySelector('.header-right .header-group') || document.querySelector('.header-right');
    if (!host) return;
    chipEl = document.createElement('div');
    chipEl.className = 'qx-yuhe-chip-wrap';
    chipEl.innerHTML = chipHtml();
    chipEl.addEventListener('click', function () {
      var l = linkCache || { linked: false };
      if (l.linked) {
        if (window.confirm('已绑定主站账号「' + l.username + '」。\n\n确定要解绑吗？解绑后设备/智能体管理将不可用。')) {
          QXAuth.api('/api/yuhe/unlink', { method: 'POST' }).then(function () {
            saveLinkCache({ linked: false });
            QXCrud.toast('已解绑主站账号', true);
            renderChip();
          }).catch(function () { QXCrud.toast('解绑失败', false); });
        }
      } else {
        openLinkModal();
      }
    });
    host.insertBefore(chipEl, host.firstChild);
  }

  /* ---------- 对外 API ---------- */
  /* 未绑定主站账号时的空态引导：遮住假数据表格，提示绑定 */
  function showUnlinkedOverlay(pageKey) {
    if (document.getElementById('qx-yuhe-unlinked')) return;
    var style = document.createElement('style');
    style.textContent = '.qx-yu-unlinked-cover{position:absolute;inset:0;z-index:50;display:flex;align-items:center;justify-content:center;'
      + 'background:rgba(24,24,27,.97);backdrop-filter:blur(3px);border-radius:12px;}'
      + '.qx-yu-unlinked-box{text-align:center;padding:40px 48px;max-width:460px;}'
      + '.qx-yu-unlinked-title{font-size:17px;font-weight:600;color:#FAFAFA;margin-bottom:10px;}'
      + '.qx-yu-unlinked-desc{font-size:13px;color:#A1A1AA;line-height:1.7;margin-bottom:22px;}'
      + '.qx-yu-unlinked-btn{display:inline-block;padding:10px 26px;border-radius:10px;cursor:pointer;font-size:14px;font-weight:600;'
      + 'background:rgba(99,102,241,.15);border:1px solid rgba(99,102,241,.45);color:#818CF8;transition:all .15s;}'
      + '.qx-yu-unlinked-btn:hover{background:rgba(99,102,241,.25);}';
    document.head.appendChild(style);

    var findHost = function () {
      // 表格卡片容器：优先 .ant-table 外层的卡片/面板
      var tbl = document.querySelector('.ant-table');
      if (!tbl) return null;
      var node = tbl;
      while (node && node !== document.body) {
        var cs = getComputedStyle(node);
        if (/(relative|absolute)/.test(cs.position)) return node;
        node = node.parentElement;
      }
      return tbl.parentElement;
    };
    var mount = function () {
      var host = findHost();
      if (!host || document.getElementById('qx-yuhe-unlinked')) return;
      host.style.position = 'relative';
      var cover = document.createElement('div');
      cover.id = 'qx-yuhe-unlinked';
      cover.className = 'qx-yu-unlinked-cover';
      cover.innerHTML = '<div class="qx-yu-unlinked-box">'
        + '<div class="qx-yu-unlinked-title">🔗 绑定主站账号后查看真实数据</div>'
        + '<div class="qx-yu-unlinked-desc">当前页面需要连接 yuhe 主站账号（sandyun.top / yuhe.pro）后才能加载你的智能体、设备与记忆数据。绑定只需一次，之后自动保持登录。</div>'
        + '<span class="qx-yu-unlinked-btn" id="qx-yuhe-unlinked-btn">绑定主站账号</span>'
        + '</div>';
      host.appendChild(cover);
      cover.querySelector('#qx-yuhe-unlinked-btn').addEventListener('click', function () {
        openLinkModal();
      });
    };
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () { setTimeout(mount, 80); });
    } else {
      setTimeout(mount, 80);
    }
    // 绑定成功 → 撤掉遮罩
    document.addEventListener('qx-yuhe-linked', function () {
      var el = document.getElementById('qx-yuhe-unlinked');
      if (el) el.remove();
    });
  }

  var QXYuhe = {
    proxy: proxy,
    proxied: proxied,
    me: me,
    refreshLink: function () { linkCache = null; return me(true); },
    renderChip: renderChip,
    openLinkModal: openLinkModal,
    showUnlinkedOverlay: showUnlinkedOverlay,
    /* 播放主站音频：uuid 由 POST /voiceClone/audio/{id} 换取；走后端桥流式转发 */
    playVoice: function (uuid) {
      window.open('/api/yuhe/play/' + encodeURIComponent(uuid), '_blank');
    },
    ensureLinked: function () {
      /* 返回 Promise<boolean>；未绑定弹绑定弹窗并 reject */
      return me().then(function (l) {
        if (l.linked) return true;
        openLinkModal();
        throw { code: 401, message: '请先绑定主站账号' };
      });
    }
  };
  window.QXYuhe = QXYuhe;

  /* ---------- 初始化 ---------- */
  function init() {
    // 登录页/错误页不处理
    var p = location.pathname;
    if (p.indexOf('login.html') >= 0 || p.indexOf('403.html') >= 0 || p.indexOf('404.html') >= 0) return;
    if (!window.QXAuth || !QXAuth.getToken()) return;

    me().then(function () {
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', renderChip);
      } else {
        renderChip();
      }
    }).catch(function () {});
  }

  /* chip 样式注入 */
  function injectStyle() {
    if (document.getElementById('qx-yuhe-style')) return;
    var css = [
      '.qx-yuhe-chip-wrap { display:inline-flex; align-items:center; }',
      '.qx-yuhe-chip { display:inline-flex; align-items:center; gap:7px; padding:5px 14px; border-radius:999px;',
      '  font-size:12.5px; font-weight:600; cursor:pointer; user-select:none;',
      '  border:1px solid; transition:opacity .15s; white-space:nowrap; }',
      '.qx-yuhe-chip:hover { opacity:.85; }',
      '.qx-yuhe-chip-ok { background:rgba(16,185,129,.10); border-color:rgba(16,185,129,.40); color:#10B981; }',
      '.qx-yuhe-chip-warn { background:rgba(245,158,11,.10); border-color:rgba(245,158,11,.45); color:#F59E0B; }',
      '.qx-yuhe-dot { width:7px; height:7px; border-radius:50%; background:currentColor; box-shadow:0 0 6px currentColor; }'
    ].join('\n');
    var st = document.createElement('style');
    st.id = 'qx-yuhe-style';
    st.textContent = css;
    document.head.appendChild(st);
  }
  injectStyle();

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
