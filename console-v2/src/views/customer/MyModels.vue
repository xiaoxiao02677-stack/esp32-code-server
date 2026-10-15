<template>
  <div>
    <div class="page-head">
      <div>
        <h1>我的 <span style="color:var(--primary)">模型</span></h1>
        <p class="sub">自定义模型与音色 · 审核通过后可在设备配置中使用</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="activeTab === 'models' ? openCreate() : openCreateVoice()">{{ activeTab === 'models' ? '＋ 新增模型' : '＋ 新增音色' }}</button>
        <button class="btn btn-ghost" :disabled="loading" @click="load">{{ loading ? '加载中…' : '↻ 刷新' }}</button>
      </div>
    </div>

    <!-- 审核提示条 -->
    <div class="notice">
      ⏳ 自定义模型/音色提交后需管理员审核，<b>审核通过前</b>不可在设备配置（智能体模型下拉）中使用。
    </div>

    <!-- chip tab：自定义模型 / 自定义音色 -->
    <div class="chips">
      <div class="chip" :class="{ active: activeTab === 'models' }" @click="switchTab('models')">🧩 自定义模型</div>
      <div class="chip" :class="{ active: activeTab === 'voices' }" @click="switchTab('voices')">🎙 自定义音色</div>
    </div>

    <DataTable v-if="activeTab === 'models'" title="模型清单" :total="models.length" :page="1" :pages="1">
      <table class="data-table">
        <thead>
          <tr><th>类型</th><th>名称</th><th>Base URL</th><th>密钥</th><th>审核</th><th>用量</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="m in models" :key="m.id">
            <td><span class="badge badge-blue"><span class="dot"></span>{{ m.modelType || '—' }}</span></td>
            <td>
              <div class="cell-main">{{ m.modelName }}</div>
              <div class="cell-sub">{{ m.providerCode || '通用' }}<template v-if="m.remark"> · {{ m.remark }}</template></div>
            </td>
            <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px" :title="m.baseUrl">{{ m.baseUrl || '—' }}</td>
            <td style="font-size:12px">{{ m.apiKeyMask || '—' }}</td>
            <td><span class="badge" :class="auditCls(m.auditStatus)"><span class="dot"></span>{{ auditText(m.auditStatus) }}</span></td>
            <td style="font-size:12px;color:var(--text-sub)">{{ m.usedCount ?? 0 }} / {{ m.quotaLimit == null ? '不限' : m.quotaLimit }}</td>
            <td><span class="badge" :class="m.status === 0 ? 'badge-gray' : 'badge-green'"><span class="dot"></span>{{ m.status === 0 ? '停用' : '启用' }}</span></td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="openEdit(m)">编辑</button>
                <button class="link-btn" :disabled="healthId === m.id" @click="checkHealth(m)">{{ healthId === m.id ? '检测中…' : '健康检查' }}</button>
                <button class="link-btn danger" @click="removeModel(m)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="models.length === 0" class="empty-state">
        <div class="empty-icon">🧩</div>
        <strong>暂无自定义模型</strong>
        <p>点击右上角「＋ 新增模型」接入自己的 LLM / ASR / TTS 服务</p>
      </div>
    </DataTable>

    <DataTable v-if="activeTab === 'voices'" title="音色清单" :total="voices.length" :page="1" :pages="1">
      <table class="data-table">
        <thead>
          <tr><th>名称</th><th>TTS 模型</th><th>音色编码</th><th>语言</th><th>参考音频</th><th>审核</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="v in voices" :key="v.id">
            <td>
              <div class="cell-main">{{ v.name }}</div>
              <div class="cell-sub">{{ v.remark || '—' }}</div>
            </td>
            <td style="font-size:12px">{{ v.ttsModelId || '—' }}</td>
            <td style="font-size:12px">{{ v.voiceCode || '—' }}</td>
            <td style="font-size:12px">{{ v.language || '—' }}</td>
            <td style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px" :title="v.referenceAudio">{{ v.referenceAudio || '—' }}</td>
            <td><span class="badge" :class="auditCls(v.auditStatus)"><span class="dot"></span>{{ auditText(v.auditStatus) }}</span></td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="openEditVoice(v)">编辑</button>
                <button class="link-btn danger" @click="removeVoice(v)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="voices.length === 0" class="empty-state">
        <div class="empty-icon">🎙</div>
        <strong>暂无自定义音色</strong>
        <p>点击右上角「＋ 新增音色」创建你的专属声音</p>
      </div>
    </DataTable>

    <!-- 新建/编辑模型弹窗 -->
    <div v-if="editor.show" class="modal-mask" @click.self="editor.show = false">
      <div class="modal" style="width:min(640px,94vw);max-height:88vh;overflow:auto">
        <h3>{{ editor.id ? '编辑模型' : '新建模型' }}</h3>
        <div class="edit-grid">
          <div class="form-row"><label>模型类型</label>
            <select v-model="editor.modelType">
              <option v-for="t in MODEL_TYPES" :key="t" :value="t">{{ t }}</option>
            </select>
          </div>
          <div class="form-row"><label>名称 *</label><input v-model="editor.modelName" placeholder="如：我的 DeepSeek" /></div>
          <div class="form-row"><label>供应器编码</label><input v-model="editor.providerCode" placeholder="可空，如 openai（用于匹配驱动）" /></div>
          <div class="form-row"><label>Base URL *</label><input v-model="editor.baseUrl" placeholder="https://api.example.com/v1" /></div>
          <div class="form-row"><label>API Key</label><input v-model="editor.apiKey" type="password" :placeholder="editor.id ? '留空则不修改' : 'sk-...'" /></div>
        </div>
        <div class="form-row"><label>备注</label><textarea v-model="editor.remark" rows="2" placeholder="用途说明（可空）"></textarea></div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="editor.show = false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="saveModel">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>

    <!-- 新建/编辑音色弹窗 -->
    <div v-if="vEditor.show" class="modal-mask" @click.self="vEditor.show = false">
      <div class="modal" style="width:min(640px,94vw);max-height:88vh;overflow:auto">
        <h3>{{ vEditor.id ? '编辑音色' : '新建音色' }}</h3>
        <div class="edit-grid">
          <div class="form-row"><label>名称 *</label><input v-model="vEditor.name" placeholder="如：温柔女声" /></div>
          <div class="form-row"><label>TTS 模型 ID *</label><input v-model="vEditor.ttsModelId" placeholder="对应平台的 TTS 模型 id" /></div>
          <div class="form-row"><label>音色编码</label><input v-model="vEditor.voiceCode" placeholder="如 zh-CN-XiaoyiNeural（可空）" /></div>
          <div class="form-row"><label>语言</label><input v-model="vEditor.language" placeholder="如 zh-CN（可空）" /></div>
        </div>
        <div class="form-row"><label>参考音频路径</label><input v-model="vEditor.referenceAudio" placeholder="referenceAudio 存储路径（可空）" /></div>
        <div class="form-row"><label>参考文本</label><textarea v-model="vEditor.referenceText" rows="2" placeholder="参考音频对应文本（可空）"></textarea></div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="vEditor.show = false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="saveVoice">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { inject, onMounted, reactive, ref } from 'vue'
