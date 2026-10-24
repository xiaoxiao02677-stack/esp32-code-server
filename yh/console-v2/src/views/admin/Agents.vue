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
          <!-- 智能体主行：点击「设备」在行下展开该智能体已绑设备（按需加载，收起不占空间）；
               点击行主体（名称单元格）打开共享权限抽屉 -->
          <template v-for="a in agents" :key="a.id">
            <tr>
              <td class="cell-clickable" :title="isSuperAdmin ? '点击设置可见权限' : ''" @click="isSuperAdmin && openShareDrawer(a)">
                <div class="cell-main">{{ a.name }}</div>
                <div class="cell-sub">
                  {{ a.boundCount ? `📡 ${a.boundCount} 台设备` : '未绑定设备' }}
                  <span v-if="isSuperAdmin && a.shareCount" class="share-badge">👁 {{ a.shareCount }} 可见</span>
                </div>
              </td>
              <td style="font-size:12px">{{ a.llmModel || '—' }}<br />{{ a.ttsModel || '—' }}</td>
              <td>
                <div class="row-actions">
                  <button class="link-btn" @click="toggleDevices(a)">
                    {{ expandedAgentId === a.id ? '▲ 收起' : '📱 设备' }}{{ expandedAgentId === a.id ? '' : (a.boundCount ? `(${a.boundCount})` : '') }}
                  </button>
                  <button v-if="isSuperAdmin" class="link-btn" @click="openShareDrawer(a)">权限</button>
                  <button class="link-btn" @click="loadSessions(a)">会话</button>
                  <button class="link-btn" @click="loadMcp(a)">MCP</button>
                  <button class="link-btn" @click="openEdit(a)">编辑</button>
                  <button class="link-btn danger" @click="remove(a)">删除</button>
                </div>
              </td>
            </tr>
            <tr v-if="expandedAgentId === a.id" class="device-row">
              <td colspan="3">
                <div class="device-panel">
                  <div v-if="devicesLoading" class="device-hint">设备加载中…</div>
                  <template v-else-if="agentDevices.length">
                    <span v-for="d in agentDevices" :key="d.id" class="device-chip">
                      <span class="chip-name" :title="d.id">{{ d.alias || d.id }}</span>
                      <span class="chip-sub">{{ d.board || '未知版型' }}<template v-if="d.appVersion"> · v{{ d.appVersion }}</template></span>
                      <button class="chip-unbind" title="解绑此设备" @click="unbindFromList(d)">✕</button>
                    </span>
                  </template>
                  <div v-else class="device-hint">该智能体暂无绑定设备（编辑弹窗内可用验证码或 MAC 绑定）</div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <div v-if="agents.length === 0" class="empty-state">
        <div class="empty-icon"><YhIcon name="bot" /></div><strong>暂无智能体</strong>
        <p>点击右上角「新增智能体」创建第一个</p>
      </div>
    </DataTable>

    <!-- 共享权限抽屉：点击条目名称/权限按钮弹出，设置哪些用户/角色组可以看到该智能体 -->
    <div v-if="shareDrawer.show" class="drawer-mask" @click.self="shareDrawer.show = false">
      <div class="drawer">
        <div class="drawer-head">
          <div>
            <h3>可见权限 — {{ shareDrawer.agentName }}</h3>
            <p class="drawer-sub">设置哪些用户 / 角色组可以在自己的列表中看到该智能体及其绑定设备（对被共享者视同自建，可增删改查）</p>
          </div>
          <button class="drawer-close" @click="shareDrawer.show = false">✕</button>
        </div>

        <div v-if="shareDrawer.loading" class="drawer-body"><p class="drawer-hint">加载中…</p></div>
        <div v-else class="drawer-body">
          <!-- 角色组 -->
          <div class="share-section">
            <div class="share-section-title">👥 按角色组共享</div>
            <p class="drawer-hint">该角色下所有用户可见</p>
            <div class="share-options">
              <label v-for="r in shareDrawer.roles" :key="'r' + r.id" class="share-option" :class="{ on: shareDrawer.selectedRoles.includes(r.id) }">
                <input type="checkbox" :value="r.id" v-model="shareDrawer.selectedRoles" />
                <span class="share-option-name">{{ r.roleName }}</span>
                <span class="share-option-code">{{ r.roleCode }}</span>
              </label>
              <p v-if="!shareDrawer.roles.length" class="drawer-hint">暂无可分配角色</p>
            </div>
          </div>

          <!-- 用户 -->
          <div class="share-section">
            <div class="share-section-title">👤 按用户共享</div>
            <div class="share-search-row">
              <input v-model.trim="shareDrawer.userKeyword" placeholder="搜索用户名…" @input="filterUsers" />
            </div>
            <div class="share-options">
              <label v-for="u in filteredUsers" :key="'u' + u.id" class="share-option" :class="{ on: shareDrawer.selectedUsers.includes(u.id) }">
                <input type="checkbox" :value="u.id" v-model="shareDrawer.selectedUsers" />
                <span class="share-option-name">{{ u.username }}</span>
                <span class="share-option-code">{{ u.roleNames?.length ? u.roleNames.join(' / ') : '未分配角色' }}</span>
              </label>
              <p v-if="!filteredUsers.length" class="drawer-hint">{{ shareDrawer.userKeyword ? '无匹配用户' : '暂无用户' }}</p>
            </div>
            <p v-if="shareDrawer.selectedUsers.length > filteredUsers.length && !shareDrawer.userKeyword" class="drawer-hint">
              另有 {{ shareDrawer.selectedUsers.length - filteredUsers.length }} 个已选用户未在列表前 {{ USER_PAGE_LIMIT }} 条中（保存时保留）
            </p>
          </div>
        </div>

        <div class="drawer-foot">
          <span class="drawer-summary">
            已选：{{ shareDrawer.selectedRoles.length }} 个角色组 · {{ shareDrawer.selectedUsers.length }} 个用户
          </span>
          <div>
            <button class="btn btn-ghost" @click="shareDrawer.show = false">取消</button>
            <button class="btn btn-primary" :disabled="shareDrawer.saving" @click="saveShares">
              {{ shareDrawer.saving ? '保存中…' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </div>

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
          <div class="label-with-switch">
            <label>实时打断阈值（0~100，拉选调节）</label>
            <label class="switch-wrap" title="关闭后服务端不再打断播报（设备本地打断不受影响）">
              <input v-model="editor.interruptEnabled" type="checkbox" class="switch-input" />
              <span class="switch-track"><span class="switch-thumb"></span></span>
              <span class="switch-text">{{ editor.interruptEnabled === false ? '已关闭' : '已开启' }}</span>
            </label>
          </div>
          <div class="slider-row" :class="{ disabled: editor.interruptEnabled === false }">
            <input v-model.number="editor.interruptThreshold" type="range" min="0" max="100" step="1"
                   class="slider" :style="{ '--pct': editor.interruptThreshold + '%' }"
                   :disabled="editor.interruptEnabled === false" />
            <span class="slider-value">{{ editor.interruptThreshold }}</span>
          </div>
          <p class="field-hint">
            播放时用户说话打断的灵敏度：0 最灵敏（立即打断）· 100 最难打断（连续 2 秒人声才打断）· 默认 15 ≈ 300ms。
            <span v-if="editor.interruptEnabled === false" style="color:#B45309;font-weight:600">
              ⚠️ 实时打断已关闭：播报期间用户说话不会打断（保存后立即生效）
            </span>
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
import { adminApi } from '../../lib/api'
import { userState } from '../../lib/api'

const router = useRouter()
const toast = inject('toast')
const askConfirm = inject('askConfirm')
// 超管判断：抽屉入口（行点击/权限按钮/可见角标）仅超级管理员可见
const isSuperAdmin = computed(() => (userState.value?.superAdmin ?? 0) === 1)

const agents = ref([])
const loading = ref(false)
const saving = ref(false)
const boundTotal = ref(0)
const sessionCount = ref(0)
const sessions = reactive({ show: false, agentName: '', agentId: null, list: [] })

// 编辑弹窗状态（契约字段与 cc-console editForm 一致；wakeWords 分号分隔，空=默认「你好」；
// wakeWordThreshold 唤醒词阈值 0~100（0=最灵敏），interruptThreshold 实时打断阈值
// 0~100（0=最容易打断）；两者 未设置时显示设备默认；
// interruptEnabled 实时打断一键开关（null=未设置走默认开启，false=关闭服务端打断）
const editor = reactive({ show: false, id: '', wakeWords: '', wakeWordThreshold: '', interruptThreshold: 15, interruptEnabled: null })
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
      boundCount: a.deviceCount ?? a.boundCount ?? 0,
      shareCount: a.shareCount ?? 0
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
  // 后端契约：GET /device/bind/{agentId} → 已绑定设备列表（POST 是 MQTT 在线状态转发，勿混用）
  const res = await adminApi.boundDevices(agentId)
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
  editor.interruptEnabled = null
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
  // 打断开关回显：null/undefined = 未设置（默认开启）；false = 已关闭
  editor.interruptEnabled = d.interruptEnabled ?? null
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
  // 实时打断一键开关：checkbox 双态（true/false 总是发送，null 不可能——模板开关只有两态）
  payload.interruptEnabled = editor.interruptEnabled === false ? false : true
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

// ── 行内展开：智能体已绑设备（按需加载） ──
const expandedAgentId = ref('')
const agentDevices = ref([])
const devicesLoading = ref(false)
async function toggleDevices(a) {
  if (expandedAgentId.value === a.id) { expandedAgentId.value = ''; return }
  expandedAgentId.value = a.id
  agentDevices.value = []
  devicesLoading.value = true
  try {
    // 后端契约：GET /device/bind/{agentId} → 已绑定设备列表
    const res = await adminApi.boundDevices(a.id)
    agentDevices.value = res.data || []
  } catch (e) {
    toast(e.msg || '设备列表加载失败', 'error')
    expandedAgentId.value = ''
  } finally { devicesLoading.value = false }
}

function unbindFromList(d) {
  askConfirm({
    title: '解绑设备', message: `确定将「${d.alias || d.id}」从该智能体解绑吗？`, danger: true,
    onOk: async () => {
      try {
        await adminApi.deviceUnbind({ deviceId: d.id })
        toast('已解绑')
        agentDevices.value = agentDevices.value.filter(x => x.id !== d.id)
        // 同步主行计数
        const a = agents.value.find(x => x.id === expandedAgentId.value)
        if (a && a.boundCount > 0) a.boundCount--
        boundTotal.value = agents.value.reduce((s, x) => s + (x.boundCount || 0), 0)
      } catch (e) { toast(e.msg || '解绑失败', 'error') }
    }
  })
}

function goChat(s) {
  sessions.show = false
  router.push({ path: '/admin/chat', query: { agentId: sessions.agentId, sessionId: s.sessionId } })
}

// ── 共享权限抽屉（超管配置：哪些用户/角色组可见该智能体） ──
const USER_PAGE_LIMIT = 200
const shareDrawer = reactive({
  show: false, loading: false, saving: false,
  agentId: '', agentName: '',
  roles: [],            // 全部可分配角色 [{id, roleName, roleCode}]
  users: [],            // 用户候选 [{id, username, roleNames}]
  selectedRoles: [],    // 已选角色 id
  selectedUsers: [],    // 已选用户 id
  userKeyword: ''
})
const filteredUsers = computed(() => {
  const kw = shareDrawer.userKeyword.toLowerCase()
  if (!kw) return shareDrawer.users
  return shareDrawer.users.filter(u => (u.username || '').toLowerCase().includes(kw))
})

async function loadShareCandidates() {
  // 角色 + 用户候选并行加载（角色列表轻量全量；用户拉前 200 条，够勾选）
  const [rolesRes, usersRes] = await Promise.all([
    adminApi.roleList(),
    adminApi.userPage({ page: 1, limit: USER_PAGE_LIMIT })
  ])
  shareDrawer.roles = rolesRes.data || []
  const list = usersRes.data?.list || []
  shareDrawer.users = list.map(u => ({ id: u.id, username: u.username, roleNames: u.roleNames || [] }))
}

async function openShareDrawer(a) {
  shareDrawer.agentId = a.id
  shareDrawer.agentName = a.name
  shareDrawer.show = true
  shareDrawer.loading = true
  shareDrawer.selectedRoles = []
  shareDrawer.selectedUsers = []
  shareDrawer.userKeyword = ''
  try {
    if (!shareDrawer.roles.length || !shareDrawer.users.length) {
      await loadShareCandidates()
    }
    const res = await adminApi.agentShares(a.id)
    const shares = res.data || []
    const roleIds = new Set(shareDrawer.roles.map(r => r.id))
    const userIds = new Set(shareDrawer.users.map(u => u.id))
    for (const s of shares) {
      if (s.targetType === 'role') {
        // 已选但不在候选列表（角色被删/停用）也要保留可保存
        if (!roleIds.has(s.targetId)) {
          shareDrawer.roles.push({ id: s.targetId, roleName: `角色#${s.targetId}`, roleCode: '(已失效)' })
        }
        shareDrawer.selectedRoles.push(s.targetId)
      } else if (s.targetType === 'user') {
        if (!userIds.has(s.targetId)) {
          shareDrawer.users.push({ id: s.targetId, username: `用户#${s.targetId}`, roleNames: ['(不在前200条)'] })
        }
        shareDrawer.selectedUsers.push(s.targetId)
      }
    }
  } catch (e) {
    toast(e.msg || '共享配置加载失败', 'error')
  } finally {
    shareDrawer.loading = false
  }
}

function filterUsers() { /* v-model.trim 已实时过滤，computed filteredUsers 自动生效 */ }

async function saveShares() {
  shareDrawer.saving = true
  try {
    const shares = [
      ...shareDrawer.selectedRoles.map(id => ({ targetType: 'role', targetId: id })),
      ...shareDrawer.selectedUsers.map(id => ({ targetType: 'user', targetId: id }))
    ]
    await adminApi.agentSharesSave(shareDrawer.agentId, shares)
    toast('共享权限已保存')
    shareDrawer.show = false
    load() // 刷新可见数角标
  } catch (e) { toast(e.msg || '保存失败', 'error') }
  finally { shareDrawer.saving = false }
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
/* 实时打断一键开关：label 行右对齐布局 */
.label-with-switch { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.switch-wrap { display: inline-flex; align-items: center; gap: 8px; cursor: pointer; user-select: none; flex: 0 0 auto; }
.switch-input { display: none; }
.switch-track {
  width: 40px; height: 22px; border-radius: 999px; background: #CBD5E1;
  position: relative; transition: background .18s; flex: 0 0 auto;
}
.switch-thumb {
  position: absolute; top: 2px; left: 2px; width: 18px; height: 18px; border-radius: 50%;
  background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.25); transition: transform .18s;
}
.switch-input:checked + .switch-track { background: var(--primary); }
.switch-input:checked + .switch-track .switch-thumb { transform: translateX(18px); }
.switch-text { font-size: 12px; color: var(--text-sub); font-weight: 600; }
/* 开关关闭时滑条整体降透明度并禁用交互 */
.slider-row.disabled { opacity: .45; pointer-events: none; }
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
/* 行内展开的已绑设备面板 */
.device-row > td { padding: 0 14px 14px !important; background: var(--bg-soft, #F8FAFD); border-bottom: 1px solid var(--border) !important; }
.device-panel { border-radius: 12px; display: flex; flex-wrap: wrap; gap: 8px; padding: 10px; background: var(--surface); border: 1px dashed var(--border); }
.device-hint { font-size: 12.5px; color: var(--text-sub); padding: 4px 2px; }
.device-chip {
  display: inline-flex; align-items: center; gap: 8px;
  background: var(--primary-soft); border-radius: 999px; padding: 5px 8px 5px 14px;
}
.chip-name { font-size: 13px; font-weight: 600; color: var(--text); max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chip-sub { font-size: 11px; color: var(--text-sub); white-space: nowrap; }
.chip-unbind {
  width: 20px; height: 20px; border-radius: 50%; border: none; cursor: pointer;
  background: transparent; color: var(--text-sub); font-size: 11px; line-height: 1;
  display: inline-flex; align-items: center; justify-content: center; transition: all .15s;
}
.chip-unbind:hover { background: var(--danger); color: #fff; }
/* ── 共享权限抽屉 ── */
.cell-clickable { cursor: pointer; }
.cell-clickable:hover .cell-main { color: var(--primary); }
.share-badge {
  margin-left: 8px; font-size: 11px; color: var(--primary); font-weight: 600;
  background: var(--primary-soft); border-radius: 999px; padding: 1px 8px;
}
.drawer-mask {
  position: fixed; inset: 0; background: rgba(15, 23, 42, .45);
  z-index: 200; display: flex; justify-content: flex-end;
}
.drawer {
  width: min(440px, 92vw); height: 100%; background: var(--surface, #fff);
  display: flex; flex-direction: column;
  box-shadow: -8px 0 32px rgba(0, 0, 0, .18);
  animation: drawer-in .22s ease;
}
@keyframes drawer-in { from { transform: translateX(40px); opacity: .4; } to { transform: none; opacity: 1; } }
.drawer-head {
  display: flex; justify-content: space-between; align-items: flex-start; gap: 10px;
  padding: 18px 20px 12px; border-bottom: 1px solid var(--border);
}
.drawer-head h3 { margin: 0 0 4px; font-size: 16px; }
.drawer-sub { margin: 0; font-size: 12px; color: var(--text-sub); line-height: 1.5; }
.drawer-close {
  border: none; background: transparent; cursor: pointer; font-size: 15px;
  color: var(--text-sub); width: 30px; height: 30px; border-radius: 8px; flex: 0 0 auto;
}
.drawer-close:hover { background: var(--bg-soft, #F1F5F9); color: var(--text); }
.drawer-body { flex: 1; overflow-y: auto; padding: 14px 20px; }
.drawer-hint { font-size: 11.5px; color: var(--text-sub); margin: 2px 0 8px; }
.share-section { margin-bottom: 18px; }
.share-section-title { font-size: 13px; font-weight: 700; margin-bottom: 2px; }
.share-search-row { margin: 6px 0; }
.share-search-row input {
  width: 100%; border: 1.5px solid var(--border); border-radius: 10px;
  padding: 8px 12px; font-size: 13px; outline: none; font-family: var(--font);
}
.share-search-row input:focus { border-color: var(--primary); }
.share-options { display: flex; flex-direction: column; gap: 6px; max-height: 260px; overflow-y: auto; }
.share-option {
  display: flex; align-items: center; gap: 10px; cursor: pointer;
  border: 1.5px solid var(--border); border-radius: 10px; padding: 8px 12px;
  transition: border-color .12s, background .12s;
}
.share-option:hover { border-color: var(--primary); }
.share-option.on { border-color: var(--primary); background: var(--primary-soft, #EEF2FF); }
.share-option input { accent-color: var(--primary); }
.share-option-name { font-size: 13px; font-weight: 600; color: var(--text); }
.share-option-code { font-size: 11px; color: var(--text-sub); margin-left: auto; }
.drawer-foot {
  display: flex; justify-content: space-between; align-items: center; gap: 10px;
  padding: 12px 20px; border-top: 1px solid var(--border);
}
.drawer-summary { font-size: 12px; color: var(--text-sub); }
.drawer-foot .btn { margin-left: 8px; }

/* 移动端：编辑栅格单列、抽屉全宽、行操作换行 */
@media (max-width: 768px) {
  .edit-grid { grid-template-columns: 1fr; }
  .drawer { width: 100vw; max-width: 100vw; }
  .row-actions { flex-wrap: wrap; }
}
</style>
