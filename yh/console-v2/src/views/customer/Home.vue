<template>
  <div>
    <div class="page-head">
      <div>
        <h1>我的智能体</h1>
        <p class="sub">创建智能体、绑定设备、配置模型</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" :disabled="creating" @click="openCreateModal">{{ creating ? '创建中…' : '＋ 新增智能体' }}</button>
        <button class="btn btn-ghost" :disabled="loading" @click="load">{{ loading ? '加载中…' : '↻ 刷新列表' }}</button>
      </div>
    </div>

    <div class="hero-row">
      <div class="hero-blob">
        <div>
          <div class="en">INTELLIGENCE / CONNECTED</div>
          <h2>连接设备<br />也连接更聪明的服务</h2>
          <p>统一管理你的设备、智能体与音色</p>
        </div>
        <div class="blob-actions">
          <button class="btn btn-primary" @click="$router.push('/customer/devices')">管理设备</button>
          <button class="btn btn-ghost" @click="$router.push('/customer/voices')">查看音色</button>
        </div>
        <div class="blob-3d">🤖</div>
      </div>
      <div class="stats-grid">
        <StatCard icon="bot" label="智能体" :value="agents.length" note="已创建" />
        <StatCard icon="device" label="设备" :value="deviceCount" note="已绑定" />
        <StatCard icon="mic" label="音色" :value="voices" note="可用" />
        <StatCard icon="grid" label="可用模型" :value="llmModels.length" note="平台启用 + 自定义" />
      </div>
    </div>

    <DataTable title="智能体清单" hint="管理你的智能体配置" :total="agents.length" :page="1" :pages="1" :loading="loading">
      <template #actions>
        <button class="btn btn-ghost" style="padding:7px 16px;font-size:13px" @click="openCreateModal">新增</button>
      </template>
      <table class="data-table">
        <thead>
          <tr><th>智能体信息</th><th>绑定设备</th><th>最近连接</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="a in agents" :key="a.id">
            <td>
              <div class="cell-main">{{ a.name }}</div>
              <div class="cell-sub">{{ a.model }}</div>
            </td>
            <td>
              <span class="badge" :class="a.deviceCount ? 'badge-green' : 'badge-gray'">
                <span class="dot"></span>{{ a.deviceCount ? a.deviceCount + ' 台' : '未绑定' }}
              </span>
            </td>
            <td style="color:var(--text-sub)">{{ a.lastActive }}</td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="openEdit(a)">编辑</button>
                <button class="link-btn" @click="openBind(a)">绑定设备</button>
                <button class="link-btn" @click="$router.push('/customer/devices')">查看设备</button>
                <button class="link-btn danger" @click="remove(a)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    <div v-if="agents.length === 0" class="empty-state">
      <div class="empty-icon"><YhIcon name="bot" /></div>
      <strong>暂无智能体</strong>
      <p>点击右上角「新增智能体」创建第一个智能体</p>
      <button class="btn btn-primary" style="margin-top:14px" @click="openCreateModal">＋ 立即创建</button>
    </div>
    </DataTable>

    <!-- 绑定设备弹窗（六位码 / 手动 MAC / 解绑） -->
    <BindDeviceModal v-model:show="bind.show" :agent-id="bind.agentId" :agent-name="bind.agentName" @bound="onBoundRefresh" />

    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div class="modal">
        <h3>新增智能体</h3>
        <div class="form-row"><label>智能体名称</label><input v-model="draft.name" placeholder="例如：小何" /></div>
        <!-- 模型为0规则：LLM 数据源改为 /user/resources（平台启用+本人审核通过），为空隐藏下拉显示引导 -->
        <div class="form-row"><label>大脑（LLM 模型）</label>
          <select v-if="llmModels.length > 0" v-model="draft.llmModelId">
            <option v-for="m in llmModels" :key="m.id" :value="m.id">{{ m.modelName }}</option>
          </select>
          <div v-else class="inline-empty">
            <div>
              <strong>暂无可用模型</strong>
              <p>请联系管理员开通，或前往「我的模型」添加自定义模型（审核通过后可用）</p>
            </div>
            <button class="btn btn-ghost" style="padding:7px 16px;font-size:12.5px" @click="$router.push('/customer/my-models')">前往我的模型</button>
          </div>
        </div>
        <div class="form-row"><label>角色提示词</label><textarea v-model="draft.prompt" rows="3" placeholder="描述智能体的性格与说话风格"></textarea></div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" :disabled="creating || !draft.name || (llmModels.length > 0 && !draft.llmModelId)" @click="createAgent">创建</button>
        </div>
      </div>
    </div>

    <!-- 编辑弹窗（共享智能体视同自建，可编辑） -->
    <div v-if="edit.show" class="modal-mask" @click.self="edit.show = false">
      <div class="modal">
        <h3>编辑智能体</h3>
        <div v-if="edit.loading" class="edit-loading">加载中…</div>
        <template v-else>
          <div class="form-row"><label>智能体名称</label><input v-model="edit.name" placeholder="例如：小何" /></div>
          <div class="form-row"><label>大脑（LLM 模型）</label>
            <select v-if="llmModels.length > 0" v-model="edit.llmModelId">
              <option v-for="m in llmModels" :key="m.id" :value="m.id">{{ m.modelName }}</option>
            </select>
            <div v-else class="inline-empty">
              <div>
                <strong>暂无可用模型</strong>
                <p>保持原有模型不变，或前往「我的模型」添加自定义模型</p>
              </div>
              <button class="btn btn-ghost" style="padding:7px 16px;font-size:12.5px" @click="$router.push('/customer/my-models')">前往我的模型</button>
            </div>
          </div>
          <div class="form-row"><label>角色提示词</label><textarea v-model="edit.prompt" rows="3" placeholder="描述智能体的性格与说话风格"></textarea></div>
          <div class="modal-actions">
            <button class="btn btn-ghost" @click="edit.show = false">取消</button>
            <button class="btn btn-primary" :disabled="edit.saving || !edit.name" @click="saveEdit">保存</button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import YhIcon from '../../components/YhIcon.vue'
