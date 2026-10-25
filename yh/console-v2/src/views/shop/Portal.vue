<template>
  <div>
    <!-- Hero：不对称分栏（左文案/右产品棚拍），左下浮标打破对称 -->
    <section class="hero">
      <div class="hero-copy">
        <p class="hero-kicker">YUHE · 屿禾工坊官方商店</p>
        <h1>把屿禾<br /><em>带回家</em></h1>
        <p class="hero-sub">智能音箱 · 语音伴侣 · 桌面机器人 · 官方周边<br />下单无需注册，填写收货信息即可</p>
        <div class="hero-btns">
          <button class="btn btn-primary" @click="scrollToGoods">开始选购</button>
          <router-link to="/shop/orders" class="hero-link">查询订单<ShopIcon name="arrow" :size="15"/></router-link>
        </div>
      </div>
      <div class="hero-art">
        <GoodsVisual emoji="🛍️" :size="96" hue="blue" />
        <div class="hero-float">
          <ShopIcon name="truck" :size="17"/><span>24h 内发货</span>
        </div>
      </div>
    </section>

    <!-- 信任条：SVG 图标 + 短句 -->
    <section class="trust" aria-label="服务承诺">
      <span class="trust-item"><ShopIcon name="truck" :size="17"/>24h 内发货</span>
      <span class="trust-item"><ShopIcon name="package" :size="17"/>隐私包装</span>
      <span class="trust-item"><ShopIcon name="badge" :size="17"/>官方正品</span>
      <span class="trust-item"><ShopIcon name="spark" :size="17"/>免注册下单</span>
    </section>

    <!-- 分类 chips -->
    <div class="cat-bar" ref="goodsAnchor">
      <button v-for="c in catChips" :key="c.value" class="chip"
              :class="{ active: category === c.value }" @click="category = c.value">
        {{ c.label }}
      </button>
    </div>

    <div v-if="errorTip" class="error-tip">{{ errorTip }}</div>

    <!-- 商品橱窗：交错入场 -->
    <div v-if="loading" class="goods-grid">
      <div v-for="i in 8" :key="i" class="goods-card sk-card">
        <div class="sk-cover"></div>
        <span class="sk-bar" style="width:60%;margin:12px auto 0"></span>
        <span class="sk-bar" style="width:35%;margin:8px auto 14px"></span>
      </div>
    </div>
    <div v-else-if="shown.length === 0" class="empty-state panel">
      <ShopIcon name="package" :size="34"/>
      <strong>该分类暂无在售商品</strong>
      <p>换个分类看看，或点击「全部」</p>
    </div>
    <div v-else class="goods-grid">
      <div v-for="(g, i) in shown" :key="g.id" class="goods-card" :style="{ animationDelay: (i % 8) * 45 + 'ms' }"
           @click="goDetail(g)">
        <div class="goods-pic" :class="{ oos: Number(g.stock) <= 0 }">
          <GoodsVisual :emoji="g.cover || '🛍️'" :size="58" :hue="hueFor(i)" />
          <span v-if="Number(g.stock) <= 0" class="tag oos-tag">缺货</span>
          <span v-else-if="Number(g.stock) <= 10" class="tag low-tag">仅剩 {{ g.stock }} 件</span>
        </div>
        <div class="goods-name" :title="g.name">{{ g.name }}</div>
        <div class="goods-cat">{{ g.category || '通用' }}</div>
        <div class="goods-foot">
          <span class="goods-price">¥{{ price(g.price) }}</span>
          <button class="btn btn-primary add-btn" :disabled="Number(g.stock) <= 0"
                  @click.stop="addToCart(g)">＋ 加购</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { guestApi } from '../../lib/api'
import { addToCart as localAdd } from '../../lib/shopCart'
import ShopIcon from './ShopIcon.vue'
import GoodsVisual from './GoodsVisual.vue'

const toast = inject('toast', () => {})
const router = useRouter()

const goods = ref([])
const categories = ref([])
const category = ref('')
const loading = ref(false)
const errorTip = ref('')
const goodsAnchor = ref(null)

const HUES = ['blue', 'teal', 'warm', 'violet']
const hueFor = (i) => HUES[i % HUES.length]

const catChips = computed(() => {
  const base = [{ value: '', label: '全部' }]
  for (const c of categories.value) base.push({ value: c, label: c })
  return base
})

const shown = computed(() => {
  if (!category.value) return goods.value
  return goods.value.filter((g) => g.category === category.value)
})

function price(p) {
  if (p === null || p === undefined || p === '') return '0.00'
  const n = Number(p)
  return isNaN(n) ? String(p) : n.toFixed(2)
}

async function load() {
  loading.value = true
  errorTip.value = ''
  try {
    const [g, c] = await Promise.all([guestApi.goodsOnSale(), guestApi.goodsCategories()])
    goods.value = Array.isArray(g.data) ? g.data : []
    categories.value = Array.isArray(c.data) ? c.data : []
  } catch (e) {
    goods.value = []
    errorTip.value = (e && e.msg) || '加载商品失败'
  } finally {
    loading.value = false
  }
}

function goDetail(g) {
  router.push(`/shop/goods/${g.id}`)
}

function addToCart(g) {
  localAdd(g, 1)
  toast(`已加入购物车：${g.name}`)
}

function scrollToGoods() {
  if (goodsAnchor.value) goodsAnchor.value.scrollIntoView({ behavior: 'smooth' })
}

onMounted(load)
</script>

