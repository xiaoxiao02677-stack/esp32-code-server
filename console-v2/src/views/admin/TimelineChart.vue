<template>
  <div>
    <div class="page-head">
      <div>
        <h1>时间线图表 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">可视化记忆条目随时间的分布趋势</p>
      </div>
      <div class="head-actions">
        <select v-model="days" class="mini-select" @change="load">
          <option value="7">近7天</option>
          <option value="30">近30天</option>
          <option value="90">近90天</option>
          <option value="365">近一年</option>
        </select>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="chart-container">
      <canvas ref="chartCanvas" width="800" height="400"></canvas>
    </div>

    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else-if="!data.labels.length" class="empty">暂无数据</div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { api } from '../../lib/api'

const chartCanvas = ref(null)
const loading = ref(false)
const error = ref('')
const days = ref(30)
const data = ref({ labels: [], counts: [] })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.get(`/memory/timeline/conversation.chatgpt/chart?days=${days.value}`)
    if (res.code === 0) {
      data.value = res.data
      drawChart()
    } else {
      error.value = res.msg || '加载失败'
    }
  } catch (e) {
    error.value = e.message || '网络错误'
  } finally {
    loading.value = false
  }
}

function drawChart() {
  const canvas = chartCanvas.value
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

  // 绘制柱状图
  counts.forEach((count, i) => {
    const x = padding.left + i * (barWidth + barGap)
    const barHeight = (count / maxCount) * chartHeight
    const y = padding.top + chartHeight - barHeight

    ctx.fillStyle = '#4F46E5'
    ctx.fillRect(x, y, barWidth, barHeight)

    // X轴标签
    ctx.fillStyle = '#666'
    ctx.font = '12px sans-serif'
    ctx.textAlign = 'center'
    if (labels.length <= 31 || i % 5 === 0) {
      ctx.fillText(labels[i], x + barWidth / 2, canvas.height - padding.bottom + 20)
    }

    // Y轴数值
    if (count > 0) {
      ctx.fillStyle = '#333'
      ctx.fillText(count.toString(), x + barWidth / 2, y - 5)
    }
  })

  // 坐标轴
  ctx.strokeStyle = '#ddd'
  ctx.beginPath()
  ctx.moveTo(padding.left, padding.top)
  ctx.lineTo(padding.left, padding.top + chartHeight)
  ctx.lineTo(padding.left + chartWidth, padding.top + chartHeight)
  ctx.stroke()
}

onMounted(load)
watch(days, load)
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
}
.loading, .error, .empty {
  text-align: center;
  padding: 40px;
  color: #666;
}
.error { color: #dc2626; }
</style>
