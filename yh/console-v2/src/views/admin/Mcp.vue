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

    <!-- ===== MCP Server 配置面板 ===== -->
    <div class="mcp-config-section" style="margin-top:28px">
      <div class="mcp-config-title">📋 MCP Server 配置</div>
      <div class="mcp-config-hint">
        配置 per-agent 的 MCP Server JSON（`mcpServers` 对象，每个 key 为一个 server）。
        修改后需重启智能体服务生效。
      </div>

      <div class="mcp-config-form">
        <div class="form-row">
          <label class="form-label">配置名称</label>
          <input class="form-input" v-model="configName" placeholder="如：搜索工具、日历助手" />
        </div>
        <div class="form-row form-row-full">
          <label class="form-label">JSON 配置内容</label>
          <textarea
            class="form-textarea"
            v-model="serverJson"
            placeholder='{\n  "mcpServers": {\n    "filesystem": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/folder"],\n      "env": {}\n    }\n  }\n}'
            spellcheck="false"
          ></textarea>
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" :disabled="configLoading" @click="handleSave">
            {{ configLoading ? '保存中…' : '保存配置' }}
          </button>
          <button class="btn btn-ghost" :disabled="configLoading" @click="handleValidate">
            校验 JSON
          </button>
          <button class="btn btn-danger" :disabled="configLoading || !agentId" @click="handleDelete">
            删除配置
          </button>
        </div>
        <div v-if="configResult" class="mcp-config-result" :class="configResult.ok ? 'result-ok' : 'result-fail'">
          {{ configResult.ok ? '✅ ' : '❌ ' }}{{ configResult.message }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, ref, watch } from 'vue'
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

// ===== MCP Server 配置 =====
const configName = ref('')
const serverJson = ref('')
const configResult = ref(null)
const configLoading = ref(false)

async function loadConfig() {
  if (!agentId.value) return
  try {
    const res = await adminApi.mcpConfig(agentId.value)
    const data = res.data
    if (data) {
      // 尝试解析为 JSON 对象获取 name，否则回退
      if (typeof data === 'object' && data.name) {
        configName.value = data.name
      } else {
        configName.value = ''
      }
      // serverJson 字段或直接整个响应
      serverJson.value = typeof data === 'string' ? data : JSON.stringify(data, null, 2)
    } else {
      configName.value = ''
      serverJson.value = ''
    }
    configResult.value = null
  } catch (e) {
    // 无配置时返回空即可
    configName.value = ''
    serverJson.value = ''
  }
}

function parseJson() {
  try {
    const obj = JSON.parse(serverJson.value)
    return { ok: true, obj }
  } catch (e) {
    return { ok: false, error: e.message }
  }
}

async function handleValidate() {
  configResult.value = null
  if (!serverJson.value.trim()) {
    configResult.value = { ok: false, message: 'JSON 内容为空' }
    return
  }
  const parsed = parseJson()
  if (!parsed.ok) {
    configResult.value = { ok: false, message: 'JSON 格式错误：' + parsed.error }
    return
  }
  try {
    const res = await adminApi.validateMcpJson(JSON.stringify(parsed.obj))
    configResult.value = { ok: true, message: '✅ JSON 校验通过' }
    toast('JSON 校验通过')
  } catch (e) {
    configResult.value = { ok: false, message: '❌ 校验失败：' + (e.msg || '未知错误') }
    toast(e.msg || 'JSON 校验失败', 'error')
  }
}

async function handleSave() {
  configResult.value = null
  if (!agentId.value) { toast('请先选择一个智能体', 'error'); return }
  if (!serverJson.value.trim()) { configResult.value = { ok: false, message: 'JSON 内容为空' }; return }

  const parsed = parseJson()
  if (!parsed.ok) {
    configResult.value = { ok: false, message: 'JSON 格式错误：' + parsed.error }
    toast('JSON 格式错误，请先校验', 'error')
    return
  }

  configLoading.value = true
  try {
    // 先校验
    await adminApi.validateMcpJson(JSON.stringify(parsed.obj))
    // 再保存
    await adminApi.saveMcpConfig({ agent_id: agentId.value, name: configName.value, serverJson: JSON.stringify(parsed.obj) })
    configResult.value = { ok: true, message: '✅ 配置已保存' }
    toast('配置保存成功')
  } catch (e) {
    configResult.value = { ok: false, message: '❌ 保存失败：' + (e.msg || '未知错误') }
    toast(e.msg || '保存失败', 'error')
  } finally {
    configLoading.value = false
  }
}

async function handleDelete() {
  if (!agentId.value) { toast('请先选择一个智能体', 'error'); return }
  if (!confirm('确认删除该智能体的 MCP Server 配置？此操作不可撤销。')) return
  configLoading.value = true
  try {
    await adminApi.deleteMcpConfig(agentId.value)
    configResult.value = { ok: true, message: '✅ 配置已删除' }
    configName.value = ''
    serverJson.value = ''
    toast('配置已删除')
  } catch (e) {
    configResult.value = { ok: false, message: '❌ 删除失败：' + (e.msg || '未知错误') }
    toast(e.msg || '删除失败', 'error')
  } finally {
    configLoading.value = false
  }
}

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

// 监听 agentId 变化，自动加载对应配置
watch(agentId, () => { loadConfig() })
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

/* ===== MCP Server 配置面板 ===== */
.mcp-config-section { padding: 20px; border-radius: var(--radius-lg); background: var(--surface); box-shadow: var(--shadow-card); }
.mcp-config-title { font-size: 15px; font-weight: 700; margin-bottom: 6px; }
.mcp-config-hint { font-size: 12px; color: var(--text-sub); margin-bottom: 16px; }
.mcp-config-form { display: flex; flex-direction: column; gap: 12px; }
.form-row { display: flex; align-items: flex-start; gap: 12px; }
.form-row-full { flex-direction: column; }
.form-label { font-size: 13px; font-weight: 600; min-width: 80px; padding-top: 8px; color: var(--text-primary); }
.form-input { flex: 1; padding: 8px 12px; border: 1.5px solid var(--border); border-radius: var(--radius-md); font-size: 14px; background: var(--input-bg, #fff); color: var(--text-primary); outline: none; transition: border-color .15s; }
.form-input:focus { border-color: var(--primary); }
.form-textarea { width: 100%; min-height: 220px; padding: 12px; border: 1.5px solid var(--border); border-radius: var(--radius-md); font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; font-size: 13px; line-height: 1.6; background: var(--input-bg, #fff); color: var(--text-primary); outline: none; resize: vertical; transition: border-color .15s; box-sizing: border-box; }
.form-textarea:focus { border-color: var(--primary); }
.form-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.mcp-config-result { margin-top: 4px; padding: 10px 14px; border-radius: var(--radius-md); font-size: 13.5px; font-weight: 600; }
.result-ok { background: rgba(47, 191, 113, .10); border: 1px solid rgba(47, 191, 113, .28); color: #1a7a42; }
.result-fail { background: rgba(240, 83, 77, .10); border: 1px solid rgba(240, 83, 77, .28); color: #c0392b; }
</style>
