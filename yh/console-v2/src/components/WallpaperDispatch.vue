<template>
  <!--
    壁纸下发浮层（P1-4）
    - 必须 Teleport 到 body：.dock 有 backdrop-filter + overflow，会成为 fixed 定位的包含块，
      留在 <nav> 内会被裁成 56~140px 宽（需求 §5.3 / 风险 R1）。
    - 外层用 v-show 而非 v-if：组件不销毁，关闭浮层后 dispatching 轮询仍能跑到 done（需求 §5.3 / R5）。
  -->
  <Teleport to="body">
    <div v-show="open" class="wp-overlay" @click.self="requestClose">
      <div class="wp-modal" role="dialog" aria-modal="true" aria-label="壁纸下发">
        <!-- 头部 -->
        <header class="wp-header">
          <div class="wp-title">
            <span class="wp-logo">🎨</span>
            <div>
              <h3>壁纸下发</h3>
              <p>浮层内完成选设备 / 选壁纸 / 下发，不跳转页面</p>
            </div>
          </div>
          <button type="button" class="wp-close" aria-label="关闭" @click="requestClose">×</button>
        </header>

        <!-- 主体：双栏 320px | 1fr -->
        <div class="wp-body">
          <!-- 左栏：步骤 + 当前选择摘要 -->
          <aside class="wp-side">
            <ol class="wp-steps">
              <li v-for="s in steps" :key="s.id" :class="stepClass(s.id)">
                <span class="dot">{{ s.n }}</span>
                <span class="txt">{{ s.label }}</span>
              </li>
            </ol>

            <div class="wp-summary">
              <h4>当前选择</h4>
              <div class="sum-row">
                <span class="k">下发目标</span>
                <span class="v">{{ targetSummary }}</span>
              </div>
              <div class="sum-row">
                <span class="k">壁纸</span>
                <span class="v">{{ selectedWallpaper ? selectedWallpaper.name : '未选择' }}</span>
              </div>
              <div class="sum-row">
                <span class="k">生效方式</span>
                <span class="v">{{ applyMode === 'immediate' ? '立即生效' : '下次启动生效' }}</span>
              </div>
              <div v-if="task" class="sum-row">
                <span class="k">任务状态</span>
                <span class="v" :class="taskTone">{{ taskStatusText }}</span>
              </div>
              <div v-if="taskId" class="sum-row">
                <span class="k">任务号</span>
                <span class="v mono">{{ taskId }}</span>
              </div>
            </div>

            <p class="wp-tip">
              下发依赖设备在线（WebSocket）。离线设备会在任务结果中标记失败，可稍后单独重试。
            </p>
          </aside>

          <!-- 右栏：三步内容 -->
          <section class="wp-main">
            <!-- ========== 步骤 1：选择目标 ========== -->
            <div v-if="state === 'target'" class="pane">
              <div class="seg">
                <button type="button" :class="{ on: targetMode === 'devices' }" @click="setTargetMode('devices')">按设备</button>
                <button type="button" :class="{ on: targetMode === 'group' }" @click="setTargetMode('group')">按组</button>
                <button type="button" :class="{ on: targetMode === 'all' }" @click="setTargetMode('all')">全部</button>
              </div>

              <!-- 按设备：远程搜索 + 勾选 -->
              <template v-if="targetMode === 'devices'">
                <div class="search-row">
                  <input
                    v-model="deviceKeyword"
                    type="search"
                    placeholder="搜索设备名称 / MAC（服务端搜索，输入即查）"
                    @input="onSearchInput"
                  />
                  <button type="button" class="wp-btn" :disabled="devicesLoading" @click="loadDevices">
                    {{ devicesLoading ? '加载中…' : '刷新' }}
                  </button>
                </div>

                <div class="list-tools">
                  <label class="chk">
                    <input type="checkbox" :checked="allVisibleSelected" @change="toggleAllVisible" />
                    <span>全选当前列表</span>
                  </label>
                  <span class="muted">共 {{ devices.length }} 台，已选 {{ selectedDeviceIds.length }} 台</span>
                </div>

                <div class="dev-list">
                  <div v-if="devicesLoading && !devices.length" class="state">加载设备中…</div>
                  <div v-else-if="devicesError" class="state err">
                    {{ devicesError }}
                    <button type="button" class="link" @click="loadDevices">重试</button>
                  </div>
                  <div v-else-if="!devices.length" class="state">
                    {{ deviceKeyword ? '没有匹配的设备' : '暂无设备（请先在「设备」页添加或绑定）' }}
                  </div>
                  <template v-else>
                    <label v-for="d in devices" :key="d.id" class="dev-row" :class="{ checked: selectedDeviceIds.includes(d.id) }">
                      <input v-model="selectedDeviceIds" type="checkbox" :value="d.id" />
                      <span class="dev-main">
                        <span class="dev-name">{{ d.name }}</span>
                        <span class="dev-mac">{{ d.mac }}</span>
                      </span>
                      <span class="dev-state" :class="d.online ? 'on' : 'off'">
                        <i></i>{{ d.online ? '在线' : '离线' }}
                      </span>
                    </label>
                  </template>
                </div>

                <div class="foot-bar">
                  已选 <b>{{ selectedDeviceIds.length }}</b> 台，在线 <b>{{ onlineSelectedCount }}</b> 台
                </div>
              </template>

              <!-- 按组：按智能体分组（后端契约字段 agentIds） -->
              <template v-else-if="targetMode === 'group'">
                <p class="hint">
                  按「智能体」分组下发：后端接收 <code>agentIds[]</code>，会解析为各智能体绑定的全部设备。
                </p>
                <div class="dev-list">
                  <div v-if="agentsLoading" class="state">加载智能体分组中…</div>
                  <div v-else-if="agentsError" class="state err">
                    {{ agentsError }}
                    <button type="button" class="link" @click="loadAgents">重试</button>
                  </div>
                  <div v-else-if="!agents.length" class="state">暂无可选分组（无智能体）</div>
                  <template v-else>
                    <label v-for="a in agents" :key="a.id" class="dev-row" :class="{ checked: selectedAgentIds.includes(a.id) }">
                      <input v-model="selectedAgentIds" type="checkbox" :value="a.id" />
                      <span class="dev-main">
                        <span class="dev-name">{{ a.name }}</span>
                        <span class="dev-mac">agentId: {{ a.id }}</span>
                      </span>
                      <span v-if="a.deviceCount != null" class="dev-state off"><i></i>{{ a.deviceCount }} 台</span>
                    </label>
                  </template>
                </div>
                <div class="foot-bar">
                  已选 <b>{{ selectedAgentIds.length }}</b> 个分组（<code>targetType=group</code>）
                </div>
              </template>

              <!-- 全部 -->
              <template v-else>
                <div class="all-card">
                  <div class="all-icon">📡</div>
                  <div>
                    <strong>下发到全部设备</strong>
                    <p>
                      <code>targetType=all</code>，由后端解析全平台设备。
                      当前设备列表统计 {{ deviceTotal || devices.length }} 台，其中在线 {{ onlineDeviceCount }} 台。
                    </p>
                  </div>
                </div>
                <p class="hint">建议先确认在线设备数量；离线设备会进入失败列表，可在结果页重试。</p>
              </template>
            </div>

            <!-- ========== 步骤 2：选择壁纸 ========== -->
            <div v-else-if="state === 'wallpaper'" class="pane">
              <div class="seg">
                <button type="button" :class="{ on: wpMode === 'library' }" @click="wpMode = 'library'">服务器库</button>
                <button type="button" :class="{ on: wpMode === 'upload' }" @click="wpMode = 'upload'">上传新图</button>
              </div>

              <!-- 服务器库 -->
              <template v-if="wpMode === 'library'">
                <div class="lib-head">
                  <span class="muted">共 {{ wpTotal }} 张</span>
                  <button type="button" class="wp-btn" :disabled="wpLoading" @click="loadWallpapers(wpPage)">
                    {{ wpLoading ? '加载中…' : '刷新' }}
                  </button>
                </div>

                <div v-if="wpLoading && !wallpapers.length" class="state">加载壁纸库中…</div>
                <div v-else-if="wpError" class="state err">
                  {{ wpError }}
                  <button type="button" class="link" @click="loadWallpapers(wpPage)">重试</button>
                </div>
                <div v-else-if="!wallpapers.length" class="state">
                  壁纸库为空，切到「上传新图」上传第一张（PNG / JPG / WebP，240×240 最佳）
                </div>
                <div v-else class="wp-grid">
                  <button
                    v-for="w in wallpapers" :key="w.id" type="button"
                    class="wp-card" :class="{ on: selectedWallpaperId === w.id }"
                    :title="w.name" @click="selectWallpaper(w)"
                  >
                    <div class="thumb" :style="w.thumbUrl ? { backgroundImage: 'url(' + w.thumbUrl + ')' } : null">
                      <span v-if="!w.thumbUrl" class="thumb-ph">无预览</span>
                    </div>
                    <div class="meta">
                      <span class="name">{{ w.name }}</span>
                      <span class="sub">{{ w.width }}×{{ w.height }} · {{ fmtSize(w.size) }}</span>
                    </div>
                    <span v-if="selectedWallpaperId === w.id" class="tick">✓</span>
                  </button>
                </div>

                <div v-if="wpPages > 1" class="pager">
                  <button type="button" class="wp-btn" :disabled="wpPage <= 1 || wpLoading" @click="loadWallpapers(wpPage - 1)">上一页</button>
                  <span class="muted">{{ wpPage }} / {{ wpPages }}</span>
                  <button type="button" class="wp-btn" :disabled="wpPage >= wpPages || wpLoading" @click="loadWallpapers(wpPage + 1)">下一页</button>
                </div>
              </template>

              <!-- 上传新图 -->
              <template v-else>
                <div class="up-grid">
                  <div class="up-left">
                    <label class="up-drop" :class="{ busy: uploading }">
                      <span class="up-ic">{{ uploading ? '⏳' : '⬆' }}</span>
                      <strong>{{ uploading ? '上传中…' : '选择图片上传' }}</strong>
                      <span class="muted">PNG / JPG / WebP，单图 ≤ 2MB，服务端统一转 240×240 RGB565</span>
                      <input type="file" accept="image/*" :disabled="uploading" @change="onFilePicked" />
                    </label>
                    <p v-if="uploadError" class="up-err">{{ uploadError }}</p>
                    <p v-if="uploadedWallpaper" class="up-ok">
                      已上传：<b>{{ uploadedWallpaper.name }}</b>
                      （{{ uploadedWallpaper.width }}×{{ uploadedWallpaper.height }} · {{ fmtSize(uploadedWallpaper.size) }}）
                    </p>
                    <p class="hint">
                      上传完成即自动选中该壁纸，可回「服务器库」查看。上传中禁止重复提交。
                    </p>
                  </div>

                  <div class="up-right">
                    <div class="preview">
                      <img v-if="previewUrl" :src="previewUrl" alt="壁纸预览" :style="{ objectFit: fit }" />
                      <span v-else class="preview-ph">240×240 预览</span>
                    </div>
                    <div class="fit-row">
                      <label class="chk"><input v-model="fit" type="radio" value="cover" /> cover（裁剪填满）</label>
                      <label class="chk"><input v-model="fit" type="radio" value="contain" /> contain（完整显示）</label>
                    </div>
                    <!-- TODO: 后端 dispatch 契约暂无 fit 字段（见需求 §4.8），当前 fit 仅用于本页预览，
                         后端补充字段后在此处一并传给 wallpaperApi.dispatch({ ..., fit }) -->
                    <p class="hint tiny">fit 目前仅前端预览展示，下发字段待后端契约补充</p>
                  </div>
                </div>
              </template>
            </div>

            <!-- ========== 步骤 3-A：确认下发 ========== -->
            <div v-else-if="state === 'review'" class="pane">
              <div class="confirm-card">
                <h4>确认下发</h4>
                <div class="kv">
                  <span class="k">目标</span>
                  <span class="v">{{ targetSummary }}</span>
                </div>
                <div class="kv">
                  <span class="k">壁纸</span>
                  <span class="v">
                    {{ selectedWallpaper ? selectedWallpaper.name : '未选择' }}
                    <span v-if="selectedWallpaper" class="muted">
                      （{{ selectedWallpaper.width }}×{{ selectedWallpaper.height }} · {{ fmtSize(selectedWallpaper.size) }}）
                    </span>
                  </span>
                </div>
                <div class="kv">
                  <span class="k">生效方式</span>
                  <span class="v apply-row">
                    <label class="chk"><input v-model="applyMode" type="radio" value="immediate" /> 立即生效（在线设备 5s 内变更）</label>
                    <label class="chk"><input v-model="applyMode" type="radio" value="next_boot" /> 下次启动生效</label>
                  </span>
                </div>
                <div class="kv" v-if="selectedWallpaper">
                  <span class="k">文件 MD5</span>
                  <span class="v mono">{{ selectedWallpaper.md5 || '—' }}</span>
                </div>
              </div>
              <p class="hint">
                点击「开始下发」后任务提交到后台，浮层可关闭，轮询在后台继续；90 秒未完成会提示超时。
              </p>
            </div>

            <!-- ========== 步骤 3-B：下发中 / 结果 ========== -->
            <div v-else class="pane">
              <div class="result-head">
                <div class="rh-left">
                  <span class="rh-icon" :class="resultTone">
                    {{ state === 'dispatching' ? '⏳' : (allSuccess ? '✅' : '⚠️') }}
                  </span>
                  <div>
                    <strong>{{ resultTitle }}</strong>
                    <p class="muted">{{ resultSub }}</p>
                  </div>
                </div>
                <div class="rh-nums">
                  <span class="num ok">{{ successCount }}</span>
                  <span class="sep">/</span>
                  <span class="num">{{ totalCount }}</span>
                  <span class="num-l">成功</span>
                  <span class="num bad">{{ failedCount }}</span>
                  <span class="num-l">失败</span>
                </div>
              </div>

              <div class="bar" :class="{ pulse: state === 'dispatching' }">
                <div class="fill ok" :style="{ width: pct(successCount, totalCount) + '%' }"></div>
                <div class="fill bad" :style="{ width: pct(failedCount, totalCount) + '%' }"></div>
              </div>
              <div class="bar-meta">
                <span>已处理 {{ processedCount }} / {{ totalCount || '—' }} 台</span>
                <span v-if="state === 'dispatching'" class="muted">每 2 秒刷新，最长 90 秒</span>
                <span v-else-if="timedOut" class="warn">
                  轮询超时（90 秒），后台可能仍在执行
                  <button type="button" class="link" @click="pollOnce">刷新状态</button>
                </span>
                <span v-else-if="pollError" class="warn">{{ pollError }}</span>
              </div>

              <div class="dev-result">
                <div v-if="!resultDevices.length" class="state">
                  {{ state === 'dispatching' ? '等待设备回执…' : '任务无设备明细' }}
                </div>
                <div v-for="d in resultDevices" :key="d.deviceId" class="res-row" :class="d.status">
                  <span class="res-state" :class="d.status">{{ statusText(d.status) }}</span>
                  <span class="res-main">
                    <span class="dev-name">{{ deviceLabel(d) }}</span>
                    <span class="dev-mac">{{ d.mac || d.deviceId }}</span>
                  </span>
                  <span v-if="d.error" class="res-err" :title="d.error">{{ d.error }}</span>
                  <button
                    v-if="isFailed(d) && state === 'done'"
                    type="button" class="wp-btn tiny" :disabled="retrying"
                    @click="retryDevices([d.deviceId])"
                  >重试</button>
                </div>
              </div>

              <div v-if="state === 'done' && failedCount > 0" class="retry-bar">
                共 {{ failedCount }} 台失败
                <button type="button" class="wp-btn" :disabled="retrying" @click="retryAll">
                  {{ retrying ? '提交重试中…' : '批量重试失败设备' }}
                </button>
              </div>
            </div>
          </section>
        </div>

        <!-- 底部操作区 -->
        <footer class="wp-footer">
          <div v-if="closeConfirm" class="close-confirm">
            <span>任务已提交，关闭不影响后台下发</span>
            <button type="button" class="wp-btn" @click="closeConfirm = false">继续查看</button>
            <button type="button" class="wp-btn danger" @click="confirmClose">仍要关闭</button>
          </div>
          <div v-else class="foot-actions">
            <button
              v-if="state === 'wallpaper' || state === 'review'"
              type="button" class="wp-btn" @click="goBack"
            >上一步</button>
            <span class="grow"></span>
            <button type="button" class="wp-btn" @click="requestClose">关闭</button>
            <button
              v-if="state === 'target'" type="button" class="wp-btn primary"
              :disabled="!hasTarget" @click="state = 'wallpaper'; ensureWallpaperLoaded()"
            >下一步：选壁纸</button>
            <button
              v-else-if="state === 'wallpaper'" type="button" class="wp-btn primary"
              :disabled="!selectedWallpaper || uploading" @click="state = 'review'"
            >下一步：确认下发</button>
            <button
              v-else-if="state === 'review'" type="button" class="wp-btn primary"
              :disabled="submitting || !selectedWallpaper" @click="doDispatch"
            >{{ submitting ? '提交中…' : '开始下发' }}</button>
            <button
              v-else-if="state === 'done'" type="button" class="wp-btn primary"
              @click="resetFlow"
            >再来一次</button>
            <button
              v-else type="button" class="wp-btn" disabled
            >下发中…</button>
          </div>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, inject, onUnmounted, ref, watch } from 'vue'
