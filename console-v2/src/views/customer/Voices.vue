<template>
  <div>
    <div class="page-head">
      <div>
        <h1>音色 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">试听与管理你的声音资源</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" :disabled="loading" @click="load">{{ loading ? '加载中…' : '↻ 刷新' }}</button>
      </div>
    </div>

    <div class="hero-row">
      <div class="hero-blob" style="min-height:170px">
        <div>
          <div class="en">VOICE / CLONING</div>
          <h2>音色工坊</h2>
          <p>管理音色与语言，一键试听</p>
        </div>
        <div class="blob-3d">🎙</div>
      </div>
      <div class="stats-grid">
        <StatCard icon="🎙" label="音色" :value="voices.length" />
        <StatCard icon="🌍" label="语言" :value="languageCount" note="去重" />
        <StatCard icon="▶" label="可试听" :value="previewable" note="含模型信息" />
        <StatCard icon="🔇" label="不可试听" :value="voices.length - previewable" note="到管理端试听" />
      </div>
    </div>

    <DataTable title="音色清单" :total="voices.length" :page="1" :pages="1">
      <table class="data-table">
        <thead>
          <tr><th>试听</th><th>音色信息</th><th>语言</th><th>备注</th><th>创建时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="v in voices" :key="v.id">
            <td>
              <button
                v-if="canPreview(v)"
                class="link-btn"
                :disabled="playingId === v.id"
                @click="playVoice(v)"
              >{{ playingId === v.id ? '试听中…' : '▶' }}</button>
              <button
                v-else
                class="link-btn"
                disabled
                title="该音色缺少模型信息，暂时无法试听，请到管理端试听"
              >▶</button>
            </td>
            <td>
              <div class="cell-main">{{ v.name }}</div>
              <div class="cell-sub">{{ v.ttsVoice || '—' }}</div>
            </td>
            <td>{{ v.languages || '—' }}</td>
            <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-sub)">{{ v.remark || '—' }}</td>
            <td style="color:var(--text-sub)">{{ v.createdAt || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="voices.length === 0" class="empty-state">
        <div class="empty-icon">🎙</div>
        <strong>暂无音色</strong>
        <p>还没有可用的音色资源</p>
      </div>
    </DataTable>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { customerApi, adminApi } from '../../lib/api'

const toast = inject('toast')

const voices = ref([])
const loading = ref(false)
const playingId = ref('')
let warned = false

const languageCount = computed(() => new Set(voices.value.map(v => v.languages).filter(Boolean)).size)
const previewable = computed(() => voices.value.filter(v => canPreview(v)).length)

function canPreview(v) {
  return !!(v.ttsModelId && (v.ttsVoice || v.id))
}

async function load() {
  loading.value = true
  try {
    // 契约：GET /ttsVoice → data 为 { total, list: TimbreDetailsVO[] }
    const res = await customerApi.ttsVoicePage({ page: 1, limit: 50 })
    const data = res.data
    const list = Array.isArray(data) ? data : (data?.list || [])
    voices.value = list.map(v => ({
      id: v.id,
      name: v.name || v.voiceName || v.ttsVoice || '未命名音色',
      languages: v.languages || '',
      remark: v.remark || v.voiceInstruction || '',
      ttsModelId: v.ttsModelId || '',
      ttsVoice: v.ttsVoice || '',
      createdAt: v.createdAt || v.createTime || ''
    }))
  } catch (e) {
    voices.value = []
    if (!warned) { warned = true; toast(e.msg || '音色列表加载失败', 'error') }
  } finally {
    loading.value = false
  }
}

async function playVoice(v) {
  playingId.value = v.id
  try {
    // 契约：GET /models/ttsPreview?modelId&voice&text → 音频 blob（TimbreDetailsVO 携带 ttsModelId）
    const blob = await adminApi.ttsPreview(v.ttsModelId, v.ttsVoice || v.id, '你好，这是试听文本')
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    audio.onended = () => URL.revokeObjectURL(url)
    audio.onerror = () => URL.revokeObjectURL(url)
    audio.play().catch(() => toast('播放失败', 'error'))
  } catch (e) {
    toast('试听失败：' + (e.msg || e.message || '网络异常'), 'error')
  } finally {
    setTimeout(() => { playingId.value = '' }, 1500)
  }
}

onMounted(load)
</script>
