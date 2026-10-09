<template>
  <div class="panel">
    <div class="panel-head">
      <h3>{{ title }}<span class="hint">{{ hint }}</span></h3>
      <slot name="actions" />
    </div>
    <slot />
    <div class="pager" v-if="total > 0">
      <span>共 {{ total }} 条</span>
      <select :value="pageSize" @change="$emit('update:pageSize', Number($event.target.value))">
        <option v-for="s in pageSizeOptions" :key="s" :value="s">{{ s }}条/页</option>
      </select>
      <button class="page-btn wide" :disabled="page <= 1" @click="go(1)">首页</button>
      <button class="page-btn" :disabled="page <= 1" @click="go(page - 1)">‹</button>
      <button class="page-btn active">{{ page }}</button>
      <button class="page-btn" :disabled="page >= pages" @click="go(page + 1)">›</button>
      <button class="page-btn wide" :disabled="page >= pages" @click="go(pages)">下一页</button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  hint: { type: String, default: '' },
  total: { type: Number, default: 0 },
  page: { type: Number, default: 1 },
  pageSize: { type: Number, default: 20 },
  pages: { type: Number, default: 1 }
})

const emit = defineEmits(['update:page', 'update:pageSize'])

const pageSizeOptions = computed(() => {
  const opts = [4, 8, 20, 50]
  if (!opts.includes(props.pageSize)) opts.push(props.pageSize)
  return opts.sort((a, b) => a - b)
})

const totalPages = computed(() => props.pages)

function go(p) {
  const target = Math.min(Math.max(1, p), totalPages.value)
  if (target !== props.page) emit('update:page', target)
}
</script>
