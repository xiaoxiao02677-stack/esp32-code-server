<template>
  <div class="shop-portal">
    <!-- 品牌顶栏：SVG 字标 + 图标导航 -->
    <header class="sp-header">
      <div class="sp-inner">
        <router-link to="/shop" class="sp-brand" aria-label="屿禾商店首页">
          <span class="sp-mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" width="26" height="26" fill="none">
              <rect width="32" height="32" rx="9" fill="#1B6CFF"/>
              <path d="M10 9.5 16 17.5 22 9.5" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M16 17.5V23" stroke="#fff" stroke-width="3" stroke-linecap="round"/>
            </svg>
          </span>
          <span class="sp-name">屿禾商店</span>
        </router-link>
        <nav class="sp-nav" aria-label="商店导航">
          <router-link to="/shop" class="sp-link"><ShopIcon name="spark" :size="15"/>首页</router-link>
          <router-link to="/shop/cart" class="sp-link">
            <ShopIcon name="bag" :size="15"/>购物车<template v-if="count > 0">（{{ count }}）</template>
          </router-link>
          <router-link to="/shop/orders" class="sp-link"><ShopIcon name="receipt" :size="15"/>订单查询</router-link>
        </nav>
        <div class="sp-actions">
          <a v-if="hasConsole" href="#/customer" class="sp-console"><ShopIcon name="user" :size="15"/>控制台</a>
          <a v-else href="#/login" class="sp-console"><ShopIcon name="user" :size="15"/>登录</a>
        </div>
      </div>
    </header>

    <main class="sp-main">
      <router-view />
    </main>

    <footer class="sp-footer">
      <div class="sp-inner">
        <span class="sp-legal">屿禾商店 · 官方正品 · 密封寄出</span>
        <span class="sp-dot" aria-hidden="true">·</span>
        <span>下单无需注册，填写收货信息即可</span>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getToken } from '../../lib/api'
import { cartCount } from '../../lib/shopCart'
import ShopIcon from './ShopIcon.vue'

const route = useRoute()
const hasConsole = computed(() => !!getToken())
const count = ref(cartCount())
watch(() => route.fullPath, () => { count.value = cartCount() })
</script>

<style scoped>
.shop-portal {
  /* A10 滚动体系：body overflow hidden，容器自己滚（与 .app-shell 同构） */
  height: 100vh;
  height: 100dvh;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-gutter: stable;
  background:
    radial-gradient(1100px 480px at 82% -12%, rgba(27,108,255,.065), transparent 62%),
    radial-gradient(880px 420px at -8% 108%, rgba(55,200,168,.07), transparent 58%),
    #E9EDF3;
  display: flex;
  flex-direction: column;
}
/* 全页微噪点（打破数码平感） */
.shop-portal::before {
  content: "";
  position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E");
}
.sp-header {
  position: sticky; top: 0; z-index: 40;
  backdrop-filter: blur(16px) saturate(1.3);
  -webkit-backdrop-filter: blur(16px) saturate(1.3);
  background: rgba(255,255,255,.72);
  border-bottom: 1px solid rgba(27,44,80,.07);
}
/* 顶栏顶部 1px 高光（玻璃边缘折射感） */
.sp-header::after {
  content: ""; position: absolute; left: 0; right: 0; top: 0; height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,.9), transparent);
}
.sp-inner {
  max-width: 1180px; margin: 0 auto; padding: 0 22px;
  height: 62px; display: flex; align-items: center; gap: 26px;
}
.sp-brand { display: flex; align-items: center; gap: 10px; text-decoration: none; }
.sp-mark { display: flex; filter: drop-shadow(0 3px 8px rgba(27,108,255,.35)); }
.sp-name {
  font-size: 16.5px; font-weight: 800; color: var(--text);
  letter-spacing: -.02em;
}
.sp-nav { display: flex; gap: 4px; flex: 1; }
.sp-link {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 14px; border-radius: 999px; text-decoration: none;
  color: var(--text-sub); font-size: 13.5px; font-weight: 600;
  transition: color .2s ease, background .2s ease, transform .15s ease;
}
.sp-link:hover { color: var(--primary); background: var(--primary-soft); }
.sp-link:active { transform: scale(.97); }
.sp-link.router-link-exact-active { color: var(--primary); background: var(--primary-soft); }
.sp-link:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.sp-actions { display: flex; align-items: center; gap: 10px; }
.sp-console {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 16px; border-radius: 999px; text-decoration: none;
  border: 1.5px solid var(--border); color: var(--text-sub); font-size: 13px; font-weight: 600;
  transition: all .2s ease; background: var(--surface);
}
.sp-console:hover { border-color: var(--primary); color: var(--primary); transform: translateY(-1px); }
.sp-console:active { transform: translateY(0) scale(.98); }
.sp-console:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.sp-main {
  flex: 1; width: 100%; max-width: 1180px; margin: 0 auto;
  padding: 26px 22px 64px; position: relative; z-index: 1;
}
.sp-footer {
  border-top: 1px solid rgba(27,44,80,.07); background: rgba(255,255,255,.55);
  padding: 18px 0; font-size: 12.5px; color: var(--text-sub);
}
.sp-footer .sp-inner { height: auto; justify-content: center; gap: 10px; flex-wrap: wrap; }
.sp-legal { font-weight: 600; }
.sp-dot { opacity: .45; }

@media (max-width: 768px) {
  .sp-inner { padding: 0 14px; gap: 10px; }
  .sp-nav { gap: 0; }
  .sp-link { padding: 7px 8px; font-size: 12.5px; gap: 4px; }
  .sp-main { padding: 18px 14px 52px; }
  .sp-console { padding: 7px 12px; }
}
</style>
