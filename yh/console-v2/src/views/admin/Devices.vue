<template>
  <div>
    <div class="page-head">
      <div>
        <h1>设备 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">你的设备状态（改名 / 绑定 / 解绑）</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="manual.show = true">＋ 手动添加</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="device" label="设备总数" :value="total" />
      <StatCard icon="dot" label="在线" :value="devices.filter(d => d.online).length" />
      <StatCard icon="link" label="已绑定智能体" :value="devices.filter(d => d.agentId).length" />
    </div>

    <DataTable title="设备列表" :total="total" :pages="pages" v-model:page="page" v-model:pageSize="pageSize" :loading="loading">
      <table class="data-table">
        <thead><tr><th>设备</th><th>MAC / IP</th><th>智能体</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="d in devices" :key="d.id">
            <td><div class="cell-main">{{ d.name }}</div><div class="cell-sub">{{ d.lastSeen || d.updateDate || '' }}</div></td>
            <td style="font-size:12px">{{ d.mac || '—' }}<template v-if="d.ip"><br />{{ d.ip }}</template></td>
            <td>{{ d.agentName || d.agentId || '—' }}</td>
            <td>
              <span class="badge" :class="d.online ? 'badge-green' : 'badge-gray'">
                <span class="dot"></span>{{ d.online ? '在线' : '离线' }}
              </span>
            </td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="openRename(d)">✎ 改名</button>
                <button class="link-btn" @click="openOta(d)">⬆ OTA</button>
                <button class="link-btn" @click="openBind(d)">⇄ 绑定</button>
                <button class="link-btn danger" @click="unbind(d)">⤫ 解绑</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="devices.length === 0" class="empty-state"><div class="empty-icon"><YhIcon name="device" /></div><strong>暂无设备</strong></div>
    </DataTable>

    <!-- 改名弹窗 -->
    <div v-if="rename.show" class="modal-mask" @click.self="rename.show = false">
      <div class="modal">
        <h3>设备改名</h3>
        <div class="form-row"><label>新名称</label><input v-model="rename.name" /></div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="rename.show = false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="doRename">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>

    <!-- 绑定智能体弹窗 -->
    <div v-if="bind.show" class="modal-mask" @click.self="bind.show = false">
      <div class="modal">
        <h3>绑定智能体</h3>
        <p class="bind-sub">{{ bind.device.name }} → 选择要绑定的智能体</p>
        <div class="form-row">
          <label>智能体</label>
          <select v-model="bind.agentId">
            <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="bind.show = false">取消</button>
          <button class="btn btn-primary" :disabled="!bind.agentId || saving" @click="doBind">{{ saving ? '绑定中…' : '绑定' }}</button>
        </div>
      </div>
    </div>

    <!-- OTA 定向配置弹窗 -->
    <div v-if="ota.show" class="modal-mask" @click.self="ota.show = false">
      <div class="modal">
        <h3>OTA 定向配置</h3>
        <p class="bind-sub">{{ ota.device.name }}（{{ ota.device.mac }}）· 当前版本 {{ ota.device.appVersion || '未知' }} / 轨道 {{ ota.device.board || '未知' }}</p>

        <div class="form-row">
          <label>单台指定固件（优先级最高，升级到位后自动解除）</label>
          <select v-model="ota.targetOtaId">
            <option value="">不指定（按轨道自动更新）</option>
            <option v-for="f in ota.firmwares" :key="f.id" :value="f.id">
              {{ f.firmwareName }} · {{ f.type }} · v{{ f.version }}
            </option>
          </select>
        </div>

        <div class="form-row">
          <label>主题轨道（autoUpdate 开启时按此轨道更新；与设备当前主题不同会强制切换）</label>
          <select v-model="ota.otaType">
            <option value="">跟随设备上报（默认）</option>
            <option v-for="t in ota.tracks" :key="t" :value="t">{{ t }}</option>
          </select>
        </div>

        <p class="ota-hint">
          单台指定用于把这一台设备切到任意固件（含跨主题）；主题轨道用于让它持续跟随某条轨道自动更新。
          两者都设置时单台指定优先，完成后再走轨道。
        </p>

        <div class="modal-actions">
          <button class="btn btn-ghost" @click="ota.show = false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="doOtaTarget">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>

    <!-- 手动添加弹窗 -->
    <div v-if="manual.show" class="modal-mask" @click.self="manual.show = false">
      <div class="modal">
        <h3>手动添加设备</h3>
        <div class="form-row"><label>MAC 地址</label><input v-model="manual.mac" placeholder="AA:BB:CC:DD:EE:FF" /></div>
        <div class="form-row"><label>设备名称（可选）</label><input v-model="manual.name" /></div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="manual.show = false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="doManualAdd">{{ saving ? '添加中…' : '添加' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import YhIcon from '../../components/YhIcon.vue'
