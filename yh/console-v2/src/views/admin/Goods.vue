<template>
  <div>
    <div class="page-head">
      <div>
        <h1>商品 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">商品上架、库存与价格的日常维护（shop_goods 实时读写）</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="openCreate">＋ 新增商品</button>
        <button class="btn btn-ghost" @click="exportExcel" :disabled="exporting">{{ exporting ? '导出中…' : '⬇ 导出 Excel' }}</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">{{ loading ? '加载中…' : '↻ 刷新' }}</button>
      </div>
    </div>

    <div class="hero-row">
      <div class="hero-blob" style="min-height:170px">
        <div>
          <div class="en">GOODS / INVENTORY</div>
          <h2>商品</h2>
          <p>上架状态与库存水位一览</p>
        </div>
        <div class="blob-3d">🛍️</div>
      </div>
      <div class="stats-grid">
        <StatCard icon="package" label="在售商品" :value="stats.onSale" note="上架中" />
        <StatCard icon="gem" label="总库存" :value="stats.totalStock" note="件" />
        <StatCard icon="clock" label="低库存" :value="stats.lowStock" note="≤10 预警" />
        <StatCard icon="zap" label="缺货" :value="stats.outOfStock" note="库存为0" />
      </div>
    </div>

    <DataTable title="商品清单" :total="total" :pages="pages" v-model:page="page" v-model:pageSize="pageSize" :loading="loading">
      <template #actions>
        <input
          v-model="keyword"
          placeholder="搜索名称 / 分类"
          class="filter-input"
          @keyup.enter="doSearch"
        />
        <select v-model="categoryFilter" class="filter-select" @change="doSearch">
          <option value="">全部分类</option>
          <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
        </select>
        <button class="btn btn-ghost" style="padding:6px 14px;font-size:12.5px" @click="doSearch">搜索</button>
        <button class="btn btn-ghost" style="padding:6px 14px;font-size:12.5px" @click="resetSearch">重置</button>
      </template>

      <div v-if="errorTip" class="error-tip">{{ errorTip }}</div>

      <table class="data-table">
        <thead>
          <tr>
            <th style="width:120px">封面</th>
            <th>商品名称</th>
            <th style="width:110px">分类</th>
            <th style="width:100px">售价</th>
            <th style="width:100px">库存</th>
            <th style="width:100px">状态</th>
            <th style="width:150px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="7" style="text-align:center;color:var(--text-sub);padding:28px 0">加载中…</td>
          </tr>
          <tr v-else-if="goods.length === 0">
            <td colspan="7" style="text-align:center;color:var(--text-sub);padding:28px 0">
              {{ errorTip ? '数据加载失败' : '暂无商品，点击「＋ 新增商品」创建' }}
            </td>
          </tr>
          <tr v-for="g in goods" :key="g.id">
            <td>
              <div class="goods-cover">{{ g.cover || '🛍️' }}</div>
            </td>
            <td>
              <div class="cell-main">{{ g.name || '—' }}</div>
              <div class="cell-sub">{{ g.remark || '' }}</div>
            </td>
            <td style="color:var(--text-sub)">{{ g.category || '—' }}</td>
            <td><strong class="price-text">¥{{ formatPrice(g.price) }}</strong></td>
            <td>
              <span :class="stockCls(g.stock)">{{ g.stock ?? 0 }}</span>
            </td>
            <td>
              <span class="badge" :class="Number(g.status) === 1 ? 'badge-green' : 'badge-gray'">
                <span class="dot"></span>{{ Number(g.status) === 1 ? '在售' : '下架' }}
              </span>
            </td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="openEdit(g)">编辑</button>
                <button class="link-btn" @click="toggleStatus(g)">
                  {{ Number(g.status) === 1 ? '下架' : '上架' }}
                </button>
                <button class="link-btn danger" @click="removeGoods(g)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </DataTable>

    <!-- 新增 / 编辑商品弹窗 -->
    <div v-if="editor.show" class="modal-mask" @click.self="editor.show = false">
      <div class="modal" style="width:min(560px,94vw);max-height:88vh;overflow:auto">
        <h3>{{ editor.isEdit ? '编辑商品' : '新增商品' }}</h3>
        <div class="form-grid">
          <div class="form-row full">
            <label>商品名称 *</label>
            <input v-model="editor.form.name" maxlength="200" placeholder="例如：屿禾智能音箱 YH-01" />
          </div>
          <div class="form-row">
            <label>封面（emoji 或图片 URL）</label>
            <input v-model="editor.form.cover" maxlength="500" placeholder="🔊 或 https://…" />
          </div>
          <div class="form-row">
            <label>分类</label>
            <input v-model="editor.form.category" maxlength="50" list="cat-list" placeholder="例如：智能硬件" />
            <datalist id="cat-list">
              <option v-for="c in categories" :key="c" :value="c"></option>
            </datalist>
          </div>
          <div class="form-row">
            <label>售价（元）*</label>
            <input v-model="editor.form.price" type="number" step="0.01" min="0" placeholder="0.00" />
          </div>
          <div class="form-row">
            <label>库存（件）*</label>
            <input v-model="editor.form.stock" type="number" min="0" step="1" placeholder="0" />
          </div>
          <div class="form-row">
            <label>上架状态</label>
            <select v-model="editor.form.status">
              <option :value="1">在售</option>
              <option :value="0">下架</option>
            </select>
          </div>
          <div class="form-row">
            <label>排序值（大者靠前）</label>
            <input v-model="editor.form.sort" type="number" step="1" placeholder="0" />
          </div>
          <div class="form-row full">
            <label>备注</label>
            <textarea v-model="editor.form.remark" rows="2" placeholder="选填"></textarea>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="editor.show = false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="saveGoods">
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

