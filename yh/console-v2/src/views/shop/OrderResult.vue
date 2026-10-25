<template>
  <div>
    <!-- 刚下单提示 -->
    <div v-if="justCreated" class="pay-banner">
      <div class="pb-info">
        <strong>订单已提交</strong>
        <span>订单号 {{ justCreated.orderId }} · 应付 ¥{{ justCreated.amount }}</span>
      </div>
      <div class="pay-btns" v-if="hasChannel">
        <button v-if="channels.xddpay" class="btn btn-primary" :disabled="paying" @click="pay(justCreated.orderId, 'xddpay-alipay')">
          {{ paying === 'xddpay-alipay' ? '创建中…' : '支付宝支付' }}
        </button>
        <button v-if="channels.xddpay" class="btn btn-wechat" :disabled="paying" @click="pay(justCreated.orderId, 'xddpay-wechat')">
          {{ paying === 'xddpay-wechat' ? '创建中…' : '微信支付' }}
        </button>
        <button v-if="!channels.xddpay && channels.alipayDirect" class="btn btn-primary" :disabled="paying" @click="pay(justCreated.orderId, 'alipay')">
          {{ paying ? '创建支付中…' : '去支付' }}
        </button>
      </div>
      <span v-else class="pb-off">在线支付暂未开通，订单已保留</span>
    </div>

    <!-- 订单查询（游客凭单号查单） -->
    <div class="panel lookup-panel">
      <div class="panel-head">
        <h3 class="lk-title"><ShopIcon name="search" :size="17"/>订单查询</h3>
        <span class="guest-tip">输入下单时返回的订单号</span>
      </div>
      <div class="lookup-row">
        <input v-model.trim="orderId" placeholder="如 ODxxxxxxxxxxxxxxxxxx" maxlength="32" @keyup.enter="lookup" aria-label="订单号" />
        <button class="btn btn-primary" :disabled="looking || !orderId" @click="lookup">
          {{ looking ? '查询中…' : '查询' }}
        </button>
      </div>

      <!-- 查询结果 -->
      <div v-if="order" class="order-detail">
        <div class="od-head">
          <span class="od-id">{{ order.id }}</span>
          <span class="badge" :class="badgeClass(order.shipping_status)">
            <span class="dot"></span>{{ statusText(order.shipping_status) }}
          </span>
        </div>
        <div class="od-row"><span>商品</span><strong>{{ order.product }}</strong></div>
        <div class="od-row"><span>金额</span><strong class="od-amount">¥{{ fmt(order.amount) }}</strong></div>
        <div class="od-row"><span>收货人</span><strong>{{ order.user_name }}</strong></div>
        <div class="od-row"><span>联系电话</span><strong>{{ order.contact }}</strong></div>
        <div class="od-row"><span>收货地址</span><strong>{{ order.address || '—' }}</strong></div>
        <div class="od-row"><span>下单时间</span><strong>{{ fmtDate(order.create_time) }}</strong></div>
        <div class="od-row">
          <span>支付状态</span>
          <strong :class="payStateClass">{{ payStateText }}</strong>
        </div>
        <div class="od-actions" v-if="canPay">
          <button v-if="channels.xddpay" class="btn btn-primary" :disabled="!!paying" @click="pay(order.id, 'xddpay-alipay')">
            {{ paying === 'xddpay-alipay' ? '创建中…' : '支付宝支付' }}
          </button>
          <button v-if="channels.xddpay" class="btn btn-wechat" :disabled="!!paying" @click="pay(order.id, 'xddpay-wechat')">
            {{ paying === 'xddpay-wechat' ? '创建中…' : '微信支付' }}
          </button>
          <button v-if="!channels.xddpay && channels.alipayDirect" class="btn btn-primary" :disabled="!!paying" @click="pay(order.id, 'alipay')">
            {{ paying ? '创建支付中…' : '去支付' }}
          </button>
        </div>
      </div>

      <div v-else-if="lookupErr" class="error-tip">{{ lookupErr }}</div>

      <!-- 历史订单（本机localStorage 记忆最近 10 单） -->
      <div v-if="history.length > 0" class="history">
        <div class="panel-head">
          <h3 class="lk-title"><ShopIcon name="clock" :size="16"/>最近订单（本机）</h3>
        </div>
        <div class="h-row" v-for="h in history" :key="h.id" @click="orderId = h.id; lookup()">
          <span class="h-id">{{ h.id }}</span>
          <span class="h-amount">¥{{ fmt(h.amount) }}</span>
          <span class="h-date">{{ fmtDate(h.create_time) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { guestApi } from '../../lib/api'
import ShopIcon from './ShopIcon.vue'

const toast = inject('toast', () => {})
const route = useRoute()

const orderId = ref('')
const order = ref(null)
const looking = ref(false)
const lookupErr = ref('')
const paying = ref(false)
const justCreated = ref(null)
const history = ref([])
// 支付渠道可用性：{ xddpay: bool, alipayDirect: bool }（未配置渠道不渲染按钮）
const channels = ref({ xddpay: false, alipayDirect: false })

const HISTORY_KEY = 'guest_orders_v1'

const hasChannel = computed(() => channels.value.xddpay || channels.value.alipayDirect)

async function loadChannels() {
  try {
    const res = await guestApi.payChannels()
    const d = res.data || {}
    const x = d.xddpay || {}
    channels.value = {
      xddpay: !!(x.alipay || x.wechat),
      alipayDirect: !!d.alipayDirect
    }
  } catch { channels.value = { xddpay: false, alipayDirect: false } }
}

const canPay = computed(() => {
  if (!order.value) return false
  return String(order.value.shipping_status) === '0' && Number(order.value.payStatus) !== 1
})

const payStateText = computed(() => {
  if (!order.value) return '—'
  const ps = Number(order.value.payStatus)
  if (ps === 1) return '已付款'
  if (ps === 2) return '已关闭'
  if (ps === 0) return '待付款'
  return String(order.value.shipping_status) === '0' ? '待付款' : '已付款'
})

const payStateClass = computed(() => {
  const ps = Number(order.value && order.value.payStatus)
  return ps === 1 ? 'pay-ok' : 'pay-wait'
})

function fmt(n) {
  const v = Number(n)
  return Number.isFinite(v) ? v.toFixed(2) : '—'
}
function fmtDate(d) {
  if (!d) return '—'
  return String(d).replace('T', ' ').slice(0, 16)
}
function statusText(s) {
  const v = String(s)
  if (v === '0') return '待发货'
  if (v === '1') return '已发货'
  if (v === '2') return '已完成'
  if (v === '3') return '已取消'
  return s == null ? '—' : v
}
function badgeClass(s) {
  const v = String(s)
  if (v === '0') return 'badge-orange'
  if (v === '1') return 'badge-green'
  if (v === '2') return 'badge-blue'
  return 'badge-gray'
}

function loadHistory() {
  try {
    const arr = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]')
    history.value = Array.isArray(arr) ? arr.slice(0, 10) : []
  } catch { history.value = [] }
}

function pushHistory(o) {
  try {
    const arr = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]')
    const next = [{ id: o.id, amount: o.amount, create_time: o.create_time }]
      .concat(arr.filter((x) => x.id !== o.id)).slice(0, 10)
    localStorage.setItem(HISTORY_KEY, JSON.stringify(next))
    history.value = next
  } catch { /* 忽略隐私模式存储失败 */ }
}

