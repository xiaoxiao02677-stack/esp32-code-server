<template>
  <div class="chat-page">
    <div class="page-head">
      <div>
        <h1>聊天 <span style="color:var(--primary)">记录</span></h1>
        <p class="sub">按智能体查看会话与消息记录，支持语音回放</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="chat-layout">
      <!-- 列：智能体 + 会话（契约：sessionId/title/createdAt/chatCount；PageData.total） -->
      <aside class="chat-side">
        <div class="side-block">
          <div class="side-title"><YhIcon name="bot" :size="14" /> 智能体</div>
          <div class="side-scroll" role="listbox" aria-label="智能体列表">
            <button v-for="a in agents" :key="a.id" class="side-item"
                    :class="{ active: agentId === a.id }" role="option"
                    :aria-selected="agentId === a.id" @click="pickAgent(a)">
              <span class="side-name">{{ a.name }}</span>
              <small class="side-meta">{{ a.id.slice(0, 8) }}</small>
            </button>
            <div v-if="!loading && !agents.length" class="side-empty">
              <YhIcon name="bot" :size="22" />
              <strong>暂无智能体</strong>
            </div>
          </div>
        </div>

        <div class="side-block side-sessions">
          <div class="side-title">
            <YhIcon name="clock" :size="14" /> 会话
            <span v-if="sessionTotal" class="side-count">{{ sessionTotal }}</span>
          </div>
          <div class="side-scroll" role="listbox" aria-label="会话列表">
            <button v-for="s in sessions" :key="s.sessionId" class="side-item"
                    :class="{ active: sessionId === s.sessionId }" role="option"
                    :aria-selected="sessionId === s.sessionId" @click="pickSession(s)">
              <span class="side-name">{{ s.title || s.sessionId.slice(0, 14) }}</span>
              <small class="side-meta"><template v-if="s.createdAt">{{ s.createdAt }} · </template>{{ s.chatCount }} 条</small>
            </button>
            <div v-if="agentId && !loading && !sessions.length" class="side-empty">
              <strong>暂无会话，去跟设备说句话吧</strong>
            </div>
            <div v-if="!agentId && !loading" class="side-empty">
              <YhIcon name="chat" :size="22" />
              <strong>先选择一个智能体</strong>
            </div>
          </div>
          <div v-if="sessionPages > 1" class="side-pager">
            <button class="mini-btn" :disabled="sessionPage <= 1" aria-label="上一页会话" @click="turnSessionPage(sessionPage - 1)">‹</button>
            <span class="pager-info">{{ sessionPage }} / {{ sessionPages }}</span>
            <button class="mini-btn" :disabled="sessionPage >= sessionPages" aria-label="下一页会话" @click="turnSessionPage(sessionPage + 1)">›</button>
          </div>
        </div>
      </aside>

      <!-- 主区：消息流（契约：m.chatType===1 用户侧，content JSON 需 parseChatText） -->
      <section class="chat-main" aria-label="消息流">
        <div v-if="sessionId" class="main-head">
          <div class="main-title">
            <strong>{{ currentSessionTitle }}</strong>
            <small>{{ messages.length }} 条消息</small>
          </div>
          <button class="link-btn danger" @click="removeSession">删除会话</button>
        </div>

        <div class="msg-scroll" ref="msgScrollRef">
          <template v-if="messages.length">
            <div v-for="(m, i) in messages" :key="i" class="chat-msg" :class="m.chatType === 1 ? 'user' : 'assistant'">
              <div class="msg-bubble">{{ m.content }}</div>
              <div v-if="m.audioId" class="msg-actions">
                <button class="link-btn" :disabled="playingAudio === m.audioId" @click="playAudio(m.audioId)">
                  {{ playingAudio === m.audioId ? '▶ 播放中…' : '▶ 播放语音' }}
                </button>
              </div>
            </div>
          </template>
          <div v-else-if="loading" class="msg-empty">
            <div class="msg-skeleton"><div v-for="n in 5" :key="n" class="sk-line" :class="{ alt: n % 2 }"></div></div>
          </div>
          <div v-else class="msg-empty">
            <YhIcon name="message" :size="34" />
            <strong>{{ sessionId ? '该会话暂无消息' : '选择左侧会话查看消息' }}</strong>
            <small>用户与智能体的对话会按时间顺序显示在这里</small>
          </div>
        </div>
      </section>
    </div>
    <audio ref="audioRef" hidden></audio>
  </div>
