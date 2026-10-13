<template>
  <div>
    <div class="page-head">
      <div>
        <h1>΢�� ClawBot <span style="color:var(--primary)">����</span></h1>
        <p class="sub">��״̬ �� �Ի���¼ �� ��ʱ���� �� LLM ����</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="load" :disabled="loading">? ˢ��</button>
      </div>
    </div>

    <div class="tabs">
      <button class="tab" :class="{ active: tab === 'bind' }" @click="tab = 'bind'">��״̬</button>
      <button class="tab" :class="{ active: tab === 'chat' }" @click="tab = 'chat'">�Ի���¼</button>
      <button class="tab" :class="{ active: tab === 'cron' }" @click="tab = 'cron'">��ʱ����</button>
      <button class="tab" :class="{ active: tab === 'settings' }" @click="tab = 'settings'">LLM ����</button>
    </div>

    <div v-if="tab === 'bind'" class="panel-content">
      <div class="card">
        <div class="card-head">
          <h3>�Ѱ��û��б�</h3>
          <span class="badge badge-green">{{ boundUsers.length }} ����</span>
        </div>
        <div v-if="bindLoading" class="loading">������...</div>
        <div v-else-if="bindError" class="error">{{ bindError }}</div>
        <table v-else-if="boundUsers.length" class="data-table">
          <thead>
            <tr><th>�û�ID</th><th>΢�ź�</th><th>�ǳ�</th><th>��ʱ��</th><th>����¼</th><th>����</th></tr>
          </thead>
          <tbody>
            <tr v-for="u in boundUsers" :key="u.userId">
              <td><code>{{ u.userId?.slice(0, 12) }}��</code></td>
              <td>{{ u.wechatId || '��' }}</td>
              <td>{{ u.nickname || '��' }}</td>
              <td style="color:var(--text-sub)">{{ fmtTime(u.boundAt) }}</td>
              <td style="color:var(--text-sub)">{{ fmtTime(u.lastLoginAt) }}</td>
              <td><button class="link-btn danger" @click="unbindUser(u)">���</button></td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state"><div class="empty-icon">??</div><strong>���ް��û�</strong></div>
      </div>

      <div class="card">
        <div class="card-head"><h3>�ֶ�������Ϣ</h3></div>
        <div class="send-form">
          <div class="form-row">
            <select v-model="sendForm.userId">
              <option value="">ѡ��Ŀ���û���</option>
              <option v-for="u in boundUsers" :key="u.userId" :value="u.userId">
                {{ u.nickname || u.wechatId || u.userId }}
              </option>
            </select>
          </div>
          <div class="form-row">
            <textarea v-model="sendForm.content" placeholder="������Ϣ���ݡ�" rows="3"></textarea>
          </div>
          <div class="form-row">
            <button class="btn btn-primary" @click="sendMessage" :disabled="sending">{{ sending ? '�����С�' : '����' }}</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="tab === 'chat'" class="panel-content">
      <div class="chat-layout">
        <div class="card chat-list-card">
          <div class="card-head">
            <h3>�Ի��б�</h3>
            <input v-model="chatSearch" placeholder="�����Ự��" class="search-input" />
          </div>
          <div v-if="chatLoading" class="loading">������...</div>
          <div v-else-if="chatError" class="error">{{ chatError }}</div>
          <div v-else-if="sessions.length" class="sess-list">
            <div v-for="s in filteredSessions" :key="s.sessionId"
              class="sess-item" :class="{ active: selSession?.sessionId === s.sessionId }"
              @click="pickSession(s)">
              <div class="sess-main">{{ s.title || (s.lastMessage || '').slice(0, 20) || 'δ�����Ự' }}</div>
              <div class="sess-sub">{{ fmtTime(s.lastActiveAt) }} �� {{ s.msgCount ?? 0 }} ��</div>
            </div>
          </div>
          <div v-else class="empty-state"><div class="empty-icon">??</div><strong>���޶Ի���¼</strong></div>
        </div>

        <div class="card chat-msg-card">
          <div class="card-head">
            <h3>{{ selSession?.title || 'ѡ��Ự' }}<span v-if="selSession" class="hint">{{ selSession.sessionId?.slice(0, 12) }}</span></h3>
            <button class="btn btn-sm btn-ghost" @click="loadMessages" :disabled="msgLoading">?</button>
          </div>
          <div v-if="!selSession" class="empty-state" style="min-height:200px">
            <div class="empty-icon">??</div><strong>�����ѡ��Ự�鿴��Ϣ</strong>
          </div>
          <div v-else style="max-height:420px;overflow:auto;padding:8px 0">
            <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
              <div class="msg-role">{{ m.role === 'user' ? '�û�' : 'ClawBot' }}</div>
              <div class="msg-bubble">{{ m.content }}</div>
              <div class="msg-time">{{ fmtTime(m.timestamp) }}</div>
            </div>
            <div v-if="msgLoading" class="loading">�����С�</div>
            <div v-if="!messages.length && !msgLoading" class="empty-state"><strong>������Ϣ</strong></div>
          </div>
          <div v-if="selSession" class="send-bar">
            <input v-model="chatInput" placeholder="������Ϣ��" @keyup.enter="sendToSession" />
            <button class="btn btn-primary btn-sm" @click="sendToSession" :disabled="!chatInput.trim() || sending">��</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="tab === 'cron'" class="panel-content">
      <div class="card">
        <div class="card-head">
          <h3>��ʱ�����б�</h3>
          <button class="btn btn-primary btn-sm" @click="showCreateCron = true">�� �½�����</button>
        </div>
        <div v-if="cronLoading" class="loading">������...</div>
        <div v-else-if="cronError" class="error">{{ cronError }}</div>
        <div v-else-if="!cronTasks.length" class="empty-state"><div class="empty-icon">?</div><strong>���޶�ʱ����</strong></div>
        <table v-else class="data-table">
          <thead>
            <tr><th>��������</th><th>Cron</th><th>Ŀ���û�</th><th>��Ϣ����</th><th>״̬</th><th>���ִ��</th><th>����</th></tr>
          </thead>
          <tbody>
            <tr v-for="t in cronTasks" :key="t.id">
              <td><strong>{{ t.name || 'δ����' }}</strong></td>
              <td><code>{{ t.cron }}</code></td>
              <td>{{ t.targetUserId ? t.targetUserId.slice(0,12)+'��' : 'ȫ��' }}</td>
              <td class="cell-ellipsis">{{ (t.message||'').slice(0,40) }}</td>
              <td><span class="badge" :class="t.enabled?'badge-green':'badge-gray'">{{ t.enabled?'����':'����' }}</span></td>
              <td style="color:var(--text-sub)">{{ fmtTime(t.lastRunAt) }}</td>
              <td>
                <button class="link-btn" @click="toggleCron(t)">{{ t.enabled?'����':'����' }}</button>
                <button class="link-btn danger" @click="deleteCron(t.id)">ɾ��</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="tab === 'settings'" class="panel-content">
      <div class="card">
        <div class="card-head"><h3>LLM �ṩ������</h3></div>
        <div v-if="llmLoading" class="loading">������...</div>
        <div v-else-if="llmError" class="error">{{ llmError }}</div>
        <form v-else @submit.prevent="saveLlmConfig" class="llm-form">
          <div class="form-group"><label>�ṩ��</label>
            <select v-model="llmForm.provider">
              <option value="deepseek">DeepSeek</option>
              <option value="openai">OpenAI</option>
              <option value="azure">Azure OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="custom">�Զ��� (OpenAI ����)</option>
            </select>
          </div>
          <div class="form-group"><label>API Base URL</label><input v-model="llmForm.baseUrl" placeholder="https://api.deepseek.com" /></div>
          <div class="form-group"><label>API Key</label><input v-model="llmForm.apiKey" type="password" placeholder="sk-��" /></div>
          <div class="form-group"><label>ģ������</label><input v-model="llmForm.model" placeholder="deepseek-chat" /></div>
          <div class="form-row form-group">
            <div><label>�¶� (temperature)</label><input v-model.number="llmForm.temperature" type="number" step="0.1" min="0" max="2" /></div>
            <div><label>��� Token</label><input v-model.number="llmForm.maxTokens" type="number" min="1" /></div>
          </div>
          <div class="form-group"><label>ϵͳ��ʾ��</label><textarea v-model="llmForm.systemPrompt" rows="4" placeholder="����һ���������֡�"></textarea></div>
          <div class="form-actions">
            <button type="submit" class="btn btn-primary" :disabled="llmSaving">��������</button>
            <button type="button" class="btn btn-ghost" @click="testLlm" :disabled="llmTesting">{{ llmTesting ? '�����С�' : '��������' }}</button>
          </div>
          <div v-if="llmTestResult" :class="['test-result', llmTestOk ? 'ok' : 'err']">{{ llmTestResult }}</div>
        </form>
      </div>
    </div>

    <div v-if="showCreateCron" class="modal-overlay" @click.self="showCreateCron = false">
      <div class="modal">
        <div class="modal-header">
          <h3>�½���ʱ����</h3>
          <button class="close" @click="showCreateCron = false">��</button>
        </div>
        <div class="modal-body">
          <div class="form-group"><label>��������</label><input v-model="cronForm.name" placeholder="ÿ���ʺ�" /></div>
          <div class="form-group"><label>Cron ����ʽ</label><input v-model="cronForm.cron" placeholder="0 9 * * *" /><small class="hint">����ÿ�� 9:00 �� 0 9 * * *</small></div>
          <div class="form-group"><label>Ŀ���û�</label>
            <select v-model="cronForm.targetUserId">
              <option value="">ȫ�����û�</option>
              <option v-for="u in boundUsers" :key="u.userId" :value="u.userId">{{ u.nickname || u.wechatId }}</option>
            </select>
          </div>
          <div class="form-group"><label>��Ϣ����</label><textarea v-model="cronForm.message" rows="3" placeholder="�簲������ҲҪ����Ŷ��"></textarea></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="showCreateCron = false">ȡ��</button>
          <button class="btn btn-primary" @click="createCron" :disabled="cronCreating">����</button>
        </div>
      </div>
    </div>
  </div>
