<template>
  <div>
    <div class="page-head">
      <div>
        <h1>智能体 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">配置智能体的模型、音色与设备绑定</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="openCreate">＋ 新增智能体</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="bot" label="智能体" :value="agents.length" />
      <StatCard icon="device" label="绑定设备" :value="boundTotal" />
      <StatCard icon="chat" label="会话" :value="sessionCount" note="选中智能体" />
    </div>

    <DataTable title="智能体清单" :total="agents.length" :page="1" :pages="1" :loading="loading">
      <table class="data-table">
        <thead><tr><th>智能体</th><th>模型</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="a in agents" :key="a.id">
            <td>
              <div class="cell-main">{{ a.name }}</div>
              <div class="cell-sub">{{ a.boundCount ? `📡 ${a.boundCount} 台设备` : '未绑定设备' }}</div>
            </td>
            <td style="font-size:12px">{{ a.llmModel || '—' }}<br />{{ a.ttsModel || '—' }}</td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="loadSessions(a)">会话</button>
                <button class="link-btn" @click="loadMcp(a)">MCP</button>
                <button class="link-btn" @click="openEdit(a)">编辑</button>
                <button class="link-btn danger" @click="remove(a)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="agents.length === 0" class="empty-state">
        <div class="empty-icon"><YhIcon name="bot" /></div><strong>暂无智能体</strong>
        <p>点击右上角「新增智能体」创建第一个</p>
      </div>
    </DataTable>

    <!-- 会话列表 -->
    <div v-if="sessions.show" class="modal-mask" @click.self="sessions.show = false">
      <div class="modal" style="width:min(560px,94vw)">
        <h3>会话 — {{ sessions.agentName }}</h3>
        <table class="data-table">
          <thead><tr><th>会话 ID</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="s in sessions.list" :key="s.sessionId">
              <td style="font-size:12px">{{ s.sessionId }}</td>
              <td><button class="link-btn" @click="goChat(s)">查看聊天</button></td>
            </tr>
          </tbody>
        </table>
        <div class="modal-actions" style="margin-top:14px">
          <button class="btn btn-ghost" @click="sessions.show = false">关闭</button>
        </div>
      </div>
    </div>

    <!-- 编辑弹窗（全量 12 项配置，契约对齐 cc-console openAgentEdit/persistAgent） -->
    <div v-if="editor.show" class="modal-mask" @click.self="editor.show = false">
      <div class="modal" style="width:min(720px,94vw);max-height:88vh;overflow:auto">
        <h3>{{ editor.id ? '编辑智能体' : '新建智能体' }}</h3>

        <div class="edit-grid">
          <div class="form-row"><label>名字</label><input v-model="form.agentName" placeholder="给 AI 起个名字" /></div>
          <div class="form-row"><label>大脑（LLM）</label>
            <select v-model="form.llmModelId">
              <option v-for="m in opts.LLM" :key="m.id" :value="m.id">{{ m.modelName }}</option>
            </select>
          </div>
          <div class="form-row"><label>声音引擎（TTS）</label>
            <select v-model="form.ttsModelId" @change="loadEditVoices">
              <option v-for="m in opts.TTS" :key="m.id" :value="m.id">{{ m.modelName }}</option>
            </select>
          </div>
          <div class="form-row"><label>音色</label>
            <select v-model="form.ttsVoiceId">
              <option v-if="!editVoices.length" value="">（先选 TTS 引擎）</option>
              <option v-for="v in editVoices" :key="v.id" :value="v.id">{{ v.name }}</option>
            </select>
          </div>
          <div class="form-row"><label>记忆</label>
            <select v-model="form.memModelId">
              <option v-for="m in opts.Memory" :key="m.id" :value="m.id">{{ m.modelName }}</option>
            </select>
            <p v-if="memHint" class="field-hint">{{ memHint }}</p>
          </div>
          <div class="form-row"><label>意图配置</label>
            <select v-model="form.intentModelId">
              <option v-for="m in opts.Intent" :key="m.id" :value="m.id">{{ m.modelName }}</option>
            </select>
            <p v-if="intentHint" class="field-hint">{{ intentHint }}</p>
          </div>
          <div class="form-row"><label>语音识别（ASR）</label>
            <select v-model="form.asrModelId">
              <option v-for="m in opts.ASR" :key="m.id" :value="m.id">{{ m.modelName }}</option>
            </select>
          </div>
          <div class="form-row"><label>聊天上报</label>
            <select v-model.number="form.chatHistoryConf">
              <option :value="0">不上报</option>
              <option :value="1">仅文字</option>
              <option :value="2">文字+音频</option>
            </select>
          </div>
          <div class="form-row"><label>语速 (-50~100)</label>
            <input v-model.number="form.ttsRate" type="number" min="-50" max="100" placeholder="0" />
          </div>
        </div>

        <div class="form-row"><label>唤醒词（多个用分号 ; 分隔，留空使用默认）</label>
          <input v-model.trim="editor.wakeWords" placeholder="如：你好;早上好" />
          <p class="field-hint">设备待机唤醒由固件本地模型负责；此处唤醒词用于服务器识别与快速应答</p>
        </div>

        <div class="form-row"><label>唤醒词阈值（0~100，0 最灵敏，100 最不灵敏）</label>
          <input v-model.number="editor.wakeWordThreshold" type="number" min="0" max="100"
                 placeholder="留空使用设备默认（40）" />
          <p class="field-hint">保存后立即下发到绑定设备热生效，无需重启；数值越小越容易唤醒</p>
        </div>

        <div class="form-row">
          <label>实时打断阈值（0~100，拉选调节）</label>
          <div class="slider-row">
            <input v-model.number="editor.interruptThreshold" type="range" min="0" max="100" step="1"
                   class="slider" :style="{ '--pct': editor.interruptThreshold + '%' }" />
            <span class="slider-value">{{ editor.interruptThreshold }}</span>
          </div>
          <p class="field-hint">
            播放时用户说话打断的灵敏度：0 最灵敏（立即打断）· 100 最难打断（连续 2 秒人声才打断）· 默认 15 ≈ 300ms
          </p>
        </div>

        <div class="form-row"><label>人设提示词（它怎么说话）</label>
          <textarea v-model="form.systemPrompt" rows="5" placeholder="比如：你是温柔可爱的助手，说话简短口语化"></textarea>
        </div>

        <!-- 设备绑定区（契约对齐 cc-console：保存后配置生效） -->
        <div class="bind-box">
          <div class="bind-label">📱 设备绑定<span v-if="editor.id">（保存后配置生效）</span></div>

          <div v-if="boundDevices.length" class="bound-list">
            <div v-for="d in boundDevices" :key="d.id" class="bound-item">
              <span>{{ d.alias || d.id }}</span>
              <button class="link-btn danger" @click="unbindDevice(d)">解绑</button>
            </div>
          </div>
          <p v-else class="bind-empty">
            ⚠️ {{ editor.id ? '该智能体还没有绑定任何设备，设备将无法使用它对话。' : '先保存智能体后再绑定设备。' }}请在下方输入设备屏幕显示的 6 位验证码完成绑定。
          </p>

          <div class="bind-code-row">
            <input v-model="bindCode" placeholder="设备上的 6 位验证码" maxlength="6" inputmode="numeric" />
            <button class="btn btn-primary" :disabled="!(/^\d{6}$/.test(bindCode)) || bindBusy" @click="bindByCode">
              {{ bindBusy ? '绑定中…' : '验证码绑定' }}
            </button>
          </div>

          <details class="manual-add">
            <summary>手动录入 MAC 添加设备</summary>
            <div class="edit-grid" style="margin-top:10px">
              <div class="form-row"><label>板型</label><input v-model="manual.board" placeholder="如 my-s3-tft（可空）" /></div>
              <div class="form-row"><label>固件版本</label><input v-model="manual.appVersion" placeholder="如 2.5.1（可空）" /></div>
              <div class="form-row"><label>MAC 地址 *</label><input v-model="manual.macAddress" placeholder="14:c1:9f:xx:xx:xx" /></div>
            </div>
            <button class="btn btn-ghost" :disabled="!manual.macAddress || bindBusy" @click="manualAdd">＋ 手动添加设备</button>
          </details>
        </div>

        <div class="modal-actions">
          <button class="btn btn-ghost" @click="editor.show = false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import YhIcon from '../../components/YhIcon.vue'
