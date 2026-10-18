<template>
  <div>
    <div class="page-head">
      <div>
        <h1>订单 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">订单数据、发货状态的查看与维护（实时读写 order_table）</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="openCreate">＋ 新增订单</button>
        <button class="btn btn-ghost" @click="exportExcel" :disabled="exporting">{{ exporting ? '导出中…' : '⬇ 导出 Excel' }}</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">{{ loading ? '加载中…' : '↻ 刷新' }}</button>
      </div>
    </div>

    <div class="hero-row">
      <div class="hero-blob" style="min-height:170px">
        <div>
          <div class="en">ORDERS / SALES</div>
          <h2>订单</h2>
          <p>全量订单数据与发货状态管理</p>
        </div>
        <div class="blob-3d">📦</div>
      </div>
      <div class="stats-grid">
        <StatCard icon="package" label="订单总数" :value="stats.total" note="有效订单" />
        <StatCard icon="clock" label="待发货" :value="stats.pending" note="待处理" />
        <StatCard icon="🚚" label="已发货" :value="stats.shipped" note="在途" />
        <StatCard icon="check-circle" label="已完成" :value="stats.done" note="已签收" />
      </div>
    </div>

    <DataTable title="订单清单" :total="total" :pages="pages" v-model:page="page" v-model:pageSize="pageSize" :loading="loading">
      <template #actions>
        <input
          v-model="keyword"
          placeholder="搜索姓名 / 联系方式 / 商品"
          class="filter-input"
          @keyup.enter="doSearch"
        />
        <button class="btn btn-ghost" style="padding:6px 14px;font-size:12.5px" @click="doSearch">搜索</button>
        <button class="btn btn-ghost" style="padding:6px 14px;font-size:12.5px" @click="resetSearch">重置</button>
      </template>

      <div v-if="errorTip" class="error-tip">{{ errorTip }}</div>

      <table class="data-table">
        <thead>
          <tr>
            <th style="width:150px">订单ID</th>
            <th style="width:100px">用户姓名</th>
            <th style="width:130px">联系方式</th>
            <th>商品</th>
            <th style="width:100px">金额</th>
            <th style="width:150px">支付时间</th>
            <th style="width:110px">发货状态</th>
            <th style="width:90px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="8" style="text-align:center;color:var(--text-sub);padding:28px 0">加载中…</td>
          </tr>
          <tr v-else-if="orders.length === 0">
            <td colspan="8" style="text-align:center;color:var(--text-sub);padding:28px 0">
              {{ errorTip ? '数据加载失败' : '暂无订单数据，点击「＋ 新增订单」创建' }}
            </td>
          </tr>
          <tr v-for="order in orders" :key="order.id">
            <td class="mono-cell">{{ order.id }}</td>
            <td>
              <div class="cell-main">{{ order.user_name || '—' }}</div>
            </td>
            <td style="color:var(--text-sub)">{{ order.contact || '—' }}</td>
            <td :title="order.product">{{ order.product || '—' }}</td>
            <td><strong>¥{{ formatAmount(order.amount) }}</strong></td>
            <td style="color:var(--text-sub)">{{ formatTime(order.pay_time) }}</td>
            <td>
              <span class="badge" :class="statusBadge(order.shipping_status).cls">
                <span class="dot"></span>{{ statusBadge(order.shipping_status).text }}
              </span>
            </td>
            <td>
              <button class="link-btn" @click="openEdit(order)">编辑</button>
            </td>
          </tr>
        </tbody>
      </table>
    </DataTable>

    <!-- 新增 / 编辑订单弹窗 -->
    <div v-if="editor.show" class="modal-mask" @click.self="editor.show = false">
      <div class="modal" style="width:min(560px,94vw);max-height:88vh;overflow:auto">
        <h3>{{ editor.isEdit ? '编辑订单' : '新增订单' }}</h3>
        <div class="form-grid">
          <div class="form-row">
            <label>用户姓名 *</label>
            <input v-model="editor.form.userName" maxlength="100" placeholder="请输入用户姓名" />
          </div>
          <div class="form-row">
            <label>联系方式 *</label>
            <input v-model="editor.form.contact" maxlength="50" placeholder="手机号 / 微信" />
          </div>
          <div class="form-row full">
            <label>商品名称 *</label>
            <input v-model="editor.form.product" placeholder="例如：ESP32-S3 开发板" />
          </div>
          <div class="form-row">
            <label>金额 *</label>
            <input v-model="editor.form.amount" type="number" step="0.01" min="0" placeholder="0.00" />
          </div>
          <div class="form-row">
            <label>发货状态</label>
            <select v-model="editor.form.status">
              <option value="0">待发货</option>
              <option value="1">已发货</option>
              <option value="2">已完成</option>
              <option value="3">已取消</option>
            </select>
          </div>
          <div class="form-row full">
            <label>支付时间</label>
            <input v-model="editor.form.paymentTime" type="datetime-local" />
            <p class="field-hint">留空则表示未支付</p>
          </div>
          <div class="form-row full">
            <label>收货地址</label>
            <input v-model="editor.form.shippingAddress" placeholder="收货地址" />
          </div>
          <div class="form-row full">
            <label>备注</label>
            <textarea v-model="editor.form.remark" rows="2" placeholder="选填"></textarea>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="editor.show = false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="saveOrder">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, ref, watch } from 'vue'