import { adminApi, wallpaperApi } from '../lib/api'

const props = defineProps({
  open: { type: Boolean, default: false }
})
const emit = defineEmits(['update:open'])

const toast = inject('toast', () => {})

// ---------------- 状态机 ----------------
// 关闭（open=false）即 idle；打开后 target → wallpaper → review → dispatching → done。
// review 是「确认下发」子态（需求 §5.3 第 3 步的确认卡），与 dispatching/done 同属第 3 步。
const state = ref('target') // target | wallpaper | review | dispatching | done
const STEPS = [
  { id: 'target', n: 1, label: '选择目标' },
  { id: 'wallpaper', n: 2, label: '选择壁纸' },
  { id: 'review', n: 3, label: '下发与结果' }
]
const steps = STEPS
const currentStep = computed(() => {
  if (state.value === 'target') return 'target'
  if (state.value === 'wallpaper') return 'wallpaper'
  return 'review'
})
function stepClass(id) {
  const order = { target: 1, wallpaper: 2, review: 3 }
  const cur = order[currentStep.value]
  const mine = order[id]
  return { active: mine === cur, done: mine < cur }
}

// ---------------- 目标选择 ----------------
const targetMode = ref('devices') // devices | group | all
const devices = ref([])
const deviceTotal = ref(0)
const devicesLoading = ref(false)
const devicesError = ref('')
const deviceKeyword = ref('')
const selectedDeviceIds = ref([])
const agents = ref([])
const agentsLoading = ref(false)
const agentsError = ref('')
const selectedAgentIds = ref([])

