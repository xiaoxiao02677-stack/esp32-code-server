<template>
  <div>
    <div class="page-head">
      <div>
        <h1>链路 <span style="color:var(--primary)">模拟器</span></h1>
        <p class="sub">ASR → LLM → TTS 全链路（浏览器替代硬件扬声器）</p>
      </div>
    </div>

    <!-- B1/B2: 智能体选择，驱动全流程 -->
    <div class="panel" style="margin-bottom:16px">
      <div class="panel-head">
        <h3>智能体</h3>
        <span class="hint">选择后自动载入 LLM / TTS / ASR 模型配置</span>
      </div>
      <div class="sim-toolbar">
        <select v-model="simAgentId" class="sim-select">
          <option value="">选择智能体</option>
          <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.agentName }}</option>
        </select>
        <span v-if="detailLoading" class="sim-hint">模型配置加载中…</span>
        <span v-else-if="simAgentId && agentConfig" class="sim-hint">
          LLM：{{ agentConfig.llmModelId || '未配置' }} · TTS：{{ agentConfig.ttsModelId || '未配置' }} · ASR：{{ agentConfig.asrModelId || '未配置' }}
        </span>
        <span v-else-if="simAgentId" class="sim-hint sim-hint-warn">详情获取失败，录音 / 运行全链路时会自动重试</span>
      </div>
    </div>

    <!-- B8: 三阶段状态条 -->
    <div class="sim-stages">
      <div class="sim-stage" :class="simStageClass('asr')">
        <div class="sim-stage-head">① ASR 语音识别</div>
        <div v-if="simStage.asr === 'done'" class="sim-stage-body">
          {{ simAsrText || '（无文本）' }}
          <div v-if="simElapsed.asr" class="sim-stage-meta">{{ simElapsed.asr }}</div>
        </div>
        <div v-else-if="simStage.asr === 'loading'" class="sim-stage-body sim-loading">识别中…</div>
        <div v-else-if="simStage.asr === 'error'" class="sim-stage-body sim-error">{{ simError.asr }}</div>
        <div v-else class="sim-stage-body sim-hint">待输入</div>
      </div>
      <div class="sim-arrow">→</div>
      <div class="sim-stage" :class="simStageClass('llm')">
        <div class="sim-stage-head">② LLM 对话</div>
        <div v-if="simStage.llm === 'done'" class="sim-stage-body">
          {{ simLlmReply }}
          <div v-if="simElapsed.llm" class="sim-stage-meta">{{ simElapsed.llm }}</div>
        </div>
        <div v-else-if="simStage.llm === 'loading'" class="sim-stage-body sim-loading">思考中…</div>
        <div v-else-if="simStage.llm === 'error'" class="sim-stage-body sim-error">{{ simError.llm }}</div>
        <div v-else class="sim-stage-body sim-hint">待上一步</div>
      </div>
      <div class="sim-arrow">→</div>
      <div class="sim-stage" :class="simStageClass('tts')">
        <div class="sim-stage-head">③ TTS 合成播放</div>
        <div v-if="simStage.tts === 'done'" class="sim-stage-body">
          <audio ref="simAudioEl" controls :src="simAudioUrl"></audio>
          <a class="sim-download" :href="simAudioUrl" download="sim-tts">⬇ 下载</a>
          <div v-if="simElapsed.tts" class="sim-stage-meta">{{ simElapsed.tts }}</div>
        </div>
        <div v-else-if="simStage.tts === 'loading'" class="sim-stage-body sim-loading">合成中…</div>
        <div v-else-if="simStage.tts === 'error'" class="sim-stage-body sim-error">{{ simError.tts }}</div>
        <div v-else class="sim-stage-body sim-hint">待上一步</div>
      </div>
    </div>

    <!-- 输入区：录音 + 文本 -->
    <div class="panel" style="margin-bottom:16px">
      <div class="panel-head">
        <h3>输入</h3>
        <span class="hint">说话 或 直接打字</span>
      </div>
      <div class="sim-panel-body">
        <div class="sim-input-row">
          <button class="btn btn-ghost rec-btn" :class="{ 'is-recording': simListening }" :disabled="!simAgentId" @click="toggleSimListen">
            {{ simListening ? '● 结束录音并发送识别' : '🎙 录音（服务端真实 ASR）' }}
          </button>
        </div>
        <div class="sim-input-row" style="margin-top:10px">
          <input v-model.trim="simInputText" class="sim-input" placeholder="输入要发送的话（也可手动修改识别结果）" @keyup.enter="runSimPipeline" />
          <button class="btn btn-primary" :disabled="!simInputText || !simAgentId || simBusy" @click="runSimPipeline">
            {{ simBusy ? '链路运行中…' : '▶ 运行全链路' }}
          </button>
        </div>
        <p class="sim-hint" style="margin-top:10px">TTS 试听上限 60 字；超长回复将截断合成。</p>
      </div>
    </div>

    <!-- B9: 链路日志 -->
    <div v-if="simLogs.length" class="panel">
      <div class="panel-head">
        <h3>链路日志</h3>
        <span class="hint">{{ simLogs.length }} 条</span>
      </div>
      <div class="sim-panel-body">
        <pre class="sim-log">{{ simLogs.join('\n') }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')

const agents = ref([])
const simAgentId = ref('')
const detailLoading = ref(false)
const agentConfig = ref(null)

const simStage = ref({ asr: '', llm: '', tts: '' })
const simError = ref({ asr: '', llm: '', tts: '' })
const simElapsed = ref({ asr: '', llm: '', tts: '' })
const simLogs = ref([])
const simAsrText = ref('')
const simLlmReply = ref('')
const simAudioUrl = ref('')
const simAudioEl = ref(null)
const simInputText = ref('')
const simBusy = ref(false)
const simListening = ref(false)
const simRecorder = ref(null)

let disposed = false

function simLog(line) {
  simLogs.value.push(`[${new Date().toLocaleTimeString()}] ${line}`)
}

function simStageClass(stage) {
  return {
    'sim-stage--loading': simStage.value[stage] === 'loading',
    'sim-stage--done': simStage.value[stage] === 'done',
    'sim-stage--error': simStage.value[stage] === 'error'
  }
}

function resetStages() {
  simStage.value = { asr: '', llm: '', tts: '' }
  simError.value = { asr: '', llm: '', tts: '' }
  simElapsed.value = { asr: '', llm: '', tts: '' }
  simAsrText.value = ''
  simLlmReply.value = ''
  if (simAudioUrl.value) { URL.revokeObjectURL(simAudioUrl.value); simAudioUrl.value = '' }
}

async function loadAgentDetail(id) {
  detailLoading.value = true
  try {
    const res = await adminApi.agentDetail(id)
    agentConfig.value = (res && res.data) || null
  } catch (e) {
    agentConfig.value = null
    toast(e.msg || '智能体详情获取失败，运行时将自动重试', 'error')
  } finally {
    detailLoading.value = false
  }
}

watch(simAgentId, (id) => {
  if (simListening.value) stopSimRecorder()
  agentConfig.value = null
  resetStages()
  simLogs.value = []
  if (id) loadAgentDetail(id)
})

onMounted(async () => {
  try {
    const res = await adminApi.agentList()
    agents.value = ((res && res.data) || []).map(a => ({
      id: a.agentId || a.id,
      agentName: a.agentName || a.name || '未命名'
    }))
  } catch (e) {
    toast(e.msg || '智能体列表加载失败', 'error')
  }
})

onBeforeUnmount(() => {
  disposed = true
  stopSimRecorder()
  if (simAudioUrl.value) { URL.revokeObjectURL(simAudioUrl.value); simAudioUrl.value = '' }
})

async function toggleSimListen() {
  if (simListening.value) {
    stopSimRecorder()
    return
  }
  // 真实 ASR：MediaRecorder 录音 → 服务端识别（与设备同一 ASR 引擎）
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
    toast('当前浏览器不支持录音（需要 HTTPS 页面 + MediaRecorder）', 'error')
    return
  }
  let asrModelId = (agentConfig.value && agentConfig.value.asrModelId) || ''
  if (!asrModelId) {
    // /agent/list 不带 asrModelId，拉详情补齐
    try {
      const res = await adminApi.agentDetail(simAgentId.value)
      if (res && res.data) {
        agentConfig.value = res.data
        asrModelId = res.data.asrModelId || ''
      }
    } catch (e) { /* 详情失败时下面统一提示 */ }
  }
  if (!asrModelId) {
    toast('该智能体未配置 ASR 模型，请先在「智能体」页编辑选择语音识别引擎', 'error')
    return
  }
  let stream
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch (e) {
    toast('无法访问麦克风：' + (e.message || e.name || '请检查浏览器权限（页面需 https）'), 'error')
    return
  }
  const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus'
    : (MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '')
  const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
  const chunks = []
  recorder.ondataavailable = (ev) => { if (ev.data && ev.data.size) chunks.push(ev.data) }
  recorder.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop())
    if (disposed) return
    const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
    if (!blob.size) {
      simStage.value.asr = 'error'
      simError.value.asr = '未录到音频'
      simLog('ASR 失败: 未录到音频')
      return
    }
    simStage.value.asr = 'loading'
    simError.value.asr = ''
    simLog(`上传音频 ${(blob.size / 1024).toFixed(1)}KB → 服务端 ASR 识别中…`)
    const t0 = performance.now()
    try {
      const res = await adminApi.asrRecognize(asrModelId, blob)
      const data = (res && res.data) || {}
      const text = (data.text || '').trim()
      if (!text) {
        simStage.value.asr = 'error'
        simError.value.asr = '识别结果为空（请靠近麦克风再说一次）'
        simLog('ASR 失败: 识别结果为空')
      } else {
        simInputText.value = text
        simAsrText.value = text
        simStage.value.asr = 'done'
        simElapsed.value.asr = `前端 ${Math.round(performance.now() - t0)}ms + 服务端 ${data.elapsed_ms || 0}ms`
        simLog(`ASR（服务端 ${data.elapsed_ms || 0}ms）: ${text}`)
      }
    } catch (e) {
      simStage.value.asr = 'error'
      simError.value.asr = '识别失败：' + (e.msg || e.message || '网络异常')
      simLog(`ASR 失败: ${e.msg || e.message || '网络异常'}`)
    }
  }
  recorder.start()
  simRecorder.value = recorder
  simListening.value = true
  simStage.value.asr = 'loading'
  simError.value.asr = ''
  simLog('录音中…（真实上传服务端 ASR，再点一次结束）')
}

