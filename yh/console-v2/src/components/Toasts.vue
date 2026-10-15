<template>
  <transition-group name="toast" tag="div" class="toast-stack">
    <div v-for="t in toasts" :key="t.id" class="toast" :class="t.type">
      <span class="ic">{{ t.type === 'success' ? '✓' : t.type === 'error' ? '✕' : 'ⓘ' }}</span>
      <span>{{ t.msg }}</span>
    </div>
  </transition-group>
</template>

<script setup>
import { ref } from 'vue'

const toasts = ref([])
let seq = 0

function toast(msg, type = 'success', ms = 2600) {
  const id = ++seq
  toasts.value.push({ id, msg, type })
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }, ms)
}

defineExpose({ toast })
</script>

<style scoped>
.toast-stack {
  position: fixed; top: 20px; right: 20px; z-index: 200;
  display: flex; flex-direction: column; gap: 10px;
}
.toast {
  display: flex; align-items: center; gap: 9px;
  padding: 12px 20px; border-radius: 14px; font-size: 13.5px; font-weight: 600;
  box-shadow: 0 10px 30px rgba(20, 40, 80, 0.18);
  animation: slideIn .25s ease;
}
.toast .ic { font-size: 14px; }
.toast.success { background: #0FBF6E; color: #fff; }
.toast.error { background: #F0534D; color: #fff; }
.toast.info { background: #1B6CFF; color: #fff; }
.toast-enter-active, .toast-leave-active { transition: all .3s; }
.toast-enter-from { opacity: 0; transform: translateX(40px); }
.toast-leave-to { opacity: 0; transform: translateY(-10px); }
@keyframes slideIn { from { opacity: 0; transform: translateX(40px); } }
</style>
