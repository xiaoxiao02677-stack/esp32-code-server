<template>
  <transition-group name="toast" tag="div" class="toast-stack">
    <div
      v-for="t in toasts" :key="t.id"
      class="toast" :class="t.type"
      role="status"
      @mouseenter="pause(t.id)" @mouseleave="resume(t.id)"
    >
      <span class="ic"><YhIcon :name="ICONS_BY_TYPE[t.type] || 'info'" :size="14" /></span>
      <span class="msg">{{ t.msg }}</span>
      <button type="button" class="toast-x" aria-label="关闭提示" @click="dismiss(t.id)">
        <YhIcon name="x" :size="12" />
      </button>
    </div>
  </transition-group>
</template>

<script setup>
import { ref } from 'vue'
import YhIcon from './YhIcon.vue'

const ICONS_BY_TYPE = { success: 'check', error: 'x', info: 'info' }

const toasts = ref([])
let seq = 0

// hover 暂停：记录剩余时长；关闭按钮支持手动移除
function timerOf(id) {
  return toasts.value.find(t => t.id === id)
}
function arm(t) {
  clearTimeout(t.timer)
  t.startedAt = Date.now()
  t.timer = setTimeout(() => dismiss(t.id), t.remaining)
}
function toast(msg, type = 'success', ms = 2600) {
  const id = ++seq
  const t = { id, msg, type, remaining: ms, startedAt: 0, timer: null }
  toasts.value.push(t)
  arm(t)
}
function pause(id) {
  const t = timerOf(id)
  if (!t) return
  clearTimeout(t.timer)
  t.remaining -= Date.now() - t.startedAt
}
function resume(id) {
  const t = timerOf(id)
  if (t) arm(t)
}
function dismiss(id) {
  const t = timerOf(id)
  if (t) clearTimeout(t.timer)
  toasts.value = toasts.value.filter(x => x.id !== id)
}

defineExpose({ toast })
</script>

<style scoped>
.toast-stack {
  position: fixed; top: 20px; right: 20px; z-index: var(--z-toast);
  display: flex; flex-direction: column; gap: 10px;
}
.toast {
  display: flex; align-items: center; gap: 9px;
  padding: 12px 14px 12px 20px; border-radius: 14px; font-size: 13.5px; font-weight: 600;
  box-shadow: 0 10px 30px rgba(20, 40, 80, 0.18);
  animation: slideIn .25s ease;
  max-width: min(420px, calc(100vw - 40px));
}
.toast .ic { font-size: 14px; display: inline-flex; }
.toast .msg { flex: 1; }
.toast-x {
  border: none; background: rgba(255,255,255,.25); color: #fff; cursor: pointer;
  width: 20px; height: 20px; border-radius: 6px; display: inline-flex;
  align-items: center; justify-content: center; padding: 0; flex-shrink: 0;
}
.toast-x:hover { background: rgba(255,255,255,.4); }
.toast.success { background: #0FBF6E; color: #fff; }
.toast.error { background: #F0534D; color: #fff; }
.toast.info { background: #1B6CFF; color: #fff; }
.toast-enter-active, .toast-leave-active { transition: all .3s; }
.toast-enter-from { opacity: 0; transform: translateX(40px); }
.toast-leave-to { opacity: 0; transform: translateY(-10px); }
@keyframes slideIn { from { opacity: 0; transform: translateX(40px); } }
</style>