let searchTimer = null
let devicesLoadedOnce = false

function normalizeDevice(d) {
  const mac = d.macAddress || d.mac || d.id || ''
  return {
    id: d.id != null ? d.id : mac,
    name: d.alias || d.name || d.deviceName || (mac ? '设备 ' + String(mac).slice(-5) : '未命名'),
    mac,
    online: d.status === 1 || d.online === true || !!d.lastConnectedAtTimestamp
  }
}

async function loadDevices() {
  devicesLoading.value = true
  devicesError.value = ''
  try {
    // 与 Devices.vue 同源：GET /admin/device/all（api.js:349 adminApi.devicePage）
    const res = await adminApi.devicePage({
      page: 1,
      limit: 500,
      keyword: deviceKeyword.value.trim() || undefined
    })
    const data = res.data || {}
    let list = (data.list || (Array.isArray(data) ? data : [])).map(normalizeDevice)
    // 后端若忽略 keyword，则前端兜底过滤（保证搜索框有反馈）
    const kw = deviceKeyword.value.trim().toLowerCase()
    if (kw) {
      list = list.filter(d =>
        String(d.name).toLowerCase().includes(kw) || String(d.mac).toLowerCase().includes(kw)
      )
    }
    devices.value = list
    deviceTotal.value = Number(data.total) || list.length
    devicesLoadedOnce = true
  } catch (e) {
    devicesError.value = e.msg || '设备列表加载失败'
    devices.value = []
  } finally {
    devicesLoading.value = false
  }
}

function onSearchInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(loadDevices, 350)
}

async function loadAgents() {
  agentsLoading.value = true
  agentsError.value = ''
  try {
    const res = await adminApi.agentList()
    const list = res.data || []
    agents.value = (Array.isArray(list) ? list : []).map(a => ({
      id: a.id,
      name: a.agentName || a.name || '未命名智能体',
      deviceCount: a.deviceCount != null ? a.deviceCount : null
    }))
  } catch (e) {
    agentsError.value = e.msg || '智能体分组加载失败'
    agents.value = []
  } finally {
    agentsLoading.value = false
  }
}

function setTargetMode(mode) {
  targetMode.value = mode
  if (mode === 'group' && !agents.value.length) loadAgents()
}

const allVisibleSelected = computed(() => {
  if (!devices.value.length) return false
  return devices.value.every(d => selectedDeviceIds.value.includes(d.id))
})
function toggleAllVisible() {
  if (allVisibleSelected.value) {
    const visible = new Set(devices.value.map(d => d.id))
    selectedDeviceIds.value = selectedDeviceIds.value.filter(id => !visible.has(id))
  } else {
    const set = new Set(selectedDeviceIds.value)
    devices.value.forEach(d => set.add(d.id))
    selectedDeviceIds.value = Array.from(set)
  }
}
const onlineSelectedCount = computed(() => {
  const set = new Set(selectedDeviceIds.value)
  return devices.value.filter(d => set.has(d.id) && d.online).length
})
const onlineDeviceCount = computed(() => devices.value.filter(d => d.online).length)

const hasTarget = computed(() => {
  if (targetMode.value === 'all') return true
  if (targetMode.value === 'group') return selectedAgentIds.value.length > 0
  return selectedDeviceIds.value.length > 0
})

const targetSummary = computed(() => {
  if (targetMode.value === 'all') return `全部设备（约 ${deviceTotal.value || devices.value.length} 台）`
  if (targetMode.value === 'group') return `${selectedAgentIds.value.length} 个分组（智能体）`
  return `${selectedDeviceIds.value.length} 台设备（在线 ${onlineSelectedCount.value} 台）`
})

// ---------------- 壁纸选择 ----------------
const wpMode = ref('library') // library | upload
const wallpapers = ref([])
const wpTotal = ref(0)
const wpPage = ref(1)
const wpLimit = 12
const wpPages = computed(() => Math.max(1, Math.ceil(wpTotal.value / wpLimit)))
const wpLoading = ref(false)
const wpError = ref('')
const selectedWallpaperId = ref('')
const selectedWallpaper = computed(() => {
  if (!selectedWallpaperId.value) return null
  const inList = wallpapers.value.find(w => String(w.id) === String(selectedWallpaperId.value))
  if (inList) return inList
  if (uploadedWallpaper.value && String(uploadedWallpaper.value.id) === String(selectedWallpaperId.value)) {
    return uploadedWallpaper.value
  }
  return null
})
const uploadedWallpaper = ref(null)
const uploading = ref(false)
const uploadError = ref('')
const previewUrl = ref('')
const fit = ref('cover') // TODO: 后端 dispatch 契约暂无 fit 字段，当前仅前端预览用

// 兼容 wallpaperApi 两种返回形态：直接返回 data，或返回 api 原始 {code,data}
function unwrap(res) {
  if (res && typeof res === 'object' && !Array.isArray(res) && 'code' in res && 'data' in res) return res.data
  return res
}
function normalizeWallpaper(w) {
  const o = w || {}
  return {
    id: o.id,
    name: o.name || '未命名壁纸',
    url: o.url || '',
    thumbUrl: o.thumbUrl || o.url || '',
    md5: o.md5 || '',
    size: Number(o.size) || 0,
    width: Number(o.width) || 0,
    height: Number(o.height) || 0,
    format: o.format || ''
  }
}

