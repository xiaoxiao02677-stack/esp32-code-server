<template>
  <div>
    <div class="page-head">
      <div>
        <h1>模型 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">迁移自 /cc/ 模型页：分类型列表 / 启停 / 连通测试</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="🧩" label="模型总数" :value="models.length" :note="activeType" />
      <StatCard icon="✅" label="启用中" :value="models.filter(m => m.enable).length" />
      <StatCard icon="🔌" label="连通测试" :value="lastTest ? '完成' : '—'" :note="lastTest" />
    </div>

    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px">
      <div v-for="t in TYPES" :key="t" class="chip" :class="{ active: activeType === t }" @click="pickType(t)">{{ t }}</div>
    </div>

    <DataTable title="模型列表">
      <table class="data-table">
        <thead><tr><th>模型</th><th>供应商</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="m in models" :key="m.id">
            <td><div class="cell-main">{{ m.modelName || m.id }}</div><div class="cell-sub">{{ m.id }}</div></td>
            <td>{{ m.providerCode || m.provider || '—' }}</td>
            <td>
              <span class="badge" :class="m.enable ? 'badge-green' : 'badge-gray'">
                <span class="dot"></span>{{ m.enable ? '启用' : '停用' }}
              </span>
            </td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="test(m)">测试</button>
                <button class="link-btn" @click="toggle(m)">{{ m.enable ? '停用' : '启用' }}</button>
                <button class="link-btn danger" @click="remove(m)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="models.length === 0" class="empty-state"><div class="empty-icon">🧩</div><strong>此类型暂无模型</strong></div>
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
const TYPES = ['LLM', 'ASR', 'TTS', 'Memory', 'VAD', 'Intent']
const models = ref([])
const activeType = ref('LLM')
const loading = ref(false)
const lastTest = ref('')

async function load() {
  loading.value = true
  try {
    const res = await adminApi.modelList(activeType.value)
    const data = res.data || {}
    models.value = (data.list || data || []).map(m => ({
      id: m.modelId || m.id,
      modelName: m.modelName || m.name || m.modelId,
      providerCode: m.providerCode || m.provider,
      enable: m.enable === undefined ? m.status === 1 : !!m.enable
    }))
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

function pickType(t) { activeType.value = t; load() }

async function test(m) {
  lastTest.value = m.modelName
  try {
    const res = await adminApi.modelTest(m.id, activeType.value)
    toast(`「${m.modelName}」连通: ${res.data?.message || res.msg || 'OK'}`)
  } catch (e) { toast(`「${m.modelName}」测试失败: ${e.msg || ''}`, 'error') }
}

async function toggle(m) {
  const next = m.enable ? 0 : 1
  try {
    await adminApi.enableModel(m.id, next)
    toast(`「${m.modelName}」已${next ? '启用' : '停用'}`)
    load()
  } catch (e) { toast(e.msg || '操作失败', 'error') }
}

function remove(m) {
  askConfirm({
    title: '删除模型', message: `确定删除「${m.modelName}」吗？`, danger: true,
    onOk: async () => {
      try { await adminApi.deleteModel(m.id); toast('已删除'); load() }
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
