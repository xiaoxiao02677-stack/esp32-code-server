<template>
  <div>
    <div class="page-head">
      <div>
        <h1>替换词 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">迁移自 /cc/ 替换词页：文件列表 / 增改删</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="openCreate">＋ 新建</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="🔤" label="替换词文件" :value="files.length" />
    </div>

    <DataTable title="文件列表">
      <table class="data-table">
        <thead><tr><th>名称</th><th>描述</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="f in files" :key="f.id">
            <td><div class="cell-main">{{ f.name || f.fileName }}</div></td>
            <td>{{ f.description || '—' }}</td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="openEdit(f)">编辑</button>
                <button class="link-btn danger" @click="remove(f)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="files.length === 0" class="empty-state"><div class="empty-icon">🔤</div><strong>暂无替换词文件</strong></div>
    </DataTable>

    <div v-if="editor.show" class="modal-mask" @click.self="editor.show = false">
      <div class="modal">
        <h3>{{ editor.id ? '编辑' : '新建' }}替换词文件</h3>
        <div class="form-row"><label>名称</label><input v-model="editor.name" /></div>
        <div class="form-row"><label>描述</label><input v-model="editor.description" /></div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="editor.show = false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { inject, onMounted, reactive, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')
const files = ref([])
const loading = ref(false)
const saving = ref(false)
const editor = reactive({ show: false, id: null, name: '', description: '' })

async function load() {
  loading.value = true
  try {
    const res = await adminApi.correctWordList({ page: 1, limit: 100 })
    const data = res.data || {}
    files.value = data.list || []
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

function openCreate() { Object.assign(editor, { show: true, id: null, name: '', description: '' }) }
function openEdit(f) { Object.assign(editor, { show: true, id: f.id, name: f.name || f.fileName, description: f.description || '' }) }

async function save() {
  if (!editor.name) { toast('请填写名称', 'error'); return }
  saving.value = true
  try {
    if (editor.id) await adminApi.updateCorrectWord(editor.id, { name: editor.name, description: editor.description })
    else await adminApi.createCorrectWord({ name: editor.name, description: editor.description })
    toast('已保存'); editor.show = false; load()
  } catch (e) { toast(e.msg || '保存失败', 'error') }
  finally { saving.value = false }
}

function remove(f) {
  askConfirm({
    title: '删除替换词文件', message: `确定删除「${f.name || f.fileName}」吗？`, danger: true,
    onOk: async () => {
      try { await adminApi.deleteCorrectWord(f.id); toast('已删除'); load() }
      catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}

onMounted(load)
</script>

<style scoped>
.form-row { margin-bottom: 14px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input { border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px; font-size: 14px; outline: none; }
.form-row input:focus { border-color: var(--primary); }
</style>
