<template>
  <div class="dock-wrap">
    <nav class="dock">
      <!-- 导航自适应展开：单击在 展开(自适应文字宽度 72~140px) ↔ 收起(仅图标 56px) 间切换，状态存 localStorage 'cc_dock_collapsed' -->
      <button class="dock-toggle" :title="collapsed ? '展开导航栏' : '收起导航栏'" @click="toggleDock">
        <span class="ic">{{ collapsed ? '☰' : '«' }}</span>
        <span class="dock-label">{{ collapsed ? '展开' : '收起' }}</span>
      </button>
      <router-link
        v-for="item in items" :key="item.to"
        :to="item.to" class="dock-item"
        :class="{ active: isActive(item.to) }"
        :title="item.label"
      >
        <span class="ic">{{ item.icon }}</span>
        <span class="dock-label">{{ item.label }}</span>
      </router-link>
      <div class="dock-foot">
        <div class="theme-row">
          <button
            v-for="t in THEMES" :key="t.id"
            class="theme-swatch" :class="{ 'is-active': currentTheme === t.id }"
            :title="t.name" :style="{ background: t.dot }"
            @click="setTheme(t.id)"
          ></button>
        </div>
        <button
          class="compact-btn" :title="compact ? '切换宽松' : '切换紧凑'"
          :class="{ on: compact }" @click="toggleCompact"
        >⚅</button>
        <button class="dock-more" :title="role === 'admin' ? '切换到顾客端' : '切换到管理端'" @click="toggle">
          {{ role === 'admin' ? '⇄' : '→' }}
        </button>
      </div>
    </nav>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const props = defineProps({ role: { type: String, default: 'customer' } })
const emit = defineEmits(['toggle-compact'])

const route = useRoute()
const router = useRouter()

// 导航自适应展开：收起/展开状态（key 'cc_dock_collapsed'），仅布局自适应，文字字号 13px 不变。
// 类挂在 <html> 上：CSS 变量 --dock-w 只能向下继承，挂 <html> 才能同时联动 .app-shell 左 padding 与 dock 宽度。
const DOCK_CLASS = 'dock-collapsed'
const collapsed = ref(false)
function applyDockClass() {
  document.documentElement.classList.toggle(DOCK_CLASS, collapsed.value)
}
function toggleDock() {
  collapsed.value = !collapsed.value
  localStorage.setItem('cc_dock_collapsed', collapsed.value ? '1' : '0')
  applyDockClass()
}

// A9 主题（key 'cc_theme' 与原控制台互通，参照 App.vue:978-985、2543-2547）
const THEMES = [
  { id: 'blue', name: '蓝白（默认）', dot: 'linear-gradient(135deg,#2563EB,#0EA5E9)' },
  { id: 'kawaii', name: '奶油粉', dot: 'linear-gradient(135deg,#F9A8D4,#A78BFA)' },
  { id: 'dark', name: '深色', dot: 'linear-gradient(135deg,#0B1120,#3B82F6)' },
  { id: 'purple', name: '紫色', dot: 'linear-gradient(135deg,#7C3AED,#C026D3)' },
  { id: 'green', name: '绿色', dot: 'linear-gradient(135deg,#16A34A,#84CC16)' },
  { id: 'morandi', name: '莫兰迪', dot: 'linear-gradient(135deg,#8B9DAF,#D8A7A0)' }
]
const currentTheme = ref('blue')
const compact = ref(false)

function setTheme(id) {
  currentTheme.value = id
  document.documentElement.setAttribute('data-theme', id)
  localStorage.setItem('cc_theme', id)
}
function toggleCompact() {
  compact.value = !compact.value
  emit('toggle-compact', compact.value)
}
function restore() {
  const saved = localStorage.getItem('cc_theme') || 'blue'
  currentTheme.value = saved
  document.documentElement.setAttribute('data-theme', saved)
  compact.value = localStorage.getItem('cc_compact') === '1'
  emit('toggle-compact', compact.value)
  collapsed.value = localStorage.getItem('cc_dock_collapsed') === '1'
  applyDockClass()
}
onMounted(restore)