</template>
<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { api, getToken } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')

// API helpers
const auth = () => `Bearer ${getToken()}`
const apiGet = (path) => api.get(path)
const apiPost = (path, body) => api.post(path, body)
const apiDel = (path) => api.del(path)
const apiPut = (path, body) => api.put(path, body)

const tab = ref('bind')
const loading = ref(false)

// ===== ��״̬ =====
const boundUsers = ref([])
const bindLoading = ref(false)
const bindError = ref('')
const sending = ref(false)
const sendForm = ref({ userId: '', content: '' })

// ===== �Ի���¼ =====
const sessions = ref([])
const selSession = ref(null)
const messages = ref([])
const chatLoading = ref(false)
const chatError = ref('')
const msgLoading = ref(false)
const chatInput = ref('')
const chatSearch = ref('')

const filteredSessions = computed(() => {
  if (!chatSearch.value) return sessions.value
  const q = chatSearch.value.toLowerCase()
  return sessions.value.filter(s =>
    (s.title || '').toLowerCase().includes(q) ||
    (s.openid || '').toLowerCase().includes(q)
  )
})

// ===== ��ʱ���� =====
const cronTasks = ref([])
const cronLoading = ref(false)
const cronError = ref('')
const showCreateCron = ref(false)
const cronCreating = ref(false)
const cronForm = ref({ name: '', cron: '', targetUserId: '', message: '' })

