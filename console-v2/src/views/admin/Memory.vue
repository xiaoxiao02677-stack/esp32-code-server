<template>
  <div>
    <div class="page-head">
      <div>
        <h1>记忆 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">契约对齐 /cc/：引擎配置 / 分类筛选 / 状态审核 / 编辑分类 / 信任度</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="creator.show = true">＋ 新增记忆</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <!-- 记忆引擎配置（契约对齐 cc-console applyMemoryEngine） -->
    <div class="bind-box">
      <div class="bind-label">🧠 记忆引擎（{{ memoryAgents.length }} 个智能体使用中）</div>
      <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end">
        <div class="form-row" style="flex:1;min-width:200px">
          <label>引擎</label>
          <select v-model="memoryEngine" @change="engineApplied = ''">
            <option v-for="m in engineOpts" :key="m.id" :value="m.id">{{ m.modelName }}</option>
          </select>
          <p v-if="engineHint" class="field-hint">{{ engineHint }}</p>
        </div>
        <div class="form-row" v-if="engineNeedsSummary" style="flex:1;min-width:200px">
          <label>总结 LLM（记忆压缩/事实沉淀用）</label>
          <select v-model="memorySummaryLlm">
            <option value="">跟随主 LLM</option>
            <option v-for="m in llmOpts" :key="m.id" :value="m.id">{{ m.modelName }}</option>
          </select>
          <p class="field-hint">独立于对话主脑：选便宜的模型做总结更省 token</p>
        </div>
        <div class="form-row" style="flex:1;min-width:220px">
          <label>应用到智能体</label>
          <select v-model="engineTargetAgentId">
            <option value="">选择智能体…</option>
            <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select>
        </div>
        <button class="btn btn-primary" :disabled="!engineTargetAgentId || !memoryEngine || engineSaving" @click="applyEngine">
          {{ engineSaving ? '应用中…' : '应用引擎配置' }}
        </button>
      </div>
      <p v-if="engineApplied" class="field-hint" style="color:#16a34a">{{ engineApplied }}</p>
    </div>

    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px">
      <div v-for="a in memoryAgents" :key="a.agent_id" class="chip" :class="{ active: currentAgentId === a.agent_id }" @click="selectMemAgent(a.agent_id)">
        {{ a.name || '未命名' }}（{{ a.fact_count }}条）
      </div>
    </div>

    <!-- 筛选工具条（契约：category/status query） -->
    <div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap">
      <select v-model="filterCategory" class="mini-select" @change="loadFacts">
        <option value="">全部分类</option>
        <option value="preference">偏好</option>
        <option value="profile">画像</option>
        <option value="habit">习惯</option>
        <option value="event">事件</option>
        <option value="general">通用</option>
      </select>
      <select v-model="filterStatus" class="mini-select" @change="loadFacts">
        <option value="">全部状态</option>
        <option value="active">生效中</option>
        <option value="rejected">已驳回</option>
      </select>
    </div>

    <DataTable title="记忆事实">
      <table class="data-table">
        <thead><tr><th>分类</th><th>内容</th><th>状态/信任</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="f in facts" :key="f.fact_id">
            <td><span class="badge badge-gray">{{ catZh(f.category) }}</span></td>
            <td>
              <div class="cell-main">{{ f.content }}</div>
              <div class="cell-sub">{{ f.created_at || '' }}</div>
            </td>
            <td>
              <span class="badge" :class="f.status === 'active' || f.status === undefined ? 'badge-green' : 'badge-gray'">
                {{ f.status === 'rejected' ? '已驳回' : '生效中' }}
              </span>
              <span v-if="f.trust_score !== undefined" class="cell-sub" style="margin-top:3px">信任 {{ Number(f.trust_score).toFixed(2) }}</span>
            </td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="feedback(f, true)">👍 有用</button>
                <button class="link-btn" @click="feedback(f, false)">👎 没用</button>
                <button v-if="f.status !== 'active'" class="link-btn" @click="review(f, 'approve')">✓ 通过</button>
                <button v-else class="link-btn" @click="review(f, 'reject')">✕ 驳回</button>
                <button class="link-btn" @click="openFactEdit(f)">✎ 编辑</button>
                <button class="link-btn danger" @click="remove(f)">🗑 删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="facts.length === 0" class="empty-state"><div class="empty-icon">🧠</div><strong>还没有记忆，多跟小智聊聊，它会自动记住你的喜好</strong></div>
    </DataTable>

    <!-- 新增记忆（契约：POST /memory/facts {agent_id, content}） -->
    <div v-if="creator.show" class="modal-mask" @click.self="creator.show = false">
      <div class="modal">
        <h3>新增记忆</h3>
        <div class="form-row"><label>内容</label><textarea v-model="creator.content" rows="3" maxlength="500" placeholder="例：用户喜欢在早上听新闻"></textarea></div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="creator.show = false">取消</button>
          <button class="btn btn-primary" :disabled="!creator.content" @click="createFact">保存</button>
        </div>
      </div>
    </div>

    <!-- 编辑记忆（契约：PUT /memory/facts/{id} {agent_id, content, category}） -->
    <div v-if="factEditor.show" class="modal-mask" @click.self="factEditor.show = false">
      <div class="modal">
        <h3>编辑记忆</h3>
        <p class="sub">内容变更会触发实体重抽取</p>
        <div class="form-row"><label>内容</label><textarea v-model="factEditor.content" rows="4" maxlength="500"></textarea></div>
        <div class="form-row"><label>分类</label>
          <select v-model="factEditor.category">
            <option value="preference">偏好</option>
            <option value="profile">画像</option>
            <option value="habit">习惯</option>
            <option value="event">事件</option>
            <option value="general">通用</option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="factEditor.show = false">取消</button>
          <button class="btn btn-primary" :disabled="!factEditor.content" @click="saveFactEdit">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, reactive, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')
