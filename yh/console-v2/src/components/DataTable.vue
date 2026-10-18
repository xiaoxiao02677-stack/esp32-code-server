<template>
  <div class="panel">
    <div class="panel-head">
      <h3>{{ title }}<span class="hint">{{ hint }}</span></h3>
      <slot name="actions" />
    </div>
    <!-- 加载骨架：与表格行同构，替代空白/转圈 -->
    <div v-if="loading" class="dt-skeleton" role="status" aria-label="加载中">
      <div v-for="r in 5" :key="r" class="sk-row">
        <span class="sk-bar" style="width: 22%"></span>
        <span class="sk-bar" style="width: 16%"></span>
        <span class="sk-bar" style="width: 30%"></span>
        <span class="sk-bar" style="width: 12%"></span>
      </div>
    </div>
    <slot v-else />
    <div class="pager" v-if="total > 0">
      <span>共 {{ total }} 条</span>
      <select :value="pageSize" aria-label="每页条数" @change="$emit('update:pageSize', Number($event.target.value))">
        <option v-for="s in pageSizeOptions" :key="s" :value="s">{{ s }}条/页</option>
      </select>
      <button class="page-btn" :disabled="page <= 1" aria-label="上一页" @click="go(page - 1)">‹</button>
      <template v-for="(p, i) in pageItems" :key="i">
        <span v-if="p === '…'" class="page-ellipsis">…</span>
        <button v-else class="page-btn" :class="{ active: p === page }" @click="go(p)">{{ p }}</button>
      </template>
      <button class="page-btn" :disabled="page >= pages" aria-label="下一页" @click="go(page + 1)">›</button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  hint: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  total: { type: Number, default: 0 },
  page: { type: Number, default: 1 },
  pageSize: { type: Number, default: 20 },
  pages: { type: Number, default: 1 },
  pageSizeOptions: { type: Array, default: () => [10, 20, 50, 100] }
})

const emit = defineEmits(['update:page', 'update:pageSize'])

const pageSizeOptions = computed(() => {
  const opts = [...props.pageSizeOptions]
  if (!opts.includes(props.pageSize)) opts.push(props.pageSize)
  return opts.sort((a, b) => a - b)
})

// 页码窗口：1 … cur-1 cur cur+1 … 末页（总页数少时全展开）
const pageItems = computed(() => {
  const total = Math.max(1, props.pages)
  const cur = props.page
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const set = new Set([1, total, cur - 1, cur, cur + 1].filter(p => p >= 1 && p <= total))
  const sorted = [...set].sort((a, b) => a - b)
  const out = []
  let prev = 0
  for (const p of sorted) {
    if (p - prev > 1) out.push('…')
    out.push(p)
    prev = p
  }
  return out
})

function go(p) {
  const target = Math.min(Math.max(1, p), Math.max(1, props.pages))
  if (target !== props.page) emit('update:page', target)
}
</script>

<style scoped>
.dt-skeleton { padding: 6px 0 10px; }
.sk-row { display: flex; gap: 14px; padding: 16px 20px; }
.sk-row + .sk-row { border-top: 1px solid var(--border); }
.sk-bar {
  display: block; height: 12px; border-radius: 6px;
  background: var(--border); animation: sk-fade 1.2s ease-in-out infinite;
}
@keyframes sk-fade { 50% { opacity: .4; } }
.page-ellipsis { min-width: 24px; text-align: center; color: var(--text-sub); align-self: center; }
</style>