import { computed, inject, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi, api } from '../../lib/api'

const router = useRouter()
const toast = inject('toast')
const askConfirm = inject('askConfirm')

const agents = ref([])
const loading = ref(false)
const saving = ref(false)
const boundTotal = ref(0)
const sessionCount = ref(0)
const sessions = reactive({ show: false, agentName: '', agentId: null, list: [] })

// 编辑弹窗状态（契约字段与 cc-console editForm 一致；wakeWords 分号分隔，空=默认「你好」；
// wakeWordThreshold 唤醒词阈值 0~100（0=最灵敏），interruptThreshold 实时打断阈值
// 0~100（0=最容易打断）；两者 未设置时显示设备默认）
const editor = reactive({ show: false, id: '', wakeWords: '', wakeWordThreshold: '', interruptThreshold: 15 })
const form = reactive({
  agentName: '', llmModelId: '', ttsModelId: '', ttsVoiceId: '',
  memModelId: '', intentModelId: '', asrModelId: '',
  chatHistoryConf: 2, ttsRate: 0, systemPrompt: ''
})
const opts = reactive({ LLM: [], TTS: [], Memory: [], ASR: [], Intent: [] })
const editVoices = ref([])
const boundDevices = ref([])
const bindCode = ref('')
const bindBusy = ref(false)
const manual = reactive({ board: '', appVersion: '', macAddress: '' })

