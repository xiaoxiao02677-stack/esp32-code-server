<template>
  <div>
    <div class="page-head">
      <div>
        <h1>记忆 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">契约对齐 /cc/：引擎配置 / 列表·时间轴·图谱三视图 / 审核编辑 / 信任度</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" :disabled="!currentAgentId" @click="creator.show = true">＋ 新增记忆</button>
        <button class="btn btn-primary btn-sm" :disabled="!currentAgentId || summarizing" :title="!currentAgentId ? '请先在下方选择智能体' : '用 LLM 总结该智能体近期对话并写入一条记忆'" @click="summarizeMemory">{{ summarizing ? '总结中…' : '⚡ 快速总结' }}</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <!-- 记忆引擎面板：每智能体独立选择四档引擎 -->
    <div class="bind-box">
      <div class="bind-label">🧠 记忆引擎（每智能体独立选择，切换后设备重连生效）</div>
      <div v-for="a in agents" :key="a.id" class="engine-row">
        <div class="engine-agent">
          <span class="engine-name">{{ a.name || '未命名' }}</span>
          <span class="badge" :class="engineBadgeClass(a.memModelId)">{{ engineZh(a.memModelId) }}</span>
        </div>
        <select class="engine-select" :value="a.memModelId || ''" @change="switchEngine(a, $event.target.value)">
          <option value="" disabled>选择引擎…</option>
          <option v-for="e in ENGINE_CHOICES" :key="e.id" :value="e.id">{{ e.label }}</option>
        </select>
      </div>
      <div v-if="!agents.length" class="field-hint">暂无智能体，请先到「智能体」页创建。</div>
      <p class="field-hint" style="margin-top:8px">
        短期总结=对话摘要轻量省token · 仅上报=只存聊天记录不做记忆 · Holographic=本地正则事实库零LLM成本 · 混合=短期总结+长期事实+LLM沉淀（推荐）
      </p>
    </div>

    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px">
      <div v-for="a in memoryAgents" :key="a.agent_id" class="chip" :class="{ active: currentAgentId === a.agent_id }" @click="selectMemAgent(a.agent_id)">
        {{ a.name || '未命名' }}（{{ a.fact_count }}条）
      </div>
    </div>

    <!-- 筛选工具条 + 三视图切换（契约同 cc-console mem-toolbar / mem-view-switch） -->
    <div class="mem-toolbar">
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
      <div class="mem-view-switch">
        <button class="mem-view-btn" :class="{ 'is-on': memViewMode === 'list' }" @click="switchMemView('list')">☰ 列表</button>
        <button class="mem-view-btn" :class="{ 'is-on': memViewMode === 'timeline' }" @click="switchMemView('timeline')">🕐 时间轴</button>
        <button class="mem-view-btn" :class="{ 'is-on': memViewMode === 'graph' }" @click="switchMemView('graph')">🕸 实体图谱</button>
      </div>
    </div>

    <DataTable title="记忆事实" :hint="factsHint">
      <!-- 时间轴视图（移植 cc-console MemoryTimeline：日期分组倒序 + 组内时间倒序） -->
      <div v-if="memViewMode === 'timeline'" class="mem-timeline-wrap">
        <div class="mem-timeline-track">
          <div v-for="group in memTimelineGroups" :key="group.date" class="mem-tl-group">
            <div class="mem-tl-date">
              <span class="mem-tl-date-dot"></span>
              <span class="mem-tl-date-text">{{ group.date }}</span>
              <span class="mem-tl-date-count">{{ group.items.length }}</span>
            </div>
            <div class="mem-tl-items">
              <div v-for="f in group.items" :key="f.fact_id" class="mem-tl-item" :class="'mem-tl-item--' + (f.category || 'general')">
                <div class="mem-tl-item-head">
                  <span class="mem-tl-cat">{{ catZh(f.category) }}</span>
                  <span class="mem-tl-time">{{ memTimeOf(f.created_at) }}</span>
                  <span v-if="f.trust_score != null" class="mem-tl-trust" :style="memTrustStyle(f.trust_score)">{{ Number(f.trust_score).toFixed(2) }}</span>
                  <span v-if="f.retrieval_count" class="mem-tl-rc">↺{{ f.retrieval_count }}</span>
                </div>
                <div class="mem-tl-content">{{ f.content }}</div>
              </div>
            </div>
          </div>
        </div>
        <div v-if="!facts.length" class="empty-state"><div class="empty-icon">🕐</div><strong>暂无记忆数据</strong></div>
      </div>

      <!-- 实体图谱视图（Canvas 手绘免 ECharts：实体聚合 → 环形布局 → 记忆小点连线） -->
      <div v-else-if="memViewMode === 'graph'" class="mem-graph-wrap">
        <canvas ref="memGraphCanvas" class="mem-graph-canvas" width="900" height="560"></canvas>
        <div class="mem-graph-legend">
          <span class="legend-item"><i class="dot dot--entity"></i>实体</span>
          <span class="legend-item"><i class="dot dot--fact"></i>记忆</span>
          <span class="legend-item"><i class="dot dot--hot"></i>高频实体</span>
        </div>
        <div v-if="!facts.length" class="empty-state"><div class="empty-icon">🕸</div><strong>暂无记忆数据</strong></div>
      </div>

      <!-- 列表视图 fact-card（信任度进度条 + 召回次数徽标） -->
      <template v-else>
        <div v-if="facts.length" class="fact-list">
          <div v-for="f in facts" :key="f.fact_id" class="fact-card">
            <div class="fact-top">
              <span class="fact-cat" :class="'fact-cat--' + (f.category || 'general')">{{ catZh(f.category) }}</span>
              <span v-if="f.status && f.status !== 'active'" class="fact-status">{{ f.status === 'rejected' ? '已驳回' : f.status }}</span>
              <span v-if="f.retrieval_count" class="fact-rc" title="被召回次数">↺{{ f.retrieval_count }}</span>
              <span class="fact-date">{{ f.created_at }}</span>
            </div>
            <div class="fact-content">{{ f.content }}</div>
            <div v-if="f.trust_score != null" class="fact-trust">
              <div class="trust-bar"><div class="trust-fill" :style="{ width: (Number(f.trust_score) * 100) + '%' }"></div></div>
              <span class="trust-num">信任 {{ Number(f.trust_score).toFixed(2) }}</span>
            </div>
            <div class="fact-actions">
              <button class="link-btn" @click="feedback(f, true)">👍 有用</button>
              <button class="link-btn" @click="feedback(f, false)">👎 没用</button>
              <button v-if="f.status !== 'active'" class="link-btn" @click="review(f, 'approve')">✓ 通过</button>
              <button v-else class="link-btn" @click="review(f, 'reject')">✕ 驳回</button>
              <button class="link-btn" @click="openFactEdit(f)">✎ 编辑</button>
              <button class="link-btn danger" @click="remove(f)">🗑 删除</button>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">
          <div class="empty-icon">🧠</div>
          <strong>还没有记忆，多聊聊天，它会自动记住你的喜好</strong>
        </div>
      </template>
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
import { computed, inject, nextTick, onMounted, reactive, ref } from 'vue'
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
const summarizing = ref(false)
const creator = reactive({ show: false, content: '' })
const factEditor = reactive({ show: false, factId: '', content: '', category: 'general' })

