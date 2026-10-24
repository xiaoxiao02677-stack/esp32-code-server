/* demo-data.js —— 全站 Demo 数据渲染引擎
 *
 * 设计目标：与后端 API 对齐。后端只需按同一份 JSON 契约返回数据，
 * 前端 fetch() 换成真实接口即可无缝切换。
 *
 * 契约（与 js/data/*.json 同构）：
 *   {
 *     "code": 200, "message": "success",
 *     "data": { "total": N, "pageNum": 1, "pageSize": 10, "list": [ ... ] }
 *   }
 *
 * 渲染约定：每行 <tr> 复用原站捕获的行模板结构（含 ant-* class 与
 * cssinjs 哈希 class），只替换单元格内容。
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
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  /* ---------- 单元格构造器 ---------- */
  function tdCenter(html, extraStyle) {
    return '<td class="ant-table-cell" style="text-align: center;' + (extraStyle || '') + '"><!---->' + html + '<!----></td>';
  }
  function tdCenterFix(html, styleAttr) {
    return '<td class="ant-table-cell ant-table-cell-fix-right ant-table-cell-fix-right-first" style="text-align: center; position: sticky; right: 0px;"><!---->' + html + '<!----></td>';
  }
  function textCell(v) {
    return tdCenter(ellipsisSpan(v));
  }
  // 带 title 悬浮提示的 ellipsis span；style 为可选内联样式
  function ellipsisSpan(v, style) {
    var s = (v === null || v === undefined) ? '-' : String(v);
    var attr = ' class="ellipsis-text"';
    if (style) attr += ' style="' + style + '"';
    if (s && s !== '-') attr += ' title="' + esc(s).replace(/"/g, '&quot;') + '"';
    return '<span' + attr + '>' + esc(s) + '</span>';
  }

  // 状态徽标（内联样式兜底，主题切换时由 --ant-* 变量自适应）
  function statusTag(online) {
    if (online) {
      return '<span class="ant-tag ' + currentHash() + '" style="display:inline-flex;align-items:center;gap:6px;background:rgba(16,185,129,.12);border-color:rgba(16,185,129,.35);color:#10B981;">' +
        '<span class="status-dot" style="width:6px;height:6px;border-radius:50%;background:#10B981;box-shadow:0 0 6px #10B981;"></span>正常</span>';
    }
    return '<span class="ant-tag ' + currentHash() + '" style="display:inline-flex;align-items:center;gap:6px;background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.35);color:#EF4444;">' +
      '<span class="status-dot" style="width:6px;height:6px;border-radius:50%;background:#EF4444;"></span>离线</span>';
  }

  // 角色徽标
  function roleTag(name) {
    return '<span class="ant-tag ' + currentHash() + '" style="background:rgba(99,102,241,.12);border-color:rgba(99,102,241,.35);color:#6366F1;">' + esc(name) + '</span>';
  }

  // 操作列：编辑 | 删除（带分隔线）
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

  /* ---------- 分页器 ---------- */
  var PAG_TEMPLATE = null;

  function ensurePagination(total, pageSize) {
    var existing = document.querySelector('.ant-table-pagination');
    if (existing) {
      var tt = existing.querySelector('.ant-pagination-total-text');
      if (tt) tt.textContent = '共 ' + total + ' 条';
      return;
    }
    // 无分页器（原站空表不渲染）→ 用捕获模板插入
    if (!PAG_TEMPLATE) return;
    var html = PAG_TEMPLATE
      .replace('{TOTAL}', String(total))
      .replace(/css-97cec0/g, currentHash());
    var host = document.createElement('div');
    host.innerHTML = html;
    var pag = host.firstChild;
    // 插到表格容器后（.ant-table-wrapper 的父 spin-container 末尾）
    var wrapper = document.querySelector('.ant-table-wrapper');
    if (wrapper && wrapper.parentElement) {
      wrapper.parentElement.appendChild(pag);
    }
  }

  /* ---------- 通用表格骨架 ---------- */
  // 清除空表 placeholder 行, 保留 measure-row
  function clearPlaceholder() {
    document.querySelectorAll('.ant-table-placeholder').forEach(function (tr) { tr.remove(); });
  }

  // 在 tbody 末尾插入数据行 (measure-row 已由页面自带或不在, 统一置于数据行前)
  function fillTbody(rowsHtml) {
    var tbody = document.querySelector('.ant-table-tbody');
    if (!tbody) return;
    var measure = tbody.querySelector('.ant-table-measure-row');
    tbody.innerHTML = (measure ? measure.outerHTML : '') + rowsHtml;
  }

  /* ---------- 设备页 ---------- */
  function renderDeviceTable(resp) {
    var list = (resp && resp.data && resp.data.list) || [];
    var total = (resp && resp.data && resp.data.total) || list.length;
    var rows = list.map(function (d) {
      return '<tr data-row-key="' + d.id + '" class="ant-table-row ant-table-row-level-0">' +
        textCell(d.deviceId) +
        tdCenter(ellipsisSpan(esc(d.deviceName), 'font-weight:500;')) +
        tdCenter('<span class="ant-tag ' + currentHash() + '" style="background:rgba(99,102,241,.12);border-color:rgba(99,102,241,.35);color:#6366F1;">' + esc(d.roleName) + '</span>') +
        textCell(d.wifiName) +
        textCell(d.location) +
        tdCenter(statusTag(d.online)) +
        textCell(d.productType) +
        textCell(d.deviceType) +
        textCell(d.version) +
        tdCenter(ellipsisSpan(esc(d.lastActiveTime), 'color:var(--ant-color-text-secondary);')) +
        tdCenter(ellipsisSpan(esc(d.createTime), 'color:var(--ant-color-text-secondary);')) +
        opsCell([{ key: 'edit', label: '编辑' }, { key: 'delete', label: '删除', danger: true }]) +
        '</tr>';
    }).join('');
    var tbody = document.querySelector('.ant-table-tbody');
    if (tbody) {
      // 保留 measure-row，其后插入数据行
      var measure = tbody.querySelector('.ant-table-measure-row');
      if (measure) {
        tbody.innerHTML = measure.outerHTML + rows;
      } else {
        tbody.innerHTML = rows;
      }
    }
    ensurePagination(total, (resp.data && resp.data.pageSize) || 10);
  }

  /* ---------- 首页 (最近设备列表 + 统计卡片) ---------- */
  function renderIndex(resp) {
    var list = (resp && resp.data && resp.data.list) || [];
    var total = (resp && resp.data && resp.data.total) || list.length;
    var rows = list.map(function (d) {
      return '<tr data-row-key="' + d.id + '" class="ant-table-row ant-table-row-level-0">' +
        tdCenter(ellipsisSpan(esc(d.deviceName), 'font-weight:500;')) +
        tdCenter(ellipsisSpan(esc(d.roleName))) +
        tdCenter(statusTag(d.online)) +
        tdCenter(ellipsisSpan(esc(d.lastActiveTime), 'color:var(--ant-color-text-secondary);')) +
        '</tr>';
    }).join('');
    clearPlaceholder();
    fillTbody(rows);
    // 统计卡片: 设备总数/智能体总数 与 API stats 联动（兜底 demo 值）
    var stats = (resp && resp.data && resp.data.stats) || null;
    var values = document.querySelectorAll('.ant-statistic-content-value-int');
    if (values.length >= 3) {
      values[0].textContent = String(stats ? stats.chatTotal : 186);
      values[1].textContent = String(stats ? stats.deviceTotal : 8);   // 设备总数
      values[2].textContent = String(stats ? stats.agentTotal : 6);    // 智能体总数
    }
  }

  /* ---------- 固件管理 ---------- */
  function firmwareStatusTag(status) {
    var map = {
      1: { t: '已发布', bg: 'rgba(16,185,129,.12)', bd: 'rgba(16,185,129,.35)', c: '#10B981' },
      2: { t: '内测中', bg: 'rgba(99,102,241,.12)', bd: 'rgba(99,102,241,.35)', c: '#6366F1' },
      3: { t: '已归档', bg: 'rgba(113,113,122,.12)', bd: 'rgba(113,113,122,.35)', c: '#A1A1AA' }
    };
    var s = map[status] || map[3];
    return '<span class="ant-tag ' + currentHash() + '" style="display:inline-flex;align-items:center;gap:6px;background:' + s.bg + ';border-color:' + s.bd + ';color:' + s.c + ';">' + s.t + '</span>';
  }

  function renderFirmwareTable(resp) {
    var list = (resp && resp.data && resp.data.list) || [];
    var total = (resp && resp.data && resp.data.total) || list.length;
    var rows = list.map(function (d) {
      return '<tr data-row-key="' + d.id + '" class="ant-table-row ant-table-row-level-0">' +
        tdCenter(ellipsisSpan(d.version ? 'v' + d.version : '-', 'font-weight:500')) +
        tdCenter('<span class="ant-tag ' + currentHash() + '" style="background:rgba(99,102,241,.12);border-color:rgba(99,102,241,.35);color:#6366F1;">' + esc(d.chipType) + '</span>') +
        textCell(d.fileSize) +
        tdCenter(firmwareStatusTag(d.status)) +
        tdCenter(ellipsisSpan((d.forceUpdate ? '是' : '否'), 'color:var(--ant-color-text-secondary);')) +
        tdCenter(ellipsisSpan(esc(d.changelog), 'color:var(--ant-color-text-secondary);')) +
        textCell(d.lastOnlineTime) +
        opsCell([{ key: 'edit', label: '编辑' }, { key: 'delete', label: '删除', danger: true }]) +
        '</tr>';
    }).join('');
    clearPlaceholder();
    fillTbody(rows);
    ensurePagination(total, (resp.data && resp.data.pageSize) || 10);
  }

  /* ---------- 记忆-聊天记录 ---------- */
  function senderTag(sender) {
    if (sender === 'user') {
      return '<span class="ant-tag ' + currentHash() + '" style="display:inline-flex;align-items:center;gap:6px;background:rgba(16,185,129,.12);border-color:rgba(16,185,129,.35);color:#10B981;">用户</span>';
    }
    return '<span class="ant-tag ' + currentHash() + '" style="display:inline-flex;align-items:center;gap:6px;background:rgba(99,102,241,.12);border-color:rgba(99,102,241,.35);color:#6366F1;">智能体</span>';
  }

  function renderMemoryChatTable(resp) {
    var list = (resp && resp.data && resp.data.list) || [];
    var total = (resp && resp.data && resp.data.total) || list.length;
    var rows = list.map(function (d) {
      var tools = (d.tools && d.tools.length)
        ? '<span class="ant-tag ' + currentHash() + '" style="background:rgba(16,185,129,.12);border-color:rgba(16,185,129,.35);color:#10B981;">' + esc(d.tools.join(',')) + '</span>'
        : '<span class="ellipsis-text" style="color:var(--ant-color-text-secondary);">-</span>';
      var audio = d.audio
        ? '<span class="ant-tag ' + currentHash() + '" style="background:rgba(99,102,241,.12);border-color:rgba(99,102,241,.35);color:#6366F1;">有</span>'
        : '<span class="ellipsis-text" style="color:var(--ant-color-text-secondary);">-</span>';
      return '<tr data-row-key="' + d.id + '" class="ant-table-row ant-table-row-level-0">' +
        '<td class="ant-table-cell ant-table-row-expand-icon-cell" style="text-align: center;"><span class="ant-table-row-expand-icon ant-table-row-expand-icon-collapsed" aria-label="展开行"></span></td>' +
        textCell(d.time) +
        textCell(d.deviceName) +
        tdCenter(senderTag(d.sender)) +
        tdCenter(tools) +
        tdCenter(ellipsisSpan(esc(d.content), 'color:var(--ant-color-text-secondary);')) +
        tdCenter(audio) +
        opsCell([{ key: 'view', label: '查看' }, { key: 'delete', label: '删除', danger: true }]) +
        '</tr>';
    }).join('');
    clearPlaceholder();
    fillTbody(rows);
    ensurePagination(total, (resp.data && resp.data.pageSize) || 10);
  }

  /* ---------- 记忆-长期记忆 ---------- */
  function importanceTag(imp) {
    var map = {
      high: { t: '高', bg: 'rgba(239,68,68,.12)', bd: 'rgba(239,68,68,.35)', c: '#EF4444' },
      medium: { t: '中', bg: 'rgba(99,102,241,.12)', bd: 'rgba(99,102,241,.35)', c: '#6366F1' },
      low: { t: '低', bg: 'rgba(113,113,122,.12)', bd: 'rgba(113,113,122,.35)', c: '#A1A1AA' }
    };
    var s = map[imp] || map.low;
    return '<span class="ant-tag ' + currentHash() + '" style="display:inline-flex;align-items:center;gap:6px;background:' + s.bg + ';border-color:' + s.bd + ';color:' + s.c + ';">' + s.t + '</span>';
  }

  function renderMemoryLongTable(resp) {
    var list = (resp && resp.data && resp.data.list) || [];
    var total = (resp && resp.data && resp.data.total) || list.length;
    var rows = list.map(function (d) {
      return '<tr data-row-key="' + d.id + '" class="ant-table-row ant-table-row-level-0">' +
        textCell(d.time) +
        tdCenter(ellipsisSpan(esc(d.content))) +
        tdCenter(ellipsisSpan(esc(d.source), 'color:var(--ant-color-text-secondary);')) +
        tdCenter(importanceTag(d.importance)) +
        opsCell([{ key: 'edit', label: '编辑' }, { key: 'delete', label: '删除', danger: true }]) +
        '</tr>';
    }).join('');
    clearPlaceholder();
    fillTbody(rows);
    ensurePagination(total, (resp.data && resp.data.pageSize) || 10);
  }

  /* ---------- 记忆-对话摘要 ---------- */
  function renderMemorySummaryTable(resp) {
    var list = (resp && resp.data && resp.data.list) || [];
    var total = (resp && resp.data && resp.data.total) || list.length;
    var rows = list.map(function (d) {
      return '<tr data-row-key="' + d.id + '" class="ant-table-row ant-table-row-level-0">' +
        textCell(d.time) +
        textCell(d.deviceName) +
        tdCenter(ellipsisSpan(esc(d.summary), 'color:var(--ant-color-text-secondary);')) +
        opsCell([{ key: 'view', label: '查看' }, { key: 'delete', label: '删除', danger: true }]) +
        '</tr>';
    }).join('');
    clearPlaceholder();
    fillTbody(rows);
    ensurePagination(total, (resp.data && resp.data.pageSize) || 10);
  }

  /* ---------- 声纹 ---------- */
  function renderVoiceprintTable(resp) {
    var list = (resp && resp.data && resp.data.list) || [];
    var total = (resp && resp.data && resp.data.total) || list.length;
    var rows = list.map(function (d) {
      return '<tr data-row-key="' + d.id + '" class="ant-table-row ant-table-row-level-0">' +
        tdCenter(ellipsisSpan(esc(d.speakerId), 'font-weight:500;')) +
        tdCenter(ellipsisSpan(esc(d.name))) +
        tdCenter(ellipsisSpan(esc(d.description), 'color:var(--ant-color-text-secondary);')) +
        tdCenter(statusTag(d.status === 1)) +
        opsCell([{ key: 'edit', label: '编辑' }, { key: 'delete', label: '删除', danger: true }]) +
        '</tr>';
    }).join('');
    clearPlaceholder();
    fillTbody(rows);
    ensurePagination(total, (resp.data && resp.data.pageSize) || 10);
  }

  /* ---------- 智能体管理 ---------- */
  function renderAgentTable(resp) {
    var list = (resp && resp.data && resp.data.list) || [];
    var total = (resp && resp.data && resp.data.total) || list.length;
    var rows = list.map(function (d) {
      var avatar = '<span class="ant-avatar ant-avatar-circle ' + currentHash() + '" style="width:36px;height:36px;line-height:36px;background:rgba(99,102,241,.15);color:#6366F1;font-size:16px;">' +
        esc(String(d.agentName).charAt(0)) + '</span>';
      var isDefault = d.isDefault
        ? '<span class="ant-tag ' + currentHash() + '" style="display:inline-flex;align-items:center;gap:6px;background:rgba(16,185,129,.12);border-color:rgba(16,185,129,.35);color:#10B981;">默认</span>'
        : '<span class="ellipsis-text" style="color:var(--ant-color-text-secondary);">-</span>';
      return '<tr data-row-key="' + d.id + '" class="ant-table-row ant-table-row-level-0">' +
        '<td class="ant-table-cell ant-table-cell-fix-left" style="text-align: center; position: sticky; left: 0px;"><!---->' + avatar + '<!----></td>' +
        '<td class="ant-table-cell ant-table-cell-fix-left ant-table-cell-fix-left-last" style="text-align: center; position: sticky; left: 80px;"><!---->' + ellipsisSpan(d.agentName, 'font-weight:500') + '<!----></td>' +
        textCell(d.agentId) +
        tdCenter(ellipsisSpan(esc(d.platform), 'color:var(--ant-color-text-secondary);')) +
        tdCenter(ellipsisSpan(esc(d.description), 'color:var(--ant-color-text-secondary);')) +
        tdCenter(isDefault) +
        textCell(d.publishTime) +
        opsCell([{ key: 'edit', label: '编辑' }, { key: 'delete', label: '删除', danger: true }]) +
        '</tr>';
    }).join('');
    clearPlaceholder();
    fillTbody(rows);
    ensurePagination(total, (resp.data && resp.data.pageSize) || 10);
  }

  /* ---------- 数据加载器：真实 API 优先，本地 demo JSON 兜底 ---------- */
  // 页面 key → API 路径
  var API_ROUTES = {
    'device': '/api/device/list',
    'index': '/api/index/recent',
    'firmware': '/api/firmware/list',
    'memory-chat': '/api/memory/chat/list',
    'memory-long': '/api/memory/long/list',
    'memory-summary': '/api/memory/summary/list',
    'voiceprint': '/api/voiceprint/list',
    'config-agent': '/api/agent/list'
  };

  function loadFromApi(path, cb, fallback) {
    if (!window.QXAuth || !QXAuth.getToken()) { fallback(); return; }
    QXAuth.api(path)
      .then(function (j) {
        if (j && j.code === 200 && j.data) { cb(j); }
        else { fallback(); }
      })
      .catch(function () { fallback(); });
  }

  function loadDemoData(page, cb) {
    var fallback = function () {
      fetch('../js/data/' + page + '.json')
        .then(function (r) { return r.json(); })
        .then(cb)
        .catch(function (e) { console.warn('[demo-data] ' + page + ' 数据加载失败:', e); });
    };
    var apiPath = API_ROUTES[page];
    if (apiPath) { loadFromApi(apiPath, cb, fallback); }
    else { fallback(); }
  }

  /* ---------- 初始化 ---------- */
  function init() {
    var path = location.pathname;
    // 预载分页模板
    fetch('../js/data/pagination_template.html')
      .then(function (r) { return r.text(); })
      .then(function (t) { PAG_TEMPLATE = t; })
      .catch(function () {})
      .then(function () {
        if (path.indexOf('device.html') >= 0) {
          loadDemoData('device', renderDeviceTable);
        } else if (path.indexOf('index.html') >= 0) {
          loadDemoData('index', renderIndex);
        } else if (path.indexOf('firmware.html') >= 0) {
          loadDemoData('firmware', renderFirmwareTable);
        } else if (path.indexOf('memory-chat.html') >= 0) {
          loadDemoData('memory-chat', renderMemoryChatTable);
        } else if (path.indexOf('memory-long.html') >= 0) {
          loadDemoData('memory-long', renderMemoryLongTable);
        } else if (path.indexOf('memory-summary.html') >= 0) {
          loadDemoData('memory-summary', renderMemorySummaryTable);
        } else if (path.indexOf('voiceprint.html') >= 0) {
          loadDemoData('voiceprint', renderVoiceprintTable);
        } else if (path.indexOf('config-agent.html') >= 0) {
          loadDemoData('config-agent', renderAgentTable);
        }
      });

    // 主题切换时同步 demo 行内哈希 class
    document.addEventListener('qx-theme-change', function (e) {
      var target = e.detail.mode === 'light' ? LIGHT_HASH : DARK_HASH;
      var from = e.detail.mode === 'light' ? DARK_HASH : LIGHT_HASH;
      document.querySelectorAll('.ant-table-tbody .' + from + ', .ant-table-tbody [class*="' + from + '"]')
        .forEach(function (el) { el.classList.remove(from); el.classList.add(target); });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
