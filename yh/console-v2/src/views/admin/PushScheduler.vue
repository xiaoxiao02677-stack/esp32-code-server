<template>
  <div>
    <div class="page-head">
      <div>
        <h1>推送调度 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">定时向设备推送音频通知（Python PushScheduler，notify 消息）</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="openCreate">＋ 新建任务</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <!-- 统计条 -->
    <div class="stats-mini">
      <div class="stat-mini"><span class="n">{{ tasks.length }}</span><span class="l">任务总数</span></div>
      <div class="stat-mini"><span class="n ok">{{ statusCount('sent') }}</span><span class="l">已完成</span></div>
      <div class="stat-mini"><span class="n run">{{ statusCount('pending') + statusCount('running') }}</span><span class="l">待执行/执行中</span></div>
      <div class="stat-mini"><span class="n bad">{{ statusCount('failed') }}</span><span class="l">失败</span></div>
      <div class="stat-mini"><span class="n">{{ onlineDevices.length }}</span><span class="l">在线设备</span></div>
      <label class="auto-refresh"><input type="checkbox" v-model="autoRefresh" /> 自动刷新(5s)</label>
    </div>

    <!-- 任务列表 -->
    <div class="task-list">
      <div v-if="loading && !tasks.length" class="empty">加载中...</div>
      <div v-else-if="error" class="empty err">{{ error }}</div>
      <div v-else-if="!tasks.length" class="empty">
        <div style="font-size:34px">📮</div>
        <strong>暂无推送任务</strong>
        <p class="empty-sub">点击右上角「新建任务」，向在线设备推送音频通知</p>
      </div>
      <div v-else class="tasks">
        <div v-for="task in tasks" :key="task.push_id" class="task-card" @click="showDetail(task)">
          <div class="task-header">
            <span class="push-id">{{ task.push_id }}</span>
            <span class="task-status" :class="statusClass(task.status)">{{ statusText(task.status) }}</span>
          </div>
          <div class="task-meta">
            <span class="meta-item" :title="'调度类型'">{{ typeIcon(task.type) }} {{ typeText(task.type) }}</span>
            <span class="meta-item" :title="'优先级'">{{ priorityText(task.priority) }}</span>
            <span class="meta-item" :title="'目标设备数'">📡 {{ task.device_count }} 台</span>
            <span class="meta-item ok" :title="'已发送'">✓ {{ task.sent_count }}</span>
            <span class="meta-item bad" :title="'失败'">✗ {{ task.failed_count }}</span>
            <span class="meta-item time">{{ fmtTime(task.created_at) }}</span>
          </div>
          <div class="task-progress" v-if="task.device_count > 0">
            <div class="bar">
              <div class="fill ok" :style="{ width: pct(task.sent_count, task.device_count) + '%' }"></div>
              <div class="fill bad" :style="{ width: pct(task.failed_count, task.device_count) + '%' }"></div>
            </div>
          </div>
          <div class="task-actions">
            <button class="btn btn-sm" @click.stop="refreshTask(task.push_id)">查看详情</button>
            <button class="btn btn-sm btn-danger" @click.stop="deleteTask(task)">删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 创建弹窗 -->
    <div v-if="showCreate" class="modal-overlay" @click.self="closeCreate">
      <div class="modal">
        <div class="modal-header">
          <h3>新建推送任务</h3>
          <button class="close" @click="closeCreate">×</button>
        </div>
        <div class="modal-body">
          <!-- 目标设备 -->
          <div class="form-group">
            <label>目标设备 <span class="req">*</span> <span class="hint-inline">{{ onlineDevices.length }} 台在线</span></label>
            <div class="dev-picker">
              <div v-if="!onlineDevices.length" class="dev-empty">⚠ 当前无设备通过 WebSocket 在线（设备需处于对话连接状态才能接收推送）</div>
              <label v-for="d in onlineDevices" :key="d" class="dev-check">
                <input type="checkbox" :value="d" v-model="form.deviceIds" />
                <span class="dev-name">{{ d }}</span>
              </label>
              <label class="dev-check all" v-if="onlineDevices.length">
                <input type="checkbox" :checked="allSelected" @change="toggleAll" />
                <span>全选</span>
              </label>
            </div>
          </div>
          <!-- 推送类型 -->
          <div class="form-row">
            <div class="form-group">
              <label>推送类型</label>
              <select v-model="form.pushType">
                <option value="random">random（随机插入，对话空闲时播）</option>
                <option value="urgent">urgent（紧急，立即插播）</option>
                <option value="low">low（低优先级）</option>
              </select>
            </div>
            <div class="form-group">
              <label>调度方式</label>
              <select v-model="form.scheduleType">
                <option value="immediate">立即执行</option>
                <option value="delayed">延迟执行</option>
                <option value="cron">周期执行</option>
              </select>
            </div>
          </div>
          <div class="form-row" v-if="form.scheduleType === 'delayed'">
            <div class="form-group">
              <label>延迟秒数</label>
              <input v-model.number="form.delaySeconds" type="number" min="0" placeholder="如 60" />
            </div>
          </div>
          <div class="form-group" v-if="form.scheduleType === 'cron'">
            <label>周期表达式 <span class="hint-inline">every_30s / every_5m / hourly / daily</span></label>
            <input v-model="form.cron" placeholder="every_30s" />
            <div class="cron-presets">
              <button v-for="p in cronPresets" :key="p.v" class="btn btn-sm" @click="form.cron = p.v">{{ p.t }}</button>
            </div>
          </div>
          <!-- 音频 -->
          <div class="form-group">
            <label>音频 URL <span class="hint-inline">留空则必须选择话题源，由服务端生成推送内容（http/https, mp3/ogg）</span></label>
            <input v-model="form.audioUrl" placeholder="https://example.com/notify.mp3" />
          </div>
          <!-- 话题源 -->
          <div class="form-group">
            <label>话题源 <span class="hint-inline">留空时音频 URL 必填；填写后按话题源动态生成内容</span></label>
            <div class="topic-sources">
              <label v-for="src in TOPIC_SOURCES" :key="src.value">
                <input type="checkbox" v-model="form.topicSources" :value="src.value" />
                {{ src.label }}
              </label>
            </div>
          </div>
          <!-- 字幕 -->
          <div class="form-group">
            <label>字幕文本 <span class="hint-inline">播放时显示在设备屏幕上（不要填 URL），每行一条</span></label>
            <textarea v-model="form.subtitleText" rows="3" placeholder="提醒：该喝水啦～"></textarea>
          </div>
          <div class="push-tip">
            💡 推送说明：设备 <b>WS 在线</b>（对话中）→ 实时收到；仅 <b>心跳在线</b>（空闲待机）→ 自动入离线队列，
            设备下次唤醒建立 WS 时立即补推。
          </div>
          <!-- 频率限制 -->
          <div class="form-row">
            <div class="form-group">
              <label>每设备次数限制</label>
              <input v-model.number="form.ratePerDevice" type="number" min="1" placeholder="3" />
            </div>
            <div class="form-group">
              <label>限制窗口（秒）</label>
              <input v-model.number="form.rateWindow" type="number" min="1" placeholder="300" />
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="closeCreate">取消</button>
          <button class="btn btn-primary" @click="createTask" :disabled="creating">{{ creating ? '提交中…' : '创建任务' }}</button>
        </div>
      </div>
    </div>

    <!-- 详情弹窗 -->
    <div v-if="detail" class="modal-overlay" @click.self="detail = null">
      <div class="modal">
        <div class="modal-header">
          <h3>任务详情</h3>
          <button class="close" @click="detail = null">×</button>
        </div>
        <div class="modal-body">
          <div class="detail-grid">
            <div class="kv"><span class="k">任务ID</span><span class="v mono">{{ detail.push_id }}</span></div>
            <div class="kv"><span class="k">状态</span><span class="v"><span class="task-status" :class="statusClass(detail.status)">{{ statusText(detail.status) }}</span></span></div>
            <div class="kv"><span class="k">调度类型</span><span class="v">{{ typeText(detail.schedule?.type) }}<template v-if="detail.schedule?.cron"> ({{ detail.schedule.cron }})</template><template v-if="detail.schedule?.type === 'delayed'"> ({{ detail.schedule.delay_seconds }}s)</template></span></div>
            <div class="kv"><span class="k">推送类型</span><span class="v">{{ detail.content?.push_type || 'random' }}</span></div>
            <div class="kv"><span class="k">音频URL</span><span class="v mono break">{{ detail.content?.audio_url || (detail.content?.topic_sources?.length ? '（按话题源动态生成）' : '—') }}</span></div>
            <div v-if="detail.content?.topic_sources?.length" class="kv"><span class="k">话题源</span><span class="v">{{ (detail.content?.topic_sources || []).join('、') }}</span></div>
            <div class="kv"><span class="k">字幕</span><span class="v">{{ subtitleTexts(detail.content?.subtitles).join(' / ') || '—' }}</span></div>
            <div class="kv"><span class="k">目标设备</span><span class="v mono">{{ (detail.device_ids || []).join(', ') || '—' }}</span></div>
            <div class="kv"><span class="k">发送/失败</span><span class="v">{{ detail.sent_count ?? 0 }} / {{ detail.failed_count ?? 0 }}</span></div>
            <div class="kv"><span class="k">频率限制</span><span class="v">{{ detail.rate_limit ? `每设备 ${detail.rate_limit.per_device} 次 / ${detail.rate_limit.window_seconds}s` : '默认 (3次/300s)' }}</span></div>
            <div class="kv"><span class="k">创建时间</span><span class="v">{{ fmtTime(detail.created_at) }}</span></div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="detail = null">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject, onMounted, onUnmounted } from 'vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')

