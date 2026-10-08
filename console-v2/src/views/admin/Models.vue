<template>
  <div>
    <div class="page-head">
      <div>
        <h1>模型 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">契约对齐 /cc/：9 类型 / 供应器动态表单 / 新增编辑删除 / 启停测试</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="openCreate">＋ 新增模型</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="🧩" label="模型总数" :value="models.length" :note="activeType" />
      <StatCard icon="✅" label="启用中" :value="models.filter(m => m.isEnabled).length" />
      <StatCard icon="🔌" label="连通测试" :value="lastTest || '—'" />
    </div>

    <!-- 契约对齐 cc-console MODEL_TYPES：9 类型 -->
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px">
      <div v-for="t in MODEL_TYPES" :key="t.value" class="chip" :class="{ active: activeType === t.value }" @click="pickType(t.value)">
        {{ t.label }}
      </div>
    </div>

    <DataTable title="模型列表">
      <table class="data-table">
        <thead><tr><th>模型</th><th>类型</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="m in models" :key="m.id">
            <td><div class="cell-main">{{ m.modelName }}</div><div class="cell-sub">{{ m.id }}</div></td>
            <td>{{ m.modelType || activeType }}</td>
            <td>
              <span class="badge" :class="m.isEnabled ? 'badge-green' : 'badge-gray'">
                <span class="dot"></span>{{ m.isEnabled ? '启用' : '停用' }}
              </span>
            </td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="test(m)">测试</button>
                <button class="link-btn" @click="toggle(m)">{{ m.isEnabled ? '停用' : '启用' }}</button>
                <button class="link-btn" @click="openEdit(m)">编辑</button>
                <button class="link-btn danger" @click="remove(m)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="models.length === 0" class="empty-state"><div class="empty-icon">🧩</div><strong>此类型暂无模型</strong></div>
    </DataTable>

    <!-- 模型编辑弹窗（契约对齐 cc-console openModelEdit/saveModelConfig） -->
    <div v-if="editor.show" class="modal-mask" @click.self="editor.show = false">
      <div class="modal" style="width:min(640px,94vw);max-height:88vh;overflow:auto">
        <h3>{{ editor.id ? '编辑模型' : '新增模型' }}（{{ activeType }}）</h3>
        <div class="form-row"><label>供应器</label>
          <select v-model="editor.providerCode" @change="onProviderChange">
            <option v-for="p in providers" :key="p.providerCode" :value="p.providerCode">{{ p.providerName || p.providerCode }}</option>
          </select>
        </div>
        <div class="form-row"><label>模型名</label><input v-model="editor.modelName" placeholder="显示名称" /></div>
        <div v-if="editor.providerCode === '__custom_openai__'" class="form-row"><label>接口类型</label>
          <input v-model="editor.customType" placeholder="openai" />
        </div>
        <div v-for="f in providerFields" :key="f.key" class="form-row">
          <label>{{ f.label }}</label>
          <input :type="f.type" v-model="editor.config[f.key]" :placeholder="f.placeholder" />
        </div>
        <div class="form-row"><label>新增自定义字段</label>
          <div style="display:flex;gap:8px">
            <input v-model="newCustomFieldKey" placeholder="字段 key" style="flex:1" />
            <button class="btn btn-ghost" @click="addCustomField">添加</button>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="editor.show = false">取消</button>
          <button class="btn btn-primary" :disabled="saving || !editor.modelName" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
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
// 契约对齐 cc-console MODEL_TYPES
const MODEL_TYPES = [
  { value: 'TTS', label: '🔊 TTS 语音合成' },
  { value: 'LLM', label: '🧠 LLM 大语言' },
  { value: 'ASR', label: '🎙 ASR 语音识别' },
  { value: 'VLLM', label: '👁 VLLM 视觉' },
  { value: 'Intent', label: '🎯 Intent 意图' },
  { value: 'Memory', label: '💾 Memory 记忆' },
  { value: 'VAD', label: '〰 VAD 活动检测' },
  { value: 'Plugin', label: '🔌 Plugin 插件' },
  { value: 'RAG', label: '📚 RAG 知识库' }
]
const models = ref([])
const activeType = ref('LLM')
const loading = ref(false)
const saving = ref(false)
const lastTest = ref('')
const providers = ref([])
const providerFields = ref([])
const newCustomFieldKey = ref('')
const editor = reactive({ show: false, id: '', providerCode: '', modelName: '', customType: 'openai', config: {} })

