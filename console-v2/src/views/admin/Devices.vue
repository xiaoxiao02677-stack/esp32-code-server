<template>
  <div>
    <div class="page-head">
      <div>
        <h1>设备 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">迁移自 /cc/ 设备页：全量设备 / 改名 / 手动添加 / 解绑</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="manual.show = true">＋ 手动添加</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="📡" label="设备总数" :value="devices.length" />
      <StatCard icon="🟢" label="在线" :value="devices.filter(d => d.online).length" />
      <StatCard icon="🔗" label="已绑定智能体" :value="devices.filter(d => d.agentId).length" />
    </div>

    <DataTable title="设备列表">
      <table class="data-table">
        <thead><tr><th>设备</th><th>MAC / IP</th><th>智能体</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="d in devices" :key="d.id">
            <td><div class="cell-main">{{ d.name || d.deviceName || '未命名' }}</div><div class="cell-sub">{{ d.lastSeen || d.updateDate || '' }}</div></td>
            <td style="font-size:12px">{{ d.macAddress || d.mac || '—' }}<br />{{ d.ip || '' }}</td>
            <td>{{ d.agentName || d.agentId || '—' }}</td>
            <td>
              <span class="badge" :class="d.online ? 'badge-green' : 'badge-gray'">
                <span class="dot"></span>{{ d.online ? '在线' : '离线' }}
              </span>
            </td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="openRename(d)">改名</button>
                <button class="link-btn danger" @click="unbind(d)">解绑</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="devices.length === 0" class="empty-state"><div class="empty-icon">📡</div><strong>暂无设备</strong></div>
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
import { inject, onMounted, reactive, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')
const devices = ref([])
const loading = ref(false)
const saving = ref(false)
const rename = reactive({ show: false, id: null, name: '' })
const manual = reactive({ show: false, mac: '', name: '' })

async function load() {
  loading.value = true
  try {
    const res = await adminApi.devicePage({ page: 1, limit: 200 })
    const data = res.data || {}
    devices.value = (data.list || data || []).map(d => ({
      id: d.id || d.macAddress,
      name: d.name || d.deviceName,
      mac: d.macAddress || d.mac,
      ip: d.ip,
      agentId: d.agentId,
      agentName: d.agentName,
      online: d.status === 1 || d.online,
      lastSeen: d.lastSeen || d.updateDate
    }))
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

function openRename(d) { rename.id = d.id; rename.name = d.name || ''; rename.show = true }
async function doRename() {
  if (!rename.name) { toast('请填写名称', 'error'); return }
  saving.value = true
  try {
    await adminApi.deviceUpdate(rename.id, { name: rename.name })
    toast('已改名'); rename.show = false; load()
  } catch (e) { toast(e.msg || '改名失败', 'error') }
  finally { saving.value = false }
}

async function doManualAdd() {
  if (!manual.mac) { toast('请填写 MAC 地址', 'error'); return }
  saving.value = true
  try {
    await adminApi.deviceManualAdd({ macAddress: manual.mac, name: manual.name || undefined })
    toast('设备已添加'); manual.show = false; manual.mac = ''; manual.name = ''; load()
  } catch (e) { toast(e.msg || '添加失败', 'error') }
  finally { saving.value = false }
}

function unbind(d) {
  askConfirm({
    title: '解绑设备', message: `确定解绑「${d.name || d.mac}」吗？`, danger: true,
    onOk: async () => {
      try { await adminApi.deviceUnbind({ macAddress: d.mac }); toast('已解绑'); load() }
      catch (e) { toast(e.msg || '解绑失败', 'error') }
    }
  })
}

onMounted(load)
</script>

<style scoped>
.form-row { margin-bottom: 14px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input { border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px; font-size: 14px; outline: none; }
.form-row input:focus { border-color: var(--primary); }
</style>
