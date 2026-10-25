<template>
  <div>
    <div class="page-head">
      <div>
        <h1>商品 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">商品上架、库存与价格的日常维护（shop_goods 实时读写）</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="openPayConfig">💳 支付设置</button>
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
              <div class="goods-cover" :class="{ 'has-img': isImgCover(g.cover) }">
                <img v-if="isImgCover(g.cover)" :src="coverSrc(g.cover)" alt="" loading="lazy" />
                <template v-else>{{ g.cover || '🛍️' }}</template>
              </div>
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
          <div class="form-row full">
            <label>封面图（上传图片，或填 emoji / 图片 URL）</label>
            <div class="cover-field">
              <div class="cover-preview" :class="{ 'is-empty': !coverPreviewSrc }">
                <img v-if="coverPreviewSrc" :src="coverPreviewSrc" alt="封面预览" />
                <span v-else class="cover-empty-hint">{{ editor.form.cover || '🛍️' }}</span>
              </div>
              <div class="cover-ops">
                <label class="btn btn-ghost cover-upload-btn" :class="{ disabled: coverUploading }">
                  {{ coverUploading ? '上传中…' : '📷 上传图片' }}
                  <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" hidden
                         :disabled="coverUploading" @change="onCoverFile" />
                </label>
                <button v-if="editor.form.cover" type="button" class="btn btn-ghost" @click="editor.form.cover = ''">清除</button>
                <input v-model="editor.form.cover" class="cover-url-input" maxlength="500"
                       placeholder="或直接填 🔊 / https://…" />
              </div>
              <p class="field-hint">支持 PNG/JPG/WebP/GIF，≤8MB；任意尺寸自动裁切铺满，过大过小都会自适应。</p>
            </div>
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

    <!-- 支付设置弹窗（XDDPay 小多支付配置，写 sys_params） -->
    <div v-if="payCfg.show" class="modal-mask" @click.self="payCfg.show = false">
      <div class="modal" style="width:min(600px,94vw);max-height:88vh;overflow:auto">
        <h3>支付设置</h3>
        <div v-if="payCfg.loading" style="color:var(--text-sub);padding:20px 0;text-align:center">加载配置中…</div>
        <template v-else>
          <div class="pc-section">
            <div class="pc-head">
              <strong>小多支付 XDDPay</strong>
              <span class="badge" :class="payCfg.form.configured ? 'badge-green' : 'badge-gray'">
                <span class="dot"></span>{{ payCfg.form.configured ? '已启用' : '未配置' }}
              </span>
            </div>
            <p class="pc-tip">支付网关 gateway.xddpay.com，支持支付宝 / 微信收款。填写的三键须与 XDDPay 商户后台一致。</p>
            <div class="form-grid">
              <div class="form-row">
                <label>App ID（数字）*</label>
                <input v-model.trim="payCfg.form.appId" inputmode="numeric" placeholder="商户后台-应用管理" />
              </div>
              <div class="form-row">
                <label>通信密钥 *</label>
                <div class="pc-secret">
                  <input v-model.trim="payCfg.form.secret" placeholder="签名密钥（保存时留掩码即不变）" />
                  <button v-if="payCfg.form.secret.includes('****')" class="pc-eye" type="button" @click="payCfg.form.secret = ''">重新填写</button>
                </div>
              </div>
              <div class="form-row full">
                <label>异步通知地址</label>
                <input v-model.trim="payCfg.form.notifyUrl" placeholder="https://你的域名/yuhe/shop/pay/xddpay/notify" />
                <span class="pc-note">须公网可达，且原样填到 XDDPay 商户后台的通知地址栏</span>
              </div>
            </div>
          </div>

          <div class="pc-section pc-readonly">
            <div class="pc-head">
              <strong>支付宝（官方直连）</strong>
              <span class="badge" :class="payCfg.alipayConfigured ? 'badge-green' : 'badge-gray'">
                <span class="dot"></span>{{ payCfg.alipayConfigured ? '已启用' : '未配置' }}
              </span>
            </div>
            <p class="pc-tip" v-if="payCfg.alipayConfigured">
              已配置 App ID {{ payCfg.alipayAppId }} · {{ payCfg.alipayGateway || '默认网关' }}。密钥类参数涉安全，请在「系统管理 → 参数管理」维护。
            </p>
            <p class="pc-tip" v-else>官方支付宝直连未配置（当前收款走 XDDPay）。如需启用，在「系统管理 → 参数管理」添加 pay.alipay.* 五键。</p>
          </div>
        </template>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="payCfg.show = false">取消</button>
          <button class="btn btn-primary" :disabled="payCfg.saving" @click="savePayConfig">
            {{ payCfg.saving ? '保存中…' : '保存配置' }}
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
import { coverSrc, isImgCover } from '../../lib/coverImg'

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

// ===== 封面图（上传 / 预览 / URL 兜底） =====
const coverUploading = ref(false)

/** 编辑弹窗实时预览：图片 URL 显示图（本站封面归一化为同源相对路径防混合内容拦截），emoji/文本原样展示 */
const coverPreviewSrc = computed(() => isImgCover(editor.value.form.cover) ? coverSrc(editor.value.form.cover) : '')

