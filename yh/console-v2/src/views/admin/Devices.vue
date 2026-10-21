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
        <thead><tr>
          <th class="check-cell"><input type="checkbox" class="row-check" :checked="allChecked" :indeterminate.prop="someChecked && !allChecked" aria-label="全选本页设备" @change="toggleCheckAll" /></th>
          <th>设备</th><th>MAC / IP</th><th>智能体</th><th>状态</th><th>操作</th>
        </tr></thead>
        <tbody>
          <tr v-for="d in devices" :key="d.id" :class="{ 'row-checked': checkedIds.has(d.id) }">
            <td class="check-cell"><input type="checkbox" class="row-check" :checked="checkedIds.has(d.id)" :aria-label="`选择 ${d.name}`" @change="toggleCheck(d.id)" /></td>
            <td><div class="cell-main">{{ d.name }}</div><div class="cell-sub">{{ d.lastSeen || d.updateDate || '' }}</div></td>
            <td style="font-size:12px">{{ d.mac || '—' }}<template v-if="d.ip"><br />{{ d.ip }}</template></td>
            <td>
              <div class="cell-main">{{ d.agentName || '—' }}</div>
              <div v-if="d.agentName && d.bindUserName" class="cell-sub">{{ d.bindUserName }}</div>
            </td>
            <td>
              <span class="badge" :class="d.online ? 'badge-green' : 'badge-gray'">
                <span class="dot"></span>{{ d.online ? '在线' : '离线' }}
              </span>
            </td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="openRename(d)">✎ 改名</button>
                <button class="link-btn" @click="openOta(d)">⬆ OTA</button>
                <button class="link-btn danger" @click="unbind(d)">⤫ 解绑</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="devices.length === 0" class="empty-state"><div class="empty-icon"><YhIcon name="device" /></div><strong>暂无设备</strong></div>
    </DataTable>

    <!-- 批量操作条：勾选设备后浮出 -->
    <div v-if="someChecked" class="bulk-bar">
      <span class="bulk-count">已选 {{ checkedIds.size }} 台</span>
      <button class="btn btn-primary bulk-btn" @click="openBatchOta">⬆ 批量 OTA</button>
      <button class="btn btn-ghost bulk-btn" @click="clearCheck">取消选择</button>
    </div>

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

    <!-- 绑定智能体：已移至智能体管理页（编辑弹窗内验证码/MAC 绑定），设备页不再提供 -->

    <!-- OTA 定向配置弹窗（单台） -->
    <div v-if="ota.show" class="modal-mask" @click.self="ota.show = false">
      <div class="modal">
        <h3>OTA 定向配置</h3>
        <p class="bind-sub">{{ ota.device.name }}（{{ ota.device.mac }}）· 当前版本 {{ ota.device.appVersion || '未知' }} / 轨道 {{ ota.device.board || '未知' }}</p>

        <div class="form-row">
          <label>指定固件（升级到位后自动解除）</label>
          <select v-model="ota.targetOtaId">
            <option value="">不指定（保持当前版本）</option>
            <option v-for="f in ota.firmwares" :key="f.id" :value="f.id">
              {{ f.firmwareName }} · {{ f.type }} · v{{ f.version }}
            </option>
          </select>
        </div>

        <p class="ota-hint">
          自动更新已停用：设备不会因服务器存在更高版本而自动升级，升级一律在此手动指定。
          可选任意固件（含跨主题切换），设备上报版本与类型收敛后指定自动解除。
        </p>

        <div class="modal-actions">
          <button class="btn btn-ghost" @click="ota.show = false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="doOtaTarget">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>

    <!-- 批量 OTA 弹窗 -->
    <div v-if="batchOta.show" class="modal-mask" @click.self="batchOta.show = false">
      <div class="modal">
        <h3>批量 OTA</h3>
        <p class="bind-sub">已选 {{ checkedIds.size }} 台设备 · 为它们统一指定固件（逐台 pin，离线设备下次上线收到）</p>

        <div class="form-row">
          <label>目标固件</label>
          <select v-model="batchOta.targetOtaId">
            <option value="">请选择固件</option>
            <option v-for="f in batchOta.firmwares" :key="f.id" :value="f.id">
              {{ f.firmwareName }} · {{ f.type }} · v{{ f.version }}
            </option>
          </select>
        </div>

        <p class="ota-hint">
          指定即升级（含跨主题）；各设备升级到位后指定自动解除。
          已有指定的设备会被本次选择覆盖。
        </p>

        <div class="modal-actions">
          <button class="btn btn-ghost" @click="batchOta.show = false">取消</button>
          <button class="btn btn-primary" :disabled="!batchOta.targetOtaId || batchOta.busy" @click="doBatchOta">
            {{ batchOta.busy ? `下发中 ${batchOta.done}/${checkedIds.size}…` : `下发到 ${checkedIds.size} 台` }}
          </button>
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
import { computed, inject, onMounted, reactive, ref, watch } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')
const devices = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const pages = ref(1)
const loading = ref(false)
const saving = ref(false)
const rename = reactive({ show: false, id: null, name: '' })
const manual = reactive({ show: false, mac: '', name: '' })
const ota = reactive({ show: false, device: null, targetOtaId: '', firmwares: [] })
const batchOta = reactive({ show: false, targetOtaId: '', firmwares: [], busy: false, done: 0 })
// 勾选集合（跨页保留）：分页翻页后已勾选的设备保持选中
const checkedIds = ref(new Set())
const allChecked = computed(() => devices.value.length > 0 && devices.value.every(d => checkedIds.value.has(d.id)))
const someChecked = computed(() => devices.value.some(d => checkedIds.value.has(d.id)))
function toggleCheck(id) {
  const s = new Set(checkedIds.value)
  s.has(id) ? s.delete(id) : s.add(id)
  checkedIds.value = s
}
function toggleCheckAll() {
  const s = new Set(checkedIds.value)
  if (allChecked.value) devices.value.forEach(d => s.delete(d.id))
  else devices.value.forEach(d => s.add(d.id))
  checkedIds.value = s
}
function clearCheck() { checkedIds.value = new Set() }

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
    agentName: d.agentName || '',
    bindUserName: d.bindUserName || '',
    online: onlineSet ? onlineSet.has(normMac(mac)) : false,
    lastSeen: d.recentChatTime || d.lastSeen || d.updateDate,
    appVersion: d.appVersion || '',
    board: d.board || '',
    targetOtaId: d.targetOtaId || '',
    otaType: d.otaType || ''
  }
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

