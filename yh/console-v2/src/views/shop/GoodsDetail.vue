<template>
  <div>
    <!-- 面包屑：SVG 箭头分隔 -->
    <nav class="crumb" aria-label="面包屑">
      <router-link to="/shop">商店</router-link>
      <ShopIcon name="arrow" :size="13"/>
      <span>{{ goods.name || '商品详情' }}</span>
    </nav>

    <div v-if="loading" class="detail-skel">
      <div class="sk-pic"></div>
      <div class="sk-info">
        <span class="sk-bar" style="width:70%"></span>
        <span class="sk-bar" style="width:40%"></span>
        <span class="sk-bar" style="width:55%"></span>
      </div>
    </div>

    <div v-else-if="errorTip" class="error-tip">{{ errorTip }}</div>

    <div v-else class="detail-box">
      <div class="detail-pic" :class="{ oos: Number(goods.stock) <= 0 }">
        <GoodsVisual :emoji="goods.cover || '🛍️'" :size="118" hue="blue" />
        <span v-if="Number(goods.stock) <= 0" class="tag oos-tag">缺货</span>
        <span v-else-if="Number(goods.stock) <= 10" class="tag low-tag">仅剩 {{ goods.stock }} 件</span>
      </div>

      <div class="detail-info">
        <h1 class="name">{{ goods.name }}</h1>
        <p class="desc">{{ goods.remark || '用心甄选 · 密封包装 · 安心到手' }}</p>

        <div class="price-box">
          <span class="label">售价</span>
          <span class="value">¥{{ price(goods.price) }}</span>
          <span class="tax">含标准运费</span>
        </div>

        <div class="meta">
          <span><ShopIcon name="package" :size="15"/>密封寄出</span>
          <span><ShopIcon name="truck" :size="15"/>24h 内发货</span>
          <span><ShopIcon name="badge" :size="15"/>官方正品</span>
        </div>

        <div class="qty-row">
          <span class="qty-label">数量</span>
          <div class="stepper">
            <button class="step-btn" :disabled="qty <= 1" @click="qty = Math.max(1, qty - 1)" aria-label="减少数量">−</button>
            <input class="qty-input" type="number" min="1" max="99" v-model.number="qty" @change="clampQty" aria-label="商品数量" />
            <button class="step-btn" :disabled="qty >= 99" @click="qty = Math.min(99, qty + 1)" aria-label="增加数量">＋</button>
          </div>
          <span class="stock-hint">库存 {{ goods.stock }} 件</span>
        </div>

        <div class="actions">
          <button class="btn btn-primary big" :disabled="!canBuy" @click="buyNow">立即购买</button>
          <button class="btn btn-ghost big" :disabled="!canBuy" @click="addCart">加入购物车</button>
        </div>

        <div class="notice">
          <p class="notice-title"><ShopIcon name="spark" :size="15"/>温馨提示</p>
          <p>所有商品均为官方正品，支持售后。<br />拍下后我们会尽快为你密封打包，安心等待收货就好。</p>
        </div>
      </div>
    </div>

    <div v-if="!loading && goods.remark" class="detail-long">
      <h3>商品详情</h3>
      <p class="long-text">{{ goods.remark }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { guestApi } from '../../lib/api'
import { addToCart as localAdd } from '../../lib/shopCart'
import ShopIcon from './ShopIcon.vue'
import GoodsVisual from './GoodsVisual.vue'

const route = useRoute()
const router = useRouter()
const toast = inject('toast', () => {})

const goods = ref({})
const loading = ref(false)
const errorTip = ref('')
const qty = ref(1)

const canBuy = computed(() => Number(goods.value.stock) > 0)

function price(p) {
  if (p === null || p === undefined || p === '') return '0.00'
  const n = Number(p)
  return isNaN(n) ? String(p) : n.toFixed(2)
}

function clampQty() {
  if (!Number.isFinite(qty.value) || qty.value < 1) qty.value = 1
  if (qty.value > 99) qty.value = 99
}

async function load() {
  loading.value = true
  errorTip.value = ''
  try {
    const res = await guestApi.goodsOnSale()
    const list = Array.isArray(res.data) ? res.data : []
    const found = list.find((g) => String(g.id) === String(route.params.id))
    if (!found) {
      errorTip.value = '商品不存在或已下架'
      return
    }
    goods.value = found
  } catch (e) {
    errorTip.value = (e && e.msg) || '加载商品失败'
  } finally {
    loading.value = false
  }
}

function addCart() {
  localAdd(goods.value, qty.value)
  toast(`已加入购物车：${goods.value.name}`)
}

function buyNow() {
  localAdd(goods.value, qty.value)
  router.push('/shop/cart')
}

onMounted(load)
</script>

<style scoped>
.crumb {
  display: flex; align-items: center; gap: 8px;
  font-size: 12.5px; color: var(--text-sub); margin-bottom: 16px;
}
.crumb a { color: var(--text-sub); text-decoration: none; transition: color .15s; }
.crumb a:hover { color: var(--primary); }
.crumb svg { opacity: .45; }

.detail-skel { display: flex; gap: 24px; }
.sk-pic { flex: 0 0 380px; aspect-ratio: 1/1; border-radius: 22px; background: var(--border); animation: sk-fade 1.2s ease-in-out infinite; }
.sk-info { flex: 1; display: flex; flex-direction: column; gap: 14px; justify-content: center; }
.sk-bar { display: block; height: 14px; border-radius: 7px; background: var(--border); animation: sk-fade 1.2s ease-in-out infinite; }
@keyframes sk-fade { 0%, 100% { opacity: 1; } 50% { opacity: .4; } }
.error-tip { margin: 12px 0; padding: 8px 12px; border-radius: 8px; background: #FEF2F2; color: #B42318; font-size: 13px; }

.detail-box {
  display: flex; gap: 32px; align-items: stretch;
  background: var(--surface); border-radius: 26px; padding: 26px;
  box-shadow: 0 2px 10px rgba(27,44,80,.05);
  animation: rise .45s cubic-bezier(.2,.7,.3,1) both;
}
@keyframes rise { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: none; } }
.detail-pic {
  position: relative; flex: 0 0 400px; aspect-ratio: 1/1;
  border-radius: 20px; overflow: hidden; background: #F4F7FC;
}
.detail-pic.oos :deep(.goods-visual) { filter: grayscale(.75); opacity: .8; }
.tag { position: absolute; top: 12px; right: 12px; border-radius: 8px; padding: 4px 12px; font-size: 12px; font-weight: 700; z-index: 5; }
.oos-tag { background: rgba(15,22,40,.72); color: #fff; }
.low-tag { background: var(--warning); color: #fff; }

.detail-info { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.name { font-size: 26px; font-weight: 800; color: var(--text); margin: 0 0 8px; letter-spacing: -.02em; text-wrap: balance; }
.desc { font-size: 13.5px; color: var(--text-sub); margin: 0 0 16px; line-height: 1.75; }
.price-box {
  display: flex; align-items: baseline; gap: 12px;
  padding: 16px 18px; border-radius: 16px;
  background: linear-gradient(105deg, rgba(27,108,255,.07), rgba(55,200,168,.06));
  margin-bottom: 16px;
}
.price-box .label { font-size: 12.5px; color: var(--text-sub); font-weight: 600; }
.price-box .value { font-size: 32px; font-weight: 800; color: var(--orange); font-variant-numeric: tabular-nums; letter-spacing: -.02em; }
.price-box .tax { margin-left: auto; font-size: 12px; color: var(--text-sub); }
.meta { display: flex; gap: 10px; font-size: 12.5px; color: var(--text-sub); margin-bottom: 20px; flex-wrap: wrap; }
.meta span { display: inline-flex; align-items: center; gap: 6px; padding: 7px 13px; border-radius: 10px; background: var(--bg); border: 1px solid rgba(27,44,80,.05); font-weight: 600; }
.meta svg { color: var(--teal-3); }
.qty-row { display: flex; align-items: center; gap: 14px; margin-bottom: 22px; }
.qty-label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.stepper { display: inline-flex; align-items: center; border: 1.5px solid var(--border); border-radius: 999px; overflow: hidden; background: var(--surface); }
.step-btn { width: 34px; height: 34px; border: none; background: transparent; font-size: 16px; cursor: pointer; color: var(--text); transition: all .15s; }
.step-btn:hover:not(:disabled) { background: var(--primary-soft); color: var(--primary); }
.step-btn:disabled { opacity: .35; cursor: not-allowed; }
.qty-input { width: 52px; height: 34px; border: none; text-align: center; font-size: 14px; font-weight: 600; color: var(--text); font-family: var(--font); outline: none; background: transparent; -moz-appearance: textfield; }
.qty-input::-webkit-inner-spin-button, .qty-input::-webkit-outer-spin-button { -webkit-appearance: none; }
.stock-hint { font-size: 12px; color: var(--text-sub); }
.actions { display: flex; gap: 12px; margin-top: auto; padding-top: 6px; }
.big { padding: 12px 28px; font-size: 14.5px; }
.big:active { transform: scale(.97); }
.notice {
  margin-top: 18px; padding: 14px 18px; border-radius: 16px;
  background: var(--bg); border: 1px dashed rgba(27,44,80,.12);
  font-size: 12.5px; color: var(--text-sub); line-height: 1.8;
}
.notice-title { display: flex; align-items: center; gap: 7px; margin: 0 0 4px; font-weight: 700; color: var(--text); }
.notice-title svg { color: var(--teal-3); }
.notice p { margin: 0; }
.detail-long { margin-top: 24px; padding: 22px 26px; background: var(--surface); border-radius: 22px; box-shadow: 0 2px 10px rgba(27,44,80,.05); }
.detail-long h3 { margin: 0 0 10px; font-size: 16px; font-weight: 750; }
.long-text { font-size: 13.5px; color: var(--text); line-height: 1.9; white-space: pre-wrap; margin: 0; }

@media (max-width: 768px) {
  .detail-box { flex-direction: column; padding: 16px; gap: 20px; }
  .detail-pic { flex: none; width: 100%; }
  .price-box { flex-wrap: wrap; }
  .price-box .tax { margin-left: 0; width: 100%; }
}
</style>
