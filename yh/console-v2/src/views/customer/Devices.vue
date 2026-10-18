<template>
  <div>
    <div class="page-head">
      <div>
        <h1>设备 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">绑定与查看你的设备</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" :disabled="loading" @click="load">{{ loading ? '加载中…' : '↻ 刷新' }}</button>
      </div>
    </div>

    <div class="hero-row">
      <div class="hero-blob" style="min-height:180px">
        <div>
          <div class="en">DEVICES / ONLINE</div>
          <h2>我的设备</h2>
          <p>圆屏 · 方屏 · 无屏全部支持</p>
        </div>
        <div class="blob-actions">
          <button class="btn btn-primary" @click="$router.push('/customer')">返回智能体</button>
        </div>
        <div class="blob-3d">📡</div>
      </div>
      <div class="stats-grid">
        <StatCard icon="device" label="设备总数" :value="devices.length" />
        <StatCard icon="plug" label="型号" :value="boardCount" note="设备板型" />
        <StatCard icon="bot" label="绑定智能体" :value="agentCount" />
        <StatCard icon="clock" label="最近连接" :value="lastConnected" note="最新活动" />
      </div>
    </div>

    <DataTable title="设备清单" :total="devices.length" :page="1" :pages="1" :loading="loading">
      <table class="data-table">
        <thead>
          <tr><th>设备信息</th><th>型号 / MAC</th><th>固件</th><th>绑定智能体</th><th>最近连接</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="d in devices" :key="d.id || d.macAddress">
            <td>
              <div class="cell-main">{{ d.alias || '未命名设备' }}</div>
              <div class="cell-sub">{{ d.deviceType || '未知类型' }}</div>
            </td>
            <td>
              <div>{{ d.board || '—' }}</div>
              <div class="cell-sub">{{ d.macAddress || '—' }}</div>
            </td>
            <td>{{ d.appVersion || '—' }}</td>
            <td>
              <span class="badge badge-blue"><span class="dot"></span>{{ d.agentName || '未绑定' }}</span>
            </td>
            <td style="color:var(--text-sub)">{{ d.lastSeen || '—' }}</td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="detail(d)">详情</button>
                <button class="link-btn danger" :disabled="unbinding" @click="unbind(d)">解绑</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="devices.length === 0" class="empty-state">
        <div class="empty-icon"><YhIcon name="device" /></div>
        <strong>暂无设备</strong>
        <p>还没有绑定任何设备，去创建智能体并绑定设备吧</p>
      </div>
    </DataTable>

    <!-- 设备详情弹窗（契约字段 UserShowDeviceListVO） -->
    <div v-if="showDetail" class="modal-mask" @click.self="showDetail = null">
      <div class="modal">
        <h3>设备详情</h3>
        <div class="form-row"><label>名称</label><input :value="showDetail.alias || '未命名设备'" readonly /></div>
        <div class="form-row"><label>MAC 地址</label><input :value="showDetail.macAddress || '—'" readonly /></div>
        <div class="form-row"><label>型号</label><input :value="showDetail.deviceType || '—'" readonly /></div>
        <div class="form-row"><label>板型</label><input :value="showDetail.board || '—'" readonly /></div>
        <div class="form-row"><label>固件版本</label><input :value="showDetail.appVersion || '—'" readonly /></div>
        <div class="form-row"><label>绑定智能体</label><input :value="showDetail.agentName || '未绑定'" readonly /></div>
        <div class="form-row"><label>绑定用户</label><input :value="showDetail.bindUserName || '—'" readonly /></div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showDetail = null">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import YhIcon from '../../components/YhIcon.vue'
import { computed, inject, onMounted, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { api, customerApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')

const devices = ref([])
const loading = ref(false)
const unbinding = ref(false)
const showDetail = ref(null)
let warned = false

const boardCount = computed(() => new Set(devices.value.map(d => d.board).filter(Boolean)).size)
const agentCount = computed(() => new Set(devices.value.map(d => d.agentName).filter(Boolean)).size)
const lastConnected = computed(() => {
  const times = devices.value.map(d => d.lastConnectedAtTimestamp).filter(t => t && !isNaN(Number(t)))
  if (!times.length) return '—'
  const latest = Math.max(...times.map(Number))
  return fmtTime(latest)
})

function fmtTime(ts) {
  const d = new Date(Number(ts))
  if (isNaN(d.getTime())) return '—'
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function fmtSeen(ts) {
  if (!ts) return '—'
  const t = Number(ts)
  if (!isNaN(t)) return fmtTime(t)
  const str = String(ts)
  return str.length >= 16 ? str.slice(5, 16) : str
}

async function load() {
  loading.value = true
  try {
    // 1. 拉取智能体列表；2. 对每个智能体 GET /device/bind/{agentId}；3. 按 id/macAddress 去重汇总
    const agentsRes = await customerApi.agentList()
    const agentList = agentsRes.data || []
    const agentNameMap = {}
    agentList.forEach(a => {
      const id = a.id || a.agentId
      if (id) agentNameMap[id] = a.agentName || a.name || '智能体'
    })
    const results = await Promise.all(
      agentList.map(a => customerApi.boundDevices(a.id || a.agentId).catch(() => ({ data: [] })))
    )
    const seen = new Set()
    const list = []
    agentList.forEach((a, i) => {
      const rows = results[i]?.data || []
      rows.forEach(d => {
        const key = d.id || d.macAddress
        if (!key || seen.has(key)) return
        seen.add(key)
        list.push({
          ...d,
          id: d.id,
          macAddress: d.macAddress || '',
          alias: d.alias || d.deviceName || '',
          appVersion: d.appVersion || '',
          deviceType: d.deviceType || '',
          board: d.board || '',
          agentName: d.agentName || agentNameMap[a.id || a.agentId] || '',
          lastSeen: fmtSeen(d.lastConnectedAtTimestamp || d.recentChatTime || d.createDate),
          lastConnectedAtTimestamp: d.lastConnectedAtTimestamp
        })
      })
    })
    devices.value = list
  } catch (e) {
    devices.value = []
    if (!warned) { warned = true; toast(e.msg || '设备列表加载失败', 'error') }
  } finally {
    loading.value = false
  }
}

function detail(d) {
  showDetail.value = d
}

function unbind(d) {
  askConfirm({
    title: '解绑设备',
    message: `确定解绑设备「${d.alias || d.macAddress}」吗？`,
    danger: true,
    okText: '解绑',
    onOk: async () => {
      unbinding.value = true
      try {
        // 契约：POST /device/unbind，body { deviceId }
        await api.post('/device/unbind', { deviceId: d.id })
        toast('已解绑')
        load()
      } catch (e) {
        toast(e.msg || '解绑失败', 'error')
      } finally {
        unbinding.value = false
      }
    }
  })
}

onMounted(load)
</script>

<style scoped>
.modal-mask { position: fixed; inset: 0; background: rgba(15,22,40,.45); display: grid; place-items: center; z-index: 100; }
.modal { background: #fff; border-radius: 20px; padding: 26px; width: min(440px, 92vw); box-shadow: 0 24px 60px rgba(0,0,0,.2); }
.modal h3 { font-size: 17px; margin-bottom: 18px; }
.form-row { margin-bottom: 14px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input {
  border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px;
  font-size: 14px; outline: none; font-family: var(--font); background: #F7F9FC;
}
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 6px; }
</style>
