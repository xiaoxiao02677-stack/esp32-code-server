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

    <!-- 检索测试弹窗 -->
    <div v-if="rt.show" class="modal-mask" @click.self="rt.show = false">
      <div class="modal rt-modal">
        <h3>检索测试 — {{ rt.name }}</h3>
        <p class="rt-tip">输入查询文本，验证该知识库的向量召回效果</p>
        <div class="rt-input-row">
          <input
            v-model="rt.query"
            placeholder="输入查询文本，回车或点击「测试」"
            :disabled="rt.loading"
            @keyup.enter="runRetrieval"
          />
          <button class="btn btn-primary" :disabled="rt.loading" @click="runRetrieval">
            {{ rt.loading ? '测试中…' : '测试' }}
          </button>
        </div>
        <div v-if="rt.meta" class="rt-meta">
          召回 <strong>{{ rt.meta.count }}</strong> 条 · 耗时 <strong>{{ rt.meta.cost }}</strong> ms
          <span v-if="rt.byDistance">（distance 越小越相关）</span>
        </div>
        <div class="rt-results">
          <div v-if="rt.loading" class="rt-loading">检索中，请稍候…</div>
          <template v-else-if="rt.done">
            <div v-if="rt.results.length === 0" class="rt-empty">
              <strong>未召回任何内容</strong>
              <p>可尝试更换查询文本，或确认知识库已完成文档解析</p>
            </div>
            <div v-for="(item, i) in rt.results" :key="i" class="rt-item">
              <div class="rt-item-head">
                <span class="rt-idx">#{{ i + 1 }}</span>
                <span v-if="item.scoreText" class="rt-score" :class="{ dist: item.byDistance }">
                  {{ item.byDistance ? 'distance' : '相似度' }} {{ item.scoreText }}
                </span>
              </div>
              <p class="rt-content">{{ item.expanded ? item.text : item.short }}</p>
              <button v-if="item.long" class="rt-toggle" @click="item.expanded = !item.expanded">
                {{ item.expanded ? '收起' : '展开全文' }}
              </button>
            </div>
          </template>
        </div>
        <div class="modal-actions" style="margin-top:14px">
          <button class="btn btn-ghost" @click="rt.show = false">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, reactive, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi, api } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')

const datasets = ref([])
const total = ref(0)
const loading = ref(false)
const saving = ref(false)
const ragModels = ref([])
const creator = reactive({ show: false, name: '', description: '', ragModelId: '' })
const docs = reactive({ show: false, name: '', list: [], total: 0 })
const rt = reactive({ show: false, datasetId: null, name: '', query: '', loading: false, done: false, results: [], meta: null, byDistance: false })

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
  Object.assign(rt, { show: true, datasetId: k.id, name: k.name, query: '', loading: false, done: false, results: [], meta: null, byDistance: false })
}
function extractScore(chunk) {
  const raw = chunk.score ?? chunk.similarity ?? chunk.distance
  if (raw === undefined || raw === null || raw === '' || isNaN(Number(raw))) return null
  return { value: Number(raw), byDistance: chunk.distance !== undefined && chunk.score === undefined && chunk.similarity === undefined }
}
function normalizeResults(data) {
  const list = Array.isArray(data) ? data : (data?.list || data?.chunks || data?.results || [])
  return list.map(c => {
    const text = String(c.content ?? c.text ?? c.chunk ?? '').trim()
    const score = extractScore(c)
    return {
      text,
      short: text.length > 200 ? text.slice(0, 200) + '…' : text,
      long: text.length > 200,
      expanded: false,
      scoreText: score ? score.value.toFixed(4) : '',
      byDistance: score?.byDistance || false
    }
  })
}
async function runRetrieval() {
  if (rt.loading) return
  const queryText = (rt.query || '').trim()
  if (!queryText) { toast('请输入查询文本', 'error'); return }
  rt.loading = true
  rt.done = false
  rt.meta = null
  const started = performance.now()
  try {
    // 后端契约（manager-api RetrievalDTO.TestReq）：JSON 对象，question 必填；
    // datasetIds 为空时 Controller 自动回填路径 datasetId；page/pageSize 后端有强管控默认值
    const res = await api.post(`/datasets/${rt.datasetId}/retrieval-test`, { question: queryText })
    rt.results = normalizeResults(res.data)
    rt.byDistance = rt.results.some(r => r.byDistance)
    rt.meta = { count: rt.results.length, cost: Math.max(1, Math.round(performance.now() - started)) }
    rt.done = true
  } catch (e) {
    toast(e.msg || '检索测试失败', 'error')
  } finally {
    rt.loading = false
  }
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

/* 检索测试弹窗 */
.rt-modal { width: min(620px, 94vw); }
.rt-tip { color: var(--text-sub); font-size: 12.5px; margin: 6px 0 12px; }
.rt-input-row { display: flex; gap: 10px; }
.rt-input-row input {
  flex: 1; border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px;
  font-size: 14px; outline: none; font-family: var(--font); transition: border .15s;
}
.rt-input-row input:focus { border-color: var(--primary); }
.rt-input-row input:disabled { background: #F5F7FA; cursor: not-allowed; }
.rt-meta { margin-top: 10px; font-size: 12.5px; color: var(--text-sub); }
.rt-meta strong { color: var(--primary); }
.rt-results { margin-top: 12px; max-height: min(46vh, 420px); overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
.rt-loading { text-align: center; color: var(--text-sub); font-size: 13px; padding: 18px 0; }
.rt-empty {
  text-align: center; padding: 26px 0 20px; color: var(--text-sub);
  border: 1.5px dashed var(--border); border-radius: 14px;
}
.rt-empty strong { display: block; color: var(--text); margin-bottom: 4px; }
.rt-empty p { font-size: 12.5px; margin: 0; }
.rt-item { border: 1.5px solid var(--border); border-radius: 14px; padding: 12px 14px; }
.rt-item-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.rt-idx { font-size: 12px; font-weight: 700; color: var(--text-sub); }
.rt-score { font-size: 12px; font-weight: 700; color: var(--primary); background: rgba(27,108,255,.08); padding: 2px 8px; border-radius: 999px; }
.rt-score.dist { color: #C77700; background: rgba(199,119,0,.1); }
.rt-content { margin: 0; font-size: 13.5px; line-height: 1.65; white-space: pre-wrap; word-break: break-word; }
.rt-toggle {
  border: none; background: none; padding: 0; margin-top: 4px; cursor: pointer;
  font-size: 12.5px; color: var(--primary); font-family: var(--font);
}
</style>