const memoryAgents = ref([])
const agents = ref([])
const facts = ref([])
const currentAgentId = ref('')
const loading = ref(false)
const filterCategory = ref('')
const filterStatus = ref('')
const creator = reactive({ show: false, content: '' })
const factEditor = reactive({ show: false, factId: '', content: '', category: 'general' })

// 引擎配置（契约对齐 cc-console memoryEngine/applyMemoryEngine）
const memoryEngine = ref('')
const memorySummaryLlm = ref('')
const engineTargetAgentId = ref('')
const engineSaving = ref(false)
const engineApplied = ref('')
const engineOpts = ref([])
const llmOpts = ref([])

const ENGINE_HINTS = {
  Memory_mem_holographic: '本地全息记忆：自动抽取事实/时间线/实体，功能最全',
  Memory_mem_local_short: '短期记忆：对话摘要总结，轻量省 token',
  Memory_mem_report_only: '仅上报聊天记录，不生成记忆',
  Memory_nomem: '完全关闭记忆'
}
const engineHint = computed(() => ENGINE_HINTS[memoryEngine.value] || '')
const engineNeedsSummary = computed(() => memoryEngine.value === 'Memory_mem_hybrid' || memoryEngine.value === 'Memory_mem_local_short')

function catZh(c) {
  const map = { preference: '偏好', profile: '画像', habit: '习惯', event: '事件', general: '通用' }
  return map[c] || c
}

