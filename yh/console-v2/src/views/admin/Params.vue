<template>
  <div>
    <div class="page-head">
      <div>
        <h1>系统 <span style="color:var(--primary)">参数</span></h1>
        <p class="sub">查看与调整系统运行参数</p>
      </div>
      <div class="head-actions">
        <input v-model="paramFilter" placeholder="搜索参数编码/名称…" class="filter-input" style="width:220px;font-size:13px;padding:8px 16px" />
        <button class="btn btn-primary" @click="openCreate">＋ 新增参数</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="sliders" label="参数总数" :value="params.length" />
      <StatCard icon="✏️" label="本次修改" :value="dirtyCount" note="未保存" />
    </div>

    <DataTable title="参数列表" :loading="loading">
      <table class="data-table">
        <thead><tr><th>参数编码</th><th>名称</th><th>值</th><th>类型</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="p in filteredParams" :key="p.id">
            <td style="font-size:12px">{{ p.paramCode }}</td>
            <td>{{ p.paramName || p.remark || '—' }}</td>
            <td>
              <span v-if="editingId !== p.id">{{ p.paramValue }}</span>
              <input v-else v-model="p._newValue" style="width:140px;border:1.5px solid var(--primary);border-radius:8px;padding:6px 10px;font-size:13px" @keyup.enter="saveParam(p)" @keydown.esc.prevent="cancelEdit" />
            </td>
            <td><span class="type-tag">{{ p.type || 'string' }}</span></td>
            <td>
              <div class="row-actions">
                <template v-if="editingId !== p.id">
                  <button class="link-btn" @click="startEdit(p)">编辑</button>
                </template>
                <template v-else>
                  <button class="link-btn" @click="saveParam(p)">保存</button>
                  <button class="link-btn" @click="cancelEdit">取消</button>
                </template>
                <button class="link-btn danger" @click="removeParam(p)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="params.length === 0" class="empty-state"><div class="empty-icon"><YhIcon name="sliders" /></div><strong>暂无参数</strong></div>
    </DataTable>

    <!-- 新增参数（契约：POST /admin/params，api.js adminApi.createParam） -->
    <div v-if="creator.show" class="modal-mask" @click.self="creator.show = false">
      <div class="modal">
        <h3>新增参数</h3>
        <div class="form-row"><label>参数编码 *</label><input v-model="creator.paramCode" placeholder="如 system.name" /></div>
        <div class="form-row"><label>名称</label><input v-model="creator.paramName" placeholder="参数显示名称" /></div>
        <div class="form-row"><label>值</label><input v-model="creator.paramValue" placeholder="参数值" /></div>
        <div class="form-row"><label>备注</label><input v-model="creator.remark" placeholder="选填" /></div>
        <div class="form-row">
          <label>类型</label>
          <select v-model="creator.type">
            <option value="string">string</option>
            <option value="number">number</option>
            <option value="boolean">boolean</option>
            <option value="json">json</option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="creator.show = false">取消</button>
          <button class="btn btn-primary" :disabled="creating || !creator.paramCode.trim()" @click="createParam">提交</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import YhIcon from '../../components/YhIcon.vue'
import { computed, inject, onMounted, reactive, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')
const params = ref([])
const loading = ref(false)
const editingId = ref(null)
const paramFilter = ref('')
const creating = ref(false)
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
    toast(`「${p.paramCode}」已保存。部分参数需重启服务后生效，可在「服务器」页一键重启`)
  } catch (e) {
    p._dirty = true
    toast(e.msg || '保存失败', 'error')
  }
}

// 新增参数：打开弹窗（类型默认 string）
const creator = reactive({ show: false, paramCode: '', paramName: '', paramValue: '', remark: '', type: 'string' })

function openCreate() {
  Object.assign(creator, { show: true, paramCode: '', paramName: '', paramValue: '', remark: '', type: 'string' })
  toast('新增参数：请填写编码与值后提交')
}

async function createParam() {
  if (creating.value) return
  creating.value = true
  try {
    await adminApi.createParam({
      paramCode: creator.paramCode.trim(),
      paramName: creator.paramName.trim(),
      paramValue: creator.paramValue,
      remark: creator.remark.trim(),
      type: creator.type
    })
    creator.show = false
    toast(`「${creator.paramCode.trim()}」已新增。部分参数需重启服务后生效，可在「服务器」页一键重启`)
    await load()
  } catch (e) {
    toast(e.msg || '新增失败', 'error')
  } finally {
    creating.value = false
  }
}

// 删除参数：确认后 DELETE /admin/params/{id}
function removeParam(p) {
  askConfirm({
    title: '删除参数',
    message: `确定删除参数「${p.paramCode}」吗？删除后不可恢复。`,
    danger: true,
    onOk: async () => {
      try {
        await adminApi.deleteParam(p.id)
        if (editingId.value === p.id) editingId.value = null
        toast(`「${p.paramCode}」已删除`)
        await load()
      } catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}

onMounted(load)
</script>

<style scoped>
.form-row { margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row select {
  border: 1.5px solid var(--border);
  border-radius: 12px;
  padding: 10px 14px;
  font-size: 14px;
  outline: none;
  background: var(--surface, #fff);
  color: var(--text);
}
.form-row input:focus, .form-row select:focus { border-color: var(--primary); }
.type-tag {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 999px;
  background: var(--primary-soft);
  color: var(--primary);
  font-weight: 600;
}
</style>
