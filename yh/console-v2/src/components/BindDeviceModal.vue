<template>
  <div v-if="show" class="modal-mask" @click.self="$emit('update:show', false)">
    <div class="modal">
      <h3>绑定设备</h3>
      <p class="bind-agent-name">
        绑定到智能体：<strong>{{ agentName || '未命名' }}</strong>
      </p>

      <!-- 已绑定设备 -->
      <div v-if="boundDevices.length" class="bound-list">
        <div v-for="d in boundDevices" :key="d.id || d.macAddress" class="bound-item">
          <span class="bound-name">{{ d.alias || d.deviceName || d.macAddress || d.id }}</span>
          <span v-if="d.board" class="bound-sub">{{ d.board }}</span>
          <button class="chip-unbind" title="解绑" :disabled="busy" @click="unbind(d)">✕</button>
        </div>
      </div>
      <p v-else class="bind-empty">
        该智能体还没有绑定设备，设备将无法使用它对话。在下方输入设备屏幕显示的 6 位验证码完成绑定。
      </p>

      <!-- 六位码绑定 -->
      <div class="bind-code-row">
        <input
          v-model="code" placeholder="设备上的 6 位验证码" maxlength="6" inputmode="numeric"
          @keyup.enter="bindByCode"
        />
        <button class="btn btn-primary" :disabled="!isCode || busy" @click="bindByCode">
          {{ busy ? '绑定中…' : '验证码绑定' }}
        </button>
      </div>

      <!-- 手动 MAC 添加（收起式） -->
      <details class="manual-add">
        <summary>手动录入 MAC 添加设备</summary>
        <div class="manual-grid">
          <div class="form-row"><label>板型</label><input v-model="manual.board" placeholder="如 yh-154tft-wifi（可空）" /></div>
          <div class="form-row"><label>固件版本</label><input v-model="manual.appVersion" placeholder="如 2.5.1（可空）" /></div>
          <div class="form-row"><label>MAC 地址 *</label><input v-model="manual.macAddress" placeholder="14:c1:9f:xx:xx:xx" /></div>
        </div>
        <button class="btn btn-ghost" :disabled="!manual.macAddress || busy" @click="manualAdd">＋ 手动添加设备</button>
      </details>

      <div class="modal-actions">
        <button class="btn btn-ghost" @click="$emit('update:show', false)">关闭</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, ref, watch } from 'vue'
import { customerApi } from '../lib/api'

const props = defineProps({
  show: { type: Boolean, default: false },
  agentId: { type: String, default: '' },
  agentName: { type: String, default: '' }
})
const emit = defineEmits(['update:show', 'bound'])

const toast = inject('toast', (msg, type) => console.log('[toast]', msg, type))
const askConfirm = inject('askConfirm', null)

const code = ref('')
const busy = ref(false)
const boundDevices = ref([])
const manual = ref({ board: '', appVersion: '', macAddress: '' })
const isCode = computed(() => /^\d{6}$/.test(code.value))

async function loadBound() {
  if (!props.agentId) { boundDevices.value = []; return }
  try {
    const res = await customerApi.boundDevices(props.agentId)
    boundDevices.value = res.data || []
  } catch { boundDevices.value = [] }
}

watch(() => props.show, v => { if (v) { code.value = ''; loadBound() } })
watch(() => props.agentId, () => { if (props.show) loadBound() })

async function bindByCode() {
  if (!isCode.value) { toast('请输入设备上的 6 位数字验证码', 'error'); return }
  busy.value = true
  try {
    await customerApi.bindDeviceByCode(props.agentId, code.value)
    toast('绑定成功')
    code.value = ''
    await loadBound()
    emit('bound')
  } catch (e) {
    toast(e.msg || '绑定失败，请确认验证码是否正确', 'error')
  } finally { busy.value = false }
}

async function manualAdd() {
  if (!manual.value.macAddress) { toast('请填写 MAC 地址', 'error'); return }
  busy.value = true
  try {
    const payload = { agentId: props.agentId, macAddress: manual.value.macAddress.trim() }
    if (manual.value.board) payload.board = manual.value.board.trim()
    if (manual.value.appVersion) payload.appVersion = manual.value.appVersion.trim()
    await customerApi.deviceManualAdd(payload)
    toast('设备已添加并绑定')
    manual.value = { board: '', appVersion: '', macAddress: '' }
    await loadBound()
    emit('bound')
  } catch (e) {
    toast(e.msg || '添加失败', 'error')
  } finally { busy.value = false }
}

function unbind(d) {
  const name = d.alias || d.deviceName || d.macAddress || d.id
  const doUnbind = async () => {
    busy.value = true
    try {
      await customerApi.deviceUnbind({ deviceId: d.id })
      toast('已解绑')
      await loadBound()
      emit('bound')
    } catch (e) {
      toast(e.msg || '解绑失败', 'error')
    } finally { busy.value = false }
  }
  if (askConfirm) {
    askConfirm({ title: '解绑设备', message: `确定解绑设备「${name}」吗？`, danger: true, okText: '解绑', onOk: doUnbind })
  } else {
    doUnbind()
  }
}
</script>

<style scoped>
.bind-agent-name { font-size: 13.5px; color: var(--text-sub); margin: -8px 0 14px; }
.bind-empty { font-size: 12.5px; color: #B45309; margin: 6px 0 10px; line-height: 1.5; }
.bound-list { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.bound-item {
  display: flex; align-items: center; gap: 8px; background: #fff;
  border: 1px solid var(--border); border-radius: 999px; padding: 4px 6px 4px 14px; font-size: 12.5px;
}
.bound-name { font-weight: 600; max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bound-sub { color: var(--text-sub); font-size: 11px; }
.chip-unbind {
  width: 20px; height: 20px; border-radius: 50%; border: none; cursor: pointer;
  background: transparent; color: var(--text-sub); font-size: 11px; line-height: 1;
  display: inline-flex; align-items: center; justify-content: center; transition: all .15s;
}
.chip-unbind:hover { background: var(--danger); color: #fff; }
.bind-code-row { display: flex; gap: 10px; }
.bind-code-row input {
  flex: 1; border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px;
  font-size: 14px; letter-spacing: 2px; outline: none; font-family: var(--font); background: #fff;
}
.bind-code-row input:focus { border-color: var(--primary); }
.manual-add { margin-top: 12px; font-size: 13px; }
.manual-add summary { cursor: pointer; color: var(--text-sub); font-weight: 600; }
.manual-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 10px 0; }
.manual-grid .form-row:last-child { grid-column: 1 / -1; }
.form-row { display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input {
  border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px;
  font-size: 14px; outline: none; font-family: var(--font); background: #fff;
}
.form-row input:focus { border-color: var(--primary); }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }

/* 移动端：手动添加双列表单单列 */
@media (max-width: 768px) {
  .manual-grid { grid-template-columns: 1fr; }
  .modal-actions { flex-wrap: wrap; }
  .modal-actions .btn { flex: 1; justify-content: center; }
}
</style>