async function loadWallpapers(page) {
  wpPage.value = Math.max(1, Number(page) || 1)
  wpLoading.value = true
  wpError.value = ''
  try {
    const res = await wallpaperApi.page({ page: wpPage.value, limit: wpLimit })
    const data = unwrap(res) || {}
    const list = Array.isArray(data) ? data : (data.list || [])
    wallpapers.value = list.map(normalizeWallpaper)
    wpTotal.value = Number(data.total) || wallpapers.value.length
  } catch (e) {
    wpError.value = e.msg || '壁纸库加载失败'
    wallpapers.value = []
    wpTotal.value = 0
  } finally {
    wpLoading.value = false
  }
}

function selectWallpaper(w) {
  selectedWallpaperId.value = w.id
  // 库里的图不需要本地预览；上传页预览保留最后一张上传图
}

function ensureWallpaperLoaded() {
  if (!wallpapers.value.length) loadWallpapers(1)
}

function revokePreview() {
  if (previewUrl.value && previewUrl.value.startsWith('blob:')) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
}

async function onFilePicked(e) {
  const file = e.target.files && e.target.files[0]
  e.target.value = '' // 允许重复选择同一文件
  if (!file || uploading.value) return

  uploadError.value = ''
  revokePreview()
  previewUrl.value = URL.createObjectURL(file)
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('name', file.name.replace(/\.[^.]+$/, ''))
    const res = await wallpaperApi.upload(fd)
    const wp = normalizeWallpaper(unwrap(res))
    if (!wp.id) throw { msg: '上传响应缺少 id' }
    uploadedWallpaper.value = wp
    selectedWallpaperId.value = wp.id
    // 切到服务端 URL 前释放本地 blob，避免对象 URL 泄漏
    if (wp.url) {
      revokePreview()
      previewUrl.value = wp.url
    }
    // 库里同步插入，切回「服务器库」立即可见（去重）
    if (!wallpapers.value.some(w => String(w.id) === String(wp.id))) {
      wallpapers.value = [wp, ...wallpapers.value]
      wpTotal.value += 1
    }
    toast('壁纸上传成功', 'success')
  } catch (err) {
    uploadError.value = err.msg || '上传失败，请重试'
    toast(uploadError.value, 'error')
  } finally {
    uploading.value = false
  }
}

// ---------------- 下发与轮询 ----------------
const applyMode = ref('immediate')
const submitting = ref(false)
const taskId = ref('')
const task = ref(null)
const pollError = ref('')
const timedOut = ref(false)
const retrying = ref(false)
const POLL_INTERVAL = 2000
const POLL_TIMEOUT = 90000

let pollTimer = null
let pollStartedAt = 0
let pollBusy = false

const totalCount = computed(() => Number(task.value && task.value.total) || 0)
const successCount = computed(() => Number(task.value && task.value.success) || 0)
const failedCount = computed(() => Number(task.value && task.value.failed) || 0)
const processedCount = computed(() => {
  const t = task.value || {}
  // sent 为已下发数，success 为回执成功数；两者可能重叠，取较大值并与 failed 相加后封顶 total
  const n = Math.max(Number(t.sent) || 0, successCount.value) + failedCount.value
  return Math.min(totalCount.value || n, n)
})
const allSuccess = computed(() => failedCount.value === 0 && successCount.value > 0)
const resultDevices = computed(() => {
  const list = (task.value && Array.isArray(task.value.devices)) ? task.value.devices.slice() : []
  // 失败优先展示，方便排查/重试
  return list.sort((a, b) => {
    const fa = isFailed(a) ? 0 : 1
    const fb = isFailed(b) ? 0 : 1
    return fa - fb
  })
})
const resultTone = computed(() => (state.value === 'dispatching' ? 'run' : (allSuccess.value ? 'ok' : 'bad')))
const resultTitle = computed(() => {
  if (state.value === 'dispatching') return '下发中…'
  if (allSuccess.value) return '全部成功'
  return failedCount.value > 0 ? '部分失败' : '任务结束'
})
const resultSub = computed(() => {
  if (state.value === 'dispatching') return `任务 ${taskId.value} 正在执行，关闭浮层不影响后台下发`
  if (allSuccess.value) return `任务 ${taskId.value} 已完成，在线设备应已切换壁纸`
  return `任务 ${taskId.value} 结束，失败设备可单条或批量重试`
})
const taskStatusText = computed(() => {
  const s = String((task.value && task.value.status) || '').toLowerCase()
  const map = {
    pending: '待执行', running: '下发中', dispatching: '下发中',
    done: '已完成', finished: '已完成', completed: '已完成',
    success: '成功', partial: '部分失败', failed: '失败'
  }
  return map[s] || (s || (state.value === 'dispatching' ? '下发中' : '—'))
})
const taskTone = computed(() => (state.value === 'dispatching' ? 'tone-run' : (allSuccess.value ? 'tone-ok' : 'tone-bad')))

function isFailed(d) {
  return String((d && d.status) || '').toLowerCase() === 'failed'
}
function statusText(s) {
  const map = {
    pending: '待下发', sent: '已下发', success: '成功', acked: '已确认',
    failed: '失败', skipped: '已跳过'
  }
  return map[String(s || '').toLowerCase()] || (s || '未知')
}
function deviceLabel(d) {
  const found = devices.value.find(x => String(x.id) === String(d.deviceId))
  if (found) return found.name
  return d.mac || d.deviceId || '未知设备'
}
function pct(n, total) {
  if (!total) return 0
  return Math.min(100, Math.round((Number(n) || 0) * 100 / total))
}
function fmtSize(bytes) {
  const n = Number(bytes) || 0
  if (!n) return '—'
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB'
  return (n / 1024 / 1024).toFixed(1) + ' MB'
}
function isTaskFinished(t) {
  const s = String((t && t.status) || '').toLowerCase()
  if (['done', 'finished', 'completed', 'success', 'partial', 'failed', 'cancelled', 'timeout'].includes(s)) return true
  const total = Number(t && t.total) || 0
  if (total <= 0) return false
  const done = Math.max(Number(t.sent) || 0, Number(t.success) || 0) + (Number(t.failed) || 0)
  return done >= total
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  pollBusy = false
}

