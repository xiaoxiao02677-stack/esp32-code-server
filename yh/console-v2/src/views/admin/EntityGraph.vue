<template>
  <div>
    <div class="page-head">
      <div>
        <h1>实体图谱</h1>
        <p class="sub">可视化智能体记忆中的实体及其关系</p>
      </div>
      <div class="head-actions">
        <select v-model="agentId" class="mini-select" @change="load">
          <option value="" disabled>选择智能体</option>
          <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.name }}</option>
        </select>
        <button class="btn btn-ghost" @click="load" :disabled="loading || !agentId">↻ 刷新</button>
      </div>
    </div>

    <div v-if="loading" class="state-hint">加载中…</div>
    <div v-else-if="error" class="state-hint err">
      <p>{{ error }}</p>
      <button class="btn btn-ghost" @click="load">重试</button>
    </div>
    <div v-else-if="!agentId" class="state-hint">请先选择一个智能体</div>
    <div v-else class="graph-container panel">
      <canvas ref="canvasRef"></canvas>
      <div v-if="!entities.length" class="state-hint">
        <strong>暂无实体数据</strong>
        <p class="hint">创建记忆条目后自动提取实体</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { adminApi } from '../../lib/api'

const canvasRef = ref(null)
const loading = ref(false)
const error = ref('')
const agents = ref([])
const agentId = ref('')
const entities = ref([])

// 实体类型配色（浅色底上可读；描边/文字颜色取主题 token，随深色模式自适应）
const typeColors = {
  person: '#E8618C',
  organization: '#2FA79B',
  location: '#4C86C6',
  concept: '#C77700',
  default: '#8A94A6'
}

function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

async function loadAgents() {
  try {
    const res = await adminApi.agentList()
    const list = Array.isArray(res.data) ? res.data : (res.data?.list || [])
    agents.value = list.map(a => ({ id: a.id || a.agentId, name: a.agentName || a.name || '未命名' }))
    if (agents.value.length && !agentId.value) {
      agentId.value = agents.value[0].id
      load()
    }
  } catch { /* 下拉为空时提示选择 */ }
}

async function load() {
  if (!agentId.value) return
  loading.value = true
  error.value = ''
  try {
    const res = await adminApi.memoryEntities(agentId.value)
    if (res.code === 0) {
      entities.value = res.data?.entities || []
      drawGraph()
    } else {
      error.value = res.msg || '加载失败'
    }
  } catch (e) {
    error.value = e.message || '网络错误'
  } finally {
    loading.value = false
  }
}

function drawGraph() {
  const canvas = canvasRef.value
  if (!canvas) return

  // DPR 适配：canvas 物理像素 = CSS 尺寸 × devicePixelRatio，绘制坐标仍用 CSS 像素
  const dpr = window.devicePixelRatio || 1
  const cssW = canvas.clientWidth || 800
  const cssH = 500
  canvas.width = Math.round(cssW * dpr)
  canvas.height = Math.round(cssH * dpr)
  const ctx = canvas.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, cssW, cssH)

  if (!entities.value.length) return

  const textColor = cssVar('--text', '#1F2733')
  const surface = cssVar('--surface', '#fff')
  const border = cssVar('--border', '#E4E9F2')

  const centerX = cssW / 2
  const centerY = cssH / 2
  const radius = Math.min(cssW, cssH) * 0.36

  // hub：中心智能体节点
  ctx.beginPath()
  ctx.arc(centerX, centerY, 30, 0, 2 * Math.PI)
  ctx.fillStyle = cssVar('--primary', '#1B6CFF')
  ctx.fill()
  ctx.fillStyle = '#fff'
  ctx.font = '600 11px sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText('智能体', centerX, centerY)

  // spoke：环绕实体 + hub-spoke 连线
  entities.value.forEach((entity, i) => {
    const angle = (i / entities.value.length) * 2 * Math.PI - Math.PI / 2
    const x = centerX + radius * Math.cos(angle)
    const y = centerY + radius * Math.sin(angle)

    ctx.beginPath()
    ctx.moveTo(centerX, centerY)
    ctx.lineTo(x, y)
    ctx.strokeStyle = border
    ctx.lineWidth = 1.5
    ctx.stroke()

    ctx.beginPath()
    ctx.arc(x, y, 20, 0, 2 * Math.PI)
    ctx.fillStyle = typeColors[entity.type] || typeColors.default
    ctx.fill()
    ctx.strokeStyle = surface
    ctx.lineWidth = 2
    ctx.stroke()

    ctx.fillStyle = textColor
    ctx.font = '12px sans-serif'
    ctx.textBaseline = 'alphabetic'
    const label = entity.name || '未知'
    ctx.fillText(label.length > 10 ? label.slice(0, 10) + '…' : label, x, y + 35)

    entity._x = x
    entity._y = y
  })
}

function onResize() { if (!loading.value && !error.value) drawGraph() }

onMounted(() => {
  loadAgents()
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => window.removeEventListener('resize', onResize))
</script>

<style scoped>
.graph-container { position: relative; }
canvas { width: 100%; height: 500px; display: block; }
.state-hint { text-align: center; padding: 60px 20px; color: var(--text-sub); }
.state-hint.err { color: var(--danger); }
.state-hint .hint { font-size: 12.5px; color: var(--text-sub); margin-top: 8px; }
.mini-select {
  padding: 8px 14px; border: 1.5px solid var(--border); border-radius: 10px;
  font-size: 13px; font-family: var(--font); background: var(--surface); color: var(--text);
}
.mini-select:focus { border-color: var(--primary); outline: none; }
</style>