const customerItems = [
  { to: '/customer', icon: '🏠', label: '首页' },
  { to: '/customer/devices', icon: '📡', label: '我的设备' },
  { to: '/customer/voices', icon: '🎙', label: '音色' },
  { to: '/customer/points', icon: '💎', label: '积分' }
]
const adminItems = [
  { to: '/admin', icon: '🏠', label: '概览' },
  { to: '/admin/agents', icon: '🤖', label: '智能体' },
  { to: '/admin/chat', icon: '💬', label: '聊天' },
  { to: '/admin/memory', icon: '🧠', label: '记忆' },
  { to: '/admin/voices', icon: '🎙', label: '音色' },
  { to: '/admin/templates', icon: '🧩', label: '模板' },
  { to: '/admin/knowledge', icon: '📚', label: '知识库' },
  { to: '/admin/models', icon: '🧩', label: '模型' },
  { to: '/admin/devices', icon: '📡', label: '设备' },
  { to: '/admin/params', icon: '⚙️', label: '参数' },
  { to: '/admin/users', icon: '👥', label: '用户' },
  { to: '/admin/ota', icon: '📦', label: 'OTA' },
  { to: '/admin/dicts', icon: '📖', label: '字典' },
  { to: '/admin/servers', icon: '🖥', label: '服务器' },
  { to: '/admin/mcp', icon: '🔗', label: 'MCP' },
  { to: '/admin/linksim', icon: '🧪', label: '链路模拟' },
  { to: '/admin/wake-word', icon: '🔊', label: '唤醒词' },
  { to: '/admin/push-scheduler', icon: '📮', label: '推送调度' },
  { to: '/admin/apis', icon: '🛠', label: 'API调试' }
]
const items = computed(() => (props.role === 'admin' ? adminItems : customerItems))

function isActive(to) {
  return route.path === to
}
function toggle() {
  router.push(props.role === 'admin' ? '/customer' : '/admin')
}
</script>

<style scoped>
/* 折叠/展开切换按钮（布局与 .dock-item 对齐，收起态样式由 global.css .dock-collapsed 统一控制） */
.dock-toggle {
  display: flex; flex-direction: row; align-items: center; justify-content: flex-start;
  gap: 10px; padding: 10px 12px; margin-bottom: 6px; border: none; background: none; cursor: pointer;
  border-radius: 14px; color: var(--text-sub); font-size: 13px; font-weight: 600;
  font-family: var(--font); transition: all .18s; white-space: nowrap; position: relative;
}
.dock-toggle .ic { font-size: 18px; line-height: 1; flex-shrink: 0; transition: transform .18s; }
.dock-toggle .dock-label { white-space: nowrap; }
.dock-toggle:hover { color: var(--primary); background: var(--primary-soft); }
.dock-toggle:hover .ic { transform: scale(1.12); }

.dock-foot {
  margin-top: auto;
  padding-top: 10px;
  border-top: 1px solid rgba(27,44,80,.08);
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
}
.theme-row { display: flex; flex-wrap: wrap; gap: 5px; justify-content: center; max-width: 72px; }
.theme-swatch {
  width: 16px; height: 16px; border-radius: 50%; border: 2px solid transparent;
  cursor: pointer; padding: 0; transition: transform .15s, border-color .15s;
}
.theme-swatch:hover { transform: scale(1.2); }
.theme-swatch.is-active { border-color: #fff; box-shadow: 0 0 0 2px var(--primary); }
.compact-btn {
  width: 34px; height: 30px; border-radius: 10px; border: 1.5px solid var(--border);
  background: var(--surface); color: var(--text-sub); cursor: pointer; font-size: 14px;
  transition: all .15s;
}
.compact-btn.on { border-color: var(--primary); color: var(--primary); background: var(--primary-soft); }
</style>