const tasks = ref([])
const onlineDevices = ref([])
const loading = ref(false)
const error = ref('')
const autoRefresh = ref(true)
let timer = null

const showCreate = ref(false)
const creating = ref(false)
const detail = ref(null)

const cronPresets = [
  { t: '每30秒', v: 'every_30s' },
  { t: '每5分钟', v: 'every_5m' },
  { t: '每小时', v: 'hourly' },
  { t: '每天', v: 'daily' }
]

const TOPIC_SOURCES = [
  { value: 'memory', label: '记忆' },
  { value: 'weather', label: '天气' },
  { value: 'chat', label: '闲聊' }
]

const blankForm = () => ({
  deviceIds: [],
  pushType: 'random',
  scheduleType: 'immediate',
  delaySeconds: 60,
  cron: 'every_30s',
  audioUrl: '',
  subtitleText: '',
  topicSources: [],
  ratePerDevice: 3,
  rateWindow: 300
})
const form = ref(blankForm())

const allSelected = computed(() => onlineDevices.value.length > 0 && form.value.deviceIds.length === onlineDevices.value.length)

function toggleAll() {
  form.value.deviceIds = allSelected.value ? [] : [...onlineDevices.value]
}

// ---------- 状态/展示工具 ----------
const STATUS_TEXT = { pending: '待执行', running: '执行中', sent: '已完成', failed: '失败', cancelled: '已取消' }
function statusText(s) { return STATUS_TEXT[s] || s || '未知' }
function statusClass(s) {
  if (s === 'sent') return 'active'
  if (s === 'failed' || s === 'cancelled') return 'inactive'
  return 'pending'
}
function statusCount(s) { return tasks.value.filter(t => t.status === s).length }
function typeIcon(t) { return t === 'cron' ? '🔁' : t === 'delayed' ? '⏱' : '⚡' }
function typeText(t) { return t === 'cron' ? '周期' : t === 'delayed' ? '延迟' : '立即' }
function priorityText(p) { return `P${p ?? '-'}` }
function pct(n, total) { return total ? Math.min(100, Math.round((n / total) * 100)) : 0 }
function fmtTime(ts) {
  if (!ts) return '—'
  const d = new Date(ts * (ts < 1e12 ? 1000 : 1))
  const pad = n => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
function subtitleTexts(list) { return (list || []).map(s => (typeof s === 'string' ? s : s?.text)).filter(Boolean) }

// ---------- 数据加载 ----------
async function load() {
  loading.value = true
  error.value = ''
  try {
    const [taskRes, devRes] = await Promise.all([
      adminApi.pushTasks(),
      adminApi.pushOnlineDevices().catch(() => null)
    ])
    if (taskRes.code === 0) {
      tasks.value = taskRes.data?.tasks || []
    } else {
      error.value = taskRes.msg || '加载失败'
    }
    if (devRes && devRes.code === 0) {
      onlineDevices.value = devRes.data?.devices || []
    }
  } catch (e) {
    error.value = e.msg || e.message || '网络错误'
  } finally {
    loading.value = false
  }
}

async function refreshTask(pushId) {
  try {
    const res = await adminApi.pushGetTask(pushId)
    if (res.code === 0 && res.data) {
      detail.value = res.data
    } else {
      toast(res.msg || '查询失败')
    }
  } catch (e) {
    toast(e.msg || '查询失败')
  }
}

function showDetail(task) { refreshTask(task.push_id) }

// ---------- 创建任务 ----------
function openCreate() {
  form.value = blankForm()
  showCreate.value = true
  load()
}
function closeCreate() { showCreate.value = false }

async function createTask() {
  const f = form.value
  if (!f.deviceIds.length) { toast('请选择至少一台目标设备'); return }
  if (!f.audioUrl.trim() && !f.topicSources.length) { toast('音频 URL 与话题源至少配置一项'); return }
  const content = { push_type: f.pushType }
  if (f.audioUrl.trim()) content.audio_url = f.audioUrl.trim()
  if (f.topicSources.length) content.topic_sources = f.topicSources
  const subs = f.subtitleText.split('\n').map(s => s.trim()).filter(Boolean)
  if (subs.length) content.subtitles = subs.map(text => ({ text }))

  const schedule = { type: f.scheduleType }
  if (f.scheduleType === 'delayed') {
    if (!(f.delaySeconds > 0)) { toast('延迟秒数必须大于0'); return }
    schedule.delay_seconds = f.delaySeconds
  }
  if (f.scheduleType === 'cron') {
    if (!f.cron.trim()) { toast('请填写周期表达式'); return }
    schedule.cron = f.cron.trim()
  }

  creating.value = true
  try {
    const res = await adminApi.pushSchedule({
      device_ids: f.deviceIds,
      content,
      schedule,
      rate_limit: { per_device: f.ratePerDevice || 3, window_seconds: f.rateWindow || 300 }
    })
    if (res.code === 0) {
      toast(`任务已创建: ${res.data?.push_id}`)
      closeCreate()
      await load()
    } else {
      toast(res.msg || '创建失败')
    }
  } catch (e) {
    toast(e.msg || '网络错误')
  } finally {
    creating.value = false
  }
}

// ---------- 删除任务 ----------
function deleteTask(task) {
  askConfirm({
    title: '删除推送任务',
    message: `确定删除任务 ${task.push_id} 吗？`,
    danger: true,
    okText: '删除',
    onOk: () => {
      // 后端未提供 DELETE 端点：cron 任务删除需走 Python 内部；此处给出明确提示
      // 预留：后端补充 DELETE /api/push/tasks/{id} 后改为真实调用
      toast('当前后端暂未开放删除接口（cron 任务将随服务重启清除）')
    }
  })
}

// ---------- 自动刷新 ----------
function startTimer() {
  stopTimer()
  timer = setInterval(() => { if (autoRefresh.value && !showCreate.value && !detail.value) load() }, 5000)
}
function stopTimer() { if (timer) { clearInterval(timer); timer = null } }

onMounted(() => { load(); startTimer() })
onUnmounted(stopTimer)
</script>

<style scoped>
.stats-mini {
  display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
  background: white; border-radius: 14px; padding: 12px 18px; margin-top: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.stat-mini { display: flex; align-items: baseline; gap: 6px; }
.stat-mini .n { font-size: 20px; font-weight: 800; }
.stat-mini .n.ok { color: #16a34a; }
.stat-mini .n.bad { color: #dc2626; }
.stat-mini .n.run { color: #d97706; }
.stat-mini .l { font-size: 12px; color: var(--text-sub); }
.auto-refresh { margin-left: auto; display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text-sub); cursor: pointer; }

.task-list { margin-top: 18px; }
.tasks { display: grid; gap: 14px; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); }
.task-card {
  background: white; border-radius: 14px; padding: 16px; cursor: pointer;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08); transition: box-shadow .15s, transform .15s;
}
.task-card:hover { box-shadow: 0 4px 14px rgba(0,0,0,0.12); transform: translateY(-1px); }
.task-header { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.push-id { font-weight: 700; font-size: 13.5px; font-family: ui-monospace, monospace; }
.task-status { padding: 2px 10px; border-radius: 999px; font-size: 12px; white-space: nowrap; }
.task-status.active { background: #dcfce7; color: #16a34a; }
.task-status.inactive { background: #fee2e2; color: #dc2626; }
.task-status.pending { background: #fef3c7; color: #d97706; }
.task-meta { display: flex; flex-wrap: wrap; gap: 6px 12px; margin: 10px 0 6px; }
.meta-item { font-size: 12.5px; color: var(--text-sub); }
.meta-item.ok { color: #16a34a; }
.meta-item.bad { color: #dc2626; }
.meta-item.time { color: #94a3b8; }
.task-progress { margin: 6px 0 10px; }
.bar { display: flex; height: 6px; border-radius: 4px; overflow: hidden; background: #f1f5f9; }
.fill.ok { background: #16a34a; }
.fill.bad { background: #dc2626; }
.task-actions { display: flex; gap: 8px; }

.modal-overlay { position: fixed; inset: 0; background: rgba(15,23,42,0.45); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal { background: white; border-radius: 16px; width: 560px; max-width: 92vw; max-height: 88vh; overflow-y: auto; }
.modal-header { padding: 16px 20px; border-bottom: 1px solid #eef2f7; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; background: white; z-index: 1; }
.modal-header h3 { margin: 0; font-size: 17px; }
.modal-header .close { background: none; border: none; font-size: 24px; cursor: pointer; color: #94a3b8; }
.modal-body { padding: 18px 20px; }
.modal-footer { padding: 14px 20px; border-top: 1px solid #eef2f7; display: flex; justify-content: flex-end; gap: 8px; }

.form-group { margin-bottom: 14px; }
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.form-group label { display: block; margin-bottom: 5px; font-weight: 600; font-size: 13.5px; }
.form-group input, .form-group textarea, .form-group select {
  width: 100%; padding: 8px 12px; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 14px; box-sizing: border-box;
}
.form-group input:focus, .form-group textarea:focus, .form-group select:focus { outline: none; border-color: var(--primary); }
.req { color: #dc2626; }
.hint-inline { font-weight: 400; font-size: 12px; color: #94a3b8; margin-left: 4px; }

.dev-picker { display: flex; flex-wrap: wrap; gap: 8px; border: 1px dashed #e2e8f0; border-radius: 10px; padding: 10px; }
.dev-check { display: inline-flex; align-items: center; gap: 6px; padding: 5px 10px; border-radius: 8px; background: #f8fafc; cursor: pointer; font-size: 13px; }
.dev-check.all { background: #eff6ff; color: var(--primary); }
.dev-check input { width: auto; }
.dev-name { font-family: ui-monospace, monospace; font-size: 12.5px; }
.dev-empty { color: #d97706; font-size: 13px; padding: 4px; }
.topic-sources { display: flex; flex-wrap: wrap; gap: 8px; }
.topic-sources label { display: inline-flex; align-items: center; gap: 6px; padding: 5px 10px; border-radius: 8px; background: #f8fafc; cursor: pointer; font-size: 13px; user-select: none; }
.topic-sources input { width: auto; }
.cron-presets { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
.cron-presets .btn { padding: 4px 10px; font-size: 12px; }

.detail-grid { display: flex; flex-direction: column; gap: 10px; }
.kv { display: grid; grid-template-columns: 90px 1fr; gap: 10px; align-items: baseline; }
.kv .k { font-size: 13px; color: var(--text-sub); }
.kv .v { font-size: 14px; word-break: break-all; }
.mono { font-family: ui-monospace, monospace; font-size: 13px; }

.btn-sm { padding: 6px 12px; font-size: 13px; }
/* .btn-danger 已收敛到 global.css（token 化，避免 #dc2626 硬编码） */
.push-tip {
  margin-top: 4px; padding: 10px 12px; border-radius: 10px;
  background: #eff6ff; color: #1e40af; font-size: 12.5px; line-height: 1.6;
}
.empty { text-align: center; padding: 48px 20px; color: var(--text-sub); }
.empty.err { color: #dc2626; }
.empty-sub { font-size: 13px; color: #94a3b8; margin-top: 6px; }
</style>
