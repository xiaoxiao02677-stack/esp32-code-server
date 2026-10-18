// ============ 原控制台 API 适配层（契约零修改，差异前端消化 C4） ============
// 基线: cc-console/contract/openapi.json (173 接口)
// 反代: /xiaozhi/ -> manager-api:8002 (同源，无 CORS)
// 鉴权: Bearer token (localStorage)，登录密码 SM2 加密 —— 与原控制台完全一致 (C3)

import { sm2 } from 'sm-crypto'
import { ref } from 'vue'

const API_BASE = '/xiaozhi'
const TOKEN_KEY = 'cc_token'
// 用户模块：登录后缓存的用户信息（username/superAdmin/roles[]），路由守卫与导航切换按钮用
const USER_INFO_KEY = 'cc_user_info'
// Token提前过期检查阈值：剩余时间小于此值(毫秒)时提示续期
const TOKEN_WARN_THRESHOLD_MS = 5 * 60 * 1000 // 5分钟

export function getToken() {
  const stored = localStorage.getItem(TOKEN_KEY)

  // 如果已有cc_token，直接解析返回
  if (stored) {
    try {
      const parsed = JSON.parse(stored)
      if (parsed && parsed.token) return parsed.token
      // 如果是纯字符串token（旧格式），直接返回
      if (typeof parsed === 'string') return parsed
    } catch {
      // 解析失败，可能是纯字符串，直接返回
      return stored
    }
  }

  // 迁移：v2_token → cc_token（与原控制台登录态互通）
  const legacy = localStorage.getItem('v2_token')
  if (legacy) {
    // 判断是否为纯字符串（JWT无"."分隔段解析失败即为纯串）
    let isPlainString = false
    try { JSON.parse(legacy); isPlainString = false } catch { isPlainString = true }
    if (isPlainString) {
      // 纯字符串JWT：包装为JSON格式并记录登录时间，供后续过期检测使用
      localStorage.setItem(TOKEN_KEY, JSON.stringify({ token: legacy, loginAt: Date.now() }))
    } else {
      // 已是JSON格式，原样迁移
      localStorage.setItem(TOKEN_KEY, legacy)
    }
    localStorage.removeItem('v2_token')
    return legacy
  }

  return ''
}

export function getTokenInfo() {
  try {
    const raw = localStorage.getItem(TOKEN_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    // 纯字符串token（迁移后或旧格式），补全必要字段避免误判过期
    if (typeof parsed === 'string') {
      return { token: parsed, loginAt: Date.now(), expire: 999999 }
    }
    // 兼容缺少loginAt/expire的残缺JSON
    if (parsed.token && !parsed.loginAt) parsed.loginAt = Date.now()
    if (parsed.token && !parsed.expire) parsed.expire = 999999
    return parsed
  } catch { return null }
}

/** 检查token是否即将过期（提前5分钟预警） */
export function isTokenExpiringSoon() {
  const info = getTokenInfo()
  if (!info || !info.expire || !info.loginAt) return false
  const remaining = info.loginAt + info.expire * 1000 - Date.now()
  return remaining < TOKEN_WARN_THRESHOLD_MS
}

/** 检查token是否已过期 */
export function isTokenExpired() {
  const info = getTokenInfo()
  if (!info || !info.expire || !info.loginAt) return true
  return Date.now() >= info.loginAt + info.expire * 1000
}

export function setToken(raw) { localStorage.setItem(TOKEN_KEY, raw) }
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_INFO_KEY)
  // 退出登录/过期清理：同步重置响应式用户状态，避免界面按钮残留旧角色判断
  userState.value = { username: '', superAdmin: 0, roles: [] }
}