const goods = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const keyword = ref('')
const categoryFilter = ref('')
const categories = ref([])
const loading = ref(false)
const saving = ref(false)
const errorTip = ref('')
const stats = ref({ onSale: 0, totalStock: 0, lowStock: 0, outOfStock: 0 })

const editor = ref({ show: false, isEdit: false, form: emptyForm() })

const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

function emptyForm() {
  return { id: null, name: '', cover: '', category: '', price: '', stock: 0, status: 1, sort: 0, remark: '' }
}

function formatPrice(p) {
  if (p === null || p === undefined || p === '') return '0.00'
  const n = Number(p)
  return isNaN(n) ? String(p) : n.toFixed(2)
}

function stockCls(stock) {
  const n = Number(stock ?? 0)
  if (n <= 0) return 'stock-out'
  if (n <= 10) return 'stock-low'
  return 'stock-ok'
}

async function load() {
  loading.value = true
  errorTip.value = ''
  try {
    const res = await adminApi.goodsPage({
      page: page.value, limit: pageSize.value,
      keyword: keyword.value, category: categoryFilter.value
    })
    const data = res.data || {}
    goods.value = Array.isArray(data.list) ? data.list : []
    total.value = data.total ?? 0
  } catch (e) {
    goods.value = []
    total.value = 0
    errorTip.value = (e && e.msg) || '加载商品失败'
    toast((e && e.msg) || '加载商品失败', 'error')
  } finally {
    loading.value = false
  }
}

/** 统计四卡走全量导出接口（商品量级小，一次取回即可） */
async function loadStats() {
  try {
    const res = await adminApi.goodsExportList()
    const list = res.data || []
    let onSale = 0
    let totalStock = 0
    let lowStock = 0
    let outOfStock = 0
    for (const g of list) {
      const stock = Number(g.stock ?? 0)
      if (Number(g.status) === 1) onSale++
      totalStock += stock
      if (stock <= 0) outOfStock++
      else if (stock <= 10) lowStock++
    }
    stats.value = { onSale, totalStock, lowStock, outOfStock }
  } catch {
    stats.value = { onSale: 0, totalStock: 0, lowStock: 0, outOfStock: 0 }
  }
}

async function loadCategories() {
  try {
    const res = await adminApi.goodsCategories()
    categories.value = Array.isArray(res.data) ? res.data : []
  } catch { /* 分类加载失败不影响主流程 */ }
}

function doSearch() {
  page.value = 1
  load()
}

function resetSearch() {
  keyword.value = ''
  categoryFilter.value = ''
  page.value = 1
  load()
}

const exporting = ref(false)

