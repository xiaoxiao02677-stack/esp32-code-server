<template>
  <div>
    <div class="page-head">
      <div>
        <h1>数据 <span style="color:var(--primary)">字典</span></h1>
        <p class="sub">维护平台字典的类型与数据项</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" :disabled="!activeType" @click="openCreate">＋ 新增字典项</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="book" label="字典类型" :value="types.length" />
      <StatCard icon="file" label="当前类型数据" :value="datas.length" :note="activeType" />
    </div>

    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px">
      <button type="button" v-for="t in types" :key="t.id" class="chip" :class="{ active: activeType === t.dictType }" @click="pickType(t)">
        {{ t.dictName || t.dictType }}
      </button>
    </div>

    <DataTable title="字典数据" :loading="loading">
      <table class="data-table">
        <thead><tr><th>标签</th><th>值</th><th>排序</th><th>备注</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="d in datas" :key="d.id ?? d.key">
            <td><div class="cell-main">{{ d.dictLabel }}</div></td>
            <td style="font-size:12px">{{ d.dictValue }}</td>
            <td>{{ d.sort ?? '—' }}</td>
            <td style="font-size:12px">{{ d.remark || '—' }}</td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="openEdit(d)">编辑</button>
                <button class="link-btn danger" @click="remove(d)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="activeType && datas.length === 0" class="empty-state"><strong>此类型暂无数据</strong></div>
      <div v-if="!activeType" class="empty-state"><div class="empty-icon"><YhIcon name="book" /></div><strong>先选择字典类型</strong></div>
    </DataTable>

    <!-- 编辑/新增（契约：有 id → POST /admin/dict/data/update；无 id → /save） -->
    <div v-if="editor.show" class="modal-mask" @click.self="editor.show = false">
      <div class="modal">
        <h3>{{ editor.id ? '编辑字典项' : '新增字典项' }}（{{ activeType }}）</h3>
        <div class="form-row"><label>标签</label><input v-model="editor.dictLabel" /></div>
        <div class="form-row"><label>值</label><input v-model="editor.dictValue" /></div>
        <div class="form-row"><label>排序</label><input v-model.number="editor.sort" type="number" /></div>
        <div class="form-row"><label>备注</label><input v-model="editor.remark" /></div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="editor.show = false">取消</button>
          <button class="btn btn-primary" :disabled="!editor.dictLabel || !editor.dictValue" @click="save">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import YhIcon from '../../components/YhIcon.vue'
import { inject, onMounted, reactive, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')
const types = ref([])
const datas = ref([])
const activeType = ref('')
const loading = ref(false)
const editor = reactive({ show: false, id: '', dictLabel: '', dictValue: '', sort: 0, remark: '' })

async function load() {
  loading.value = true
  try {
    const res = await adminApi.dictTypePage({ page: 1, limit: 100 })
    types.value = res.data?.list || []
    if (types.value.length && !activeType.value) pickType(types.value[0])
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

async function pickType(t) {
  activeType.value = t.dictType
  try {
    const res = await adminApi.dictData(t.dictType)
    // 契约：data 为 [{name,key}]（firmware 类型）或 [{dictLabel,dictValue,id,sort,remark}]
    datas.value = (res.data || []).map((d, i) => ({
      id: d.id ?? d.key ?? i,
      dictLabel: d.dictLabel ?? d.name ?? d.label,
      dictValue: d.dictValue ?? d.key ?? d.value,
      sort: d.sort ?? d.orderNum,
      remark: d.remark ?? d.description
    }))
  } catch (e) { toast(e.msg || '字典数据加载失败', 'error'); datas.value = [] }
}

function openCreate() {
  Object.assign(editor, { show: true, id: '', dictLabel: '', dictValue: '', sort: 0, remark: '' })
}
function openEdit(d) {
  Object.assign(editor, { show: true, id: d.id, dictLabel: d.dictLabel, dictValue: d.dictValue, sort: d.sort || 0, remark: d.remark || '' })
}

async function save() {
  try {
    // 契约：编辑走 update（带 id），新建走 save（自动带 dictType）
    const body = {
      id: editor.id || undefined,
      dictType: activeType.value,
      dictLabel: editor.dictLabel,
      dictValue: editor.dictValue,
      sort: editor.sort || 0,
      remark: editor.remark || ''
    }
    await adminApi.saveDictData(body)
    toast('已保存'); editor.show = false; pickType({ dictType: activeType.value })
  } catch (e) { toast(e.msg || '保存失败（可能需要超级管理员权限）', 'error') }
}

function remove(d) {
  askConfirm({
    title: '删除字典项', message: `确定删除字典项「${d.dictLabel}」吗？`, danger: true,
    onOk: async () => {
      try { await adminApi.deleteDictData([d.id]); toast('已删除'); pickType({ dictType: activeType.value }) }
      catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}

onMounted(load)
</script>

<style scoped>
/* .chip 已收敛到 global.css */

/* .chip 已收敛到 global.css */

.form-row { margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input { border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px; font-size: 14px; outline: none; }
.form-row input:focus { border-color: var(--primary); }
</style>