async function lookup() {
  if (!orderId.value || looking.value) return
  looking.value = true
  lookupErr.value = ''
  order.value = null
  try {
    const res = await guestApi.order(orderId.value)
    if (res.data) {
      order.value = res.data
      pushHistory(res.data)
    } else {
      lookupErr.value = '订单不存在，请核对订单号'
    }
  } catch (e) {
    lookupErr.value = (e && e.msg) || '查询失败'
  } finally {
    looking.value = false
  }
}

/**
 * 发起支付。method:
 *   'xddpay-alipay' / 'xddpay-wechat' — XDDPay 小多支付（动态表单 POST 网关，1:1 商城中转页）
 *   'alipay' — 支付宝官方直连（payForm 注入提交）
 */
async function pay(id, method = 'alipay') {
  if (paying.value) return
  paying.value = method
  try {
    if (method === 'xddpay-alipay' || method === 'xddpay-wechat') {
      const res = await guestApi.payCreateXddpay(id, method === 'xddpay-wechat' ? 'wechat' : 'alipay')
      const d = res.data || {}
      if (d.errorCode === 'PAY_NOT_CONFIGURED') {
        toast('在线支付暂未开通，订单已保留，客服会联系你付款', 'error')
        return
      }
      if (d.errorCode) {
        toast(d.errorMsg || '支付创建失败', 'error')
        return
      }
      // 动态建表单 POST 到网关（对应商城中转页 submitPayForm）
      if (d.gatewayUrl && d.params) {
        const form = document.createElement('form')
        form.action = d.gatewayUrl
        form.method = 'POST'
        form.style.display = 'none'
        for (const [k, v] of Object.entries(d.params)) {
          const input = document.createElement('input')
          input.type = 'hidden'
          input.name = k
          input.value = String(v)
          form.appendChild(input)
        }
        document.body.appendChild(form)
        form.submit()
        return
      }
      toast('支付链接异常，请稍后重试', 'error')
      return
    }

    // 支付宝官方直连
    const res = await guestApi.payCreate(id)
    const d = res.data || {}
    if (d.errorCode === 'PAY_NOT_CONFIGURED') {
      toast('在线支付暂未开通，订单已保留，客服会联系你付款', 'error')
      return
    }
    if (d.errorCode) {
      toast(d.errorMsg || '支付创建失败', 'error')
      return
    }
    if (d.payForm) {
      const box = document.createElement('div')
      box.innerHTML = d.payForm
      const form = box.querySelector('form')
      if (form) {
        document.body.appendChild(form)
        form.submit()
        return
      }
    }
    if (d.payUrl) {
      window.location.href = d.payUrl
      return
    }
    toast('支付链接异常，请稍后重试', 'error')
  } catch (e) {
    toast((e && e.msg) || '支付发起失败', 'error')
  } finally {
    paying.value = false
  }
}