const EXPORT_COLUMNS = [
  { title: 'ID', key: 'id' },
  { title: '商品名称', key: 'name' },
  { title: '分类', key: 'category' },
  { title: '售价', key: 'price' },
  { title: '库存', key: 'stock' },
  { title: '状态', key: 'status' },
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

/** 生成 Excel 2003 SpreadsheetML（.xls），Excel / WPS 原生可直接打开，零依赖（照 Orders.vue） */
function buildXls(rows) {
  const head = EXPORT_COLUMNS
    .map((c) => `<Cell ss:StyleID="h"><Data ss:Type="String">${xmlEsc(c.title)}</Data></Cell>`)
    .join('')
  const body = rows
    .map((r) => {
      const cells = EXPORT_COLUMNS.map((c) => {
        if (c.key === 'status') {
          const t = Number(r.status) === 1 ? '在售' : '下架'
          return `<Cell><Data ss:Type="String">${xmlEsc(t)}</Data></Cell>`
        }
        if (c.key === 'price') {
          const n = Number(r.price)
          if (r.price !== null && r.price !== undefined && r.price !== '' && !isNaN(n)) {
            return `<Cell><Data ss:Type="Number">${n}</Data></Cell>`
          }
          return '<Cell><Data ss:Type="String"></Data></Cell>'
        }
        return `<Cell><Data ss:Type="String">${xmlEsc(r[c.key])}</Data></Cell>`
      }).join('')
      return `<Row>${cells}</Row>`
    })
    .join('')
  return '<?xml version="1.0" encoding="UTF-8"?>\n' +
    '<?mso-application progid="Excel.Sheet"?>\n' +
    '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">' +
    '<Styles><Style ss:ID="h"><Font ss:Bold="1"/></Style></Styles>' +
    '<Worksheet ss:Name="商品"><Table>' +
    `<Row>${head}</Row>${body}` +
    '</Table></Worksheet></Workbook>'
}

async function exportExcel() {
  if (exporting.value) return
  exporting.value = true
  try {
    const res = await adminApi.goodsExportList()
    const rows = Array.isArray(res.data) ? res.data : []
    if (rows.length === 0) {
      toast('没有可导出的商品', 'error')
      return
    }
    const blob = new Blob([buildXls(rows)], { type: 'application/vnd.ms-excel;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `商品导出_${stamp()}.xls`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    toast(`已导出 ${rows.length} 条商品`)
  } catch (e) {
    toast((e && e.msg) || '导出失败', 'error')
  } finally {
    exporting.value = false
  }
}

function openCreate() {
  editor.value = { show: true, isEdit: false, form: emptyForm() }
}

function openEdit(g) {
  editor.value = {
    show: true,
    isEdit: true,
    form: {
      id: g.id,
      name: g.name || '',
      cover: g.cover || '',
      category: g.category || '',
      price: g.price === null || g.price === undefined ? '' : g.price,
      stock: g.stock ?? 0,
      status: Number(g.status) === 1 ? 1 : 0,
      sort: g.sort ?? 0,
      remark: g.remark || ''
    }
  }
}

async function saveGoods() {
  const f = editor.value.form
  if (!String(f.name || '').trim()) {
    toast('请填写商品名称', 'error')
    return
  }
  if (f.price === '' || isNaN(Number(f.price))) {
    toast('请填写正确的售价', 'error')
    return
  }
  if (f.stock === '' || isNaN(Number(f.stock)) || Number(f.stock) < 0) {
    toast('请填写正确的库存', 'error')
    return
  }
  saving.value = true
  try {
    const payload = {
      name: String(f.name).trim(),
      cover: f.cover || '',
      category: f.category || '',
      price: Number(f.price),
      stock: Number(f.stock),
      status: f.status,
      sort: Number(f.sort ?? 0),
      remark: f.remark || ''
    }
    if (editor.value.isEdit) {
      await adminApi.goodsUpdate(f.id, payload)
      toast('商品已更新')
    } else {
      await adminApi.goodsCreate(payload)
      toast('商品已创建')
    }
    editor.value.show = false
    await Promise.all([load(), loadStats(), loadCategories()])
  } catch (e) {
    toast((e && e.msg) || '保存失败', 'error')
  } finally {
    saving.value = false
  }
}

async function toggleStatus(g) {
  try {
    const next = Number(g.status) === 1 ? 0 : 1
    await adminApi.goodsToggle(g.id, next)
    toast(next === 1 ? '已上架' : '已下架')
    await Promise.all([load(), loadStats()])
  } catch (e) {
    toast((e && e.msg) || '操作失败', 'error')
  }
}

async function removeGoods(g) {
  if (!window.confirm(`确定删除商品「${g.name}」？此操作不可恢复。`)) return
  try {
    await adminApi.goodsDelete(g.id)
    toast('商品已删除')
    await Promise.all([load(), loadStats()])
  } catch (e) {
    toast((e && e.msg) || '删除失败', 'error')
  }
}

// DataTable 的 v-model:page / v-model:pageSize 变更后自动重新拉取
watch([page, pageSize], () => load())

onMounted(async () => {
  await Promise.all([load(), loadStats(), loadCategories()])
})
</script>

<style scoped>
.goods-cover {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: var(--primary-soft);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  overflow: hidden;
}
.price-text { color: var(--orange); }
.stock-ok { color: var(--text); font-weight: 600; }
.stock-low { color: var(--warning); font-weight: 700; }
.stock-out { color: var(--danger); font-weight: 700; }
.link-btn.danger { color: var(--danger); }
.error-tip {
  margin: 0 20px 10px;
  padding: 8px 12px;
  border-radius: 8px;
  background: #FEF2F2;
  color: #B42318;
  font-size: 13px;
}
.filter-input {
  border: 1.5px solid var(--border);
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 12.5px;
  outline: none;
  background: var(--surface);
  color: var(--text);
  width: 200px;
}
.filter-select {
  border: 1.5px solid var(--border);
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 12.5px;
  outline: none;
  background: var(--surface);
  color: var(--text);
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
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 6px; }

@media (max-width: 640px) {
  .form-grid { grid-template-columns: 1fr; }
}
</style>
