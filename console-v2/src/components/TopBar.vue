<template>
  <header class="topbar">
    <div class="brand">
      <div class="brand-logo">⚡</div>
      <div>
        <span class="brand-name">屿禾工坊</span>
        <span class="brand-sub">{{ role === 'admin' ? '管理端' : '体验端' }}</span>
      </div>
    </div>
    <div class="searchbox">
      <span>🔍</span>
      <input
        ref="searchInput"
        v-model="keyword"
        placeholder="搜索页面，回车快速跳转"
        @focus="focused = true"
        @blur="onBlur"
        @keydown.enter="onEnter"
        @keydown.esc="onEsc"
      />
      <span class="kbd">Ctrl K</span>
      <div v-if="showPanel" class="search-drop">
        <button
          v-for="m in matches"
          :key="m.path"
          class="drop-item"
          @mousedown.prevent
          @click="go(m.path)"
        >
          <span class="drop-ic">{{ m.icon }}</span>
          <span class="drop-label">{{ m.label }}</span>
          <span class="drop-path">{{ m.path }}</span>
        </button>
        <div v-if="matches.length === 0" class="drop-empty">无匹配页面</div>
      </div>
    </div>
    <div class="topbar-right">
      <button class="role-switch" @click="$emit('switch-role', role === 'admin' ? 'customer' : 'admin')">
        {{ role === 'admin' ? '→ 顾客视图' : '→ 管理员视图' }}
      </button>
      <button class="btn btn-ghost logout-btn" @click="confirmLogout">退出登录</button>
      <div class="avatar" :title="avatarTitle">{{ avatarChar }}</div>
    </div>
  </header>
</template>

<script setup>
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { clearToken } from '../lib/api'

const props = defineProps({ role: { type: String, default: 'customer' } })
defineEmits(['switch-role'])

const route = useRoute()
const router = useRouter()
const askConfirm = inject('askConfirm')

// ===== A20b 快速跳转：导航映射（路径与 DockNav.vue 完全一致） =====
const adminNav = [
  { label: '概览', path: '/admin', icon: '🏠' },
  { label: '智能体', path: '/admin/agents', icon: '🤖' },
  { label: '聊天', path: '/admin/chat', icon: '💬' },
  { label: '记忆', path: '/admin/memory', icon: '🧠' },
  { label: '音色', path: '/admin/voices', icon: '🎙' },
  { label: '模板', path: '/admin/templates', icon: '🧩' },
  { label: '知识库', path: '/admin/knowledge', icon: '📚' },
  { label: '模型', path: '/admin/models', icon: '🧩' },
  { label: '设备', path: '/admin/devices', icon: '📡' },
  { label: '参数', path: '/admin/params', icon: '⚙️' },
  { label: '用户', path: '/admin/users', icon: '👥' },
  { label: 'OTA', path: '/admin/ota', icon: '📦' },
  { label: '字典', path: '/admin/dicts', icon: '📖' },
  { label: '服务器', path: '/admin/servers', icon: '🖥' },
  { label: 'MCP', path: '/admin/mcp', icon: '🔗' },
  { label: '链路模拟', path: '/admin/linksim', icon: '🧪' },
  { label: 'API调试', path: '/admin/apis', icon: '🛠' }
]
const customerNav = [
  { label: '首页', path: '/customer', icon: '🏠' },
  { label: '我的设备', path: '/customer/devices', icon: '📡' },
  { label: '音色', path: '/customer/voices', icon: '🎙' },
  { label: '积分', path: '/customer/points', icon: '💎' }
]

const searchInput = ref(null)
const keyword = ref('')
const focused = ref(false)

const matches = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  if (!k) return []
  const nav = props.role === 'admin' ? adminNav : customerNav
  return nav.filter(m => m.label.toLowerCase().includes(k) || m.path.toLowerCase().includes(k))
})
const showPanel = computed(() => focused.value && keyword.value.trim() !== '')

function go(path) {
  router.push(path)
  keyword.value = ''
  focused.value = false
  searchInput.value?.blur()
}
function onEnter(e) {
  if (e.isComposing) return
  if (matches.value.length) go(matches.value[0].path)
}
function onEsc() {
  keyword.value = ''
  focused.value = false
  searchInput.value?.blur()
}
function onBlur() {
  // 延迟关闭，给下拉项的 click 留出时间
  setTimeout(() => { focused.value = false }, 150)
}
function onGlobalKeydown(e) {
  if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault()
    searchInput.value?.focus()
  }
}
onMounted(() => window.addEventListener('keydown', onGlobalKeydown))
onUnmounted(() => window.removeEventListener('keydown', onGlobalKeydown))

// ===== A6 用户名（登录成功后写入 localStorage 'v2-user'，路由切换时重读） =====
function readUsername() {
  try { return (localStorage.getItem('v2-user') || '').trim() } catch { return '' }
}
const username = ref(readUsername())
watch(() => route.fullPath, () => { username.value = readUsername() })

const avatarChar = computed(() => username.value
  ? username.value.charAt(0).toUpperCase()
  : (props.role === 'admin' ? '管' : '客'))
const avatarTitle = computed(() => username.value || (props.role === 'admin' ? '管理员' : '顾客'))

function confirmLogout() {
  askConfirm({
    title: '退出登录',
    message: '确定退出当前账号吗？',
    okText: '退出登录',
    onOk: () => {
      clearToken()
      localStorage.removeItem('v2-user')
      router.push('/login')
    }
  })
}
</script>

<style scoped>
.searchbox { position: relative; }
.logout-btn { padding: 7px 16px; font-size: 13px; }
.logout-btn:hover { border-color: var(--danger); color: var(--danger); background: #FDEDEC; }
.search-drop {
  position: absolute; top: calc(100% + 8px); left: 0; right: 0;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 14px; box-shadow: 0 12px 32px rgba(20, 40, 80, .14);
  padding: 6px; z-index: 90; max-height: 320px; overflow-y: auto;
}
.drop-item {
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 9px 12px; border: none; background: transparent;
  border-radius: 10px; cursor: pointer; font-size: 13px;
  text-align: left; font-family: var(--font);
}
.drop-item:hover { background: var(--primary-soft); }
.drop-ic { font-size: 15px; flex-shrink: 0; }
.drop-label { font-weight: 600; color: var(--text); flex-shrink: 0; }
.drop-path { margin-left: auto; font-size: 11.5px; color: var(--text-sub); }
.drop-empty { padding: 14px; text-align: center; color: var(--text-sub); font-size: 12.5px; }
</style>