</template>

<script setup>
import YhIcon from '../../components/YhIcon.vue'
import { computed, inject, onMounted, ref, nextTick } from 'vue'
import { useRoute } from 'vue-router'
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
const msgScrollRef = ref(null)

const SESSION_PAGE_SIZE = 10
const sessionPage = ref(1)
const sessionTotal = ref(0)
const sessionPages = computed(() => Math.max(1, Math.ceil(sessionTotal.value / SESSION_PAGE_SIZE)))
const currentSessionTitle = computed(() => {
  const s = sessions.value.find(x => x.sessionId === sessionId.value)
  return s?.title || sessionId.value.slice(0, 14) || '会话'
})

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
    // 路由直入或刷新时恢复选中态
    if (agentId.value && agents.value.some(a => a.id === agentId.value)) {
      await loadSessions()
    } else if (agentId.value) {
      // query 里的 agentId 已失效（被删除），清掉避免空白
      agentId.value = ''
    }
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

async function pickAgent(a) {
  if (agentId.value === a.id) return
  agentId.value = a.id
  sessionId.value = ''
  messages.value = []
  sessionPage.value = 1
  await loadSessions()
}

async function loadSessions() {
  try {
    const res = await adminApi.agentSessions(agentId.value, { page: sessionPage.value, limit: SESSION_PAGE_SIZE })
    // 契约：PageData { total, list }
    sessionTotal.value = Number(res.data?.total) || res.data?.list?.length || 0
    sessions.value = res.data?.list || []
    if (sessionId.value) {
      if (sessions.value.some(s => s.sessionId === sessionId.value)) await loadMessages()
      else sessionId.value = '' // 翻页后当前会话不在本页，消息区复位
    }
  } catch (e) { toast(e.msg || '会话加载失败', 'error') }
}

