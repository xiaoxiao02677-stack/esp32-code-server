<template>
  <div>
    <div class="page-head">
      <div>
        <h1>服务器 <span style="color:var(--primary)">节点</span></h1>
        <p class="sub">迁移自 /cc/ 服务器节点页：WS 接入节点列表</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="🖥" label="节点总数" :value="servers.length" />
      <StatCard icon="🟢" label="启用" :value="servers.filter(s => s.enable).length" />
    </div>

    <DataTable title="节点列表">
      <table class="data-table">
        <thead><tr><th>名称</th><th>地址</th><th>状态</th><th>说明</th></tr></thead>
        <tbody>
          <tr v-for="s in servers" :key="s.id || s.name">
            <td><div class="cell-main">{{ s.name || s.serverName || s.id }}</div></td>
            <td style="font-size:12px">{{ s.wsUrl || s.url || s.address || '—' }}</td>
            <td>
              <span class="badge" :class="s.enable ? 'badge-green' : 'badge-gray'">
                <span class="dot"></span>{{ s.enable ? '启用' : '停用' }}
              </span>
            </td>
            <td style="font-size:12px">{{ s.remark || s.description || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="servers.length === 0" class="empty-state"><div class="empty-icon">🖥</div><strong>暂无节点</strong></div>
    </DataTable>
  </div>
</template>

<script setup>
import { inject, onMounted, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const servers = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await adminApi.serverList()
    const data = res.data
    // 契约：data 为字符串数组（WS 地址列表）
    servers.value = (Array.isArray(data) ? data : (data?.list || [])).map((s, i) =>
      typeof s === 'string'
        ? { id: 'srv-' + i, name: '节点 ' + (i + 1), wsUrl: s, enable: true }
        : { id: s.id || s.name, name: s.name || s.serverName, wsUrl: s.wsUrl || s.url || s.address, enable: s.enable }
    )
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

onMounted(load)
</script>
