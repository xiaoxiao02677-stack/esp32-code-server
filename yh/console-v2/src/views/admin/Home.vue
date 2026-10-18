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
        <StatCard icon="users" label="用户" :value="userTotal" :note="`本页 ${users.length}`" />
        <StatCard icon="bot" label="模板" :value="templateCount" note="智能体模板" />
        <StatCard icon="device" label="设备" :value="deviceTotal" :note="onlineText" />
        <StatCard icon="chat" label="会话数" :value="sessionTotal" note="首个智能体" />
      </div>
    </div>

    <DataTable title="设备清单" hint="全平台设备（GET /admin/device/all）" :total="deviceTotal" :page="1" :pages="1" :loading="loading">
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
        <div class="empty-icon"><YhIcon name="device" /></div>
        <strong>暂无设备</strong>
      </div>
    </DataTable>

    <div class="panel sessions-panel">
      <div class="panel-head">
        <h3>最近会话<span class="hint">首个智能体的最新对话</span></h3>
        <button class="btn btn-ghost" style="padding:6px 14px;font-size:12.5px" @click="router.push('/admin/chat')">查看全部</button>
      </div>
      <div v-if="recentSessions.length" class="sess-list">
        <button v-for="s in recentSessions" :key="s.id" class="sess-item" type="button" @click="router.push('/admin/chat')">
          <div class="cell-main">{{ s.title }}</div>
          <div class="cell-sub">{{ s.createdAt }} · {{ s.chatCount }} 条</div>
        </button>
      </div>
      <div v-else class="empty-state">
        <div class="empty-icon"><YhIcon name="chat" /></div>
        <strong>暂无会话，去跟设备说句话吧</strong>
      </div>
    </div>
  </div>
</template>

<script setup>
import YhIcon from '../../components/YhIcon.vue'
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
const sessionTotal = ref(0)
const recentSessions = ref([])
const loading = ref(false)

const onlineText = computed(() => `${devices.value.filter(d => d.online).length} 在线`)

// 归一化 MAC：与 Python 侧 _normalize_device_id 对齐（在线表按归一化 ID 匹配）
function normMac(s) {
  let v = String(s || '').trim().toLowerCase()
  if (v.startsWith('xiaozhi-')) v = v.slice(8)
  return v.replace(/[:\-]/g, '')
}

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
    adminApi.devicePage({ page: 1, limit: 20 }).then(async res => {
      const data = res.data || {}
      const list = data.list || []
      // 真实在线源：Python /api/wake-word/devices（WS ∪ 心跳），经 Java 代理
      let onlineSet = null
      try {
        const r = await adminApi.wakeWordDevices()
        onlineSet = new Set((r?.data?.devices || []).map(normMac).filter(Boolean))
      } catch { onlineSet = null }
      devices.value = list.map(d => ({
        id: d.id, macAddress: d.macAddress,
        name: d.deviceName || d.name || d.macAddress || '未命名设备',
        board: d.board || d.model || '—',
        appVersion: String(d.appVersion || '').replace(/^v/, '') || '—',
        bindUser: d.bindUsername || d.bindUser || null,
        online: onlineSet ? onlineSet.has(normMac(d.macAddress)) : false,
        lastActive: d.lastActiveTime ? String(d.lastActiveTime).slice(5, 16) : '—'
      }))
      deviceTotal.value = data.total ?? list.length
    }).catch(() => {}),
    adminApi.templateList().then(res => {
      const list = Array.isArray(res.data) ? res.data : (res.data?.list || [])
      templateCount.value = list.length
    }).catch(() => {}),
    adminApi.agentList().then(async res => {
      const agents = Array.isArray(res.data) ? res.data : (res.data?.list || [])
      await loadFirstAgentSessions(agents)
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
    ['会话总数', sessionTotal.value]
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
.sessions-panel { margin-top: 20px; }
.sess-list { display: flex; flex-direction: column; gap: 4px; padding: 8px 14px 16px; }
.sess-item {
  padding: 10px 12px; border-radius: 12px; cursor: pointer; transition: background .15s;
  border: none; background: none; font-family: var(--font); text-align: left; width: 100%;
}
.sess-item:hover { background: #F5F8FD; }
.sess-item:focus-visible { outline: 2px solid var(--primary); outline-offset: -2px; }
</style>
