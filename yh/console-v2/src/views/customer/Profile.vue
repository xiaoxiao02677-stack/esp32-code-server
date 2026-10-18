<template>
  <div>
    <div class="page-head">
      <div>
        <h1>个人 <span style="color:var(--primary)">中心</span></h1>
        <p class="sub">账号资料 · 密码安全 · 用量概览</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" :disabled="loading" @click="loadAll">{{ loading ? '加载中…' : '↻ 刷新' }}</button>
      </div>
    </div>

    <!-- 页头：用户名 / 角色 / 最后登录 -->
    <div class="hero-row">
      <div class="hero-blob" style="min-height:170px">
        <div>
          <div class="en">PROFILE / ACCOUNT</div>
          <h2>{{ user.username || '未登录' }}</h2>
          <p>
            <span v-for="(r, i) in roleBadges" :key="r.code" class="role-badge" :class="r.cls">{{ r.label }}</span>
            <span v-if="!roleBadges.length" class="role-badge role-plain">普通用户</span>
          </p>
          <p class="last-login">最后登录：{{ fmtTime(user.lastLoginDate) }}</p>
        </div>
        <div class="blob-3d">👤</div>
      </div>
      <div class="stats-grid">
        <StatCard icon="key" label="密码状态" :value="user.mustChangePwd === 1 ? '待修改' : '正常'" :note="user.mustChangePwd === 1 ? '管理员要求修改' : '定期更换更安全'" />
        <StatCard icon="grid" label="自定义模型" :value="models.length" note="本人创建" />
        <StatCard icon="mic" label="自定义音色" :value="voicesCount" note="本人创建" />
        <StatCard icon="shield" label="会话安全" value="Bearer" note="令牌自动过期" />
      </div>
    </div>

    <div class="profile-grid">
      <!-- 卡片1：修改密码 -->
      <div class="panel">
        <div class="panel-head"><h3>🔑 修改密码</h3></div>
        <div class="panel-body">
          <div class="form-row"><label>旧密码</label><input type="password" v-model="pwd.oldPassword" placeholder="请输入当前密码" /></div>
          <div class="form-row"><label>新密码</label><input type="password" v-model="pwd.newPassword" placeholder="请输入新密码" @input="checkStrength" /></div>
          <div v-if="pwd.newPassword" class="strength">
            <span class="strength-bar"><span :style="{ width: strengthPercent + '%' }" :class="strengthCls"></span></span>
            <span class="strength-tip">
              <span :class="{ ok: strength.upper }">大写</span>
              <span :class="{ ok: strength.lower }">小写</span>
              <span :class="{ ok: strength.digit }">数字</span>
            </span>
          </div>
          <div class="form-row"><label>确认新密码</label><input type="password" v-model="pwd.confirm" placeholder="再次输入新密码" @keyup.enter="changePwd" /></div>
          <div class="modal-actions" style="margin-top:4px">
            <button class="btn btn-primary" :disabled="pwdBusy || !pwd.oldPassword || !pwd.newPassword || pwd.newPassword !== pwd.confirm" @click="changePwd">
              {{ pwdBusy ? '提交中…' : '保存新密码' }}
            </button>
          </div>
        </div>
      </div>

      <!-- 卡片2：我的用量 -->
      <div class="panel">
        <div class="panel-head"><h3>📊 我的用量</h3><span class="hint">自定义模型调用配额</span></div>
        <div class="panel-body">
          <div v-if="quotaLoading" class="quota-empty">加载中…</div>
          <div v-else-if="models.length === 0" class="quota-empty">
            暂无自定义模型
            <button class="link-btn" @click="$router.push('/customer/my-models')">去添加</button>
          </div>
          <div v-else class="quota-list">
            <div v-for="m in models" :key="m.id" class="quota-item">
              <div class="quota-head">
                <span class="quota-name">{{ m.modelName }}</span>
                <span class="quota-num">{{ m.usedCount ?? 0 }} / {{ m.quotaLimit == null ? '不限' : m.quotaLimit }}</span>
              </div>
              <div class="quota-bar">
                <span :style="{ width: quotaPercent(m) + '%' }" :class="quotaPercent(m) >= 90 ? 'quota-fill warn' : 'quota-fill'"></span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 卡片3：会话安全提示（静态） -->
      <div class="panel">
        <div class="panel-head"><h3>🛡 会话安全</h3></div>
        <div class="panel-body">
          <ul class="tips">
            <li>登录令牌采用 Bearer Token，默认过期时间 7 天，过期后需重新登录。</li>
            <li>初始密码或管理员重置的密码会要求首次登录时强制修改。</li>
            <li>请勿在公共设备勾选「记住登录」，离开时请主动退出登录。</li>
            <li>自定义模型的 API Key 全程 AES-256-GCM 加密存储，界面仅展示掩码。</li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import { api } from '../../lib/api'