<style scoped>
/* ===== Hero：不对称 + 排版重心 ===== */
.hero {
  display: grid; grid-template-columns: 1.15fr .85fr; gap: 30px; align-items: center;
  margin-bottom: 22px; padding: 8px 0 6px;
}
.hero-kicker {
  margin: 0 0 14px; font-size: 12px; font-weight: 700;
  letter-spacing: .16em; color: var(--text-sub); text-transform: uppercase;
}
.hero h1 {
  margin: 0 0 16px; font-size: clamp(38px, 5.4vw, 58px);
  font-weight: 800; line-height: 1.08; letter-spacing: -.035em; color: var(--text);
  text-wrap: balance;
}
.hero h1 em {
  font-style: normal; color: transparent;
  background: linear-gradient(100deg, #1B6CFF 8%, #37C8A8 96%);
  -webkit-background-clip: text; background-clip: text;
}
.hero-sub {
  margin: 0 0 22px; font-size: 14.5px; line-height: 1.8; color: var(--text-sub);
  max-width: 34em;
}
.hero-btns { display: flex; align-items: center; gap: 20px; }
.hero-link {
  display: inline-flex; align-items: center; gap: 6px;
  color: var(--primary); font-size: 14px; font-weight: 700; text-decoration: none;
  border-bottom: 1.5px solid transparent; transition: border-color .2s ease;
}
.hero-link:hover { border-bottom-color: var(--primary); }
.hero-art {
  position: relative; aspect-ratio: 1.05/1; border-radius: 30px;
  overflow: hidden; display: flex; align-items: center; justify-content: center;
  background: linear-gradient(160deg, rgba(27,108,255,.07), rgba(255,255,255,.85) 55%, rgba(55,200,168,.10));
  box-shadow: 0 24px 60px rgba(27,44,80,.10), inset 0 0 0 1px rgba(255,255,255,.75);
}
.hero-float {
  position: absolute; left: 5%; bottom: 7%; z-index: 4;
  display: inline-flex; align-items: center; gap: 8px;
  background: rgba(255,255,255,.86); backdrop-filter: blur(10px);
  border: 1px solid rgba(27,44,80,.08); border-radius: 14px;
  padding: 9px 14px; font-size: 12.5px; font-weight: 700; color: var(--text);
  box-shadow: 0 10px 26px rgba(27,44,80,.12);
}

/* ===== 信任条 ===== */
.trust {
  display: flex; gap: 10px; flex-wrap: wrap; margin: 0 0 16px;
}
.trust-item {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 12.5px; color: var(--text-sub); font-weight: 600;
  padding: 9px 16px; border-radius: 12px;
  background: rgba(255,255,255,.6); border: 1px solid rgba(27,44,80,.06);
}
.trust-item svg { color: var(--teal-3); }

/* ===== 分类 ===== */
.cat-bar { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0 18px; }
.chip {
  border: 1.5px solid var(--border); background: var(--surface); color: var(--text-sub);
  border-radius: 999px; padding: 7px 17px; font-size: 13px; font-weight: 600;
  cursor: pointer; transition: all .18s ease; font-family: var(--font);
}
.chip:hover { border-color: var(--primary); color: var(--primary); transform: translateY(-1px); }
.chip:active { transform: scale(.97); }
.chip.active { border-color: var(--primary); color: var(--primary); background: var(--primary-soft); }
.chip:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }

/* ===== 商品橱窗 ===== */
.goods-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(218px, 1fr)); gap: 16px; }
.goods-card {
  background: var(--surface); border-radius: 20px;
  box-shadow: 0 2px 10px rgba(27, 44, 80, .05);
  padding: 12px 12px 14px; cursor: pointer;
  display: flex; flex-direction: column;
  transition: transform .22s cubic-bezier(.2,.7,.3,1), box-shadow .22s ease;
  animation: card-in .5s cubic-bezier(.2,.7,.3,1) both;
}
@keyframes card-in {
  from { opacity: 0; transform: translateY(14px); }
  to { opacity: 1; transform: translateY(0); }
}
.goods-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 14px 34px rgba(27, 44, 80, .13);
}
.goods-card:active { transform: translateY(-1px) scale(.99); }
.goods-pic {
  position: relative; aspect-ratio: 1/1; border-radius: 14px; overflow: hidden;
  background: #F4F7FC;
}
.goods-pic.oos :deep(.goods-visual) { filter: grayscale(.75); opacity: .8; }
.tag { position: absolute; top: 8px; right: 8px; border-radius: 8px; padding: 3px 10px; font-size: 11px; font-weight: 700; z-index: 5; }
.oos-tag { background: rgba(15,22,40,.72); color: #fff; }
.low-tag { background: var(--warning); color: #fff; }
.goods-name {
  margin-top: 11px; font-size: 13.5px; font-weight: 650; color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.goods-cat { font-size: 12px; color: var(--text-sub); margin-top: 3px; }
.goods-foot { margin-top: 10px; display: flex; align-items: center; justify-content: space-between; }
.goods-price { color: var(--orange); font-size: 17px; font-weight: 800; font-variant-numeric: tabular-nums; }
.add-btn { padding: 6px 14px; font-size: 12.5px; }
.add-btn:active { transform: scale(.96); }
.sk-card { cursor: default; }
.sk-cover { aspect-ratio: 1/1; border-radius: 14px; background: var(--border); animation: sk-fade 1.2s ease-in-out infinite; }
.sk-bar { display: block; height: 12px; border-radius: 6px; background: var(--border); animation: sk-fade 1.2s ease-in-out infinite; }
@keyframes sk-fade { 0%, 100% { opacity: 1; } 50% { opacity: .4; } }
.error-tip { margin: 12px 0; padding: 8px 12px; border-radius: 8px; background: #FEF2F2; color: #B42318; font-size: 13px; }

@media (max-width: 768px) {
  .hero { grid-template-columns: 1fr; gap: 18px; }
  .hero-art { aspect-ratio: 1.35/1; }
  .hero-btns { justify-content: flex-start; }
  .goods-grid { grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
}
</style>
