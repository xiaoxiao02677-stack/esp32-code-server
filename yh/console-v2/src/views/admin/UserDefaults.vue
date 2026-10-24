<template>
  <div>
    <div class="page-head">
      <div>
        <h1>默认 <span style="color:var(--primary)">配置</span></h1>
        <p class="sub">配置默认 LLM / TTS 音色 / ASR 与参数模板</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
        <button class="btn btn-primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '💾 保存配置' }}</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="globe" label="当前作用域" :value="SCOPES.find(s => s.value === scopeType)?.label || '—'" />
      <StatCard icon="target" label="目标对象" :value="scopeName" />
      <StatCard icon="memory" label="默认 LLM" :value="llmName || '未设置'" />
      <StatCard icon="🔒" label="锁定策略" :value="lockPolicy ? '已锁定' : '未锁定'" :note="lockPolicy ? '下级不可覆盖' : '下级可覆盖'" />
    </div>

    <!-- 作用域选择器：平台(0)/角色(1)/用户(2) -->
    <div class="panel" style="margin-bottom:20px">
      <div class="panel-head"><h3>作用域<span class="hint">保存到对应层级的默认配置</span></h3></div>
      <div class="scope-row">
        <button type="button" v-for="s in SCOPES" :key="s.value" class="chip" :class="{ active: scopeType === s.value }" @click="pickScope(s.value)">
          {{ s.label }}
        </button>
        <select v-if="scopeType === 1" v-model="roleId" class="scope-select">
          <option :value="''" disabled>选择角色</option>
          <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.roleName }}</option>
        </select>
        <select v-else-if="scopeType === 2" v-model="userId" class="scope-select">
          <option :value="''" disabled>选择用户</option>
          <option v-for="u in users" :key="u.id" :value="u.id">{{ u.username }}</option>
        </select>
      </div>
    </div>

    <!-- 表单面板 -->
    <div class="panel form-panel">
      <div class="panel-head"><h3>默认项<span class="hint">默认模型/音色在用户未配置时生效</span></h3></div>
      <div class="form-body">
        <div class="form-row">
          <label>默认 LLM 模型</label>
          <select v-model="form.llmModelId">
            <option value="">未设置</option>
            <option v-if="llmModels.length === 0" value="" disabled>暂无可用模型</option>
            <option v-for="m in llmModels" :key="m.id" :value="m.id">{{ m.modelName }}</option>
          </select>
          <p class="field-hint">平台启用的 LLM 模型（modelList('LLM')）</p>
        </div>

        <div class="form-row">
          <label>默认 TTS 模型</label>
          <select v-model="form.ttsModelId" @change="onTtsModelChange">
            <option value="">未设置</option>
            <option v-if="ttsModels.length === 0" value="" disabled>暂无可用模型</option>
            <option v-for="m in ttsModels" :key="m.id" :value="m.id">{{ m.modelName }}</option>
          </select>
        </div>

        <div class="form-row">
          <label>默认音色</label>
          <select v-model="form.ttsVoiceId" :disabled="!form.ttsModelId">
            <option value="">未设置</option>
            <option v-if="form.ttsModelId && voices.length === 0" value="" disabled>暂无可用音色</option>
            <option v-for="v in voices" :key="v.id" :value="v.id">{{ v.name || v.voiceName || v.ttsVoice || v.id }}</option>
          </select>
          <p class="field-hint">音色随 TTS 模型联动加载</p>
        </div>

        <div class="form-row">
          <label>默认 ASR 模型</label>
          <select v-model="form.asrModelId">
            <option value="">未设置</option>
            <option v-if="asrModels.length === 0" value="" disabled>暂无可用模型</option>
            <option v-for="m in asrModels" :key="m.id" :value="m.id">{{ m.modelName }}</option>
          </select>
        </div>

        <div class="form-row">
          <label>参数模板 paramJson</label>
          <div class="edit-grid">
            <div class="form-row">
              <label>temperature</label>
              <input v-model.number="form.temperature" type="number" min="0" max="2" step="0.1" placeholder="如 0.7" />
            </div>
            <div class="form-row">
              <label>topP</label>
              <input v-model.number="form.topP" type="number" min="0" max="1" step="0.05" placeholder="如 0.9" />
            </div>
          </div>
          <p class="field-hint">保存时组装为 {"temperature":…,"topP":…}；留空则不写入该键</p>
        </div>

        <div class="form-row">
          <label class="switch-row">
            <span>
              🔒 锁定默认配置（lockPolicy）
              <span class="switch-sub">锁定后下级（角色/用户）不可覆盖</span>
            </span>
            <button type="button" class="switch" :class="{ on: lockPolicy }" title="锁定后下级不可覆盖" @click="lockPolicy = !lockPolicy">
              <span class="knob"></span>
            </button>
          </label>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, reactive, ref, watch } from 'vue'
