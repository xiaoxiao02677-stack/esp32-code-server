<template>
  <div>
    <div class="page-head">
      <div>
        <h1>模型 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">契约对齐 /cc/：9 类型 / 供应器动态表单 / 新增编辑删除 / 启停测试</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="openCreate">＋ 新增{{ activeType }}模型</button>
        <button class="btn btn-ghost" @click="loadAll" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="🧩" label="模型总数" :value="totalCount" :note="`当前 ${activeType}`" />
      <StatCard icon="✅" label="启用中" :value="enabledCount" :note="`${activeType} 类型`" />
      <StatCard icon="🔌" label="连通测试" :value="lastTest || '—'" />
    </div>

    <!-- 契约对齐 cc-console MODEL_TYPES：9 类型（预加载全量计数） -->
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px">
      <div v-for="t in MODEL_TYPES" :key="t.value" class="chip" :class="{ active: activeType === t.value }" @click="pickType(t.value)">
        {{ t.label }} ({{ modelTypeCount(t.value) }})
      </div>
    </div>

    <DataTable title="模型列表" :total="models.length" :page="1" :pages="1">
      <template #actions>
        <button class="link-btn" @click="loadAll" :disabled="loading">{{ loading ? '加载中…' : '↻ 刷新' }}</button>
      </template>
      <table class="data-table">
        <thead><tr><th>模型</th><th>类型</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="m in models" :key="m.id">
            <td>
              <div class="cell-main">{{ m.modelName }}</div>
              <div class="cell-sub">{{ m.id }}</div>
              <div v-if="testState[m.id] && testState[m.id].text" class="model-test-result" :class="testState[m.id].ok === true ? 'test-ok' : (testState[m.id].ok === false ? 'test-fail' : '')">
                {{ testState[m.id].text }}
              </div>
            </td>
            <td>{{ m.modelType || activeType }}</td>
            <td>
              <span class="badge" :class="m.isEnabled ? 'badge-green' : 'badge-gray'">
                <span class="dot"></span>{{ m.isEnabled ? '启用' : '停用' }}
              </span>
            </td>
            <td>
              <div class="row-actions">
                <button class="link-btn" :disabled="testState[m.id] && testState[m.id].loading" @click="test(m)">
                  {{ testState[m.id] && testState[m.id].loading ? '测试中…' : '测试' }}
                </button>
                <button class="link-btn" @click="toggle(m)">{{ m.isEnabled ? '停用' : '启用' }}</button>
                <button class="link-btn" @click="openEdit(m)">编辑</button>
                <button class="link-btn danger" @click="remove(m)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="models.length === 0" class="empty-state"><div class="empty-icon">🧩</div><strong>此类型暂无模型</strong><p>点右上「＋ 新增{{ activeType }}模型」创建</p></div>
    </DataTable>

    <!-- 模型编辑弹窗（契约对齐 cc-console openModelEdit/saveModelConfig） -->
    <div v-if="editor.show" class="modal-mask" @click.self="editor.show = false">
      <div class="modal" style="width:min(640px,94vw);max-height:88vh;overflow:auto">
        <h3>{{ editor.id ? '编辑模型' : '新增模型' }}（{{ activeType }}）</h3>
        <div class="form-row"><label>供应器</label>
          <select v-model="editor.providerCode" @change="onProviderChange">
            <option v-for="p in providers" :key="p.providerCode" :value="p.providerCode">{{ p.providerName || p.providerCode }}</option>
            <option value="__custom_openai__">⭐ 自定义接口（OpenAI 兼容）</option>
          </select>
        </div>
        <div class="form-row"><label>模型名</label><input v-model="editor.modelName" placeholder="显示名称" /></div>
        <div v-if="editor.providerCode === '__custom_openai__'" class="form-row"><label>接口类型</label>
          <input v-model="editor.customType" placeholder="openai" />
        </div>
        <div v-for="f in providerFields" :key="f.key" class="form-row">
          <label>{{ f.label }}</label>
          <div style="display:flex;gap:8px;align-items:center">
            <input :type="f.type" v-model="editor.config[f.key]" :placeholder="f.placeholder" style="flex:1" />
            <button v-if="editor.providerCode === '__custom_openai__'" class="link-btn danger" title="删除字段" @click="removeCustomField(f.key)">✕</button>
          </div>
        </div>
        <div class="form-row"><label>新增自定义字段</label>
          <div style="display:flex;gap:8px">
            <input v-model="newCustomFieldKey" placeholder="字段 key" style="flex:1" />
            <button class="btn btn-ghost" @click="addCustomField">添加</button>
          </div>
        </div>
        <!-- 自定义接口：保存前直连测试（跨域被拦时提示改走服务端「一键测试」） -->
        <div v-if="isCustomOpenAI" class="form-row custom-test-row">
          <label>连接测试</label>
          <div class="custom-test-bar">
            <button class="btn btn-ghost" :disabled="customTest.loading || !customTestReady" @click="testCustomNow">
              {{ customTest.loading ? '测试中…' : '⚡ 测试连接' }}
            </button>
            <span v-if="customTest.text" class="model-test-result inline" :class="customTest.ok === true ? 'test-ok' : (customTest.ok === false ? 'test-fail' : '')">{{ customTest.text }}</span>
          </div>
          <p class="custom-test-hint">保存前从浏览器直连测试；若被 CORS 拦截，保存后可用列表行「测试」走服务端测试（权威）。</p>
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
import { computed, inject, onMounted, reactive, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')

// 契约对齐 cc-console App.vue:948-958 MODEL_TYPES（9 类，含 emoji 标签）
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

// 契约对齐 cc-console modelsByType / activeModelType / testState
const modelsByType = reactive({})
const testState = reactive({})
const activeType = ref('TTS')
const loading = ref(false)
const saving = ref(false)
const lastTest = ref('')
const providers = ref([])
const providerFields = ref([])
const newCustomFieldKey = ref('')
const editor = reactive({ show: false, id: '', providerCode: '', modelName: '', customType: 'openai', config: {} })
// 自定义接口直连测试（保存前）：{loading, ok, text}
const customTest = reactive({ loading: false, ok: null, text: '' })

// 当前类型缓存视图（切换 tab 不重复请求）
const models = computed(() => modelsByType[activeType.value] || [])
const totalCount = computed(() => MODEL_TYPES.reduce((n, t) => n + modelTypeCount(t.value), 0))
const enabledCount = computed(() => models.value.filter(m => m.isEnabled).length)
const isCustomOpenAI = computed(() => activeType.value === 'LLM' && editor.providerCode === '__custom_openai__')
// baseUrl / apiKey / model 至少各有一项才允许发起测试（apiKey 允许为空，兼容本地网关）
const customTestReady = computed(() => {
  if (!isCustomOpenAI.value) return false
  const cfg = editor.config || {}
  return !!(String(cfg.base_url || '').trim() && String(cfg.model_name || '').trim())
})

function modelTypeCount(t) {
  return (modelsByType[t] || []).length
}

// 进入页面一次性并行预加载全部 9 类；单类型失败不阻塞其他（置空数组）
async function loadAll() {
  loading.value = true
  await Promise.all(MODEL_TYPES.map(async t => {
    try {
      const res = await adminApi.modelList(t.value)
      modelsByType[t.value] = res.data?.list || []
    } catch (e) {
      modelsByType[t.value] = []
      if (t.value === activeType.value) toast(`「${t.label}」加载失败: ${e.msg || ''}`, 'error')
    }
  }))
  loading.value = false
}

async function load() {
  try {
    const res = await adminApi.modelList(activeType.value)
    modelsByType[activeType.value] = res.data?.list || []
  } catch (e) { toast(e.msg || '加载失败', 'error') }
}

function pickType(t) {
  activeType.value = t
  if (!modelsByType[t]) load()
}

// 契约对齐 cc-console testModel：testState[id] = {loading, ok, text}
async function test(m) {
  testState[m.id] = { loading: true, ok: null, text: '⏳ 测试中…' }
  lastTest.value = m.modelName
  try {
    const res = await adminApi.modelTest(m.id, activeType.value)
    const d = res.data || {}
    testState[m.id] = {
      loading: false,
      ok: !!d.ok,
      text: (d.ok ? '✅ ' : '❌ ') + (d.message || '') + (d.elapsed_ms != null ? `（${d.elapsed_ms}ms）` : '')
    }
  } catch (e) {
    testState[m.id] = { loading: false, ok: false, text: '❌ 请求异常：' + (e.msg || e.message || '') }
  }
}

// 自定义接口直连测试（保存前）：POST {base_url}/chat/completions，10s 超时
async function testCustomNow() {
  if (customTest.loading) return
  const cfg = editor.config || {}
  const baseUrl = String(cfg.base_url || '').trim().replace(/\/+$/, '')
  const modelName = String(cfg.model_name || '').trim()
  const apiKey = String(cfg.api_key || '').trim()
  if (!baseUrl || !modelName) { customTest.ok = false; customTest.text = '❌ 请先填写接口地址和模型名'; return }

  customTest.loading = true
  customTest.ok = null
  customTest.text = '⏳ 连接中…'
  const startedAt = performance.now()
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 10000)
  try {
    const res = await fetch(baseUrl + '/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}) },
      body: JSON.stringify({ model: modelName, messages: [{ role: 'user', content: 'ping' }] }),
      signal: controller.signal
    })
    const elapsed = Math.round(performance.now() - startedAt)
    if (res.ok) {
      customTest.ok = true
      customTest.text = `✅ 连接成功（HTTP ${res.status}，${elapsed}ms）`
    } else {
      const bodyText = await res.text().catch(() => '')
      let detail = `HTTP ${res.status}`
      try { const j = JSON.parse(bodyText); detail = j.error?.message || j.message || detail } catch (e) { if (bodyText) detail = bodyText.slice(0, 120) }
      customTest.ok = false
      customTest.text = `❌ 接口返回失败：${detail}（${elapsed}ms）`
    }
  } catch (e) {
    if (e.name === 'AbortError') {
      customTest.ok = false
      customTest.text = '❌ 测试超时（10s），请检查接口地址或网络'
    } else {
      // fetch TypeError = 网络错 / CORS 拦截
      customTest.ok = false
      customTest.text = '❌ 直接测试失败（可能被浏览器 CORS 拦截）'
      toast('直接测试失败（可能被浏览器 CORS 拦截），请保存后用「一键测试」走服务端测试', 'error')
    }
  } finally {
    clearTimeout(timer)
    customTest.loading = false
  }
}

