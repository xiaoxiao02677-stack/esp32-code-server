<template>
  <div>
    <div class="page-head">
      <div>
        <h1>时间线图表</h1>
        <p class="sub">可视化记忆条目随时间的分布趋势</p>
      </div>
      <div class="head-actions">
        <select v-model="agentId" class="mini-select" @change="load">
          <option value="" disabled>选择智能体</option>
          <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.name }}</option>
        </select>
        <select v-model="days" class="mini-select" @change="load">
          <option value="7">近7天</option>
          <option value="30">近30天</option>
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
    <div v-else class="chart-container panel">
      <canvas ref="canvasRef"></canvas>
      <div v-if="!data.labels.length" class="state-hint">
        <strong>暂无数据</strong>
        <p class="hint">创建记忆条目后将显示趋势图</p>
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
const days = ref(30)
const data = ref({ labels: [], counts: [] })

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
    const res = await adminApi.memoryTimelineChart(agentId.value, days.value)
    if (res?.code === 0) {
      const d = res.data || { labels: [], counts: [] }
      data.value = { labels: d.labels || [], counts: (d.counts || []).map(n => Number(n) || 0) }
      drawChart()
    } else {
      error.value = res?.msg || '加载失败'
    }
  } catch (e) {
    error.value = e.msg || e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function drawChart() {
  const canvas = canvasRef.value
  if (!canvas) return

  // DPR 适配：canvas 物理像素 = CSS 尺寸 × devicePixelRatio，绘制坐标仍用 CSS 像素
  const dpr = window.devicePixelRatio || 1
  const cssW = canvas.clientWidth || 800
  const cssH = 400
  canvas.width = Math.round(cssW * dpr)
  canvas.height = Math.round(cssH * dpr)
  const ctx = canvas.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, cssW, cssH)

  const { labels, counts } = data.value
  if (!labels.length) return

  const primary = cssVar('--primary', '#1B6CFF')
  const textColor = cssVar('--text', '#1F2733')
  const subColor = cssVar('--text-sub', '#6B7686')
  const border = cssVar('--border', '#E4E9F2')

  const padding = { top: 40, right: 40, bottom: 60, left: 60 }
  const chartWidth = cssW - padding.left - padding.right
  const chartHeight = cssH - padding.top - padding.bottom
  const maxCount = Math.max(...counts, 1)
  const slot = chartWidth / labels.length
  const barWidth = slot * 0.8

  // Y 轴网格线 + 刻度
  ctx.strokeStyle = border
  ctx.lineWidth = 1
  ctx.fillStyle = subColor
  ctx.font = '11px sans-serif'
  ctx.textAlign = 'right'
  const yTicks = 4
  for (let i = 0; i <= yTicks; i++) {
    const val = Math.round((maxCount / yTicks) * i)
    const y = padding.top + chartHeight - (val / maxCount) * chartHeight
    if (i > 0) {
      ctx.beginPath()
      ctx.moveTo(padding.left, y)
      ctx.lineTo(padding.left + chartWidth, y)
      ctx.stroke()
    }
    ctx.fillText(String(val), padding.left - 8, y + 4)
  }

  counts.forEach((count, i) => {
    const x = padding.left + i * slot + (slot - barWidth) / 2
    const barHeight = (count / maxCount) * chartHeight
    const y = padding.top + chartHeight - barHeight

    ctx.fillStyle = count > 0 ? primary : border
    ctx.beginPath()
    // 顶部圆角柱
    const r = Math.min(4, barWidth / 2, barHeight)
    ctx.moveTo(x, cssH - padding.bottom)
    ctx.lineTo(x, y + r)
    ctx.arc(x + r, y + r, r, Math.PI, 1.5 * Math.PI)
    ctx.lineTo(x + barWidth - r, y)
    ctx.arc(x + barWidth - r, y + r, r, 1.5 * Math.PI, 2 * Math.PI)
    ctx.lineTo(x + barWidth, cssH - padding.bottom)
    ctx.closePath()
    ctx.fill()

    ctx.fillStyle = subColor
    ctx.font = '11px sans-serif'
    ctx.textAlign = 'center'
    if (labels.length <= 14 || i % 5 === 0 || i === labels.length - 1) {
      ctx.fillText(String(labels[i]).slice(5), x + barWidth / 2, cssH - padding.bottom + 16)
    }

    if (count > 0) {
      ctx.fillStyle = textColor
      ctx.font = '600 10px sans-serif'
      ctx.fillText(String(count), x + barWidth / 2, y - 6)
    }
  })

  // 坐标轴
  ctx.strokeStyle = subColor
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(padding.left, padding.top)
  ctx.lineTo(padding.left, padding.top + chartHeight)
  ctx.lineTo(padding.left + chartWidth, padding.top + chartHeight)
  ctx.stroke()
}

function onResize() { if (!loading.value && !error.value) drawChart() }

onMounted(() => {
  loadAgents()
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => window.removeEventListener('resize', onResize))
</script>

<style scoped>
.chart-container { position: relative; }
canvas { width: 100%; height: 400px; display: block; }
.state-hint { text-align: center; padding: 60px 20px; color: var(--text-sub); }
.state-hint.err { color: var(--danger); }
.state-hint .hint { font-size: 12.5px; color: var(--text-sub); margin-top: 8px; }
.mini-select {
  padding: 8px 14px; border: 1.5px solid var(--border); border-radius: 10px;
  font-size: 13px; font-family: var(--font); background: var(--surface); color: var(--text);
}
.mini-select:focus { border-color: var(--primary); outline: none; }

/* 移动端：时间线画布降高 */
@media (max-width: 768px) {
  canvas { height: 320px; }
}
</style>