import DataTable from '../../components/DataTable.vue'
import StatCard from '../../components/StatCard.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast', () => {})

const orders = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const keyword = ref('')
const loading = ref(false)
const saving = ref(false)
const errorTip = ref('')
const stats = ref({ total: 0, pending: 0, shipped: 0, done: 0 })

const editor = ref({ show: false, isEdit: false, form: emptyForm() })

const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

function emptyForm() {
  return {
    id: null,
    userName: '',
    contact: '',
    product: '',
    amount: '',
    paymentTime: '',
    shippingAddress: '',
    status: '0',
    remark: ''
  }
}

/** 库里历史上存过中文状态（如"已发货"），统一归一成数字码再展示 */
function statusCode(s) {
  if (s === null || s === undefined || s === '') return '0'
  const v = String(s).trim()
  const cnMap = { '待发货': '0', '已发货': '1', '已完成': '2', '已取消': '3', '已删除': '3' }
  return cnMap[v] !== undefined ? cnMap[v] : v
}

function statusBadge(s) {
  const map = {
    '0': { text: '待发货', cls: 'badge-orange' },
    '1': { text: '已发货', cls: 'badge-blue' },
    '2': { text: '已完成', cls: 'badge-green' },
    '3': { text: '已取消', cls: 'badge-gray' }
  }
  return map[statusCode(s)] || { text: String(s || '未知'), cls: 'badge-gray' }
}

function formatTime(t) {
  if (!t) return '—'
  return String(t).slice(0, 16).replace('T', ' ')
}

function formatAmount(a) {
  if (a === null || a === undefined || a === '') return '0.00'
  const n = Number(a)
  return isNaN(n) ? String(a) : n.toFixed(2)
}

async function load() {
  loading.value = true
  errorTip.value = ''
  try {
    const res = await adminApi.orderPage({ page: page.value, limit: pageSize.value, keyword: keyword.value })
    const data = res.data || {}
    orders.value = Array.isArray(data.list) ? data.list : []
    total.value = data.total ?? 0
  } catch (e) {
    orders.value = []
    total.value = 0
    errorTip.value = (e && e.msg) || '加载订单失败'
    toast((e && e.msg) || '加载订单失败', 'error')
  } finally {
    loading.value = false
  }
}

/** 统计卡走全量导出接口（订单量级小，一次取回即可） */
async function loadStats() {
  try {
    const res = await adminApi.orderExportList()
    const list = res.data || []
    let pending = 0
    let shipped = 0
    let done = 0
    for (const o of list) {
      const c = statusCode(o.shipping_status)
      if (c === '0') pending++
      else if (c === '1') shipped++
      else if (c === '2') done++
    }
    stats.value = { total: list.length, pending, shipped, done }
  } catch {
    stats.value = { total: total.value, pending: 0, shipped: 0, done: 0 }
  }
}

function doSearch() {
  page.value = 1
  load()
}

function resetSearch() {
  keyword.value = ''
  page.value = 1
  load()
}

const exporting = ref(false)

const EXPORT_COLUMNS = [
  { title: '订单ID', key: 'id' },
  { title: '用户姓名', key: 'user_name' },
  { title: '联系方式', key: 'contact' },
  { title: '商品', key: 'product' },
  { title: '金额', key: 'amount' },
  { title: '支付时间', key: 'pay_time' },
  { title: '收货地址', key: 'address' },
  { title: '发货状态', key: 'shipping_status' },
  { title: '备注', key: 'remark' }
]