// 三视图（A1）：list | timeline | graph
const memViewMode = ref('list')
const memGraphCanvas = ref(null)

// 引擎面板：四档可选引擎（用户指定），切换走 PUT agent {memModelId}
const ENGINE_CHOICES = [
  { id: 'Memory_mem_hybrid', label: '混合记忆（短期+长期+LLM沉淀）', zh: '混合记忆', badge: 'badge-green' },
  { id: 'Memory_mem_holographic', label: 'Holographic 本地记忆（零LLM成本）', zh: 'Holographic', badge: 'badge-gray' },
  { id: 'Memory_mem_local_short', label: '短期总结（对话摘要）', zh: '短期总结', badge: 'badge-gray' },
  { id: 'Memory_mem_report_only', label: '仅上报聊天记录（不做记忆）', zh: '仅上报', badge: 'badge-gray' }
]
const engineSavingId = ref('')

function engineZh(id) {
  const hit = ENGINE_CHOICES.find(e => e.id === id)
  return hit ? hit.zh : (id ? '其他引擎' : '未设置')
}
function engineBadgeClass(id) {
  const hit = ENGINE_CHOICES.find(e => e.id === id)
  return hit ? hit.badge : 'badge-gray'
}
async function switchEngine(a, newEngineId) {
  if (!newEngineId || newEngineId === (a.memModelId || '') || engineSavingId.value) return
  engineSavingId.value = a.id
  try {
    const dres = await adminApi.agentDetail(a.id)
    const d = dres.data || {}
    await adminApi.updateAgent(a.id, {
      agentName: d.agentName || a.name,
      llmModelId: d.llmModelId,
      ttsModelId: d.ttsModelId,
      ttsVoiceId: d.ttsVoiceId,
      memModelId: newEngineId,
      intentModelId: d.intentModelId,
      asrModelId: d.asrModelId,
      chatHistoryConf: d.chatHistoryConf ?? 2,
      systemPrompt: d.systemPrompt,
      ttsRate: d.ttsRate ?? 0
    })
    a.memModelId = newEngineId
    toast(`「${a.name}」已切换为 ${engineZh(newEngineId)}，设备重连后生效`)
  } catch (e) { toast(e.msg || '切换失败', 'error') }
  finally { engineSavingId.value = '' }
}

