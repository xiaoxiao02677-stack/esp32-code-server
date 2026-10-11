<template>
  <div v-if="booting" class="boot-bar"><div class="boot-bar-fill"></div></div>
  <div v-else class="app-shell" :class="[roleClass, { 'shell-compact': compact }]">
    <div class="app-canvas">
      <TopBar :role="role" @switch-role="switchRole" />
      <router-view />
      <DockNav :role="role" @toggle-compact="onToggleCompact" />
      <Toasts ref="toastsRef" />
      <div v-if="confirm.show" class="modal-mask" @click.self="confirm.show = false">
        <div class="modal confirm">
          <h3>{{ confirm.title }}</h3>
          <p>{{ confirm.message }}</p>
          <div class="modal-actions">
            <button class="btn btn-ghost" @click="confirm.show = false">取消</button>
            <button class="btn btn-primary" :class="{ danger: confirm.danger }" @click="runConfirmOk">
              {{ confirm.okText || '确定' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, provide, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import TopBar from './components/TopBar.vue'
import DockNav from './components/DockNav.vue'
import Toasts from './components/Toasts.vue'

const route = useRoute()
const router = useRouter()
const role = computed(() => (route.path.startsWith('/admin') ? 'admin' : 'customer'))
const roleClass = computed(() => 'role-' + role.value)

// A8 booting 初始化加载态（参照原控制台 App.vue:3-7、954）
const booting = ref(true)

// A9 紧凑模式（localStorage 'cc_compact'，与 DockNav 主题行配合）
const compact = ref(localStorage.getItem('cc_compact') === '1')

const toastsRef = ref(null)
function toast(msg, type = 'success', ms) {
  // ms 可选：长文案（如生效条件说明）传入更长展示时长，默认 2600ms
  toastsRef.value?.toast(msg, type, ms)
}
provide('toast', toast)

// 全局确认弹窗（删除等危险操作）
const confirm = reactive({ show: false, title: '', message: '', okText: '确定', danger: false, onOk: null })
function askConfirm({ title, message, okText, danger, onOk }) {
  Object.assign(confirm, { show: true, title, message, okText: okText || '确定', danger: !!danger, onOk })
}
provide('askConfirm', askConfirm)

// OK 立即关窗再执行回调（异步操作失败由调用方 toast 提示）
function runConfirmOk() {
  const cb = confirm.onOk
  confirm.show = false
  if (cb) cb()
}

function switchRole(r) {
  router.push(r === 'admin' ? '/admin' : '/customer')
}

function onToggleCompact(val) {
  compact.value = !!val
  localStorage.setItem('cc_compact', compact.value ? '1' : '0')
}

onMounted(() => {
  setTimeout(() => { booting.value = false }, 300)
})
</script>

<style>
/* A8 booting 进度条 */
.boot-bar { position: fixed; top: 0; left: 0; right: 0; z-index: 10000; padding: 4px 10px; }
.boot-bar-fill {
  height: 4px; border-radius: 4px;
  background: linear-gradient(90deg, var(--primary), var(--teal-3));
  animation: boot-fill 0.32s ease-out forwards;
}
@keyframes boot-fill { from { width: 8%; } to { width: 100%; } }

.modal-mask { position: fixed; inset: 0; background: rgba(15,22,40,.45); display: grid; place-items: center; z-index: 150; }
.modal { background: #fff; border-radius: 20px; padding: 26px; width: min(440px, 92vw); box-shadow: 0 24px 60px rgba(0,0,0,.2); }
.modal.confirm h3 { font-size: 17px; margin-bottom: 10px; }
.modal.confirm p { color: var(--text-sub); font-size: 14px; line-height: 1.6; margin-bottom: 20px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; }
.btn.danger { background: var(--danger); box-shadow: 0 4px 14px rgba(240,83,77,.35); }
</style>
