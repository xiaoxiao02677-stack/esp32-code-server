<template>
  <div>
    <div class="page-head">
      <div>
        <h1>音色 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">管理 TTS 音色：切换引擎、增改与试听</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" :disabled="!activeModelId" @click="openCreate">＋ 新增音色</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="mic" label="TTS 引擎" :value="ttsModels.length" />
      <StatCard icon="🗣" label="当前引擎音色" :value="voices.length" :note="activeModelName" />
      <StatCard icon="volume" label="默认引擎" :value="defaultTtsName" />
    </div>

    <div style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:20px">
      <button type="button" v-for="m in ttsModels" :key="m.id" class="chip" :class="{ active: activeModelId === m.id }" @click="pickModel(m)">
        {{ m.modelName }}{{ m.isDefault ? ' ⭐' : '' }}
      </button>
    </div>

    <DataTable title="音色列表" :loading="loading">
      <table class="data-table">
        <thead><tr><th>音色</th><th>代码</th><th>语言</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="v in voices" :key="v.id">
            <td>
              <div class="cell-main">{{ v.name }}{{ v.dynamicInstruction ? ' 🔄动态' : '' }}</div>
              <div v-if="v.isClone" class="cell-sub">🔊 克隆音色</div>
              <div v-if="v.voiceInstruction" class="cell-sub" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">💬 {{ v.voiceInstruction }}</div>
            </td>
            <td style="font-size:12px">{{ v.ttsVoice || v.id }}</td>
            <td>{{ v.languages || '—' }}</td>
            <td>
              <div class="row-actions">
                <button class="link-btn" :disabled="playingVoice === v.id" @click="playVoice(v)">
                  {{ playingVoice === v.id ? '试听中…' : '▶ 试听' }}
                </button>
                <button class="link-btn" @click="openEdit(v)">编辑</button>
                <button class="link-btn danger" @click="remove(v)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="voices.length === 0" class="empty-state"><div class="empty-icon"><YhIcon name="mic" /></div><strong>此引擎暂无音色</strong></div>
    </DataTable>

    <!-- 音色编辑（契约对齐 cc-console openVoiceEdit/saveVoice：payload 带 ttsModelId） -->
    <div v-if="editor.show" class="modal-mask" @click.self="editor.show = false">
      <div class="modal">
        <h3>{{ editor.id ? '编辑' : '新增' }}音色（{{ activeModelName }}）</h3>
        <div class="form-row"><label>名称</label><input v-model="editor.name" /></div>
        <div class="form-row"><label>音色代码</label><input v-model="editor.ttsVoice" placeholder="如 Cherry" /></div>
        <div class="form-row"><label>语言</label><input v-model="editor.languages" placeholder="普通话" /></div>
        <div class="form-row"><label>排序</label><input v-model.number="editor.sort" type="number" /></div>
        <div class="form-row"><label>音色指令（doubao 2.0 音色生效，如「用标准大陆普通话说话」）</label>
          <input v-model="editor.voiceInstruction" placeholder="可选" /></div>
        <div class="form-row">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
            <input type="checkbox" v-model="editor.dynamicInstruction" style="width:auto" /> ✔ 动态更新
          </label>
          <p class="field-hint">勾选后由 LLM 读取短期+长期聊天记录，自动定制口语化语气指令（覆盖固定指令）</p>
        </div>
        <div class="form-row" v-if="editor.dynamicInstruction"><label>指令生成 LLM</label>
          <select v-model="editor.instructionLlmId">
            <option value="">跟随智能体主 LLM</option>
            <option v-for="m in llmOpts" :key="m.id" :value="m.id">{{ m.modelName }}</option>
          </select>
        </div>
        <div class="form-row"><label>试听链接 voice_demo（可直接粘贴一个音频 URL）</label>
          <input v-model.trim="editor.voiceDemo" placeholder="https://... 可选" /></div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="editor.show = false">取消</button>
          <button class="btn btn-primary" :disabled="saving || !editor.name || !editor.ttsVoice" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import YhIcon from '../../components/YhIcon.vue'