import DataTable from '../../components/DataTable.vue'
import { api } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')

const MODEL_TYPES = ['LLM', 'ASR', 'TTS']
const activeTab = ref('models')
const models = ref([])
const voices = ref([])
const loading = ref(false)
const saving = ref(false)
const healthId = ref('')
let warned = false

const editor = reactive({ show: false, id: '', modelType: 'LLM', modelName: '', providerCode: '', baseUrl: '', apiKey: '', remark: '' })
const vEditor = reactive({ show: false, id: '', name: '', ttsModelId: '', voiceCode: '', language: '', referenceAudio: '', referenceText: '' })

function auditCls(s) {
  return s === 1 ? 'badge-green' : s === 2 ? 'badge-danger' : 'badge-orange'
}
function auditText(s) {
  return s === 1 ? '已通过' : s === 2 ? '已驳回' : '待审核'
}

function switchTab(t) {
  if (activeTab.value === t) return
  activeTab.value = t
  load()
}

async function load() {
  loading.value = true
  try {
    if (activeTab.value === 'models') {
      const res = await api.get('/user/custom-models', { params: { page: 1, limit: 100 } })
      const data = res.data
      const list = Array.isArray(data) ? data : (data?.list || [])
      models.value = list.map(m => ({
        id: m.id,
        modelType: m.modelType || 'LLM',
        modelName: m.modelName || '未命名模型',
        providerCode: m.providerCode || '',
        baseUrl: m.baseUrl || '',
        apiKeyMask: m.apiKeyMask != null ? m.apiKeyMask : (m.apiKey ? maskKey(m.apiKey) : ''),
        auditStatus: m.auditStatus != null ? m.auditStatus : 0,
        usedCount: m.usedCount,
        quotaLimit: m.quotaLimit,
        status: m.status != null ? m.status : 1,
        remark: m.remark || ''
      }))
    } else {
      const res = await api.get('/user/custom-voices', { params: { page: 1, limit: 100 } })
      const data = res.data
      const list = Array.isArray(data) ? data : (data?.list || [])
      voices.value = list.map(v => ({
        id: v.id,
        name: v.name || v.voiceName || '未命名音色',
        ttsModelId: v.ttsModelId || '',
        voiceCode: v.voiceCode || '',
        language: v.language || '',
        referenceAudio: v.referenceAudio || '',
        referenceText: v.referenceText || '',
        auditStatus: v.auditStatus != null ? v.auditStatus : 0,
        remark: v.remark || ''
      }))
    }
  } catch (e) {
    // 未登录/权限被拒：静默降级（数据置空，只 toast 一次）
    models.value = []
    voices.value = []
    if (!warned) { warned = true; toast(e.msg || '加载失败', 'error') }
  } finally {
    loading.value = false
  }
}

