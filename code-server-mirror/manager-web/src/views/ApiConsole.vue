<template>
  <div class="cc-console">
    <!-- 未登录：居中登录卡片 -->
    <div v-if="!loggedIn" class="cc-login-wrap">
      <div class="kawaii-card cc-login-card">
        <img class="cc-login-logo" src="@/assets/kawaii/logo-kawaii.svg" alt="logo" />
        <h2 class="cc-login-title">功能控制台</h2>
        <p class="cc-login-sub">登录后可使用 15 个模块的全部功能</p>
        <div class="cc-login-form">
          <div class="cc-field">
            <label>用户名</label>
            <input v-model.trim="loginForm.username" class="cc-input" placeholder="用户名 / 手机号" @keyup.enter="doLogin" />
          </div>
          <div class="cc-field">
            <label>密码</label>
            <input v-model.trim="loginForm.password" type="password" class="cc-input" placeholder="密码" @keyup.enter="doLogin" />
          </div>
          <div class="cc-field cc-captcha-row">
            <label>验证码</label>
            <input v-model.trim="loginForm.captcha" class="cc-input" placeholder="验证码" @keyup.enter="doLogin" />
            <img v-if="captchaSrc" :src="captchaSrc" class="cc-captcha-img" title="点击刷新" @click="refreshCaptcha" />
          </div>
          <button class="kawaii-pill cc-login-btn" :disabled="loginLoading" @click="doLogin">
            {{ loginLoading ? '登录中…' : '登录' }}
          </button>
          <p v-if="loginError" class="cc-login-error">{{ loginError }}</p>
        </div>
      </div>
    </div>

    <!-- 已登录：顾客功能面板 -->
    <div v-else class="cc-shell">
      <!-- 左侧模块栏 -->
      <aside class="kawaii-card cc-sidebar">
        <div class="cc-sidebar-head">
          <img src="@/assets/kawaii/logo-kawaii.svg" class="cc-logo" alt="logo" @click="$router.push('/home')" />
          <div class="cc-sidebar-title">功能控制台</div>
          <div class="cc-sidebar-count">{{ totalApis }} 项功能</div>
        </div>
        <div class="cc-search-box">
          <input v-model.trim="filterKeyword" class="cc-input cc-input--sm" placeholder="搜索功能…" />
        </div>
        <nav class="cc-module-list">
          <button
            v-for="mod in filteredModules"
            :key="mod.key"
            class="cc-module-item"
            :class="{ 'is-active': mod.key === activeModule }"
            @click="selectModule(mod.key)"
          >
            <img :src="moduleIcon(mod.icon)" class="cc-module-icon" alt="" />
            <span class="cc-module-name">{{ mod.zh }}</span>
            <span class="cc-module-badge">{{ mod.count }}</span>
          </button>
        </nav>
        <button class="kawaii-pill cc-logout" @click="doLogout">退出</button>
      </aside>

      <!-- 右侧主内容：功能卡片墙 -->
      <main class="kawaii-card cc-main">
        <div class="cc-main-head">
          <div>
            <h2 class="cc-main-title">{{ activeMeta.zh }}</h2>
            <p class="cc-main-sub">共 {{ visibleApis.length }} 项功能 · 点击卡片即可使用</p>
          </div>
          <div class="cc-main-head-badges">
            <span class="cc-badge cc-badge--get">查询 {{ methodCount('GET') }}</span>
            <span class="cc-badge cc-badge--post">执行 {{ methodCount('POST') }}</span>
            <span class="cc-badge cc-badge--put">保存 {{ methodCount('PUT') }}</span>
            <span class="cc-badge cc-badge--delete">删除 {{ methodCount('DELETE') }}</span>
          </div>
        </div>

        <div v-if="visibleApis.length === 0" class="cc-empty">没有匹配的功能，换个关键词试试～</div>

        <!-- 功能卡片墙 -->
        <div class="cc-action-grid">
          <div
            v-for="(api, idx) in visibleApis"
            :key="activeModule + '-' + idx"
            class="kawaii-card cc-action-card"
            :class="{ 'is-danger': isDanger(api) }"
            @click="openAction(api)"
          >
            <div class="cc-action-top">
              <span class="cc-verb" :class="'cc-verb--' + api.h.toLowerCase()">{{ verbOf(api) }}</span>
              <span class="cc-action-title">{{ api.s }}</span>
            </div>
            <div class="cc-action-path">{{ api.h }} {{ api.p }}</div>
            <div class="cc-action-params">
              <span v-if="parseApi(api).pathParams.length" class="cc-chip">需填 {{ parseApi(api).pathParams.length }} 项</span>
              <span v-if="parseApi(api).hasBody" class="cc-chip cc-chip--body">填内容</span>
              <span v-if="isDanger(api)" class="cc-chip cc-chip--danger">谨慎操作</span>
              <span v-if="!parseApi(api).pathParams.length && !parseApi(api).hasBody" class="cc-chip cc-chip--free">一键执行</span>
            </div>
          </div>
        </div>
      </main>
    </div>

    <!-- 功能弹窗：自动表单 + 结果 -->
    <el-dialog
      :visible.sync="dialogVisible"
      :title="dialogTitle"
      width="720px"
      custom-class="cc-action-dialog"
      :close-on-click-modal="false"
    >
      <div v-if="currentApi" class="cc-form-area">
        <!-- 自动表单 -->
        <template v-if="!resultState">
          <p class="cc-form-hint">{{ currentApi.s }}（{{ verbOf(currentApi) }}）{{ isDanger(currentApi) ? ' · 该操作不可撤销，请确认后执行' : '' }}</p>

          <div v-if="formFields.length" class="cc-form-grid">
            <div v-for="f in formFields" :key="f.key" class="cc-form-item">
              <label class="cc-form-label">
                {{ f.label }}
                <span class="cc-form-where">{{ f.where === 'path' ? '必填' : '选填' }}</span>
              </label>
              <!-- 枚举型字段：下拉选择（modelType/status 等与原控制台一致的选项集） -->
              <select
                v-if="enumOptions(f.key).length"
                v-model.trim="form.values[f.key]"
                class="cc-input cc-select"
              >
                <option value="" disabled>请选择{{ f.label }}</option>
                <option v-for="opt in enumOptions(f.key)" :key="opt.v" :value="opt.v">{{ opt.t }}</option>
              </select>
              <input
                v-else
                v-model.trim="form.values[f.key]"
                class="cc-input"
                :placeholder="f.placeholder"
                :type="f.type"
              />
            </div>
          </div>
          <p v-else class="cc-form-hint cc-form-hint--free">该功能无需填写任何内容，直接点击下方按钮即可。</p>

          <div v-if="needBody" class="cc-form-body">
            <label class="cc-form-label">内容（JSON 格式）{{ bodyKeysHint ? ' · 字段参考：' + bodyKeysHint : '' }}</label>
            <textarea
              v-model="form.bodyText"
              class="cc-textarea"
              rows="6"
              placeholder='{"key": "value"}'
            ></textarea>
          </div>

          <div class="cc-form-actions">
            <button class="kawaii-pill cc-send-btn" :disabled="sending" @click="submitAction">
              {{ sending ? '执行中…' : (isDanger(currentApi) ? '确认执行' : verbOf(currentApi)) }}
            </button>
            <button class="kawaii-pill cc-cancel-btn" @click="dialogVisible = false">取消</button>
          </div>
        </template>

        <!-- 结果渲染 -->
        <template v-else>
          <div class="cc-result-head">
            <span class="cc-result-status" :class="resultState.ok ? 'is-ok' : 'is-err'">
              {{ resultState.ok ? '✔ 操作成功' : '✘ 操作失败' }}
            </span>
            <span class="cc-result-meta">HTTP {{ resultState.status }} · {{ resultState.ms }}ms</span>
            <button class="kawaii-pill cc-back-btn" @click="resultState = null">← 重新填写</button>
          </div>

          <!-- 表格型结果 -->
          <div v-if="resultState.mode === 'table'" class="cc-result-table-wrap">
            <p class="cc-result-note">共 {{ resultState.rows.length }} 条{{ resultState.total != null ? '（总计 ' + resultState.total + ' 条）' : '' }}</p>
            <el-table :data="resultState.rows" size="mini" max-height="360" border>
              <el-table-column
                v-for="col in resultState.columns"
                :key="col"
                :prop="col"
                :label="friendlyKey(col)"
                min-width="110"
                show-overflow-tooltip
              />
            </el-table>
          </div>

          <!-- 键值型结果 -->
          <div v-else-if="resultState.mode === 'kv'" class="cc-result-kv">
            <div v-for="kv in resultState.kvs" :key="kv.k" class="cc-kv-row">
              <span class="cc-kv-key">{{ friendlyKey(kv.k) }}</span>
              <span class="cc-kv-val">{{ kv.v }}</span>
            </div>
          </div>

          <!-- 音频/二进制 -->
          <div v-else-if="resultState.mode === 'audio'" class="cc-result-audio">
            <p>🎵 收到音频响应（{{ resultState.meta }}）</p>
            <audio v-if="resultState.audioUrl" :src="resultState.audioUrl" controls class="cc-audio-player"></audio>
          </div>

          <!-- 纯文本/JSON -->
          <pre v-else class="cc-result-pre">{{ resultState.text }}</pre>

          <!-- 业务错误信息 -->
          <p v-if="!resultState.ok && resultState.bizMsg" class="cc-result-errmsg">{{ resultState.bizMsg }}</p>
        </template>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import { getServiceUrl } from '@/apis/api';
