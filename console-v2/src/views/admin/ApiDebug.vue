<template>
  <div>
    <div class="page-head">
      <div>
        <h1>API <span style="color:var(--primary)">调试</span></h1>
        <p class="sub">迁移自 /cc/ API 调试页：142 接口目录，任意原始请求</p>
      </div>
      <div class="head-actions">
        <input v-model="search" placeholder="搜索接口路径/说明…" style="border:1.5px solid var(--border);border-radius:999px;padding:8px 16px;font-size:13px;outline:none;width:220px" />
      </div>
    </div>

    <div style="display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap">
      <!-- 左：目录树 -->
      <div style="flex:0 0 300px;max-height:560px;overflow:auto">
        <div v-for="(group, gk) in filteredCatalog" :key="gk" style="margin-bottom:14px">
          <div style="font-size:12px;font-weight:700;color:var(--text-sub);margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px">{{ group.zh }} ({{ group.apis.length }})</div>
          <div v-for="a in group.apis" :key="a.m" class="api-item" :class="{ active: selected && selected.m === a.m }" @click="select(a)">
            <span class="method-badge" :class="a.h.toLowerCase()">{{ a.h }}</span>
            <div style="flex:1;min-width:0">
              <div style="font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ a.p }}</div>
              <div style="font-size:11px;color:var(--text-sub)">{{ a.s }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右：请求面板 -->
      <div style="flex:1;min-width:320px">
        <DataTable :title="selected ? selected.h + ' ' + selected.p : '请求面板'">
          <template v-if="selected">
            <div class="form-row"><label>路径参数（${} 占位，逗号分隔值）</label><input v-model="pathArgs" :placeholder="selected.pa" /></div>
            <div class="form-row"><label>Query / Body（JSON，可选）</label><textarea v-model="reqBody" rows="4" placeholder='{"page":1,"limit":10}'></textarea></div>
            <div style="display:flex;gap:10px;align-items:center">
              <button class="btn btn-primary" :disabled="sending" @click="send">{{ sending ? '请求中…' : '发送请求' }}</button>
              <span v-if="statusText" style="font-size:13px;font-weight:600" :style="{color: statusOk ? '#16a34a' : '#dc2626'}">{{ statusText }}</span>
            </div>
            <pre v-if="respText" class="resp-box">{{ respText }}</pre>
          </template>
          <div v-else class="empty-state"><div class="empty-icon">🧪</div><strong>左侧选择接口开始调试</strong></div>
        </DataTable>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, ref } from 'vue'
import DataTable from '../../components/DataTable.vue'
import API_CATALOG from '../../lib/apiCatalog'
import { api } from '../../lib/api'

const toast = inject('toast')
const search = ref('')
const selected = ref(null)
const pathArgs = ref('')
const reqBody = ref('')
const respText = ref('')
const statusText = ref('')
const statusOk = ref(false)
const sending = ref(false)

const filteredCatalog = computed(() => {
  if (!search.value) return API_CATALOG
  const q = search.value.toLowerCase()
  const out = {}
  for (const [k, g] of Object.entries(API_CATALOG)) {
    const apis = g.apis.filter(a => a.p.toLowerCase().includes(q) || a.s.toLowerCase().includes(q) || a.m.toLowerCase().includes(q))
    if (apis.length) out[k] = { ...g, apis }
  }
  return out
})

function select(a) {
  selected.value = a
  respText.value = ''
  statusText.value = ''
  const phCount = (a.p.match(/\$\{/g) || []).length
  pathArgs.value = phCount ? '' : ''
  reqBody.value = ''
}

async function send() {
  if (!selected.value) return
  sending.value = true
  respText.value = ''
  try {
    let path = selected.value.p
    const args = pathArgs.value.split(',').map(s => s.trim()).filter(Boolean)
    args.forEach(arg => { path = path.replace(/\$\{[^}]+\}/, encodeURIComponent(arg)) })
    const method = selected.value.h.toLowerCase()
    let params
    if (reqBody.value.trim()) {
      try { params = JSON.parse(reqBody.value) }
      catch { toast('Body 不是合法 JSON', 'error'); sending.value = false; return }
    }
    const fn = method === 'get' ? api.get : method === 'post' ? api.post : method === 'put' ? api.put : api.del
    const res = await fn(path, params)
    statusText.value = '✓ code=' + (res.code ?? 0)
    statusOk.value = res.code === 0
    respText.value = JSON.stringify(res, null, 2).slice(0, 8000)
  } catch (e) {
    statusText.value = '✗ ' + (e.code || '') + ' ' + (e.msg || '请求失败')
    statusOk.value = false
    respText.value = JSON.stringify(e, null, 2)
  } finally { sending.value = false }
}
</script>

<style scoped>
.api-item { display: flex; gap: 8px; align-items: center; padding: 8px 10px; border-radius: 10px; cursor: pointer; }
.api-item:hover { background: var(--bg-soft); }
.api-item.active { background: #EAF2FF; }
.method-badge { font-size: 10px; font-weight: 800; padding: 2px 6px; border-radius: 6px; flex-shrink: 0; }
.method-badge.get { background: #DBEAFE; color: #1D4ED8; }
.method-badge.post { background: #DCFCE7; color: #15803D; }
.method-badge.put { background: #FEF3C7; color: #B45309; }
.method-badge.delete { background: #FEE2E2; color: #B91C1C; }
.form-row { margin-bottom: 14px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row textarea { border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px; font-size: 13px; outline: none; font-family: ui-monospace, monospace; }
.form-row textarea:focus { border-color: var(--primary); }
.resp-box { background: #0F172A; color: #7DD3FC; border-radius: 12px; padding: 14px; font-size: 12px; overflow: auto; max-height: 320px; font-family: ui-monospace, monospace; }
</style>