// ===== LLM ���� =====
const llmLoading = ref(false)
const llmError = ref('')
const llmSaving = ref(false)
const llmTesting = ref(false)
const llmTestResult = ref('')
const llmTestOk = ref(false)
const llmForm = ref({
  provider: 'deepseek',
  baseUrl: '',
  apiKey: '',
  model: 'deepseek-chat',
  temperature: 0.7,
  maxTokens: 2048,
  systemPrompt: '����һ���������֡�'
})

function fmtTime(v) {
  if (!v) return '��'
  try { return new Date(v * 1000).toLocaleString('zh-CN', { hour12: false }).replace(/\//g, '-') } catch { return String(v) }
}

async function loadBoundUsers() {
  bindLoading.value = true
  bindError.value = ''
  try {
    const res = await apiGet('/wechat/claw/users')
    boundUsers.value = (res.data?.users || []).map(u => ({
      userId: u.openid,
      wechatId: u.openid,
      nickname: u.device_id,
      boundAt: u.bound_at * 1000,
      lastLoginAt: null,
      conversationCount: u.conversation_count || 0
    }))
  } catch (e) { bindError.value = e.msg || '����ʧ��' }
  finally { bindLoading.value = false }
}

async function unbindUser(u) {
  askConfirm({
    title: '����û�',
    message: `ȷ������û� ${u.nickname || u.wechatId || u.userId}��`,
    danger: true,
    onOk: async () => {
      try {
        await apiDel(`/wechat/claw/unbind/${u.userId}`)
        toast('�ѽ��')
        boundUsers.value = boundUsers.value.filter(x => x.userId !== u.userId)
      } catch (e) { toast(e.msg || '���ʧ��', 'error') }
    }
  })
}

async function sendMessage() {
  if (!sendForm.value.userId || !sendForm.value.content.trim()) {
    toast('��ѡ���û���������Ϣ', 'error'); return
  }
  sending.value = true
  try {
    await apiPost(`/wechat/claw/messages/${sendForm.value.userId}`, {
      content: sendForm.value.content,
      type: 'text'
    })
    toast('���ͳɹ�')
    sendForm.value.content = ''
  } catch (e) { toast(e.msg || '����ʧ��', 'error') }
  finally { sending.value = false }
}

async function loadSessions() {
  chatLoading.value = true
  chatError.value = ''
  try {
    const res = await apiGet('/wechat/claw/users')
    sessions.value = (res.data?.users || []).map(u => ({
      sessionId: u.openid,
      title: u.device_id || u.openid,
      lastMessage: '',
      lastActiveAt: u.bound_at * 1000,
      msgCount: u.conversation_count || 0
    }))
  } catch (e) { chatError.value = e.msg || '����ʧ��' }
  finally { chatLoading.value = false }
}

function pickSession(s) { selSession.value = s; messages.value = []; loadMessages() }

async function loadMessages() {
  if (!selSession.value) return
  msgLoading.value = true
  try {
    const res = await apiGet(`/wechat/claw/conversations/${selSession.value.sessionId}`)
    messages.value = (res.data?.messages || []).map(m => ({
      role: m.role || 'user',
      content: m.content || '',
      timestamp: m.timestamp * 1000
    }))
  } catch (e) { toast(e.msg || '����ʧ��', 'error') }
  finally { msgLoading.value = false }
}

async function sendToSession() {
  if (!chatInput.value.trim() || !selSession.value) return
  const text = chatInput.value.trim()
  chatInput.value = ''
  try {
    await apiPost(`/wechat/claw/messages/${selSession.value.sessionId}`, {
      content: text,
      type: 'text'
    })
    messages.value.push({ role: 'user', content: text, timestamp: Date.now() })
    toast('��Ϣ�ѷ���')
  } catch (e) { toast(e.msg || '����ʧ��', 'error') }
}

async function loadCronTasks() {
  cronLoading.value = true
  cronError.value = ''
  try {
    // Load schedules for first user (or all if no user selected)
    const openid = boundUsers.value[0]?.userId || ''
    if (!openid) {
      cronTasks.value = []
      return
    }
    const res = await apiGet(`/wechat/claw/schedules/${openid}`)
    cronTasks.value = (res.data?.schedules || []).map(s => ({
      id: s.id,
      name: s.task_name,
      cron: s.cron_expr,
      targetUserId: s.user_id,
      message: s.payload?.message || '',
      enabled: s.enabled,
      lastRunAt: s.last_run ? s.last_run * 1000 : null
    }))
  } catch (e) { cronError.value = e.msg || '����ʧ��' }
  finally { cronLoading.value = false }
}

async function toggleCron(t) {
  try {
    const openid = boundUsers.value[0]?.userId || ''
    await apiPut(`/wechat/claw/schedules/${openid}/${t.id}/toggle`)
    t.enabled = !t.enabled
    toast(t.enabled ? '������' : '�ѽ���')
  } catch (e) { toast(e.msg || '����ʧ��', 'error') }
}

async function deleteCron(id) {
  askConfirm({
    title: 'ɾ����ʱ����', message: 'ȷ��ɾ��������', danger: true,
    onOk: async () => {
      try {
        const openid = boundUsers.value[0]?.userId || ''
        await apiDel(`/wechat/claw/schedules/${openid}/${id}`)
        cronTasks.value = cronTasks.value.filter(t => t.id !== id)
        toast('��ɾ��')
      } catch (e) { toast(e.msg || 'ɾ��ʧ��', 'error') }
    }
  })
}

async function createCron() {
  if (!cronForm.value.cron || !cronForm.value.message.trim()) {
    toast('����д Cron ����ʽ����Ϣ����', 'error'); return
  }
  const openid = cronForm.value.targetUserId || (boundUsers.value[0]?.userId || '')
  if (!openid) {
    toast('���Ȱ��û�', 'error'); return
  }
  cronCreating.value = true
  try {
    await apiPost(`/wechat/claw/schedules/${openid}`, {
      task_name: cronForm.value.name || 'δ��������',
      cron: cronForm.value.cron,
      message: cronForm.value.message
    })
    showCreateCron.value = false
    cronForm.value = { name: '', cron: '', targetUserId: '', message: '' }
    await loadCronTasks()
    toast('�����ɹ�')
  } catch (e) { toast(e.msg || '����ʧ��', 'error') }
  finally { cronCreating.value = false }
}

async function loadLlmConfig() {
  llmLoading.value = true
  llmError.value = ''
  try {
    // Try to load from config, fallback to defaults
    const res = await apiGet('/wechat/claw/llm-config')
    if (res.data) {
      llmForm.value = { ...llmForm.value, ...res.data }
    }
  } catch (e) {
    // Use defaults
    llmForm.value = { provider: 'deepseek', baseUrl: 'https://api.deepseek.com', apiKey: '', model: 'deepseek-chat', temperature: 0.7, maxTokens: 2048, systemPrompt: '����һ���������֡�' }
  } finally { llmLoading.value = false }
}

async function saveLlmConfig() {
  llmSaving.value = true
  try {
    await apiPost('/wechat/claw/llm-config', llmForm.value)
    toast('����ɹ�')
  } catch (e) { toast(e.msg || '����ʧ��', 'error') }
  finally { llmSaving.value = false }
}

async function testLlm() {
  llmTesting.value = true
  llmTestResult.value = ''
  try {
    const res = await apiPost('/wechat/claw/llm-test', llmForm.value)
    llmTestOk.value = true
    llmTestResult.value = '���ӳɹ� ?'
  } catch (e) {
    llmTestOk.value = false
    llmTestResult.value = '����ʧ�ܣ�' + (e.msg || 'δ֪����')
  } finally { llmTesting.value = false }
}

async function load() {
  loading.value = true
  try { await Promise.all([loadBoundUsers(), loadSessions(), loadCronTasks(), loadLlmConfig()]) }
  finally { loading.value = false }
}

onMounted(load)
</script>
<style scoped>
.tabs { display: flex; gap: 4px; margin: 16px 0 20px; border-bottom: 2px solid var(--border); }
.tab {
  padding: 8px 18px; border: none; background: none; cursor: pointer;
  font-size: 14px; color: var(--text-sub); border-bottom: 2px solid transparent;
  margin-bottom: -2px; transition: color .15s, border-color .15s;
}
.tab:hover { color: var(--primary); }
.tab.active { color: var(--primary); border-bottom-color: var(--primary); font-weight: 600; }

.panel-content { animation: fadeIn .2s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(4px) } to { opacity: 1; transform: none } }

.card {
  background: white; border-radius: 12px; padding: 20px;
  box-shadow: var(--shadow-card); margin-bottom: 20px;
}
.card-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--border);
}
.card-head h3 { margin: 0; font-size: 15px; font-weight: 600; }
.card-head .hint { font-size: 12px; color: var(--text-sub); font-weight: 400; margin-left: 8px; }