async function load() {
  loading.value = true
  try {
    // 引擎下拉数据源（契约：/models/names?modelType=Memory）
    const [memNames, llmNames] = await Promise.all([adminApi.modelNames('Memory'), adminApi.modelNames('LLM')])
    engineOpts.value = memNames.data || []
    llmOpts.value = llmNames.data || []
    if (!memoryEngine.value && engineOpts.value.length) memoryEngine.value = engineOpts.value[0].id

    // 记忆智能体（契约：{agent_id, name, fact_count}）
    const res = await adminApi.memoryAgents()
    memoryAgents.value = res.data || []
    if (!currentAgentId.value && memoryAgents.value.length) {
      currentAgentId.value = memoryAgents.value[0].agent_id
    }
    // 全量智能体（引擎应用目标）
    const ares = await adminApi.agentList()
    agents.value = (ares.data || []).map(a => ({ id: a.id, name: a.agentName || a.name || '未命名' }))
    if (currentAgentId.value) await loadFacts()
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

async function loadFacts() {
  if (!currentAgentId.value) { facts.value = []; return }
  // 契约：?agent_id=&page=&size=&category=&status=
  const qs = { agent_id: currentAgentId.value, page: 1, size: 50 }
  if (filterCategory.value) qs.category = filterCategory.value
  if (filterStatus.value) qs.status = filterStatus.value
  try {
    const res = await adminApi.memoryFacts(qs)
    facts.value = res.data?.list || []
  } catch (e) { toast(e.msg || '记忆加载失败', 'error'); facts.value = [] }
}

function selectMemAgent(id) {
  currentAgentId.value = id
  loadFacts()
}

async function createFact() {
  try {
    await adminApi.createFact(currentAgentId.value, creator.content)
    toast('已添加'); creator.show = false; creator.content = ''
    loadFacts()
  } catch (e) { toast(e.msg || '添加失败', 'error') }
}

function openFactEdit(f) {
  Object.assign(factEditor, { show: true, factId: f.fact_id, content: f.content, category: f.category || 'general' })
}

async function saveFactEdit() {
  try {
    await adminApi.updateFact(factEditor.factId, currentAgentId.value, factEditor.content, factEditor.category)
    toast('已保存'); factEditor.show = false; loadFacts()
  } catch (e) { toast(e.msg || '保存失败', 'error') }
}

async function feedback(f, helpful) {
  try {
    // 契约：返回新的 trust_score 就地更新
    const res = await adminApi.factFeedback(f.fact_id, currentAgentId.value, helpful)
    if (res.data?.trust_score) f.trust_score = res.data.trust_score
    toast(helpful ? '已反馈 👍' : '已反馈 👎')
  } catch (e) { toast(e.msg || '操作失败', 'error') }
}

async function review(f, action) {
  try {
    await adminApi.factReview(f.fact_id, currentAgentId.value, action)
    // 契约：approve→active，reject→rejected 就地更新
    f.status = action === 'approve' ? 'active' : 'rejected'
    toast(action === 'approve' ? '已通过' : '已驳回')
  } catch (e) { toast(e.msg || '操作失败', 'error') }
}

function remove(f) {
  askConfirm({
    title: '删除记忆', message: '确定删除这条记忆吗？不可恢复', danger: true,
    onOk: async () => {
      try { await adminApi.deleteFact(f.fact_id, currentAgentId.value); toast('已删除'); loadFacts() }
      catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}

// 契约对齐 cc-console applyMemoryEngine：改 memModelId + 更新模型 config.llm → PUT agent
async function applyEngine() {
  engineSaving.value = true
  engineApplied.value = ''
  try {
    const dres = await adminApi.agentDetail(engineTargetAgentId.value)
    const d = dres.data
    if (!d) { toast('拉取智能体详情失败', 'error'); return }
    if (engineNeedsSummary.value) {
      const cfgRes = await adminApi.modelDetail(memoryEngine.value)
      const cfg = cfgRes.data
      let rawConfig = cfg?.configJson || null
      if (rawConfig && typeof rawConfig === 'object') {
        rawConfig = { ...rawConfig, llm: memorySummaryLlm.value || rawConfig.llm }
        const providerCode = rawConfig.type || 'custom'
        await adminApi.updateModel('Memory', providerCode, memoryEngine.value, {
          modelName: cfg.modelName || memoryEngine.value,
          isDefault: cfg.isDefault || 0,
          isEnabled: cfg.isEnabled != null ? cfg.isEnabled : 1,
          configJson: rawConfig
        }).catch(e => console.warn('[memory-engine] 更新总结 LLM 失败', e.msg))
      }
    }
    await adminApi.updateAgent(engineTargetAgentId.value, {
      agentName: d.agentName,
      llmModelId: d.llmModelId,
      ttsModelId: d.ttsModelId,
      ttsVoiceId: d.ttsVoiceId,
      memModelId: memoryEngine.value,
      intentModelId: d.intentModelId,
      asrModelId: d.asrModelId,
      chatHistoryConf: d.chatHistoryConf ?? 2,
      systemPrompt: d.systemPrompt,
      ttsRate: d.ttsRate ?? 0
    })
    engineApplied.value = '✅ 已应用到「' + (agents.value.find(a => a.id === engineTargetAgentId.value)?.name || engineTargetAgentId.value) + '」'
    toast('引擎配置已应用')
  } catch (e) { toast(e.msg || '应用失败', 'error') }
  finally { engineSaving.value = false }
}

onMounted(load)
</script>

<style scoped>
.chip { padding: 8px 16px; border-radius: 999px; background: var(--bg-card); border: 1.5px solid var(--border); cursor: pointer; font-size: 13px; }
.chip.active { border-color: var(--primary); color: var(--primary); font-weight: 600; }
.mini-select { border: 1.5px solid var(--border); border-radius: 10px; padding: 8px 12px; font-size: 13px; outline: none; background: #fff; }
.form-row { margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row textarea, .form-row select { border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px; font-size: 14px; outline: none; font-family: var(--font); background: #fff; }
.form-row input:focus, .form-row textarea:focus, .form-row select:focus { border-color: var(--primary); }
.field-hint { font-size: 11.5px; color: var(--text-sub); margin: 2px 0 0; }
.bind-box { border: 1.5px solid var(--border); border-radius: 16px; padding: 14px 16px; margin-bottom: 16px; background: var(--bg-soft, #F8FAFD); }
.bind-label { font-size: 13px; font-weight: 700; margin-bottom: 10px; }
</style>
