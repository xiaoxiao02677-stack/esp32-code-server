<template>
  <div>
    <div class="page-head">
      <div>
        <h1>音色 <span style="color:var(--primary)">试听</span></h1>
        <p class="sub">迁移自 /cc/ 音色页：TTS 模型 / 音色列表 / 试听</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="🎙" label="TTS 模型" :value="ttsModels.length" />
      <StatCard icon="🗣" label="当前音色" :value="voices.length" :note="currentVoiceId || '未选择'" />
      <StatCard icon="🔊" label="试听" :value="playing ? '播放中' : '待命'" note="点列表 ▶ 试听" />
    </div>

    <DataTable title="音色列表">
      <table class="data-table">
        <thead><tr><th>音色</th><th>ID</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="v in voices" :key="v.id || v.ttsVoice">
            <td><div class="cell-main">{{ v.name || v.voiceName || v.ttsVoice }}</div><div class="cell-sub">{{ v.desc || '' }}</div></td>
            <td style="font-size:12px">{{ v.id || v.ttsVoice }}</td>
            <td><div class="row-actions"><button class="link-btn" @click="preview(v)">▶ 试听</button></div></td>
          </tr>
        </tbody>
      </table>
      <div v-if="voices.length === 0" class="empty-state">
        <div class="empty-icon">🎙</div><strong>先选择左侧 TTS 模型</strong>
      </div>
    </DataTable>

    <div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:20px">
      <div v-for="m in ttsModels" :key="m.id" class="chip" :class="{ active: activeModelId === m.id }" @click="pickModel(m)">
        {{ m.modelName || m.id }}
      </div>
    </div>

    <!-- 试听音频 -->
    <audio v-if="audioUrl" ref="audioRef" :src="audioUrl" autoplay @ended="playing = false" hidden></audio>
  </div>
</template>

<script setup>
import { inject, onMounted, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const ttsModels = ref([])
const voices = ref([])
const activeModelId = ref('')
const currentVoiceId = ref('')
const loading = ref(false)
const playing = ref(false)
const audioUrl = ref('')
const audioRef = ref(null)

async function load() {
  loading.value = true
  try {
    const res = await adminApi.ttsModels()
    const list = res.data?.list || res.data || []
    ttsModels.value = list.map(m => ({ id: m.modelId || m.id, modelName: m.modelName || m.name || m.modelId }))
    if (ttsModels.value.length && !activeModelId.value) {
      await pickModel(ttsModels.value[0], true)
    }
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

async function pickModel(m, silent) {
  activeModelId.value = m.id
  if (!silent) toast(`切换到 ${m.modelName}`)
  try {
    const res = await adminApi.modelVoices(m.id)
    const list = res.data?.voices || res.data || []
    voices.value = list.map(v => ({
      id: v.id || v.ttsVoice, name: v.name || v.voiceName || v.ttsVoice, desc: v.description || ''
    }))
  } catch (e) { toast(e.msg || '音色加载失败', 'error'); voices.value = [] }
}

async function preview(v) {
  const voice = v.id || v.ttsVoice
  const modelId = activeModelId.value
  if (!modelId) { toast('请先选择模型', 'error'); return }
  currentVoiceId.value = voice
  try {
    const res = await adminApi.ttsPreview(modelId, voice, '你好，这是试听文本')
    const base64 = res.data?.audio || res.data?.base64 || res.data
    if (base64) {
      audioUrl.value = 'data:audio/mp3;base64,' + base64
      playing.value = true
    } else {
      toast('试听接口未返回音频（该模型可能不支持）', 'error')
    }
  } catch (e) { toast(e.msg || '试听失败', 'error') }
}

onMounted(load)
</script>

<style scoped>
.chip { padding: 8px 16px; border-radius: 999px; background: var(--bg-card); border: 1.5px solid var(--border); cursor: pointer; font-size: 13px; }
.chip.active { border-color: var(--primary); color: var(--primary); font-weight: 600; }
</style>