import { sm2Encrypt, getUUID } from '@/utils';
import store from '@/store';
import catalogData from './ccCatalogData';

const API_CATALOG = catalogData;

/* ---------- 顾客友好层：动词 / 键名 ---------- */
const VERB_MAP = {
  GET: '查询',
  POST: '执行',
  PUT: '保存',
  DELETE: '删除'
};

const FIELD_LABELS = {
  agentId: '智能体 ID',
  sessionId: '会话 ID',
  id: 'ID',
  ids: 'ID 列表',
  page: '页码',
  limit: '每页数量',
  keyword: '搜索关键词',
  searchType: '搜索类型',
  name: '名称',
  modelName: '模型名称',
  modelType: '模型类型（VAD/ASR/LLM/VLLM/Intent/TTS/Memory/RAG）',
  provideCode: '供应器编码',
  modelId: '模型 ID',
  voice: '音色',
  voiceName: '音色名称',
  text: '试听文本',
  apiKey: '千问 API Key',
  device_id: '设备 ID',
  deviceId: '设备 ID',
  deviceCode: '设备编码',
  dictType: '字典类型',
  templateId: '模板 ID',
  snapshotId: '快照 ID',
  audioId: '音频 ID',
  phone: '手机号',
  uuid: '验证码 UUID',
  token: '恢复令牌',
  status: '状态',
  userIds: '用户 ID 列表'
};

