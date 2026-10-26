/* static-pages.js —— 10 个静态页（user/reminder/music/knowledge/template/auth-role/
 * config-model/config-oss/config-stt/config-tts）的 API 数据渲染引擎
 *
 * 依赖：auth.js（QXAuth.api）、crud.js（QXCrud：行缓存/分页/刷新注册）
 * 数据流：GET /api/{module}/list → 渲染 tbody → QXCrud.setRows → QXCrud.renderPagination
 */
(function () {
  'use strict';

  var DARK_HASH = 'css-97cec0';
  var LIGHT_HASH = 'css-1p8u2sp';

  function currentHash() {
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

  function tdCenter(html, extraStyle) {
    return '<td class="ant-table-cell" style="text-align: center;' + (extraStyle || '') + '"><!---->' + html + '<!----></td>';
  }
  function tdCenterFix(html, styleAttr) {
    return '<td class="ant-table-cell ant-table-cell-fix-right ant-table-cell-fix-right-first" style="text-align: center; position: sticky; right: 0px;"><!---->' + html + '<!----></td>';
  }
  function textCell(v) {
    return tdCenter(ellipsisSpan(v));
  }
  function ellipsisSpan(v, style) {
    var s = (v === null || v === undefined) ? '-' : String(v);
    var attr = ' class="ellipsis-text"';
    if (style) attr += ' style="' + style + '"';
    if (s && s !== '-') attr += ' title="' + esc(s).replace(/"/g, '&quot;') + '"';
    return '<span' + attr + '>' + esc(s) + '</span>';
  }

  function tag(text, color, bg) {
    return '<span class="ant-tag ' + currentHash() + '" style="background:' + bg + ';border-color:rgba(' + '16,185,129,.35);color:' + color + ';">' + esc(text) + '</span>';
  }
  function greenTag(t) {
    return '<span class="ant-tag ' + currentHash() + '" style="background:rgba(16,185,129,.12);border-color:rgba(16,185,129,.35);color:#10B981;">' + esc(t) + '</span>';
  }
  function indigoTag(t) {
    return '<span class="ant-tag ' + currentHash() + '" style="background:rgba(99,102,241,.12);border-color:rgba(99,102,241,.35);color:#6366F1;">' + esc(t) + '</span>';
  }
  function grayTag(t) {
    return '<span class="ant-tag ' + currentHash() + '" style="background:rgba(113,113,122,.12);border-color:rgba(113,113,122,.35);color:#A1A1AA;">' + esc(t) + '</span>';
  }

  // 操作列
  function opsCell(actions) {
    var items = actions.map(function (a, idx) {
      var sep = idx < actions.length - 1
        ? '<div class="ant-space-item" style=""><div class="ant-divider ant-divider-vertical" role="separator"><!----></div></div><!---->'
        : '';
      var cls = a.danger ? 'delete-link' : '';
      return '<div class="ant-space-item" style=""><a class="' + cls + '" data-qx-op="' + a.key + '">' + a.label + '</a></div><!---->' + sep;
    }).join('');
    return tdCenterFix('<div class="ant-space ant-space-horizontal ant-space-align-center ' + currentHash() + '" style="gap: 8px;">' + items + '</div>');
  }

  /* ---------- 页面 → 模块映射 ---------- */
  var PAGE_KEY = {
    'user.html': 'user',
    'reminder.html': 'reminder',
    'music.html': 'music',
    'knowledge.html': 'knowledge',
    'template.html': 'template',
    'auth-role.html': 'auth-role',
    'config-model.html': 'config-model',
    'config-oss.html': 'config-oss',
    'config-stt.html': 'config-stt',
    'config-tts.html': 'config-tts'
  };
  var API_BASE = {
    'user': '/api/user/list',
    'reminder': '/api/reminder/list',
    'music': '/api/music/list',
    'knowledge': '/api/knowledge/list',
    'template': '/api/template/list',
    'auth-role': '/api/auth-role/list',
    'config-model': '/api/config/model/list',
    'config-oss': '/api/config/oss/list',
    'config-stt': '/api/config/stt/list',
    'config-tts': '/api/config/tts/list'
  };

  /* ---------- 各页渲染函数 ---------- */
  function renderUser(resp) {
    var list = (resp.data && resp.data.list) || [];
    var rows = list.map(function (d) {
      var avatar = d.avatar
        ? '<span class="ant-avatar ant-avatar-circle ' + currentHash() + '" style="width:32px;height:32px;line-height:32px;background:rgba(99,102,241,.15);color:#6366F1;font-size:14px;"><span class="ant-avatar-string" style="transform: scale(1) translateX(-50%);">' + esc(String(d.name).charAt(0)) + '</span></span>'
        : '<span class="ant-avatar ant-avatar-circle ' + currentHash() + '" style="width:32px;height:32px;line-height:32px;"><span class="ant-avatar-string" style="transform: scale(1) translateX(-50%);"><!----></span></span>';
      var status = d.status === 1 ? greenTag('正常') : grayTag('禁用');
      return '<tr data-row-key="' + d.id + '" class="ant-table-row ant-table-row-level-0">' +
        tdCenter(ellipsisSpan(d.name, 'font-weight:500;')) +
        tdCenter(avatar) +
        tdCenter(ellipsisSpan(d.email)) +
        tdCenter(ellipsisSpan(d.tel)) +
        tdCenter(esc(d.deviceCount === null || d.deviceCount === undefined ? '-' : d.deviceCount)) +
        tdCenter(esc(d.onlineCount === null || d.onlineCount === undefined ? '-' : d.onlineCount)) +
        tdCenter(esc(d.messageCount === null || d.messageCount === undefined ? '-' : d.messageCount)) +
        tdCenter(status) +
        tdCenter(indigoTag(d.accountType || '-')) +
        tdCenter('<span class="' + currentHash() + '">' + esc(d.roleName || '-') + '</span>') +
        tdCenter(ellipsisSpan(d.lastLoginTime)) +
        tdCenter(ellipsisSpan(d.lastLoginIp)) +
        opsCell([{ key: 'edit', label: '编辑' }, { key: 'delete', label: '删除', danger: true }]) +
        '</tr>';
    }).join('');
    fillTbody(rows);
  }

  function renderReminder(resp) {
    var list = (resp.data && resp.data.list) || [];
    var rows = list.map(function (d) {
      var status = d.status === 1 ? greenTag('已触发') : indigoTag('待触发');
      return '<tr data-row-key="' + d.id + '" class="ant-table-row ant-table-row-level-0">' +
        tdCenter(esc(d.id)) +
        tdCenter(ellipsisSpan(d.content)) +
        tdCenter(ellipsisSpan(d.time)) +
        tdCenter(ellipsisSpan(d.repeatType)) +
        tdCenter(status) +
        tdCenter(ellipsisSpan(d.deviceName)) +
        opsCell([{ key: 'edit', label: '编辑' }, { key: 'delete', label: '删除', danger: true }]) +
        '</tr>';
    }).join('');
    fillTbody(rows);
  }

  function renderMusic(resp) {
    var list = (resp.data && resp.data.list) || [];
    var rows = list.map(function (d) {
      return '<tr data-row-key="' + d.id + '" class="ant-table-row ant-table-row-level-0">' +
        tdCenter(ellipsisSpan(d.name, 'font-weight:500;')) +
        tdCenter(ellipsisSpan(d.category)) +
        tdCenter(d.url ? '<a href="' + esc(d.url) + '" target="_blank" rel="noopener" class="ellipsis-text" title="' + esc(d.url) + '">' + esc(d.url) + '</a>' : '-') +
        tdCenter(esc(d.sort === null || d.sort === undefined ? '-' : d.sort)) +
        opsCell([{ key: 'edit', label: '编辑' }, { key: 'delete', label: '删除', danger: true }]) +
        '</tr>';
    }).join('');
    fillTbody(rows);
  }

  function renderKnowledge(resp) {
    var list = (resp.data && resp.data.list) || [];
    var rows = list.map(function (d) {
      var status = d.status === 1 ? greenTag('启用') : grayTag('停用');
      return '<tr data-row-key="' + d.id + '" class="ant-table-row ant-table-row-level-0">' +
        tdCenter(ellipsisSpan(d.name, 'font-weight:500;')) +
        tdCenter(status) +
        tdCenter(esc(d.docCount === null || d.docCount === undefined ? '-' : d.docCount)) +
        tdCenter(esc(d.chunkCount === null || d.chunkCount === undefined ? '-' : d.chunkCount)) +
        tdCenter(ellipsisSpan(d.createTime)) +
        opsCell([{ key: 'view', label: '文档' }, { key: 'delete', label: '删除', danger: true }]) +
        '</tr>';
    }).join('');
    fillTbody(rows);
  }

  function renderTemplate(resp) {
    var list = (resp.data && resp.data.list) || [];
    var rows = list.map(function (d) {
      var isDefault = d.isDefault ? greenTag('默认') : ellipsisSpan('-');
      return '<tr data-row-key="' + d.id + '" class="ant-table-row ant-table-row-level-0">' +
        tdCenter(ellipsisSpan(d.name, 'font-weight:500;')) +
        tdCenter(ellipsisSpan(d.category)) +
        tdCenter(ellipsisSpan(d.content)) +
        tdCenter(isDefault) +
        tdCenter(ellipsisSpan(d.createTime)) +
        opsCell([{ key: 'edit', label: '编辑' }, { key: 'view', label: '查看' }, { key: 'setdefault', label: '设为默认' }, { key: 'delete', label: '删除', danger: true }]) +
        '</tr>';
    }).join('');
    fillTbody(rows);
  }

  function renderAuthRole(resp) {
    var list = (resp.data && resp.data.list) || [];
    var rows = list.map(function (d) {
      var visible = d.visible ? greenTag('是') : grayTag('否');
      var status = d.status === 1 ? greenTag('启用') : grayTag('停用');
      return '<tr data-row-key="' + d.id + '" class="ant-table-row ant-table-row-level-0">' +
        '<td class="ant-table-cell ant-table-selection-column"><!----><label class="ant-checkbox-wrapper ' + currentHash() + '"><span class="ant-checkbox ' + currentHash() + '"><input type="checkbox" class="ant-checkbox-input"><span class="ant-checkbox-inner"></span></span><!----></label><!----></td>' +
        tdCenter('<div class="permission-name-cell"><div class="permission-name-cell__content"><div class="permission-name-cell__title">' + esc(d.title) + '</div><div class="permission-name-cell__sub"><span>' + esc('#' + d.sort) + '</span></div></div></div>') +
        tdCenter('<code class="permission-code">' + esc(d.permission) + '</code>') +
        tdCenter(indigoTag(d.type || '-')) +
        tdCenter(ellipsisSpan(d.route)) +
        tdCenter(ellipsisSpan(d.component)) +
        tdCenter(ellipsisSpan(d.icon)) +
        tdCenter(esc(d.sort === null || d.sort === undefined ? '-' : d.sort)) +
        tdCenter(visible) +
        tdCenter(status) +
        opsCell([{ key: 'edit', label: '编辑' }, { key: 'delete', label: '删除', danger: true }]) +
        '</tr>';
    }).join('');
    fillTbody(rows);
  }

  function renderConfigItem(list, withDefault, withType) {
    return list.map(function (d) {
      var isDefault = withDefault ? (d.isDefault ? greenTag('默认') : ellipsisSpan('-')) : '';
      return '<tr data-row-key="' + d.id + '" class="ant-table-row ant-table-row-level-0">' +
        tdCenter(ellipsisSpan(d.category, 'font-weight:500;')) +
        tdCenter(ellipsisSpan(d.name)) +
        (withType ? tdCenter(ellipsisSpan(d.modelType)) : '') +
        tdCenter(ellipsisSpan(d.description)) +
        (withDefault ? tdCenter(isDefault) : '') +
        tdCenter(ellipsisSpan(d.createTime)) +
        opsCell([{ key: 'edit', label: '编辑' }, { key: 'delete', label: '删除', danger: true }]) +
        '</tr>';
    }).join('');
  }

  function renderConfigModel(resp) {
    var list = (resp.data && resp.data.list) || [];
    fillTbody(renderConfigItem(list, true, true));
  }
  function renderConfigOss(resp) {
    var list = (resp.data && resp.data.list) || [];
    fillTbody(renderConfigItem(list, true, false));
  }
  function renderConfigStt(resp) {
    var list = (resp.data && resp.data.list) || [];
    fillTbody(renderConfigItem(list, true, false));
  }
  function renderConfigTts(resp) {
    var list = (resp.data && resp.data.list) || [];
    fillTbody(renderConfigItem(list, false, false));
  }

  var RENDERERS = {
    'user': renderUser, 'reminder': renderReminder, 'music': renderMusic,
    'knowledge': renderKnowledge, 'template': renderTemplate, 'auth-role': renderAuthRole,
    'config-model': renderConfigModel, 'config-oss': renderConfigOss,
    'config-stt': renderConfigStt, 'config-tts': renderConfigTts
  };

  /* ---------- 通用 ---------- */
  function clearPlaceholder() {
    document.querySelectorAll('.ant-table-placeholder').forEach(function (tr) { tr.remove(); });
  }

  function fillTbody(rowsHtml) {
    var tbody = document.querySelector('.ant-table-tbody');
    if (!tbody) return;
    var measure = tbody.querySelector('.ant-table-measure-row');
    tbody.innerHTML = (measure ? measure.outerHTML : '') + rowsHtml;
    if (!rowsHtml) {
      // 空列表：保留/恢复"暂无数据"占位（渲染函数已删过，补回来）
      var tbl = document.querySelector('.ant-table-container table');
      if (tbl && !document.querySelector('.ant-table-placeholder')) {
        var ph = document.createElement('tr');
        ph.className = 'ant-table-placeholder';
        ph.innerHTML = '<td colspan="20" class="ant-table-cell" style="text-align:center;padding:28px;color:#71717A;">暂无数据</td>';
        tbody.appendChild(ph);
      }
    }
  }

  /* ---------- 加载 ---------- */
  function loadPage(key) {
    var base = API_BASE[key];
    if (!base) return;
    function go() {
      if (!window.QXAuth || !QXAuth.getToken()) return;
      var st = window.QXCrud ? QXCrud.state(key) : { pageNum: 1, pageSize: 10, keyword: '' };
      var path = base + '?pageNum=' + st.pageNum + '&pageSize=' + st.pageSize;
      if (st.keyword) path += '&keyword=' + encodeURIComponent(st.keyword);
      QXAuth.api(path).then(function (j) {
        if (j && j.code === 200 && j.data) {
          QXCrud.setRows(key, j.data.list || []);
          RENDERERS[key](j);
          QXCrud.renderPagination(document, j.data.total, j.data.pageNum, j.data.pageSize);
        }
      }).catch(function (e) { console.warn('[static-pages] ' + key + ' 加载失败:', e); });
    }
    if (window.QXCrud) QXCrud.register(key, go);
    go();
  }

  function init() {
    var p = location.pathname;
    for (var page in PAGE_KEY) {
      if (p.indexOf(page) >= 0) {
        loadPage(PAGE_KEY[page]);
        break;
      }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