import { inject, onMounted, reactive, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import BindDeviceModal from '../../components/BindDeviceModal.vue'
import { customerApi, api } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')

const showCreate = ref(false)
const draft = ref({ name: '', prompt: '' })
const agents = ref([])
const loading = ref(false)
const creating = ref(false)
const deviceCount = ref(0)
const voices = ref(0)
// 模型为0规则：LLM 下拉数据源（平台启用+本人审核通过）
const llmModels = ref([])
// 绑定弹窗状态：{ show, agentId, agentName }
const bind = reactive({ show: false, agentId: '', agentName: '' })
// 编辑弹窗状态：共享/自建智能体统一可编辑（后端 PUT /agent/{id} 非空字段更新）
const edit = reactive({ show: false, loading: false, saving: false, id: '', name: '', prompt: '', llmModelId: '' })
let warned = false

function fmtTime(s) {
  if (!s) return '—'
  const str = String(s)
  return str.length >= 16 ? str.slice(5, 16) : str
}

async function load() {
  loading.value = true
  try {
    // GET /agent/list → data 为数组（契约 ResultListAgentDTO）
    const res = await customerApi.agentList()
    const list = res.data || []
    agents.value = list.map(a => ({
      id: a.id || a.agentId,
      name: a.agentName || a.name || '未命名',
      model: [a.llmModelName, a.ttsModelName].filter(Boolean).join(' · ') || a.llmModel || '默认模型',
      deviceCount: a.deviceCount != null ? a.deviceCount : (a.deviceName || a.macAddress ? 1 : 0),
      lastActive: fmtTime(a.lastConnectedAt || a.updateTime)
    }))
    // 设备总数：对所有智能体调用 boundDevices 汇总去重（契约 deviceCount 字段不可用时回退统计）
    const withCount = list.filter(a => a.deviceCount != null)
    if (withCount.length === list.length && list.length > 0) {
      deviceCount.value = withCount.reduce((s, a) => s + (Number(a.deviceCount) || 0), 0)
    } else {
      deviceCount.value = await loadDeviceCount(list)
    }
    // 音色资源计数
    try {
      const v = await customerApi.ttsVoicePage({ page: 1, limit: 1 })
      voices.value = v.data?.total ?? (v.data?.list ? v.data.list.length : 0)
    } catch { voices.value = 0 }
  } catch (e) {
    agents.value = []
    deviceCount.value = 0
    voices.value = 0
    if (!warned) { warned = true; toast(e.msg || '数据加载失败', 'error') }
  } finally {
    loading.value = false
  }
}

async function loadDeviceCount(agentsList) {
  try {
    const results = await Promise.all(
      agentsList.map(a => customerApi.boundDevices(a.id || a.agentId).catch(() => ({ data: [] })))
    )
    const seen = new Set()
    let n = 0
    results.forEach(r => {
      (r.data || []).forEach(d => {
        const key = d.id || d.macAddress
        if (key && !seen.has(key)) { seen.add(key); n++ }
      })
    })
    return n
  } catch { return 0 }
}

async function createAgent() {
  if (!draft.value.name.trim()) return
  creating.value = true
  try {
    const body = { agentName: draft.value.name.trim(), systemPrompt: draft.value.prompt }
    // LLM 模型（/user/resources 提供时）随创建一并提交
    if (draft.value.llmModelId) body.llmModelId = draft.value.llmModelId
    const res = await customerApi.createAgent(body)
    toast(`智能体「${draft.value.name.trim()}」已创建`)
    showCreate.value = false
    // 创建成功直接引导绑定设备（后端返回纯字符串 agentId）
    const newId = typeof res.data === 'string' ? res.data : (res.data?.id || res.data)
    if (newId) {
      bind.agentId = newId
      bind.agentName = draft.value.name.trim()
      bind.show = true
    }
    draft.value = { name: '', prompt: '', llmModelId: '' }
    load()
  } catch (e) {
    toast(e.msg || '创建失败', 'error')
  } finally {
    creating.value = false
  }
}

function openBind(a) {
  bind.agentId = a.id
  bind.agentName = a.name
  bind.show = true
}

// 编辑：agentDetail 回显（AgentInfoVO 继承 AgentEntity：agentName/systemPrompt/llmModelId）
async function openEdit(a) {
  edit.id = a.id
  edit.name = a.name
  edit.prompt = ''
  edit.llmModelId = ''
  edit.show = true
  edit.loading = true
  try {
    const res = await customerApi.agentDetail(a.id)
    const d = res.data || {}
    edit.name = d.agentName || a.name
    edit.prompt = d.systemPrompt || ''
    edit.llmModelId = d.llmModelId || ''
  } catch (e) {
    // 详情拉取失败不阻塞：仍可改名保存（prompt/模型保持空=不更新）
    toast(e.msg || '详情加载失败，仅可修改名称', 'error')
  } finally {
    edit.loading = false
  }
  if (!llmModels.value.length) loadLlmModels()
}

async function saveEdit() {
  if (!edit.name.trim()) return
  edit.saving = true
  try {
    // PUT /agent/{id} 只更新非空字段：prompt 留空表示不改
    const body = { agentName: edit.name.trim() }
    if (edit.prompt.trim()) body.systemPrompt = edit.prompt.trim()
    if (edit.llmModelId) body.llmModelId = edit.llmModelId
    await customerApi.updateAgent(edit.id, body)
    toast(`智能体「${edit.name.trim()}」已更新`)
    edit.show = false
    load()
  } catch (e) {
    toast(e.msg || '保存失败', 'error')
  } finally {
    edit.saving = false
  }
}

function remove(a) {
  askConfirm({
    title: '删除智能体',
    message: `确定删除「${a.name}」吗？删除后绑定关系一并解除，且不可恢复。`,
    danger: true,
    onOk: async () => {
      try {
        await customerApi.deleteAgent(a.id)
        toast('已删除')
        load()
      } catch (e) {
        toast(e.msg || '删除失败', 'error')
      }
    }
  })
}

function onBoundRefresh() {
  load()
}

// 模型为0规则：拉取用户可用 LLM 列表（平台启用+本人审核通过的自定义模型）
async function loadLlmModels() {
  try {
    const res = await api.get('/user/resources')
    const d = res.data || {}
    llmModels.value = (d.llmModels || []).map(m => ({ id: m.id, modelName: m.modelName }))
    if (llmModels.value.length > 0 && !draft.value.llmModelId) {
      draft.value.llmModelId = llmModels.value[0].id
    }
  } catch {
    // 静默降级：接口不可用时不阻塞创建弹窗（无下拉，显示空状态引导）
    llmModels.value = []
  }
}

function openCreateModal() {
  showCreate.value = true
  if (!llmModels.value.length) loadLlmModels()
}

onMounted(() => { load(); loadLlmModels() })
</script>

<style scoped>
.modal-mask { position: fixed; inset: 0; background: rgba(15,22,40,.45); display: grid; place-items: center; z-index: 100; }
/* .modal 基类收敛到 App.vue（含 max-height/overflow 超高滚动），此处不再重复定义 */
.modal h3 { font-size: 17px; margin-bottom: 18px; }
.form-row { margin-bottom: 14px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row textarea, .form-row select {
  border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px;
  font-size: 14px; outline: none; font-family: var(--font); transition: border .15s; background: #fff;
}
.form-row input:focus, .form-row textarea:focus, .form-row select:focus { border-color: var(--primary); }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 6px; }
/* 模型为0：弹窗内 inline 空状态（缩小版 empty-state） */
.inline-empty {
  border: 1.5px dashed var(--border); border-radius: 14px; padding: 14px 16px;
  display: flex; align-items: center; justify-content: space-between; gap: 12px; background: var(--bg, #F8FAFD);
}
.inline-empty strong { font-size: 13.5px; }
.inline-empty p { font-size: 12px; color: var(--text-sub); margin: 4px 0 0; line-height: 1.5; }
.link-btn.danger { color: var(--danger); }
.edit-loading { padding: 30px 0; text-align: center; color: var(--text-sub); font-size: 13.5px; }
</style>