const KEY_LABELS = {
  id: 'ID', name: '名称', agentId: '智能体ID', agentName: '智能体名称',
  createTime: '创建时间', updateDate: '更新时间', createDate: '创建时间',
  page: '页码', limit: '每页数', total: '总数', modelName: '模型名称',
  modelType: '模型类型', device_id: '设备ID', deviceCode: '设备编码',
  macAddress: 'MAC 地址', status: '状态', remark: '备注', type: '类型',
  voice: '音色', voiceName: '音色名称', isEnabled: '是否启用',
  isDefault: '是否默认', sort: '排序', title: '标题', sessionId: '会话ID',
  role: '角色', text: '文本', trainStatus: '训练状态', version: '版本', url: '链接'
};

function friendlyKey(key) {
  if (!key) return '';
  return KEY_LABELS[key] || FIELD_LABELS[key] || key;
}

export default {
  name: 'ApiConsole',
  data() {
    return {
      /* 登录态 */
      loginForm: { username: '', password: '', captcha: '' },
      captchaSrc: '',
      captchaUuid: '',
      loginLoading: false,
      loginError: '',
      /* 面板态 */
      filterKeyword: '',
      activeModule: 'agent',
      /* 弹窗态 */
      dialogVisible: false,
      currentApi: null,
      form: { values: {}, bodyText: '' },
      sending: false,
      resultState: null
    };
  },
  computed: {
    loggedIn() {
      const token = store.getters.getToken;
      return Boolean(token);
    },
    modules() {
      return Object.keys(API_CATALOG).map((key) => ({
        key,
        zh: API_CATALOG[key].zh,
        icon: API_CATALOG[key].icon,
        count: API_CATALOG[key].apis.length
      }));
    },
    filteredModules() {
      const kw = this.filterKeyword.toLowerCase();
      if (!kw) return this.modules;
      return this.modules.filter((m) => {
        if (m.zh.toLowerCase().includes(kw) || m.key.toLowerCase().includes(kw)) return true;
        return API_CATALOG[m.key].apis.some(
          (a) => a.p.toLowerCase().includes(kw) || a.s.includes(kw) || a.m.toLowerCase().includes(kw)
        );
      });
    },
    totalApis() {
      return this.modules.reduce((sum, m) => sum + m.count, 0);
    },
    activeMeta() {
      return API_CATALOG[this.activeModule] || { zh: '', apis: [] };
    },
    visibleApis() {
      const kw = this.filterKeyword.toLowerCase();
      const apis = this.activeMeta.apis || [];
      if (!kw) return apis;
      return apis.filter((a) => a.p.toLowerCase().includes(kw) || a.s.includes(kw) || a.m.toLowerCase().includes(kw));
    },
    /* 表单字段（自动生成） */
    formFields() {
      if (!this.currentApi) return [];
      const info = this.parseApi(this.currentApi);
      const fields = [];
      info.pathParams.forEach((k) => {
        fields.push({
          key: k,
          label: friendlyKey(k),
          where: 'path',
          placeholder: '请输入' + friendlyKey(k),
          type: 'text'
        });
      });
      info.queryParams.forEach((k) => {
        fields.push({
          key: k,
          label: friendlyKey(k),
          where: 'query',
          placeholder: this.queryDefault(k) !== undefined ? '' : '选填',
          type: k === 'page' || k === 'limit' ? 'number' : 'text'
        });
      });
      return fields;
    },
    needBody() {
      if (!this.currentApi) return false;
      return this.currentApi.h === 'POST' || this.currentApi.h === 'PUT';
    },
    bodyKeysHint() {
      if (!this.currentApi) return '';
      const m = /\(([^)]*)\)/.exec(this.currentApi.pa || '');
      if (!m) return '';
      return m[1]
        .split(',')
        .filter((s) => /body/.test(s))
        .map((s) => s.replace(/\(body\)|body/, '').trim())
        .filter(Boolean)
        .join('、');
    },
    dialogTitle() {
      if (!this.currentApi) return '功能';
      return (this.resultState ? '执行结果 · ' : '') + this.currentApi.s;
    }
  },
  mounted() {
    if (!this.loggedIn) this.refreshCaptcha();
  },
  methods: {
    /* ---------- 基础 ---------- */
    moduleIcon(icon) {
      try {
        return require(`@/assets/kawaii/icon-module-${icon}.svg`);
      } catch (e) {
        return require('@/assets/kawaii/logo-kawaii.svg');
      }
    },
    methodCount(m) {
      return this.visibleApis.filter((a) => a.h === m).length;
    },
    verbOf(api) {
      return VERB_MAP[api.h] || api.h;
    },
    isDanger(api) {
      if (api.h === 'DELETE') return true;
      return /delete|remove|unbind|batch/i.test(api.p);
    },
    parseApi(api) {
      const pathParams = [];
      let m;
      const re = /\$\{(\w+)\}/g;
      while ((m = re.exec(api.p)) !== null) {
        if (!pathParams.includes(m[1])) pathParams.push(m[1]);
      }
      const queryParams = [];
      const qm = /([A-Za-z_]\w*)\(query\)/g;
      while ((m = qm.exec(api.pa || '')) !== null) {
        if (!pathParams.includes(m[1]) && !queryParams.includes(m[1])) queryParams.push(m[1]);
      }
      const hasBody = /\(body\)/.test(api.pa || '') && api.h !== 'GET' && api.h !== 'DELETE';
      return { pathParams, queryParams, hasBody };
    },
    queryDefault(key) {
      if (key === 'page') return 1;
      if (key === 'limit') return 10;
      return undefined;
    },
    /* 枚举字段下拉选项（与原控制台一致的模型类型全集，LLM/视觉/音频一个不少） */
    enumOptions(key) {
      if (key === 'modelType') {
        return [
          { v: 'VAD', t: '语言活动检测（VAD）' },
          { v: 'ASR', t: '语音识别（ASR）' },
          { v: 'LLM', t: '大语言模型（LLM）' },
          { v: 'VLLM', t: '视觉大语言模型（VLLM）' },
          { v: 'Intent', t: '意图识别（Intent）' },
          { v: 'TTS', t: '语音合成（TTS）' },
          { v: 'Memory', t: '记忆（Memory）' },
          { v: 'RAG', t: '知识库（RAG）' }
        ];
      }
      if (key === 'status') {
        return [
          { v: '0', t: '禁用（0）' },
          { v: '1', t: '启用（1）' }
        ];
      }
      if (key === 'searchType') {
        return [
          { v: 'name', t: '按名称' },
          { v: 'mac', t: '按 MAC 地址' }
        ];
      }
      return [];
    },
    selectModule(key) {
      this.activeModule = key;
    },

    /* ---------- 打开功能 ---------- */
    openAction(api) {
      this.currentApi = api;
      this.resultState = null;
      this.sending = false;
      const values = {};
      const info = this.parseApi(api);
      info.queryParams.forEach((k) => {
        const d = this.queryDefault(k);
        if (d !== undefined) values[k] = d;
      });
      this.form = { values, bodyText: '' };
      this.dialogVisible = true;
    },

    /* ---------- 执行 ---------- */
    async submitAction() {
      const api = this.currentApi;
      if (!api) return;
      /* 危险操作二次确认 */
      if (this.isDanger(api)) {
        try {
          await this.$confirm(`「${api.s}」执行后不可撤销，确认继续吗？`, '谨慎操作', {
            confirmButtonText: '确认执行',
            cancelButtonText: '再想想',
            type: 'warning'
          });
        } catch (e) {
          return;
        }
      }
      /* 校验路径必填 */
      const info = this.parseApi(api);
      for (const k of info.pathParams) {
        const v = (this.form.values[k] || '').trim();
        if (!v) {
          this.$message.warning('请先填写「' + friendlyKey(k) + '」');
          return;
        }
      }
      this.sending = true;
      try {
        const rs = await this.sendRequest(api);
        this.resultState = rs;
      } catch (e) {
        this.resultState = {
          ok: false, mode: 'text', status: 0, ms: 0,
          text: '请求失败：' + (e && e.message ? e.message : e), bizMsg: ''
        };
      } finally {
        this.sending = false;
      }
    },
    async sendRequest(api) {
      const info = this.parseApi(api);
      let url = `${getServiceUrl()}${api.p}`;
      /* 路径替换 */
      info.pathParams.forEach((k) => {
        url = url.replace('${' + k + '}', encodeURIComponent(this.form.values[k] || ''));
      });
      /* query 拼接 */
      const qs = [];
      info.queryParams.forEach((k) => {
        const v = (this.form.values[k] === undefined ? '' : String(this.form.values[k])).trim();
        if (v !== '') qs.push(encodeURIComponent(k) + '=' + encodeURIComponent(v));
      });
      if (qs.length) url += (url.includes('?') ? '&' : '?') + qs.join('&');

      const token = store.getters.getToken;
      let tokenStr = token;
      try { tokenStr = JSON.parse(token).token; } catch (e) { /* 裸字符串 */ }
      const headers = {};
      if (tokenStr) headers.Authorization = 'Bearer ' + tokenStr;

      const opts = { method: api.h, headers };
      if (api.h !== 'GET' && api.h !== 'DELETE') {
        let bodyObj = null;
        if (this.form.bodyText && this.form.bodyText.trim()) {
          try {
            bodyObj = JSON.parse(this.form.bodyText);
          } catch (e) {
            this.$message.warning('内容不是合法的 JSON，请检查格式');
            throw new Error('JSON 格式错误');
          }
        }
        if (bodyObj !== null) {
          headers['Content-Type'] = 'application/json';
          opts.body = JSON.stringify(bodyObj);
        }
      }

      const t0 = performance.now();
      const resp = await fetch(url, opts);
      const ms = Math.round(performance.now() - t0);
      const ctype = resp.headers.get('Content-Type') || '';

      /* 音频/二进制：就地播放 */
      if (ctype.includes('audio') || ctype.includes('octet-stream')) {
        const blob = await resp.blob();
        return {
          ok: resp.ok, mode: 'audio', status: resp.status, ms,
          meta: `${ctype} · ${(blob.size / 1024).toFixed(1)} KB`,
          audioUrl: URL.createObjectURL(blob), bizMsg: ''
        };
      }

      const bodyText = await resp.text();
      let json = null;
      try { json = JSON.parse(bodyText); } catch (e) { /* 非 JSON */ }

      if (json === null) {
        return { ok: resp.ok, mode: 'text', status: resp.status, ms, text: bodyText.slice(0, 4000), bizMsg: '' };
      }

      const bizOk = json.code === 0 || json.code === 200 || json.code === undefined;
      const bizMsg = json.msg || json.message || '';
      const payload = json.data !== undefined ? json.data : json;

      /* 智能分类：表格 / 键值 / 文本 */
      let list = null;
      let total = null;
      if (Array.isArray(payload)) {
        list = payload;
      } else if (payload && typeof payload === 'object') {
        if (Array.isArray(payload.list)) { list = payload.list; total = payload.total; }
        else if (Array.isArray(payload.records)) { list = payload.records; total = payload.total; }
      }
      if (list && list.length && typeof list[0] === 'object') {
        const columns = [];
        list.slice(0, 5).forEach((row) => {
          Object.keys(row).forEach((k) => {
            if (!columns.includes(k) && columns.length < 8) columns.push(k);
          });
        });
        return { ok: bizOk, mode: 'table', status: resp.status, ms, rows: list, columns, total, bizMsg };
      }
      if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
        const kvs = Object.keys(payload)
          .filter((k) => typeof payload[k] !== 'object' || payload[k] === null)
          .slice(0, 24)
          .map((k) => ({ k, v: payload[k] === null ? '—' : String(payload[k]).slice(0, 200) }));
        if (kvs.length) return { ok: bizOk, mode: 'kv', status: resp.status, ms, kvs, bizMsg };
      }
      const text = typeof payload === 'string' ? payload : JSON.stringify(json, null, 2);
      return { ok: bizOk, mode: 'text', status: resp.status, ms, text: text.slice(0, 4000), bizMsg };
    },

    /* ---------- 登录（沿用既有逻辑） ---------- */
    refreshCaptcha() {
      this.captchaUuid = getUUID();
      this.captchaSrc = `${getServiceUrl()}/user/captcha?uuid=${this.captchaUuid}`;
    },
    async doLogin() {
      if (!this.loginForm.username || !this.loginForm.password) {
        this.loginError = '请输入用户名和密码';
        return;
      }
      this.loginLoading = true;
      this.loginError = '';
      try {
        let encryptedPassword;
        let pubKey = (store.getters.getPubConfig || {}).sm2PublicKey;
        if (!pubKey) {
          const cfg = await fetch(`${getServiceUrl()}/user/pub-config`).then((r) => r.json());
          if (cfg.code === 0 && cfg.data) {
            store.commit('setPubConfig', cfg.data);
            pubKey = cfg.data.sm2PublicKey;
          }
        }
        encryptedPassword = sm2Encrypt(pubKey, this.loginForm.password);
        const resp = await fetch(`${getServiceUrl()}/user/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username: this.loginForm.username,
            password: encryptedPassword,
            captcha: this.loginForm.captcha,
            uuid: this.captchaUuid
          })
        }).then((r) => r.json());
        if (resp.code === 0 && resp.data && resp.data.token) {
          store.commit('setToken', JSON.stringify(resp.data));
          store.commit('setUserInfo', resp.data.user || {});
          this.$message.success('登录成功');
        } else {
          this.loginError = resp.msg || '登录失败，请检查账号密码';
          this.refreshCaptcha();
        }
      } catch (e) {
        this.loginError = '网络异常，请稍后再试';
        this.refreshCaptcha();
      } finally {
        this.loginLoading = false;
      }
    },
    doLogout() {
      store.dispatch('logout');
    }
  }
};
</script>

<style lang="scss" scoped>
@import '@/styles/kawaii/tokens.scss';

.cc-console {
  min-height: 100%;
}

/* ---------- 登录卡片 ---------- */
.cc-login-wrap {
  min-height: 70vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
}
.cc-login-card {
  width: 100%;
  max-width: 380px;
  text-align: center;
}
.cc-login-logo {
  width: 72px;
  height: 72px;
  margin-bottom: 8px;
}
.cc-login-title {
  font-size: 1.4rem;
  font-weight:600;
  color: var(--kawaii-text, #4b3b44);
  margin: 0 0 4px;
}
.cc-login-sub {
  font-size: 0.85rem;
  color: var(--kawaii-text-soft, #a08e96);
  margin: 0 0 20px;
}
/* 通用输入框（粉彩描边 + 聚焦光圈） */
.cc-input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--kawaii-border, #ffd9e3);
  border-radius: 10px;
  padding: 9px 12px;
  font-size: 0.88rem;
  color: var(--kawaii-text, #4b3b44);
  background: var(--kawaii-surface, #fff);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
  &:focus {
    outline: none;
    border-color: var(--kawaii-primary, #ff8fab);
    box-shadow: 0 0 0 3px rgba(255, 143, 171, 0.15);
  }
  &.cc-input--sm { padding: 7px 10px; font-size: 0.82rem; }
}
.cc-field {
  text-align: left;
  margin-bottom: 14px;
  label {
    display: block;
    font-size: 0.85rem;
    color: var(--kawaii-text, #4b3b44);
    margin-bottom: 6px;
    font-weight: 500;
  }
}
.cc-captcha-row {
  display: flex;
  align-items: center;
  gap: 10px;
  input { flex: 1; }
}
.cc-captcha-img {
  height: 38px;
  border-radius: 8px;
  cursor: pointer;
  border: 1px solid var(--kawaii-border, #ffd9e3);
}
.cc-login-btn {
  width: 100%;
  margin-top: 6px;
  background: var(--kawaii-primary, #ff8fab);
  color: #fff;
  border: none;
  cursor: pointer;
  &:disabled { opacity: 0.6; cursor: wait; }
}
.cc-login-error {
  color: #e6657f;
  font-size: 0.82rem;
  margin: 10px 0 0;
}

/* ---------- 双栏外壳 ---------- */
.cc-shell {
  display: flex;
  gap: 18px;
  min-height: calc(100vh - 120px);
  text-align: left;
}
.cc-sidebar {
  flex: 0 0 240px;
  display: flex;
  flex-direction: column;
  padding: 18px 14px;
  position: sticky;
  top: 16px;
  height: calc(100vh - 110px);
}
.cc-sidebar-head {
  text-align: center;
  padding-bottom: 12px;
  border-bottom: 1px dashed var(--kawaii-border, #ffd9e3);
}
.cc-logo {
  width: 44px;
  height: 44px;
  cursor: pointer;
}
.cc-sidebar-title {
  font-weight: 600;
  color: var(--kawaii-text, #4b3b44);
  margin-top: 4px;
}
.cc-sidebar-count {
  font-size: 0.75rem;
  color: var(--kawaii-text-soft, #a08e96);
}
.cc-search-box {
  margin: 12px 4px;
}
.cc-module-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cc-module-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: none;
  background: transparent;
  border-radius: 10px;
  cursor: pointer;
  color: var(--kawaii-text, #4b3b44);
  transition: all 0.18s ease;
  text-align: left;
  &:hover { background: var(--kawaii-surface-2, #fff0f5); }
  &.is-active {
    background: var(--kawaii-primary-soft, #ffe1ea);
    font-weight: 600;
  }
}
.cc-module-icon { width: 20px; height: 20px; flex-shrink: 0; }
.cc-module-name { flex: 1; font-size: 0.88rem; }
.cc-module-badge {
  font-size: 0.72rem;
  background: var(--kawaii-surface-2, #fff0f5);
  border-radius: 9999px;
  padding: 1px 8px;
  color: var(--kawaii-text-soft, #a08e96);
}
.cc-logout {
  margin-top: 10px;
  background: var(--kawaii-surface-2, #fff0f5);
  color: var(--kawaii-text, #4b3b44);
  border: none;
  cursor: pointer;
}

/* ---------- 主区 ---------- */
.cc-main {
  flex: 1;
  min-width: 0;
  padding: 20px 22px;
}
.cc-main-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
}
.cc-main-title {
  margin: 0;
  font-size: 1.15rem;
  color: var(--kawaii-text, #4b3b44);
}
.cc-main-sub {
  margin: 2px 0 0;
  font-size: 0.8rem;
  color: var(--kawaii-text-soft, #a08e96);
}
.cc-main-head-badges { display: flex; gap: 6px; flex-wrap: wrap; }
.cc-badge {
  font-size: 0.72rem;
  padding: 2px 10px;
  border-radius: 9999px;
  font-weight: 500;
}
.cc-badge--get { background: #e8f7ef; color: #3d9970; }
.cc-badge--post { background: #fff3e0; color: #d98a2b; }
.cc-badge--put { background: #e8f0fe; color: #5a7dc4; }
.cc-badge--delete { background: #fdeaea; color: #d46a6a; }

.cc-empty {
  text-align: center;
  color: var(--kawaii-text-soft, #a08e96);
  padding: 60px 0;
}

/* ---------- 功能卡片墙 ---------- */
.cc-action-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
}
.cc-action-card {
  padding: 16px 18px;
  cursor: pointer;
  border: 1px solid var(--kawaii-border, #ffd9e3);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  &:hover {
    transform: translateY(-3px);
    box-shadow: 0 6px 20px rgba(255, 143, 171, 0.25);
  }
  &.is-danger { border-color: #f5c6c6; }
}
.cc-action-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.cc-verb {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 9999px;
  flex-shrink: 0;
}
.cc-verb--get { background: #e8f7ef; color: #3d9970; }
.cc-verb--post { background: #fff3e0; color: #d98a2b; }
.cc-verb--put { background: #e8f0fe; color: #5a7dc4; }
.cc-verb--delete { background: #fdeaea; color: #d46a6a; }
.cc-action-title {
  font-weight: 600;
  font-size: 0.92rem;
  color: var(--kawaii-text, #4b3b44);
}
.cc-action-path {
  font-size: 0.72rem;
  color: var(--kawaii-text-soft, #a08e96);
  font-family: monospace;
  margin-bottom: 10px;
  word-break: break-all;
}
.cc-action-params { display: flex; gap: 6px; flex-wrap: wrap; }
.cc-chip {
  font-size: 0.7rem;
  padding: 1px 8px;
  border-radius: 9999px;
  background: var(--kawaii-surface-2, #fff0f5);
  color: var(--kawaii-text-soft, #a08e96);
}
.cc-chip--body { background: #fff3e0; color: #d98a2b; }
.cc-chip--danger { background: #fdeaea; color: #d46a6a; }
.cc-chip--free { background: #e8f7ef; color: #3d9970; }

/* ---------- 弹窗表单 ---------- */
.cc-form-hint {
  font-size: 0.85rem;
  color: var(--kawaii-text-soft, #a08e96);
  margin: 0 0 14px;
  &--free { padding: 20px 0; text-align: center; }
}
.cc-form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}
.cc-form-item { text-align: left; }
.cc-form-label {
  display: block;
  font-size: 0.82rem;
  font-weight: 500;
  color: var(--kawaii-text, #4b3b44);
  margin-bottom: 5px;
}
.cc-form-where {
  font-size: 0.7rem;
  color: var(--kawaii-text-soft, #a08e96);
  font-weight: 400;
  margin-left: 4px;
}
.cc-textarea {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--kawaii-border, #ffd9e3);
  border-radius: 10px;
  padding: 10px 12px;
  font-family: monospace;
  font-size: 0.82rem;
  background: var(--kawaii-surface, #fff);
  resize: vertical;
  &:focus { outline: none; border-color: var(--kawaii-primary, #ff8fab); }
}
.cc-form-body { margin-bottom: 14px; text-align: left; }
.cc-form-actions { display: flex; gap: 10px; margin-top: 6px; }
.cc-send-btn {
  background: var(--kawaii-primary, #ff8fab);
  color: #fff;
  border: none;
  cursor: pointer;
  &:disabled { opacity: 0.6; cursor: wait; }
}
.cc-cancel-btn {
  background: var(--kawaii-surface-2, #fff0f5);
  color: var(--kawaii-text, #4b3b44);
  border: none;
  cursor: pointer;
}

/* ---------- 结果渲染 ---------- */
.cc-result-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.cc-result-status {
  font-weight: 600;
  &.is-ok { color: #3d9970; }
  &.is-err { color: #d46a6a; }
}
.cc-result-meta {
  font-size: 0.78rem;
  color: var(--kawaii-text-soft, #a08e96);
}
.cc-back-btn {
  margin-left: auto;
  background: var(--kawaii-surface-2, #fff0f5);
  color: var(--kawaii-text, #4b3b44);
  border: none;
  cursor: pointer;
  font-size: 0.8rem;
  padding: 4px 14px;
}
.cc-result-note {
  font-size: 0.8rem;
  color: var(--kawaii-text-soft, #a08e96);
  margin: 0 0 8px;
  text-align: left;
}
.cc-result-kv {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 8px;
}
.cc-kv-row {
  display: flex;
  gap: 10px;
  padding: 8px 12px;
  background: var(--kawaii-surface-2, #fff0f5);
  border-radius: 10px;
  font-size: 0.82rem;
}
.cc-kv-key {
  color: var(--kawaii-text-soft, #a08e96);
  flex-shrink: 0;
  min-width: 90px;
}
.cc-kv-val {
  color: var(--kawaii-text, #4b3b44);
  word-break: break-all;
}
.cc-result-pre {
  background: var(--kawaii-surface-2, #fff0f5);
  border-radius: 10px;
  padding: 14px;
  font-size: 0.8rem;
  max-height: 360px;
  overflow: auto;
  text-align: left;
  white-space: pre-wrap;
  word-break: break-all;
}
.cc-result-audio {
  text-align: center;
  padding: 20px 0;
  p { color: var(--kawaii-text, #4b3b44); margin: 0 0 12px; }
}
.cc-audio-player { width: 100%; }
.cc-result-errmsg {
  color: #d46a6a;
  font-size: 0.85rem;
  background: #fdeaea;
  border-radius: 10px;
  padding: 10px 14px;
  text-align: left;
  margin-top: 10px;
}

/* ---------- 响应式 ---------- */
@media (max-width: 900px) {
  .cc-shell { flex-direction: column; }
  .cc-sidebar {
    position: static;
    height: auto;
    flex-basis: auto;
  }
  .cc-module-list { flex-direction: row; flex-wrap: wrap; }
}

/* ---------- 果冻动效与 reduced-motion 双保险 ---------- */
@media (prefers-reduced-motion: reduce) {
  .cc-module-item,
  .cc-action-card {
    transition: none;
    &:hover { transform: none; box-shadow: none; }
  }
}
</style>
