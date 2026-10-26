/* yuhe-device.js —— 设备管理页主站接管（device.html 专用，在 yuhe-api.js 之后加载）
 *
 * 已绑定主站时：
 *   1. 表格数据源 → 主站代理：智能体列表 + 各智能体绑定设备（GET /agent/list +
 *      GET /device/bind/{agentId}）聚合展开为设备行
 *   2. 表头重映射（主站字段：macAddress/alias/agentName/board/appVersion/...）
 *   3. 注入「验证码绑定设备」按钮：选智能体 → 输 6 位验证码 →
 *      POST /device/bind/{agentId}/{code}（与主站 Agents.vue 同契约）
 *   4. 行操作 → 解绑（POST /device/unbind {deviceId}）
 * 未绑定时保持本地 demo 表格不动（顶栏 chip 引导绑定）。
 */
(function () {
  'use strict';

  if (location.pathname.indexOf('device.html') < 0) return;
  if (!window.QXYuhe || !window.QXCrud) return;

  var DARK_HASH = 'css-97cec0';
  var LIGHT_HASH = 'css-1p8u2sp';

  function hash() {
    var mode = localStorage.getItem('theme-mode') || 'auto';
    if (mode === 'auto') {
      mode = (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
    }
    return mode === 'light' ? LIGHT_HASH : DARK_HASH;
  }

  function esc(s) {
    if (s === null || s === undefined) return '-';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function td(html) {
    return '<td class="ant-table-cell" style="text-align: center;"><!---->' + html + '<!----></td>';
  }
  function tdFix(html) {
    return '<td class="ant-table-cell ant-table-cell-fix-right ant-table-cell-fix-right-first" style="text-align: center; position: sticky; right: 0px;"><!---->' + html + '<!----></td>';
  }
  function ell(v, style) {
    var s = (v === null || v === undefined || v === '') ? '-' : String(v);
    var a = ' class="ellipsis-text"';
    if (style) a += ' style="' + style + '"';
    if (s !== '-') a += ' title="' + esc(s) + '"';
    return '<span' + a + '>' + esc(s) + '</span>';
  }

  function fmtTs(ts) {
    if (!ts) return '-';
    try {
      var d = new Date(Number(ts) * (Number(ts) > 1e12 ? 1 : 1000));
      if (isNaN(d.getTime())) return String(ts);
      var p = function (n) { return (n < 10 ? '0' : '') + n; };
      return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
    } catch (e) { return '-'; }
  }

  function onlineTag(recentTs) {
    // 主站无实时在线字段：30 分钟内有连接视为活跃
    var alive = recentTs && (Date.now() / 1000 - Number(recentTs) < 1800);
    if (alive) {
      return '<span class="ant-tag ' + hash() + '" style="display:inline-flex;align-items:center;gap:6px;background:rgba(16,185,129,.12);border-color:rgba(16,185,129,.35);color:#10B981;">' +
        '<span style="width:6px;height:6px;border-radius:50%;background:#10B981;box-shadow:0 0 6px #10B981;"></span>在线</span>';
    }
    return '<span class="ant-tag ' + hash() + '" style="display:inline-flex;align-items:center;gap:6px;background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.35);color:#EF4444;">' +
      '<span style="width:6px;height:6px;border-radius:50%;background:#EF4444;box-shadow:0 0 6px #EF4444;"></span>离线</span>';
  }

  /* ---------- 数据加载：智能体 × 绑定设备 展开 ---------- */
  var agentsCache = [];

  function loadAll(cb, fb) {
    QXYuhe.proxied('GET', '/agent/list').then(function (agents) {
      agentsCache = agents || [];
      var jobs = (agents || []).map(function (a) {
        return QXYuhe.proxied('GET', '/device/bind/' + encodeURIComponent(a.id))
          .then(function (devices) {
            return (devices || []).map(function (d) {
              d.__agentName = a.agentName;
              d.__agentId = a.id;
              return d;
            });
          }).catch(function () { return []; });
      });
      return Promise.all(jobs);
    }).then(function (groups) {
      var rows = [];
      groups.forEach(function (g) { rows = rows.concat(g); });
      cb(rows);
    }).catch(function (e) {
      if (fb) fb(e);
    });
  }

  /* ---------- 表头重映射 ---------- */
  var HEADS = ['设备MAC', '设备名称', '所属智能体', '板型', '设备类型', '状态', '固件版本', 'OTA通道', '最近聊天', '最后连接', '创建时间', '来源', '绑定人', '操作'];

  function rewriteHead() {
    var thead = document.querySelector('.ant-table-thead tr');
    if (!thead) return;
    thead.innerHTML = HEADS.map(function (h, i) {
      var fix = (i === 0) ? ' ant-table-cell-fix-left ant-table-cell-fix-left-last" style="text-align: center; position: sticky; left: 0px;' : '';
      var fixR = (i === HEADS.length - 1) ? ' ant-table-cell-fix-right ant-table-cell-fix-right-first" style="text-align: center; position: sticky; right: 0px;' : '';
      return '<th class="ant-table-cell' + (fix || fixR || '"') + '><!---->' + h + '<!----></th>';
    }).join('');
  }

  /* ---------- 行渲染 ---------- */
  function renderRows(devices) {
    var tbody = document.querySelector('.ant-table-tbody');
    if (!tbody) return;
    var rows = (devices || []).map(function (d) {
      var ops = '<div class="ant-space ant-space-horizontal ant-space-align-center ' + hash() + '" style="gap: 8px;">' +
        '<div class="ant-space-item"><a class="delete-link" data-qy-unbind="' + esc(d.id) + '">解绑</a></div></div>';
      return '<tr data-row-key="' + esc(d.id) + '" class="ant-table-row ant-table-row-level-0">' +
        td(ell(d.macAddress, 'font-weight:500;font-family:monospace;')) +
        td(ell(d.alias || d.board, 'font-weight:500;')) +
        td('<span class="ant-tag ' + hash() + '" style="background:rgba(99,102,241,.12);border-color:rgba(99,102,241,.35);color:#6366F1;">' + esc(d.__agentName) + '</span>') +
        td(ell(d.board)) +
        td(ell(d.deviceType)) +
        td(onlineTag(d.lastConnectedAtTimestamp)) +
        td(ell(d.appVersion)) +
        td(ell(d.otaType)) +
        td(ell(d.recentChatTime, 'color:var(--ant-color-text-secondary);')) +
        td(ell(fmtTs(d.lastConnectedAtTimestamp), 'color:var(--ant-color-text-secondary);')) +
        td(ell(fmtTs(d.createDateTimestamp), 'color:var(--ant-color-text-secondary);')) +
        td('<span class="ant-tag ' + hash() + '" style="background:rgba(82,196,26,.12);border-color:rgba(82,196,26,.45);color:#52C41A;">主站</span>') +
        td(ell(d.bindUserName, 'color:var(--ant-color-text-secondary);')) +
        tdFix(ops) +
        '</tr>';
    }).join('');
    var measure = tbody.querySelector('.ant-table-measure-row');
    tbody.innerHTML = (measure ? measure.outerHTML : '') + (rows || '<tr><td colspan="' + HEADS.length + '" style="text-align:center;padding:32px;color:var(--ant-color-text-quaternary);">暂无绑定设备</td></tr>');
    // 分页器隐藏（主站列表无分页语义）
    var pag = document.querySelector('.ant-table-pagination');
    if (pag) pag.style.display = 'none';
  }

  /* ---------- 解绑委托 ---------- */
  document.addEventListener('click', function (e) {
    var a = e.target.closest ? e.target.closest('a[data-qy-unbind]') : null;
    if (!a) return;
    e.preventDefault();
    var id = a.getAttribute('data-qy-unbind');
    if (!window.confirm('确认解绑该设备吗？解绑后设备需重新激活。')) return;
    QXYuhe.proxied('POST', '/device/unbind', { deviceId: id }).then(function () {
      QXCrud.toast('设备已解绑', true);
      refresh();
    }).catch(function (err) {
      QXCrud.toast((err && err.message) || '解绑失败', false);
    });
  });

  /* ---------- 验证码绑定弹窗 ---------- */
  function openBindModal() {
    var wrap = document.createElement('div');
    wrap.className = 'ant-modal-wrap';
    var modal = document.createElement('div');
    modal.className = 'ant-modal';
    modal.style.cssText = 'width:460px;margin:0 auto;';
    var options = (agentsCache || []).map(function (a) {
      return '<option value="' + esc(a.id) + '">' + esc(a.agentName) + '</option>';
    }).join('');
    modal.innerHTML =
      '<div tabindex="0"><div class="ant-modal-content">' +
      '<button type="button" aria-label="Close" class="ant-modal-close"><span class="ant-modal-close-x">✕</span></button>' +
      '<div class="ant-modal-header"><div class="ant-modal-title">验证码绑定设备</div></div>' +
      '<div class="ant-modal-body">' +
      '<p style="margin:0 0 14px;font-size:13px;color:var(--ant-color-text-secondary);">设备首次联网后屏幕会显示 6 位激活验证码，输入即可绑定到所选智能体。</p>' +
      '<div style="display:flex;flex-direction:column;gap:6px;margin-bottom:12px;">' +
      '<label style="font-size:13px;font-weight:600;">绑定到智能体</label>' +
      '<select id="qy-bind-agent" style="padding:9px 12px;border:1.5px solid var(--ant-color-border);border-radius:10px;font-size:14px;outline:none;background:var(--ant-color-bg-container);color:var(--ant-color-text);">' + options + '</select>' +
      '</div>' +
      '<div style="display:flex;flex-direction:column;gap:6px;">' +
      '<label style="font-size:13px;font-weight:600;">6 位验证码</label>' +
      '<input id="qy-bind-code" type="text" maxlength="6" placeholder="设备屏幕上显示的 6 位数字" style="padding:9px 12px;border:1.5px solid var(--ant-color-border);border-radius:10px;font-size:14px;letter-spacing:4px;outline:none;">' +
      '</div>' +
      '<p id="qy-bind-err" style="display:none;margin:12px 0 0;padding:8px 12px;border-radius:8px;font-size:13px;background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.35);color:#EF4444;"></p>' +
      '</div>' +
      '<div class="ant-modal-footer"><div class="ant-modal-footer-buttons">' +
      '<button type="button" class="ant-btn qy-bd-close"><span>取 消</span></button>' +
      '<button type="button" class="ant-btn ant-btn-primary qy-bd-ok"><span>绑 定</span></button>' +
      '</div></div></div></div>';
    var mask = document.createElement('div');
    mask.className = 'ant-modal-mask';
    document.body.appendChild(mask);
    document.body.appendChild(wrap);

    function close() { wrap.remove(); mask.remove(); }
    modal.querySelector('.ant-modal-close').addEventListener('click', close);
    modal.querySelector('.qy-bd-close').addEventListener('click', close);
    mask.addEventListener('click', close);

    modal.querySelector('.qy-bd-ok').addEventListener('click', function () {
      var agentId = modal.querySelector('#qy-bind-agent').value;
      var code = modal.querySelector('#qy-bind-code').value.trim();
      var errEl = modal.querySelector('#qy-bind-err');
      function showErr(m) { errEl.textContent = m; errEl.style.display = 'block'; }
      if (!agentId) { showErr('请选择智能体'); return; }
      if (!/^\d{6}$/.test(code)) { showErr('请输入 6 位数字验证码'); return; }
      var btn = modal.querySelector('.qy-bd-ok');
      btn.disabled = true;
      btn.textContent = '绑定中...';
      QXYuhe.proxied('POST', '/device/bind/' + encodeURIComponent(agentId) + '/' + encodeURIComponent(code))
        .then(function () {
          QXCrud.toast('设备绑定成功', true);
          close();
          refresh();
        })
        .catch(function (err) {
          showErr((err && err.message) || '绑定失败');
          btn.disabled = false;
          btn.textContent = '绑 定';
        });
    });
  }

  /* ---------- 主站接管入口 ---------- */
  var took = false;

  function refresh() {
    loadAll(function (devices) {
      renderRows(devices);
      QXCrud.setRows('device', devices);  // crud.js 行缓存替换（防止 demo 编辑误操作）
    }, function (err) {
      QXCrud.toast((err && err.message) || '主站设备加载失败', false);
    });
  }

  function takeover() {
    if (took) { refresh(); return; }
    took = true;
    rewriteHead();
    refresh();

    // 注入「验证码绑定」按钮（挨着原「添加设备」按钮）
    var injected = false;
    document.querySelectorAll('button').forEach(function (b) {
      if (injected) return;
      var t = (b.textContent || '').trim();
      if (t === '添加设备') {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'ant-btn ant-btn-primary';
        btn.style.cssText = 'margin-left:10px;background:linear-gradient(135deg,#6366F1,#8B5CF6);border:none;color:#fff;';
        btn.textContent = '验证码绑定设备';
        btn.addEventListener('click', function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          openBindModal();
        });
        b.parentNode.insertBefore(btn, b.nextSibling);
        injected = true;
      }
    });

    // 覆盖 crud.js 的刷新注册：分页/搜索触发时走主站刷新
    QXCrud.register('device', refresh);
  }

  /* ---------- 初始化 ---------- */
  QXYuhe.me().then(function (l) {
    if (!l.linked) { QXYuhe.showUnlinkedOverlay('device'); return; }  // 未绑定：遮罩引导绑定
    // 等 demo-data.js 首轮渲染完再接管（脚本顺序保证它在前面跑）
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () { setTimeout(takeover, 50); });
    } else {
      setTimeout(takeover, 50);
    }
  }).catch(function () {});

  /* 绑定成功后（绑定弹窗发生在本页时）自动接管 */
  document.addEventListener('qx-yuhe-linked', function () {
    QXYuhe.me(true).then(function (l) { if (l.linked) takeover(); });
  });
})();