function resetCustomTest() {
  customTest.loading = false
  customTest.ok = null
  customTest.text = ''
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
      try {
        await adminApi.deleteModel(m.id)
        toast('已删除')
        await load()
      } catch (e) { toast(e.msg || '删除失败', 'error') }
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
  resetCustomTest()
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

function removeCustomField(k) {
  providerFields.value = providerFields.value.filter(f => f.key !== k)
  delete editor.config[k]
}

async function openCreate() {
  await loadProviders()
  resetCustomTest()
  Object.assign(editor, {
    show: true, id: '',
    providerCode: (providers.value[0] || {}).providerCode || '__custom_openai__',
    modelName: '', customType: 'openai', config: {}
  })
  providerFields.value = parseProviderFields(editor.providerCode)
}

async function openEdit(m) {
  await loadProviders()
  resetCustomTest()
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
  // 自定义接口编辑：把 configJson 现有键都展示为可编辑字段
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
    toast('已保存')
    editor.show = false
    await load()
  } catch (e) { toast(e.msg || '保存失败（可能需要超级管理员权限）', 'error') }
  finally { saving.value = false }
}

onMounted(loadAll)
</script>

<style scoped>
.chip { padding: 8px 14px; border-radius: 999px; background: var(--bg-card); border: 1.5px solid var(--border); cursor: pointer; font-size: 12.5px; }
.chip.active { border-color: var(--primary); color: var(--primary); font-weight: 600; }
.form-row { margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row select { border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px; font-size: 14px; outline: none; font-family: var(--font); background: #fff; }
.form-row input:focus, .form-row select:focus { border-color: var(--primary); }
.model-test-result { margin-top: 6px; font-size: 12px; line-height: 1.5; }
.model-test-result.inline { margin-top: 0; }
.model-test-result.test-ok { color: var(--success); }
.model-test-result.test-fail { color: var(--danger); }
.custom-test-row .custom-test-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.custom-test-row .custom-test-hint { margin: 2px 0 0; font-size: 12px; color: var(--text-sub); line-height: 1.5; }
</style>