const VIEW_ZH = { list: '卡片', timeline: '时间轴', graph: '实体图谱' }
const factsHint = computed(() => `${facts.value.length} 条 · ${VIEW_ZH[memViewMode.value] || ''}视图`)

// A1：时间轴分组（cc-console App.vue:1190-1204）——分组日期倒序、组内时间倒序
const memTimelineGroups = computed(() => {
  const map = new Map()
  const list = facts.value || []
  list.forEach(f => {
    const d = String(f.created_at || '').slice(0, 10) || '—'
    if (!map.has(d)) map.set(d, [])
    map.get(d).push(f)
  })
  return Array.from(map.entries())
    .sort((a, b) => (a[0] < b[0] ? 1 : -1))
    .map(([date, items]) => ({
      date,
      items: items.slice().sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
    }))
})

function catZh(c) {
  const map = { preference: '偏好', profile: '画像', habit: '习惯', event: '事件', general: '通用' }
  return map[c] || c
}

async function load() {
  loading.value = true
  try {
    // 记忆智能体（契约：{agent_id, name, fact_count}）
    const res = await adminApi.memoryAgents()
    memoryAgents.value = res.data || []
    if (!currentAgentId.value && memoryAgents.value.length) {
      currentAgentId.value = memoryAgents.value[0].agent_id
    }
    // 全量智能体（引擎面板行 + 引擎现状：memModelId 从列表接口取，缺失时从详情补）
    const ares = await adminApi.agentList()
    agents.value = (ares.data || []).map(a => ({
      id: a.id,
      name: a.agentName || a.name || '未命名',
      memModelId: a.memModelId || ''
    }))
    if (currentAgentId.value) await loadFacts()
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

async function loadFacts() {
  if (!currentAgentId.value) { facts.value = []; return }
  // 契约：?agent_id=&page=&size=&category=&status=（注意是 size 不是 limit）
  const qs = { agent_id: currentAgentId.value, page: 1, size: 50 }
  if (filterCategory.value) qs.category = filterCategory.value
  if (filterStatus.value) qs.status = filterStatus.value
  try {
    const res = await adminApi.memoryFacts(qs)
    facts.value = res.data?.list || []
  } catch (e) { toast(e.msg || '记忆加载失败', 'error'); facts.value = [] }
  // 图谱视图下数据刷新后重绘
  if (memViewMode.value === 'graph') nextTick(drawMemGraph)
}

function selectMemAgent(id) {
  currentAgentId.value = id
  loadFacts()
}

// ===== 三视图（A1，移植 cc-console App.vue:2220-2326） =====
function switchMemView(mode) {
  memViewMode.value = mode
  if (mode === 'graph') nextTick(drawMemGraph)
}

function memTimeOf(ts) {
  return String(ts || '').slice(11, 19) || ''
}

function memTrustStyle(v) {
  const n = Number(v)
  let color = '#a08e96'
  if (n >= 0.75) color = '#FF8FAB'
  else if (n >= 0.4) color = '#d98a2b'
  return { color, borderColor: color }
}

function drawMemGraph() {
  const canvas = memGraphCanvas.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const W = canvas.width, H = canvas.height
  ctx.clearRect(0, 0, W, H)
  const list = facts.value || []
  if (!list.length) return

  // 实体聚合（f.entities 数组；无实体归「未关联」）
  const entityMap = new Map()
  list.forEach(f => {
    const ents = Array.isArray(f.entities) && f.entities.length ? f.entities : []
    if (!ents.length) {
      const key = '__orphan__'
      if (!entityMap.has(key)) entityMap.set(key, { count: 0, facts: [], name: '未关联' })
      entityMap.get(key).count += 1
      entityMap.get(key).facts.push(f)
    }
    ents.forEach(e => {
      const name = typeof e === 'string' ? e : (e.name || String(e))
      if (!entityMap.has(name)) entityMap.set(name, { count: 0, facts: [], name })
      entityMap.get(name).count += 1
      entityMap.get(name).facts.push(f)
    })
  })

  const PALETTE = ['#FF8FAB', '#FFB6C6', '#FFD86B', '#9EE6D0', '#B8A9F5', '#8FC7FF', '#FFC3A0', '#A8E6CF']
  // 实体节点环形布局
  const entities = Array.from(entityMap.values())
  const cx = W / 2, cy = H / 2
  const R = Math.min(W, H) * 0.34
  const nodes = entities.map((e, i) => {
    const angle = (2 * Math.PI * i) / Math.max(entities.length, 1) - Math.PI / 2
    return {
      ...e,
      x: cx + R * Math.cos(angle),
      y: cy + R * Math.sin(angle),
      r: Math.min(16 + e.count * 5, 34),
      color: e.count >= 3 ? '#FF8FAB' : PALETTE[i % PALETTE.length],
      hot: e.count >= 3
    }
  })

  // 连线（实体→其记忆小点：布在实体外侧小圆）
  ctx.lineWidth = 1.2
  nodes.forEach(n => {
    n.facts.forEach((_, fi) => {
      const fa = Math.atan2(n.y - cy, n.x - cx)
      const fr = R + 60 + (fi % 4) * 26
      const fx = cx + fr * Math.cos(fa)
      const fy = cy + fr * Math.sin(fa)
      ctx.strokeStyle = 'rgba(180,150,170,0.35)'
      ctx.beginPath()
      ctx.moveTo(n.x, n.y)
      ctx.lineTo(fx, fy)
      ctx.stroke()
      // 记忆小点
      ctx.fillStyle = 'rgba(184,169,245,0.75)'
      ctx.beginPath()
      ctx.arc(fx, fy, 3.4, 0, 2 * Math.PI)
      ctx.fill()
    })
  })

  // 实体节点 + 标签 + 高频发光
  nodes.forEach(n => {
    if (n.hot) {
      ctx.shadowBlur = 14; ctx.shadowColor = 'rgba(255,143,171,0.5)'
    } else {
      ctx.shadowBlur = 5; ctx.shadowColor = 'rgba(255,143,171,0.25)'
    }
    ctx.fillStyle = n.color
    ctx.beginPath()
    ctx.arc(n.x, n.y, n.r, 0, 2 * Math.PI)
    ctx.fill()
    ctx.shadowBlur = 0
    ctx.strokeStyle = '#fff'
    ctx.lineWidth = 2
    ctx.stroke()
    // 标签
    ctx.fillStyle = '#4b3b44'
    ctx.font = '600 12px system-ui, sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(n.name.length > 10 ? n.name.slice(0, 10) + '…' : n.name, n.x, n.y + n.r + 14)
    ctx.fillStyle = '#a08e96'
    ctx.font = '10px system-ui, sans-serif'
    ctx.fillText(String(n.count), n.x, n.y + 4)
  })
}

// ===== 记忆 CRUD（契约对齐 cc-console） =====
async function createFact() {
  if (!currentAgentId.value) { toast('请先选择智能体', 'error'); return }
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
    if (res.data && res.data.trust_score !== undefined) f.trust_score = res.data.trust_score
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

// ===== 快速总结（契约：POST /memory/agents/{agentId}/summarize，返回总结文本或 {summary|content}） =====
function summarizeMemory() {
  if (!currentAgentId.value || summarizing.value) return
  askConfirm({
    title: '⚡ 快速总结',
    message: '将用 LLM 总结该智能体的近期对话并写入一条记忆（category=summary）。确定执行？',
    onOk: async () => {
      summarizing.value = true
      try {
        const res = await adminApi.memorySummarize(currentAgentId.value)
        const d = res?.data
        const brief = (typeof d === 'string' ? d
          : (d && typeof d === 'object' ? String(d.summary || d.content || '') : '')).slice(0, 40) || '完成'
        toast('总结已写入记忆：' + brief)
        await loadFacts()
      } catch (e) { toast(e.msg || '总结失败', 'error') }
      finally { summarizing.value = false }
    }
  })
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

onMounted(load)
</script>

<style scoped>
/* 快速总结按钮（小尺寸，对齐全局 .btn 设计令牌） */
.btn-sm { padding: 7px 16px; font-size: 13px; }
.chip { padding: 8px 16px; border-radius: 999px; background: var(--surface); border: 1.5px solid var(--border); cursor: pointer; font-size: 13px; }
.chip.active { border-color: var(--primary); color: var(--primary); font-weight: 600; }
.mini-select { border: 1.5px solid var(--border); border-radius: 10px; padding: 8px 12px; font-size: 13px; outline: none; background: #fff; }
.form-row { margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row textarea, .form-row select { border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px; font-size: 14px; outline: none; font-family: var(--font); background: #fff; }
.form-row input:focus, .form-row textarea:focus, .form-row select:focus { border-color: var(--primary); }
.field-hint { font-size: 11.5px; color: var(--text-sub); margin: 2px 0 0; }
.bind-box { border: 1.5px solid var(--border); border-radius: 16px; padding: 14px 16px; margin-bottom: 16px; background: var(--bg, #F8FAFD); }
.bind-label { font-size: 13px; font-weight: 700; margin-bottom: 10px; }

/* ===== 引擎面板：每智能体一行 ===== */
.engine-row { display: flex; align-items: center; gap: 12px; padding: 8px 0; border-bottom: 1px dashed var(--border); }
.engine-row:last-of-type { border-bottom: none; }
.engine-agent { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; }
.engine-name { font-size: 13.5px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.engine-select { border: 1.5px solid var(--border); border-radius: 10px; padding: 8px 12px; font-size: 13px; outline: none; background: var(--surface, #fff); color: var(--text); min-width: 240px; }
.engine-select:focus { border-color: var(--primary); }

/* ===== 工具条 + 三视图切换（移植 cc-console mem-toolbar / mem-view-switch） ===== */
.mem-toolbar { display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; align-items: center; }
.mem-view-switch { display: flex; gap: 6px; margin-left: auto; }
.mem-view-btn { border: 1.5px solid var(--border); background: var(--surface); color: var(--text-sub); border-radius: var(--radius-pill); padding: 7px 14px; font-size: 12.5px; font-weight: 600; cursor: pointer; }
.mem-view-btn:hover { border-color: var(--primary); color: var(--primary); }
.mem-view-btn.is-on { background: var(--primary); border-color: var(--primary); color: #fff; }

/* ===== 时间轴视图（移植 cc-console .mem-tl-*） ===== */
.mem-timeline-wrap { position: relative; max-height: 560px; overflow-y: auto; padding: 10px 12px; background: #FBFCFE; border: 1px solid var(--border); border-radius: var(--radius-md); }
.mem-timeline-track { position: relative; padding-left: 18px; }
.mem-timeline-track::before {
  content: ''; position: absolute; left: 6px; top: 8px; bottom: 8px; width: 3px;
  border-radius: 3px; background: linear-gradient(180deg, #FF8FAB, #FFD86B, #9EE6D0); opacity: 0.5;
}
.mem-tl-group { margin-bottom: 18px; }
.mem-tl-group:last-child { margin-bottom: 4px; }
.mem-tl-date { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.mem-tl-date-dot { width: 13px; height: 13px; border-radius: 50%; background: #fff; border: 3px solid #FF8FAB; box-shadow: 0 0 8px rgba(255,143,171,.5); flex-shrink: 0; }
.mem-tl-date-text { font-weight: 700; font-size: 13.5px; }
.mem-tl-date-count { font-size: 11.5px; background: #F0F2F6; color: var(--text-sub); border-radius: var(--radius-pill); padding: 1px 9px; }
.mem-tl-items { display: flex; flex-direction: column; gap: 8px; }
.mem-tl-item { background: var(--surface); border: 1px solid #E3E9F2; border-radius: 12px; padding: 10px 14px; }
.mem-tl-item--preference { border-left: 4px solid #FF8FAB; }
.mem-tl-item--profile { border-left: 4px solid #8FC7FF; }
.mem-tl-item--habit { border-left: 4px solid #FFD86B; }
.mem-tl-item--event { border-left: 4px solid #9EE6D0; }
.mem-tl-item--general { border-left: 4px solid #B8A9F5; }
.mem-tl-item-head { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; flex-wrap: wrap; }
.mem-tl-cat { font-size: 11.5px; font-weight: 600; background: #FFF0F5; color: var(--text-sub); border-radius: var(--radius-pill); padding: 2px 10px; }
.mem-tl-time { font-size: 11.5px; color: var(--text-sub); font-family: 'Menlo', 'Consolas', monospace; }
.mem-tl-trust { font-size: 11.5px; font-weight: 700; border: 1.5px solid; border-radius: var(--radius-pill); padding: 0 8px; line-height: 18px; }
.mem-tl-rc { font-size: 11.5px; color: #D96A1F; font-weight: 600; }
.mem-tl-content { font-size: 13px; line-height: 1.55; word-break: break-word; }

/* ===== 实体图谱视图（移植 cc-console .mem-graph-*，Canvas 手绘免 ECharts） ===== */
.mem-graph-wrap { background: #FBFCFE; border: 1px solid var(--border); border-radius: var(--radius-md); padding: 12px; position: relative; }
.mem-graph-canvas { width: 100%; height: auto; display: block; }
.mem-graph-legend { display: flex; gap: 14px; justify-content: center; padding-top: 8px; font-size: 12px; color: var(--text-sub); }
.legend-item { display: inline-flex; align-items: center; gap: 5px; }
.legend-item .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.dot--entity { background: #B8A9F5; }
.dot--fact { background: rgba(184,169,245,.75); }
.dot--hot { background: #FF8FAB; box-shadow: 0 0 6px rgba(255,143,171,.6); }

/* ===== 列表视图 fact-card（移植 cc-console .fact-*，适配 v2 设计令牌） ===== */
.fact-list { display: flex; flex-direction: column; gap: 12px; }
.fact-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 16px 18px; }
.fact-card:hover { border-color: #C9D6EA; }
.fact-top { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
.fact-cat { border-radius: var(--radius-pill); padding: 3px 12px; font-size: 12px; font-weight: 600; background: #fff3d6; color: #b8860b; }
.fact-cat--preference { background: #ffe3ec; color: #d0568b; }
.fact-cat--profile { background: #e3ecff; color: #5b7bd5; }
.fact-cat--habit { background: #dff5ef; color: #2d8a6b; }
.fact-cat--event { background: #f3efff; color: #8b6fd5; }
.fact-cat--general { background: #f5f0eb; color: #8a7a6d; }
.fact-status { font-size: 12px; color: #d05656; background: #ffe3e3; border-radius: var(--radius-pill); padding: 3px 10px; }
.fact-rc { font-size: 12px; font-weight: 600; color: #D96A1F; background: #FFF3EA; border-radius: var(--radius-pill); padding: 2px 9px; }
.fact-date { margin-left: auto; font-size: 12px; color: var(--text-sub); }
.fact-content { font-size: 14px; font-weight: 500; margin-bottom: 10px; line-height: 1.6; word-break: break-word; }
.fact-trust { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.trust-bar { flex: 1; max-width: 200px; height: 8px; border-radius: var(--radius-pill); background: var(--primary-soft); overflow: hidden; }
.trust-fill { height: 100%; border-radius: var(--radius-pill); background: linear-gradient(90deg, #FF8FAB, #F9A8D4); transition: width 0.4s; }
.trust-num { font-size: 12px; color: var(--text-sub); }
.fact-actions { display: flex; gap: 8px; flex-wrap: wrap; }
</style>