import StatCard from '../../components/StatCard.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')

const SCOPES = [
  { value: 0, label: '🌐 平台默认' },
  { value: 1, label: '👥 角色' },
  { value: 2, label: '👤 用户' }
]

const scopeType = ref(0)   // 0平台 / 1角色 / 2用户
const roleId = ref('')
const userId = ref('')
const roles = ref([])
const users = ref([])

const llmModels = ref([])
const ttsModels = ref([])
const asrModels = ref([])
const voices = ref([])

const lockPolicy = ref(false)
const form = reactive({ llmModelId: '', ttsModelId: '', ttsVoiceId: '', asrModelId: '', temperature: null, topP: null })

const loading = ref(false)
const saving = ref(false)

const scopeName = computed(() => {
  if (scopeType.value === 1) return roles.value.find(r => r.id === roleId.value)?.roleName || '未选择'
  if (scopeType.value === 2) return users.value.find(u => u.id === userId.value)?.username || '未选择'
  return '全部（平台默认）'
})
const llmName = computed(() => llmModels.value.find(m => m.id === form.llmModelId)?.modelName || '')

function scopeParams() {
  const p = { scopeType: scopeType.value }
  if (scopeType.value === 1) p.roleId = roleId.value
  if (scopeType.value === 2) p.userId = userId.value
  return p
}

// ===== 下拉数据源（既有端点，api.js 封装名 modelList/modelVoices） =====
async function loadModels() {
  try {
    const [llm, tts, asr] = await Promise.all([
      adminApi.modelList('LLM'),
      adminApi.modelList('TTS'),
      adminApi.modelList('ASR')
    ])
    llmModels.value = llm.data?.list || []
    ttsModels.value = tts.data?.list || []
    asrModels.value = asr.data?.list || []
  } catch (e) { toast(e.msg || '模型列表加载失败', 'error') }
}

async function loadVoices(modelId) {
  voices.value = []
  if (!modelId) return
  try {
    const res = await adminApi.modelVoices(modelId)
    voices.value = (res.data || []).map(v => ({
      id: v.id,
      name: v.name || v.voiceName || v.ttsVoice || v.id,
      ttsVoice: v.ttsVoice
    }))
  } catch (e) { toast(e.msg || '音色加载失败', 'error') }
}

function onTtsModelChange() {
  form.ttsVoiceId = ''
  loadVoices(form.ttsModelId)
}

async function loadRoles() {
  try {
    const res = await adminApi.roleList()
    roles.value = res.data || []
  } catch (e) { toast(e.msg || '角色加载失败', 'error') }
}

async function loadUsers() {
  try {
    const res = await adminApi.userPage({ page: 1, limit: 100 })
    const list = res.data?.list || []
    users.value = list.map(u => ({ id: u.userid ?? u.id, username: u.username || u.mobile || '未命名' }))
  } catch (e) { toast(e.msg || '用户加载失败', 'error') }
}

// ===== 加载当前作用域默认配置 =====
async function load() {
  // 作用域=角色/用户 但尚未选择目标：不发请求（后端 10230 校验缺参），表单显示空态
  if ((scopeType.value === 1 && !roleId.value) || (scopeType.value === 2 && !userId.value)) {
    form.llmModelId = ''; form.ttsModelId = ''; form.ttsVoiceId = ''; form.asrModelId = ''
    form.temperature = null; form.topP = null; lockPolicy.value = false
    return
  }
  loading.value = true
  try {
    const res = await adminApi.userDefaultGet(scopeParams())
    // 契约：data={llmModelId,ttsModelId,ttsVoiceId,asrModelId,paramJson,lockPolicy}
    const d = res.data || {}
    let paramJson = {}
    if (d.paramJson) {
      try { paramJson = typeof d.paramJson === 'string' ? JSON.parse(d.paramJson) : d.paramJson } catch { paramJson = {} }
    }
    form.llmModelId = d.llmModelId || ''
    form.ttsModelId = d.ttsModelId || ''
    form.ttsVoiceId = d.ttsVoiceId || ''
    form.asrModelId = d.asrModelId || ''
    form.temperature = paramJson.temperature != null ? Number(paramJson.temperature) : null
    form.topP = paramJson.topP != null ? Number(paramJson.topP) : null
    lockPolicy.value = !!d.lockPolicy
    if (form.ttsModelId) loadVoices(form.ttsModelId)
  } catch (e) {
    form.llmModelId = ''; form.ttsModelId = ''; form.ttsVoiceId = ''; form.asrModelId = ''
    form.temperature = null; form.topP = null; lockPolicy.value = false
    toast(e.msg || '加载失败', 'error')
  } finally {
    loading.value = false
  }
}