function stopSimRecorder() {
  if (simRecorder.value && simRecorder.value.state !== 'inactive') {
    try { simRecorder.value.stop() } catch (e) { /* noop */ }
  }
  simRecorder.value = null
  simListening.value = false
}

async function runSimPipeline() {
  const text = simInputText.value
  if (!text || !simAgentId.value || simBusy.value) return
  simBusy.value = true
  simLogs.value = []
  resetStages()
  // /agent/list 不返回 llmModelId 等字段（只有显示名），必须拉详情拿真实模型 ID
  let agent = null
  let detailErr = ''
  try {
    const detailRes = await adminApi.agentDetail(simAgentId.value)
    agent = (detailRes && detailRes.data) || null
    if (agent) agentConfig.value = agent
  } catch (e) {
    detailErr = (e && (e.msg || e.message)) || '详情获取失败'
    agent = agentConfig.value
    if (agent) simLog(`详情获取失败（${detailErr}），使用已缓存配置继续`)
  }
  if (!agent || !agent.llmModelId) {
    simStage.value.llm = 'error'
    simError.value.llm = detailErr || '该智能体未配置 LLM 模型，请先在「智能体」页编辑选择大脑'
    simLog(`LLM 失败: ${simError.value.llm}`)
    simBusy.value = false
    return
  }
  try {
    // ① ASR（文本直接作为识别结果）
    simStage.value.asr = 'loading'
    const ta = performance.now()
    await new Promise((r) => setTimeout(r, 60))
    simAsrText.value = text
    simStage.value.asr = 'done'
    simElapsed.value.asr = `文本直传 ${Math.round(performance.now() - ta)}ms`
    simLog(`ASR: ${text}`)

    // ② LLM
    simStage.value.llm = 'loading'
    const t0 = performance.now()
    const llmRes = await adminApi.llmPreview(agent.llmModelId, text, agent.systemPrompt || '')
    if (llmRes && llmRes.data) {
      simLlmReply.value = llmRes.data.reply || ''
      simStage.value.llm = 'done'
      const llmFe = Math.round(performance.now() - t0)
      const llmSe = llmRes.data.elapsed_ms || 0
      simElapsed.value.llm = `前端 ${llmFe}ms + 服务端 ${llmSe}ms`
      simLog(`LLM (${llmFe}ms + ${llmSe}ms服务端): ${simLlmReply.value.slice(0, 80)}`)
    } else {
      simStage.value.llm = 'error'
      simError.value.llm = 'LLM 调用失败'
      simLog('LLM 失败: LLM 调用失败')
      simBusy.value = false
      return
    }

    // ③ TTS（60 字截断；音色需把表 id 转成 tts_voice code）
    simStage.value.tts = 'loading'
    const ttsText = simLlmReply.value.slice(0, 60)
    if (ttsText !== simLlmReply.value) simLog('TTS 文本超 60 字，已截断')
    let voiceCode = agent.ttsVoiceId || ''
    if (agent.ttsModelId && agent.ttsVoiceId) {
      const voicesRes = await adminApi.modelVoices(agent.ttsModelId)
      const vlist = (voicesRes && voicesRes.data) || []
      const hit = vlist.find((v) => v.id === agent.ttsVoiceId)
      if (hit && hit.ttsVoice) {
        voiceCode = hit.ttsVoice
      } else if (!hit) {
        simLog(`音色表未找到 ${agent.ttsVoiceId}，原样传给合成端`)
      }
    }
    const t1 = performance.now()
    const blob = await adminApi.ttsPreview(agent.ttsModelId, voiceCode, ttsText)
    if (!blob || blob.size < 200) {
      throw new Error('TTS 返回空音频（音色或模型配置可能有误）')
    }
    simAudioUrl.value = URL.createObjectURL(blob)
    simStage.value.tts = 'done'
    const ttsFe = Math.round(performance.now() - t1)
    simElapsed.value.tts = `前端 ${ttsFe}ms`
    simLog(`TTS (${ttsFe}ms): 音频 ${(blob.size / 1024).toFixed(1)}KB · 音色 ${voiceCode}`)
    nextTick(() => {
      if (simAudioEl.value) simAudioEl.value.play().catch(() => {})
    })
  } catch (e) {
    const stage = simStage.value.llm !== 'done' ? 'llm' : 'tts'
    simStage.value[stage] = 'error'
    simError.value[stage] = (e && (e.msg || e.message)) || '请求异常'
    simLog(`${stage.toUpperCase()} 异常: ${simError.value[stage]}`)
  } finally {
    simBusy.value = false
  }
}
</script>

