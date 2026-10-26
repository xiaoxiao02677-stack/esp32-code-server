/* yuhe-memory.js — 记忆页接管：memory-long.html（长期记忆）接主站 /memory/facts 真数据
 * 依赖：yuhe-api.js（QXYuhe）、demo-data.js（工具函数在本文件内自备，避免依赖加载顺序） */
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
    return '<span class="ellipsis-text" style="' + (style || '') + '">' + esc(v) + '</span>';
  }
  function tag(text, bg, bd, c) {
    return '<span class="ant-tag ' + hashCls() + '" style="display:inline-flex;align-items:center;gap:6px;background:' + bg + ';border-color:' + bd + ';color:' + c + ';">' + esc(text) + '</span>';
  }
  function trustTag(t) {
    if (t === null || t === undefined) return '<span style="color:var(--ant-color-text-quaternary);">—</span>';
    var v = Number(t);
    if (v >= 0.8) return tag('高', 'rgba(16,185,129,.12)', 'rgba(16,185,129,.35)', '#10B981');
    if (v >= 0.5) return tag('中', 'rgba(99,102,241,.12)', 'rgba(99,102,241,.35)', '#6366F1');
    return tag('低', 'rgba(113,113,122,.12)', 'rgba(113,113,122,.35)', '#A1A1AA');
  }
  function opsCell(factId, agentId) {
    return td('<div style="display:flex;gap:8px;justify-content:center;">' +
      '<button data-qy-fact-view="' + esc(factId) + '" data-qy-agent="' + esc(agentId || '') + '" class="ant-btn css-dev-only ant-btn-link" style="color:#6366F1;">查看</button>' +
      '<button data-qy-fact-del="' + esc(factId) + '" data-qy-agent="' + esc(agentId || '') + '" class="ant-btn css-dev-only ant-btn-link" style="color:#EF4444;">删除</button>' +
      '</div>', true);
  }

  function render(facts) {
    var tbody = document.querySelector('.ant-table-tbody');
    if (!tbody) return;
    var measure = tbody.querySelector('.ant-table-measure-row');
    var rows = facts.map(function (f) {
      return '<tr data-row-key="' + esc(f.factId) + '" class="ant-table-row ant-table-row-level-0">' +
        td(ellipsis(f.createdAt, 'color:var(--ant-color-text-secondary);')) +
        td(ellipsis(f.content)) +
        td(ellipsis(f.category || '对话提炼', 'color:var(--ant-color-text-secondary);')) +
        td(trustTag(f.trustScore)) +
        opsCell(f.factId, f.agentId) +
        '</tr>';
    }).join('');
    tbody.innerHTML = (measure ? measure.outerHTML : '') + rows;
    var ph = document.querySelector('.ant-table-placeholder');
    if (ph && rows) ph.remove();
  }

  function load() {
    // 先取智能体列表，逐个查询其记忆条目后合并展示
    QXYuhe.proxied('GET', '/agent/list')
      .then(function (agents) {
        var list = agents || [];
        if (!list.length) { render([]); return; }
        // 逐智能体并发拉取记忆，按创建时间倒序合并
        return Promise.all(list.map(function (a) {
          return QXYuhe.proxied('GET', '/memory/facts?agent_id=' + encodeURIComponent(a.id) + '&page=1&limit=50')
            .then(function (data) {
              var facts = (data && (data.list || data)) || [];
              if (!Array.isArray(facts)) facts = [];
              return facts;
            })
            .catch(function () { return []; });
        })).then(function (all) {
          var merged = [];
          all.forEach(function (facts) { merged = merged.concat(facts); });
          merged.sort(function (x, y) { return String(y.createdAt || '').localeCompare(String(x.createdAt || '')); });
          render(merged);
        });
      })
      .catch(function (e) {
        console.warn('[yuhe-memory] 加载失败', e);
      });
  }

  // 绑定状态变化时刷新（首次进入 + 重新绑定后）
  document.addEventListener('qx-yuhe-linked', load);
  QXYuhe.me().then(function (l) {
    if (!l.linked) { QXYuhe.showUnlinkedOverlay('memory-long'); return; }
    load();
  }).catch(function () {});

  // 删除委托
  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest && ev.target.closest('[data-qy-fact-del]');
    if (!btn) return;
    var id = btn.getAttribute('data-qy-fact-del');
    var agentId = btn.getAttribute('data-qy-agent');
    if (!agentId) { alert('缺少智能体信息，无法删除'); return; }
    if (!confirm('确认删除该条记忆？')) return;
    QXYuhe.proxied('DELETE', '/memory/facts/' + encodeURIComponent(id) + '?agent_id=' + encodeURIComponent(agentId))
      .then(function () { load(); })
      .catch(function (e) { alert('删除失败：' + (e && e.message || e)); });
  });
})();
