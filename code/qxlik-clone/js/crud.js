/* crud.js —— 全站 CRUD 交互层（新增/编辑/删除/查看/分页/搜索/toast）
 *
 * 依赖：auth.js（QXAuth.api）、static.js（先加载）
 * 约定：表格行 tr[data-row-key=id]，操作链接 a[data-qx-op="edit|delete|view|setdefault"]
 *       渲染引擎（demo-data.js / static-pages.js）调 QXCrud.setRows 注册行数据、
 *       QXCrud.paginationHtml 生成分页器、QXCrud.register 注册刷新函数
 */
(function () {
  'use strict';

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
    if (s === null || s === undefined) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /* ---------- 模块定义：api 路径 + 表单字段 ---------- */
  var MODULES = {
    device: { api: 'device', title: '设备', fields: [
      { k: 'deviceId', l: '设备ID' }, { k: 'deviceName', l: '设备名称' }, { k: 'roleName', l: '角色名称' },
      { k: 'wifiName', l: 'WiFi名称' }, { k: 'location', l: '位置' }, { k: 'online', l: '在线状态', t: 'bool' },
      { k: 'productType', l: '产品类型' }, { k: 'deviceType', l: '设备类型' }, { k: 'version', l: '固件版本' },
      { k: 'orderNo', l: '关联订单号' }, { k: 'source', l: '来源(manual/shop)' }
    ] },
    firmware: { api: 'firmware', title: '固件', fields: [
      { k: 'version', l: '版本号' }, { k: 'chipType', l: '芯片类型' }, { k: 'fileSize', l: '文件大小' },
      { k: 'status', l: '状态(1发布2内测3归档)' }, { k: 'forceUpdate', l: '强制更新', t: 'bool' },
      { k: 'changelog', l: '更新日志', t: 'textarea' }
    ] },
    'memory-chat': { api: 'memory/chat', title: '聊天记录', fields: [
      { k: 'time', l: '时间' }, { k: 'deviceName', l: '设备名称' }, { k: 'sender', l: '发送者(user/agent)' },
      { k: 'tools', l: '调用工具(逗号分隔)' }, { k: 'content', l: '内容', t: 'textarea' }
    ] },
    'memory-long': { api: 'memory/long', title: '长期记忆', fields: [
      { k: 'time', l: '时间' }, { k: 'content', l: '内容', t: 'textarea' }, { k: 'source', l: '来源' },
      { k: 'importance', l: '重要性(high/medium/low)' }
    ] },
    'memory-summary': { api: 'memory/summary', title: '对话摘要', fields: [
      { k: 'time', l: '时间' }, { k: 'deviceName', l: '设备名称' }, { k: 'summary', l: '摘要', t: 'textarea' }
    ] },
    voiceprint: { api: 'voiceprint', title: '声纹', fields: [
      { k: 'speakerId', l: '说话人ID' }, { k: 'name', l: '名称' }, { k: 'description', l: '描述', t: 'textarea' },
      { k: 'status', l: '状态(1正常0停用)' }
    ] },
    'config-agent': { api: 'agent', title: '智能体', fields: [
      { k: 'agentName', l: '智能体名称' }, { k: 'agentId', l: '智能体ID' }, { k: 'platform', l: '平台' },
      { k: 'description', l: '描述', t: 'textarea' }, { k: 'isDefault', l: '设为默认', t: 'bool' }
    ] },
    user: { api: 'user', title: '用户', fields: [
      { k: 'name', l: '名称' }, { k: 'email', l: '邮箱' }, { k: 'tel', l: '电话' },
      { k: 'deviceCount', l: '设备数量' }, { k: 'status', l: '状态(1正常0禁用)' },
      { k: 'accountType', l: '账户类型' }, { k: 'roleName', l: '权限角色' }
    ] },
    reminder: { api: 'reminder', title: '提醒', fields: [
      { k: 'content', l: '提醒内容' }, { k: 'time', l: '触发时间' }, { k: 'repeatType', l: '重复类型' },
      { k: 'status', l: '状态(1已触发0待触发)' }, { k: 'deviceName', l: '设备' }
    ] },
    music: { api: 'music', title: '音乐', fields: [
      { k: 'name', l: '歌曲名称' }, { k: 'category', l: '分类名称' }, { k: 'url', l: '播放地址' },
      { k: 'sort', l: '排序' }
    ] },
    knowledge: { api: 'knowledge', title: '知识库', fields: [
      { k: 'name', l: '名称' }, { k: 'status', l: '状态(1启用0停用)' },
      { k: 'docCount', l: '文档数' }, { k: 'chunkCount', l: '分块数' }
    ] },
    template: { api: 'template', title: '模板', fields: [
      { k: 'name', l: '模板名称' }, { k: 'category', l: '模板分类' }, { k: 'content', l: '模板内容', t: 'textarea' },
      { k: 'isDefault', l: '设为默认', t: 'bool' }
    ] },
    'auth-role': { api: 'auth-role', title: '权限', fields: [
      { k: 'title', l: '权限名称' }, { k: 'permission', l: '权限标识' }, { k: 'type', l: '权限类型' },
      { k: 'route', l: '路由' }, { k: 'component', l: '组件' }, { k: 'icon', l: '图标' },
      { k: 'sort', l: '排序' }, { k: 'visible', l: '菜单显示', t: 'bool' }, { k: 'status', l: '状态(1启用0停用)' }
    ] },
    'config-model': { api: 'config/model', title: '模型', fields: [
      { k: 'category', l: '类别' }, { k: 'name', l: '名称' }, { k: 'modelType', l: '模型类型' },
      { k: 'description', l: '描述', t: 'textarea' }, { k: 'isDefault', l: '设为默认', t: 'bool' }
    ] },
    'config-oss': { api: 'config/oss', title: '存储', fields: [
      { k: 'category', l: '类别' }, { k: 'name', l: '名称' }, { k: 'description', l: '描述', t: 'textarea' },
      { k: 'isDefault', l: '设为默认', t: 'bool' }
    ] },
    'config-stt': { api: 'config/stt', title: '语音识别', fields: [
      { k: 'category', l: '类别' }, { k: 'name', l: '名称' }, { k: 'description', l: '描述', t: 'textarea' },
      { k: 'isDefault', l: '设为默认', t: 'bool' }
    ] },
    'config-tts': { api: 'config/tts', title: '语音合成', fields: [
      { k: 'category', l: '类别' }, { k: 'name', l: '名称' }, { k: 'description', l: '描述', t: 'textarea' }
    ] }
  };

  var KEY_BY_PAGE = {
    'device.html': 'device', 'firmware.html': 'firmware',
    'memory-chat.html': 'memory-chat', 'memory-long.html': 'memory-long', 'memory-summary.html': 'memory-summary',
    'voiceprint.html': 'voiceprint', 'config-agent.html': 'config-agent',
    'user.html': 'user', 'reminder.html': 'reminder', 'music.html': 'music',
    'knowledge.html': 'knowledge', 'template.html': 'template', 'auth-role.html': 'auth-role',
    'config-model.html': 'config-model', 'config-oss.html': 'config-oss',
    'config-stt.html': 'config-stt', 'config-tts.html': 'config-tts'
  };

  var loaders = {};      // pageKey -> refresh fn
  var rowsCache = {};    // pageKey -> {id: rowObj}
  var pageState = {};    // pageKey -> {pageNum, pageSize, keyword}

  function pageKey() {
    var p = location.pathname;
    for (var page in KEY_BY_PAGE) {
      if (p.indexOf(page) >= 0) return KEY_BY_PAGE[page];
    }
    return null;
  }

  /* ---------- toast ---------- */
  var TOAST_TIMERS = [];
  function toast(msg, isOk) {
    var color = isOk ? '#10B981' : '#EF4444';
    var icon = isOk
      ? '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor"><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm193.5 301.7l-210.6 292a31.8 31.8 0 01-51.7 0L318.5 484.9c-3.8-5.3 0-12.7 6.5-12.7h46.9c10.2 0 19.9 4.9 25.9 13.3l71.2 98.8 157.2-218c6-8.3 15.6-13.3 25.9-13.3H699c6.5 0 10.3 7.4 6.5 12.7z"/></svg>'
      : '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor"><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm165.4 618.2l-66-.3L512 563.4l-99.3 118.4-66.1.3c-4.4 0-8-3.5-8-8 0-1.9.7-3.7 1.9-5.2l130.1-155L340.5 359a8.32 8.32 0 01-1.9-5.2c0-4.4 3.6-8 8-8l66.1.3L512 464.6l99.3-118.4 66-.3c4.4 0 8 3.5 8 8 0 1.9-.7 3.7-1.9 5.2L553.5 514l130 155c1.2 1.5 1.9 3.3 1.9 5.2 0 4.4-3.6 8-8 8z"/></svg>';
    var el = document.createElement('div');
    el.className = 'ant-message-notice';
    el.style.cssText = 'position:fixed;top:24px;left:50%;transform:translateX(-50%);z-index:9999;' +
      'display:flex;align-items:center;gap:8px;background:#fff;color:#333;padding:10px 16px;border-radius:8px;' +
      'box-shadow:0 6px 16px rgba(0,0,0,.2);font-size:14px;transition:opacity .3s;opacity:1;';
    el.innerHTML = '<span style="color:' + color + ';display:inline-flex;font-size:16px;">' + icon + '</span><span>' + esc(msg) + '</span>';
    document.body.appendChild(el);
    var timer = setTimeout(function () {
      el.style.opacity = '0';
      setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 300);
    }, 2500);
    TOAST_TIMERS.push(timer);
  }

  /* ---------- API 调用 ---------- */
  function apiCall(path, method, body) {
    var opts = { method: method || 'GET' };
    if (body !== undefined) {
      opts.headers = { 'Content-Type': 'application/json' };
      opts.body = JSON.stringify(body);
    }
    return QXAuth.api(path, opts);
  }

  /* ---------- Modal ---------- */
  function openModal(title, bodyHtml, onOk) {
    var h = hash();
    var wrap = document.createElement('div');
    wrap.className = 'ant-modal-wrap';
    var modal = document.createElement('div');
    modal.className = 'ant-modal ' + h;
    modal.style.cssText = 'width:540px;margin:0 auto;';
    var inner = '<div tabindex="0"><div class="ant-modal-content">' +
      '<button type="button" aria-label="Close" class="ant-modal-close"><span class="ant-modal-close-x">' +
      '<span role="img" aria-label="close" class="anticon anticon-close ant-modal-close-icon"><svg focusable="false" data-icon="close" width="1em" height="1em" fill="currentColor" aria-hidden="true" viewBox="64 64 896 896"><path d="M799.86 166.31c.02 0 .04.02.08.06l57.69 57.7c.04.03.05.05.06.08a.12.12 0 010 .06c0 .03-.02.05-.06.09L569.93 512l287.7 287.7c.04.04.05.06.06.09a.12.12 0 010 .07c0 .02-.02.04-.06.08l-57.7 57.69c-.03.04-.05.05-.07.06a.12.12 0 01-.07 0c-.03 0-.05-.02-.09-.06L512 569.93l-287.7 287.7c-.04.04-.06.05-.09.06a.12.12 0 01-.07 0c-.02 0-.04-.02-.08-.06l-57.69-57.7c-.04-.03-.05-.05-.06-.07a.12.12 0 010-.07c0-.03.02-.05.06-.09L454.07 512l-287.7-287.7c-.04-.04-.05-.05-.06-.09a.12.12 0 010-.07c0-.02.02-.04.06-.08l57.7-57.69c.03-.04.05-.05.07-.06a.12.12 0 01.07 0c.03 0 .05.02.09.06L512 454.07l287.7-287.7c.04-.04.06-.05.09-.06a.12.12 0 01-.01-.01l57.69 57.7c.02.03.04.05.06.07a.12.12 0 010 .07c0 .02-.02.04-.06.08L569.93 512l287.7 287.7c.04.04.06.05.09.06a.12.12 0 010 .07c0 .03-.02.05-.06.09z"></path></svg></span></span></button>' +
      '<div class="ant-modal-header"><div class="ant-modal-title">' + esc(title) + '</div></div>' +
      '<div class="ant-modal-body" style="max-height:62vh;overflow-y:auto;">' + bodyHtml + '</div>' +
      '<div class="ant-modal-footer"><div class="ant-modal-footer-buttons">' +
      '<button type="button" class="ant-btn ' + h + ' qx-m-close"><span>取 消</span></button>' +
      '<button type="button" class="ant-btn ant-btn-primary ' + h + ' qx-m-ok"><span>确 定</span></button>' +
      '</div></div></div></div>';
    modal.innerHTML = inner;
    wrap.appendChild(modal);
    var mask = document.createElement('div');
    mask.className = 'ant-modal-mask';
    document.body.appendChild(mask);
    document.body.appendChild(wrap);
    function close() { wrap.remove(); mask.remove(); }
    modal.querySelector('.ant-modal-close').addEventListener('click', close);
    modal.querySelector('.qx-m-close').addEventListener('click', close);
    mask.addEventListener('click', close);
    // switch toggle
    modal.querySelectorAll('.qx-switch').forEach(function (sw) {
      sw.addEventListener('click', function () { sw.classList.toggle('ant-switch-checked'); });
    });
    modal.querySelector('.qx-m-ok').addEventListener('click', function () {
      onOk(collectForm(modal), close);
    });
  }

  function fieldHtml(f, val) {
    var h = hash();
    var v = val === null || val === undefined ? '' : val;
    var html = '<div class="ant-form-item ' + h + '"><div class="ant-row ant-form-item-row ' + h + '">' +
      '<div class="ant-col ant-col-6 ant-form-item-label ' + h + '"><label class="ant-form-item-no-colon" title="' + esc(f.l) + '">' + esc(f.l) + '</label></div>' +
      '<div class="ant-col ant-col-18 ant-form-item-control ' + h + '"><div class="ant-form-item-control-input"><div class="ant-form-item-control-input-content">';
    if (f.t === 'bool') {
      html += '<button type="button" class="ant-switch qx-switch ' + h + (v ? ' ant-switch-checked' : '') + '" data-qx-f="' + f.k + '"><div class="ant-switch-handle"></div></button>';
    } else if (f.t === 'textarea') {
      html += '<textarea class="ant-input ' + h + '" rows="4" data-qx-f="' + f.k + '" placeholder="请输入' + esc(f.l) + '">' + esc(v) + '</textarea>';
    } else {
      html += '<input type="text" class="ant-input ' + h + '" data-qx-f="' + f.k + '" placeholder="请输入' + esc(f.l) + '" value="' + esc(v) + '">';
    }
    html += '</div></div></div></div></div>';
    return html;
  }

  function collectForm(modal) {
    var out = {};
    modal.querySelectorAll('[data-qx-f]').forEach(function (el) {
      var k = el.getAttribute('data-qx-f');
      if (el.classList.contains('qx-switch')) {
        out[k] = el.classList.contains('ant-switch-checked');
      } else {
        out[k] = el.value.trim();
      }
    });
    return out;
  }

  /* ---------- 编辑 / 查看 ---------- */
  function openForm(key, row) {
    var m = MODULES[key];
    var isEdit = !!row;
    var body = '<form class="ant-form ant-form-horizontal ' + hash() + '">' +
      m.fields.map(function (f) { return fieldHtml(f, isEdit ? row[f.k] : ''); }).join('') +
      '</form>';
    openModal((isEdit ? '编辑' : '新增') + m.title, body, function (vals, close) {
      var path = '/api/' + m.api + '/' + (isEdit ? 'update' : 'create');
      var payload = vals;
      if (isEdit) payload.id = row.id;
      apiCall(path, 'POST', payload).then(function (j) {
        if (j && j.code === 200) {
          toast((isEdit ? '更新' : '创建') + '成功', true);
          close();
          QXCrud.refresh(key);
        } else {
          toast((j && j.message) || '操作失败', false);
        }
      }).catch(function () { toast('网络异常，请稍后重试', false); });
    });
  }

  function openView(key, row) {
    var m = MODULES[key];
    var h = hash();
    var rowsHtml = m.fields.map(function (f) {
      var v = row[f.k];
      if (v === null || v === undefined || v === '') v = '-';
      return '<div class="ant-row ' + h + '" style="padding:8px 0;border-bottom:1px solid var(--ant-color-border-secondary);">' +
        '<div class="ant-col ant-col-8" style="font-weight:500;color:var(--ant-color-text);">' + esc(f.l) + '</div>' +
        '<div class="ant-col ant-col-16" style="color:var(--ant-color-text-secondary);word-break:break-all;">' + esc(v) + '</div></div>';
    }).join('');
    openModal('查看' + m.title, rowsHtml, function (_vals, close) { close(); });
  }

  function confirmDelete(key, row) {
    if (!window.confirm('确认删除该条数据吗？删除后不可恢复。')) return;
    apiCall('/api/' + MODULES[key].api + '/delete', 'POST', { id: row.id }).then(function (j) {
      if (j && j.code === 200) {
        toast('删除成功', true);
        QXCrud.refresh(key);
      } else {
        toast((j && j.message) || '删除失败', false);
      }
    }).catch(function () { toast('网络异常，请稍后重试', false); });
  }

  function setDefault(key, row) {
    apiCall('/api/' + MODULES[key].api + '/update', 'POST', { id: row.id, isDefault: 1 }).then(function (j) {
      if (j && j.code === 200) {
        toast('已设为默认', true);
        QXCrud.refresh(key);
      } else {
        toast((j && j.message) || '操作失败', false);
      }
    }).catch(function () { toast('网络异常，请稍后重试', false); });
  }

  /* ---------- 分页器 ---------- */
  var ICON_LEFT = '<svg focusable="false" data-icon="left" width="1em" height="1em" fill="currentColor" aria-hidden="true" viewBox="64 64 896 896"><path d="M724 218.3V141c0-6.7-7.7-10.4-12.9-6.3L260.3 486.8a31.86 31.86 0 000 50.3l450.8 352.1c5.3 4.1 12.9.4 12.9-6.3v-77.3c0-4.9-2.3-9.6-6.1-12.6l-360-281 360-281.1c3.8-3 6.1-7.7 6.1-12.6z"></path></svg>';
  var ICON_RIGHT = '<svg focusable="false" data-icon="right" width="1em" height="1em" fill="currentColor" aria-hidden="true" viewBox="64 64 896 896"><path d="M765.7 486.8L314.9 134.7A7.97 7.97 0 00302 141v77.3c0 4.9 2.3 9.6 6.1 12.6l360 281.1-360 281.1c-3.9 3-6.1 7.7-6.1 12.6V883c0 6.7 7.7 10.4 12.9 6.3l450.8-352.1a31.96 31.96 0 000-50.4z"></path></svg>';

  function paginationHtml(total, pageNum, pageSize) {
    var h = hash();
    var pages = Math.max(1, Math.ceil(total / pageSize));
    var html = '<ul unselectable="on" size="small" class="ant-pagination ant-pagination-mini ant-table-pagination ant-table-pagination-right ' + h + '">';
    html += '<li class="ant-pagination-total-text">共 ' + total + ' 条</li>';
    // prev
    html += '<li title="上一页" class="ant-pagination-prev' + (pageNum <= 1 ? ' ant-pagination-disabled' : '') + '">' +
      '<button class="ant-pagination-item-link" type="button" data-qx-page="' + (pageNum - 1) + '"' + (pageNum <= 1 ? ' disabled' : '') + '><span role="img" aria-label="left" class="anticon anticon-left">' + ICON_LEFT + '</span></button></li>';
    // page numbers (窗口最多 7 个)
    var start = Math.max(1, pageNum - 3);
    var end = Math.min(pages, start + 6);
    start = Math.max(1, end - 6);
    if (start > 1) html += '<li title="1" class="ant-pagination-item"><a data-qx-page="1">1</a></li>';
    if (start > 2) html += '<li class="ant-pagination-jump-prev ant-pagination-jump-prev-custom-icon" title="向前 5 页"><a>•••</a></li>';
    for (var i = start; i <= end; i++) {
      html += '<li title="' + i + '" tabindex="0" class="ant-pagination-item ant-pagination-item-' + i + (i === pageNum ? ' ant-pagination-item-active' : '') + '"><a data-qx-page="' + i + '">' + i + '</a></li>';
    }
    if (end < pages - 1) html += '<li class="ant-pagination-jump-next ant-pagination-jump-next-custom-icon" title="向后 5 页"><a>•••</a></li>';
    if (end < pages) html += '<li title="' + pages + '" class="ant-pagination-item"><a data-qx-page="' + pages + '">' + pages + '</a></li>';
    // next
    html += '<li title="下一页" class="ant-pagination-next' + (pageNum >= pages ? ' ant-pagination-disabled' : '') + '">' +
      '<button class="ant-pagination-item-link" type="button" data-qx-page="' + (pageNum + 1) + '"' + (pageNum >= pages ? ' disabled' : '') + '><span role="img" aria-label="right" class="anticon anticon-right">' + ICON_RIGHT + '</span></button></li>';
    // pageSize 切换（点击循环 10→20→50）
    html += '<li class="ant-pagination-options"><div class="ant-select ant-select-sm ' + h + ' ant-pagination-options-size-changer ant-select-single ant-select-show-arrow"><!---->' +
      '<div class="ant-select-selector" style="cursor:pointer;" data-qx-pagesize-cycle="1" title="点击切换每页条数">' +
      '<span class="ant-select-selection-search"><input type="search" class="ant-select-selection-search-input" readonly="" value="" style="opacity: 0;"></span>' +
      '<span class="ant-select-selection-item">' + pageSize + ' 条/页</span></div>' +
      '<span class="ant-select-arrow" unselectable="on" aria-hidden="true" style="user-select: none;"><span role="img" aria-label="down" class="anticon anticon-down ant-select-suffix"><svg focusable="false" data-icon="down" width="1em" height="1em" fill="currentColor" aria-hidden="true" viewBox="64 64 896 896"><path d="M884 256h-75c-5.1 0-9.9 2.5-12.9 6.6L512 654.2 227.9 262.6c-3-4.1-7.8-6.6-12.9-6.6h-75c-6.5 0-10.3 7.4-6.5 12.7l352.6 486.1c12.8 17.6 39 17.6 51.7 0l352.6-486.1c3.9-5.3.1-12.7-6.4-12.7z"></path></svg></span></span></div></li>';
    html += '</ul>';
    return html;
  }

  /* ---------- 对外 API ---------- */
  var QXCrud = {
    register: function (key, fn) { loaders[key] = fn; },
    pageKey: pageKey,
    module: function (key) { return MODULES[key]; },
    setRows: function (key, list) {
      var m = {};
      (list || []).forEach(function (r) { m[r.id] = r; });
      rowsCache[key] = m;
    },
    row: function (key, id) { return (rowsCache[key] || {})[id]; },
    state: function (key) {
      if (!pageState[key]) pageState[key] = { pageNum: 1, pageSize: 10, keyword: '' };
      return pageState[key];
    },
    refresh: function (key) { if (loaders[key]) loaders[key](); },
    toast: toast,
    paginationHtml: paginationHtml,
    renderPagination: function (container, total, pageNum, pageSize) {
      // container 里替换/插入分页器
      var existing = container.querySelector('.ant-table-pagination');
      var html = paginationHtml(total, pageNum, pageSize);
      if (existing) {
        var host = document.createElement('div');
        host.innerHTML = html;
        existing.parentNode.replaceChild(host.firstChild, existing);
      } else {
        var wrapper = container.querySelector('.ant-table-wrapper');
        if (wrapper && wrapper.parentElement) {
          var div = document.createElement('div');
          div.innerHTML = html;
          wrapper.parentElement.appendChild(div.firstChild);
        }
      }
    }
  };
  window.QXCrud = QXCrud;

  /* ---------- 事件绑定 ---------- */
  document.addEventListener('DOMContentLoaded', function () { bindAll(); });
  if (document.readyState !== 'loading') bindAll();

  function bindAll() {
    // 操作列（全局委托）
    document.addEventListener('click', function (e) {
      var a = e.target.closest ? e.target.closest('a[data-qx-op]') : null;
      if (!a) return;
      e.preventDefault();
      e.stopPropagation();
      var key = pageKey();
      if (!key || !MODULES[key]) return;
      var op = a.getAttribute('data-qx-op');
      var tr = a.closest('tr');
      var id = tr ? tr.getAttribute('data-row-key') : null;
      var row = id ? QXCrud.row(key, id) : null;
      if (!row) return;
      if (op === 'edit') openForm(key, row);
      else if (op === 'view') openView(key, row);
      else if (op === 'delete') confirmDelete(key, row);
      else if (op === 'setdefault') setDefault(key, row);
    });

    // 分页（全局委托）
    document.addEventListener('click', function (e) {
      var t = e.target.closest ? e.target.closest('[data-qx-page]') : null;
      if (!t || t.disabled) return;
      var key = pageKey();
      if (!key || !loaders[key]) return;
      var p = parseInt(t.getAttribute('data-qx-page'), 10);
      if (!(p >= 1)) return;
      var st = QXCrud.state(key);
      st.pageNum = p;
      QXCrud.refresh(key);
    });

    // pageSize 切换
    document.addEventListener('click', function (e) {
      var t = e.target.closest ? e.target.closest('[data-qx-pagesize-cycle]') : null;
      if (!t) return;
      var key = pageKey();
      if (!key || !loaders[key]) return;
      var st = QXCrud.state(key);
      var seq = [10, 20, 50];
      var idx = seq.indexOf(st.pageSize);
      st.pageSize = seq[(idx + 1) % seq.length];
      st.pageNum = 1;
      QXCrud.refresh(key);
    });

    bindCreateButtons();
    bindSearchButtons();
  }

  /* ---------- 新增按钮 ---------- */
  var CREATE_TRIGGERS = {
    device: ['添加设备'], firmware: ['上传固件'], voiceprint: ['新增说话人'],
    template: ['创建模板'],
    'config-model': ['创 建'], 'config-oss': ['创 建'], 'config-stt': ['创 建'], 'config-tts': ['创 建']
  };

  function bindCreateButtons() {
    var key = pageKey();
    if (!key || !CREATE_TRIGGERS[key]) return;
    var texts = CREATE_TRIGGERS[key];
    document.querySelectorAll('button').forEach(function (b) {
      if (b.__qx_create_bound) return;
      var t = (b.textContent || '').trim();
      if (texts.indexOf(t) >= 0) {
        b.__qx_create_bound = true;
        b.addEventListener('click', function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          openForm(key, null);
        });
      }
    });
  }

  /* ---------- 搜索 ---------- */
  function collectKeyword(scope) {
    var parts = [];
    scope.querySelectorAll('input[type="text"]').forEach(function (inp) {
      var v = (inp.value || '').trim();
      if (v) parts.push(v);
    });
    return parts.join(' ');
  }

  function bindSearchButtons() {
    var key = pageKey();
    if (!key) return;
    var isSearchPage = key === 'firmware' || key === 'reminder';
    document.querySelectorAll('button').forEach(function (b) {
      if (b.__qx_search_bound) return;
      var t = (b.textContent || '').trim().replace(/\s/g, '');
      if (t === '搜索' || t === '查询' || t === '重置') {
        b.__qx_search_bound = true;
        b.addEventListener('click', function () {
          if (!isSearchPage) return;
          var form = b.closest('form') || document;
          var st = QXCrud.state(key);
          if (t === '重置') {
            form.querySelectorAll('input[type="text"]').forEach(function (inp) { inp.value = ''; });
            st.keyword = '';
          } else {
            st.keyword = collectKeyword(form);
          }
          st.pageNum = 1;
          QXCrud.refresh(key);
        });
      }
    });
    // device 页：筛选输入框回车触发搜索
    if (key === 'device') {
      document.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter') return;
        var inp = e.target;
        if (inp.tagName !== 'INPUT' || inp.type !== 'text') return;
        var form = inp.closest('form');
        if (!form) return;
        var st = QXCrud.state(key);
        st.keyword = collectKeyword(form);
        st.pageNum = 1;
        QXCrud.refresh(key);
      });
    }
  }
})();