/** 读取本地用户信息（登录时写入；旧登录态可能不存在，调用方需兜底） */
export function getUserInfo() {
  try {
    const raw = localStorage.getItem(USER_INFO_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    return parsed
  } catch { return null }
}

/** 是否具备管理端访问权限：superAdmin===1 或 roles 含 super_admin/admin */
export function hasAdminRole(info) {
  const u = info || getUserInfo()
  if (!u) return false
  if (Number(u.superAdmin) === 1) return true
  const roles = Array.isArray(u.roles) ? u.roles : []
  return roles.some(r => r === 'super_admin' || r === 'admin')
}

// 响应式用户状态：登录/守卫/按钮组件共用，避免裸读 localStorage 的非响应式陈旧值
export const userState = ref(getUserInfo() || { username: '', superAdmin: 0, roles: [] })

/** 是否为 demo 公开展示账号（DB super_admin=1）：默认进游客页但保留管理端切换按钮 */
export function isDemoUser(info) {
  const u = info || userState.value
  return !!(u && u.username && String(u.username).toLowerCase() === 'demo')
}

// 登录后默认路由：demo 展示账号→游客页；超管/管理员→管理端；其余→游客页
// 依赖 userState（refreshUserInfo 补全后调用才可靠；未补全时退化为角色未知→游客页，安全侧）
export function defaultRouteAfterLogin() {
  if (isDemoUser()) return '/customer'
  if (hasAdminRole(userState.value)) return '/admin'
  return '/customer'
}

// 用 /user/info 补全身份（TokenDTO 缺 superAdmin/roles 的旧后端兜底；新后端两源一致无副作用）
// 成功后同步写回 cc_user_info 与 userState；失败静默返回 false（不 throw，调用方用 localStorage 旧值）
export async function refreshUserInfo() {
  if (!getToken()) return false
  try {
    const res = await api.get('/user/info')
    const d = res.data || {}
    const merged = {
      username: d.username || (userState.value ? userState.value.username : '') || '',
      superAdmin: Number(d.superAdmin) === 1 ? 1 : 0,
      roles: Array.isArray(d.roles) ? d.roles : (userState.value && Array.isArray(userState.value.roles) ? userState.value.roles : [])
    }
    localStorage.setItem(USER_INFO_KEY, JSON.stringify(merged))
    userState.value = merged
    return true
  } catch { return false }
}

// 定时器：每30秒检查一次token状态，即将过期时自动重新登录（如果有refresh机制）或提示
let tokenCheckTimer = null
export function startTokenCheck(onExpire) {
  if (tokenCheckTimer) clearInterval(tokenCheckTimer)
  tokenCheckTimer = setInterval(() => {
    if (isTokenExpired()) {
      clearToken()
      if (onExpire && typeof onExpire === 'function') onExpire()
      else if (!location.hash.startsWith('#/login')) location.hash = '#/login'
    }
  }, 30000) // 每30秒检查一次
}

function buildQuery(params) {
  if (!params) return ''
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') q.append(k, v)
  }
  const s = q.toString()
  return s ? '?' + s : ''
}