import { inject, onMounted, reactive, ref, watch } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi, api } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')
const devices = ref([])
const agents = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const pages = ref(1)
const loading = ref(false)
const saving = ref(false)
const rename = reactive({ show: false, id: null, name: '' })
const bind = reactive({ show: false, device: null, agentId: '' })
const manual = reactive({ show: false, mac: '', name: '' })
const ota = reactive({ show: false, device: null, targetOtaId: '', otaType: '', firmwares: [], tracks: [] })

async function load() {
  loading.value = true
  try {
    // 管理员视角全量设备列表（分页）+ 真实在线设备并行拉取
    const [res, onlineSet] = await Promise.all([
      adminApi.devicePage({ page: page.value, limit: pageSize.value }),
      loadOnlineSet()
    ])
    const data = res.data || {}
    devices.value = (data.list || data || []).map(d => normalize(d, onlineSet))
    total.value = data.total ?? devices.value.length
  } catch (e) {
    // 降级：绑定视角 —— 取第一个智能体再查其绑定设备（原控制台 loadDevices 思路）
    try {
      const agentRes = await adminApi.agentList()
      const agentId = (agentRes.data || [])[0] && (agentRes.data || [])[0].id
      if (!agentId) { devices.value = []; total.value = 0 }
      else {
        const [res, onlineSet] = await Promise.all([
          adminApi.boundDevices(agentId),
          loadOnlineSet()
        ])
        devices.value = (((res.data || {}).list || res.data || [])).map(d => normalize(d, onlineSet))
        total.value = devices.value.length
      }
      page.value = 1
      if (agents.value.length === 0) agents.value = (agentRes.data || []).map(a => ({ id: a.id, name: a.agentName || a.name || '未命名' }))
    } catch (e2) {
      toast(e2.msg || e.msg || '加载失败', 'error')
    }
  } finally {
    pages.value = Math.max(1, Math.ceil(total.value / pageSize.value))
    loading.value = false
  }
}

// 归一化 MAC：与 Python 侧 _normalize_device_id 对齐（心跳/WS 在线表按归一化 ID 匹配）
function normMac(s) {
  let v = String(s || '').trim().toLowerCase()
  if (v.startsWith('yuhe-')) v = v.slice(8)
  return v.replace(/[:\-]/g, '')
}

// 真实在线源：Python /api/wake-word/devices（WS 连接 ∪ 心跳在线），经 Java 代理。
// 原先用 !!lastConnectedAtTimestamp 兜底会把「曾经连过」的设备全判在线（误报）
async function loadOnlineSet() {
  try {
    const res = await adminApi.wakeWordDevices()
    const list = res?.data?.devices || []
    return new Set(list.map(normMac).filter(Boolean))
  } catch {
    return null // 通道失败时返回 null，normalize 保持不显示在线
  }
}

function normalize(d, onlineSet) {
  const mac = d.macAddress || d.mac || d.id
  return {
    id: d.id || d.macAddress,
    name: d.alias || d.name || d.deviceName || (d.macAddress ? '设备 ' + d.macAddress.slice(-5) : '未命名'),
    mac,
    ip: d.ip || '',
    agentId: d.agentId,
    agentName: d.agentName || d.bindUserName,
    online: onlineSet ? onlineSet.has(normMac(mac)) : false,
    lastSeen: d.recentChatTime || d.lastSeen || d.updateDate,
    appVersion: d.appVersion || '',
    board: d.board || '',
    targetOtaId: d.targetOtaId || '',
    otaType: d.otaType || ''
  }
}

