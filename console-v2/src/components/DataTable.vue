<template>
  <div class="panel">
    <div class="panel-head">
      <h3>{{ title }}<span class="hint">{{ hint }}</span></h3>
      <slot name="actions" />
    </div>
    <slot />
    <div class="pager">
      <span>共 {{ total }} 条</span>
      <select>
        <option>4条/页</option><option>8条/页</option><option>20条/页</option>
      </select>
      <button class="page-btn wide" :disabled="page <= 1">首页</button>
      <button class="page-btn" :disabled="page <= 1">‹</button>
      <button class="page-btn active">{{ page }}</button>
      <button class="page-btn" :disabled="page >= pages">›</button>
      <button class="page-btn wide" :disabled="page >= pages">下一页</button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  hint: { type: String, default: '' },
  total: { type: Number, default: 0 },
  page: { type: Number, default: 1 },
  pages: { type: Number, default: 1 }
})
</script>
