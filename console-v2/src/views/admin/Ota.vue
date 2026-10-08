<template>
  <div>
    <div class="page-head">
      <div>
        <h1>OTA <span style="color:var(--primary)">固件</span></h1>
        <p class="sub">迁移自 /cc/ OTA 页：固件列表 / 删除</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="📦" label="固件包" :value="otas.length" />
      <StatCard icon="⬆️" label="最高版本" :value="maxVersion" />
    </div>

    <DataTable title="固件列表">
      <table class="data-table">
        <thead><tr><th>版本</th><th>文件</th><th>时间</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="o in otas" :key="o.id">
            <td><div class="cell-main">{{ o.version || o.appVersion }}</div></td>
            <td style="font-size:12px">{{ o.fileName || o.path || '—' }}</td>
            <td style="font-size:12px">{{ o.createDate || '' }}</td>
            <td><div class="row-actions"><button class="link-btn danger" @click="remove(o)">删除</button></div></td>
          </tr>
        </tbody>
      </table>
      <div v-if="otas.length === 0" class="empty-state"><div class="empty-icon">📦</div><strong>暂无固件</strong></div>
    </DataTable>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')
const otas = ref([])
const loading = ref(false)
const maxVersion = computed(() => otas.value.map(o => o.version || o.appVersion).sort().pop() || '—')

async function load() {
  loading.value = true
  try {
    const res = await adminApi.otaPage({ page: 1, limit: 100 })
    const data = res.data || {}
    otas.value = data.list || []
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

function remove(o) {
  askConfirm({
    title: '删除固件', message: `确定删除「${o.version || o.appVersion}」吗？`, danger: true,
    onOk: async () => {
      try { await adminApi.deleteOta(o.id); toast('已删除'); load() }
      catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}

onMounted(load)
</script>