function maskKey(k) {
  const s = String(k)
  return s.length > 8 ? s.slice(0, 4) + '****' + s.slice(-4) : s ? s.slice(0, 2) + '****' : ''
}

// 同型同名前端查重（提交前提示，后端 10234 仍兜底）
function duplicateName() {
  return models.value.some(m => String(m.modelName).trim() === String(editor.modelName).trim() && m.id !== editor.id)
}

function openCreate() {
  Object.assign(editor, { show: true, id: '', modelType: 'LLM', modelName: '', providerCode: '', baseUrl: '', apiKey: '', remark: '' })
  vEditor.show = false
}
function openEdit(m) {
  Object.assign(editor, { show: true, id: m.id, modelType: m.modelType || 'LLM', modelName: m.modelName, providerCode: m.providerCode, baseUrl: m.baseUrl, apiKey: '', remark: m.remark })
  vEditor.show = false
}

async function saveModel() {
  if (!editor.modelName.trim()) { toast('请填写模型名称', 'error'); return }
  if (!editor.baseUrl.trim()) { toast('请填写 Base URL', 'error'); return }
  if (duplicateName()) { toast('同类型下已存在同名模型', 'error'); return }
  saving.value = true
  try {
    const body = {
      modelType: editor.modelType,
      modelName: editor.modelName.trim(),
      providerCode: editor.providerCode || '',
      baseUrl: editor.baseUrl.trim(),
      remark: editor.remark || ''
    }
    // 编辑时 apiKey 留空 = 不修改（后端契约）
    if (editor.apiKey) body.apiKey = editor.apiKey
    if (editor.id) await api.put('/user/custom-models/' + editor.id, body)
    else await api.post('/user/custom-models', body)
    toast('已保存')
    editor.show = false
    load()
  } catch (e) {
    toast(e.msg || '保存失败', 'error')
  } finally {
    saving.value = false
  }
}

