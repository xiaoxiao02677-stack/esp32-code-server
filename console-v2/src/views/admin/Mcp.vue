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
      <button class="btn btn-primary" :disabled="loading || testing" @click="loadAddress">{{ loading ? '获取中…' : '获取 MCP 地址' }}</button>
      <button class="btn btn-ghost" :disabled="loading || testing" @click="loadTools">列出工具</button>
      <button class="btn btn-ghost" :disabled="loading || testing" @click="runTest">{{ testing ? '测试中…' : '⚡ 连通测试' }}</button>
    </div>

    <div v-if="mcpTestResult" class="mcp-test-panel" :class="mcpTestResult.ok ? 'mcp-test-ok' : 'mcp-test-fail'">
      <div class="mcp-test-label">测试结果（{{ mcpTestResult.elapsed_ms }}ms）</div>
      <div class="mcp-test-msg">{{ mcpTestResult.ok ? '✅ ' : '❌ ' }}{{ mcpTestResult.message }}</div>
      <div v-if="mcpTestResult.address" class="mcp-test-addr">{{ mcpTestResult.address }}</div>
    </div>

    <div v-if="mcpUrl" class="mcp-panel">
      <div class="mcp-panel-title">MCP 接入地址</div>
      <div class="mcp-address-row">
        <code class="mcp-address">{{ mcpUrl }}</code>
        <button class="btn btn-ghost mcp-copy-btn" @click="copyMcpAddress">⧉ 复制</button>
      </div>
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
import { computed, inject, onMounted, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const agents = ref([])
const agentId = ref('')
const mcpUrl = ref('')
const tools = ref([])
const mcpTestResult = ref(null)
const loading = ref(false)
const testing = ref(false)

const testResult = computed(() => {
  if (testing.value) return '测试中…'
  if (!mcpTestResult.value) return '—'
  return mcpTestResult.value.ok ? '✓ 连通' : '✗ 失败'
})

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
  mcpTestResult.value = null
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
  testing.value = true
  mcpTestResult.value = null
  try {
    const res = await adminApi.mcpTest(agentId.value)
    const d = res.data
    if (d && typeof d === 'object') {
      mcpTestResult.value = {
        ok: !!d.ok,
        message: d.message || (d.ok ? '测试成功' : '测试失败'),
        elapsed_ms: d.elapsed_ms ?? 0,
        address: d.address || ''
      }
    } else {
      mcpTestResult.value = { ok: false, message: (res && res.msg) || '测试失败', elapsed_ms: 0, address: '' }
    }
    if (mcpTestResult.value.ok) toast('MCP 连通测试通过')
    else toast(mcpTestResult.value.message, 'error')
    if (d?.tools) tools.value = d.tools
  } catch (e) {
    mcpTestResult.value = { ok: false, message: '请求异常：' + (e.msg || e.message || '未知错误'), elapsed_ms: 0, address: '' }
    toast(mcpTestResult.value.message, 'error')
  } finally { testing.value = false }
}

async function copyMcpAddress() {
  const text = mcpUrl.value
  if (!text) return
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const el = document.createElement('textarea')
      el.value = text
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
    }
    toast('已复制')
  } catch (e) {
    toast('复制失败', 'error')
  }
}

onMounted(load)
</script>

<style scoped>
.chip { padding: 8px 16px; border-radius: 999px; background: var(--surface); border: 1.5px solid var(--border); cursor: pointer; font-size: 13px; }
.chip.active { border-color: var(--primary); color: var(--primary); font-weight: 600; }

/* ===== A3 接入点地址 + 复制按钮 ===== */
.mcp-panel { margin-bottom: 16px; padding: 16px; border-radius: var(--radius-lg); background: var(--surface); box-shadow: var(--shadow-card); }
.mcp-panel-title { font-size: 13px; font-weight: 700; margin-bottom: 6px; }
.mcp-address-row { display: flex; align-items: center; gap: 10px; }
.mcp-address { flex: 1; min-width: 0; font-size: 12px; word-break: break-all; background: var(--bg, #F5F7FA); padding: 10px 12px; border-radius: 10px; display: block; }
.mcp-copy-btn { padding: 8px 14px; font-size: 12.5px; flex-shrink: 0; }

/* ===== A12 测试结果面板 ===== */
.mcp-test-panel { border-radius: var(--radius-md); padding: 14px 16px; margin-bottom: 16px; }
.mcp-test-ok { background: rgba(47, 191, 113, .10); border: 1px solid rgba(47, 191, 113, .28); }
.mcp-test-fail { background: rgba(240, 83, 77, .10); border: 1px solid rgba(240, 83, 77, .28); }
.mcp-test-label { font-size: 12px; font-weight: 700; color: var(--text-sub); margin-bottom: 6px; }
.mcp-test-msg { font-size: 13.5px; font-weight: 600; }
.mcp-test-addr { font-size: 12px; word-break: break-all; margin-top: 6px; color: var(--text-sub); font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; }
</style>
