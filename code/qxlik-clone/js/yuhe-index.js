/* yuhe-index.js —— 首页主站接管（index.html 专用）
 *
 * 已绑定主站时：统计卡片 + 最近设备表 → 主站真实数据
 *   - GET /agent/list → 智能体数；逐个 GET /device/bind/{id} → 设备总数/最近连接
 *   - 统计三卡：聊天总数（会话数近似）/ 设备总数 / 智能体总数
 * 未绑定时保持本地 demo 数据。
 */
(function () {
  'use strict';

  if (location.pathname.indexOf('index.html') < 0) return;
  if (!window.QXYuhe) return;

  var DARK_HASH = 'css-97cec0';
  var LIGHT_HASH = 'css-1p8u2sp';
  function hash() {
    var mode = localStorage.getItem('theme-mode') || 'auto';
    if (mode === 'auto') mode = (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
    return mode === 'light' ? LIGHT_HASH : DARK_HASH;
  }
  function esc(s) {
    if (s === null || s === undefined) return '-';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function td(html) { return '<td class="ant-table-cell" style="text-align: center;"><!---->' + html + '<!----></td>'; }
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
    var alive = recentTs && (Date.now() / 1000 - Number(recentTs) < 1800);
    return alive
      ? '<span class="ant-tag ' + hash() + '" style="display:inline-flex;align-items:center;gap:6px;background:rgba(16,185,129,.12);border-color:rgba(16,185,129,.35);color:#10B981;"><span style="width:6px;height:6px;border-radius:50%;background:#10B981;"></span>在线</span>'
      : '<span class="ant-tag ' + hash() + '" style="display:inline-flex;align-items:center;gap:6px;background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.35);color:#EF4444;"><span style="width:6px;height:6px;border-radius:50%;background:#EF4444;"></span>离线</span>';
  }

  function takeover() {
    QXYuhe.proxied('GET', '/agent/list').then(function (agents) {
      agents = agents || [];
      return Promise.all(agents.map(function (a) {
        return QXYuhe.proxied('GET', '/device/bind/' + encodeURIComponent(a.id))
          .then(function (devs) {
            return (devs || []).map(function (d) {
              d.__agentName = a.agentName;
              return d;
            });
          }).catch(function () { return []; });
      })).then(function (groups) {
        var rows = [];
        groups.forEach(function (g) { rows = rows.concat(g); });
        rows.sort(function (x, y) { return (y.lastConnectedAtTimestamp || 0) - (x.lastConnectedAtTimestamp || 0); });

        // 统计卡片
        var values = document.querySelectorAll('.ant-statistic-content-value-int');
        if (values.length >= 3) {
          values[0].textContent = String(rows.length);            // 近似聊天总数 → 设备活动数
          values[1].textContent = String(rows.length);            // 设备总数
          values[2].textContent = String(agents.length);          // 智能体总数
        }

        // 最近设备表（前 6）
        var tbody = document.querySelector('.ant-table-tbody');
        if (tbody) {
          var top = rows.slice(0, 6).map(function (d) {
            return '<tr data-row-key="' + esc(d.id) + '" class="ant-table-row ant-table-row-level-0">' +
              td(ell(d.alias || d.board, 'font-weight:500;')) +
              td(ell(d.__agentName)) +
              td(onlineTag(d.lastConnectedAtTimestamp)) +
              td(ell(fmtTs(d.lastConnectedAtTimestamp), 'color:var(--ant-color-text-secondary);')) +
              '</tr>';
          }).join('');
          var measure = tbody.querySelector('.ant-table-measure-row');
          tbody.innerHTML = (measure ? measure.outerHTML : '') + (top || '<tr><td colspan="4" style="text-align:center;padding:32px;color:var(--ant-color-text-quaternary);">暂无设备</td></tr>');
        }
      });
    }).catch(function () { /* 未绑定或失败：保持 demo */ });
  }

  QXYuhe.me().then(function (l) {
    if (!l.linked) {
      QXYuhe.showUnlinkedOverlay('index');
      // 统计卡置为 — ，避免显示 demo 数值
      document.querySelectorAll('.ant-statistic-content-value-int').forEach(function (el) {
        el.textContent = '—';
      });
      return;
    }
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () { setTimeout(takeover, 50); });
    } else {
      setTimeout(takeover, 50);
    }
  }).catch(function () {});

  document.addEventListener('qx-yuhe-linked', function () { takeover(); });
})();
