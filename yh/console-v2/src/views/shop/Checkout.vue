<template>
  <div>
    <!-- 三步进度条 -->
    <div class="steps">
      <div class="step done"><span class="num">✓</span><span>购物车</span></div>
      <div class="conn on"></div>
      <div class="step active"><span class="num">2</span><span>填写信息</span></div>
      <div class="conn"></div>
      <div class="step"><span class="num">3</span><span>支付确认</span></div>
    </div>

    <div v-if="checkedItems.length === 0" class="panel empty-panel">
      <div class="empty-state">
        <ShopIcon name="bag" :size="36"/>
        <strong>没有要结算的商品</strong>
        <p>请先在购物车勾选要购买的商品</p>
        <router-link to="/shop/cart" class="btn btn-primary" style="margin-top:12px">去购物车</router-link>
      </div>
    </div>

    <div v-else class="checkout-layout">
      <!-- 左：收货表单（商城 checkout 字段 1:1：收货人/手机/地址/备注，免登录） -->
      <div class="panel form-panel">
        <div class="panel-head">
          <h3 class="ck-title"><ShopIcon name="pin" :size="16"/>收货信息</h3>
          <span class="guest-tip">下单无需注册登录</span>
        </div>
        <div class="form-grid">
          <div class="field">
            <label>收货人姓名 <i>*</i></label>
            <input v-model.trim="form.userName" placeholder="收件人姓名" maxlength="30" />
          </div>
          <div class="field">
            <label>手机号 <i>*</i></label>
            <input v-model.trim="form.contact" placeholder="用于物流联系" maxlength="20" />
          </div>
          <div class="field full">
            <label>详细地址 <i>*</i></label>
            <input v-model.trim="form.shippingAddress" placeholder="省 / 市 / 区 + 详细街道地址（如：广东省深圳市南山区xx路xx号）" maxlength="200" />
          </div>
          <div class="field full">
            <label>订单备注</label>
            <input v-model.trim="form.remark" placeholder="有什么想告诉客服的吗～（选填）" maxlength="200" />
          </div>
        </div>

        <div class="panel-head" style="margin-top:22px">
          <h3 class="ck-title"><ShopIcon name="bag" :size="16"/>商品清单</h3>
        </div>
        <div class="order-item" v-for="it in checkedItems" :key="it.goodsId">
          <div class="oi-pic">
            <img v-if="isImgCover(it.cover)" :src="coverSrc(it.cover)" alt="" loading="lazy" />
            <span v-else>{{ it.cover || '🛍️' }}</span>
          </div>
          <div class="oi-name">{{ it.name }}</div>
          <div class="oi-qty">x{{ it.qty }}</div>
          <div class="oi-amount">¥{{ fmt(Number(it.price) * Number(it.qty)) }}</div>
        </div>
      </div>

      <!-- 右：提交汇总 -->
      <aside class="panel summary">
        <h3>订单汇总</h3>
        <div class="row"><span>商品（{{ count }} 件）</span><span>¥{{ fmt(total) }}</span></div>
        <div class="row"><span>运费</span><span class="free">免运费</span></div>
        <div class="divider"></div>
        <div class="row total"><span>应付</span><span class="amount">¥{{ fmt(total) }}</span></div>
        <button class="btn btn-primary submit" :disabled="busy" @click="submit">
          {{ busy ? '提交中…' : '提交订单' }}
        </button>
        <router-link to="/shop/cart" class="btn btn-ghost back">← 返回购物车</router-link>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, ref } from 'vue'
import { useRouter } from 'vue-router'
import { guestApi } from '../../lib/api'
import { clearChecked, loadCart } from '../../lib/shopCart'
import { coverSrc, isImgCover } from '../../lib/coverImg'
import ShopIcon from './ShopIcon.vue'

const toast = inject('toast', () => {})
const router = useRouter()

const cart = ref(loadCart())
const form = ref({ userName: '', contact: '', shippingAddress: '', remark: '' })
const busy = ref(false)

const checkedItems = computed(() => cart.value.filter((it) => it.checked === 1 && Number(it.stock) > 0))

const count = computed(() => checkedItems.value.reduce((s, it) => s + Number(it.qty || 0), 0))
const total = computed(() => checkedItems.value.reduce((s, it) => s + Number(it.price) * Number(it.qty), 0))