// 设备绑定智能体：入口在智能体管理页编辑弹窗（验证码/MAC），本页不再提供绑定功能

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

// ── OTA 定向配置（单台） ──
async function openOta(d) {
  ota.device = d
  ota.targetOtaId = d.targetOtaId || ''
  ota.firmwares = []
  ota.show = true
  try {
    const res = await adminApi.otaPage({ page: 1, limit: 200 })
    ota.firmwares = (res.data && (res.data.list || res.data)) || []
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
      otaType: ota.device.otaType || ''
    })
    toast('OTA 配置已保存，设备下次上报生效')
    ota.show = false
    load()
  } catch (e) { toast(e.msg || '保存失败', 'error') }
  finally { saving.value = false }
}

// ── 批量 OTA（逐台 pin，循环调单台接口） ──
async function openBatchOta() {
  if (!checkedIds.value.size) return
  batchOta.targetOtaId = ''
  batchOta.firmwares = []
  batchOta.done = 0
  batchOta.busy = false
  batchOta.show = true
  try {
    const res = await adminApi.otaPage({ page: 1, limit: 200 })
    batchOta.firmwares = (res.data && (res.data.list || res.data)) || []
  } catch (e) {
    toast(e.msg || '固件列表加载失败', 'error')
  }
}

async function doBatchOta() {
  const ids = [...checkedIds.value]
  if (!ids.length || !batchOta.targetOtaId) return
  batchOta.busy = true
  batchOta.done = 0
  let ok = 0, fail = 0
  for (const id of ids) {
    try {
      await adminApi.deviceOtaTarget(id, { targetOtaId: batchOta.targetOtaId })
      ok++
    } catch { fail++ }
    batchOta.done++
  }
  batchOta.busy = false
  batchOta.show = false
  toast(`批量 OTA 已下发：成功 ${ok} 台${fail ? `，失败 ${fail} 台` : ''}，设备下次上报生效`, fail ? 'error' : 'success', 4000)
  load()
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

onMounted(load)
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
/* 勾选列 */
.check-cell { width: 40px; text-align: center; }
.row-check { width: 16px; height: 16px; accent-color: var(--primary); cursor: pointer; }
tr.row-checked { background: var(--primary-soft); }
/* 批量操作条：勾选后底部浮出 */
.bulk-bar {
  position: fixed; left: 50%; transform: translateX(-50%); bottom: 26px;
  display: flex; align-items: center; gap: 12px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius-pill); padding: 10px 18px;
  box-shadow: var(--shadow-dock); z-index: var(--z-dock);
}
.bulk-count { font-size: 13px; font-weight: 600; color: var(--text); padding: 0 4px; }
.bulk-btn { padding: 8px 16px; font-size: 13px; }
</style>
