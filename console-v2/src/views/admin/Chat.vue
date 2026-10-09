<template>
  <div>
    <div class="page-head">
      <div>
        <h1>聊天 <span style="color:var(--primary)">记录</span></h1>
        <p class="sub">契约对齐 /cc/：chatType 消息流 / JSON 内容解析 / 语音两段式播放 / 删会话</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div style="display:flex;gap:20px;flex-wrap:wrap;align-items:flex-start">
      <!-- 左：智能体 + 会话（契约：sessionId/title/createdAt/chatCount） -->
      <div style="flex:0 0 260px">
        <DataTable title="智能体">
          <div v-for="a in agents" :key="a.id" class="chat-agent" :class="{ active: agentId === a.id }" @click="pickAgent(a)">
            <span>{{ a.name }}</span><small>{{ a.id.slice(0, 8) }}</small>
          </div>
          <div v-if="!agents.length" class="empty-state"><div class="empty-icon">💬</div><strong>暂无智能体</strong></div>
        </DataTable>
        <DataTable title="会话" style="margin-top:16px">
          <div v-for="s in sessions" :key="s.sessionId" class="chat-agent" :class="{ active: sessionId === s.sessionId }" @click="pickSession(s)">
            <span style="font-size:12px">{{ s.title || s.sessionId.slice(0, 14) }}</span>
            <small v-if="s.createdAt">{{ s.createdAt }} · {{ s.chatCount }} 条</small>
          </div>
          <div v-if="agentId && !sessions.length" class="empty-state"><strong>暂无会话，去跟设备说句话吧～</strong></div>
        </DataTable>
      </div>

      <!-- 右：消息流（契约：m.chatType===1 用户侧，content JSON 需 parseChatText） -->
      <div style="flex:1;min-width:300px">
        <DataTable title="消息流">
          <div style="max-height:480px;overflow:auto">
            <div v-for="(m, i) in messages" :key="i" class="chat-msg" :class="m.chatType === 1 ? 'user' : 'assistant'">
              <div class="msg-bubble">{{ m.content }}</div>
              <div v-if="m.audioId" class="msg-actions">
                <button class="link-btn" :disabled="playingAudio === m.audioId" @click="playAudio(m.audioId)">
                  {{ playingAudio === m.audioId ? '▶ 播放中…' : '▶ 播放语音' }}
                </button>
              </div>
            </div>
            <div v-if="sessionId && !messages.length" class="empty-state"><strong>选择会话查看消息</strong></div>
          </div>
          <div style="display:flex;justify-content:flex-end;padding:10px 0" v-if="sessionId">
            <button class="btn btn-danger" @click="removeSession">删除本会话</button>
          </div>
        </DataTable>
      </div>
    </div>
    <audio ref="audioRef" hidden></audio>
  </div>
</template>

<script setup>
import { inject, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')
const route = useRoute()
const agents = ref([])
const sessions = ref([])
const messages = ref([])
const agentId = ref(route.query.agentId || '')
const sessionId = ref(route.query.sessionId || '')
const loading = ref(false)
const playingAudio = ref('')
const audioRef = ref(null)

// 契约对齐 cc-console parseChatText：content 是 JSON 时取 obj.content/obj.text
function parseChatText(content) {
  try {
    const obj = JSON.parse(content)
    return (obj.content || obj.text || content).toString()
  } catch (e) { return content }
}

async function load() {
  loading.value = true
  try {
    const res = await adminApi.agentList()
    agents.value = (res.data || []).map(a => ({ id: a.id, name: a.agentName || a.name || '未命名' }))
    if (agentId.value) await loadSessions()
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

async function pickAgent(a) {
  agentId.value = a.id
  sessionId.value = ''
  messages.value = []
  await loadSessions()
}

async function loadSessions() {
  try {
    const res = await adminApi.agentSessions(agentId.value, { page: 1, limit: 10 })
    sessions.value = res.data?.list || []
    if (sessionId.value) await loadMessages()
  } catch (e) { toast(e.msg || '会话加载失败', 'error') }
}

async function pickSession(s) {
  sessionId.value = s.sessionId
  await loadMessages()
}

async function loadMessages() {
  try {
    const res = await adminApi.chatHistory(agentId.value, sessionId.value)
    // 契约：data 为消息数组 [{chatType, content, audioId}]
    const list = res.data || []
    messages.value = list.map(m => ({
      chatType: m.chatType,
      content: parseChatText(m.content),
      audioId: m.audioId
    }))
  } catch (e) { toast(e.msg || '消息加载失败', 'error'); messages.value = [] }
}

// 契约对齐 cc-console playChatAudio：POST /agent/audio/{id} → realId → GET /agent/play/{realId}（blob）播放
async function playAudio(audioId) {
  playingAudio.value = audioId
  try {
    const res = await adminApi.chatHistoryAudio(audioId)
    // 后端可能返回裸字符串或 { data: 'xxx' } 包装，兼容取值
    const realId = typeof res.data === 'string' ? res.data : (res.data?.data || res.data?.id || '')
    if (!realId) throw new Error('empty realId')
    let blobUrl = ''
    try {
      const blob = await adminApi.playAudioBlob(realId)
      blobUrl = URL.createObjectURL(blob)
    } finally {
      // 播放完成后释放 blob URL，防止内存泄漏
      const audio = audioRef.value
      if (audio) {
        audio.addEventListener('ended', () => URL.revokeObjectURL(blobUrl), { once: true })
        audio.addEventListener('error', () => URL.revokeObjectURL(blobUrl), { once: true })
      }
    }
    if (!audioRef.value) { URL.revokeObjectURL(blobUrl); return }
    audioRef.value.src = blobUrl
    await audioRef.value.play().catch(() => toast('播放失败（浏览器拦截了自动播放，请点击页面后重试）', 'error'))
  } catch (e) {
    toast(e?.msg || '音频加载失败（该消息可能没有语音文件）', 'error')
  } finally { playingAudio.value = '' }
}

function removeSession() {
  const s = sessions.value.find(x => x.sessionId === sessionId.value)
  askConfirm({
    title: '删除会话', message: `确定删除会话「${s?.title || sessionId.value}」吗？`, danger: true,
    onOk: async () => {
      try {
        await adminApi.deleteChatSession(agentId.value, sessionId.value)
        toast('已删除')
        sessionId.value = ''
        messages.value = []
        loadSessions()
      } catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}

onMounted(load)
</script>

<style scoped>
.chat-agent { padding: 10px 12px; border-radius: 10px; cursor: pointer; display: flex; flex-direction: column; gap: 2px; }
.chat-agent:hover { background: var(--bg-soft); }
.chat-agent.active { background: #EAF2FF; color: var(--primary); font-weight: 600; }
.chat-agent small { color: var(--text-sub); font-size: 11px; }
.chat-msg { margin-bottom: 10px; display: flex; flex-direction: column; }
.chat-msg.user { align-items: flex-end; }
.chat-msg.user .msg-bubble { background: var(--primary); color: #fff; border-radius: 14px 14px 4px 14px; }
.chat-msg.assistant .msg-bubble { background: var(--bg-soft); color: var(--text); border-radius: 14px 14px 14px 4px; }
.msg-bubble { max-width: 70%; padding: 10px 14px; font-size: 13px; word-break: break-word; }
.msg-actions { margin-top: 3px; }
</style>
