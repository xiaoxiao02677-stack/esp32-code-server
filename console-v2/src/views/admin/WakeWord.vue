<template>
  <div>
    <div class="page-head">
      <div>
        <h1>唤醒词 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">配置智能体的自定义唤醒词，支持多词，最多 10 个，每个不超过 30 字符</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="🔊" label="智能体总数" :value="agents.length" />
      <StatCard icon="✅" label="已配置唤醒词" :value="configuredCount" />
      <StatCard icon="📡" label="在线设备" :value="onlineDevices.length" note="实时状态" />
    </div>

    <DataTable title="智能体唤醒词配置">
      <table class="data-table">
        <thead><tr><th>智能体</th><th>唤醒词列表</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="a in agents" :key="a.id">
            <td>
              <div class="cell-main">{{ a.name }}</div>
              <div class="cell-sub">{{ a.boundCount ? `📡 ${a.boundCount} 台设备` : '未绑定设备' }}</div>
            </td>
            <td style="font-size:12px; max-width:300px">
              <div v-if="!a.wakeWords || a.wakeWords.length === 0" style="color:var(--muted)">未配置（使用全局默认）</div>
              <div v-else class="wake-word-tags">
                <span v-for="(w, i) in a.wakeWords" :key="i" class="wake-word-tag">{{ w }}</span>
              </div>
            </td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="openEdit(a)">编辑</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="agents.length === 0" class="empty-state">
        <div class="empty-icon">🔊</div><strong>暂无智能体</strong>
        <p>请先在「智能体管理」中创建智能体</p>
      </div>
    </DataTable>

    <!-- 编辑弹窗 -->
    <div v-if="editor.show" class="modal-mask" @click.self="editor.show = false">
      <div class="modal" style="width:min(560px,94vw)">
        <h3>编辑唤醒词 — {{ editor.agentName }}</h3>
        <div class="form-row">
          <label>唤醒词列表 <span class="field-hint">（最多 10 个，每个 ≤30 字符，分号分隔）</span></label>
          <textarea
            v-model="editor.rawInput"
            rows="6"
            placeholder="你好小智&#10;早上好&#10;嗨你好"
            style="font-family:monospace"
          ></textarea>
        </div>
        <div class="form-row" v-if="editor.preview.length > 0">
          <label>预览</label>
          <div class="wake-word-tags">
            <span v-for="(w, i) in editor.preview" :key="i" class="wake-word-tag">{{ w }}</span>
          </div>
        </div>
        <div class="form-row" v-if="editor.error">
          <label class="error-hint">{{ editor.error }}</label>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="editor.show = false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { inject, onMounted, reactive, ref, watch } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const agents = ref([])
const loading = ref(false)
const saving = ref(false)
const onlineDevices = ref([])
const editor = reactive({
  show: false,
  agentId: '',
  agentName: '',
  rawInput: '',
  preview: [],
  error: ''
})

// 解析唤醒词输入
watch(() => editor.rawInput, (val) => {
  if (!val) {
    editor.preview = []
    return
  }
  const words = val.split(/[,，\n]/).map(s => s.trim()).filter(Boolean)
  editor.preview = words
  editor.error = ''
  if (words.length > 10) {
    editor.error = '最多输入 10 个唤醒词'
  } else if (words.some(w => w.length > 30)) {
    editor.error = '每个唤醒词最多 30 个字符'
  }
})

async function load() {
  loading.value = true
  try {
    const res = await adminApi.agentPage({ page: 1, limit: 200 })
    agents.value = (res.data?.list || []).map(a => ({
      ...a,
      wakeWords: a.wakeWords ? a.wakeWords.split(';').filter(Boolean) : []
    }))
    // 加载在线设备
    try {
      const devRes = await fetch('/api/wake-word/devices', {
        headers: { Authorization: 'Bearer ' + localStorage.getItem('token') }
      })
      if (devRes.ok) {
        const d = await devRes.json()
        onlineDevices.value = d.data?.devices || []
      }
    } catch {}
  } catch (e) {
    toast(e.msg || '加载失败', 'error')
  } finally {
    loading.value = false
  }
}

function openEdit(agent) {
  Object.assign(editor, {
    show: true,
    agentId: agent.id,
    agentName: agent.name,
    rawInput: (agent.wakeWords || []).join('\n'),
    preview: agent.wakeWords || [],
    error: ''
  })
}

async function save() {
  if (!editor.rawInput.trim()) {
    toast('请填写唤醒词', 'error')
    return
  }
  if (editor.error) {
    toast(editor.error, 'error')
    return
  }
  saving.value = true
  try {
    const words = editor.preview.filter(w => w.length > 0 && w.length <= 30)
    if (words.length === 0) {
      toast('唤醒词不能为空', 'error')
      return
    }
    await adminApi.setAgentWakeWords(editor.agentId, words)
    toast('保存成功', 'success')
    editor.show = false
    load()
  } catch (e) {
    toast(e.msg || '保存失败', 'error')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.wake-word-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.wake-word-tag {
  background: var(--primary-light, #e8f4ff);
  color: var(--primary, #0066cc);
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}
.error-hint {
  color: #dc3545;
  font-size: 12px;
}
</style>