function fmt(n) {
  const v = Number(n)
  return Number.isFinite(v) ? v.toFixed(2) : '0.00'
}

async function submit() {
  const f = form.value
  if (!f.userName) { toast('请填写收货人姓名', 'error'); return }
  if (!f.contact) { toast('请填写手机号', 'error'); return }
  if (!f.shippingAddress) { toast('请填写详细地址', 'error'); return }
  if (busy.value) return
  busy.value = true
  try {
    const res = await guestApi.checkout({
      userName: f.userName,
      contact: f.contact,
      shippingAddress: f.shippingAddress,
      remark: f.remark,
      items: checkedItems.value.map((it) => ({ goodsId: it.goodsId, qty: Number(it.qty) }))
    })
    const orderId = res.data && res.data.orderId
    const amount = res.data && res.data.amount
    if (!orderId) throw new Error('下单异常')
    clearChecked()          // 清掉已勾选行
    cart.value = loadCart() // 留存未勾选行
    toast('订单已提交')
    router.push({ path: '/shop/orders', query: { created: orderId, amount } })
  } catch (e) {
    toast((e && e.msg) || '下单失败', 'error')
  } finally {
    busy.value = false
  }
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
.step.done { color: var(--success); }
.step.done .num { background: var(--success); border-color: var(--success); color: #fff; }
.conn { flex: 0 1 60px; height: 2px; background: var(--border); border-radius: 1px; }
.conn.on { background: var(--success); }

.checkout-layout { display: grid; grid-template-columns: 1fr 320px; gap: 16px; align-items: start; }
.empty-panel { padding: 30px; }
.empty-state { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 18px 0; }
.empty-state svg { color: var(--text-sub); opacity: .45; margin-bottom: 6px; }
.form-panel { padding: 18px 20px; }
.panel-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.ck-title { display: inline-flex; align-items: center; gap: 8px; margin: 0; font-size: 15px; font-weight: 750; }
.ck-title svg { color: var(--primary); }
.guest-tip { font-size: 11.5px; color: var(--success); font-weight: 600; background: rgba(55,200,168,.12); padding: 3px 10px; border-radius: 999px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field.full { grid-column: 1 / -1; }
.field label { font-size: 12.5px; color: var(--text-sub); font-weight: 600; }
.field label i { color: var(--danger); font-style: normal; }
.field input {
  height: 40px; border: 1.5px solid var(--border); border-radius: 12px;
  padding: 0 14px; font-size: 13.5px; color: var(--text); background: var(--surface);
  outline: none; transition: all .2s; font-family: var(--font);
}
.field input:focus { border-color: var(--primary); box-shadow: 0 0 0 3px var(--primary-soft); }

.order-item { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px dashed var(--border); font-size: 13px; }
.order-item:last-of-type { border-bottom: none; }
.oi-pic {
  width: 44px; height: 44px; border-radius: 10px; background: var(--primary-soft);
  display: flex; align-items: center; justify-content: center; font-size: 24px; flex: 0 0 44px;
  overflow: hidden;
}
.oi-pic img { width: 100%; height: 100%; object-fit: cover; display: block; }
.oi-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text); }
.oi-qty { color: var(--text-sub); }
.oi-amount { color: var(--orange); font-weight: 700; font-variant-numeric: tabular-nums; }

.summary { position: sticky; top: 84px; padding: 18px 20px; }
.summary h3 { margin: 0 0 14px; font-size: 15px; }
.row { display: flex; justify-content: space-between; font-size: 13px; color: var(--text-sub); padding: 6px 0; }
.free { color: var(--success); }
.divider { height: 1px; background: var(--border); margin: 10px 0; }
.row.total { font-size: 14px; color: var(--text); font-weight: 700; }
.amount { color: var(--orange); font-size: 22px; font-weight: 800; font-variant-numeric: tabular-nums; }
.submit { width: 100%; margin-top: 14px; justify-content: center; }
.back { width: 100%; margin-top: 10px; justify-content: center; }

@media (max-width: 900px) {
  .checkout-layout { grid-template-columns: 1fr; }
  .form-grid { grid-template-columns: 1fr; }
}
</style>