.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th, .data-table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); }
.data-table th { color: var(--text-sub); font-weight: 500; font-size: 12px; }
.data-table tr:last-child td { border-bottom: none; }
.data-table code { background: #F0F4FF; padding: 2px 6px; border-radius: 4px; font-size: 12px; color: var(--primary); }
.cell-ellipsis { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.send-form { display: flex; flex-direction: column; gap: 12px; }
.form-row { display: flex; gap: 8px; }
.form-row select, .form-row input, .form-row textarea {
  flex: 1; padding: 8px 12px; border: 1.5px solid var(--border); border-radius: 8px;
  font-size: 13px; outline: none; background: white; color: var(--text);
}
.form-row select:focus, .form-row input:focus, .form-row textarea:focus { border-color: var(--primary); }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 12px; color: var(--text-sub); margin-bottom: 4px; font-weight: 500; }
.form-group input, .form-group select, .form-group textarea {
  width: 100%; padding: 8px 12px; border: 1.5px solid var(--border); border-radius: 8px;
  font-size: 13px; outline: none; background: white; color: var(--text);
}
.form-group input:focus, .form-group select:focus, .form-group textarea:focus { border-color: var(--primary); }
.form-row.form-group { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.form-actions { display: flex; gap: 10px; margin-top: 4px; }
.test-result { margin-top: 12px; padding: 10px 14px; border-radius: 8px; font-size: 13px; }
.test-result.ok { background: #dcfce7; color: #16a34a; }
.test-result.err { background: #fee2e2; color: #dc2626; }

/* �Ի����� */
.chat-layout { display: flex; gap: 20px; }
.chat-list-card { flex: 0 0 280px; }
.chat-msg-card { flex: 1; min-width: 0; }
.search-input {
  border: 1.5px solid var(--border); border-radius: 8px; padding: 5px 10px;
  font-size: 12px; outline: none; width: 140px;
}
.search-input:focus { border-color: var(--primary); }

.sess-list { display: flex; flex-direction: column; gap: 2px; }
.sess-item {
  padding: 10px 12px; border-radius: 10px; cursor: pointer;
  transition: background .15s; border: 1.5px solid transparent;
}
.sess-item:hover { background: var(--bg-soft); }
.sess-item.active { background: #EAF2FF; border-color: var(--primary); }
.sess-main { font-size: 13px; font-weight: 500; margin-bottom: 2px; }
.sess-sub { font-size: 11px; color: var(--text-sub); }

.msg { margin-bottom: 12px; display: flex; flex-direction: column; }
.msg.user { align-items: flex-end; }
.msg-role { font-size: 11px; color: var(--text-sub); margin-bottom: 2px; }
.msg-bubble {
  max-width: 75%; padding: 8px 14px; border-radius: 12px;
  font-size: 13px; line-height: 1.5; word-break: break-word;
}
.msg.user .msg-bubble { background: var(--primary); color: #fff; border-radius: 12px 12px 2px 12px; }
.msg.assistant .msg-bubble { background: var(--bg-soft); color: var(--text); border-radius: 12px 12px 12px 2px; }
.msg-time { font-size: 11px; color: var(--text-sub); margin-top: 2px; }

.send-bar {
  display: flex; gap: 8px; padding: 12px 0 4px; border-top: 1px solid var(--border); margin-top: 8px;
}
.send-bar input {
  flex: 1; padding: 8px 12px; border: 1.5px solid var(--border); border-radius: 8px;
  font-size: 13px; outline: none; background: var(--bg-soft);
}
.send-bar input:focus { border-color: var(--primary); background: white; }

/* ���� */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(15,22,40,.45);
  display: grid; place-items: center; z-index: 150;
}
.modal {
  background: #fff; border-radius: 16px; width: min(480px, 92vw);
  box-shadow: 0 24px 60px rgba(0,0,0,.2);
}
.modal-header {
  padding: 18px 20px; border-bottom: 1px solid var(--border);
  display: flex; justify-content: space-between; align-items: center;
}
.modal-header h3 { margin: 0; font-size: 16px; }
.modal-header .close {
  background: none; border: none; font-size: 22px; cursor: pointer;
  color: var(--text-sub); line-height: 1;
}
.modal-header .close:hover { color: var(--text); }
.modal-body { padding: 20px; }
.modal-footer {
  padding: 14px 20px; border-top: 1px solid var(--border);
  display: flex; justify-content: flex-end; gap: 10px;
}

/* ͨ��״̬ */
.loading, .error, .empty-state { text-align: center; padding: 40px 20px; color: var(--text-sub); }
.error { color: var(--danger); }
.empty-state .empty-icon { font-size: 32px; margin-bottom: 8px; }
.empty-state strong { display: block; color: var(--text); font-size: 14px; margin-top: 4px; }

.hint { font-size: 11px; color: var(--text-sub); margin-top: 2px; display: block; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 99px; font-size: 11px; font-weight: 500; }
.badge-green { background: #dcfce7; color: #16a34a; }
.badge-gray { background: #f1f5f9; color: #64748b; }

.link-btn { background: none; border: none; cursor: pointer; font-size: 13px; color: var(--primary); padding: 0; }
.link-btn:hover { text-decoration: underline; }
.link-btn.danger { color: var(--danger); }

.btn-sm { padding: 5px 12px; font-size: 12px; }
.btn-ghost { background: transparent; border: 1.5px solid var(--border); color: var(--text); border-radius: 8px; padding: 6px 14px; font-size: 13px; cursor: pointer; }
.btn-ghost:hover { background: var(--bg-soft); }
.btn-ghost:disabled { opacity: .5; cursor: not-allowed; }
.btn-primary {
  background: var(--primary); color: #fff; border: none; border-radius: 8px;
  padding: 7px 16px; font-size: 13px; cursor: pointer; font-weight: 500;
}
.btn-primary:hover { background: var(--primary-hover); }
.btn-primary:disabled { opacity: .5; cursor: not-allowed; }

@media (max-width: 768px) {
  .chat-layout { flex-direction: column; }
  .chat-list-card { flex: none; }
  .form-row.form-group { grid-template-columns: 1fr; }
}
</style>