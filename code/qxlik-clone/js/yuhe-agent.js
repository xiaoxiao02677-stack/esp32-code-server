/* yuhe-agent.js —— 智能体管理页主站接管（config-agent.html 专用，在 yuhe-api.js 之后加载）
 *
 * 已绑定主站时：
 *   1. 表格数据源 → 主站代理 GET /agent/list（agentId/agentName/platform/description...）
 *   2. 「编辑」弹窗 → 12 项配置编辑（与主站 Agents.vue 编辑弹窗同字段）：
 *      智能体名称、LLM 模型、TTS 模型、音色（随 TTS 引擎级联）、记忆模型、
 *      意图模型、ASR 模型、聊天记录策略、语速(-50~100)、唤醒词、唤醒阈值(0~100)、
 *      实时打断开关+阈值(0~100)、人设提示词
 *     保存 → PUT /agent/{id}（AgentUpdateDTO 契约）
 *   3. 「删除」→ DELETE /agent/{id}（主站有绑定设备时后端会拒绝）
 * 未绑定时保持本地 demo 表格不动。
 */
(function () {
  'use strict';

  if (location.pathname.indexOf('config-agent.html') < 0) return;
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

  function fmtDate(v) {
    if (!v) return '-';
    try {
      var d = new Date(v);
      if (isNaN(d.getTime())) return String(v);
      var p = function (n) { return (n < 10 ? '0' : '') + n; };
      return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
    } catch (e) { return '-'; }
  }

  /* ---------- 表头重映射（主站无 头像/默认/发布时间 语义） ---------- */
  var HEADS = ['智能体名称', '智能体ID', '绑定设备数', 'LLM模型', 'TTS模型', '音色', '记忆模型', '意图模型', 'ASR模型', '语速', '人设', '操作'];

  function rewriteHead() {
    var thead = document.querySelector('.ant-table-thead tr');
    if (!thead) return;
    thead.innerHTML = HEADS.map(function (h, i) {
      if (i === 0) return '<th class="ant-table-cell ant-table-cell-fix-left ant-table-cell-fix-left-last" style="text-align: center; position: sticky; left: 0px;"><!---->' + h + '<!----></th>';
      if (i === HEADS.length - 1) return '<th class="ant-table-cell ant-table-cell-fix-right ant-table-cell-fix-right-first" style="text-align: center; position: sticky; right: 0px;"><!---->' + h + '<!----></th>';
      return '<th class="ant-table-cell" style="text-align: center;"><!---->' + h + '<!----></th>';
    }).join('');
  }

  /* ---------- 数据加载 ---------- */
  var agentsCache = [];
  var detailCache = {};

  function loadList(cb, fb) {
    QXYuhe.proxied('GET', '/agent/list').then(function (list) {
      agentsCache = list || [];
      // 并发拉详情（设备数、模型名展示）
      return Promise.all(agentsCache.map(function (a) {
        return QXYuhe.proxied('GET', '/agent/' + encodeURIComponent(a.id)).then(function (d) {
          detailCache[a.id] = d;
        }).catch(function () {});
      }));
    }).then(function () {
      // 设备数
      return Promise.all(agentsCache.map(function (a) {
        return QXYuhe.proxied('GET', '/device/bind/' + encodeURIComponent(a.id))
          .then(function (devs) { a.__deviceCount = (devs || []).length; })
          .catch(function () { a.__deviceCount = 0; });
      }));
    }).then(function () { cb(agentsCache); })
      .catch(function (e) { if (fb) fb(e); });
  }

  function renderRows(agents) {
    var tbody = document.querySelector('.ant-table-tbody');
    if (!tbody) return;
    var rows = (agents || []).map(function (a) {
      var d = detailCache[a.id] || {};
      var ops = '<div class="ant-space ant-space-horizontal ant-space-align-center ' + hash() + '" style="gap: 8px;">' +
        '<div class="ant-space-item"><a data-qy-agent-edit="' + esc(a.id) + '">配置</a></div>' +
        '<div class="ant-space-item"><a class="delete-link" data-qy-agent-del="' + esc(a.id) + '">删除</a></div></div>';
      return '<tr data-row-key="' + esc(a.id) + '" class="ant-table-row ant-table-row-level-0">' +
        td(ell(a.agentName, 'font-weight:500;')) +
        td(ell(a.agentId, 'font-family:monospace;')) +
        td(String(a.__deviceCount || 0)) +
        td(ell(d.llmModelId, 'color:var(--ant-color-text-secondary);')) +
        td(ell(d.ttsModelId, 'color:var(--ant-color-text-secondary);')) +
        td(ell(d.ttsVoiceId, 'color:var(--ant-color-text-secondary);')) +
        td(ell(d.memModelId, 'color:var(--ant-color-text-secondary);')) +
        td(ell(d.intentModelId, 'color:var(--ant-color-text-secondary);')) +
        td(ell(d.asrModelId, 'color:var(--ant-color-text-secondary);')) +
        td(ell(d.ttsRate !== undefined && d.ttsRate !== null ? String(d.ttsRate) : '-')) +
        td(ell(d.systemPrompt ? '已配置' : '-', d.systemPrompt ? 'color:#10B981;' : 'color:var(--ant-color-text-quaternary);')) +
        tdFix(ops) +
        '</tr>';
    }).join('');
    var measure = tbody.querySelector('.ant-table-measure-row');
    tbody.innerHTML = (measure ? measure.outerHTML : '') + (rows || '<tr><td colspan="' + HEADS.length + '" style="text-align:center;padding:32px;color:var(--ant-color-text-quaternary);">暂无智能体</td></tr>');
    var pag = document.querySelector('.ant-table-pagination');
    if (pag) pag.style.display = 'none';
    QXCrud.setRows('config-agent', agents);
  }

  /* ---------- 模型选项 / 音色 ---------- */
  var modelOpts = { LLM: [], TTS: [], Memory: [], ASR: [], Intent: [] };

  function loadModelOpts() {
    var types = ['LLM', 'TTS', 'Memory', 'ASR', 'Intent'];
    return Promise.all(types.map(function (t) {
      return QXYuhe.proxied('GET', '/models/names?modelType=' + encodeURIComponent(t))
        .then(function (list) { modelOpts[t] = list || []; })
        .catch(function () { modelOpts[t] = []; });
    }));
  }

  function optHtml(kind, selected) {
    return (modelOpts[kind] || []).map(function (m) {
      return '<option value="' + esc(m.id) + '"' + (m.id === selected ? ' selected' : '') + '>' + esc(m.modelName || m.id) + '</option>';
    }).join('');
  }

  function voiceHtml(voices, selected) {
    return (voices || []).map(function (v) {
      return '<option value="' + esc(v.id) + '"' + (v.id === selected ? ' selected' : '') + '>' + esc(v.name || v.id) + '</option>';
    }).join('');
  }

  /* ---------- 12 项配置编辑弹窗 ---------- */
  function openEditModal(a) {
    var d = detailCache[a.id] || {};
    var voices = [];
    var bodyHtml =
      '<div style="display:flex;flex-direction:column;gap:6px;margin-bottom:12px;">' +
      '<label style="font-size:13px;font-weight:600;">智能体名称</label>' +
      '<input id="qy-ag-name" type="text" value="' + esc(d.agentName || '') + '" style="padding:9px 12px;border:1.5px solid var(--ant-color-border);border-radius:10px;font-size:14px;outline:none;"></div>' +

      '<div style="display:flex;flex-direction:column;gap:6px;margin-bottom:12px;">' +
      '<label style="font-size:13px;font-weight:600;">LLM 模型</label>' +
      '<select id="qy-ag-llm" style="padding:9px 12px;border:1.5px solid var(--ant-color-border);border-radius:10px;font-size:14px;outline:none;background:var(--ant-color-bg-container);color:var(--ant-color-text);">' + optHtml('LLM', d.llmModelId) + '</select></div>' +

      '<div style="display:flex;flex-direction:column;gap:6px;margin-bottom:12px;">' +
      '<label style="font-size:13px;font-weight:600;">TTS 模型</label>' +
      '<select id="qy-ag-tts" style="padding:9px 12px;border:1.5px solid var(--ant-color-border);border-radius:10px;font-size:14px;outline:none;background:var(--ant-color-bg-container);color:var(--ant-color-text);">' + optHtml('TTS', d.ttsModelId) + '</select></div>' +

      '<div style="display:flex;flex-direction:column;gap:6px;margin-bottom:12px;">' +
      '<label style="font-size:13px;font-weight:600;">音色（随 TTS 引擎切换）</label>' +
      '<select id="qy-ag-voice" style="padding:9px 12px;border:1.5px solid var(--ant-color-border);border-radius:10px;font-size:14px;outline:none;background:var(--ant-color-bg-container);color:var(--ant-color-text);">' + voiceHtml(voices, d.ttsVoiceId) + '</select></div>' +

      '<div style="display:flex;gap:12px;margin-bottom:12px;">' +
      '<div style="flex:1;display:flex;flex-direction:column;gap:6px;">' +
      '<label style="font-size:13px;font-weight:600;">记忆模型</label>' +
      '<select id="qy-ag-mem" style="padding:9px 12px;border:1.5px solid var(--ant-color-border);border-radius:10px;font-size:14px;outline:none;background:var(--ant-color-bg-container);color:var(--ant-color-text);">' + optHtml('Memory', d.memModelId) + '</select></div>' +
      '<div style="flex:1;display:flex;flex-direction:column;gap:6px;">' +
      '<label style="font-size:13px;font-weight:600;">意图模型</label>' +
      '<select id="qy-ag-intent" style="padding:9px 12px;border:1.5px solid var(--ant-color-border);border-radius:10px;font-size:14px;outline:none;background:var(--ant-color-bg-container);color:var(--ant-color-text);">' + optHtml('Intent', d.intentModelId) + '</select></div>' +
      '</div>' +

      '<div style="display:flex;gap:12px;margin-bottom:12px;">' +
      '<div style="flex:1;display:flex;flex-direction:column;gap:6px;">' +
      '<label style="font-size:13px;font-weight:600;">ASR 模型</label>' +
      '<select id="qy-ag-asr" style="padding:9px 12px;border:1.5px solid var(--ant-color-border);border-radius:10px;font-size:14px;outline:none;background:var(--ant-color-bg-container);color:var(--ant-color-text);">' + optHtml('ASR', d.asrModelId) + '</select></div>' +
      '<div style="flex:1;display:flex;flex-direction:column;gap:6px;">' +
      '<label style="font-size:13px;font-weight:600;">聊天记录策略</label>' +
      '<select id="qy-ag-hist" style="padding:9px 12px;border:1.5px solid var(--ant-color-border);border-radius:10px;font-size:14px;outline:none;background:var(--ant-color-bg-container);color:var(--ant-color-text);">' +
      '<option value="0"' + (d.chatHistoryConf === 0 ? ' selected' : '') + '>不记录</option>' +
      '<option value="1"' + (d.chatHistoryConf === 1 ? ' selected' : '') + '>仅记录文本</option>' +
      '<option value="2"' + ((d.chatHistoryConf === 2 || d.chatHistoryConf === null || d.chatHistoryConf === undefined) ? ' selected' : '') + '>记录文本和语音</option>' +
      '</select></div>' +
      '</div>' +

      '<div style="display:flex;gap:12px;margin-bottom:12px;">' +
      '<div style="flex:1;display:flex;flex-direction:column;gap:6px;">' +
      '<label style="font-size:13px;font-weight:600;">语速（-50 ~ 100）</label>' +
      '<input id="qy-ag-rate" type="number" min="-50" max="100" value="' + esc(d.ttsRate ?? 0) + '" style="padding:9px 12px;border:1.5px solid var(--ant-color-border);border-radius:10px;font-size:14px;outline:none;"></div>' +
      '<div style="flex:1;display:flex;flex-direction:column;gap:6px;">' +
      '<label style="font-size:13px;font-weight:600;">唤醒词（分号分隔）</label>' +
      '<input id="qy-ag-wake" type="text" value="' + esc(d.wakeWords || '') + '" placeholder="如：你好小智；小智小智" style="padding:9px 12px;border:1.5px solid var(--ant-color-border);border-radius:10px;font-size:14px;outline:none;"></div>' +
      '</div>' +

      '<div style="display:flex;gap:12px;margin-bottom:12px;">' +
      '<div style="flex:1;display:flex;flex-direction:column;gap:6px;">' +
      '<label style="font-size:13px;font-weight:600;">唤醒词阈值（0~100，0 最灵敏）</label>' +
      '<input id="qy-ag-wthr" type="number" min="0" max="100" value="' + esc(d.wakeWordThreshold ?? '') + '" placeholder="留空用设备默认" style="padding:9px 12px;border:1.5px solid var(--ant-color-border);border-radius:10px;font-size:14px;outline:none;"></div>' +
      '<div style="flex:1;display:flex;flex-direction:column;gap:6px;">' +
      '<label style="font-size:13px;font-weight:600;">实时打断灵敏度（0~100，0 最容易打断）</label>' +
      '<input id="qy-ag-ithr" type="number" min="0" max="100" value="' + esc(d.interruptThreshold ?? 15) + '" style="padding:9px 12px;border:1.5px solid var(--ant-color-border);border-radius:10px;font-size:14px;outline:none;"></div>' +
      '</div>' +

      '<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">' +
      '<label style="font-size:13px;font-weight:600;">实时打断</label>' +
      '<button type="button" id="qy-ag-int" class="ant-switch qx-switch ' + hash() + ((d.interruptEnabled === false) ? '' : ' ant-switch-checked') + '"><div class="ant-switch-handle"></div></button>' +
      '<span style="font-size:12px;color:var(--ant-color-text-secondary);">' + (d.interruptEnabled === false ? '已关闭' : '已开启') + '</span></div>' +

      '<div style="display:flex;flex-direction:column;gap:6px;">' +
      '<label style="font-size:13px;font-weight:600;">人设提示词</label>' +
      '<textarea id="qy-ag-prompt" rows="6" placeholder="例如：你是屿禾小助手，说话温柔耐心…" style="padding:9px 12px;border:1.5px solid var(--ant-color-border);border-radius:10px;font-size:13px;line-height:1.6;outline:none;resize:vertical;font-family:inherit;">' + esc(d.systemPrompt || '') + '</textarea></div>' +

      '<p id="qy-ag-err" style="display:none;margin:12px 0 0;padding:8px 12px;border-radius:8px;font-size:13px;background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.35);color:#EF4444;"></p>';

    var wrap = document.createElement('div');
    wrap.className = 'ant-modal-wrap';
    var modal = document.createElement('div');
    modal.className = 'ant-modal';
    modal.style.cssText = 'width:640px;margin:0 auto;';
    modal.innerHTML =
      '<div tabindex="0"><div class="ant-modal-content">' +
      '<button type="button" aria-label="Close" class="ant-modal-close"><span class="ant-modal-close-x">✕</span></button>' +
      '<div class="ant-modal-header"><div class="ant-modal-title">配置智能体 · ' + esc(a.agentName) + '</div></div>' +
      '<div class="ant-modal-body" style="max-height:66vh;overflow-y:auto;">' + bodyHtml + '</div>' +
      '<div class="ant-modal-footer"><div class="ant-modal-footer-buttons">' +
      '<button type="button" class="ant-btn qy-ag-close"><span>取 消</span></button>' +
      '<button type="button" class="ant-btn ant-btn-primary qy-ag-save"><span>保 存</span></button>' +
      '</div></div></div></div>';
    var mask = document.createElement('div');
    mask.className = 'ant-modal-mask';
    document.body.appendChild(mask);
    document.body.appendChild(wrap);

    function close() { wrap.remove(); mask.remove(); }
    function showErr(m) { modal.querySelector('#qy-ag-err').textContent = m; modal.querySelector('#qy-ag-err').style.display = 'block'; }

    modal.querySelector('.ant-modal-close').addEventListener('click', close);
    modal.querySelector('.qy-ag-close').addEventListener('click', close);
    mask.addEventListener('click', close);

    var interruptEl = modal.querySelector('#qy-ag-int');
    interruptEl.addEventListener('click', function () {
      interruptEl.classList.toggle('ant-switch-checked');
      var span = interruptEl.nextElementSibling;
      if (span) span.textContent = interruptEl.classList.contains('ant-switch-checked') ? '已开启' : '已关闭';
    });

    // 音色级联：TTS 引擎变化 → 重载音色
    var ttsSel = modal.querySelector('#qy-ag-tts');
    var voiceSel = modal.querySelector('#qy-ag-voice');
    function loadVoices(ttsModelId, keep) {
      if (!ttsModelId) { voiceSel.innerHTML = '<option value="">（请先选 TTS 模型）</option>'; return; }
      QXYuhe.proxied('GET', '/models/' + encodeURIComponent(ttsModelId) + '/voices')
        .then(function (list) {
          voiceSel.innerHTML = voiceHtml(list || [], keep || '');
          if (!list || !list.length) voiceSel.innerHTML = '<option value="">该引擎暂无音色</option>';
        })
        .catch(function () { voiceSel.innerHTML = '<option value="">音色加载失败</option>'; });
    }
    if (d.ttsModelId) loadVoices(d.ttsModelId, d.ttsVoiceId);
    ttsSel.addEventListener('change', function () { loadVoices(ttsSel.value, ''); });

    // 保存
    modal.querySelector('.qy-ag-save').addEventListener('click', function () {
      var rate = parseInt(modal.querySelector('#qy-ag-rate').value, 10);
      if (isNaN(rate) || rate < -50 || rate > 100) { showErr('语速需为 -50 ~ 100 的整数'); return; }
      var wthrRaw = modal.querySelector('#qy-ag-wthr').value.trim();
      var ithr = parseInt(modal.querySelector('#qy-ag-ithr').value, 10);
      if (isNaN(ithr) || ithr < 0 || ithr > 100) { showErr('实时打断灵敏度需为 0~100 的整数'); return; }

      var payload = {
        agentName: modal.querySelector('#qy-ag-name').value.trim() || a.agentName,
        llmModelId: modal.querySelector('#qy-ag-llm').value,
        ttsModelId: ttsSel.value,
        ttsVoiceId: voiceSel.value || null,
        memModelId: modal.querySelector('#qy-ag-mem').value,
        intentModelId: modal.querySelector('#qy-ag-intent').value,
        asrModelId: modal.querySelector('#qy-ag-asr').value,
        chatHistoryConf: parseInt(modal.querySelector('#qy-ag-hist').value, 10),
        ttsRate: rate,
        wakeWords: modal.querySelector('#qy-ag-wake').value.trim(),
        systemPrompt: modal.querySelector('#qy-ag-prompt').value,
        interruptEnabled: interruptEl.classList.contains('ant-switch-checked'),
        interruptThreshold: ithr
      };
      if (wthrRaw !== '') {
        var wthr = parseInt(wthrRaw, 10);
        if (isNaN(wthr) || wthr < 0 || wthr > 100) { showErr('唤醒词阈值需为 0~100 的整数'); return; }
        payload.wakeWordThreshold = wthr;
      }
      var btn = modal.querySelector('.qy-ag-save');
      btn.disabled = true;
      btn.textContent = '保存中...';
      QXYuhe.proxied('PUT', '/agent/' + encodeURIComponent(a.id), payload)
        .then(function () {
          QXCrud.toast('配置已保存', true);
          close();
          refresh();
        })
        .catch(function (err) {
          showErr((err && err.message) || '保存失败');
          btn.disabled = false;
          btn.textContent = '保 存';
        });
    });
  }

  /* ---------- 事件委托 ---------- */
  document.addEventListener('click', function (e) {
    var t = e.target.closest ? e.target : null;
    var editA = t && t.closest ? t.closest('a[data-qy-agent-edit]') : null;
    if (editA) {
      e.preventDefault();
      e.stopPropagation();
      var id = editA.getAttribute('data-qy-agent-edit');
      var a = null;
      (agentsCache || []).forEach(function (x) { if (x.id === id) a = x; });
      if (a) openEditModal(a);
      return;
    }
    var delA = t && t.closest ? t.closest('a[data-qy-agent-del]') : null;
    if (delA) {
      e.preventDefault();
      e.stopPropagation();
      var did = delA.getAttribute('data-qy-agent-del');
      if (!window.confirm('确认删除该智能体吗？删除后绑定设备将失去智能体配置。')) return;
      QXYuhe.proxied('DELETE', '/agent/' + encodeURIComponent(did))
        .then(function () { QXCrud.toast('智能体已删除', true); refresh(); })
        .catch(function (err) { QXCrud.toast((err && err.message) || '删除失败', false); });
    }
  });

  /* ---------- 接管 ---------- */
  var took = false;

  function refresh() {
    loadList(function (agents) {
      renderRows(agents);
    }, function (err) {
      QXCrud.toast((err && err.message) || '主站智能体加载失败', false);
    });
  }

  function takeover() {
    if (took) { refresh(); return; }
    took = true;
    rewriteHead();
    refresh();
    QXCrud.register('config-agent', refresh);
  }

  QXYuhe.me().then(function (l) {
    if (!l.linked) { QXYuhe.showUnlinkedOverlay('config-agent'); return; }
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () { setTimeout(takeover, 50); });
    } else {
      setTimeout(takeover, 50);
    }
  }).catch(function () {});

  document.addEventListener('qx-yuhe-linked', function () {
    QXYuhe.me(true).then(function (l) { if (l.linked) takeover(); });
  });
})();
