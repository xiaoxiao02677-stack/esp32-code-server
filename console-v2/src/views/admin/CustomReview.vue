<template>
  <div>
    <div class="page-head">
      <div>
        <h1>自定义 <span style="color:var(--primary)">审核</span></h1>
        <p class="sub">审核用户提交的自定义模型与音色</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="🧩" label="待审核模型" :value="tab === 'model' ? pendingCount : '—'" note="当前筛选下" />
      <StatCard icon="🎙" label="待审核音色" :value="tab === 'voice' ? pendingCount : '—'" note="当前筛选下" />
      <StatCard icon="✅" label="已通过" :value="passedCount" note="当前筛选下" />
      <StatCard icon="⛔" label="已驳回" :value="rejectedCount" note="当前筛选下" />
    </div>

    <!-- ① 模型 / 音色 tab -->
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px">
      <div class="chip" :class="{ active: tab === 'model' }" @click="pickTab('model')">🧩 模型</div>
      <div class="chip" :class="{ active: tab === 'voice' }" @click="pickTab('voice')">🎙 音色</div>
    </div>

    <DataTable :title="tab === 'model' ? '自定义模型审核' : '自定义音色审核'" :total="total" :pages="pages" v-model:page="page" v-model:pageSize="pageSize">
      <template #actions>
        <!-- ② auditStatus chip：全部 / 待审核0 / 已通过1 / 已驳回2 -->
        <div class="status-chips">
          <div v-for="s in STATUS_FILTERS" :key="s.value" class="chip sm" :class="{ active: auditStatus === s.value }" @click="pickStatus(s.value)">
            {{ s.label }}
          </div>
        </div>
        <!-- keyword 搜索 -->
        <div class="search-bar">
          <input v-model.trim="keyword" :placeholder="tab === 'model' ? '搜索模型名 / 用户名 / 供应器' : '搜索音色名 / 用户名'" @keyup.enter="search" />
          <button class="btn btn-ghost" style="padding:6px 14px;font-size:12.5px" @click="search">搜索</button>
        </div>
      </template>

      <!-- ===== 模型表 ===== -->
      <table v-if="tab === 'model'" class="data-table">
        <thead>
          <tr><th>所属用户</th><th>类型</th><th>名称</th><th>接口地址</th><th>密钥</th><th>审核状态</th><th>配额</th><th>提交时间</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="m in models" :key="m.id">
            <td>
              <div class="cell-main">{{ m.username || '—' }}</div>
              <div class="cell-sub">{{ m.userId || '' }}</div>
            </td>
            <td><span class="badge badge-blue">{{ m.modelType || '—' }}</span></td>
            <td>
              <div class="cell-main">{{ m.modelName }}</div>
              <div class="cell-sub">{{ m.providerCode || '' }}</div>
            </td>
            <td>
              <div class="cell-main mono" :title="m.baseUrl || '—'">{{ truncate(m.baseUrl, 28) }}</div>
            </td>
            <td style="font-size:12px;color:var(--text-sub)">{{ m.apiKeyMasked || '—' }}</td>
            <td>
              <span class="badge" :class="statusBadgeClass(m.auditStatus)">
                <span class="dot"></span>{{ statusText(m.auditStatus) }}
              </span>
              <div v-if="m.auditRemark" class="cell-sub remark" :title="m.auditRemark">驳回意见：{{ m.auditRemark }}</div>
            </td>
            <td>
              <div class="cell-main" style="font-size:13px">{{ quotaText(m.quotaLimit) }}</div>
              <div class="cell-sub">已用 {{ m.usedCount ?? 0 }} 次</div>
            </td>
            <td style="font-size:12px;color:var(--text-sub)">{{ fmtDate(m.createDate) }}</td>
            <td>
              <div class="row-actions">
                <button v-if="m.auditStatus !== 1" class="link-btn" @click="approveModel(m)">通过</button>
                <button v-if="m.auditStatus !== 2" class="link-btn danger" @click="openRejectModel(m)">驳回</button>
                <button class="link-btn" @click="openQuota(m)">配额</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- ===== 音色表（同构） ===== -->
      <table v-else class="data-table">
        <thead>
          <tr><th>所属用户</th><th>名称</th><th>编码</th><th>语言</th><th>参考文本</th><th>审核状态</th><th>提交时间</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="v in voices" :key="v.id">
            <td>
              <div class="cell-main">{{ v.username || '—' }}</div>
              <div class="cell-sub">{{ v.userId || '' }}</div>
            </td>
            <td><div class="cell-main">{{ v.name }}</div></td>
            <td style="font-size:12px">{{ v.ttsVoice || '—' }}</td>
            <td style="font-size:12px">{{ v.languages || '—' }}</td>
            <td>
              <div class="cell-main mono" :title="v.referenceText || '—'">{{ truncate(v.referenceText, 30) }}</div>
            </td>
            <td>
              <span class="badge" :class="statusBadgeClass(v.auditStatus)">
                <span class="dot"></span>{{ statusText(v.auditStatus) }}
              </span>
              <div v-if="v.auditRemark" class="cell-sub remark" :title="v.auditRemark">驳回意见：{{ v.auditRemark }}</div>
            </td>
            <td style="font-size:12px;color:var(--text-sub)">{{ fmtDate(v.createDate) }}</td>
            <td>
              <div class="row-actions">
                <button v-if="v.auditStatus !== 1" class="link-btn" @click="approveVoice(v)">通过</button>
                <button v-if="v.auditStatus !== 2" class="link-btn danger" @click="openRejectVoice(v)">驳回</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="(tab === 'model' ? models : voices).length === 0" class="empty-state">
        <div class="empty-icon">{{ tab === 'model' ? '🧩' : '🎙' }}</div>
        <strong>{{ auditStatus === null ? '暂无待审核' : '暂无数据' }}</strong>
        <p>{{ auditStatus === null ? '没有待审核的自定义' + (tab === 'model' ? '模型' : '音色') : '切换筛选条件试试' }}</p>
      </div>
    </DataTable>

    <!-- ===== 驳回弹窗：填写审核意见 → pass:false, remark ===== -->
    <div v-if="reject.show" class="modal-mask" @click.self="reject.show = false">
      <div class="modal">
        <h3>驳回{{ tab === 'model' ? '模型' : '音色' }}</h3>
        <p class="modal-sub">「{{ reject.name }}」</p>
        <div class="form-row">
          <label>驳回意见（必填）</label>
          <textarea v-model="reject.remark" rows="4" placeholder="说明驳回原因，将展示给用户"></textarea>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="reject.show = false">取消</button>
          <button class="btn btn-danger" :disabled="busy || !reject.remark.trim()" @click="doReject">{{ busy ? '提交中…' : '确认驳回' }}</button>
        </div>
      </div>
    </div>

    <!-- ===== 配额弹窗：number 或清空=不限 → customModelQuota ===== -->
    <div v-if="quota.show" class="modal-mask" @click.self="quota.show = false">
      <div class="modal">
        <h3>调用配额</h3>
        <p class="modal-sub">「{{ quota.name }}」当前：{{ quotaText(quota.current) }}（已用 {{ quota.used ?? 0 }} 次）</p>
        <div class="form-row">
          <label>配额上限（次）</label>
          <input v-model="quota.input" type="number" min="0" placeholder="留空 = 不限" />
        </div>
        <p class="field-hint">清空后保存即为「不限」</p>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="quota.show = false">取消</button>
          <button class="btn btn-primary" :disabled="busy" @click="doQuota">{{ busy ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, reactive, ref, watch } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')

const STATUS_FILTERS = [
  { value: null, label: '全部' },
  { value: 0, label: '⏳ 待审核' },
  { value: 1, label: '✅ 已通过' },
  { value: 2, label: '⛔ 已驳回' }
]

const tab = ref('model')          // model / voice
const auditStatus = ref(null)     // null 全部 / 0 待 / 1 过 / 2 驳
const keyword = ref('')
const models = ref([])
const voices = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const pages = ref(1)
const loading = ref(false)
const busy = ref(false)

const reject = reactive({ show: false, id: '', name: '', remark: '' })
const quota = reactive({ show: false, id: '', name: '', current: null, used: 0, input: '' })

const list = computed(() => (tab.value === 'model' ? models.value : voices.value))
const pendingCount = computed(() => list.value.filter(x => x.auditStatus === 0).length)
const passedCount = computed(() => list.value.filter(x => x.auditStatus === 1).length)
const rejectedCount = computed(() => list.value.filter(x => x.auditStatus === 2).length)

function statusText(s) {
  return s === 0 ? '待审核' : s === 1 ? '已通过' : '已驳回'
}
function statusBadgeClass(s) {
  return s === 0 ? 'badge-orange' : s === 1 ? 'badge-green' : 'badge-gray'
}
function quotaText(q) {
  return q == null ? '不限' : `${q} 次`
}
function truncate(s, n) {
  const t = String(s ?? '')
  return t.length > n ? t.slice(0, n) + '…' : t
}
function fmtDate(d) {
  return d ? String(d).slice(0, 19).replace('T', ' ') : '—'
}

// ===== 真分页加载 =====
async function load() {
  loading.value = true
  try {
    const p = { page: page.value, limit: pageSize.value }
    if (auditStatus.value !== null) p.auditStatus = auditStatus.value
    if (keyword.value) p.keyword = keyword.value
    if (tab.value === 'model') {
      const res = await adminApi.customModelAuditPage(p)
      const data = res.data || {}
      models.value = (data.list || []).map(m => ({ ...m, userId: m.userId ?? m.userid }))
      total.value = data.total ?? models.value.length
    } else {
      const res = await adminApi.customVoiceAuditPage(p)
      const data = res.data || {}
      voices.value = (data.list || []).map(v => ({ ...v, userId: v.userId ?? v.userid }))
      total.value = data.total ?? voices.value.length
    }
  } catch (e) {
    models.value = []; voices.value = []; total.value = 0
    toast(e.msg || '加载失败', 'error')
  } finally {
    pages.value = Math.max(1, Math.ceil(total.value / pageSize.value))
    loading.value = false
  }
}

function pickTab(t) {
  if (tab.value === t) return
  tab.value = t
  page.value = 1
  load()
}
function pickStatus(s) {
  if (auditStatus.value === s) return
  auditStatus.value = s
  page.value = 1
  load()
}
function search() {
  page.value = 1
  load()
}

// ===== 模型操作 =====
function approveModel(m) {
  askConfirm({
    title: '通过审核',
    message: `确定通过「${m.modelName}」吗？通过后该模型可供用户调用。`,
    onOk: async () => {
      try {
        await adminApi.customModelAudit({ id: m.id, pass: true })
        toast('已通过')
        load()
      } catch (e) { toast(e.msg || '操作失败', 'error') }
    }
  })
}

function openRejectModel(m) {
  Object.assign(reject, { show: true, id: m.id, name: m.modelName, remark: m.auditRemark || '' })
}

function approveVoice(v) {
  askConfirm({
    title: '通过审核',
    message: `确定通过音色「${v.name}」吗？通过后该音色可供用户调用。`,
    onOk: async () => {
      try {
        await adminApi.customVoiceAudit({ id: v.id, pass: true })
        toast('已通过')
        load()
      } catch (e) { toast(e.msg || '操作失败', 'error') }
    }
  })
}

function openRejectVoice(v) {
  Object.assign(reject, { show: true, id: v.id, name: v.name, remark: v.auditRemark || '' })
}

async function doReject() {
  if (!reject.remark.trim()) { toast('请填写驳回意见', 'error'); return }
  busy.value = true
  try {
    const body = { id: reject.id, pass: false, remark: reject.remark.trim() }
    if (tab.value === 'model') await adminApi.customModelAudit(body)
    else await adminApi.customVoiceAudit(body)
    toast('已驳回')
    reject.show = false
    load()
  } catch (e) { toast(e.msg || '操作失败', 'error') }
  finally { busy.value = false }
}

// ===== 配额（仅模型） =====
function openQuota(m) {
  Object.assign(quota, {
    show: true, id: m.id, name: m.modelName,
    current: m.quotaLimit ?? null, used: m.usedCount ?? 0,
    input: m.quotaLimit != null ? String(m.quotaLimit) : ''
  })
}

async function doQuota() {
  busy.value = true
  try {
    // 清空 = 不限（quotaLimit: null）
    const raw = quota.input.trim()
    const quotaLimit = raw === '' ? null : Number(raw)
    if (raw !== '' && (!Number.isFinite(quotaLimit) || quotaLimit < 0)) {
      toast('请输入合法的配额数值', 'error')
      return
    }
    await adminApi.customModelQuota({ id: quota.id, quotaLimit })
    toast('配额已更新')
    quota.show = false
    load()
  } catch (e) { toast(e.msg || '保存失败', 'error') }
  finally { busy.value = false }
}

// 分页切换
watch([page, pageSize], () => load())

onMounted(load)
</script>

<style scoped>
.chip { padding: 8px 16px; border-radius: 999px; background: var(--bg-card); border: 1.5px solid var(--border); cursor: pointer; font-size: 13px; }
.chip.active { border-color: var(--primary); color: var(--primary); font-weight: 600; }
.chip.sm { padding: 5px 12px; font-size: 12px; }
.status-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.search-bar { display: flex; gap: 8px; align-items: center; }
.search-bar input {
  border: 1.5px solid var(--border); border-radius: 10px; padding: 6px 12px;
  font-size: 12.5px; outline: none; background: #fff; color: var(--text); width: 200px;
}
.search-bar input:focus { border-color: var(--primary); }
.mono { font-family: Consolas, "SF Mono", Menlo, monospace; }
.remark { max-width: 180px; color: var(--danger); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.modal-sub { color: var(--text-sub); font-size: 13px; margin: 6px 0 16px; }
.modal h3 { font-size: 17px; }
.modal .form-row { margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.modal .form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.modal .form-row input, .modal .form-row textarea {
  border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px;
  font-size: 14px; outline: none; font-family: var(--font); background: #fff; color: var(--text);
}
.modal .form-row input:focus, .modal .form-row textarea:focus { border-color: var(--primary); }
.field-hint { font-size: 11.5px; color: var(--text-sub); margin: 2px 0 0; }
.btn-danger { background: var(--danger); color: #fff; box-shadow: 0 4px 14px rgba(240,83,77,.35); }
</style>
