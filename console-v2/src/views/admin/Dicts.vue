<template>
  <div>
    <div class="page-head">
      <div>
        <h1>数据 <span style="color:var(--primary)">字典</span></h1>
        <p class="sub">迁移自 /cc/ 数据字典页：字典类型 / 字典数据 / 删除</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="📚" label="字典类型" :value="types.length" />
      <StatCard icon="📄" label="当前类型数据" :value="datas.length" :note="activeType" />
    </div>

    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px">
      <div v-for="t in types" :key="t.id" class="chip" :class="{ active: activeType === t.dictType }" @click="pickType(t)">
        {{ t.dictName || t.dictType }}
      </div>
    </div>

    <DataTable title="字典数据">
      <table class="data-table">
        <thead><tr><th>标签</th><th>值</th><th>排序</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="d in datas" :key="d.id">
            <td><div class="cell-main">{{ d.dictLabel }}</div></td>
            <td style="font-size:12px">{{ d.dictValue }}</td>
            <td>{{ d.sort ?? d.orderNum ?? '—' }}</td>
            <td><div class="row-actions"><button class="link-btn danger" @click="remove(d)">删除</button></div></td>
          </tr>
        </tbody>
      </table>
      <div v-if="activeType && datas.length === 0" class="empty-state"><strong>此类型暂无数据</strong></div>
      <div v-if="!activeType" class="empty-state"><div class="empty-icon">📚</div><strong>先选择字典类型</strong></div>
    </DataTable>
  </div>
</template>

<script setup>
import { inject, onMounted, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')
const types = ref([])
const datas = ref([])
const activeType = ref('')
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await adminApi.dictTypePage({ page: 1, limit: 100 })
    const data = res.data || {}
    types.value = data.list || []
    if (types.value.length && !activeType.value) pickType(types.value[0])
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

async function pickType(t) {
  activeType.value = t.dictType
  try {
    const res = await adminApi.dictData(t.dictType)
    datas.value = res.data || []
  } catch (e) { toast(e.msg || '字典数据加载失败', 'error'); datas.value = [] }
}

function remove(d) {
  askConfirm({
    title: '删除字典数据', message: `确定删除「${d.dictLabel}」吗？`, danger: true,
    onOk: async () => {
      try { await adminApi.deleteDictData([d.id]); toast('已删除'); pickType({ dictType: activeType.value }) }
      catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}

onMounted(load)
</script>

<style scoped>
.chip { padding: 8px 16px; border-radius: 999px; background: var(--bg-card); border: 1.5px solid var(--border); cursor: pointer; font-size: 13px; }
.chip.active { border-color: var(--primary); color: var(--primary); font-weight: 600; }
</style>