async function request(method, path, { body, params, formData, raw, rawBody, contentType } = {}) {
  const url = API_BASE + path + buildQuery(params)
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = 'Bearer ' + token
  const init = { method, headers }
  if (rawBody !== undefined) {
    // 二进制/原始请求体：不做 JSON.stringify（如 ASR 音频 Blob）
    headers['Content-Type'] = contentType
    init.body = rawBody
  } else if (formData) {
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
    // 仅对「用户会话类」接口清 token 踢登录；服务间代理/系统接口的 401
    // （如"无效的服务器密钥"）属于后端配置问题，不应把用户踢出登录页。
    const isAuthCheck = path.startsWith('/user/info') || path.startsWith('/user/pub-config')
    if (!freshToken && (isAuthCheck || isTokenExpired())) {
      clearToken()
      if (!location.hash.startsWith('#/login')) location.hash = '#/login'
      throw { code: 401, msg: '登录已过期，请重新登录' }
    }
    if (!isAuthCheck) {
      // 非会话校验接口的 401：仅抛错给调用方展示，不动登录态
      throw { code: 401, msg: data.msg || '无权限访问该接口' }
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
    // 用户模块：缓存用户身份（username/superAdmin/roles），路由守卫与端切换按钮据此判断管理端权限。
    // 老后端登录响应可能不带 superAdmin/roles —— roles 取不到存 []，superAdmin 缺省按普通用户处理。
    const d = res.data || {}
    const info = {
      username: d.username || username,
      superAdmin: d.superAdmin === undefined || d.superAdmin === null ? 0 : d.superAdmin,
      roles: Array.isArray(d.roles) ? d.roles : []
    }
    localStorage.setItem(USER_INFO_KEY, JSON.stringify(info))
    // 同步响应式状态：登录成功即写入（新后端 login 响应已带权威角色数据时立即生效，不等 refreshUserInfo）
    userState.value = info
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
  // MCP Server 配置（per-agent JSON）
  mcpConfig: (agentId) => api.get(`/agent/mcp/config/${agentId}`),
  saveMcpConfig: (body) => api.post('/agent/mcp/config', body),
  deleteMcpConfig: (agentId) => api.del(`/agent/mcp/config/${agentId}`),
  validateMcpJson: (serverJson) => api.post('/agent/mcp/config/validate', { serverJson }),

  // ===== 聊天记录 =====
  chatHistory: (agentId, sessionId) => api.get(`/agent/${agentId}/chat-history/${sessionId}`),
  chatHistoryAudio: (audioId) => api.post(`/agent/audio/${audioId}`),
  deleteChatSession: (agentId, sessionId) => api.del(`/agent/${agentId}/chat-history/${sessionId}`),
  // 音频两段式播放：POST /agent/audio/{id} → realId → GET /agent/play/{realId}（blob）
  // 注意：第二段必须走 /agent/play/（官方 manager-web 同款）。
  // 不能用 /voiceClone/play/——该端点查 Redis 的 uuid 命名空间与 agent 音频命名空间不同，
  // 聊天记录的 realId 在 voiceClone 命名空间查不到必 404（曾致 /admin/chat 语音无法播放）。
  playAudioBlob: (realId) => fetch(API_BASE + '/agent/play/' + realId, {
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
  voiceClonePlay: (id) => api.get('/voiceClone/play/' + id),

  // ===== 记忆 =====
  memoryAgents: () => api.get('/memory/agents'),
  memoryFacts: (params) => api.get('/memory/facts', params),
  createFact: (agentId, content) => api.post('/memory/facts', { agent_id: agentId, content }),
  updateFact: (factId, agentId, content, category) => api.put(`/memory/facts/${factId}`, { agent_id: agentId, content, category }),
  deleteFact: (factId, agentId) => api.del(`/memory/facts/${factId}?agent_id=${agentId}`),
  factFeedback: (factId, agentId, helpful) => api.post(`/memory/facts/${factId}/feedback`, { agent_id: agentId, helpful }),
  factReview: (factId, agentId, action) => api.post(`/memory/facts/${factId}/review`, { agent_id: agentId, action }),
  memoryEngineConfig: (providerCode, engine) => api.put(`/models/Memory/${providerCode}/${engine}`),

  // ===== 记忆：实体图谱 =====
  memoryEntities: (agentId) => api.get(`/memory/entities/${agentId}`),
  memoryEntityGraph: (agentId) => api.get(`/memory/entities/${agentId}/graph`),

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
  createParam: (body) => api.post('/admin/params', body),
  deleteParam: (id) => api.del(`/admin/params/${id}`),

  // ===== 运维：服务重启 =====
  // Python 重启走既有 emit-action 链路（ServerSideManageController → WS 下发 restart → Python handle_restart 自重启）
  serverAction: (data) => api.post('/admin/server/emit-action', data),
  restartJavaApi: () => api.post('/admin/server/restart-manager', {}),

  // ===== 记忆：快速总结 =====
  memorySummarize: (agentId) => api.post(`/memory/agents/${agentId}/summarize`, {}),

  // ===== 用户 =====
  userPage: (params) => api.get('/admin/users', params),
  resetPassword: (id) => api.put(`/admin/users/${id}`),
  deleteUser: (id) => api.del(`/admin/users/${id}`),
  changeUserStatus: (ids, status) => api.put(`/admin/users/changeStatus/${status}`, ids),

  // ===== 用户模块：用户管理扩展（SPEC §4.2） =====
  userCreate: (b) => api.post('/admin/users', b),
  userDetail: (id) => api.get(`/admin/users/${id}`),
  userAssignRoles: (b) => api.put('/admin/users/roles', b),
  userRestore: (id) => api.put(`/admin/users/restore/${id}`),
  userImport: (list) => api.post('/admin/users/import', list),
  userExportUrl: (p) => `/xiaozhi/admin/users/export?${new URLSearchParams(p)}`,
  userSessions: (p) => api.get('/admin/users/sessions', p),
  userForceLogout: (id) => api.post(`/admin/users/forceLogout/${id}`, {}),

  // ===== 用户模块：角色（SPEC §4.1） =====
  rolePage: (p) => api.get('/admin/role/page', p),
  roleList: () => api.get('/admin/role/list'),
  roleDetail: (id) => api.get(`/admin/role/${id}`),
  roleSave: (b) => api.post('/admin/role/save', b),
  roleUpdate: (b) => api.put('/admin/role/update', b),
  roleDelete: (ids) => api.post('/admin/role/delete', ids),

  // ===== 用户模块：展示配置 / 默认配置（SPEC §4.3） =====
  displayConfigGet: (p) => api.get('/admin/display-config', p),
  displayConfigSave: (b) => api.put('/admin/display-config', b),
  userDefaultGet: (p) => api.get('/admin/user-default', p),
  userDefaultSave: (b) => api.put('/admin/user-default', b),

  // ===== 用户模块：自定义模型/音色审核（SPEC §4.4 管理端） =====
  customModelAuditPage: (p) => api.get('/admin/custom-models/page', p),
  customModelAudit: (b) => api.post('/admin/custom-models/audit', b),
  customModelQuota: (b) => api.put('/admin/custom-models/quota', b),
  customVoiceAuditPage: (p) => api.get('/admin/custom-voices/page', p),
  customVoiceAudit: (b) => api.post('/admin/custom-voices/audit', b),

  // ===== 用户模块：审计日志（SPEC §4.5） =====
  auditPage: (p) => api.get('/admin/audit/page', p),
  auditModules: () => api.get('/admin/audit/modules'),

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
  datasetPage: (params) => api.get('/datasets', params || { page: 1, page_size: 50 }),
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
  otaDownloadUrl: (id) => API_BASE + '/otaMag/getDownloadUrl/' + id,

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
  asrRecognize: (modelId, blob) => request('POST', '/models/asrRecognize', { params: { modelId }, rawBody: blob, contentType: (blob && blob.type) || 'audio/webm' }),
  llmPreview: (modelId, text, systemPrompt) => api.get('/models/llmPreview', {
    modelId, text, systemPrompt: systemPrompt || ''
  }),

  // ===== 唤醒词管理 =====
  getAgentWakeWords: (agentId) => api.get(`/agent/wake-word/${agentId}`),
  setAgentWakeWords: (agentId, wakeWords) => api.post(`/agent/wake-word/${agentId}`, { wakeWords }),
  // 唤醒词下发统一走 setAgentWakeWords（manager-api 侧转拼音 + 落库 + 转发推送）。
  // 原 wakeWordPush（直连 Python /api/wake-word/push，发 camelCase agentId）已删除：
  // 零调用点，且实现上必然 400 / 下发汉字被固件静默丢弃，留着只会被后续代码误用。
  wakeWordDevices: () => api.get('/api/wake-word/devices'),
  // ===== 记忆扩展API =====
  memoryTimelineChart: (agentId, days) => api.get(`/memory/timeline/${agentId}/chart?days=${days || 30}`),
  // ===== 推送调度 API（Python /api/push/*，Bearer auth_key 鉴权） =====
  // 任务列表：data.tasks[] = { push_id, status, type, priority, device_count, sent_count, failed_count, created_at }
  pushTasks: () => api.get('/api/push/tasks'),
  // 创建任务：body = { device_ids: [..], content: { push_type, audio_url, subtitles }, schedule: { type, cron?, delay_seconds? }, rate_limit? }
  // 返回 data.push_id
  pushSchedule: (data) => api.post('/api/push/schedule', data),
  // 单任务详情：data = { push_id, status, device_ids, content, schedule, rate_limit, sent_count, failed_count, created_at }
  pushGetTask: (pushId) => api.get(`/api/push/tasks/${pushId}`),
  pushOnlineDevices: () => api.get('/api/wake-word/devices'),

  // ===== 微信ClawBot API =====
  clawUsers: () => api.get('/wechat/claw/users'),
  clawBind: (data) => api.post('/wechat/claw/bind', data),
  clawUnbind: (openid) => api.del(`/wechat/claw/unbind/${openid}`),
  clawConversations: (openid) => api.get(`/wechat/claw/conversations/${openid}`),
  clawClearConversation: (openid) => api.del(`/wechat/claw/conversations/${openid}`),
  clawSendMessage: (openid, data) => api.post(`/wechat/claw/messages/${openid}`, data),
  clawSchedules: (openid) => api.get(`/wechat/claw/schedules/${openid}`),
  clawCreateSchedule: (openid, data) => api.post(`/wechat/claw/schedules/${openid}`, data),
  clawDeleteSchedule: (openid, id) => api.del(`/wechat/claw/schedules/${openid}/${id}`),
  clawToggleSchedule: (openid, id) => api.put(`/wechat/claw/schedules/${openid}/${id}/toggle`),
}

// ---------- 壁纸下发（P1-4，独立端点组，不并入 adminApi） ----------
// 契约：SPEC §4.8 —— 壁纸库 CRUD + 下发任务 + 结果轮询/重试
export const wallpaperApi = {
  // 壁纸库分页：GET /wallpaperMag?page&limit&keyword → { list, total }
  page: (params) => api.get('/wallpaperMag', params || { page: 1, limit: 50 }),
  // 上传壁纸（multipart：file、name）→ { id,name,url,thumbUrl,md5,size,width,height,format }
  upload: (formData) => api.upload('/wallpaperMag/upload', formData),
  // 删除壁纸：DELETE /wallpaperMag/{id}
  remove: (id) => api.del(`/wallpaperMag/${id}`),
  // 下发：POST /wallpaperMag/dispatch，body = { wallpaperId,targetType,deviceIds,agentIds,applyMode } → { taskId }
  dispatch: (payload) => api.post('/wallpaperMag/dispatch', payload),
  // 任务进度：GET /wallpaperMag/task/{taskId} → { status,total,sent,success,failed,devices[] }
  task: (taskId) => api.get(`/wallpaperMag/task/${taskId}`),
  // 失败重试：POST /wallpaperMag/task/{taskId}/retry，body = { deviceIds } → { taskId }
  retry: (taskId, deviceIds) => api.post(`/wallpaperMag/task/${taskId}/retry`, { deviceIds })
}

// ---------- 用户模块：当前用户资源端（SPEC §6 userApi，页面 agent 按此调用） ----------
export const userApi = {
  // 数据源聚合：模型选择 UI 的唯一入口（模型为 0 规则）
  myResources: () => api.get('/user/resources'),
  myDisplayConfig: () => api.get('/user/display-config'),
  myDefaults: () => api.get('/user/defaults'),
  // 自定义模型（本人数据，apiKey 掩码）
  customModelPage: (p) => api.get('/user/custom-models', p),
  customModelCreate: (b) => api.post('/user/custom-models', b),
  customModelUpdate: (id, b) => api.put(`/user/custom-models/${id}`, b),
  customModelDelete: (id) => api.del(`/user/custom-models/${id}`),
  customModelHealth: (id) => api.post(`/user/custom-models/${id}/health`, {}),
  // 自定义音色（同构，无 health）
  customVoicePage: (p) => api.get('/user/custom-voices', p),
  customVoiceCreate: (b) => api.post('/user/custom-voices', b),
  customVoiceUpdate: (id, b) => api.put(`/user/custom-voices/${id}`, b),
  customVoiceDelete: (id) => api.del(`/user/custom-voices/${id}`)
}
// ============ 订单管理API（对齐已部署的 OrderController：@RequestMapping("/order")，context-path=/xiaozhi） ============
const orderApi = {
  // 分页列表：GET /order/page（keyword 模糊匹配 user_name/contact/product）
  orderPage: (params = {}) => {
    const { page = 1, limit = 10, keyword = '' } = params
    return api.get('/order/page', { page, limit, keyword })
  },
  // 详情：GET /order/info/{id}
  orderInfo: (id) => api.get(`/order/info/${id}`),
  // 新增：POST /order/create
  orderCreate: (data) => api.post('/order/create', data),
  // 更新：PUT /order/update（body 必须含 id）
  orderUpdate: (id, data) => api.put('/order/update', { ...data, id }),
  // 删除（软删）：DELETE /order/delete/{id}
  orderDelete: (id) => api.del(`/order/delete/${id}`),
  // 导出数据：GET /order/export?keyword= → { code:0, data:[ {...订单字段...} ] }（由前端生成 Excel）
  orderExportList: (params = {}) => api.get('/order/export', { keyword: params.keyword || '' })
}

// 合并到adminApi
Object.assign(adminApi, orderApi)
