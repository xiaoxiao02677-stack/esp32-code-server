<template>
  <div class="app-shell" :class="roleClass">
    <div class="app-canvas">
      <TopBar :role="role" @switch-role="switchRole" />
      <router-view />
      <DockNav :role="role" />
      <Toasts ref="toastsRef" />
      <div v-if="confirm.show" class="modal-mask" @click.self="confirm.show = false">
        <div class="modal confirm">
          <h3>{{ confirm.title }}</h3>
          <p>{{ confirm.message }}</p>
          <div class="modal-actions">
            <button class="btn btn-ghost" @click="confirm.show = false">取消</button>
            <button class="btn btn-primary" :class="{ danger: confirm.danger }" @click="confirm.onOk && confirm.onOk()">
              {{ confirm.okText || '确定' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, provide, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import TopBar from './components/TopBar.vue'
import DockNav from './components/DockNav.vue'
import Toasts from './components/Toasts.vue'

const route = useRoute()
const router = useRouter()
const role = computed(() => (route.path.startsWith('/admin') ? 'admin' : 'customer'))
const roleClass = computed(() => 'role-' + role.value)

const toastsRef = ref(null)
function toast(msg, type = 'success') {
  toastsRef.value?.toast(msg, type)
}
provide('toast', toast)

// 全局确认弹窗（删除等危险操作）
const confirm = reactive({ show: false, title: '', message: '', okText: '确定', danger: false, onOk: null })
function askConfirm({ title, message, okText, danger, onOk }) {
  Object.assign(confirm, { show: true, title, message, okText: okText || '确定', danger: !!danger, onOk })
}
provide('askConfirm', askConfirm)

function switchRole(r) {
  router.push(r === 'admin' ? '/admin' : '/customer')
}
</script>

<style>
.modal-mask { position: fixed; inset: 0; background: rgba(15,22,40,.45); display: grid; place-items: center; z-index: 150; }
.modal { background: #fff; border-radius: 20px; padding: 26px; width: min(440px, 92vw); box-shadow: 0 24px 60px rgba(0,0,0,.2); }
.modal.confirm h3 { font-size: 17px; margin-bottom: 10px; }
.modal.confirm p { color: var(--text-sub); font-size: 14px; line-height: 1.6; margin-bottom: 20px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; }
.btn.danger { background: var(--danger); box-shadow: 0 4px 14px rgba(240,83,77,.35); }
</style>
