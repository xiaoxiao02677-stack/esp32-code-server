<template>
  <div>
    <div class="page-head">
      <div>
        <h1>系统 <span style="color:var(--primary)">参数</span></h1>
        <p class="sub">迁移自 /cc/ 系统参数页：分页列表 / 编辑保存</p>
      </div>
      <div class="head-actions">
        <input v-model="paramFilter" placeholder="搜索参数编码/名称…" style="border:1.5px solid var(--border);border-radius:999px;padding:8px 16px;font-size:13px;outline:none;width:220px" />
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="⚙️" label="参数总数" :value="params.length" />
      <StatCard icon="✏️" label="本次修改" :value="dirtyCount" note="未保存" />
    </div>

    <DataTable title="参数列表">
      <table class="data-table">
        <thead><tr><th>参数编码</th><th>名称</th><th>值</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="p in filteredParams" :key="p.id">
            <td style="font-size:12px">{{ p.paramCode }}</td>
            <td>{{ p.paramName || p.remark || '—' }}</td>
            <td>
              <span v-if="editingId !== p.id">{{ p.paramValue }}</span>
              <input v-else v-model="p._newValue" style="width:140px;border:1.5px solid var(--primary);border-radius:8px;padding:6px 10px;font-size:13px" />
            </td>
            <td>
              <div class="row-actions">
                <template v-if="editingId !== p.id">
                  <button class="link-btn" @click="startEdit(p)">编辑</button>
                </template>
                <template v-else>
                  <button class="link-btn" @click="saveParam(p)">保存</button>
                  <button class="link-btn" @click="cancelEdit">取消</button>
                </template>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="params.length === 0" class="empty-state"><div class="empty-icon">⚙️</div><strong>暂无参数</strong></div>
    </DataTable>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const params = ref([])
const loading = ref(false)
const editingId = ref(null)
const paramFilter = ref('')
const dirtyCount = computed(() => params.value.filter(p => p._dirty).length)

// A10：参数编码/名称/备注过滤（参照原控制台 App.vue:1178-1182 filteredParams）
const filteredParams = computed(() => {
  const kw = paramFilter.value.trim().toLowerCase()
  if (!kw) return params.value
  return params.value.filter(p =>
    (p.paramCode || '').toLowerCase().includes(kw) ||
    (p.paramName || '').toLowerCase().includes(kw) ||
    (p.remark || '').toLowerCase().includes(kw))
})

async function load() {
  loading.value = true
  try {
    const res = await adminApi.paramPage({ page: 1, limit: 100 })
    const data = res.data || {}
    params.value = (data.list || []).map(p => ({ ...p, _newValue: p.paramValue, _dirty: false }))
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

function startEdit(p) { editingId.value = p.id }
function cancelEdit() { editingId.value = null; params.value.forEach(p => { p._newValue = p.paramValue; p._dirty = false }) }

async function saveParam(p) {
  if (p._newValue === p.paramValue) { editingId.value = null; p._dirty = false; return }
  try {
    await adminApi.updateParam({ id: p.id, paramCode: p.paramCode, paramValue: p._newValue, paramName: p.paramName, type: p.type, remark: p.remark })
    p.paramValue = p._newValue; p._dirty = false; editingId.value = null
    toast(`「${p.paramCode}」已保存`)
  } catch (e) {
    p._dirty = true
    toast(e.msg || '保存失败', 'error')
  }
}

onMounted(load)
</script>