async function turnSessionPage(p) {
  sessionPage.value = p
  await loadSessions()
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
    await nextTick()
    msgScrollRef.value?.scrollTo({ top: msgScrollRef.value.scrollHeight })
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
/* ============ 布局骨架：侧列 + 主区，整卡联动视口高度 ============ */
/* global.css 未定义 --bg-soft（其他页面的悬空引用一直 fallback 为透明）；
   此处局部定义，从主题变量派生以适配全部六套主题 */
.chat-page {
  --bg-soft: color-mix(in srgb, var(--text) 6%, var(--surface));
  display: flex; flex-direction: column; min-height: calc(100dvh - 130px);
}
.chat-layout {
  flex: 1;
  display: grid;
  grid-template-columns: 264px minmax(0, 1fr);
  gap: 16px;
  min-height: 0;              /* 允许子块在 grid 内收缩滚动 */
  align-items: stretch;
}

/* ---------- 侧列 ---------- */
.chat-side { display: flex; flex-direction: column; gap: 16px; min-height: 0; }
.side-block {
  background: var(--surface);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-card);
  display: flex; flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.side-sessions { flex: 1; }   /* 会话块吃掉剩余高度 */
.side-title {
  display: flex; align-items: center; gap: 6px;
  padding: 12px 14px 8px;
  font-size: 13px; font-weight: 700; color: var(--text);
}
.side-title svg { color: var(--primary); }
.side-count {
  margin-left: auto;
  background: var(--primary-soft); color: var(--primary);
  font-size: 11px; font-weight: 600;
  padding: 1px 8px; border-radius: var(--radius-pill);
}
.side-scroll { overflow: auto; padding: 4px 8px 10px; flex: 1; }
.side-item {
  width: 100%; text-align: left;
  display: flex; flex-direction: column; gap: 2px;
  padding: 9px 10px; border: none; background: none; cursor: pointer;
  border-radius: 10px; font-family: var(--font);
  transition: background .15s;
}
.side-item:hover { background: var(--bg-soft); }
.side-item.active { background: var(--primary-soft); color: var(--primary); }
.side-item.active .side-name { font-weight: 600; }
.side-name {
  font-size: 13px; color: var(--text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.side-item.active .side-name { color: var(--primary); }
.side-meta { color: var(--text-sub); font-size: 11px; font-variant-numeric: tabular-nums; }
.side-empty {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  padding: 28px 12px; color: var(--text-sub); font-size: 12.5px; text-align: center;
}
.side-empty svg { opacity: .45; }
.side-pager {
  display: flex; align-items: center; justify-content: center; gap: 10px;
  padding: 8px; border-top: 1px solid var(--border);
}
.mini-btn {
  width: 26px; height: 26px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--surface); color: var(--text); cursor: pointer; font-size: 14px;
  line-height: 1; display: inline-flex; align-items: center; justify-content: center;
  transition: all .15s;
}
.mini-btn:hover:not(:disabled) { border-color: var(--primary); color: var(--primary); }
.mini-btn:disabled { opacity: .35; cursor: default; }
.pager-info { font-size: 12px; color: var(--text-sub); font-variant-numeric: tabular-nums; }

/* ---------- 主区 ---------- */
.chat-main {
  background: var(--surface);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-card);
  display: flex; flex-direction: column;
  min-height: 0; overflow: hidden;
}
.main-head {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 12px 18px; border-bottom: 1px solid var(--border);
}
.main-title { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.main-title strong { font-size: 14.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.main-title small { color: var(--text-sub); font-size: 12px; font-variant-numeric: tabular-nums; flex-shrink: 0; }
.msg-scroll {
  flex: 1; overflow: auto; padding: 18px;
  display: flex; flex-direction: column; gap: 10px;
  scroll-behavior: smooth;
}

/* ---------- 消息气泡 ---------- */
.chat-msg { display: flex; flex-direction: column; }
.chat-msg.user { align-items: flex-end; }
.chat-msg.user .msg-bubble { background: var(--primary); color: #fff; border-radius: 14px 14px 4px 14px; }
.chat-msg.assistant .msg-bubble { background: var(--bg-soft); color: var(--text); border-radius: 14px 14px 14px 4px; }
.msg-bubble { max-width: 70%; padding: 10px 14px; font-size: 13px; line-height: 1.55; word-break: break-word; }
.msg-actions { margin-top: 3px; }

/* ---------- 空态 / 加载 ---------- */
.msg-empty {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px; color: var(--text-sub); text-align: center; padding: 40px 20px;
}
.msg-empty svg { opacity: .35; margin-bottom: 4px; }
.msg-empty strong { color: var(--text); font-size: 14.5px; }
.msg-empty small { font-size: 12.5px; }
.msg-skeleton { width: 100%; display: flex; flex-direction: column; gap: 12px; }
.sk-line {
  height: 38px; border-radius: 12px;
  background: linear-gradient(90deg, var(--bg-soft) 25%, color-mix(in srgb, var(--text) 10%, var(--surface)) 45%, var(--bg-soft) 65%);
  background-size: 200% 100%;
  animation: sk-shimmer 1.3s ease-in-out infinite;
  width: 62%;
}
.sk-line.alt { align-self: flex-end; width: 48%; }
@keyframes sk-shimmer { to { background-position: -200% 0; } }

/* ---------- 响应式：窄屏侧列置顶横向滚动，主区保底高度 ---------- */
@media (max-width: 900px) {
  .chat-page { min-height: 0; }
  .chat-layout { grid-template-columns: 1fr; }
  .chat-side {
    flex-direction: row; align-items: stretch;
    overflow-x: auto; gap: 12px;
  }
  .side-block { min-width: 240px; }
  .chat-main { min-height: 480px; }
}
</style>
