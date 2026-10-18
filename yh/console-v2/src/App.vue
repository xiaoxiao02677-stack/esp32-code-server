<template>
  <div v-if="booting" class="boot-bar"><div class="boot-bar-fill"></div></div>
  <div v-else class="app-shell" :class="[roleClass, { 'shell-compact': compact }]">
    <a href="#main-content" class="skip-link">跳到主内容</a>
    <main class="app-canvas" id="main-content">
      <TopBar :role="role" @switch-role="switchRole" />
      <router-view />
      <DockNav :role="role" @toggle-compact="onToggleCompact" />
      <Toasts ref="toastsRef" />
      <div v-if="confirm.show" class="modal-mask" @click.self="confirm.show = false" @keydown.esc.window="confirm.show && (confirm.show = false)">
        <div class="modal confirm">
          <h3>{{ confirm.title }}</h3>
          <p>{{ confirm.message }}</p>
          <div class="modal-actions">
            <button class="btn btn-ghost" @click="confirm.show = false">取消</button>
            <button ref="confirmOkBtn" class="btn btn-primary" :class="{ danger: confirm.danger }" @click="runConfirmOk">
              {{ confirm.okText || '确定' }}
            </button>
          </div>
        </div>
      </div>
      <!-- 强制改密弹窗：遮罩不可点关闭（无 click.self），期间锁定 body 滚动 -->
      <div v-if="forcePwd.show" class="modal-mask force-mask">
        <div class="modal">
          <h3>🔑 请先修改初始密码</h3>
          <p class="force-tip">管理员要求你修改初始密码后才能继续使用，修改成功后弹窗自动关闭。</p>
          <div class="form-row"><label>旧密码</label><input type="password" v-model="forcePwd.oldPassword" placeholder="请输入当前密码" /></div>
          <div class="form-row"><label>新密码</label><input type="password" v-model="forcePwd.newPassword" placeholder="需包含大写字母、小写字母和数字" /></div>
          <div class="form-row"><label>确认新密码</label><input type="password" v-model="forcePwd.confirm" placeholder="再次输入新密码" @keyup.enter="submitForcePwd" /></div>
          <div class="modal-actions">
            <button class="btn btn-primary" :disabled="forcePwdBusy || !forcePwd.oldPassword || !forcePwd.newPassword || !forcePwd.confirm || forcePwd.newPassword !== forcePwd.confirm" @click="submitForcePwd">
              {{ forcePwdBusy ? '提交中…' : '提交' }}
            </button>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, provide, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import TopBar from './components/TopBar.vue'
import DockNav from './components/DockNav.vue'
import Toasts from './components/Toasts.vue'
import { api, getToken } from './lib/api'

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

// 确认弹窗打开时聚焦确认按钮（键盘可达），ESC 关闭
const confirmOkBtn = ref(null)
watch(() => confirm.show, async (v) => {
  if (v) { await nextTick(); confirmOkBtn.value?.focus() }
})

function switchRole(r) {
  router.push(r === 'admin' ? '/admin' : '/customer')
}

function onToggleCompact(val) {
  compact.value = !!val
  localStorage.setItem('cc_compact', compact.value ? '1' : '0')
}

onMounted(() => {
  // 路由就绪即撤掉启动进度条（不再假等 300ms）
  router.isReady().then(() => { booting.value = false })
  // 强制改密：booting 结束后检查 /user/info.mustChangePwd（有 token 才查，静默失败）
  setTimeout(() => { checkForcePwd() }, 400)
})

// ===== 强制改密（mustChangePwd=1 → 全局不可关闭弹窗） =====
const forcePwd = reactive({ show: false, oldPassword: '', newPassword: '', confirm: '' })
const forcePwdBusy = ref(false)

async function checkForcePwd() {
  if (!getToken()) return
  try {
    const res = await api.get('/user/info')
    const d = res.data || {}
    if (Number(d.mustChangePwd) === 1) forcePwd.show = true
  } catch { /* 静默：未登录/接口异常不打扰用户 */ }
}

async function submitForcePwd() {
  if (!forcePwd.oldPassword || !forcePwd.newPassword) { toast('请填写旧密码和新密码', 'error'); return }
  if (forcePwd.newPassword !== forcePwd.confirm) { toast('两次输入的新密码不一致', 'error'); return }
  forcePwdBusy.value = true
  try {
    await api.put('/user/change-password', {
      oldPassword: forcePwd.oldPassword,
      newPassword: forcePwd.newPassword
    })
    toast('密码修改成功')
    forcePwd.show = false
    forcePwd.oldPassword = ''; forcePwd.newPassword = ''; forcePwd.confirm = ''
  } catch (e) {
    toast(e.msg || '修改失败', 'error')
  } finally {
    forcePwdBusy.value = false
  }
}

// 弹窗打开期间锁定 body 滚动，关闭恢复
watch(() => forcePwd.show, (v) => {
  document.body.style.overflow = v ? 'hidden' : ''
})
</script>

<style>
/* A8 booting 进度条 */
.boot-bar { position: fixed; top: 0; left: 0; right: 0; z-index: var(--z-boot); padding: 4px 10px; }
.boot-bar-fill {
  height: 4px; border-radius: 4px;
  background: linear-gradient(90deg, var(--primary), var(--teal-3));
  animation: boot-fill 0.32s ease-out forwards;
}
@keyframes boot-fill { from { width: 8%; } to { width: 100%; } }

.modal-mask { position: fixed; inset: 0; background: rgba(15,22,40,.45); display: grid; place-items: center; z-index: var(--z-modal); }
.modal { background: #fff; border-radius: 20px; padding: 26px; width: min(440px, 92vw); box-shadow: 0 24px 60px rgba(0,0,0,.2); }
.modal.confirm h3 { font-size: 17px; margin-bottom: 10px; }
.modal.confirm p { color: var(--text-sub); font-size: 14px; line-height: 1.6; margin-bottom: 20px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; }
.btn.danger { background: var(--danger); box-shadow: 0 4px 14px rgba(240,83,77,.35); }

/* 强制改密弹窗 */
.force-mask { z-index: var(--z-force); }
.force-tip { color: var(--text-sub); font-size: 13px; line-height: 1.6; margin-bottom: 16px; }
.force-mask .form-row { margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.force-mask .form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.force-mask .form-row input {
  border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px;
  font-size: 14px; outline: none; font-family: var(--font); background: #fff;
}
.force-mask .form-row input:focus { border-color: var(--primary); }
</style>
