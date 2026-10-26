/* yuhe-voiceprint.js — 声纹页接管：voiceprint.html 接主站 /voiceClone（声音克隆记录）
 * 列映射：说话人标识=voiceId/名称=name/描述=modelName+languages/状态=trainStatus(0待训练 1训练中 2成功 3失败)
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
    return '<span class="ellipsis-text" style="' + (style || '') + 'max-width:220px;display:inline-block;vertical-align:bottom;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + esc(v) + '</span>';
  }
  function tag(text, bg, bd, c) {
    return '<span class="ant-tag ' + hashCls() + '" style="display:inline-flex;align-items:center;gap:6px;background:' + bg + ';border-color:' + bd + ';color:' + c + ';">' + esc(text) + '</span>';
  }
  function trainStatusTag(st) {
    var map = {
      0: { t: '待训练', bg: 'rgba(245,158,11,.12)', bd: 'rgba(245,158,11,.35)', c: '#F59E0B' },
      1: { t: '训练中', bg: 'rgba(99,102,241,.12)', bd: 'rgba(99,102,241,.35)', c: '#6366F1' },
      2: { t: '训练成功', bg: 'rgba(16,185,129,.12)', bd: 'rgba(16,185,129,.35)', c: '#10B981' },
      3: { t: '训练失败', bg: 'rgba(239,68,68,.12)', bd: 'rgba(239,68,68,.35)', c: '#EF4444' }
    };
    var s = map[st] || map[0];
    return tag(s.t, s.bg, s.bd, s.c);
  }
  function fmtTime(t) {
    if (!t) return '';
    var d = new Date(t);
    if (isNaN(d.getTime())) return String(t).slice(0, 10);
    var p = function (n) { return n < 10 ? '0' + n : n; };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
  }

  function render(list) {
    var tbody = document.querySelector('.ant-table-tbody');
    if (!tbody) return;
    var measure = tbody.querySelector('.ant-table-measure-row');
    var rows = list.map(function (v) {
      var desc = [v.modelName, v.languages].filter(Boolean).join(' · ') || '—';
      return '<tr data-row-key="' + esc(v.id) + '" class="ant-table-row ant-table-row-level-0">' +
        td(ellipsis(v.voiceId || v.id, 'font-weight:500;'), true) +
        td(ellipsis(v.name)) +
        td(ellipsis(desc, 'color:var(--ant-color-text-secondary);'), true) +
        td(trainStatusTag(v.trainStatus) + (v.trainStatus === 3 && v.trainError ? ' <span style="font-size:11px;color:#EF4444;">' + esc(v.trainError.slice(0, 20)) + '</span>' : ''), true) +
        td('<div style="display:flex;gap:8px;justify-content:center;">' +
          (v.hasVoice ? '<button data-qy-vc-play="' + esc(v.id) + '" class="ant-btn css-dev-only ant-btn-link" style="color:#6366F1;">▶ 试听</button>' : '') +
          '<button data-qy-vc-rename="' + esc(v.id) + '" data-qy-name="' + esc(v.name) + '" class="ant-btn css-dev-only ant-btn-link" style="color:#6366F1;">重命名</button>' +
          '</div>', true) +
        '</tr>';
    }).join('');
    tbody.innerHTML = (measure ? measure.outerHTML : '') + rows;
    var ph = document.querySelector('.ant-table-placeholder');
    if (ph && rows) ph.remove();
  }

  function load() {
    QXYuhe.proxied('GET', '/voiceClone?page=1&limit=50')
      .then(function (data) {
        var list = (data && (data.list || data)) || [];
        if (!Array.isArray(list)) list = list.list || [];
        render(list);
      })
      .catch(function (e) { console.warn('[yuhe-voiceprint] 加载失败', e); });
  }

  document.addEventListener('qx-yuhe-linked', load);
  QXYuhe.me().then(function (l) {
    if (!l.linked) { QXYuhe.showUnlinkedOverlay('voiceprint'); return; }
    load();
  }).catch(function () {});

  // 试听：两段式 POST /voiceClone/audio/{id} → uuid → window.open(/voiceClone/play/{uuid})
  document.addEventListener('click', function (ev) {
    var play = ev.target.closest && ev.target.closest('[data-qy-vc-play]');
    if (play) {
      var id = play.getAttribute('data-qy-vc-play');
      QXYuhe.proxied('POST', '/voiceClone/audio/' + encodeURIComponent(id))
        .then(function (uuid) {
          if (!uuid) { alert('音频不存在'); return; }
          // 播放走主站直链（浏览器新窗口）
          QXYuhe.playVoice(uuid);
        })
        .catch(function (e) { alert('获取音频失败：' + (e && e.message || e)); });
      return;
    }
    var rn = ev.target.closest && ev.target.closest('[data-qy-vc-rename]');
    if (rn) {
      var rid = rn.getAttribute('data-qy-vc-rename');
      var old = rn.getAttribute('data-qy-name') || '';
      var name = prompt('新的声音名称：', old);
      if (!name || name === old) return;
      QXYuhe.proxied('POST', '/voiceClone/updateName', { id: rid, name: name })
        .then(function () { load(); })
        .catch(function (e) { alert('重命名失败：' + (e && e.message || e)); });
    }
  });
})();
