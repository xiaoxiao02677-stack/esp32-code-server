<template>
  <div>
    <div class="page-head">
      <div>
        <h1>记忆 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">迁移自 /cc/ 记忆页：记忆智能体 / 事实增删 / 反馈 / 审核</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="openCreate">＋ 新增记忆</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="🧠" label="记忆智能体" :value="memoryAgents.length" />
      <StatCard icon="📋" label="当前智能体记忆" :value="facts.length" :note="currentAgentName" />
      <StatCard icon="⚙️" label="记忆引擎" :value="memoryEngine || '—'" />
    </div>

    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px">
      <div v-for="a in memoryAgents" :key="a.agentId || a.id" class="chip" :class="{ active: currentAgentId === (a.agentId || a.id) }" @click="pickAgent(a)">
        {{ a.agentName || a.name || '未命名' }}
      </div>
    </div>

    <DataTable title="记忆事实">
      <table class="data-table">
        <thead><tr><th>内容</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="f in facts" :key="f.fact_id">
            <td><div class="cell-main">{{ f.content || f.fact }}</div><div class="cell-sub">{{ f.create_time || f.updated_at || '' }}</div></td>
            <td>
              <span class="badge" :class="f.status === 'approved' || f.reviewed ? 'badge-green' : 'badge-gray'">
                {{ f.status || (f.reviewed ? '已审核' : '待审核') }}
              </span>
            </td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="feedback(f, true)">👍</button>
                <button class="link-btn" @click="feedback(f, false)">👎</button>
                <button class="link-btn" @click="review(f, 'approve')">通过</button>
                <button class="link-btn danger" @click="remove(f)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="facts.length === 0" class="empty-state"><div class="empty-icon">🧠</div><strong>暂无记忆</strong></div>
    </DataTable>

    <!-- 新增弹窗 -->
    <div v-if="creator.show" class="modal-mask" @click.self="creator.show = false">
      <div class="modal">
        <h3>新增记忆</h3>
        <div class="form-row"><label>智能体</label>
          <select v-model="creator.agentId">
            <option v-for="a in memoryAgents" :key="a.agentId || a.id" :value="a.agentId || a.id">{{ a.agentName || a.name }}</option>
          </select>
        </div>
        <div class="form-row"><label>内容</label><textarea v-model="creator.content" rows="3" placeholder="例：用户喜欢在早上听新闻"></textarea></div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="creator.show = false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { inject, onMounted, reactive, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')
const memoryAgents = ref([])
const facts = ref([])
const currentAgentId = ref('')
const currentAgentName = ref('')
const memoryEngine = ref('')
const loading = ref(false)
const saving = ref(false)
const creator = reactive({ show: false, agentId: '', content: '' })

async function load() {
  loading.value = true
  try {
    const res = await adminApi.memoryAgents()
    const list = res.data?.list || res.data || []
    memoryAgents.value = list.map(a => ({
      agentId: a.agentId || a.id,
      agentName: a.agentName || a.name || '未命名',
      memoryEngine: a.memoryEngine || ''
    }))
    if (memoryAgents.value.length && !currentAgentId.value) {
      await pickAgent(memoryAgents.value[0])
    }
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

async function pickAgent(a) {
  currentAgentId.value = a.agentId
  currentAgentName.value = a.agentName
  memoryEngine.value = a.memoryEngine || ''
  try {
    // cc-console 契约：?agent_id=&page=&size=（非 limit）
    const res = await adminApi.memoryFacts({ agent_id: a.agentId, page: 1, size: 50 })
    const data = res.data || {}
    facts.value = data.list || data.facts || []
  } catch (e) { toast(e.msg || '记忆加载失败', 'error'); facts.value = [] }
}

function openCreate() {
  creator.agentId = currentAgentId.value
  creator.content = ''
  creator.show = true
}

async function save() {
  if (!creator.agentId || !creator.content) { toast('请选择智能体并填写内容', 'error'); return }
  saving.value = true
  try {
    await adminApi.createFact({ agent_id: creator.agentId, content: creator.content })
    toast('记忆已保存'); creator.show = false
    pickAgent({ agentId: creator.agentId, agentName: currentAgentName.value, memoryEngine: memoryEngine.value })
  } catch (e) { toast(e.msg || '保存失败', 'error') }
  finally { saving.value = false }
}

async function feedback(f, helpful) {
  try {
    await adminApi.factFeedback(f.fact_id, currentAgentId.value, helpful)
    toast(helpful ? '已反馈 👍' : '已反馈 👎')
  } catch (e) { toast(e.msg || '反馈失败', 'error') }
}

async function review(f, action) {
  try {
    await adminApi.factReview(f.fact_id, currentAgentId.value, action)
    toast('已审核通过')
    pickAgent({ agentId: currentAgentId.value, agentName: currentAgentName.value, memoryEngine: memoryEngine.value })
  } catch (e) { toast(e.msg || '审核失败', 'error') }
}

function remove(f) {
  askConfirm({
    title: '删除记忆', message: '确定删除此记忆吗？', danger: true,
    onOk: async () => {
      try { await adminApi.deleteFact(f.fact_id, currentAgentId.value); toast('已删除'); pickAgent({ agentId: currentAgentId.value, agentName: currentAgentName.value, memoryEngine: memoryEngine.value }) }
      catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}

onMounted(load)
</script>

<style scoped>
.chip { padding: 8px 16px; border-radius: 999px; background: var(--bg-card); border: 1.5px solid var(--border); cursor: pointer; font-size: 13px; }
.chip.active { border-color: var(--primary); color: var(--primary); font-weight: 600; }
.form-row { margin-bottom: 14px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row textarea, .form-row select {
  border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px; font-size: 14px; outline: none; font-family: var(--font);
}
.form-row input:focus, .form-row textarea:focus { border-color: var(--primary); }
</style>