function startPolling(id) {
  stopPolling()
  taskId.value = String(id)
  pollStartedAt = Date.now()
  timedOut.value = false
  pollError.value = ''
  state.value = 'dispatching'
  pollOnce()
  pollTimer = setInterval(pollOnce, POLL_INTERVAL)
}

async function pollOnce() {
  if (!taskId.value || pollBusy) return
  if (Date.now() - pollStartedAt > POLL_TIMEOUT) {
    // 超时停止轮询，保留当前结果；用户可手动「刷新状态」再查一次
    stopPolling()
    timedOut.value = true
    state.value = 'done'
    return
  }
  pollBusy = true
  try {
    const res = await wallpaperApi.task(taskId.value)
    const t = unwrap(res) || {}
    task.value = t
    pollError.value = ''
    if (isTaskFinished(t)) {
      stopPolling()
      state.value = 'done'
    }
  } catch (e) {
    pollError.value = e.msg || '任务状态查询失败，稍后自动重试'
  } finally {
    pollBusy = false
  }
}

async function doDispatch() {
  if (submitting.value || !selectedWallpaper.value) return
  submitting.value = true
  try {
    const payload = {
      wallpaperId: selectedWallpaper.value.id,
      targetType: targetMode.value === 'all' ? 'all' : (targetMode.value === 'group' ? 'group' : 'devices'),
      deviceIds: targetMode.value === 'devices' ? selectedDeviceIds.value.slice() : [],
      agentIds: targetMode.value === 'group' ? selectedAgentIds.value.slice() : [],
      applyMode: applyMode.value
    }
    const res = await wallpaperApi.dispatch(payload)
    const data = unwrap(res) || {}
    const id = data.taskId || data.id || data
    if (!id) throw { msg: '下发响应缺少 taskId' }
    task.value = { status: 'pending', total: 0, sent: 0, success: 0, failed: 0, devices: [] }
    startPolling(id)
  } catch (e) {
    toast(e.msg || '下发失败', 'error')
  } finally {
    submitting.value = false
  }
}

async function retryDevices(ids) {
  const list = (ids || []).filter(Boolean)
  if (!list.length || retrying.value || !taskId.value) return
  retrying.value = true
  pollError.value = ''
  try {
    const res = await wallpaperApi.retry(taskId.value, list)
    const data = unwrap(res) || {}
    const newId = data.taskId || data.id || (typeof data === 'string' ? data : '')
    // 后端可能复用原任务号，也可能新建任务：都接着轮询
    if (newId) taskId.value = String(newId)
    // 把重试设备标回 pending，进度条立即有反馈
    const set = new Set(list.map(String))
    const oldDevices = (task.value && task.value.devices) || []
    task.value = {
      ...(task.value || {}),
      failed: Math.max(0, failedCount.value - list.length),
      devices: oldDevices.map(d => (set.has(String(d.deviceId)) ? { ...d, status: 'pending', error: '' } : d))
    }
    startPolling(taskId.value)
  } catch (e) {
    toast(e.msg || '重试提交失败', 'error')
  } finally {
    retrying.value = false
  }
}
function retryAll() {
  const ids = resultDevices.value.filter(isFailed).map(d => d.deviceId)
  retryDevices(ids)
}

function resetFlow() {
  stopPolling()
  state.value = 'target'
  task.value = null
  taskId.value = ''
  timedOut.value = false
  pollError.value = ''
}

function goBack() {
  if (state.value === 'wallpaper') state.value = 'target'
  else if (state.value === 'review') state.value = 'wallpaper'
}

// ---------------- 关闭 / ESC ----------------
const closeConfirm = ref(false)

function requestClose() {
  // 下发进行中（含轮询未到终态）关闭需二次确认；关闭后轮询继续（组件不销毁）
  if (state.value === 'dispatching') {
    closeConfirm.value = true
    return
  }
  emit('update:open', false)
}
function confirmClose() {
  closeConfirm.value = false
  emit('update:open', false)
}

function onKeydown(e) {
  if (!props.open) return
  if (e.key === 'Escape' || e.key === 'Esc') {
    if (closeConfirm.value) {
      closeConfirm.value = false
      return
    }
    e.stopPropagation()
    requestClose()
  }
}

watch(
  () => props.open,
  (v) => {
    if (v) {
      window.addEventListener('keydown', onKeydown)
      if (!devicesLoadedOnce) loadDevices()
    } else {
      window.removeEventListener('keydown', onKeydown)
      closeConfirm.value = false
    }
  },
  { immediate: true }
)

onUnmounted(() => {
  // 轮询清理：组件真正卸载（路由切换等）时停掉 interval，避免泄漏
  stopPolling()
  clearTimeout(searchTimer)
  window.removeEventListener('keydown', onKeydown)
  revokePreview()
})
</script>

<style scoped>
/* 遮罩：z-index 140 —— 压住 dock(50)，放行 Toasts(200) 与全局确认框(150) */
.wp-overlay {
  position: fixed;
  inset: 0;
  z-index: 140;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  box-sizing: border-box;
  background: rgba(15, 23, 42, .45);
}
/* 居中 Modal：min(920px,94vw) / max-height 88vh / 双栏 320px 1fr */
.wp-modal {
  width: min(920px, 94vw);
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 16px;
  box-shadow: 0 24px 64px rgba(15, 23, 42, .28);
  font-family: var(--font);
}

.wp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
}
.wp-title { display: flex; align-items: center; gap: 10px; }
.wp-logo { font-size: 22px; line-height: 1; }
.wp-title h3 { margin: 0; font-size: 16px; }
.wp-title p { margin: 2px 0 0; font-size: 12px; color: var(--text-sub); }
.wp-close {
  border: none; background: none; cursor: pointer; font-size: 24px; line-height: 1;
  color: var(--text-sub); padding: 2px 8px; border-radius: 8px;
}
.wp-close:hover { color: var(--primary); background: var(--primary-soft); }

