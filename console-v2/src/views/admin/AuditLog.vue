<template>
  <div>
    <div class="page-head">
      <div>
        <h1>审计 <span style="color:var(--primary)">日志</span></h1>
        <p class="sub">敏感操作全链路留痕</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="hero-row">
      <div class="hero-blob" style="min-height:170px">
        <div>
          <div class="en">AUDIT / TRAIL</div>
          <h2>审计</h2>
          <p>谁在何时对什么做了什么</p>
        </div>
        <div class="blob-3d">📜</div>
      </div>
      <div class="stats-grid">
        <StatCard icon="📜" label="日志总数" :value="total" />
        <StatCard icon="✅" label="成功" :value="successCount" note="本页" />
        <StatCard icon="❌" label="失败" :value="failCount" note="本页" />
        <StatCard icon="🧭" label="模块" :value="modules.length" note="已载入" />
      </div>
    </div>

    <DataTable title="审计日志" :total="total" :pages="pages" v-model:page="page" v-model:pageSize="pageSize">
      <template #actions>
        <select v-model="query.module" style="border:1.5px solid var(--border);border-radius:10px;padding:6px 10px;font-size:12.5px;outline:none">
          <option value="">全部模块</option>
          <option v-for="m in modules" :key="m" :value="m">{{ m }}</option>
        </select>
        <input v-model="query.operation" placeholder="操作（如 save / login）" style="border:1.5px solid var(--border);border-radius:10px;padding:6px 12px;font-size:12.5px;outline:none" @keyup.enter="search" />
        <input v-model="query.userId" placeholder="用户ID" style="border:1.5px solid var(--border);border-radius:10px;padding:6px 12px;font-size:12.5px;outline:none;width:110px" @keyup.enter="search" />
        <input v-model="query.startDate" type="date" style="border:1.5px solid var(--border);border-radius:10px;padding:6px 10px;font-size:12.5px;outline:none" />
        <input v-model="query.endDate" type="date" style="border:1.5px solid var(--border);border-radius:10px;padding:6px 10px;font-size:12.5px;outline:none" />
        <button class="btn btn-ghost" style="padding:6px 14px;font-size:12.5px" @click="search">搜索</button>
      </template>
      <table class="data-table">
        <thead>
          <tr><th>时间</th><th>用户</th><th>模块</th><th>操作</th><th>目标</th><th>结果</th><th>耗时</th><th>IP</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="a in logs" :key="a.id">
            <td style="color:var(--text-sub)" class="mono">{{ a.createdDate || '—' }}</td>
            <td>
              <div class="cell-main">{{ a.username || '—' }}</div>
              <div class="cell-sub mono">{{ a.userId ?? '' }}</div>
            </td>
            <td><span class="badge badge-blue"><span class="dot"></span>{{ a.module || '—' }}</span></td>
            <td class="mono" style="font-size:12.5px">{{ a.operation || '—' }}</td>
            <td class="mono" style="font-size:12px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="targetText(a)">
              {{ a.targetType ? a.targetType + ':' + (a.targetId ?? '') : '—' }}
            </td>
            <td>
              <span class="badge" :class="a.result === 1 ? 'badge-green' : 'badge-gray'">
                <span class="dot"></span>{{ a.result === 1 ? '成功' : '失败' }}
              </span>
            </td>
            <td>{{ a.duration != null ? a.duration + 'ms' : '—' }}</td>
            <td class="mono" style="font-size:12px;color:var(--text-sub)">{{ a.ip || '—' }}</td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="openDetail(a)">详情</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="logs.length === 0" class="empty-state">
        <div class="empty-icon">📜</div>
        <strong>暂无审计日志</strong>
        <p>调整筛选条件试试</p>
      </div>
    </DataTable>

    <!-- 详情弹窗 -->
    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal" style="width:min(680px,94vw);max-height:88vh;overflow:auto">
        <h3>审计详情</h3>
        <div class="detail-grid">
          <div class="kv"><span class="k">日志ID</span><span class="v mono">{{ detail.id ?? '—' }}</span></div>
          <div class="kv"><span class="k">用户</span><span class="v">{{ detail.username || '—' }}<span class="mono sub" v-if="detail.userId"> ({{ detail.userId }})</span></span></div>
          <div class="kv"><span class="k">模块</span><span class="v">{{ detail.module || '—' }}</span></div>
          <div class="kv"><span class="k">操作</span><span class="v mono">{{ detail.operation || '—' }}</span></div>
          <div class="kv"><span class="k">目标</span><span class="v mono">{{ targetText(detail) }}</span></div>
          <div class="kv"><span class="k">结果</span><span class="v">
            <span class="badge" :class="detail.result === 1 ? 'badge-green' : 'badge-gray'"><span class="dot"></span>{{ detail.result === 1 ? '成功' : '失败' }}</span>
          </span></div>
          <div class="kv"><span class="k">耗时</span><span class="v">{{ detail.duration != null ? detail.duration + ' ms' : '—' }}</span></div>
          <div class="kv"><span class="k">IP</span><span class="v mono">{{ detail.ip || '—' }}</span></div>
          <div class="kv"><span class="k">时间</span><span class="v mono">{{ detail.createdDate || '—' }}</span></div>
          <div class="kv full"><span class="k">请求接口</span><span class="v mono">{{ detail.requestMethod || '—' }} {{ detail.requestUri || '—' }}</span></div>
          <div class="kv full" v-if="detail.errorMsg"><span class="k">错误信息</span><span class="v err">{{ detail.errorMsg }}</span></div>
        </div>
        <div class="detail-block" v-if="prettyParams">
          <div class="block-label">请求参数</div>
          <pre class="params-pre">{{ prettyParams }}</pre>
        </div>
        <div class="detail-block" v-if="detail.userAgent">
          <div class="block-label">User-Agent</div>
          <pre class="ua-pre">{{ detail.userAgent }}</pre>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="detail = null">关闭</button>
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

