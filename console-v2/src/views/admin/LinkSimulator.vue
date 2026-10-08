<template>
  <div>
    <div class="page-head">
      <div>
        <h1>链路 <span style="color:var(--primary)">模拟器</span></h1>
        <p class="sub">迁移自 /cc/ 链路模拟页：ASR 识别 / LLM 预览 / TTS 出声，模拟完整语音链路</p>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="🎧" label="ASR" :value="asrStatus" />
      <StatCard icon="💬" label="LLM" :value="llmStatus" />
      <StatCard icon="🔊" label="TTS" :value="ttsStatus" />
    </div>

    <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start">
      <!-- ASR -->
      <div style="flex:1;min-width:260px">
        <DataTable title="① ASR 识别">
          <div class="form-row"><label>ASR 模型 ID</label><input v-model="asrModelId" placeholder="如 iat" /></div>
          <button class="btn btn-primary" :disabled="asrBusy" @click="runAsr">{{ asrBusy ? '识别中…' : '开始识别' }}</button>
          <pre v-if="asrText" class="resp-box">{{ asrText }}</pre>
        </DataTable>
      </div>

      <!-- LLM -->
      <div style="flex:1;min-width:260px">
        <DataTable title="② LLM 预览">
          <div class="form-row"><label>LLM 模型 ID</label><input v-model="llmModelId" /></div>
          <div class="form-row"><label>系统提示词</label><textarea v-model="llmPrompt" rows="2"></textarea></div>
          <div class="form-row"><label>输入文本</label><textarea v-model="llmText" rows="2"></textarea></div>
          <button class="btn btn-primary" :disabled="llmBusy" @click="runLlm">{{ llmBusy ? '推理中…' : '开始推理' }}</button>
          <pre v-if="llmOut" class="resp-box">{{ llmOut }}</pre>
        </DataTable>
      </div>

      <!-- TTS -->
      <div style="flex:1;min-width:260px">
        <DataTable title="③ TTS 出声">
          <div class="form-row"><label>TTS 模型 ID</label><input v-model="ttsModelId" /></div>
          <div class="form-row"><label>音色</label><input v-model="ttsVoice" /></div>
          <div class="form-row"><label>文本</label><input v-model="ttsText" value="你好，这是链路模拟测试" /></div>
          <button class="btn btn-primary" :disabled="ttsBusy" @click="runTts">{{ ttsBusy ? '合成中…' : '合成试听' }}</button>
          <audio v-if="audioUrl" :src="audioUrl" autoplay controls style="width:100%;margin-top:10px"></audio>
        </DataTable>
      </div>
    </div>
  </div>
</template>

<script setup>
import { inject, ref } from 'vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const asrModelId = ref('')
const asrStatus = ref('—')
const asrBusy = ref(false)
const asrText = ref('')
const llmModelId = ref('')
const llmPrompt = ref('')
const llmText = ref('')
const llmStatus = ref('—')
const llmBusy = ref(false)
const llmOut = ref('')
const ttsModelId = ref('')
const ttsVoice = ref('')
const ttsText = ref('你好，这是链路模拟测试')
const ttsStatus = ref('—')
const ttsBusy = ref(false)
const audioUrl = ref('')

async function runAsr() {
  if (!asrModelId.value) { toast('请填写 ASR 模型 ID', 'error'); return }
  asrBusy.value = true; asrStatus.value = '识别中…'
  try {
    const res = await adminApi.asrRecognize(asrModelId.value)
    asrText.value = JSON.stringify(res.data, null, 2)
    asrStatus.value = '✓ 完成'
  } catch (e) { asrStatus.value = '✗ 失败'; toast(e.msg || 'ASR 失败', 'error') }
  finally { asrBusy.value = false }
}

async function runLlm() {
  if (!llmModelId.value || !llmText.value) { toast('请填写模型 ID 和文本', 'error'); return }
  llmBusy.value = true; llmStatus.value = '推理中…'
  try {
    const res = await adminApi.llmPreview(llmModelId.value, llmText.value, llmPrompt.value)
    llmOut.value = typeof res.data === 'string' ? res.data : JSON.stringify(res.data, null, 2)
    llmStatus.value = '✓ 完成'
  } catch (e) { llmStatus.value = '✗ 失败'; toast(e.msg || 'LLM 失败', 'error') }
  finally { llmBusy.value = false }
}

async function runTts() {
  if (!ttsModelId.value || !ttsText.value) { toast('请填写模型 ID 和文本', 'error'); return }
  ttsBusy.value = true; ttsStatus.value = '合成中…'
  try {
    const res = await adminApi.ttsPreview(ttsModelId.value, ttsVoice.value, ttsText.value)
    const b64 = res.data?.audio || res.data?.base64 || res.data
    if (b64) {
      audioUrl.value = 'data:audio/mp3;base64,' + b64
      ttsStatus.value = '✓ 出声'
    } else {
      ttsStatus.value = '✗ 无音频'; toast('未返回音频数据', 'error')
    }
  } catch (e) { ttsStatus.value = '✗ 失败'; toast(e.msg || 'TTS 失败', 'error') }
  finally { ttsBusy.value = false }
}
</script>

<style scoped>
.form-row { margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row textarea { border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px; font-size: 13px; outline: none; font-family: var(--font); }
.form-row input:focus, .form-row textarea:focus { border-color: var(--primary); }
.resp-box { background: #0F172A; color: #7DD3FC; border-radius: 12px; padding: 12px; font-size: 12px; margin-top: 10px; max-height: 200px; overflow: auto; font-family: ui-monospace, monospace; }
</style>
