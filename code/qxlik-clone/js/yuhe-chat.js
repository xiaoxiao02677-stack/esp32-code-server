/* yuhe-chat.js — 聊天记录页接管：memory-chat.html 接主站 /agent/{id}/sessions + /agent/{id}/chat-history/{sid}
 * 依赖：yuhe-api.js（QXYuhe） */
(function () {
  'use strict';
  if (!window.QXYuhe) return;

  function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function hashCls() {
    var t = document.querySelector('.ant-table-tbody tr');
    if (!t) return '';
    var m = (t.className || '').match(/(?:^|\s)(css-\S+)/);
    return m ? m[1] : '';
  }
  function td(html, center) {
    return '<td class="ant-table-cell"' + (center ? ' style="text-align:center;"' : '') + '>' + html + '</td>';
  }
  function ellipsis(v, style) {
    return '<span class="ellipsis-text" style="' + (style || '') + 'max-width:260px;display:inline-block;vertical-align:bottom;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + esc(v) + '</span>';
  }
  function tag(text, bg, bd, c) {
    return '<span class="ant-tag ' + hashCls() + '" style="display:inline-flex;align-items:center;gap:6px;background:' + bg + ';border-color:' + bd + ';color:' + c + ';">' + esc(text) + '</span>';
  }
  function senderTag(t) {
    return t === 1
      ? tag('用户', 'rgba(16,185,129,.12)', 'rgba(16,185,129,.35)', '#10B981')
      : tag('智能体', 'rgba(99,102,241,.12)', 'rgba(99,102,241,.35)', '#6366F1');
  }
  function fmtTime(t) {
    if (!t) return '—';
    var d = new Date(t);
    if (isNaN(d.getTime())) return String(t).replace('T', ' ').slice(0, 19);
    var p = function (n) { return n < 10 ? '0' + n : n; };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  var state = { agents: [], agentId: null };

  function render(sessions) {
    var tbody = document.querySelector('.ant-table-tbody');
    if (!tbody) return;
    var measure = tbody.querySelector('.ant-table-measure-row');
    var rows = sessions.map(function (s) {
      return '<tr data-row-key="' + esc(s.sessionId) + '" class="ant-table-row ant-table-row-level-0">' +
        '<td class="ant-table-cell ant-table-row-expand-icon-cell" style="text-align:center;"><span class="ant-table-row-expand-icon ant-table-row-expand-icon-collapsed"></span></td>' +
        td(ellipsis(fmtTime(s.createdAt), 'color:var(--ant-color-text-secondary);')) +
        td(ellipsis(s.title || s.sessionId)) +
        td(senderTag(2)) +
        td(s.chatCount != null ? tag(s.chatCount + ' 条', 'rgba(16,185,129,.12)', 'rgba(16,185,129,.35)', '#10B981') : '—') +
        td(ellipsis(s.title || '')) +
        td('<span style="color:var(--ant-color-text-quaternary);">—</span>') +
        td('<div style="display:flex;gap:8px;justify-content:center;">' +
          '<button data-qy-sess-view="' + esc(s.sessionId) + '" class="ant-btn css-dev-only ant-btn-link" style="color:#6366F1;">查看</button>' +
          '</div>', true) +
        '</tr>';
    }).join('');
    tbody.innerHTML = (measure ? measure.outerHTML : '') + rows;
    var ph = document.querySelector('.ant-table-placeholder');
    if (ph && rows) ph.remove();
  }

  function loadSessions() {
    if (!state.agentId) return;
    QXYuhe.proxied('GET', '/agent/' + encodeURIComponent(state.agentId) + '/sessions?page=1&limit=20')
      .then(function (data) {
        var list = (data && (data.list || data)) || [];
        if (!Array.isArray(list)) list = list.list || [];
        render(list);
      })
      .catch(function (e) { console.warn('[yuhe-chat] 会话加载失败', e); });
  }

  function openMsgModal(sessionId) {
    QXYuhe.proxied('GET', '/agent/' + encodeURIComponent(state.agentId) + '/chat-history/' + encodeURIComponent(sessionId))
      .then(function (msgs) {
        var list = (msgs && (msgs.list || msgs)) || [];
        if (!Array.isArray(list)) list = [];
        var bubbles = list.map(function (m) {
          var isUser = m.chatType === 1;
          return '<div style="display:flex;justify-content:' + (isUser ? 'flex-end' : 'flex-start') + ';margin:8px 0;">' +
            '<div style="max-width:75%;padding:10px 14px;border-radius:12px;background:' + (isUser ? 'rgba(99,102,241,.15)' : 'rgba(39,39,42,.9)') + ';border:1px solid ' + (isUser ? 'rgba(99,102,241,.35)' : 'rgba(63,63,70,.6)') + ';">' +
            '<div style="font-size:11px;color:var(--ant-color-text-tertiary);margin-bottom:4px;">' + (isUser ? '用户' : '智能体') + ' · ' + fmtTime(m.createdAt) + (m.audioId ? ' · 🎵' : '') + '</div>' +
            '<div style="font-size:13px;line-height:1.6;white-space:pre-wrap;">' + esc(m.content) + '</div>' +
            '</div></div>';
        }).join('');
        // 简易弹窗
        var old = document.getElementById('qy-msg-modal');
        if (old) old.remove();
        var mask = document.createElement('div');
        mask.id = 'qy-msg-modal';
        mask.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:9999;display:flex;align-items:center;justify-content:center;';
        mask.innerHTML = '<div style="width:min(680px,92vw);max-height:78vh;overflow:auto;background:#18181B;border:1px solid #3F3F46;border-radius:16px;padding:20px;">' +
          '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">' +
          '<h3 style="margin:0;font-size:16px;color:#FAFAFA;">会话记录 · ' + esc(sessionId.slice(0, 8)) + '</h3>' +
          '<button id="qy-msg-close" style="background:none;border:none;color:#A1A1AA;font-size:20px;cursor:pointer;">×</button></div>' +
          (bubbles || '<div style="color:#71717A;text-align:center;padding:30px;">该会话暂无消息</div>') +
          '</div>';
        document.body.appendChild(mask);
        mask.addEventListener('click', function (ev) {
          if (ev.target === mask || ev.target.id === 'qy-msg-close') mask.remove();
        });
      })
      .catch(function (e) { alert('加载消息失败：' + (e && e.message || e)); });
  }

  function load() {
    // 取第一个智能体的会话列表
    QXYuhe.proxied('GET', '/agent/list')
      .then(function (list) {
        state.agents = list || [];
        if (!state.agents.length) {
          render([]);
          return;
        }
        state.agentId = state.agents[0].id;
        loadSessions();
      })
      .catch(function (e) { console.warn('[yuhe-chat] 智能体加载失败', e); });
  }

  document.addEventListener('qx-yuhe-linked', load);
  QXYuhe.me().then(function (l) {
    if (!l.linked) { QXYuhe.showUnlinkedOverlay('memory-chat'); return; }
    load();
  }).catch(function () {});

  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest && ev.target.closest('[data-qy-sess-view]');
    if (!btn) return;
    openMsgModal(btn.getAttribute('data-qy-sess-view'));
  });
})();
