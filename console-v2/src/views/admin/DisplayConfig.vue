<template>
  <div>
    <div class="page-head">
      <div>
        <h1>展示 <span style="color:var(--primary)">配置</span></h1>
        <p class="sub">配置用户端字段的可见性与可编辑性</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
        <button class="btn btn-primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '💾 保存配置' }}</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="🌐" label="当前作用域" :value="SCOPES.find(s => s.value === scopeType)?.label || '—'" />
      <StatCard icon="🎯" label="目标对象" :value="scopeName" note="角色 / 用户" />
      <StatCard icon="👁" label="可见字段" :value="rows.filter(r => r.visible).length" :note="'共 ' + rows.length + ' 个字段'" />
      <StatCard icon="✏️" label="可编辑字段" :value="rows.filter(r => r.editable).length" />
    </div>

    <!-- ① 作用域选择器：系统(0)/角色(1)/用户(2) -->
    <DataTable title="字段权限编辑" hint="缺省字段=可见+可编辑；作用域继承：用户>角色>系统">
      <template #actions>
        <div class="scope-bar">
          <div v-for="s in SCOPES" :key="s.value" class="chip" :class="{ active: scopeType === s.value }" @click="pickScope(s.value)">
            {{ s.label }}
          </div>
          <select v-if="scopeType === 1" v-model="roleId" class="scope-select">
            <option :value="''" disabled>选择角色</option>
            <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.roleName }}</option>
          </select>
          <select v-else-if="scopeType === 2" v-model="userId" class="scope-select">
            <option :value="''" disabled>选择用户</option>
            <option v-for="u in users" :key="u.id" :value="u.id">{{ u.username }}</option>
          </select>
        </div>
      </template>

      <table class="data-table">
        <thead>
          <tr><th style="width:42%">字段 key</th><th>👁 可见 visible</th><th>✏️ 可编辑 editable</th><th style="width:80px"></th></tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="row.key">
            <td>
              <div class="cell-main">{{ row.key }}</div>
              <div class="cell-sub">{{ PREDEFINED_LABELS[row.key] || '自定义字段' }}</div>
            </td>
            <td>
              <label class="chk">
                <input type="checkbox" v-model="row.visible" />
                <span>{{ row.visible ? '可见' : '隐藏' }}</span>
              </label>
            </td>
            <td>
              <label class="chk">
                <input type="checkbox" v-model="row.editable" />
                <span>{{ row.editable ? '可编辑' : '只读' }}</span>
              </label>
            </td>
            <td>
              <button class="link-btn danger" :disabled="PREDEFINED_KEYS.includes(row.key)" :title="PREDEFINED_KEYS.includes(row.key) ? '预置字段不可删除' : '删除该字段'" @click="removeRow(i)">✕</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="rows.length === 0" class="empty-state">
        <div class="empty-icon">🖼</div><strong>当前作用域尚无配置</strong><p>保存后按缺省规则生效（全部可见+可编辑）</p>
      </div>

      <!-- ＋ 添加字段：追加自定义 key -->
      <div class="add-row">
        <input v-model.trim="newKey" placeholder="输入自定义字段 key，如 max_tokens" @keyup.enter="addRow" />
        <button class="btn btn-ghost" @click="addRow">＋ 添加字段</button>
      </div>
    </DataTable>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, reactive, ref, watch } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')

// 预置字段（SPEC 任务清单），label 仅作展示提示
const PREDEFINED_KEYS = ['llm_model', 'tts_voice', 'asr_model', 'system_prompt', 'temperature', 'top_p', 'tts_volume', 'tts_rate', 'wake_words']
const PREDEFINED_LABELS = {
  llm_model: 'LLM 模型', tts_voice: 'TTS 音色', asr_model: 'ASR 模型',
  system_prompt: '系统提示词', temperature: '温度', top_p: 'Top P',
  tts_volume: 'TTS 音量', tts_rate: 'TTS 语速', wake_words: '唤醒词'
}

const SCOPES = [
  { value: 0, label: '🌐 系统默认' },
  { value: 1, label: '👥 角色' },
  { value: 2, label: '👤 用户' }
]

const scopeType = ref(0)   // 0系统 / 1角色 / 2用户
const roleId = ref('')
const userId = ref('')
const roles = ref([])
const users = ref([])
const rows = ref([])
const newKey = ref('')
const loading = ref(false)
const saving = ref(false)