const toast = inject('toast')

const user = ref({ username: '', roles: [], superAdmin: 0, mustChangePwd: 0, lastLoginDate: '' })
const models = ref([])
const voicesCount = ref(0)
const loading = ref(false)
const quotaLoading = ref(false)
const pwdBusy = ref(false)
const pwd = ref({ oldPassword: '', newPassword: '', confirm: '' })
const strength = ref({ upper: false, lower: false, digit: false })
let warned = false

const ROLE_LABELS = [
  { code: 'super_admin', label: '超级管理员', cls: 'role-super' },
  { code: 'admin', label: '管理员', cls: 'role-admin' },
  { code: 'user', label: '普通用户', cls: 'role-plain' },
  { code: 'readonly', label: '只读访客', cls: 'role-ro' }
]

const roleBadges = computed(() =>
  (user.value.roles || []).map(code => {
    const hit = ROLE_LABELS.find(r => r.code === code)
    return hit ? { code, label: hit.label, cls: hit.cls } : { code, label: code, cls: 'role-plain' }
  })
)

const strengthPercent = computed(() => {
  const n = [strength.value.upper, strength.value.lower, strength.value.digit].filter(Boolean).length
  return Math.round((n / 3) * 100)
})
const strengthCls = computed(() =>
  strengthPercent.value >= 67 ? 'strong' : (strengthPercent.value >= 34 ? 'mid' : 'weak')
)

function checkStrength() {
  const v = pwd.value.newPassword || ''
  strength.value = { upper: /[A-Z]/.test(v), lower: /[a-z]/.test(v), digit: /\d/.test(v) }
}

function fmtTime(s) {
  if (!s) return '—'
  const str = String(s)
  return str.length >= 16 ? str.slice(0, 16).replace('T', ' ') : str
}

function quotaPercent(m) {
  const limit = Number(m.quotaLimit)
  if (!limit || limit <= 0) return 0
  const used = Number(m.usedCount) || 0
  return Math.min(100, Math.round((used / limit) * 100))
}

async function loadUser() {
  try {
    const res = await api.get('/user/info')
    const d = res.data || {}
    user.value = {
      id: d.id,
      username: d.username || '',
      roles: Array.isArray(d.roles) ? d.roles : [],
      superAdmin: d.superAdmin ? 1 : 0,
      mustChangePwd: Number(d.mustChangePwd) || 0,
      lastLoginDate: d.lastLoginDate || ''
    }
  } catch (e) {
    // 未登录/权限被拒：静默降级（首页已提示过的话不重复打扰）
    if (!warned) { warned = true; toast(e.msg || '用户信息加载失败', 'error') }
  }
}

async function loadQuota() {
  quotaLoading.value = true
  try {
    const res = await api.get('/user/custom-models', { params: { page: 1, limit: 100 } })
    const data = res.data
    const list = Array.isArray(data) ? data : (data?.list || [])
    models.value = list.map(m => ({
      id: m.id,
      modelName: m.modelName || '未命名模型',
      usedCount: m.usedCount != null ? m.usedCount : 0,
      quotaLimit: m.quotaLimit
    }))
    // 音色数量顺带统计（失败不影响主数据）
    try {
      const v = await api.get('/user/custom-voices', { params: { page: 1, limit: 1 } })
      const vd = v.data
      voicesCount.value = Array.isArray(vd) ? vd.length : (vd?.total ?? (vd?.list ? vd.list.length : 0))
    } catch { voicesCount.value = 0 }
  } catch (e) {
    models.value = []
    if (!warned) { warned = true; toast(e.msg || '用量加载失败', 'error') }
  } finally {
    quotaLoading.value = false
  }
}

