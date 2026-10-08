// ============ 原控制台 API 适配层（契约零修改，差异前端消化 C4） ============
// 基线: cc-console/contract/openapi.json (173 接口)
// 反代: /xiaozhi/ -> manager-api:8002 (同源，无 CORS)
// 鉴权: Bearer token (localStorage)，登录密码 SM2 加密 —— 与原控制台完全一致 (C3)

import { sm2 } from 'sm-crypto'

const API_BASE = '/xiaozhi'
const TOKEN_KEY = 'v2_token'

export function getToken() {
  try { return JSON.parse(localStorage.getItem(TOKEN_KEY) || 'null')?.token || localStorage.getItem(TOKEN_KEY) || '' } catch { return '' }
}
export function setToken(raw) { localStorage.setItem(TOKEN_KEY, raw) }
export function clearToken() { localStorage.removeItem(TOKEN_KEY) }

function buildQuery(params) {
  if (!params) return ''
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') q.append(k, v)
  }
  const s = q.toString()
  return s ? '?' + s : ''
}

async function request(method, path, { body, params, formData, raw } = {}) {
  const url = API_BASE + path + buildQuery(params)
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = 'Bearer ' + token
  const init = { method, headers }
  if (formData) {
    init.body = formData
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(body)
  }
  let resp
  try {
    resp = await fetch(url, init)
  } catch {
    throw { code: -1, msg: '网络异常，请检查连接' }
  }
  if (raw) return resp
  let data
  try { data = await resp.json() }
  catch { throw { code: resp.status, msg: `响应解析失败 (HTTP ${resp.status})` } }
  // Java 业务约定: code=0 才是成功（401 由具体值判定，HTTP 层仍可能 200）
  if (data.code === 401) {
    // 竞态防护：登录成功瞬间，旧页面的在途请求可能带过期 token 返回 401——
    // 若刚写入新 token（10s 内），不清理不跳转，让新 token 生效
    let freshToken = false
    try {
      const saved = JSON.parse(localStorage.getItem(TOKEN_KEY) || 'null')
      freshToken = !!(saved && saved.token && saved.expire && Date.now() < saved.loginAt + 10000)
    } catch { /* ignore */ }
    if (!freshToken) {
      clearToken()
      if (!location.hash.startsWith('#/login')) location.hash = '#/login'
      throw { code: 401, msg: '登录已过期，请重新登录' }
    }
    throw { code: 401, msg: '登录已过期（在途请求）' }
  }
  if (data.code !== 0) throw { code: data.code, msg: data.msg || '操作失败' }
  return data
}

export const api = {
  get: (p, params) => request('GET', p, { params }),
  post: (p, body) => request('POST', p, { body }),
  put: (p, body) => request('PUT', p, { body }),
  del: (p) => request('DELETE', p),
  upload: (p, formData) => request('POST', p, { formData })
}

// ---------- 登录 / 鉴权（与原控制台 App.vue:2465-2515 逐行对齐） ----------
export const authApi = {
  captchaUrl: (uuid) => `${API_BASE}/user/captcha?uuid=${encodeURIComponent(uuid)}`,
  async pubConfig() {
    const res = await api.get('/user/pub-config')
    return res.data // { sm2PublicKey, ... }
  },
  /** 原契约: password = '04' + sm2.doEncrypt(captcha + password, pubKey, 1) */
  async login(username, password, captcha, captchaId) {
    let pubKey = null
    try { pubKey = (await this.pubConfig()).sm2PublicKey } catch { /* fallthrough */ }
    if (!pubKey) throw { code: -1, msg: '无法获取加密公钥' }
    const encrypted = '04' + sm2.doEncrypt(captcha + password, pubKey, 1)
    const res = await api.post('/user/login', {
      username, password: encrypted, captchaId
    })
    setToken(JSON.stringify({ ...res.data, loginAt: Date.now() }))  // loginAt: 401 竞态防护
    return res.data
  },
  userInfo: () => api.get('/user/info')
}

// ---------- 顾客端 ----------
export const customerApi = {
  agentList: () => api.get('/agent/list'),
  agentDetail: (id) => api.get(`/agent/${id}`),
  createAgent: (body) => api.post('/agent', body),
  deleteAgent: (id) => api.del(`/agent/${id}`),
  boundDevices: (agentId) => api.get(`/device/bind/${agentId}`),
  voiceClonePage: (params) => api.get('/voiceClone', params),
  voiceResourcePage: (params) => api.get('/voiceResource', params),
  ttsVoicePage: (params) => api.get('/ttsVoice', params)
}