import { inject, onMounted, reactive, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')
const ttsModels = ref([])
const voices = ref([])
const activeModelId = ref('')
const activeModelName = ref('')
const defaultTtsName = ref('未设置')
const loading = ref(false)
const saving = ref(false)
const playingVoice = ref('')
const llmOpts = ref([])
const editor = reactive({ show: false, id: '', name: '', ttsVoice: '', languages: '普通话', sort: 0, voiceInstruction: '', voiceDemo: '', dynamicInstruction: false, instructionLlmId: '' })

async function load() {
  loading.value = true
  try {
    // 契约：/models/list?modelType=TTS&page=1&limit=50 → data.list
    const res = await adminApi.ttsModels()
    const list = res.data?.list || []
    ttsModels.value = list
    const def = list.find(m => m.isDefault)
    defaultTtsName.value = def ? def.modelName : '未设置'
    if (!activeModelId.value && list.length) {
      await pickModel(def || list[0], true)
    }
    // LLM 下拉（动态指令生成用）
    const lres = await adminApi.modelNames('LLM')
    llmOpts.value = lres.data || []
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

async function pickModel(m, silent) {
  activeModelId.value = m.id
  activeModelName.value = m.modelName
  if (!silent) toast(`切换到 ${m.modelName}`)
  try {
    // 契约：/models/{modelId}/voices → data 数组 [{id,name,ttsVoice,languages,isClone}]
    const res = await adminApi.modelVoices(m.id)
    voices.value = (res.data || []).map(v => ({
      id: v.id, ttsVoice: v.ttsVoice, name: v.name || v.voiceName || v.ttsVoice,
      desc: v.description || '', languages: v.languages,
      isClone: v.isClone, sort: v.sort,
      voiceInstruction: v.voiceInstruction || '',
      voiceDemo: v.voiceDemo || '',
      dynamicInstruction: !!v.dynamicInstruction,
      instructionLlmId: v.instructionLlmId || ''
    }))
  } catch (e) { toast(e.msg || '音色加载失败', 'error'); voices.value = [] }
}

// 契约对齐 cc-console playVoice：置播放态 → ttsPreview 取 blob → 播放 → 1.5s 后复位
async function playVoice(v) {
  playingVoice.value = v.id
  try {
    const blob = await adminApi.ttsPreview(activeModelId.value, v.ttsVoice || v.id, '你好，这是试听文本')
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    audio.onended = () => URL.revokeObjectURL(url)
    audio.onerror = () => URL.revokeObjectURL(url)
    audio.play().catch(() => toast('播放失败', 'error'))
  } catch (e) {
    toast('试听失败：' + (e.msg || e.message || '网络异常'), 'error')
  } finally {
    setTimeout(() => { playingVoice.value = '' }, 1500)
  }
}

function openCreate() {
  Object.assign(editor, { show: true, id: '', name: '', ttsVoice: '', languages: '普通话', sort: 0, voiceInstruction: '', voiceDemo: '', dynamicInstruction: false, instructionLlmId: '' })
}
function openEdit(v) {
  Object.assign(editor, {
    show: true, id: v.id, name: v.name || '',
    ttsVoice: v.ttsVoice || '', languages: v.languages || '普通话',
    sort: v.sort != null ? v.sort : 0,
    voiceInstruction: v.voiceInstruction || '',
    voiceDemo: v.voiceDemo || '',
    dynamicInstruction: !!v.dynamicInstruction,
    instructionLlmId: v.instructionLlmId || ''
  })
}

async function save() {
  saving.value = true
  try {
    // 契约对齐 cc-console saveVoice：payload 带 ttsModelId + 全字段 + 动态指令
    const payload = {
      name: editor.name, ttsVoice: editor.ttsVoice, ttsModelId: activeModelId.value,
      languages: editor.languages || '普通话', sort: editor.sort || 0,
      voiceInstruction: editor.voiceInstruction || '', voiceDemo: editor.voiceDemo || '',
      dynamicInstruction: editor.dynamicInstruction,
      instructionLlmId: editor.dynamicInstruction ? (editor.instructionLlmId || null) : null
    }
    if (editor.id) await adminApi.ttsVoiceUpdate(editor.id, payload)
    else await adminApi.ttsVoiceCreate(payload)
    toast('已保存'); editor.show = false
    pickModel({ id: activeModelId.value, modelName: activeModelName.value }, true)
  } catch (e) { toast(e.msg || '保存失败', 'error') }
  finally { saving.value = false }
}

function remove(v) {
  askConfirm({
    title: '删除音色', message: `删除音色「${v.name}」？`, danger: true,
    onOk: async () => {
      try { await adminApi.ttsVoiceDelete(v.id); toast('已删除'); pickModel({ id: activeModelId.value, modelName: activeModelName.value }, true) }
      catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}

onMounted(load)
</script>

<style scoped>
/* .chip 已收敛到 global.css */

/* .chip 已收敛到 global.css */

.form-row { margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input { border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px; font-size: 14px; outline: none; }
.form-row input:focus { border-color: var(--primary); }
.link-btn:disabled { opacity: 0.55; cursor: not-allowed; }
.link-btn:disabled:hover { text-decoration: none; }
</style>