onMounted(() => {
  loadHistory()
  loadChannels()
  const q = route.query
  if (q && q.created) {
    justCreated.value = { orderId: String(q.created), amount: q.amount || '' }
    orderId.value = String(q.created)
    lookup()
  }
})
</script>

<style scoped>
.pay-banner {
  display: flex; align-items: center; justify-content: space-between; gap: 14px;
  background: var(--primary-soft); border: 1px solid var(--primary);
  border-radius: 14px; padding: 14px 18px; margin-bottom: 14px;
}
.pb-info { display: flex; flex-direction: column; gap: 3px; font-size: 13px; color: var(--text); }
.pb-info strong { font-size: 14px; }
.pb-info span { color: var(--text-sub); font-size: 12px; }
.pay-btns { display: flex; gap: 10px; flex-wrap: wrap; }
.pay-btns .btn { min-width: 110px; }
.btn-wechat {
  background: #07C160; color: #fff; border: none; cursor: pointer;
  font-size: 13px; font-weight: 700; border-radius: 12px; padding: 9px 18px;
  transition: transform .15s, box-shadow .15s;
}
.btn-wechat:hover { transform: translateY(-1px); box-shadow: 0 6px 16px rgba(7, 193, 96, .35); }
.btn-wechat:active { transform: scale(.97); }
.btn-wechat:disabled { opacity: .55; cursor: default; transform: none; box-shadow: none; }
.pb-off { font-size: 12.5px; color: var(--warning); font-weight: 600; }

.lookup-panel { padding: 18px 20px; }
.panel-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.lk-title { display: inline-flex; align-items: center; gap: 8px; margin: 0; font-size: 15px; font-weight: 750; }
.lk-title svg { color: var(--primary); }
.guest-tip { font-size: 11.5px; color: var(--text-sub); }
.lookup-row { display: flex; gap: 10px; margin-bottom: 16px; }
.lookup-row input {
  flex: 1; height: 42px; border: 1.5px solid var(--border); border-radius: 12px;
  padding: 0 14px; font-size: 13.5px; color: var(--text); background: var(--surface);
  outline: none; font-family: monospace; transition: all .2s;
}
.lookup-row input:focus { border-color: var(--primary); box-shadow: 0 0 0 3px var(--primary-soft); }

.order-detail { border-top: 1px solid var(--border); padding-top: 14px; animation: od-in .4s cubic-bezier(.2,.7,.3,1) both; }
@keyframes od-in { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
.od-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.od-id { font-size: 12.5px; color: var(--text-sub); font-family: monospace; }
.od-row { display: flex; justify-content: space-between; gap: 18px; padding: 7px 0; font-size: 13px; border-bottom: 1px dashed var(--border); }
.od-row:last-of-type { border-bottom: none; }
.od-row span { color: var(--text-sub); flex: 0 0 auto; }
.od-row strong { color: var(--text); text-align: right; word-break: break-all; font-weight: 600; }
.od-amount { color: var(--orange); font-size: 16px; font-weight: 800; }
.pay-ok { color: var(--success); }
.pay-wait { color: var(--warning); }
.od-actions { display: flex; justify-content: flex-end; gap: 10px; padding-top: 12px; flex-wrap: wrap; }

.error-tip { margin: 12px 0; padding: 8px 12px; border-radius: 8px; background: #FEF2F2; color: #B42318; font-size: 13px; }

.history { border-top: 1px solid var(--border); margin-top: 16px; padding-top: 12px; }
.h-row {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 9px 4px; border-bottom: 1px dashed var(--border); cursor: pointer;
  font-size: 12.5px; transition: background .15s;
}
.h-row:hover { background: var(--primary-soft); }
.h-row:last-of-type { border-bottom: none; }
.h-id { font-family: monospace; color: var(--text); }
.h-amount { color: var(--orange); font-weight: 700; }
.h-date { color: var(--text-sub); font-size: 11.5px; }
</style>
