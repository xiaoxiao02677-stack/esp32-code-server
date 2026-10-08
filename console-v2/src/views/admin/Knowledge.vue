<template>
  <div>
    <div class="page-head">
      <div>
        <h1>知识库 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">文档、分块与向量化状态</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="openCreate">＋ 新建知识库</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新列表</button>
      </div>
    </div>

    <div class="hero-row">
      <div class="hero-blob" style="min-height:170px">
        <div>
          <div class="en">KNOWLEDGE / RAG</div>
          <h2>知识库</h2>
          <p>上传文档，让智能体更懂你的业务</p>
        </div>
        <div class="blob-3d">📚</div>
      </div>
      <div class="stats-grid">
        <StatCard icon="📚" label="知识库" :value="datasets.length" />
        <StatCard icon="📄" label="本页文档" :value="docTotal" note="当前页" />
        <StatCard icon="🧱" label="分块" :value="chunkTotal" />
        <StatCard icon="🔢" label="文档总数" :value="total" note="全库" />
      </div>
    </div>

    <DataTable title="知识库清单" :total="datasets.length" :page="1" :pages="Math.max(1, Math.ceil(datasets.length / 4))">
      <table class="data-table">
        <thead>
          <tr><th>知识库</th><th>文档数</th><th>分块数</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="k in datasets" :key="k.id">
            <td>
              <div class="cell-main">{{ k.name }}</div>
              <div class="cell-sub">{{ k.description || '暂无描述' }}</div>
            </td>
            <td>{{ k.documentCount ?? '—' }}</td>
            <td>{{ k.chunkCount ?? '—' }}</td>
            <td>
              <span class="badge" :class="k.status === 1 ? 'badge-green' : 'badge-orange'">
                <span class="dot"></span>{{ k.status === 1 ? '已就绪' : '构建中' }}
              </span>
            </td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="viewDocs(k)">文档</button>
                <button class="link-btn" @click="retrievalTest(k)">检索测试</button>
                <button class="link-btn danger" @click="remove(k)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="datasets.length === 0" class="empty-state">
        <div class="empty-icon">📚</div>
        <strong>暂无知识库</strong>
        <p>点击「新建知识库」开始</p>
      </div>
    </DataTable>

    <!-- 新建知识库弹窗 -->
    <div v-if="creator.show" class="modal-mask" @click.self="creator.show = false">
      <div class="modal">
        <h3>新建知识库</h3>
        <div class="form-row"><label>名称</label><input v-model="creator.name" placeholder="例如：产品手册" /></div>
        <div class="form-row"><label>描述</label><textarea v-model="creator.description" rows="2" placeholder="知识库用途"></textarea></div>
        <div class="form-row"><label>RAG 模型</label>
          <select v-model="creator.ragModelId">
            <option value="">默认模型</option>
            <option v-for="m in ragModels" :key="m.id" :value="m.id">{{ m.name || m.modelName || m.id }}</option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="creator.show = false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="save">{{ saving ? '创建中…' : '创建' }}</button>
        </div>
      </div>
    </div>

    <!-- 文档列表弹窗 -->
    <div v-if="docs.show" class="modal-mask" @click.self="docs.show = false">
      <div class="modal" style="width:min(560px,94vw)">
        <h3>文档 — {{ docs.name }}</h3>
        <p style="color:var(--text-sub);font-size:12.5px;margin:6px 0 12px">共 {{ docs.total }} 份文档</p>
        <table class="data-table">
          <thead><tr><th>文档名</th><th>大小</th><th>状态</th></tr></thead>
          <tbody>
            <tr v-for="d in docs.list" :key="d.id || d.documentId">
              <td>{{ d.name || d.fileName || d.documentId }}</td>
              <td style="color:var(--text-sub)">{{ d.size ? (d.size / 1024).toFixed(1) + ' KB' : '—' }}</td>
              <td>
                <span class="badge" :class="d.status === 1 ? 'badge-green' : 'badge-orange'">
                  <span class="dot"></span>{{ d.status === 1 ? '已解析' : '处理中' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="docs.list.length === 0" class="empty-state" style="padding:24px 0">
          <strong>暂无文档</strong>
          <p>上传文档请在原控制台完成（接口 POST /datasets/{id}/documents 已契约）</p>
        </div>
        <div class="modal-actions" style="margin-top:14px">
          <button class="btn btn-ghost" @click="docs.show = false">关闭</button>
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

const datasets = ref([])
const total = ref(0)
const loading = ref(false)
const saving = ref(false)
const ragModels = ref([])
const creator = reactive({ show: false, name: '', description: '', ragModelId: '' })
const docs = reactive({ show: false, name: '', list: [], total: 0 })

const docTotal = computed(() => datasets.value.reduce((s, k) => s + (k.documentCount || 0), 0))
const chunkTotal = computed(() => datasets.value.reduce((s, k) => s + (k.chunkCount || 0), 0))

async function load() {
  loading.value = true
  try {
    const res = await adminApi.datasetPage({ page: 1, limit: 100 })
    const list = Array.isArray(res.data) ? res.data : (res.data?.list || [])
    datasets.value = list.map(k => ({
      id: k.id || k.datasetId,
      name: k.name || '未命名知识库',
      description: k.description || '',
      documentCount: k.documentCount,
      chunkCount: k.chunkCount,
      status: k.status ?? 1
    }))
    total.value = list.length
  } catch (e) {
    toast(e.msg || '加载失败', 'error')
  } finally {
    loading.value = false
  }
}

async function loadRagModels() {
  try {
    const res = await adminApi.ragModels()
    ragModels.value = Array.isArray(res.data) ? res.data : (res.data?.list || [])
  } catch { ragModels.value = [] }
}

function openCreate() {
  Object.assign(creator, { show: true, name: '', description: '', ragModelId: '' })
}
async function save() {
  if (!creator.name) { toast('请填写知识库名称', 'error'); return }
  saving.value = true
  try {
    await adminApi.createDataset({ name: creator.name, description: creator.description, ragModelId: creator.ragModelId || undefined })
    toast('知识库创建成功')
    creator.show = false
    load()
  } catch (e) {
    toast(e.msg || '创建失败', 'error')
  } finally {
    saving.value = false
  }
}
async function viewDocs(k) {
  docs.show = true
  docs.name = k.name
  docs.list = []
  try {
    const res = await adminApi.datasetDocs(k.id, { page: 1, limit: 20 })
    const data = res.data || {}
    docs.list = data.list || []
    docs.total = data.total ?? docs.list.length
  } catch (e) {
    toast(e.msg || '文档加载失败', 'error')
  }
}
function retrievalTest(k) {
  toast(`「${k.name}」检索测试需关联智能体，请在原控制台执行`, 'info')
}
function remove(k) {
  askConfirm({
    title: '删除知识库', message: `确定删除「${k.name}」及其全部文档吗？此操作不可恢复。`, danger: true,
    onOk: async () => {
      try {
        await adminApi.deleteDataset(k.id)
        toast('知识库已删除')
        load()
      } catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}

onMounted(() => { load(); loadRagModels() })
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
