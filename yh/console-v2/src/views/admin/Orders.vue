<template>
  <div>
    <div class="page-head">
      <div>
        <h1>订单 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">查看与管理用户订单（状态：0 待处理 / 1 已发货 / 2 已完成）</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="exportCsv" :disabled="loading">⬇ 导出</button>
        <button class="btn btn-primary" @click="openCreate">＋ 新增订单</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <DataTable title="订单列表" :total="total" :pages="pages" v-model:page="page" v-model:pageSize="pageSize" :loading="loading">
      <template #actions>
        <div class="search-bar">
          <input v-model.trim="keyword" placeholder="搜索客户 / 联系方式 / 商品" @keyup.enter="search" />
          <button class="btn btn-ghost" style="padding:6px 14px;font-size:12.5px" @click="search">搜索</button>
        </div>
      </template>

      <table class="data-table orders-table">
        <thead>
          <tr>
            <th class="col-order">订单 / 商品</th>
            <th class="col-customer">客户</th>
            <th class="col-amount">金额</th>
            <th class="col-status">状态</th>
            <th class="col-time">支付时间</th>
            <th class="col-address">收货地址</th>
            <th class="col-actions">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="o in orders" :key="o.id">
            <!-- 订单号与商品合并一列：号做主行（等宽字体可复制），商品做次行自然换行 -->
            <td class="col-order">
              <div class="cell-main mono" :title="o.id">{{ o.id }}</div>
              <div class="cell-sub wrap" :title="o.product || ''">{{ o.product || '—' }}</div>
            </td>
            <!-- 客户名与联系方式合并：长名字换行不撑表 -->
            <td class="col-customer">
              <div class="cell-main wrap" :title="o.user_name || ''">{{ o.user_name || '—' }}</div>
              <div class="cell-sub" :title="o.contact || ''">{{ o.contact || '—' }}</div>
            </td>
            <td class="col-amount"><span class="badge badge-blue amount">¥{{ fmtAmount(o.amount) }}</span></td>
            <td class="col-status">
              <span class="badge" :class="statusBadgeClass(o.shipping_status)">
                <span class="dot"></span>{{ statusText(o.shipping_status) }}
              </span>
              <!-- 备注从独立列收进状态列次行：文字量小，悬浮看全文 -->
              <div v-if="o.remark" class="cell-sub remark" :title="o.remark">📝 {{ o.remark }}</div>
            </td>
            <td class="col-time">
              <div class="time-main">{{ fmtDate(o.pay_time) }}</div>
              <div class="cell-sub">建单 {{ fmtDate(o.create_time) }}</div>
            </td>
            <!-- 地址列自然换行：多行完整可读，不再 20 字截断 -->
            <td class="col-address">
              <div class="addr" :title="o.address || ''">{{ o.address || '—' }}</div>
            </td>
            <td class="col-actions">
              <div class="row-actions">
                <button class="link-btn" @click="openEdit(o)">编辑</button>
                <button class="link-btn danger" @click="remove(o)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="orders.length === 0" class="empty-state">
        <div class="empty-icon">📦</div>
        <strong>暂无订单</strong>
        <p>没有匹配的订单记录</p>
      </div>
    </DataTable>

    <!-- ===== 新增 / 编辑弹窗 ===== -->
    <div v-if="edit.show" class="modal-mask" @click.self="edit.show = false">
      <div class="modal">
        <h3>{{ edit.isCreate ? '新增订单' : '编辑订单' }}</h3>
        <p class="modal-sub" v-if="!edit.isCreate">订单号：{{ edit.form.id }}</p>
        <div class="form-grid">
          <div class="form-row">
            <label>客户名称</label>
            <input v-model="edit.form.userName" placeholder="客户名称" />
          </div>
          <div class="form-row">
            <label>联系方式</label>
            <input v-model="edit.form.contact" placeholder="手机号 / 微信" />
          </div>
          <div class="form-row" style="grid-column: 1 / -1">
            <label>商品</label>
            <input v-model="edit.form.product" placeholder="商品名称" />
          </div>
          <div class="form-row">
            <label>金额（元）</label>
            <input v-model="edit.form.amount" type="number" min="0" step="0.01" placeholder="0.00" />
          </div>
          <div class="form-row">
            <label>状态</label>
            <select v-model="edit.form.status">
              <option v-for="s in STATUS_OPTS" :key="s.v" :value="s.v">{{ s.label }}</option>
            </select>
          </div>
          <div class="form-row">
            <label>支付时间</label>
            <input v-model="edit.form.paymentTime" type="datetime-local" />
          </div>
          <div class="form-row" style="grid-column: 1 / -1">
            <label>收货地址</label>
            <input v-model="edit.form.shippingAddress" placeholder="收货地址" />
          </div>
          <div class="form-row" style="grid-column: 1 / -1">
            <label>备注</label>
            <textarea v-model="edit.form.remark" rows="3" placeholder="备注信息"></textarea>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="edit.show = false">取消</button>
          <button class="btn btn-primary" :disabled="busy" @click="save">{{ busy ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { inject, onMounted, reactive, ref, watch } from 'vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')

const STATUS_OPTS = [
  { v: '0', label: '待处理' },
  { v: '1', label: '已发货' },
  { v: '2', label: '已完成' }
]
const orders = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const pages = ref(1)
const keyword = ref('')
const loading = ref(false)
const busy = ref(false)

const emptyForm = () => ({
  id: '', userName: '', contact: '', product: '', amount: '', status: '0', paymentTime: '', shippingAddress: '', remark: ''
})
const edit = reactive({ show: false, isCreate: false, form: emptyForm() })

// 后端返回 Map 用下划线列名；写入用驼峰键。这里把行映射成驼峰表单。
function rowToForm(o) {
  return {
    id: o.id,
    userName: o.user_name ?? '',
    contact: o.contact ?? '',
    product: o.product ?? '',
    amount: o.amount ?? '',
    status: o.shipping_status ?? '0',
    paymentTime: toLocalInput(o.pay_time),
    shippingAddress: o.address ?? '',
    remark: o.remark ?? ''
  }
}

function toLocalInput(dt) {
  if (!dt) return ''
  const s = String(dt).replace('T', ' ').slice(0, 16) // "2026-10-14 12:30"
  return s ? s.replace(' ', 'T') : ''
}

function statusText(s) {
  // 后端语义：0 待处理 / 1 已发货 / 2 已完成 / 3 已取消（删除=逻辑置 3，列表已过滤）
  if (s === '0') return '待处理'
  if (s === '1') return '已发货'
  if (s === '2') return '已完成'
  if (s === '3') return '已取消'
  return s == null ? '—' : String(s)
}
function statusBadgeClass(s) {
  if (s === '0') return 'badge-orange'
  if (s === '1') return 'badge-green'
  if (s === '2') return 'badge-blue'
  if (s === '3') return 'badge-gray'
  return 'badge-gray'
}
function fmtAmount(a) {
  const n = Number(a)
  return Number.isFinite(n) ? n.toFixed(2) : '—'
}
function fmtDate(d) {
  if (!d) return '—'
  const s = String(d).replace('T', ' ').slice(0, 19)
  return s || '—'
}

async function load() {
  loading.value = true
  try {
    const p = { page: page.value, limit: pageSize.value }
    if (keyword.value) p.keyword = keyword.value
    const res = await adminApi.orderPage(p)
    const data = res.data || {}
    orders.value = data.list || []
    total.value = data.total ?? orders.value.length
  } catch (e) {
    orders.value = []
    total.value = 0
    toast(e.msg || '加载失败', 'error')
  } finally {
    pages.value = Math.max(1, Math.ceil(total.value / pageSize.value))
    loading.value = false
  }
}

function search() {
  page.value = 1
  load()
}

function openCreate() {
  Object.assign(edit, { show: true, isCreate: true, form: emptyForm() })
}
function openEdit(o) {
  Object.assign(edit, { show: true, isCreate: false, form: rowToForm(o) })
}

async function save() {
  busy.value = true
  try {
    const f = edit.form
    const body = {
      id: f.id,
      userName: f.userName,
      contact: f.contact,
      product: f.product,
      amount: f.amount === '' ? null : Number(f.amount),
      status: f.status,
      paymentTime: f.paymentTime || '',
      shippingAddress: f.shippingAddress,
      remark: f.remark
    }
    if (edit.isCreate) {
      await adminApi.orderCreate(body)
      toast('订单已创建')
    } else {
      await adminApi.orderUpdate(body)
      toast('已保存')
    }
    edit.show = false
    load()
  } catch (e) {
    toast(e.msg || '保存失败', 'error')
  } finally {
    busy.value = false
  }
}

function remove(o) {
  askConfirm({
    title: '删除订单',
    message: `确定删除订单「${o.id}」吗？删除后订单标记为已取消，从列表隐藏（数据保留）。`,
    onOk: async () => {
      try {
        await adminApi.orderDelete(o.id)
        toast('已删除')
        load()
      } catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}

async function exportCsv() {
  try {
    const res = await adminApi.orderExport(keyword.value ? { keyword: keyword.value } : {})
    const list = (res.data || []).map(rowToFormExport)
    const headers = ['订单号', '客户', '联系方式', '商品', '金额', '状态', '支付时间', '收货地址', '备注', '创建时间']
    const rows = list.map(o => [o.id, o.user_name, o.contact, o.product, o.amount, statusText(o.shipping_status), o.pay_time, o.address, o.remark, o.create_time])
    const csv = [headers, ...rows]
      .map(r => r.map(c => `"${String(c ?? '').replace(/"/g, '""')}"`).join(','))
      .join('\r\n')
    // UTF-8 BOM 让 Excel 正确识别中文
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `orders_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    toast(e.msg || '导出失败', 'error')
  }
}

// 导出：直接消费后端下划线列名
function rowToFormExport(o) {
  return {
    id: o.id, user_name: o.user_name, contact: o.contact, product: o.product,
    amount: o.amount, shipping_status: o.shipping_status, pay_time: fmtDate(o.pay_time),
    address: o.address, remark: o.remark, create_time: fmtDate(o.create_time)
  }
}

watch([page, pageSize], () => load())
onMounted(load)
</script>

<style scoped>
.search-bar { display: flex; gap: 8px; align-items: center; }
.search-bar input {
  border: 1.5px solid var(--border); border-radius: 10px; padding: 6px 12px;
  font-size: 12.5px; outline: none; background: #fff; color: var(--text); width: 240px;
}
.search-bar input:focus { border-color: var(--primary); }
.mono { font-family: Consolas, "SF Mono", Menlo, monospace; font-size: 12px; }

/* ===== 列布局：table-layout fixed 让宽度声明真正生效，长文本按列宽换行 ===== */
.orders-table { table-layout: fixed; }
.orders-table .col-order { width: 21%; }
.orders-table .col-customer { width: 13%; }
.orders-table .col-amount { width: 9%; }
.orders-table .col-status { width: 12%; }
.orders-table .col-time { width: 13%; }
.orders-table .col-address { width: 20%; }
.orders-table .col-actions { width: 8%; }

/* 单元格内长词（订单号/手机号/长地址）不撑破列宽：断词换行 */
.orders-table td { overflow-wrap: anywhere; }

/* 自然换行区：商品名、客户名、地址——完整可读，悬浮仍给全文 title */
.wrap { white-space: normal; line-height: 1.45; word-break: break-word; }
.addr { font-size: 12.5px; line-height: 1.5; color: var(--text); word-break: break-word; white-space: normal; }

/* 备注收在状态列次行：单行省略，悬浮看全文 */
.remark {
  max-width: 100%; color: var(--text-sub); font-size: 11.5px; margin-top: 4px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* 金额徽章与时间双行的微调 */
.amount { font-variant-numeric: tabular-nums; }
.time-main { font-size: 12.5px; }

.modal-sub { color: var(--text-sub); font-size: 13px; margin: 6px 0 16px; }
.modal h3 { font-size: 17px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.form-row { display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row select, .form-row textarea {
  border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px;
  font-size: 14px; outline: none; font-family: var(--font); background: #fff; color: var(--text);
  /* 弹窗内长内容（地址/备注）同样可断词，不撑破弹窗 */
  overflow-wrap: anywhere;
}
.form-row input:focus, .form-row select:focus, .form-row textarea:focus { border-color: var(--primary); }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }

@media (max-width: 768px) {
  .search-bar input { width: 100%; }
  .search-bar { flex-wrap: wrap; }
  .form-grid { grid-template-columns: 1fr; }
  .form-row[style] { grid-column: 1 / -1 !important; }
  /* 手机上列宽重排：地址/商品获得更多空间，状态列放宽给备注行 */
  .orders-table { min-width: 640px; }
  .orders-table .col-order { width: 26%; }
  .orders-table .col-customer { width: 16%; }
  .orders-table .col-address { width: 24%; }
  .orders-table .col-status { width: 15%; }
}
</style>
