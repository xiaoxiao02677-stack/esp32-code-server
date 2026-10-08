<template>
  <header class="topbar">
    <div class="brand">
      <div class="brand-logo">⚡</div>
      <div>
        <span class="brand-name">小智 AIoT</span>
        <span class="brand-sub">{{ role === 'admin' ? '管理端' : '体验端' }}</span>
      </div>
    </div>
    <div class="searchbox">
      <span>🔍</span>
      <input :placeholder="role === 'admin' ? '搜索模板、知识库或用户' : '搜索智能体或设备'" />
      <span class="kbd">Ctrl K</span>
    </div>
    <div class="topbar-right">
      <button class="role-switch" @click="$emit('switch-role', role === 'admin' ? 'customer' : 'admin')">
        {{ role === 'admin' ? '→ 顾客视图' : '→ 管理员视图' }}
      </button>
      <div class="avatar" :title="role === 'admin' ? '管理员' : '顾客'">
        {{ role === 'admin' ? '管' : '客' }}
      </div>
    </div>
  </header>
</template>

<script setup>
defineProps({ role: { type: String, default: 'customer' } })
defineEmits(['switch-role'])
</script>
