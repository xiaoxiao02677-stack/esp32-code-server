<template>
  <div class="stat-card">
    <span class="stat-icon">{{ icon }}</span>
    <span class="stat-label">{{ label }}</span>
    <span class="stat-value">{{ value }}</span>
    <span class="stat-note">{{ note }}</span>
  </div>
</template>

<script setup>
defineProps({
  icon: { type: String, default: '' },
  label: { type: String, default: '' },
  value: { type: [String, Number], default: '—' },
  note: { type: String, default: '' }
})
</script>
