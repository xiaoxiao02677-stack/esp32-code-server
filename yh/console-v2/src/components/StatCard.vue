<template>
  <div class="stat-card">
    <span class="stat-icon">
      <YhIcon v-if="hasIcon(icon)" :name="icon" :size="22" />
      <template v-else>{{ icon }}</template>
    </span>
    <span class="stat-label">{{ label }}</span>
    <span class="stat-value">{{ value }}</span>
    <span class="stat-note">{{ note }}</span>
  </div>
</template>

<script setup>
import YhIcon from './YhIcon.vue'
import { hasIcon } from './yh-icons'

defineProps({
  icon: { type: String, default: '' },
  label: { type: String, default: '' },
  value: { type: [String, Number], default: '—' },
  note: { type: String, default: '' }
})
</script>