function xmlEsc(v) {
  return String(v === null || v === undefined ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&apos;')
}

function stamp() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`
}

/** 生成 Excel 2003 SpreadsheetML（.xls），Excel / WPS 原生可直接打开，零依赖 */
function buildXls(rows) {
  const head = EXPORT_COLUMNS
    .map((c) => `<Cell ss:StyleID="h"><Data ss:Type="String">${xmlEsc(c.title)}</Data></Cell>`)
    .join('')
  const body = rows
    .map((r) => {
      const cells = EXPORT_COLUMNS.map((c) => {
        if (c.key === 'amount') {
          const n = Number(r.amount)
          if (r.amount !== null && r.amount !== undefined && r.amount !== '' && !isNaN(n)) {
            return `<Cell><Data ss:Type="Number">${n}</Data></Cell>`
          }
          return '<Cell><Data ss:Type="String"></Data></Cell>'
        }
        let v = r[c.key]
        if (c.key === 'shipping_status') v = statusBadge(v).text
        else if (c.key === 'pay_time') v = r.pay_time ? formatTime(r.pay_time) : ''
        return `<Cell><Data ss:Type="String">${xmlEsc(v)}</Data></Cell>`
      }).join('')
      return `<Row>${cells}</Row>`
    })
    .join('')
  return '<?xml version="1.0" encoding="UTF-8"?>\n' +
    '<?mso-application progid="Excel.Sheet"?>\n' +
    '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">' +
    '<Styles><Style ss:ID="h"><Font ss:Bold="1"/></Style></Styles>' +
    '<Worksheet ss:Name="订单"><Table>' +
    `<Row>${head}</Row>${body}` +
    '</Table></Worksheet></Workbook>'
}

async function exportExcel() {
  if (exporting.value) return
  exporting.value = true
  try {
    const res = await adminApi.orderExportList({ keyword: keyword.value })
    const rows = Array.isArray(res.data) ? res.data : []
    if (rows.length === 0) {
      toast('没有可导出的订单', 'error')
      return
    }
    const blob = new Blob([buildXls(rows)], { type: 'application/vnd.ms-excel;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `订单导出_${stamp()}.xls`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    toast(`已导出 ${rows.length} 条订单`)
  } catch (e) {
    toast((e && e.msg) || '导出失败', 'error')
  } finally {
    exporting.value = false
  }
}

function openCreate() {
  editor.value = { show: true, isEdit: false, form: emptyForm() }
}

function openEdit(order) {
  editor.value = {
    show: true,
    isEdit: true,
    form: {
      id: order.id,
      userName: order.user_name || '',
      contact: order.contact || '',
      product: order.product || '',
      amount: order.amount === null || order.amount === undefined ? '' : order.amount,
      paymentTime: toLocalInput(order.pay_time),
      shippingAddress: order.address || '',
      status: statusCode(order.shipping_status),
      remark: order.remark || ''
    }
  }
}

/** "2026-10-15 10:30:00" / "2026-10-15T10:30:00" → datetime-local 需要的 "YYYY-MM-DDTHH:mm" */
function toLocalInput(t) {
  if (!t) return ''
  const s = String(t).replace(' ', 'T')
  return s.length >= 16 ? s.slice(0, 16) : s
}

async function saveOrder() {
  const f = editor.value.form
  if (!f.userName.trim() || !f.contact.trim() || !f.product.trim()) {
    toast('请填写姓名、联系方式与商品名称', 'error')
    return
  }
  if (f.amount === '' || isNaN(Number(f.amount))) {
    toast('请填写正确的金额', 'error')
    return
  }
  saving.value = true
  try {
    const payload = {
      userName: f.userName.trim(),
      contact: f.contact.trim(),
      product: f.product.trim(),
      amount: Number(f.amount),
      paymentTime: f.paymentTime ? f.paymentTime.replace('T', ' ') + ':00' : null,
      shippingAddress: f.shippingAddress || '',
      status: f.status,
      remark: f.remark || ''
    }
    if (editor.value.isEdit) {
      await adminApi.orderUpdate(f.id, payload)
      toast('订单已更新')
    } else {
      await adminApi.orderCreate(payload)
      toast('订单已创建')
    }
    editor.value.show = false
    await Promise.all([load(), loadStats()])
  } catch (e) {
    toast((e && e.msg) || '保存失败', 'error')
  } finally {
    saving.value = false
  }
}

// DataTable 的 v-model:page / v-model:pageSize 变更后自动重新拉取
watch([page, pageSize], () => load())

onMounted(async () => {
  await Promise.all([load(), loadStats()])
})
</script>

<style scoped>
.mono-cell {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  color: var(--text-sub);
}

.error-tip {
  margin: 0 20px 10px;
  padding: 8px 12px;
  border-radius: 8px;
  background: #FEF2F2;
  color: #B42318;
  font-size: 13px;
}

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 22, 40, .45);
  display: grid;
  place-items: center;
  z-index: 150;
}
.modal {
  background: var(--surface);
  border-radius: 16px;
  padding: 26px 28px;
  box-shadow: 0 24px 60px rgba(15, 22, 40, .22);
}
.modal h3 { font-size: 17px; margin-bottom: 18px; }

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 14px;
}
.form-row { margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.form-row.full { grid-column: 1 / -1; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row select, .form-row textarea {
  border: 1.5px solid var(--border);
  border-radius: 10px;
  padding: 8px 12px;
  font-size: 13px;
  outline: none;
  background: var(--surface);
  color: var(--text);
  font-family: inherit;
}
.form-row input:focus, .form-row select:focus, .form-row textarea:focus { border-color: var(--primary); }
.form-row textarea { resize: vertical; }
.field-hint { font-size: 11.5px; color: var(--text-sub); margin: 2px 0 0; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 6px; }

@media (max-width: 640px) {
  .form-grid { grid-template-columns: 1fr; }
}
</style>
