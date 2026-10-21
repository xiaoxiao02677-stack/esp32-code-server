<template>
  <div>
    <div class="page-head">
      <div>
        <h1>屿禾 <span style="color:var(--primary)">商店</span></h1>
        <p class="sub">智能硬件与周边，一键加购下单</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="load" :disabled="loading">{{ loading ? '加载中…' : '↻ 刷新' }}</button>
        <button class="btn btn-primary" @click="goCart">
          🛒 购物车<template v-if="cartCount > 0">（{{ cartCount }}）</template>
        </button>
      </div>
    </div>

    <div class="hero-row">
      <div class="hero-blob" style="min-height:170px">
        <div>
          <div class="en">YUHE / STORE</div>
          <h2>把屿禾带回家</h2>
          <p>音箱、开发板与限定周边</p>
        </div>
        <div class="blob-actions">
          <button class="btn btn-primary" @click="scrollToGoods">开始选购</button>
        </div>
        <div class="blob-3d">🛍️</div>
      </div>
      <div class="stats-grid">
        <StatCard icon="package" label="在售商品" :value="onSaleCount" note="可购买" />
        <StatCard icon="gem" label="我的积分" :value="points" note="可用于抵扣" />
        <StatCard icon="zap" label="低库存" :value="lowStockCount" note="欲购从速" />
        <StatCard icon="check-circle" label="我的订单" :value="myOrderCount" note="累计" />
      </div>
    </div>

    <!-- 分类 chips -->
    <div class="cat-bar" ref="goodsAnchor">
      <button
        v-for="c in catChips"
        :key="c.value"
        class="chip"
        :class="{ active: category === c.value }"
        @click="pickCategory(c.value)"
      >{{ c.label }}</button>
    </div>

    <div v-if="errorTip" class="error-tip">{{ errorTip }}</div>

    <!-- 商品橱窗 -->
    <div v-if="loading" class="goods-grid">
      <div v-for="i in 8" :key="i" class="goods-card sk-card">
        <div class="sk-cover"></div>
        <span class="sk-bar" style="width:60%;margin:12px auto 0"></span>
        <span class="sk-bar" style="width:35%;margin:8px auto 14px"></span>
      </div>
    </div>
    <div v-else-if="shown.length === 0" class="empty-state">
      <div class="empty-icon"><span>🛍️</span></div>
      <strong>该分类暂无在售商品</strong>
      <p>换个分类看看，或点击「全部」</p>
    </div>
    <div v-else class="goods-grid">
      <div v-for="g in shown" :key="g.id" class="goods-card" @click="goDetail(g)">
        <div class="goods-pic" :class="{ oos: Number(g.stock) <= 0 }">
          <span class="pic">{{ g.cover || '🛍️' }}</span>
          <span v-if="Number(g.stock) <= 0" class="oos-tag">缺货</span>
          <span v-else-if="Number(g.stock) <= 10" class="low-tag">仅剩 {{ g.stock }} 件</span>
        </div>
        <div class="goods-name" :title="g.name">{{ g.name }}</div>
        <div class="goods-cat">{{ g.category || '通用' }}</div>
        <div class="goods-foot">
          <span class="goods-price">¥{{ price(g.price) }}</span>
          <button class="btn btn-primary add-btn" :disabled="Number(g.stock) <= 0 || addingId === g.id"
                  @click.stop="addToCart(g)">
            {{ addingId === g.id ? '加购中…' : '＋ 加购' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import StatCard from '../../components/StatCard.vue'
import { shopApi } from '../../lib/api'

const toast = inject('toast', () => {})
const router = useRouter()

const goods = ref([])
const categories = ref([])
const category = ref('')
const loading = ref(false)
const errorTip = ref('')
const addingId = ref(null)
const cartCount = ref(0)
const points = ref(0)
const myOrderCount = ref(0)

const catChips = computed(() => {
  const base = [{ value: '', label: '全部' }]
  for (const c of categories.value) {
    base.push({ value: c, label: c })
  }
  return base
})

const shown = computed(() => {
  if (!category.value) return goods.value
  return goods.value.filter((g) => g.category === category.value)
})

const onSaleCount = computed(() => goods.value.length)
const lowStockCount = computed(() => goods.value.filter((g) => Number(g.stock) <= 10).length)

function price(p) {
  if (p === null || p === undefined || p === '') return '0.00'
  const n = Number(p)
  return isNaN(n) ? String(p) : n.toFixed(2)
}

async function load() {
  loading.value = true
  errorTip.value = ''
  try {
    const [g, c, cart, pointsRes] = await Promise.all([
      shopApi.goodsOnSale(),
      shopApi.goodsCategories(),
      shopApi.cartList().catch(() => null),
      shopApi.myPoints().catch(() => null)
    ])
    goods.value = Array.isArray(g.data) ? g.data : []
    categories.value = Array.isArray(c.data) ? c.data : []
    cartCount.value = cart && Array.isArray(cart.data) ? cart.data.length : 0
    points.value = pointsRes && pointsRes.data && pointsRes.data.points !== undefined ? pointsRes.data.points : 0
  } catch (e) {
    goods.value = []
    errorTip.value = (e && e.msg) || '加载商品失败'
    toast((e && e.msg) || '加载商品失败', 'error')
  } finally {
    loading.value = false
  }
}

async function loadOrderCount() {
  try {
    const res = await shopApi.myOrders({ page: 1, limit: 1, keyword: '' })
    myOrderCount.value = (res.data && res.data.total) || 0
  } catch { /* 静默 */ }
}

function pickCategory(v) {
  category.value = v
}

function scrollToGoods() {
  if (goodsAnchor.value) goodsAnchor.value.scrollIntoView({ behavior: 'smooth' })
}

function goDetail(g) {
  router.push(`/shop/goods/${g.id}`)
}

function goCart() {
  router.push('/shop/cart')
}

async function addToCart(g) {
  if (addingId.value) return
  addingId.value = g.id
  try {
    await shopApi.cartAdd({ goodsId: g.id, qty: 1 })
    cartCount.value += 1
    toast(`已加入购物车：${g.name}`)
  } catch (e) {
    toast((e && e.msg) || '加购失败', 'error')
  } finally {
    addingId.value = null
  }
}

onMounted(async () => {
  await Promise.all([load(), loadOrderCount()])
})
</script>

<style scoped>
.cat-bar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin: 16px 0;
}
.chip {
  border: 1.5px solid var(--border);
  background: var(--surface);
  color: var(--text-sub);
  border-radius: 999px;
  padding: 6px 16px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all .15s ease;
  font-family: var(--font);
}
.chip:hover { border-color: var(--primary); color: var(--primary); }
.chip.active {
  border-color: var(--primary);
  color: var(--primary);
  background: var(--primary-soft);
}
.goods-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}
.goods-card {
  background: var(--surface);
  border-radius: 16px;
  box-shadow: 0 2px 12px rgba(27, 44, 80, .05);
  padding: 14px;
  cursor: pointer;
  transition: all .2s ease;
  display: flex;
  flex-direction: column;
}
.goods-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(27, 44, 80, .12);
}
.goods-pic {
  position: relative;
  aspect-ratio: 1 / 1;
  background: var(--primary-soft);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 56px;
  overflow: hidden;
}
.goods-pic .pic { line-height: 1; }
.goods-pic.oos { filter: grayscale(.7); opacity: .75; }
.oos-tag, .low-tag {
  position: absolute;
  top: 8px;
  right: 8px;
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 11px;
  font-weight: 700;
}
.oos-tag { background: rgba(15, 22, 40, .7); color: #fff; }
.low-tag { background: var(--warning); color: #fff; }
.goods-name {
  margin-top: 10px;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.goods-cat { font-size: 12px; color: var(--text-sub); margin-top: 2px; }
.goods-foot {
  margin-top: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.goods-price { color: var(--orange); font-size: 16px; font-weight: 800; font-variant-numeric: tabular-nums; }
.add-btn { padding: 6px 14px; font-size: 12.5px; }
.sk-card { cursor: default; }
.sk-cover { aspect-ratio: 1 / 1; border-radius: 12px; background: var(--border); animation: sk-fade 1.2s ease-in-out infinite; }
.sk-bar { display: block; height: 12px; border-radius: 6px; background: var(--border); animation: sk-fade 1.2s ease-in-out infinite; }
@keyframes sk-fade { 0%, 100% { opacity: 1; } 50% { opacity: .4; } }
.error-tip {
  margin: 12px 0;
  padding: 8px 12px;
  border-radius: 8px;
  background: #FEF2F2;
  color: #B42318;
  font-size: 13px;
}
@media (max-width: 640px) {
  .goods-grid { grid-template-columns: 1fr; }
}
</style>