function pickScope(v) {
  if (scopeType.value === v) return
  scopeType.value = v
  roleId.value = ''
  userId.value = ''
  load()
}

async function save() {
  if (scopeType.value === 1 && !roleId.value) { toast('请先选择角色', 'error'); return }
  if (scopeType.value === 2 && !userId.value) { toast('请先选择用户', 'error'); return }

  const paramJson = {}
  if (form.temperature !== null && form.temperature !== '') paramJson.temperature = Number(form.temperature)
  if (form.topP !== null && form.topP !== '') paramJson.topP = Number(form.topP)

  const body = {
    scopeType: scopeType.value,
    llmModelId: form.llmModelId || null,
    ttsModelId: form.ttsModelId || null,
    ttsVoiceId: form.ttsVoiceId || null,
    asrModelId: form.asrModelId || null,
    paramJson: JSON.stringify(paramJson),
    lockPolicy: lockPolicy.value
  }
  if (scopeType.value === 1) body.roleId = roleId.value
  if (scopeType.value === 2) body.userId = userId.value

  saving.value = true
  try {
    await adminApi.userDefaultSave(body)
    toast('已保存')
  } catch (e) {
    // 10231 默认模型不存在或未启用 / 10232 默认音色不存在（SPEC §3）
    if (e.code === 10231) toast(e.msg || '默认模型不存在或未启用，请重新选择', 'error')
    else if (e.code === 10232) toast(e.msg || '默认音色不存在，请重新选择', 'error')
    else toast(e.msg || '保存失败', 'error')
  } finally {
    saving.value = false
  }
}

// 角色/用户切换 → 重新加载该作用域配置
watch([roleId, userId], () => {
  if ((scopeType.value === 1 && roleId.value) || (scopeType.value === 2 && userId.value)) load()
})

onMounted(() => {
  loadModels()
  loadRoles()
  loadUsers()
  load()
})
</script>

<style scoped>
.scope-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; padding: 0 20px 16px; }
/* .chip 已收敛到 global.css */

/* .chip 已收敛到 global.css */

.scope-select {
  border: 1.5px solid var(--border); border-radius: 12px; padding: 8px 12px;
  font-size: 13px; outline: none; background: #fff; color: var(--text); min-width: 170px;
}
.scope-select:focus { border-color: var(--primary); }
.form-panel .form-body { padding: 6px 20px 22px; }
.form-row { margin-bottom: 16px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row select {
  border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px;
  font-size: 14px; outline: none; font-family: var(--font); background: #fff; color: var(--text);
}
.form-row input:focus, .form-row select:focus { border-color: var(--primary); }
.field-hint { font-size: 11.5px; color: var(--text-sub); margin: 2px 0 0; }
.edit-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px 16px; }
.switch-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 16px; border: 1.5px solid var(--border); border-radius: 14px;
  font-size: 14px; color: var(--text); cursor: default; gap: 12px;
}
.switch-sub { display: block; font-size: 12px; color: var(--text-sub); font-weight: 400; margin-top: 3px; }
.switch {
  width: 46px; height: 26px; border-radius: 999px; border: none; cursor: pointer; flex-shrink: 0;
  background: #D3DAE5; position: relative; transition: background .2s;
}
.switch.on { background: var(--primary); }
.switch .knob {
  position: absolute; top: 3px; left: 3px; width: 20px; height: 20px; border-radius: 50%;
  background: #fff; transition: left .2s; box-shadow: 0 2px 6px rgba(0,0,0,.2);
}
.switch.on .knob { left: 23px; }

/* 移动端：下拉不固定最小宽；编辑栅格单列 */
@media (max-width: 768px) {
  select { min-width: 0 !important; max-width: 100%; }
  .edit-grid { grid-template-columns: 1fr; }
}
</style>