<style scoped>
.sim-toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 6px 20px 18px; }
.sim-select {
  border: 1.5px solid var(--border); border-radius: var(--radius-pill);
  padding: 10px 18px; font-size: 14px; font-family: var(--font);
  background: var(--surface); color: var(--text); outline: none; min-width: 280px;
  transition: border-color .15s;
}
.sim-select:focus { border-color: var(--primary); }

.sim-stages { display: flex; align-items: stretch; gap: 8px; margin-bottom: 16px; }
.sim-stage {
  flex: 1; min-width: 0; padding: 12px 14px; border-radius: 14px;
  background: var(--surface); border: 2px dashed #C9D4E3;
  box-shadow: var(--shadow-card);
  transition: border-color .2s, background .2s;
}
.sim-stage--loading { border-color: var(--warning); background: rgba(245, 166, 35, .08); }
.sim-stage--done { border-color: var(--success); border-style: solid; background: rgba(47, 191, 113, .07); }
.sim-stage--error { border-color: var(--danger); border-style: solid; background: rgba(240, 83, 77, .07); }
.sim-stage-head { font-weight: 700; font-size: 13.5px; margin-bottom: 6px; }
.sim-stage-body { font-size: 13px; word-break: break-word; white-space: pre-wrap; }
.sim-stage-meta { font-size: 11.5px; color: var(--text-sub); margin-top: 6px; }
.sim-loading { opacity: .75; }
.sim-error { color: var(--danger); }
.sim-hint { opacity: .6; font-size: 12.5px; }
.sim-hint-warn { color: var(--warning); opacity: 1; font-weight: 600; }
.sim-arrow { align-self: center; font-size: 20px; font-weight: 700; opacity: .4; color: var(--text-sub); }
.sim-stage-body audio { width: 100%; margin-top: 8px; height: 36px; }
.sim-download {
  display: inline-block; margin-top: 8px; font-size: 12.5px;
  color: var(--primary); font-weight: 600; text-decoration: none;
}
.sim-download:hover { text-decoration: underline; }

