<template>
  <div>
    <!-- 三步进度条（商城 yy-checkout-steps 同款语义） -->
    <div class="steps">
      <div class="step active"><span class="num">1</span><span>购物车</span></div>
      <div class="conn"></div>
      <div class="step"><span class="num">2</span><span>填写信息</span></div>
      <div class="conn"></div>
      <div class="step"><span class="num">3</span><span>支付确认</span></div>
    </div>

    <div v-if="items.length === 0" class="panel empty-panel">
      <div class="empty-state">
        <ShopIcon name="bag" :size="36"/>
        <strong>购物车还是空的</strong>
        <p>去商店逛逛，把心仪的好物加进来吧</p>
        <router-link to="/shop" class="btn btn-primary" style="margin-top:12px">去逛逛</router-link>
      </div>
    </div>

    <div v-else class="cart-layout">
      <!-- 左：商品列表 -->
      <div class="panel items-panel">
        <div class="cart-item" v-for="it in items" :key="it.goodsId">
          <label class="ck">
            <input type="checkbox" :checked="it.checked === 1" @change="toggle(it)" />
          </label>
          <div class="it-pic">
            <img v-if="isImgCover(it.cover)" :src="coverSrc(it.cover)" alt="" loading="lazy" />
            <span v-else>{{ it.cover || '🛍️' }}</span>
          </div>
          <div class="it-info">
            <div class="it-name" @click="goGoods(it)" :title="it.name">{{ it.name }}</div>
            <div class="it-cat">{{ it.category || '通用' }} · 库存 {{ it.stock }}</div>
          </div>
          <div class="it-price">¥{{ fmt(it.price) }}</div>
          <div class="stepper">
            <button class="step-btn" @click="change(it, -1)">−</button>
            <span class="qty">{{ it.qty }}</span>
            <button class="step-btn" @click="change(it, 1)">＋</button>
          </div>
          <div class="it-subtotal">¥{{ fmt(Number(it.price) * Number(it.qty)) }}</div>
          <button class="it-remove" title="移除" @click="remove(it)">✕</button>
        </div>
        <div class="items-foot">
          <router-link to="/shop" class="btn btn-ghost">← 继续逛逛</router-link>
        </div>
      </div>

      <!-- 右：订单汇总 -->
      <aside class="panel summary">
        <h3>订单汇总</h3>
        <div class="row"><span>商品小计（{{ totalCount }} 件）</span><span>¥{{ fmt(subtotal) }}</span></div>
        <div class="row"><span>运费</span><span class="free">免运费</span></div>
        <div class="divider"></div>
        <div class="row total"><span>应付</span><span class="amount">¥{{ fmt(subtotal) }}</span></div>
        <button class="btn btn-primary settle" :disabled="checkedCount === 0" @click="goCheckout">
          去结算<template v-if="checkedCount > 0">（{{ checkedCount }} 件）</template>
        </button>
        <p class="hint">共 {{ totalCount }} 件商品，已选 {{ checkedCount }} 件</p>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { changeQty, loadCart, removeItem, toggleChecked } from '../../lib/shopCart'
import { coverSrc, isImgCover } from '../../lib/coverImg'
import ShopIcon from './ShopIcon.vue'

const router = useRouter()
const items = ref(loadCart())

const checkedItems = computed(() => items.value.filter((it) => it.checked === 1 && Number(it.stock) > 0))
const totalCount = computed(() => items.value.reduce((s, it) => s + Number(it.qty || 0), 0))
const checkedCount = computed(() => checkedItems.value.reduce((s, it) => s + Number(it.qty || 0), 0))
const subtotal = computed(() => checkedItems.value.reduce((s, it) => s + Number(it.price) * Number(it.qty), 0))

function fmt(n) {
  const v = Number(n)
  return Number.isFinite(v) ? v.toFixed(2) : '0.00'
}

function toggle(it) {
  items.value = toggleChecked(it.goodsId, it.checked === 1 ? 0 : 1)
}

function change(it, delta) {
  items.value = changeQty(it.goodsId, delta)
}

function remove(it) {
  items.value = removeItem(it.goodsId)
}

