<template>
  <div>
    <div class="page-head">
      <div>
        <h1>MCP <span style="color:var(--primary)">接入点</span></h1>
        <p class="sub">迁移自 /cc/ MCP 页：接入地址 / 工具列表 / 连通测试</p>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="🤖" label="智能体" :value="agents.length" />
      <StatCard icon="🔗" label="MCP 地址" :value="mcpUrl ? '已获取' : '—'" :note="mcpUrl.slice(0, 24)" />
      <StatCard icon="🛠" label="工具数" :value="tools.length" />
      <StatCard icon="📡" label="连通测试" :value="testResult" />
    </div>

    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px">
      <div v-for="a in agents" :key="a.id" class="chip" :class="{ active: agentId === a.id }" @click="pick(a)">
        {{ a.name }}
      </div>
    </div>

    <div v-if="agentId" style="display:flex;gap:10px;margin-bottom:16px">
      <button class="btn btn-primary" :disabled="loading" @click="loadAddress">{{ loading ? '获取中…' : '获取 MCP 地址' }}</button>
      <button class="btn btn-ghost" :disabled="loading" @click="loadTools">列出工具</button>
      <button class="btn btn-ghost" :disabled="loading" @click="runTest">连通测试</button>
    </div>

    <div v-if="mcpUrl" class="DataTable card" style="margin-bottom:16px;padding:16px;border-radius:24px;background:var(--bg-card)">
      <div style="font-size:13px;font-weight:700;margin-bottom:6px">MCP 接入地址</div>
      <code style="font-size:12px;word-break:break-all;background:var(--bg-soft);padding:10px 12px;border-radius:10px;display:block">{{ mcpUrl }}</code>
    </div>

    <DataTable title="工具列表">
      <table class="data-table">
        <thead><tr><th>工具</th><th>描述</th></tr></thead>
        <tbody>
          <tr v-for="t in tools" :key="t.name || t.id">
            <td><div class="cell-main">{{ t.name || t.toolName }}</div></td>
            <td style="font-size:12px">{{ t.description || t.desc || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="agentId && tools.length === 0" class="empty-state"><div class="empty-icon">🛠</div><strong>点击「列出工具」查看</strong></div>
    </DataTable>
  </div>
</template>

<script setup>
import { inject, onMounted, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const agents = ref([])
const agentId = ref('')
const mcpUrl = ref('')
const tools = ref([])
const testResult = ref('—')
const loading = ref(false)

async function load() {
  try {
    const res = await adminApi.agentList()
    agents.value = (res.data || []).map(a => ({ id: a.agentId || a.id, name: a.agentName || a.name || '未命名' }))
  } catch (e) { toast(e.msg || '智能体加载失败', 'error') }
}

function pick(a) {
  agentId.value = a.id
  mcpUrl.value = ''
  tools.value = []
  testResult.value = '—'
}

async function loadAddress() {
  loading.value = true
  try {
    const res = await adminApi.mcpAddress(agentId.value)
    mcpUrl.value = typeof res.data === 'string' ? res.data : (res.data?.url || res.data?.address || JSON.stringify(res.data))
    toast('MCP 地址已获取')
  } catch (e) { toast(e.msg || '获取失败', 'error') }
  finally { loading.value = false }
}

async function loadTools() {
  loading.value = true
  try {
    const res = await adminApi.mcpTools(agentId.value)
    tools.value = res.data?.tools || res.data || []
    toast(`获取到 ${tools.value.length} 个工具`)
  } catch (e) { toast(e.msg || '工具列表获取失败', 'error') }
  finally { loading.value = false }
}

async function runTest() {
  loading.value = true
  testResult.value = '测试中…'
  try {
    const res = await adminApi.mcpTest(agentId.value)
    testResult.value = '✓ 连通'
    toast('MCP 连通测试通过')
    if (res.data?.tools) tools.value = res.data.tools
  } catch (e) { testResult.value = '✗ 失败'; toast(e.msg || 'MCP 测试失败', 'error') }
  finally { loading.value = false }
}

onMounted(load)
</script>

<style scoped>
.chip { padding: 8px 16px; border-radius: 999px; background: var(--bg-card); border: 1.5px solid var(--border); cursor: pointer; font-size: 13px; }
.chip.active { border-color: var(--primary); color: var(--primary); font-weight: 600; }
</style>