async function loadAgents() {
  try {
    const res = await adminApi.agentList()
    agents.value = (res.data || []).map(a => ({ id: a.id, name: a.agentName || a.name || '未命名' }))
  } catch (e) { toast(e.msg || '智能体加载失败', 'error') }
}

function openRename(d) { rename.id = d.id; rename.name = d.name || ''; rename.show = true }
async function doRename() {
  if (!rename.name) { toast('请填写名称', 'error'); return }
  saving.value = true
  try {
    // cc-console 契约：PUT /device/update/{id} body={alias}
    await adminApi.deviceUpdate(rename.id, { alias: rename.name })
    toast('已改名'); rename.show = false; load()
  } catch (e) { toast(e.msg || '改名失败', 'error') }
  finally { saving.value = false }
}

function openBind(d) {
  bind.device = d
  bind.agentId = ''
  bind.show = true
}
async function doBind() {
  if (!bind.agentId || !bind.device) return
  saving.value = true
  try {
    // cc-console 契约：POST /device/bind/{agentId}/{macAddress|id}（api.js 未封装，直接调用）
    await api.post(`/device/bind/${bind.agentId}/${encodeURIComponent(bind.device.mac || bind.device.id)}`)
    bind.show = false
    toast('已绑定')
    load()
  } catch (e) { toast(e.msg || '绑定失败', 'error') }
  finally { saving.value = false }
}

async function doManualAdd() {
  if (!manual.mac) { toast('请填写 MAC 地址', 'error'); return }
  saving.value = true
  try {
    // cc-console 契约：POST /device/manual-add body={board,appVersion,macAddress}
    await adminApi.deviceManualAdd({ board: manual.board || 'my-s3-tft', appVersion: manual.appVersion || '1.0.0', macAddress: manual.mac })
    toast('设备已添加'); manual.show = false; manual.mac = ''; manual.name = ''; load()
  } catch (e) { toast(e.msg || '添加失败', 'error') }
  finally { saving.value = false }
}

// ── OTA 定向配置 ──
async function openOta(d) {
  ota.device = d
  ota.targetOtaId = d.targetOtaId || ''
  ota.otaType = d.otaType || ''
  ota.firmwares = []
  ota.tracks = []
  ota.show = true
  try {
    // 已注册固件列表（选择 pin 目标 + 推导可选轨道）
    const res = await adminApi.otaPage({ page: 1, limit: 200 })
    const list = (res.data && (res.data.list || res.data)) || []
    ota.firmwares = list
    // 轨道候选 = 固件记录里出现过的去重 type + 设备当前上报的 board
    const trackSet = new Set(list.map(f => f.type).filter(Boolean))
    if (d.board) trackSet.add(d.board)
    ota.tracks = [...trackSet].sort()
  } catch (e) {
    toast(e.msg || '固件列表加载失败', 'error')
  }
}

async function doOtaTarget() {
  if (!ota.device) return
  saving.value = true
  try {
    await adminApi.deviceOtaTarget(ota.device.id, {
      targetOtaId: ota.targetOtaId || '',
      otaType: ota.otaType || ''
    })
    toast('OTA 配置已保存，设备下次上报生效')
    ota.show = false
    load()
  } catch (e) { toast(e.msg || '保存失败', 'error') }
  finally { saving.value = false }
}

function unbind(d) {
  askConfirm({
    title: '解绑设备', message: `确定解绑「${d.name || d.mac}」吗？`, danger: true,
    onOk: async () => {
      try { await adminApi.deviceUnbind({ deviceId: d.id }); toast('已解绑'); load() }
      catch (e) { toast(e.msg || '解绑失败', 'error') }
    }
  })
}

watch([page, pageSize], () => load())

onMounted(() => { load(); loadAgents() })
</script>

<style scoped>
.form-row { margin-bottom: 14px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row select {
  border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px;
  font-size: 14px; outline: none; background: #fff; color: var(--text);
}
.form-row input:focus, .form-row select:focus { border-color: var(--primary); }
.bind-sub { color: var(--text-sub); font-size: 13px; margin-bottom: 16px; }
.ota-hint { color: var(--text-sub); font-size: 12px; line-height: 1.6; background: var(--bg-soft, #f7f7fa); border-radius: 10px; padding: 10px 12px; margin: 4px 0 2px; }
.modal h3 { font-size: 17px; margin-bottom: 18px; }
</style>
