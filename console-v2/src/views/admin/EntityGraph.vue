<template>
  <div>
    <div class="page-head">
      <div>
        <h1>实体图谱 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">可视化智能体记忆中的实体及其关系</p>
      </div>
      <div class="head-actions">
        <select v-model="agentId" class="mini-select" @change="load">
          <option value="" disabled>选择智能体</option>
          <option value="conversation.chatgpt">conversation.chatgpt</option>
        </select>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div v-if="loading" class="loading-state">加载中...</div>
    <div v-else-if="error" class="error-state">
      <p>{{ error }}</p>
      <button class="btn btn-ghost" @click="load">重试</button>
    </div>
    <div v-else class="graph-container">
      <canvas ref="canvasRef" width="800" height="500"></canvas>
      <div v-if="!entities.length" class="empty-state">
        <p>暂无实体数据</p>
        <p class="hint">创建记忆条目后自动提取实体</p>
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
const entities = ref([])

const typeColors = {
  person: '#FF6B9D',
  organization: '#4ECDC4',
  location: '#95E1D3',
  concept: '#F38181',
  default: '#A8A8A8'
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
  if (!canvas || !entities.value.length) return
  
  const ctx = canvas.getContext('2d')
  const width = canvas.width
  const height = canvas.height
  const centerX = width / 2
  const centerY = height / 2
  const radius = Math.min(width, height) * 0.35
  
  ctx.clearRect(0, 0, width, height)
  
  entities.value.forEach((entity, i) => {
    const angle = (i / entities.value.length) * 2 * Math.PI - Math.PI / 2
    const x = centerX + radius * Math.cos(angle)
    const y = centerY + radius * Math.sin(angle)
    
    ctx.beginPath()
    ctx.arc(x, y, 20, 0, 2 * Math.PI)
    ctx.fillStyle = typeColors[entity.type] || typeColors.default
    ctx.fill()
    ctx.strokeStyle = '#fff'
    ctx.lineWidth = 2
    ctx.stroke()
    
    ctx.fillStyle = '#333'
    ctx.font = '12px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(entity.name || '未知', x, y + 35)
    
    entity._x = x
    entity._y = y
  })
}

onMounted(load)
</script>

<style scoped>
.graph-container {
  background: white;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
canvas {
  width: 100%;
  height: 500px;
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