function removeModel(m) {
  askConfirm({
    title: '删除自定义模型',
    message: `确定删除「${m.modelName}」吗？此操作不可恢复。`,
    danger: true,
    onOk: async () => {
      try { await api.del('/user/custom-models/' + m.id); toast('已删除'); load() }
      catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}

async function checkHealth(m) {
  healthId.value = m.id
  try {
    const res = await api.post('/user/custom-models/' + m.id + '/health', {})
    const d = res.data || {}
    const latency = d.latencyMs != null ? d.latencyMs : null
    if (d.status === 1) toast(`健康检查正常${latency != null ? '（' + latency + 'ms）' : ''}`)
    else toast(`健康检查异常${latency != null ? '（' + latency + 'ms）' : ''}`, 'error')
  } catch (e) {
    toast('健康检查异常：' + (e.msg || '网络错误'), 'error')
  } finally {
    healthId.value = ''
  }
}

function openEditVoice(v) {
  Object.assign(vEditor, {
    show: true, id: v.id, name: v.name, ttsModelId: v.ttsModelId,
    voiceCode: v.voiceCode, language: v.language,
    referenceAudio: v.referenceAudio, referenceText: v.referenceText
  })
  editor.show = false
}
function openCreateVoice() {
  Object.assign(vEditor, { show: true, id: '', name: '', ttsModelId: '', voiceCode: '', language: '', referenceAudio: '', referenceText: '' })
  editor.show = false
}

async function saveVoice() {
  if (!vEditor.name.trim()) { toast('请填写音色名称', 'error'); return }
  if (!vEditor.ttsModelId.trim()) { toast('请填写 TTS 模型 ID', 'error'); return }
  saving.value = true
  try {
    const body = {
      name: vEditor.name.trim(),
      ttsModelId: vEditor.ttsModelId.trim(),
      voiceCode: vEditor.voiceCode || '',
      language: vEditor.language || '',
      referenceAudio: vEditor.referenceAudio || '',
      referenceText: vEditor.referenceText || ''
    }
    if (vEditor.id) await api.put('/user/custom-voices/' + vEditor.id, body)
    else await api.post('/user/custom-voices', body)
    toast('已保存')
    vEditor.show = false
    load()
  } catch (e) {
    toast(e.msg || '保存失败', 'error')
  } finally {
    saving.value = false
  }
}

function removeVoice(v) {
  askConfirm({
    title: '删除自定义音色',
    message: `确定删除「${v.name}」吗？此操作不可恢复。`,
    danger: true,
    onOk: async () => {
      try { await api.del('/user/custom-voices/' + v.id); toast('已删除'); load() }
      catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}

onMounted(load)
</script>

<style scoped>
.notice {
  background: var(--primary-soft, #EAF2FF); border: 1px solid var(--primary);
  border-radius: 14px; padding: 12px 16px; margin-bottom: 16px;
  font-size: 13px; color: var(--text);
}
.chips { display: flex; gap: 10px; margin-bottom: 16px; }
.chip {
  padding: 8px 16px; border-radius: 999px; cursor: pointer; font-size: 13px;
  background: var(--bg-card, var(--surface)); border: 1.5px solid var(--border);
  color: var(--text-sub); user-select: none;
}
.chip.active { border-color: var(--primary); color: var(--primary); background: var(--primary-soft, #EAF2FF); font-weight: 700; }

.badge-danger { background: var(--danger-soft, #FDECEC); color: var(--danger); border: 1px solid var(--danger); }
.modal-mask { position: fixed; inset: 0; background: rgba(15,22,40,.45); display: grid; place-items: center; z-index: 100; }
.modal { background: #fff; border-radius: 20px; padding: 26px; width: min(440px, 92vw); box-shadow: 0 24px 60px rgba(0,0,0,.2); }
.modal h3 { font-size: 17px; margin-bottom: 18px; }
.edit-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px 16px; }
.form-row { margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row textarea, .form-row select {
  border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px;
  font-size: 14px; outline: none; font-family: var(--font); background: #fff;
}
.form-row input:focus, .form-row textarea:focus, .form-row select:focus { border-color: var(--primary); }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 6px; }
</style>
