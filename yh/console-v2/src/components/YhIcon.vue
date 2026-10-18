<template>
  <svg class="yh-ic" :width="size" :height="size" viewBox="0 0 24 24" fill="none"
       stroke="currentColor" :stroke-width="strokeWidth" stroke-linecap="round"
       stroke-linejoin="round" aria-hidden="true" v-html="markup"></svg>
</template>

<script setup>
import { computed } from 'vue'
import { ICONS } from './yh-icons'

const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 18 },
  strokeWidth: { type: [Number, String], default: 1.8 }
})

// 未登记的名字回落为小圆点，避免渲染成空白
const markup = computed(() => ICONS[props.name] || '<circle cx="12" cy="12" r="4"/>')
</script>