const MEM_HINTS = {
  Memory_mem_hybrid: '⭐ 推荐：短期 LLM 滚动总结 + Holographic 长期事实库 + LLM 自动沉淀（隐式信息也能记住）',
  Memory_mem_holographic: '本地全息记忆：自动抽取事实/时间线/实体，功能最全',
  Memory_mem_local_short: '短期记忆：对话摘要总结，轻量省 token',
  Memory_mem_report_only: '仅上报聊天记录，不生成记忆',
  Memory_nomem: '完全关闭记忆',
  Memory_mem0ai: '需要 Mem0AI API Key（模型管理里配置后启用）',
  Memory_powermem: '需要 PowerMem 凭据（模型管理里配置后启用）'
}
const INTENT_HINTS = {
  Intent_function_call: '推荐：大模型自主决定何时调工具（音量/天气/音乐等）',
  Intent_intent_llm: '外挂专用小模型识别意图（省主模型 token）',
  Intent_nointent: '跳过意图识别；工具仍可用（LLM 原生 tool_calls）'
}
const memHint = computed(() => MEM_HINTS[form.memModelId] || '')
const intentHint = computed(() => INTENT_HINTS[form.intentModelId] || '')

async function load() {
  loading.value = true
  try {
    const res = await adminApi.agentList()
    agents.value = (res.data || []).map(a => ({
      id: a.id,
      name: a.agentName || a.name || '未命名',
      llmModel: a.llmModelId || '',
      ttsModel: a.ttsModelId || '',
      boundCount: a.boundCount ?? 0
    }))
    boundTotal.value = agents.value.reduce((s, a) => s + (a.boundCount || 0), 0)
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

async function loadModelOptions() {
  // cc-console 契约：/models/names?modelType={t} → [{id, modelName}]
  const types = ['LLM', 'TTS', 'Memory', 'ASR', 'Intent']
  await Promise.all(types.map(async t => {
    const res = await adminApi.modelNames(t)
    opts[t] = res.data || []
  }))
}

async function loadEditVoices() {
  if (!form.ttsModelId) { editVoices.value = []; return }
  const res = await adminApi.modelVoices(form.ttsModelId)
  editVoices.value = res.data || []
}

async function loadBoundDevices(agentId) {
  if (!agentId) { boundDevices.value = []; return }
  // cc-console 契约：POST /device/bind/{agentId} body={} → 已绑定设备列表
  const res = await api.post(`/device/bind/${agentId}`, {})
  boundDevices.value = res.data || []
}

function resetForm() {
  Object.assign(form, {
    agentName: '', llmModelId: (opts.LLM[0] || {}).id || '',
    ttsModelId: (opts.TTS[0] || {}).id || '', ttsVoiceId: '',
    memModelId: (opts.Memory[0] || {}).id || '',
    intentModelId: (opts.Intent[0] || {}).id || '',
    asrModelId: (opts.ASR[0] || {}).id || '',
    chatHistoryConf: 2, ttsRate: 0, systemPrompt: ''
  })
}

async function openCreate() {
  await loadModelOptions()
  resetForm()
  editor.id = ''
  editor.wakeWords = ''
  editor.wakeWordThreshold = ''
  editor.interruptThreshold = 15
  boundDevices.value = []
  bindCode.value = ''
  editor.show = true
  loadEditVoices()
}

async function openEdit(a) {
  await loadModelOptions()
  const res = await adminApi.agentDetail(a.id)
  const d = res.data || {}
  Object.assign(form, {
    agentName: d.agentName || '',
    llmModelId: d.llmModelId || (opts.LLM[0] || {}).id || '',
    ttsModelId: d.ttsModelId || (opts.TTS[0] || {}).id || '',
    ttsVoiceId: d.ttsVoiceId || '',
    memModelId: d.memModelId || (opts.Memory[0] || {}).id || '',
    intentModelId: d.intentModelId || (opts.Intent[0] || {}).id || '',
    asrModelId: d.asrModelId || (opts.ASR[0] || {}).id || '',
    chatHistoryConf: d.chatHistoryConf ?? 2,
    ttsRate: d.ttsRate ?? 0,
    systemPrompt: d.systemPrompt || ''
  })
  editor.id = d.id || a.id
  editor.wakeWords = d.wakeWords || ''
  // 阈值回显：0 是合法值（最灵敏），必须用 ?? 而非 ||；null/undefined 显示为空（设备默认）
  editor.wakeWordThreshold = d.wakeWordThreshold ?? ''
  // 打断阈值进度条：未设置时回落默认 15（≈300ms，与固件出厂一致）
  editor.interruptThreshold = d.interruptThreshold ?? 15
  bindCode.value = ''
  manual.board = ''; manual.appVersion = ''; manual.macAddress = ''
  editor.show = true
  loadEditVoices()
  loadBoundDevices(editor.id)
}

async function persist() {
  if (!form.agentName) { toast('请填写名字', 'error'); return false }
  const payload = {
    agentName: form.agentName,
    llmModelId: form.llmModelId,
    ttsModelId: form.ttsModelId,
    ttsVoiceId: form.ttsVoiceId,
    memModelId: form.memModelId,
    intentModelId: form.intentModelId,
    asrModelId: form.asrModelId,
    chatHistoryConf: form.chatHistoryConf,
    systemPrompt: form.systemPrompt,
    ttsRate: form.ttsRate,
    wakeWords: editor.wakeWords || ''
  }
  // 唤醒词阈值：留空不发键（保持不变）；填了则校验 0~100
  const t = editor.wakeWordThreshold
  if (t !== '' && t !== null && t !== undefined) {
    if (!Number.isInteger(t) || t < 0 || t > 100) {
      toast('唤醒词阈值需为 0~100 的整数（0 最灵敏）', 'error')
      return false
    }
    payload.wakeWordThreshold = t
  }
  // 实时打断阈值（进度条）：总为 0~100 整数，保存即下发
  const it = editor.interruptThreshold
  if (!Number.isInteger(it) || it < 0 || it > 100) {
    toast('实时打断阈值需为 0~100 的整数（0 最容易打断）', 'error')
    return false
  }
  payload.interruptThreshold = it
  if (editor.id) {
    await adminApi.updateAgent(editor.id, payload)
  } else {
    const res = await adminApi.createAgent(payload)
    if (res.data) {
      // 后端返回纯字符串 agentId（Result<String>）
      editor.id = typeof res.data === 'string' ? res.data : (res.data.id || res.data)
    }
  }
  return true
}

async function save() {
  saving.value = true
  try {
    const ok = await persist()
    if (ok) { toast('已保存，可在下方绑定设备'); load(); loadBoundDevices(editor.id) }
  } catch (e) { toast(e.msg || '保存失败', 'error') }
  finally { saving.value = false }
}

async function bindByCode() {
  if (!/^\d{6}$/.test(bindCode.value)) { toast('请输入设备上的 6 位数字验证码', 'error'); return }
  bindBusy.value = true
  try {
    // 未保存的新智能体：先自动保存拿 id 再绑定
    if (!editor.id) {
      if (!(await persist())) return
      load()
    }
    await adminApi.bindDeviceByCode(editor.id, bindCode.value)
    toast('绑定成功')
    bindCode.value = ''
    loadBoundDevices(editor.id)
  } catch (e) { toast(e.msg || '绑定失败', 'error') }
  finally { bindBusy.value = false }
}

async function manualAdd() {
  if (!manual.macAddress) { toast('请填写 MAC 地址', 'error'); return }
  bindBusy.value = true
  try {
    if (!editor.id) {
      if (!(await persist())) return
      load()
    }
    const payload = { macAddress: manual.macAddress }
    if (manual.board) payload.board = manual.board
    if (manual.appVersion) payload.appVersion = manual.appVersion
    await adminApi.deviceManualAdd(payload)
    toast('设备已添加并绑定')
    manual.board = ''; manual.appVersion = ''; manual.macAddress = ''
    loadBoundDevices(editor.id)
  } catch (e) { toast(e.msg || '添加失败', 'error') }
  finally { bindBusy.value = false }
}

function unbindDevice(d) {
  askConfirm({
    title: '解绑设备', message: `确定解绑「${d.alias || d.id}」吗？`, danger: true,
    onOk: async () => {
      try { await adminApi.deviceUnbind({ deviceId: d.id }); toast('已解绑'); loadBoundDevices(editor.id) }
      catch (e) { toast(e.msg || '解绑失败', 'error') }
    }
  })
}

async function loadSessions(a) {
  sessions.show = true
  sessions.agentName = a.name
  sessions.agentId = a.id
  sessions.list = []
  try {
    const res = await adminApi.agentSessions(a.id, { page: 1, limit: 10 })
    sessions.list = res.data?.list || []
    sessionCount.value = res.data?.total ?? sessions.list.length
  } catch (e) { toast(e.msg || '会话加载失败', 'error') }
}

function goChat(s) {
  sessions.show = false
  router.push({ path: '/admin/chat', query: { agentId: sessions.agentId, sessionId: s.sessionId } })
}

async function loadMcp(a) {
  try {
    const res = await adminApi.mcpAddress(a.id)
    toast('MCP 地址已获取：' + (typeof res.data === 'string' ? res.data.slice(0, 40) : 'ok'))
  } catch (e) { toast(e.msg || 'MCP 获取失败', 'error') }
}

function remove(a) {
  askConfirm({
    title: '删除智能体', message: `确定删除「${a.name}」吗？`, danger: true,
    onOk: async () => {
      try { await adminApi.deleteAgent(a.id); toast('已删除'); load() }
      catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}

onMounted(load)
</script>

<style scoped>
.edit-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px 16px; }
.form-row { margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row textarea, .form-row select {
  border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px;
  font-size: 14px; outline: none; font-family: var(--font); background: #fff;
}
.form-row input:focus, .form-row textarea:focus, .form-row select:focus { border-color: var(--primary); }
.field-hint { font-size: 11.5px; color: var(--text-sub); margin: 2px 0 0; }
/* 实时打断阈值进度条：--pct 由 v-bind 传入，用于渐变填充宽度 */
.slider-row { display: flex; align-items: center; gap: 12px; }
.slider {
  -webkit-appearance: none; appearance: none; flex: 1; height: 8px; border-radius: 999px;
  background: linear-gradient(to right, var(--primary) 0%, var(--primary) var(--pct, 15%),
              #E6EAF2 var(--pct, 15%), #E6EAF2 100%);
  outline: none; cursor: pointer; padding: 0; border: none;
}
.slider::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none; width: 20px; height: 20px; border-radius: 50%;
  background: #fff; border: 2.5px solid var(--primary); box-shadow: 0 1px 4px rgba(0,0,0,.18);
  cursor: grab;
}
.slider::-webkit-slider-thumb:active { cursor: grabbing; }
.slider::-moz-range-thumb {
  width: 20px; height: 20px; border-radius: 50%; background: #fff;
  border: 2.5px solid var(--primary); box-shadow: 0 1px 4px rgba(0,0,0,.18); cursor: grab;
}
.slider-value {
  flex: 0 0 44px; text-align: center; font-size: 13px; font-weight: 700;
  color: var(--primary); background: #fff; border: 1.5px solid var(--border);
  border-radius: 10px; padding: 4px 0; font-variant-numeric: tabular-nums;
}
.bind-box { border: 1.5px solid var(--border); border-radius: 16px; padding: 14px 16px; margin: 8px 0 16px; background: var(--bg-soft, #F8FAFD); }
.bind-label { font-size: 13px; font-weight: 700; margin-bottom: 8px; }
.bind-empty { font-size: 12.5px; color: #B45309; margin: 6px 0 10px; line-height: 1.5; }
.bound-list { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.bound-item { display: flex; align-items: center; gap: 8px; background: #fff; border: 1px solid var(--border); border-radius: 999px; padding: 4px 6px 4px 14px; font-size: 12.5px; }
.bind-code-row { display: flex; gap: 10px; }
.bind-code-row input { flex: 0 0 200px; border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px; font-size: 14px; letter-spacing: 2px; }
.manual-add { margin-top: 12px; font-size: 13px; }
.manual-add summary { cursor: pointer; color: var(--text-sub); font-weight: 600; }
</style>