function loadAll() {
  loading.value = true
  Promise.all([loadUser(), loadQuota()]).finally(() => { loading.value = false })
}

async function changePwd() {
  if (!pwd.value.oldPassword || !pwd.value.newPassword) { toast('请填写旧密码和新密码', 'error'); return }
  if (pwd.value.newPassword !== pwd.value.confirm) { toast('两次输入的新密码不一致', 'error'); return }
  pwdBusy.value = true
  try {
    await api.put('/user/change-password', {
      oldPassword: pwd.value.oldPassword,
      newPassword: pwd.value.newPassword
    })
    toast('密码修改成功')
    pwd.value = { oldPassword: '', newPassword: '', confirm: '' }
    strength.value = { upper: false, lower: false, digit: false }
    // 改密成功后刷新用户信息（强制改密状态可能已被后端清除）
    loadUser()
  } catch (e) {
    toast(e.msg || '修改失败', 'error')
  } finally {
    pwdBusy.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.profile-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; align-items: start; }
@media (max-width: 900px) { .profile-grid { grid-template-columns: 1fr; } }

.panel { background: var(--surface); border-radius: var(--radius-lg); box-shadow: var(--shadow-card); }
.panel-head { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px 0; }
.panel-head h3 { font-size: 15px; }
.panel-head h3::before { content: ''; display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--primary); margin-right: 8px; }
.panel-head .hint { font-size: 12px; color: var(--text-sub); }
.panel-body { padding: 14px 20px 20px; }

.role-badge {
  display: inline-block; font-size: 12px; font-weight: 700; color: #fff;
  padding: 3px 12px; border-radius: 999px; margin-right: 8px; margin-top: 6px;
}
.role-super { background: var(--danger); }
.role-admin { background: var(--primary); }
.role-ro { background: var(--text-sub); }
.role-plain { background: var(--teal-3); }
.last-login { margin-top: 12px; opacity: .85; font-size: 12.5px; }

.form-row { margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input {
  border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px;
  font-size: 14px; outline: none; font-family: var(--font); background: #fff;
  transition: border .15s;
}
.form-row input:focus { border-color: var(--primary); }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; }

.strength { display: flex; align-items: center; gap: 10px; margin: -2px 0 12px; }
.strength-bar { flex: 1; height: 6px; border-radius: 999px; background: var(--border); overflow: hidden; }
.strength-bar > span { display: block; height: 100%; border-radius: 999px; transition: width .2s, background .2s; }
.strength-bar > span.weak { background: var(--danger); }
.strength-bar > span.mid { background: var(--warning); }
.strength-bar > span.strong { background: var(--success); }
.strength-tip { display: flex; gap: 8px; font-size: 11.5px; color: var(--text-sub); }
.strength-tip .ok { color: var(--success); font-weight: 700; }

.quota-list { display: flex; flex-direction: column; gap: 14px; }
.quota-item { display: flex; flex-direction: column; gap: 6px; }
.quota-head { display: flex; justify-content: space-between; font-size: 13px; }
.quota-name { font-weight: 600; }
.quota-num { color: var(--text-sub); }
.quota-bar { height: 8px; border-radius: 999px; background: var(--border); overflow: hidden; }
.quota-fill { display: block; height: 100%; border-radius: 999px; background: var(--primary); transition: width .25s; }
.quota-fill.warn { background: var(--danger); }
.quota-empty { color: var(--text-sub); font-size: 13.5px; padding: 14px 0; }

.tips { margin: 0; padding-left: 18px; display: flex; flex-direction: column; gap: 8px; }
.tips li { font-size: 13px; color: var(--text-sub); line-height: 1.6; }
</style>