const scopeName = computed(() => {
  if (scopeType.value === 1) return roles.value.find(r => r.id === roleId.value)?.roleName || '未选择'
  if (scopeType.value === 2) return users.value.find(u => u.id === userId.value)?.username || '未选择'
  return '全部（平台默认）'
})

// 预置字段全量渲染，未配置的按缺省规则「可见+可编辑」展示
function normalizeRows(fields) {
  const map = {}
  for (const [k, v] of Object.entries(fields || {})) {
    map[k] = { key: k, visible: v?.visible !== false, editable: v?.editable !== false }
  }
  const preset = PREDEFINED_KEYS.map(k => ({ key: k, visible: true, editable: true, ...(map[k] || {}) }))
  const extra = Object.keys(map).filter(k => !PREDEFINED_KEYS.includes(k)).map(k => map[k])
  return [...preset, ...extra]
}

async function load() {
  loading.value = true
  try {
    const p = { scopeType: scopeType.value }
    if (scopeType.value === 1) p.roleId = roleId.value
    if (scopeType.value === 2) p.userId = userId.value
    const res = await adminApi.displayConfigGet(p)
    // 契约（SPEC §4.3）：data={configJson:{"fields":{key:{visible,editable}}}}
    const json = typeof res.data?.configJson === 'string' ? JSON.parse(res.data.configJson || '{}') : (res.data?.configJson || {})
    rows.value = normalizeRows(json.fields || {})
  } catch (e) {
    rows.value = normalizeRows({})
    // 403 越权 / 10230 非法作用域参数提示（SPEC §3 错误码）
    if (e.code === 403 || e.code === 10230) toast(e.msg || '无权限或作用域参数无效', 'error')
    else toast(e.msg || '加载失败', 'error')
  } finally {
    loading.value = false
  }
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

function pickScope(v) {
  if (scopeType.value === v) return
  scopeType.value = v
  roleId.value = ''
  userId.value = ''
  load()
}

function addRow() {
  const k = newKey.value
  if (!k) { toast('请输入字段 key', 'error'); return }
  if (rows.value.some(r => r.key === k)) { toast('字段已存在', 'error'); return }
  rows.value.push({ key: k, visible: true, editable: true })
  newKey.value = ''
}

function removeRow(i) {
  rows.value.splice(i, 1)
}

async function save() {
  const fields = {}
  for (const r of rows.value) fields[r.key] = { visible: r.visible, editable: r.editable }
  const body = {
    scopeType: scopeType.value,
    configJson: { fields }
  }
  if (scopeType.value === 1) {
    if (!roleId.value) { toast('请先选择角色', 'error'); return }
    body.roleId = roleId.value
  }
  if (scopeType.value === 2) {
    if (!userId.value) { toast('请先选择用户', 'error'); return }
    body.userId = userId.value
  }
  saving.value = true
  try {
    await adminApi.displayConfigSave(body)
    toast('已保存')
  } catch (e) {
    if (e.code === 403 || e.code === 10230) toast(e.msg || '无权限或作用域参数无效', 'error')
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
  loadRoles()
  loadUsers()
  load()
})
</script>

<style scoped>
.scope-bar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.chip { padding: 8px 16px; border-radius: 999px; background: var(--bg-card); border: 1.5px solid var(--border); cursor: pointer; font-size: 13px; }
.chip.active { border-color: var(--primary); color: var(--primary); font-weight: 600; }
.scope-select {
  border: 1.5px solid var(--border); border-radius: 12px; padding: 8px 12px;
  font-size: 13px; outline: none; background: #fff; color: var(--text); min-width: 170px;
}
.scope-select:focus { border-color: var(--primary); }
.chk { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.chk input { width: auto; accent-color: var(--primary); }
.chk span { font-size: 13px; color: var(--text-sub); }
.add-row {
  display: flex; gap: 10px; padding: 14px 20px 20px; align-items: center;
  border-top: 1px dashed var(--border); margin-top: 4px;
}
.add-row input {
  flex: 1; max-width: 340px; border: 1.5px solid var(--border); border-radius: 12px;
  padding: 9px 14px; font-size: 13.5px; outline: none; background: #fff; color: var(--text);
}
.add-row input:focus { border-color: var(--primary); }
</style>
