<template>
  <div>
    <div class="page-head">
      <div>
        <h1>平台 <span style="color:var(--primary)">概览</span></h1>
        <p class="sub">全局运营数据一览</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="exportReport">⬇ 导出报表</button>
        <button class="btn btn-ghost" @click="$router.push('/admin/users')">查看用户</button>
      </div>
    </div>

    <div class="hero-row">
      <div class="hero-blob">
        <div>
          <div class="en">ADMIN / OVERVIEW</div>
          <h2>运营总览</h2>
          <p>用户、设备、模板与记忆数据</p>
        </div>
        <div class="blob-actions">
          <button class="btn btn-primary" @click="$router.push('/admin/agents')">智能体管理</button>
          <button class="btn btn-ghost" @click="$router.push('/admin/devices')">设备</button>
          <button class="btn btn-ghost" @click="$router.push('/admin/chat')">聊天记录</button>
          <button class="btn btn-ghost" @click="$router.push('/admin/templates')">模板</button>
          <button class="btn btn-ghost" @click="$router.push('/admin/push-scheduler')">推送调度</button>
        </div>
        <div class="blob-3d">📊</div>
      </div>
      <div class="stats-grid">
        <StatCard icon="👥" label="用户" :value="userTotal" :note="`本页 ${users.length}`" />
        <StatCard icon="🤖" label="模板" :value="templateCount" note="智能体模板" />
        <StatCard icon="📡" label="设备" :value="deviceTotal" :note="onlineText" />
        <StatCard icon="🧠" label="记忆智能体" :value="memoryAgentCount" note="有记忆数据" />
        <StatCard icon="💬" label="会话数" :value="sessionTotal" note="首个智能体" />
        <StatCard icon="🔊" label="TTS 引擎数" :value="ttsModelCount" note="已接入" />
      </div>
    </div>

    <DataTable title="设备清单" hint="全平台设备（GET /admin/device/all）" :total="deviceTotal" :page="1" :pages="1">
      <template #actions>
        <button class="btn btn-ghost" style="padding:6px 14px;font-size:12.5px" @click="load" :disabled="loading">↻ 刷新</button>
      </template>
      <table class="data-table">
        <thead>
          <tr><th>设备</th><th>型号 / 固件</th><th>绑定用户</th><th>状态</th><th>最近活跃</th></tr>
        </thead>
        <tbody>
          <tr v-for="d in devices" :key="d.id || d.macAddress">
            <td>
              <div class="cell-main">{{ d.name }}</div>
              <div class="cell-sub">{{ d.macAddress }}</div>
            </td>
            <td>
              <div>{{ d.board }}</div>
              <div class="cell-sub">v{{ d.appVersion }}</div>
            </td>
            <td>{{ d.bindUser || '未绑定' }}</td>
            <td>
              <span class="badge" :class="d.online ? 'badge-green' : 'badge-gray'">
                <span class="dot"></span>{{ d.online ? '在线' : '离线' }}
              </span>
            </td>
            <td style="color:var(--text-sub)">{{ d.lastActive }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="devices.length === 0" class="empty-state">
        <div class="empty-icon">📡</div>
        <strong>暂无设备</strong>
      </div>
    </DataTable>

    <div class="panel sessions-panel">
      <div class="panel-head">
        <h3>最近会话<span class="hint">首个智能体的最新对话</span></h3>
        <button class="btn btn-ghost" style="padding:6px 14px;font-size:12.5px" @click="router.push('/admin/chat')">查看全部</button>
      </div>
      <div v-if="recentSessions.length" class="sess-list">
        <div v-for="s in recentSessions" :key="s.id" class="sess-item" @click="router.push('/admin/chat')">
          <div class="cell-main">{{ s.title }}</div>
          <div class="cell-sub">{{ s.createdAt }} · {{ s.chatCount }} 条</div>
        </div>
      </div>
      <div v-else class="empty-state">
        <div class="empty-icon">💬</div>
        <strong>暂无会话，去跟设备说句话吧</strong>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const router = useRouter()
const toast = inject('toast')

const users = ref([])
const userTotal = ref(0)
const devices = ref([])
const deviceTotal = ref(0)
const templateCount = ref(0)
const memoryAgentCount = ref(0)
const sessionTotal = ref(0)
const ttsModelCount = ref(0)
const recentSessions = ref([])
const loading = ref(false)

const onlineText = computed(() => `${devices.value.filter(d => d.online).length} 在线`)

// 契约对齐 cc-console loadSessions/loadTtsModels（原 1282-1306）
async function loadFirstAgentSessions(agents) {
  const first = agents[0]
  if (!first) return
  const res = await adminApi.agentSessions(first.id, { page: 1, limit: 10 })
  const data = res?.data || {}
  sessionTotal.value = data.total ?? 0
  recentSessions.value = (data.list || []).slice(0, 5).map(s => ({
    id: s.sessionId ?? s.id,
    title: s.title || '未命名会话',
    createdAt: s.createdAt ? String(s.createdAt).slice(0, 16).replace('T', ' ') : '—',
    chatCount: s.chatCount ?? 0
  }))
}

async function load() {
  loading.value = true
  const jobs = [
    adminApi.userPage({ page: 1, limit: 4 }).then(res => {
      const data = res.data || {}
      users.value = data.list || []
      userTotal.value = data.total ?? 0
    }).catch(() => {}),
    adminApi.devicePage({ page: 1, limit: 20 }).then(res => {
      const data = res.data || {}
      const list = data.list || []
      devices.value = list.map(d => ({
        id: d.id, macAddress: d.macAddress,
        name: d.deviceName || d.name || d.macAddress || '未命名设备',
        board: d.board || d.model || '—',
        appVersion: d.appVersion || '—',
        bindUser: d.bindUsername || d.bindUser || null,
        online: d.online ?? (d.status === 1),
        lastActive: d.lastActiveTime ? String(d.lastActiveTime).slice(5, 16) : '—'
      }))
      deviceTotal.value = data.total ?? list.length
    }).catch(() => {}),
    adminApi.templateList().then(res => {
      const list = Array.isArray(res.data) ? res.data : (res.data?.list || [])
      templateCount.value = list.length
    }).catch(() => {}),
    adminApi.memoryAgents().then(res => {
      const list = Array.isArray(res.data) ? res.data : (res.data?.list || [])
      memoryAgentCount.value = list.length
    }).catch(() => {}),
    adminApi.agentList().then(async res => {
      const agents = Array.isArray(res.data) ? res.data : (res.data?.list || [])
      await loadFirstAgentSessions(agents)
    }).catch(() => {}),
    adminApi.modelList('TTS').then(res => {
      const list = Array.isArray(res.data) ? res.data : (res.data?.list || [])
      ttsModelCount.value = list.length
    }).catch(() => {})
  ]
  await Promise.all(jobs)
  loading.value = false
}

function exportReport() {
  // 汇总当前真实数据为 CSV（纯前端导出，不动后端）
  const rows = [
    ['指标', '数值'],
    ['用户总数', userTotal.value],
    ['设备总数', deviceTotal.value],
    ['在线设备', devices.value.filter(d => d.online).length],
    ['模板数', templateCount.value],
    ['记忆智能体', memoryAgentCount.value],
    ['会话总数', sessionTotal.value],
    ['TTS 引擎数', ttsModelCount.value]
  ]
  const csv = '\uFEFF' + rows.map(r => r.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `admin-overview-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
  toast('报表已导出')
}

onMounted(load)
</script>

<style scoped>
/* 6 张统计卡：仅本页覆盖全局 4 列布局为 3 列两行 */
.stats-grid { grid-template-columns: repeat(3, 1fr); }
@media (max-width: 900px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
}
.sessions-panel { margin-top: 20px; }
.sess-list { display: flex; flex-direction: column; gap: 4px; padding: 8px 14px 16px; }
.sess-item { padding: 10px 12px; border-radius: 12px; cursor: pointer; transition: background .15s; }
.sess-item:hover { background: #F5F8FD; }
</style>