.sim-panel-body { padding: 12px 20px 18px; }
.sim-input-row { display: flex; gap: 10px; }
.sim-input {
  flex: 1; min-width: 0; border: 1.5px solid var(--border); border-radius: var(--radius-pill);
  padding: 10px 18px; font-size: 13.5px; outline: none; font-family: var(--font);
  background: var(--surface); color: var(--text); transition: border-color .15s;
}
.sim-input:focus { border-color: var(--primary); }
.rec-btn.is-recording {
  animation: pulse-rec 1.2s infinite;
  background: var(--danger) !important;
  border-color: var(--danger) !important;
  color: #fff !important;
}
@keyframes pulse-rec {
  0%, 100% { box-shadow: 0 0 0 0 rgba(240, 83, 77, .5); }
  50% { box-shadow: 0 0 0 8px rgba(240, 83, 77, 0); }
}

.sim-log {
  font-family: 'Menlo', 'Consolas', monospace; font-size: 12px;
  white-space: pre-wrap; background: #F7F9FC; color: var(--text);
  border-radius: 10px; padding: 12px; max-height: 200px; overflow-y: auto;
  line-height: 1.7; margin: 0;
}

@media (max-width: 760px) {
  .sim-stages { flex-direction: column; }
  .sim-arrow { display: none; }
  .sim-select { min-width: 0; width: 100%; }
}
</style>