/** 选择本地文件 → 立即上传 → 回填 URL（后端内容寻址落盘，同图幂等） */
async function onCoverFile(e) {
  const file = e.target.files && e.target.files[0]
  if (!file) return
  if (file.size > 8 * 1024 * 1024) {
    toast('图片不能超过 8MB', 'error')
    e.target.value = ''
    return
  }
  coverUploading.value = true
  try {
    const res = await adminApi.goodsCoverUpload(file)
    const url = res && res.data && res.data.url
    if (url) {
      editor.value.form.cover = url
      toast('封面已上传')
    } else {
      toast('上传返回异常', 'error')
    }
  } catch (err) {
    toast((err && err.msg) || '上传失败', 'error')
  } finally {
    coverUploading.value = false
    e.target.value = ''
  }
}

// ===== 支付设置（XDDPay 配置，读写 sys_params） =====
const payCfg = ref({
  show: false, loading: false, saving: false,
  form: { appId: '', secret: '', notifyUrl: '', configured: false },
  alipayConfigured: false, alipayAppId: '', alipayGateway: ''
})

async function openPayConfig() {
  payCfg.value.show = true
  payCfg.value.loading = true
  try {
    const res = await adminApi.payConfigGet()
    const d = (res.data || {})
    const x = d.xddpay || {}
    payCfg.value.form = {
      appId: x.appId || '',
      secret: x.secret || '',
      notifyUrl: x.notifyUrl || '',
      configured: !!x.configured
    }
    const a = d.alipay || {}
    payCfg.value.alipayConfigured = !!a.configured
    payCfg.value.alipayAppId = a.appId || ''
    payCfg.value.alipayGateway = a.gateway || ''
  } catch (e) {
    toast((e && e.msg) || '加载支付配置失败', 'error')
    payCfg.value.show = false
  } finally {
    payCfg.value.loading = false
  }
}

async function savePayConfig() {
  const f = payCfg.value.form
  if (f.appId && !/^\d+$/.test(f.appId)) {
    toast('App ID 必须为纯数字', 'error')
    return
  }
  if (f.appId && !f.secret) {
    toast('请填写通信密钥', 'error')
    return
  }
  payCfg.value.saving = true
  try {
    // secret 保持掩码（未改）→ 整个字段不发（后端缺省=不动）；非掩码值→更新/清除
    const body = { appId: f.appId, notifyUrl: f.notifyUrl }
    if (!f.secret.includes('****')) body.secret = f.secret
    const res = await adminApi.payConfigSave(body)
    const d = (res.data || {}).xddpay || {}
    payCfg.value.form = {
      appId: d.appId || '',
      secret: d.secret || '',
      notifyUrl: d.notifyUrl || '',
      configured: !!d.configured
    }
    toast(d.configured ? '支付配置已保存，商店即刻可用 XDDPay 收款' : '配置已保存（App ID/密钥不全，暂不启用）')
  } catch (e) {
    toast((e && e.msg) || '保存失败', 'error')
  } finally {
    payCfg.value.saving = false
  }
}

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
/* 封面是图片时：铺满整个格子（自适应拉满，过大裁切/过小放大） */
.goods-cover.has-img {
  background: var(--border);
}
.goods-cover.has-img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

/* ===== 封面上传字段 ===== */
.cover-field {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cover-preview {
  width: 100%;
  aspect-ratio: 16/9;
  border-radius: 14px;
  background: var(--primary-soft);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 1.5px dashed var(--border);
}
.cover-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover; /* 关键：任意尺寸自适应拉满，保持比例裁切 */
  display: block;
}
.cover-preview.is-empty .cover-empty-hint {
  font-size: 34px;
  line-height: 1;
  word-break: break-all;
  padding: 8px;
  text-align: center;
}
.cover-ops {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.cover-upload-btn {
  cursor: pointer;
  flex-shrink: 0;
}
.cover-upload-btn.disabled {
  opacity: .55;
  pointer-events: none;
}
.cover-url-input {
  flex: 1;
  min-width: 200px;
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

/* 支付设置弹窗 */
.pc-section { border: 1.5px solid var(--border); border-radius: 14px; padding: 16px 18px; margin-bottom: 14px; }
.pc-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.pc-head strong { font-size: 14.5px; }
.pc-tip { font-size: 12.5px; color: var(--text-sub); margin: 0 0 12px; line-height: 1.6; }
.pc-readonly { background: var(--primary-soft); border-style: dashed; }
.pc-secret { display: flex; gap: 8px; align-items: stretch; }
.pc-secret input { flex: 1; }
.pc-eye {
  border: none; background: none; color: var(--primary); font-size: 12px;
  cursor: pointer; white-space: nowrap; padding: 0 4px; font-weight: 600;
}
.pc-eye:hover { text-decoration: underline; }
.pc-note { font-size: 11.5px; color: var(--text-sub); }

@media (max-width: 640px) {
  .form-grid { grid-template-columns: 1fr; }
}
</style>
