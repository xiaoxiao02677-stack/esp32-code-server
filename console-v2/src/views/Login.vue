<template>
  <div class="login-wrap">
    <div class="login-left">
      <div class="en">INTELLIGENCE / CONNECTED</div>
      <h1>连接设备<br />也连接更聪明的服务</h1>
      <p>统一管理设备、智能体与服务</p>
      <div class="cube">⚡</div>
    </div>
    <div class="login-card">
      <h2>登录控制台</h2>
      <p class="sub">安全访问您的设备、智能体与服务配置</p>
      <div class="field">
        <label>用户名</label>
        <input v-model="form.username" placeholder="请输入用户名" @keyup.enter="doLogin" />
      </div>
      <div class="field">
        <label>密码</label>
        <div class="pw-row">
          <input :type="showPw ? 'text' : 'password'" v-model="form.password" placeholder="请输入密码" @keyup.enter="doLogin" />
          <button class="eye" @click="showPw = !showPw">{{ showPw ? '🙈' : '👁' }}</button>
        </div>
      </div>
      <div class="field">
        <label>验证码</label>
        <div class="cap-row">
          <input v-model="form.captcha" placeholder="请输入验证码" @keyup.enter="doLogin" />
          <img v-if="captchaUrl" :src="captchaUrl" @click="refreshCaptcha" title="点击刷新" class="cap-img" />
        </div>
      </div>
      <p v-if="errMsg" class="err">{{ errMsg }}</p>
      <div class="login-toasts">
        <div v-for="t in toasts" :key="t.id" class="mini-toast" :class="t.type">{{ t.msg }}</div>
      </div>
      <button class="btn btn-primary login-btn" :disabled="loading" @click="doLogin">
        {{ loading ? '登录中…' : '登录' }}
      </button>
      <p class="tip">新用户注册请联系管理员 · 使用原控制台账号直接登录</p>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { authApi, refreshUserInfo, defaultRouteAfterLogin } from '../lib/api'

const router = useRouter()
const showPw = ref(false)
const loading = ref(false)
const errMsg = ref('')
const captchaUrl = ref('')
const form = reactive({ username: '', password: '', captcha: '' })
let captchaId = ''

function refreshCaptcha() {
  captchaId = (crypto.randomUUID ? crypto.randomUUID() : Date.now() + '-' + Math.random()).replace(/-/g, '')
  captchaUrl.value = authApi.captchaUrl(captchaId)
}

async function doLogin() {
  if (!form.username || !form.password || !form.captcha) {
    errMsg.value = '请填写用户名、密码和验证码'
    return
  }
  loading.value = true
  errMsg.value = ''
  try {
    // 原控制台登录契约（App.vue:2500）：SM2(captcha+password) 加密传输
    const res = await authApi.login(form.username, form.password, form.captcha, captchaId)
    localStorage.setItem('v2-user', form.username)
    // 强制改密：TokenDTO.mustChangePwd===true 时先提示，reload 让 App.vue onMounted 接管全局改密弹窗
    if (res && res.mustChangePwd === true) {
      toast('请先修改初始密码', 'info')
      setTimeout(() => { location.reload() }, 600)
      return
    }
    // 身份补全（旧后端 TokenDTO 缺 superAdmin/roles，用 /user/info 兜底）→ 角色分流跳转
    await refreshUserInfo().catch(() => {})
    const target = defaultRouteAfterLogin()
    // 双保险跳转：router.push + hash 直赋（防 router 时序问题导致"登录完还在login页"）
    router.push(target).catch(() => {})
    setTimeout(() => { if (location.hash.startsWith('#/login')) location.hash = '#' + target }, 300)
  } catch (e) {
    errMsg.value = e.msg || '登录失败'
    refreshCaptcha()
    form.captcha = ''
  } finally {
    loading.value = false
  }
}

// toast：登录页无 App.vue provide（booting 前），用轻量实现
const toasts = reactive([])
let toastId = 0
function toast(msg, type = 'info') {
  const id = ++toastId
  toasts.push({ id, msg, type })
  setTimeout(() => { const i = toasts.findIndex(t => t.id === id); if (i > -1) toasts.splice(i, 1) }, 3000)
}

onMounted(refreshCaptcha)
</script>

<style scoped>
.login-wrap {
  min-height: 78vh; display: grid; grid-template-columns: 1fr 1fr; gap: 40px;
  align-items: center; padding: 20px 40px;
}
.login-left {
  border-radius: 26px; padding: 40px; position: relative; overflow: hidden;
  background: linear-gradient(160deg, var(--teal-1) 0%, var(--teal-2) 55%, var(--teal-3) 100%);
  color: #fff; min-height: 480px; display: flex; flex-direction: column; justify-content: center;
}
.login-left .en { letter-spacing: 3px; font-size: 11px; opacity: .85; font-weight: 700; margin-bottom: 14px; }
.login-left h1 { font-size: 34px; font-weight: 800; line-height: 1.35; text-shadow: 0 2px 10px rgba(0,0,0,.12); }
.login-left p { margin-top: 12px; opacity: .9; font-size: 14px; }
.cube {
  position: absolute; right: 36px; bottom: 40px; width: 84px; height: 84px;
  border-radius: 24px; background: linear-gradient(135deg, #fff, #E6F6FF);
  display: grid; place-items: center; font-size: 38px; transform: rotate(14deg);
  box-shadow: 0 14px 30px rgba(0,60,60,.28); animation: blobFloat 6s ease-in-out infinite;
}
.login-card { background: var(--surface); border-radius: 24px; padding: 40px 44px; box-shadow: var(--shadow-card); max-width: 430px; margin: 0 auto; width: 100%; }
.login-card h2 { font-size: 22px; margin-bottom: 4px; }
.login-card .sub { color: var(--text-sub); font-size: 13px; margin-bottom: 26px; }
.field { margin-bottom: 16px; display: flex; flex-direction: column; gap: 6px; }
.field label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.field input {
  border: 1.5px solid var(--border); border-radius: 14px; padding: 11px 15px;
  font-size: 14px; outline: none; transition: border .15s; font-family: var(--font);
}
.field input:focus { border-color: var(--primary); }
.pw-row, .cap-row { display: flex; gap: 10px; }
.pw-row input { flex: 1; }
.eye { border: none; background: none; cursor: pointer; font-size: 17px; }
.cap-row input { flex: 1; }
.cap-img { height: 44px; border-radius: 10px; cursor: pointer; border: 1px solid var(--border); }
.err { color: var(--danger); font-size: 12.5px; margin-bottom: 10px; }
.login-toasts { position: relative; }
.mini-toast {
  border-radius: 10px; padding: 9px 14px; font-size: 13px; margin-bottom: 8px;
  color: #fff; animation: toastIn .2s ease-out;
}
.mini-toast.info { background: var(--primary); }
.mini-toast.success { background: var(--success); }
.mini-toast.error { background: var(--danger); }
@keyframes toastIn { from { opacity: 0; transform: translateY(-6px); } to { opacity: 1; transform: none; } }
.login-btn { width: 100%; justify-content: center; padding: 12px; font-size: 15px; }
.tip { margin-top: 16px; color: var(--text-sub); font-size: 12px; text-align: center; }
@media (max-width: 800px) { .login-wrap { grid-template-columns: 1fr; } .login-left { min-height: 200px; } }
</style>
