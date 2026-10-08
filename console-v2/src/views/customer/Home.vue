<template>
  <div>
    <div class="page-head">
      <div>
        <h1>智能体 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">智能体与设备管理</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="showCreate = true">＋ 新增智能体</button>
        <button class="btn btn-ghost" @click="refresh">↻ 刷新列表</button>
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
          <button class="btn btn-primary" @click="showCreate = true">开始使用</button>
          <button class="btn btn-ghost" @click="$router.push('/customer/devices')">查看设备</button>
        </div>
        <div class="blob-3d">🤖</div>
      </div>
      <div class="stats-grid">
        <StatCard icon="🤖" label="智能体" :value="agents.length" note="已创建" />
        <StatCard icon="📡" label="设备" :value="deviceCount" note="已绑定" />
        <StatCard icon="🎙" label="音色" :value="voices" note="可用" />
        <StatCard icon="💎" label="可用积分" :value="points" note="余额" />
      </div>
    </div>

    <DataTable title="智能体清单" hint="管理你的智能体配置" :total="agents.length" :page="1" :pages="1">
      <template #actions>
        <button class="btn btn-ghost" style="padding:7px 16px;font-size:13px" @click="showCreate = true">新增</button>
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
              <span class="badge" :class="a.device ? 'badge-green' : 'badge-gray'">
                <span class="dot"></span>{{ a.device || '未绑定' }}
              </span>
            </td>
            <td style="color:var(--text-sub)">{{ a.lastActive }}</td>
            <td>
              <div class="row-actions">
                <button class="link-btn">配置</button>
                <button class="link-btn danger">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="agents.length === 0" class="empty-state">
        <div class="empty-icon">🤖</div>
        <strong>暂无智能体</strong>
        <p>点击右上角「新增智能体」创建第一个智能体</p>
      </div>
    </DataTable>

    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div class="modal">
        <h3>新增智能体</h3>
        <div class="form-row"><label>智能体名称</label><input v-model="draft.name" placeholder="例如：小何" /></div>
        <div class="form-row"><label>角色提示词</label><textarea v-model="draft.prompt" rows="3" placeholder="描述智能体的性格与说话风格"></textarea></div>
        <div class="form-row"><label>默认音色</label>
          <select v-model="draft.voice"><option>豆包小何</option><option>温柔姐姐</option><option>元气少年</option></select>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" @click="createAgent">创建</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, computed } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { customerApi, authApi } from '../../lib/api'

const showCreate = ref(false)
const draft = ref({ name: '', prompt: '', voice: '豆包小何' })
const agents = ref([])
const loadErr = ref('')
const points = ref('—')
const deviceCount = ref(0)
const voices = ref(0)

async function load() {
  loadErr.value = ''
  try {
    // GET /agent/list —— 真实接口
    const res = await customerApi.agentList()
    const list = res.data || []
    agents.value = list.map(a => ({
      id: a.agentId || a.id,
      name: a.agentName || a.name,
      model: a.llmModel || a.modelName || '默认模型',
      device: a.deviceName || null,
      lastActive: a.updateTime ? String(a.updateTime).slice(5, 16) : '—'
    }))
    deviceCount.value = list.filter(a => a.deviceName || a.macAddress).length
  } catch (e) {
    loadErr.value = e.msg || '加载失败'
  }
  // 音色资源计数
  try {
    const v = await customerApi.voiceResourcePage({ page: 1, limit: 100 })
    voices.value = (v.data && (v.data.list ? v.data.list.length : v.data.total)) ?? 0
  } catch { voices.value = 0 }
}

function createAgent() {
  if (!draft.value.name) return
  customerApi.createAgent({ agentName: draft.value.name, systemPrompt: draft.value.prompt })
    .then(() => { showCreate.value = false; load() })
    .catch(e => { loadErr.value = e.msg })
}

onMounted(load)
const refresh = load
</script>

<style scoped>
.modal-mask { position: fixed; inset: 0; background: rgba(15,22,40,.45); display: grid; place-items: center; z-index: 100; }
.modal { background: #fff; border-radius: 20px; padding: 26px; width: min(440px, 92vw); box-shadow: 0 24px 60px rgba(0,0,0,.2); }
.modal h3 { font-size: 17px; margin-bottom: 18px; }
.form-row { margin-bottom: 14px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row textarea, .form-row select {
  border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px;
  font-size: 14px; outline: none; font-family: var(--font); transition: border .15s;
}
.form-row input:focus, .form-row textarea:focus, .form-row select:focus { border-color: var(--primary); }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 6px; }
</style>
