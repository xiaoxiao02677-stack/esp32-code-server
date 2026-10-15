<template>
  <div>
    <div class="page-head">
      <div>
        <h1>替换词 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">契约对齐 /cc/：fileName + content（词条内容）增改删</p>
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
        <thead><tr><th>文件名</th><th>内容预览</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="f in files" :key="f.id">
            <td><div class="cell-main">{{ f.fileName }}</div></td>
            <td style="font-size:12px">{{ (f.content || '').slice(0, 60) }}{{ (f.content || '').length > 60 ? '…' : '' }}</td>
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

    <!-- 编辑弹窗（契约：payload = {fileName, content}） -->
    <div v-if="editor.show" class="modal-mask" @click.self="editor.show = false">
      <div class="modal">
        <h3>{{ editor.id ? '编辑' : '新建' }}替换词文件</h3>
        <div class="form-row"><label>文件名</label><input v-model="editor.fileName" placeholder="如：常见错别字" /></div>
        <div class="form-row"><label>内容（每行一条替换规则）</label>
          <textarea v-model="editor.content" rows="8" placeholder="错误词=正确词&#10;或用具体格式"></textarea>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="editor.show = false">取消</button>
          <button class="btn btn-primary" :disabled="saving || !editor.fileName" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
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
const editor = reactive({ show: false, id: '', fileName: '', content: '' })

async function load() {
  loading.value = true
  try {
    const res = await adminApi.correctWordList({ page: 1, limit: 100 })
    files.value = res.data?.list || []
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

function openCreate() { Object.assign(editor, { show: true, id: '', fileName: '', content: '' }) }
function openEdit(f) { Object.assign(editor, { show: true, id: f.id, fileName: f.fileName, content: f.content || '' }) }

async function save() {
  if (!editor.fileName) { toast('请填写文件名', 'error'); return }
  saving.value = true
  try {
    if (editor.id) await adminApi.updateCorrectWord(editor.id, editor.fileName, editor.content)
    else await adminApi.createCorrectWord(editor.fileName, editor.content)
    toast('已保存'); editor.show = false; load()
  } catch (e) { toast(e.msg || '保存失败', 'error') }
  finally { saving.value = false }
}

function remove(f) {
  askConfirm({
    title: '删除替换词文件', message: `确定删除替换词文件「${f.fileName}」吗？`, danger: true,
    onOk: async () => {
      try { await adminApi.deleteCorrectWord(f.id); toast('已删除'); load() }
      catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}

onMounted(load)
</script>

<style scoped>
.form-row { margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row textarea { border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px; font-size: 14px; outline: none; font-family: var(--font); }
.form-row input:focus, .form-row textarea:focus { border-color: var(--primary); }
</style>