.wp-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 320px 1fr;
}
.wp-side {
  min-height: 0;
  overflow-y: auto;
  padding: 16px 18px;
  border-right: 1px solid var(--border);
  background: rgba(127, 140, 160, .05);
}
.wp-main {
  min-height: 0;
  overflow-y: auto;
  padding: 16px 20px;
}

/* 步骤条 */
.wp-steps { list-style: none; margin: 0 0 16px; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.wp-steps li { display: flex; align-items: center; gap: 10px; font-size: 13px; color: var(--text-sub); padding: 6px 8px; border-radius: 9px; }
.wp-steps li .dot {
  width: 22px; height: 22px; border-radius: 50%; flex: 0 0 22px;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 12px; border: 1.5px solid var(--border); background: var(--surface);
}
.wp-steps li.active { color: var(--primary); background: var(--primary-soft); font-weight: 600; }
.wp-steps li.active .dot { border-color: var(--primary); color: var(--primary); }
.wp-steps li.done .dot { border-color: #16a34a; color: #16a34a; }

.wp-summary {
  border: 1px solid var(--border); border-radius: 12px; padding: 12px;
  background: var(--surface);
}
.wp-summary h4 { margin: 0 0 8px; font-size: 13px; }
.sum-row { display: flex; justify-content: space-between; gap: 10px; font-size: 12.5px; padding: 4px 0; }
.sum-row .k { color: var(--text-sub); flex: 0 0 auto; }
.sum-row .v { text-align: right; word-break: break-all; }
.tone-ok { color: #16a34a; }
.tone-bad { color: #dc2626; }
.tone-run { color: var(--primary); }
.wp-tip { margin: 12px 0 0; font-size: 12px; line-height: 1.6; color: var(--text-sub); }

/* 通用控件 */
.seg { display: inline-flex; gap: 4px; padding: 3px; border-radius: 10px; background: rgba(127, 140, 160, .12); margin-bottom: 14px; }
.seg button {
  border: none; background: transparent; cursor: pointer; padding: 6px 14px;
  border-radius: 8px; font-size: 13px; color: var(--text-sub); font-family: var(--font);
}
.seg button.on { background: var(--surface); color: var(--primary); font-weight: 600; box-shadow: 0 1px 3px rgba(15, 23, 42, .12); }

.wp-btn {
  border: 1px solid var(--border); background: var(--surface); color: var(--text);
  padding: 7px 14px; border-radius: 9px; font-size: 13px; cursor: pointer;
  font-family: var(--font); transition: all .15s;
}
.wp-btn:hover:not(:disabled) { border-color: var(--primary); color: var(--primary); }
.wp-btn.primary { background: var(--primary); border-color: var(--primary); color: #fff; }
.wp-btn.primary:hover:not(:disabled) { filter: brightness(1.06); color: #fff; }
.wp-btn.danger { background: #dc2626; border-color: #dc2626; color: #fff; }
.wp-btn.tiny { padding: 3px 9px; font-size: 12px; }
.wp-btn:disabled { opacity: .55; cursor: not-allowed; }

.search-row { display: flex; gap: 8px; }
.search-row input {
  flex: 1; min-width: 0; padding: 8px 11px; border: 1px solid var(--border);
  border-radius: 9px; font-size: 13px; background: var(--surface); color: var(--text);
  font-family: var(--font); outline: none;
}
.search-row input:focus { border-color: var(--primary); }

.list-tools { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin: 10px 0 6px; }
.chk { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--text-sub); cursor: pointer; }
.chk input { margin: 0; }
.muted { color: var(--text-sub); font-size: 12.5px; }
.hint { margin: 10px 0; font-size: 12.5px; line-height: 1.6; color: var(--text-sub); }
.hint.tiny { font-size: 11.5px; }
.hint code, .foot-bar code { font-family: ui-monospace, monospace; font-size: 11.5px; padding: 1px 5px; border-radius: 5px; background: rgba(127, 140, 160, .14); }

.dev-list { display: flex; flex-direction: column; gap: 6px; max-height: 300px; overflow-y: auto; padding-right: 2px; }
.dev-row {
  display: flex; align-items: center; gap: 10px; padding: 8px 10px;
  border: 1px solid var(--border); border-radius: 10px; cursor: pointer; transition: all .12s;
}
.dev-row:hover { border-color: var(--primary); }
.dev-row.checked { border-color: var(--primary); background: var(--primary-soft); }
.dev-main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.dev-name { font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dev-mac { font-size: 11.5px; color: var(--text-sub); font-family: ui-monospace, monospace; }
.dev-state { display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; white-space: nowrap; }
.dev-state i { width: 7px; height: 7px; border-radius: 50%; display: inline-block; background: currentColor; }
.dev-state.on { color: #16a34a; }
.dev-state.off { color: #94a3b8; }

.foot-bar {
  margin-top: 12px; padding: 9px 12px; border-radius: 10px;
  background: var(--primary-soft); color: var(--primary); font-size: 12.5px;
}
.foot-bar b { font-size: 13.5px; }

.all-card {
  display: flex; gap: 14px; align-items: flex-start;
  border: 1px solid var(--border); border-radius: 12px; padding: 16px;
}
.all-card .all-icon { font-size: 30px; line-height: 1; }
.all-card strong { font-size: 14px; }
.all-card p { margin: 6px 0 0; font-size: 12.5px; color: var(--text-sub); line-height: 1.6; }

.state { text-align: center; padding: 34px 12px; color: var(--text-sub); font-size: 13px; }
.state.err { color: #dc2626; }
.link { border: none; background: none; color: var(--primary); cursor: pointer; font-size: 12.5px; padding: 0 4px; text-decoration: underline; }

/* 壁纸库 4 列卡片 */
.lib-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.wp-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.wp-card {
  position: relative; text-align: left; padding: 0; overflow: hidden; cursor: pointer;
  border: 1.5px solid var(--border); border-radius: 11px; background: var(--surface);
  color: var(--text); font-family: var(--font); transition: all .15s;
}
.wp-card:hover { border-color: var(--primary); transform: translateY(-1px); }
.wp-card.on { border-color: var(--primary); box-shadow: 0 0 0 2px var(--primary-soft); }
.wp-card .thumb {
  aspect-ratio: 1 / 1; background-color: rgba(127, 140, 160, .12);
  background-size: cover; background-position: center; display: flex; align-items: center; justify-content: center;
}
.thumb-ph { font-size: 11.5px; color: var(--text-sub); }
.wp-card .meta { display: flex; flex-direction: column; gap: 2px; padding: 7px 8px 8px; }
.wp-card .name { font-size: 12px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wp-card .sub { font-size: 11px; color: var(--text-sub); }
.wp-card .tick {
  position: absolute; top: 6px; right: 6px; width: 20px; height: 20px; border-radius: 50%;
  background: var(--primary); color: #fff; font-size: 12px; line-height: 20px; text-align: center;
}
.pager { display: flex; align-items: center; justify-content: center; gap: 10px; margin-top: 12px; }

/* 上传页 */
.up-grid { display: grid; grid-template-columns: 1fr 240px; gap: 16px; align-items: start; }
.up-drop {
  display: flex; flex-direction: column; align-items: center; gap: 6px; text-align: center;
  border: 1.5px dashed var(--border); border-radius: 12px; padding: 30px 16px; cursor: pointer;
  transition: all .15s;
}
.up-drop:hover { border-color: var(--primary); background: var(--primary-soft); }
.up-drop.busy { cursor: progress; opacity: .8; }
.up-drop input[type=file] { display: none; }
.up-ic { font-size: 26px; }
.up-drop strong { font-size: 13.5px; }
.up-drop .muted { font-size: 12px; }
.up-err { color: #dc2626; font-size: 12.5px; margin: 8px 0 0; }
.up-ok { color: #16a34a; font-size: 12.5px; margin: 8px 0 0; line-height: 1.6; }
.preview {
  width: 240px; height: 240px; border-radius: 12px; overflow: hidden;
  border: 1px solid var(--border); background: rgba(127, 140, 160, .12);
  display: flex; align-items: center; justify-content: center;
}
.preview img { width: 100%; height: 100%; display: block; }
.preview-ph { font-size: 12px; color: var(--text-sub); }
.fit-row { display: flex; flex-direction: column; gap: 5px; margin-top: 10px; }

/* 确认卡 */
.confirm-card { border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }
.confirm-card h4 { margin: 0 0 10px; font-size: 14px; }
.kv { display: flex; gap: 12px; padding: 7px 0; border-top: 1px dashed var(--border); font-size: 13px; }
.kv:first-of-type { border-top: none; }
.kv .k { flex: 0 0 72px; color: var(--text-sub); }
.kv .v { flex: 1; word-break: break-all; }
.apply-row { display: flex; flex-direction: column; gap: 6px; }

/* 结果 */
.result-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.rh-left { display: flex; gap: 10px; align-items: flex-start; }
.rh-icon { font-size: 24px; line-height: 1.2; }
.rh-left strong { font-size: 14px; }
.rh-left p { margin: 3px 0 0; }
.rh-nums { display: flex; align-items: baseline; gap: 4px; white-space: nowrap; }
.rh-nums .num { font-size: 17px; font-weight: 700; }
.rh-nums .num.ok { color: #16a34a; }
.rh-nums .num.bad { color: #dc2626; margin-left: 8px; }
.rh-nums .sep { color: var(--text-sub); }
.rh-nums .num-l { font-size: 11.5px; color: var(--text-sub); }

/* 进度条范式对齐 PushScheduler.vue:47-51 */
.bar { display: flex; height: 6px; border-radius: 4px; overflow: hidden; background: rgba(127, 140, 160, .18); }
.bar.pulse { animation: wp-pulse 1.4s ease-in-out infinite; }
@keyframes wp-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .55; } }
.fill.ok { background: #16a34a; transition: width .3s; }
.fill.bad { background: #dc2626; transition: width .3s; }
.bar-meta { display: flex; flex-wrap: wrap; gap: 8px; justify-content: space-between; margin: 8px 0 10px; font-size: 12px; color: var(--text-sub); }
.bar-meta .warn { color: #d97706; }

.dev-result { display: flex; flex-direction: column; gap: 6px; max-height: 260px; overflow-y: auto; }
.res-row {
  display: flex; align-items: center; gap: 10px; padding: 8px 10px;
  border: 1px solid var(--border); border-radius: 10px; font-size: 12.5px;
}
.res-state { flex: 0 0 54px; text-align: center; padding: 2px 0; border-radius: 999px; font-size: 11.5px; background: rgba(127, 140, 160, .14); color: var(--text-sub); }
.res-state.success, .res-state.acked { background: #dcfce7; color: #16a34a; }
.res-state.failed { background: #fee2e2; color: #dc2626; }
.res-state.pending { background: #fef3c7; color: #d97706; }
.res-state.sent { background: var(--primary-soft); color: var(--primary); }
.res-main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.res-err { max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #dc2626; font-size: 11.5px; }
.retry-bar {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  margin-top: 12px; padding: 10px 12px; border-radius: 10px;
  background: rgba(220, 38, 38, .08); color: #dc2626; font-size: 12.5px;
}

/* 底部 */
.wp-footer { border-top: 1px solid var(--border); padding: 12px 20px; background: var(--surface); }
.foot-actions { display: flex; align-items: center; gap: 8px; }
.grow { flex: 1; }
.close-confirm { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 12.5px; color: #d97706; }
.close-confirm span { margin-right: auto; }
.mono { font-family: ui-monospace, monospace; font-size: 12px; }

@media (max-width: 760px) {
  .wp-body { grid-template-columns: 1fr; }
  .wp-side { display: none; }
  .wp-grid { grid-template-columns: repeat(2, 1fr); }
  .up-grid { grid-template-columns: 1fr; }
  .preview { width: 100%; max-width: 240px; height: auto; aspect-ratio: 1 / 1; }
}
</style>
