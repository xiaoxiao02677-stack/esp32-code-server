<template>
  <div>
    <div class="page-head">
      <div>
        <h1>智能体 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">迁移自 /cc/ 智能体页：列表/详情/绑定设备/会话</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="openCreate">＋ 新增智能体</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="🤖" label="智能体" :value="agents.length" />
      <StatCard icon="📡" label="已绑定设备" :value="boundTotal" />
      <StatCard icon="💬" label="会话" :value="sessionCount" note="选中智能体" />
      <StatCard icon="🔗" label="MCP 接入点" :value="mcpResult ? '已获取' : '—'" :note="mcpAddr" />
    </div>

    <DataTable title="智能体清单" :total="agents.length" :page="1" :pages="1">
      <table class="data-table">
        <thead><tr><th>智能体</th><th>模型</th><th>音色</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="a in agents" :key="a.id">
            <td><div class="cell-main">{{ a.name }}</div><div class="cell-sub">{{ a.id }}</div></td>
            <td>{{ a.llmModel || '—' }}</td>
            <td>{{ a.ttsModel || '—' }}</td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="loadSessions(a)">会话</button>
                <button class="link-btn" @click="loadMcp(a)">MCP</button>
                <button class="link-btn" @click="openEdit(a)">编辑</button>
                <button class="link-btn danger" @click="remove(a)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="agents.length === 0" class="empty-state">
        <div class="empty-icon">🤖</div><strong>暂无智能体</strong>
      </div>
    </DataTable>

    <!-- 会话列表 -->
    <div v-if="sessions.show" class="modal-mask" @click.self="sessions.show = false">
      <div class="modal" style="width:min(560px,94vw)">
        <h3>会话 — {{ sessions.agentName }}</h3>
        <table class="data-table">
          <thead><tr><th>会话 ID</th><th>消息数</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="s in sessions.list" :key="s.sessionId">
              <td style="font-size:12px">{{ s.sessionId }}</td>
              <td>{{ s.messageCount ?? s.count ?? '—' }}</td>
              <td><button class="link-btn" @click="goChat(s)">查看聊天</button></td>
            </tr>
          </tbody>
        </table>
        <div class="modal-actions" style="margin-top:14px">
          <button class="btn btn-ghost" @click="sessions.show = false">关闭</button>
        </div>
      </div>
    </div>

    <!-- 编辑弹窗 -->
    <div v-if="editor.show" class="modal-mask" @click.self="editor.show = false">
      <div class="modal">
        <h3>{{ editor.id ? '编辑智能体' : '新增智能体' }}</h3>
        <div class="form-row"><label>名称</label><input v-model="editor.name" /></div>
        <div class="form-row"><label>系统提示词</label><textarea v-model="editor.prompt" rows="3"></textarea></div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="editor.show = false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { inject, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const router = useRouter()
const toast = inject('toast')
const askConfirm = inject('askConfirm')

const agents = ref([])
const loading = ref(false)
const saving = ref(false)
const boundTotal = ref(0)
const sessionCount = ref(0)
const mcpResult = ref(null)
const mcpAddr = ref('')
const editor = reactive({ show: false, id: null, name: '', prompt: '' })
const sessions = reactive({ show: false, agentName: '', agentId: null, list: [] })

async function load() {
  loading.value = true
  try {
    const res = await adminApi.agentList()
    agents.value = (res.data || []).map(a => ({
      id: a.agentId || a.id,
      name: a.agentName || a.name || '未命名',
      llmModel: a.llmModel || '—',
      ttsModel: a.ttsModelId ? 'ID:' + a.ttsModelId.slice(0, 8) : '—'
    }))
    boundTotal.value = agents.value.filter(a => a.deviceName).length
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

async function loadSessions(a) {
  sessions.show = true
  sessions.agentName = a.name
  sessions.agentId = a.id
  sessions.list = []
  try {
    const res = await adminApi.agentSessions(a.id, { page: 1, limit: 10 })
    const data = res.data || {}
    sessions.list = data.list || []
    sessionCount.value = data.total ?? sessions.list.length
  } catch (e) { toast(e.msg || '会话加载失败', 'error') }
}

async function loadMcp(a) {
  try {
    const res = await adminApi.mcpAddress(a.id)
    mcpResult.value = res.data
    mcpAddr.value = typeof res.data === 'string' ? res.data : (res.data?.url || JSON.stringify(res.data).slice(0, 40))
    toast('MCP 地址已获取')
  } catch (e) { toast(e.msg || 'MCP 获取失败', 'error') }
}

function goChat(s) {
  sessions.show = false
  router.push({ path: '/admin/chat', query: { agentId: sessions.agentId, sessionId: s.sessionId } })
}

function openCreate() { Object.assign(editor, { show: true, id: null, name: '', prompt: '' }) }
function openEdit(a) {
  editor.id = a.id; editor.name = a.name; editor.prompt = ''
  editor.show = true
  adminApi.agentDetail(a.id).then(res => {
    editor.prompt = res.data?.systemPrompt || res.data?.agentName || ''
  }).catch(() => {})
}
async function save() {
  if (!editor.name) { toast('请填写名称', 'error'); return }
  saving.value = true
  try {
    if (editor.id) await adminApi.updateAgent(editor.id, { agentName: editor.name, systemPrompt: editor.prompt })
    else await adminApi.createAgent({ agentName: editor.name, systemPrompt: editor.prompt })
    toast('已保存'); editor.show = false; load()
  } catch (e) { toast(e.msg || '保存失败', 'error') }
  finally { saving.value = false }
}
function remove(a) {
  askConfirm({
    title: '删除智能体', message: `确定删除「${a.name}」吗？`, danger: true,
    onOk: async () => {
      try { await adminApi.deleteAgent(a.id); toast('已删除'); load() }
      catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}

onMounted(load)
</script>

<style scoped>
.form-row { margin-bottom: 14px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row textarea {
  border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px;
  font-size: 14px; outline: none; font-family: var(--font);
}
.form-row input:focus, .form-row textarea:focus { border-color: var(--primary); }
</style>
