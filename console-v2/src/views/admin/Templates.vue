<template>
  <div>
    <div class="page-head">
      <div>
        <h1>模板 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">智能体模板：人设、音色与能力配置</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="openCreate">＋ 新建模板</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新模板</button>
      </div>
    </div>

    <div class="hero-row">
      <div class="hero-blob" style="min-height:170px">
        <div>
          <div class="en">TEMPLATES / PRESETS</div>
          <h2>模板库</h2>
          <p>一键套用，快速创建智能体</p>
        </div>
        <div class="blob-3d">🧩</div>
      </div>
      <div class="stats-grid">
        <StatCard icon="🧩" label="模板" :value="templates.length" />
        <StatCard icon="✅" label="已配置" :value="templates.length" />
        <StatCard icon="🏷" label="分类" value="4" note="角色/教学/陪伴/工具" />
        <StatCard icon="🔥" label="最热门" value="英语老师" note="历史模板" />
      </div>
    </div>

    <DataTable title="模板清单" :total="templates.length" :page="1" :pages="Math.max(1, Math.ceil(templates.length / 4))">
      <template #actions>
        <input v-model="keyword" placeholder="搜索模板" style="border:1.5px solid var(--border);border-radius:10px;padding:6px 12px;font-size:12.5px;outline:none" />
      </template>
      <table class="data-table">
        <thead>
          <tr><th>模板信息</th><th>配置标签</th><th>排序</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="(t, i) in filtered" :key="t.id">
            <td>
              <div class="cell-main">{{ t.name }}</div>
              <div class="cell-sub">{{ t.author }} · 智能体模板</div>
            </td>
            <td>
              <div style="display:flex;gap:6px;flex-wrap:wrap">
                <span class="badge badge-blue">{{ t.langCode === 'zh' ? '中文' : '多语言' }}</span>
                <span v-if="t.systemPrompt" class="badge badge-blue">人设</span>
              </div>
            </td>
            <td>{{ i + 1 }}</td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="openEdit(t)">编辑</button>
                <button class="link-btn" @click="preview(t)">预览</button>
                <button class="link-btn danger" @click="remove(t)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="templates.length === 0" class="empty-state">
        <div class="empty-icon">🧩</div>
        <strong>暂无模板</strong>
        <p>点击「新建模板」创建第一个智能体模板</p>
      </div>
    </DataTable>

    <!-- 新建/编辑弹窗 -->
    <div v-if="editor.show" class="modal-mask" @click.self="editor.show = false">
      <div class="modal">
        <h3>{{ editor.id ? '编辑模板' : '新建模板' }}</h3>
        <div class="form-row"><label>模板名称</label><input v-model="editor.agentName" placeholder="例如：英语老师" /></div>
        <div class="form-row"><label>角色提示词</label><textarea v-model="editor.systemPrompt" rows="4" placeholder="描述智能体的性格与说话风格"></textarea></div>
        <div class="form-row"><label>语言</label>
          <select v-model="editor.langCode"><option value="zh">中文</option><option value="en">英文</option></select>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="editor.show = false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>

    <!-- 预览弹窗 -->
    <div v-if="previewing" class="modal-mask" @click.self="previewing = null">
      <div class="modal">
        <h3>模板预览 — {{ previewing.name }}</h3>
        <p style="color:var(--text-sub);font-size:13px;margin-bottom:10px">{{ previewing.author }} · lang={{ previewing.langCode }}</p>
        <div style="background:#F8FAFE;border-radius:12px;padding:16px;font-size:13.5px;line-height:1.7;max-height:280px;overflow:auto;white-space:pre-wrap">{{ previewing.systemPrompt || '（无提示词）' }}</div>
        <div class="modal-actions" style="margin-top:16px">
          <button class="btn btn-ghost" @click="previewing = null">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, reactive, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')

const templates = ref([])
const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
const previewing = ref(null)
const editor = reactive({ show: false, id: null, agentName: '', systemPrompt: '', langCode: 'zh' })

const filtered = computed(() => {
  if (!keyword.value) return templates.value
  return templates.value.filter(t => t.name.includes(keyword.value))
})

async function load() {
  loading.value = true
  try {
    const res = await adminApi.templateList()
    const list = Array.isArray(res.data) ? res.data : (res.data?.list || [])
    templates.value = list.map(t => ({
      id: t.id,
      name: t.agentName || t.name || '未命名模板',
      author: t.creatorName || '社区',
      langCode: t.langCode || 'zh',
      systemPrompt: t.systemPrompt || ''
    }))
  } catch (e) {
    toast(e.msg || '加载失败', 'error')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(editor, { show: true, id: null, agentName: '', systemPrompt: '', langCode: 'zh' })
}
function openEdit(t) {
  Object.assign(editor, { show: true, id: t.id, agentName: t.name, systemPrompt: t.systemPrompt, langCode: t.langCode || 'zh' })
}
async function save() {
  if (!editor.agentName) { toast('请填写模板名称', 'error'); return }
  saving.value = true
  try {
    const body = { agentName: editor.agentName, systemPrompt: editor.systemPrompt, langCode: editor.langCode }
    if (editor.id) {
      await adminApi.updateTemplate({ ...body, id: editor.id })
      toast('模板已更新')
    } else {
      await adminApi.createTemplate(body)
      toast('模板创建成功')
    }
    editor.show = false
    load()
  } catch (e) {
    toast(e.msg || '保存失败', 'error')
  } finally {
    saving.value = false
  }
}
function preview(t) { previewing.value = t }
function remove(t) {
  askConfirm({
    title: '删除模板', message: `确定删除模板「${t.name}」吗？此操作不可恢复。`, danger: true,
    onOk: async () => {
      try {
        await adminApi.deleteTemplate(t.id)
        toast('模板已删除')
        load()
      } catch (e) {
        toast(e.msg || '删除失败', 'error')
      }
    }
  })
}

onMounted(load)
</script>

<style scoped>
.form-row { margin-bottom: 14px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row textarea, .form-row select {
  border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px;
  font-size: 14px; outline: none; font-family: var(--font); transition: border .15s;
}
.form-row input:focus, .form-row textarea:focus, .form-row select:focus { border-color: var(--primary); }
</style>