// ---------- 管理端（全量迁移自 cc-console，契约基线 openapi.json 173 接口） ----------
export const adminApi = {
  // ===== 智能体 =====
  agentList: () => api.get('/agent/list'),
  agentDetail: (id) => api.get(`/agent/${id}`),
  createAgent: (body) => api.post('/agent', body),
  updateAgent: (id, body) => api.put(`/agent/${id}`, body),
  deleteAgent: (id) => api.del(`/agent/${id}`),
  boundDevices: (agentId) => api.post(`/device/bind/${agentId}`, {}),
  bindDeviceByCode: (agentId, code) => api.post(`/device/bind/${agentId}/${encodeURIComponent(code)}`),
  agentSessions: (agentId, params) => api.get(`/agent/${agentId}/sessions`, params || { page: 1, limit: 10 }),
  // MCP 接入点
  mcpAddress: (agentId) => api.get(`/agent/mcp/address/${agentId}`),
  mcpTools: (agentId) => api.get(`/agent/mcp/tools/${agentId}`),
  mcpTest: (agentId) => api.get(`/agent/mcp/test/${agentId}`),

  // ===== 聊天记录 =====
  chatHistory: (agentId, sessionId) => api.get(`/agent/${agentId}/chat-history/${sessionId}`),
  chatHistoryAudio: (audioId) => api.post(`/agent/audio/${audioId}`),
  deleteChatSession: (agentId, sessionId) => api.del(`/agent/${agentId}/chat-history/${sessionId}`),
  // 音频两段式播放：POST /agent/audio/{id} → realId → GET /voiceClone/play/{realId}（blob）
  playAudioBlob: (realId) => fetch(API_BASE + '/voiceClone/play/' + realId, {
    headers: { Authorization: 'Bearer ' + getToken() }
  }).then(r => { if (!r.ok) throw { code: r.status, msg: '音频加载失败' }; return r.blob() }),

  // ===== 音色 / TTS =====
  ttsModels: () => api.get('/models/list', { modelType: 'TTS', page: 1, limit: 50 }),
  modelVoices: (modelId) => api.get(`/models/${encodeURIComponent(modelId)}/voices`),
  // cc-console 契约：ttsPreview 返回音频二进制流（blob），非 JSON
  ttsPreview: (modelId, voice, text) => fetch(API_BASE + '/models/ttsPreview' + buildQuery({
    modelId, voice, text: text || '你好，这是试听文本'
  }), { headers: { Authorization: 'Bearer ' + getToken() } }).then(r => {
    if (!r.ok) throw { code: r.status, msg: '试听失败 (HTTP ' + r.status + ')' }
    return r.blob()
  }),
  ttsVoicePage: (params) => api.get('/ttsVoice', params),
  ttsVoiceCreate: (body) => api.post('/ttsVoice', body),
  ttsVoiceUpdate: (id, body) => api.put(`/ttsVoice/${id}`, body),
  ttsVoiceDelete: (id) => api.post('/ttsVoice/delete', id ? [id] : []),
  voiceClonePlay: (id) => api.post(`/voiceClone/play/${id}`),

  // ===== 记忆 =====
  memoryAgents: () => api.get('/memory/agents'),
  memoryFacts: (params) => api.get('/memory/facts', params),
  createFact: (agentId, content) => api.post('/memory/facts', { agent_id: agentId, content }),
  updateFact: (factId, agentId, content, category) => api.put(`/memory/facts/${factId}`, { agent_id: agentId, content, category }),
  deleteFact: (factId, agentId) => api.del(`/memory/facts/${factId}?agent_id=${agentId}`),
  factFeedback: (factId, agentId, helpful) => api.post(`/memory/facts/${factId}/feedback`, { agent_id: agentId, helpful }),
  factReview: (factId, agentId, action) => api.post(`/memory/facts/${factId}/review`, { agent_id: agentId, action }),
  memoryEngineConfig: (providerCode, engine) => api.put(`/models/Memory/${providerCode}/${engine}`),

  // ===== 模型 =====
  modelList: (type) => api.get('/models/list', type ? { modelType: type, page: 1, limit: 100 } : undefined),
  modelNames: (type) => api.get('/models/names', { modelType: type }),
  modelDetail: (id) => api.get(`/models/${id}`),
  modelProvideTypes: (type) => api.get(`/models/${type}/provideTypes`),
  createModel: (type, providerCode, body) => api.post(`/models/${type}/${providerCode}`, body),
  updateModel: (type, providerCode, id, body) => api.put(`/models/${type}/${providerCode}/${id}`, body),
  deleteModel: (id) => api.del(`/models/${id}`),
  modelTest: (id, type) => api.get('/models/modelTest', { modelId: id, modelType: type }),
  enableModel: (id, status) => api.put(`/models/enable/${id}/${status}`),
  // ===== 设备 =====
  devicePage: (params) => api.get('/admin/device/all', params),
  deviceUpdate: (id, body) => api.put(`/device/update/${id}`, body),
  deviceManualAdd: (body) => api.post('/device/manual-add', body),
  deviceUnbind: (body) => api.post('/device/unbind', body),

  // ===== 系统参数 =====
  paramPage: (params) => api.get('/admin/params/page', params || { page: 1, limit: 100 }),
  updateParam: (body) => api.put('/admin/params', body),

  // ===== 用户 =====
  userPage: (params) => api.get('/admin/users', params),
  resetPassword: (id) => api.put(`/admin/users/${id}`),
  deleteUser: (id) => api.del(`/admin/users/${id}`),
  changeUserStatus: (ids, status) => api.put(`/admin/users/changeStatus/${status}`, ids),

  // ===== 模板 =====
  templateList: () => api.get('/agent/template'),
  templatePage: (params) => api.get('/agent/template/page', params),
  templateDetail: (id) => api.get(`/agent/template/${id}`),
  createTemplate: (body) => api.post('/agent/template', body),
  updateTemplate: (body) => api.put('/agent/template', body),
  deleteTemplate: (id) => api.del(`/agent/template/${id}`),
  batchDeleteTemplate: (ids) => api.post('/agent/template/batch-remove', ids),
  tagList: () => api.get('/agent/tag/list'),

  // ===== 知识库 =====
  datasetPage: (params) => api.get('/datasets', params),
  datasetDetail: (id) => api.get(`/datasets/${id}`),
  createDataset: (body) => api.post('/datasets', body),
  updateDataset: (body, id) => api.put(`/datasets/${id}`, body),
  deleteDataset: (id) => api.del(`/datasets/${id}`),
  datasetDocs: (id, params) => api.get(`/datasets/${id}/documents`, params),
  ragModels: () => api.get('/datasets/rag-models'),

  // ===== OTA =====
  otaPage: (params) => api.get('/otaMag', params || { page: 1, limit: 100 }),
  uploadOta: (file) => {
    const form = new FormData()
    form.append('file', file)
    return fetch(API_BASE + '/otaMag/upload', {
      method: 'POST', headers: { Authorization: 'Bearer ' + getToken() }, body: form
    }).then(r => r.json())
  },
  deleteOta: (id) => api.del(`/otaMag/${id}`),
  otaDownloadUrl: (id) => API_BASE + '/otaMag/download/' + id,

  // ===== 数据字典 =====
  dictTypePage: (params) => api.get('/admin/dict/type/page', params || { page: 1, limit: 100 }),
  dictData: (dictType) => api.get(`/admin/dict/data/type/${dictType}`),
  saveDictData: (body) => api.post(body.id ? '/admin/dict/data/update' : '/admin/dict/data/save', body),
  deleteDictData: (ids) => api.post('/admin/dict/data/delete', ids),

  // ===== 替换词 =====
  correctWordList: (params) => api.get('/correct-word/file/list', params || { page: 1, limit: 100 }),
  createCorrectWord: (fileName, content) => api.post('/correct-word/file', { fileName, content }),
  updateCorrectWord: (id, fileName, content) => api.put(`/correct-word/file/${id}`, { fileName, content }),
  deleteCorrectWord: (id) => api.del(`/correct-word/file/${id}`),

  // ===== 服务器节点 =====
  serverList: () => api.get('/admin/server/server-list'),

  // ===== 链路模拟 =====
  asrRecognize: (modelId) => api.post(`/models/asrRecognize?modelId=${encodeURIComponent(modelId)}`),
  llmPreview: (modelId, text, systemPrompt) => api.get('/models/llmPreview', {
    modelId, text, systemPrompt: systemPrompt || ''
  })
}
