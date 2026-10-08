<template>
  <div class="dock-wrap">
    <nav class="dock">
      <router-link
        v-for="item in items" :key="item.to"
        :to="item.to" class="dock-item"
        :class="{ active: isActive(item.to) }"
      >
        <span class="ic">{{ item.icon }}</span>
        <span>{{ item.label }}</span>
      </router-link>
      <button class="dock-more" :title="role === 'admin' ? '切换到顾客端' : '切换到管理端'" @click="toggle">
        {{ role === 'admin' ? '⇄' : '→' }}
      </button>
    </nav>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const props = defineProps({ role: { type: String, default: 'customer' } })
const route = useRoute()
const router = useRouter()

const customerItems = [
  { to: '/customer', icon: '🏠', label: '首页' },
  { to: '/customer/devices', icon: '📡', label: '我的设备' },
  { to: '/customer/voices', icon: '🎙', label: '音色' },
  { to: '/customer/points', icon: '💎', label: '积分' }
]
const adminItems = [
  { to: '/admin', icon: '🏠', label: '概览' },
  { to: '/admin/templates', icon: '🧩', label: '模板' },
  { to: '/admin/knowledge', icon: '📚', label: '知识库' },
  { to: '/admin/users', icon: '👥', label: '用户' }
]
const items = computed(() => (props.role === 'admin' ? adminItems : customerItems))

function isActive(to) {
  return route.path === to
}
function toggle() {
  router.push(props.role === 'admin' ? '/customer' : '/admin')
}
</script>