const logs = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const pages = ref(1)
const loading = ref(false)
const modules = ref([])
const detail = ref(null)

const query = reactive({ module: '', operation: '', userId: '', startDate: '', endDate: '' })

const successCount = computed(() => logs.value.filter(a => a.result === 1).length)
const failCount = computed(() => logs.value.filter(a => a.result !== 1).length)
const prettyParams = computed(() => {
  if (!detail.value) return ''
  const p = detail.value.params
  if (p == null) return ''
  if (typeof p === 'string') {
    try { return JSON.stringify(JSON.parse(p), null, 2) } catch (e) { return p }
  }
  try { return JSON.stringify(p, null, 2) } catch (e) { return String(p) }
})

function targetText(a) {
  if (!a || !a.targetType) return '—'
  return a.targetType + ':' + (a.targetId ?? '')
}

async function load() {
  loading.value = true
  try {
    // GET /admin/audit/page —— page 从 1 开始
    const res = await adminApi.auditPage({
      userId: query.userId || undefined,
      module: query.module || undefined,
      operation: query.operation || undefined,
      startDate: query.startDate || undefined,
      endDate: query.endDate || undefined,
      page: page.value,
      limit: pageSize.value
    })
    const data = res.data || {}
    logs.value = (data.list || []).map(a => ({
      ...a,
      createdDate: a.createdDate ? String(a.createdDate).slice(0, 19) : '—'
    }))
    total.value = data.total ?? logs.value.length
  } catch (e) {
    toast(e.msg || '加载失败', 'error')
  } finally {
    pages.value = Math.max(1, Math.ceil(total.value / pageSize.value))
    loading.value = false
  }
}

async function loadModules() {
  try {
    const res = await adminApi.auditModules()
    modules.value = Array.isArray(res.data) ? res.data : (res.data?.list || [])
  } catch (e) {
    toast(e.msg || '模块加载失败', 'error')
  }
}

function search() {
  if (page.value !== 1) page.value = 1
  else load()
}

function openDetail(a) {
  detail.value = a
}

watch(page, () => load())
watch(pageSize, () => {
  if (page.value !== 1) page.value = 1
  else load()
})

onMounted(() => { load(); loadModules() })
</script>

<style scoped>
.detail-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px 16px; }
.kv { display: flex; flex-direction: column; gap: 3px; }
.kv.full { grid-column: 1 / -1; }
.kv .k { font-size: 11.5px; color: var(--text-sub); font-weight: 600; }
.kv .v { font-size: 13px; color: var(--text); word-break: break-all; }
.kv .v .sub { color: var(--text-sub); font-size: 12px; }
.kv .v.err { color: var(--danger); }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.modal h3 { font-size: 17px; margin-bottom: 18px; }
.detail-block { margin-top: 14px; }
.block-label { font-size: 11.5px; color: var(--text-sub); font-weight: 600; margin-bottom: 5px; }
.params-pre {
  background: #F6F8FA; border: 1px solid var(--border); border-radius: 10px;
  padding: 12px; font-size: 12px; max-height: 220px; overflow: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: var(--text); white-space: pre-wrap; word-break: break-all; margin: 0;
}
.ua-pre {
  background: #F6F8FA; border: 1px solid var(--border); border-radius: 10px;
  padding: 10px 12px; font-size: 12px; max-height: 80px; overflow: auto;
  color: var(--text-sub); white-space: pre-wrap; word-break: break-all; margin: 0;
}
.modal-actions { margin-top: 18px; }
</style>
