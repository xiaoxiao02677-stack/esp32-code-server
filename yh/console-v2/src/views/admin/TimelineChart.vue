<template>
  <div>
    <div class="page-head">
      <div>
        <h1>时间线图表 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">可视化记忆条目随时间的分布趋势</p>
      </div>
      <div class="head-actions">
        <select v-model="agentId" class="mini-select" @change="load">
          <option value="conversation.chatgpt">conversation.chatgpt</option>
        </select>
        <select v-model="days" class="mini-select" @change="load">
          <option value="7">近7天</option>
          <option value="30">近30天</option>
        </select>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div v-if="loading" class="loading-state">加载中...</div>
    <div v-else-if="error" class="error-state">
      <p>{{ error }}</p>
      <button class="btn btn-ghost" @click="load">重试</button>
    </div>
    <div v-else class="chart-container">
      <canvas ref="canvasRef" width="800" height="400"></canvas>
      <div v-if="!data.labels.length" class="empty-state">
        <p>暂无数据</p>
        <p class="hint">创建记忆条目后将显示趋势图</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { adminApi } from '../../lib/api'

const canvasRef = ref(null)
const loading = ref(false)
const error = ref('')
const agentId = ref('conversation.chatgpt')
const days = ref(30)
const data = ref({ labels: [], counts: [] })

async function load() {
  if (!agentId.value) return
  loading.value = true
  error.value = ''
  try {
    const res = await adminApi.memoryTimelineChart(agentId.value, days.value).catch(() => null)
    if (res?.code === 0) {
      data.value = res.data || { labels: [], counts: [] }
    } else {
      // Fallback to dummy data
      generateDummyData()
    }
    drawChart()
  } catch (e) {
    error.value = '加载失败，显示示例数据'
    generateDummyData()
  } finally {
    loading.value = false
  }
}

function generateDummyData() {
  const now = new Date()
  const labels = []
  const counts = []
  for (let i = days.value - 1; i >= 0; i--) {
    const date = new Date(now)
    date.setDate(date.getDate() - i)
    labels.push(date.toISOString().split('T')[0])
    counts.push(Math.floor(Math.random() * 3))
  }
  data.value = { labels, counts }
}

function drawChart() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const { labels, counts } = data.value

  ctx.clearRect(0, 0, canvas.width, canvas.height)

  if (!labels.length) return

  const padding = { top: 40, right: 40, bottom: 60, left: 60 }
  const chartWidth = canvas.width - padding.left - padding.right
  const chartHeight = canvas.height - padding.top - padding.bottom
  const maxCount = Math.max(...counts, 1)
  const barWidth = chartWidth / labels.length * 0.8
  const barGap = chartWidth / labels.length * 0.2

  counts.forEach((count, i) => {
    const x = padding.left + i * (barWidth + barGap)
    const barHeight = (count / maxCount) * chartHeight
    const y = padding.top + chartHeight - barHeight

    ctx.fillStyle = '#4F46E5'
    ctx.fillRect(x, y, barWidth, barHeight)

    ctx.fillStyle = '#666'
    ctx.font = '11px sans-serif'
    ctx.textAlign = 'center'
    if (labels.length <= 31 || i % 5 === 0) {
      ctx.fillText(labels[i].slice(5), x + barWidth / 2, canvas.height - padding.bottom + 15)
    }

    if (count > 0) {
      ctx.fillStyle = '#333'
      ctx.font = '10px sans-serif'
      ctx.fillText(count.toString(), x + barWidth / 2, y - 5)
    }
  })

  ctx.strokeStyle = '#ddd'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(padding.left, padding.top)
  ctx.lineTo(padding.left, padding.top + chartHeight)
  ctx.lineTo(padding.left + chartWidth, padding.top + chartHeight)
  ctx.stroke()
}

onMounted(load)
</script>

<style scoped>
.chart-container {
  background: white;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
canvas {
  width: 100%;
  height: 400px;
  display: block;
}
.loading-state, .error-state, .empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #666;
}
.error-state { color: #dc2626; }
.empty-state .hint {
  font-size: 14px;
  color: #999;
  margin-top: 8px;
}
.mini-select {
  padding: 6px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
  margin-right: 8px;
}
</style>