function goGoods(it) {
  router.push(`/shop/goods/${it.goodsId}`)
}

function goCheckout() {
  if (checkedCount.value === 0) return
  router.push('/shop/checkout')
}
</script>

<style scoped>
.steps { display: flex; align-items: center; gap: 10px; margin: 6px 0 18px; }
.step { display: inline-flex; align-items: center; gap: 7px; font-size: 13px; color: var(--text-sub); font-weight: 600; }
.step .num {
  width: 24px; height: 24px; border-radius: 999px; display: inline-flex;
  align-items: center; justify-content: center; font-size: 12px;
  background: var(--surface); border: 1.5px solid var(--border); color: var(--text-sub);
}
.step.active { color: var(--primary); }
.step.active .num { background: var(--primary); border-color: var(--primary); color: #fff; }
.conn { flex: 0 1 60px; height: 2px; background: var(--border); border-radius: 1px; }

.cart-layout { display: grid; grid-template-columns: 1fr 320px; gap: 16px; align-items: start; }
.empty-panel { padding: 30px; }
.empty-state { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 18px 0; }
.empty-state svg { color: var(--text-sub); opacity: .45; margin-bottom: 6px; }
.items-panel { padding: 6px 0; }
.cart-item { display: flex; align-items: center; gap: 12px; padding: 12px 18px; border-bottom: 1px solid var(--border); }
.cart-item:last-of-type { border-bottom: none; }
.ck input { width: 16px; height: 16px; accent-color: var(--primary); cursor: pointer; }
.it-pic {
  flex: 0 0 56px; width: 56px; height: 56px; border-radius: 12px;
  background: var(--primary-soft); display: flex; align-items: center; justify-content: center;
  font-size: 30px; overflow: hidden;
}
.it-pic img { width: 100%; height: 100%; object-fit: cover; display: block; }
.it-info { flex: 1; min-width: 0; }
.it-name { font-size: 13.5px; font-weight: 600; color: var(--text); cursor: pointer; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.it-name:hover { color: var(--primary); }
.it-cat { font-size: 11.5px; color: var(--text-sub); margin-top: 3px; }
.it-price { flex: 0 0 80px; text-align: right; font-size: 13px; color: var(--text-sub); font-variant-numeric: tabular-nums; }
.stepper { display: inline-flex; align-items: center; border: 1.5px solid var(--border); border-radius: 999px; overflow: hidden; flex: 0 0 auto; }
.step-btn { width: 28px; height: 28px; border: none; background: transparent; font-size: 14px; cursor: pointer; color: var(--text); }
.step-btn:hover { background: var(--primary-soft); color: var(--primary); }
.qty { min-width: 36px; text-align: center; font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums; }
.it-subtotal { flex: 0 0 90px; text-align: right; font-size: 14px; font-weight: 700; color: var(--orange); font-variant-numeric: tabular-nums; }
.it-remove {
  flex: 0 0 28px; width: 28px; height: 28px; border-radius: 999px; border: none;
  background: transparent; color: var(--text-sub); cursor: pointer; font-size: 13px;
}
.it-remove:hover { background: #FEF2F2; color: var(--danger); }
.items-foot { padding: 12px 18px; }

.summary { position: sticky; top: 84px; padding: 18px 20px; }
.summary h3 { margin: 0 0 14px; font-size: 15px; }
.row { display: flex; justify-content: space-between; font-size: 13px; color: var(--text-sub); padding: 6px 0; }
.free { color: var(--success); }
.divider { height: 1px; background: var(--border); margin: 10px 0; }
.row.total { font-size: 14px; color: var(--text); font-weight: 700; }
.amount { color: var(--orange); font-size: 22px; font-weight: 800; font-variant-numeric: tabular-nums; }
.settle { width: 100%; margin-top: 14px; justify-content: center; }
.hint { font-size: 11.5px; color: var(--text-sub); text-align: center; margin: 10px 0 0; }

@media (max-width: 900px) {
  .cart-layout { grid-template-columns: 1fr; }
  .it-price { display: none; }
}
</style>