async function load() {
  loading.value = true
  try {
    const res = await adminApi.modelList(activeType.value)
    models.value = res.data?.list || []
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

function pickType(t) { activeType.value = t; load() }

async function test(m) {
  lastTest.value = m.modelName
  try {
    const res = await adminApi.modelTest(m.id, activeType.value)
    toast(`「${m.modelName}」连通: ${res.data?.message || res.msg || 'OK'}`)
  } catch (e) { toast(`「${m.modelName}」测试失败: ${e.msg || ''}`, 'error') }
}

async function toggle(m) {
  // 契约：PUT /models/enable/{id}/{newStatus}，isEnabled 就地翻转
  const next = m.isEnabled ? 0 : 1
  try {
    await adminApi.enableModel(m.id, next)
    m.isEnabled = next
    toast(`「${m.modelName}」已${next ? '启用' : '停用'}`)
  } catch (e) { toast(e.msg || '操作失败（请检查权限）', 'error') }
}

function remove(m) {
  askConfirm({
    title: '删除模型', message: `确定删除「${m.modelName}」吗？`, danger: true,
    onOk: async () => {
      try { await adminApi.deleteModel(m.id); toast('已删除'); load() }
      catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}

// 契约对齐 cc-console：供应器动态表单
async function loadProviders() {
  const res = await adminApi.modelProvideTypes(activeType.value)
  providers.value = res.data || []
}

function parseProviderFields(providerCode) {
  if (providerCode === '__custom_openai__') {
    return [
      { key: 'api_key', label: 'API Key', type: 'password', placeholder: 'sk-...' },
      { key: 'base_url', label: '接口地址 Base URL', placeholder: 'https://api.example.com/v1' },
      { key: 'model_name', label: '模型名 Model', placeholder: 'gpt-4o / glm-4-flash / ...' }
    ]
  }
  const p = providers.value.find(x => x.providerCode === providerCode)
  if (!p || !p.fields) return []
  try {
    const arr = typeof p.fields === 'string' ? JSON.parse(p.fields) : p.fields
    return (arr || []).map(f => ({
      key: f.key || f.field || f.name,
      label: f.label || f.title || f.key || f.name,
      type: (f.type === 'password' || /key|secret|token/i.test(String(f.key || f.name))) ? 'password' : 'text',
      placeholder: f.placeholder || f.description || ''
    })).filter(f => f.key)
  } catch (e) { return [] }
}

function onProviderChange() {
  providerFields.value = parseProviderFields(editor.providerCode)
  if (editor.providerCode === '__custom_openai__') {
    editor.customType = editor.customType || 'openai'
    editor.config = { api_key: '', base_url: '', model_name: '' }
  } else {
    editor.config = {}
  }
}

function addCustomField() {
  const k = (newCustomFieldKey.value || '').trim()
  if (!k) return
  if (providerFields.value.some(f => f.key === k)) { toast('字段已存在', 'error'); return }
  providerFields.value = [...providerFields.value, { key: k, label: k, type: 'text', placeholder: k }]
  editor.config = { ...editor.config, [k]: '' }
  newCustomFieldKey.value = ''
}

async function openCreate() {
  await loadProviders()
  Object.assign(editor, {
    show: true, id: '',
    providerCode: (providers.value[0] || {}).providerCode || '__custom_openai__',
    modelName: '', customType: 'openai', config: {}
  })
  providerFields.value = parseProviderFields(editor.providerCode)
}

async function openEdit(m) {
  await loadProviders()
  const res = await adminApi.modelDetail(m.id)
  const d = res.data || {}
  const cfg = d.configJson || {}
  Object.assign(editor, {
    show: true, id: m.id,
    providerCode: d.providerCode || (cfg.type ? '__custom_openai__' : (providers.value[0] || {}).providerCode),
    modelName: d.modelName || m.modelName,
    customType: cfg.type || 'openai',
    config: { ...cfg }
  })
  providerFields.value = parseProviderFields(editor.providerCode)
  if (editor.providerCode === '__custom_openai__' && editor.id) {
    const extra = Object.keys(editor.config).filter(k => !providerFields.value.some(f => f.key === k))
    providerFields.value = [...providerFields.value, ...extra.map(k => ({ key: k, label: k, type: 'text', placeholder: k }))]
  }
}

async function save() {
  if (!editor.modelName) return
  saving.value = true
  try {
    // 契约对齐 cc-console saveModelConfig：config.type 必须注入
    const isCustom = editor.providerCode === '__custom_openai__'
    const providerCode = isCustom ? 'custom' : editor.providerCode
    const config = { ...editor.config }
    config.type = isCustom ? (editor.customType || 'openai') : providerCode
    const body = { modelName: editor.modelName, isDefault: 0, isEnabled: 1, configJson: config }
    if (editor.id) {
      await adminApi.updateModel(activeType.value, providerCode, editor.id, body)
    } else {
      await adminApi.createModel(activeType.value, providerCode, body)
    }
    toast('已保存'); editor.show = false; load()
  } catch (e) { toast(e.msg || '保存失败（可能需要超级管理员权限）', 'error') }
  finally { saving.value = false }
}

onMounted(() => { load() })
</script>

<style scoped>
.chip { padding: 8px 14px; border-radius: 999px; background: var(--bg-card); border: 1.5px solid var(--border); cursor: pointer; font-size: 12.5px; }
.chip.active { border-color: var(--primary); color: var(--primary); font-weight: 600; }
.form-row { margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row select { border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px; font-size: 14px; outline: none; font-family: var(--font); background: #fff; }
.form-row input:focus, .form-row select:focus { border-color: var(--primary); }
</style>
