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

    <div class="wake-word-guide">
      <div class="guide-title">ℹ️ 唤醒词生效说明</div>
      <ul class="guide-list">
        <li><b>硬件唤醒词</b>：设备待机时喊它唤醒设备（前 5 个生效，单词 ≤32 字符）。保存后在线设备实时更新；离线设备下次连接时自动生效。</li>
        <li><b>寒暄词</b>：对话进行中说这些词，获得简短回应，不唤醒待机设备（第 6 个起仅作寒暄词）。</li>
        <li>自定义唤醒词请使用常见汉字（如"你好小智"），生僻字可能不被设备语音模型支持。</li>
      </ul>
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
      <div class="modal" style="width:min(600px,96vw)">
        <h3>编辑唤醒词 — {{ editor.agentName }}</h3>

        <div class="form-row">
          <label>唤醒词列表 <span class="field-hint">（最多 10 个，每个 ≤30 字符，分号分隔）</span></label>
          <textarea
            v-model="editor.rawInput"
            rows="6"
            placeholder="你好小智&#10;早上好&#10;嗨你好"
            style="font-family:monospace"
          ></textarea>
          <p class="field-hint">建议使用常见汉字，生僻字可能不被设备语音模型支持。前 5 个将同步为设备硬件唤醒词（待机喊它唤醒），其余作为寒暄词（对话中获得简短回应）。</p>
        </div>

        <div class="form-row" v-if="editor.preview.length > 0">
          <label>预览</label>
          <div class="wake-word-tags">
            <span v-for="(w, i) in editor.preview" :key="i" class="wake-word-tag" :class="{ 'hw-word': i < 5 }">{{ w }}<em v-if="i < 5" class="tag-badge">硬件</em></span>
          </div>
          <p v-if="editor.preview.length > 5" class="field-hint warn-hint">硬件唤醒词上限 5 个，第 6 个起仅作为寒暄词生效（对话中回应，不唤醒待机设备）。</p>
        </div>

        <!-- 阈值与时长设置 -->
        <div class="config-row">
          <div class="config-field">
            <label>识别阈值 <span class="field-hint">灵敏度（越高越严格）</span></label>
            <div class="slider-group">
              <input type="range" min="0" max="100" v-model.number="threshold" class="range-input">
              <span class="range-value">{{ threshold }}%</span>
            </div>
          </div>
          <div class="config-field">
            <label>唤醒词最短时长 <span class="field-hint">ms（过滤噪声）</span></label>
            <div class="slider-group">
              <input type="range" min="100" max="2000" step="100" v-model.number="duration" class="range-input">
              <span class="range-value">{{ duration }}ms</span>
            </div>
          </div>
        </div>

        <!-- 设备选择 -->
        <div class="form-row">
          <label>动态下发至设备</label>
          <div class="device-select-box">
            <div v-if="allDevices.length === 0" class="field-hint">暂无可用设备</div>
            <div v-else class="device-grid">
              <label v-for="d in allDevices" :key="d.id" class="device-item" :class="{ active: pushTarget.includes(d.id) }">
                <input type="checkbox" :value="d.id" :checked="pushTarget.includes(d.id)" @change="toggleDeviceSelect(d.id)">
                <span class="device-name">{{ d.name || d.deviceId }}</span>
                <span class="device-status" :class="d.online ? 'online' : 'offline'">{{ d.online ? '在线' : '离线' }}</span>
              </label>
            </div>
            <div v-if="pushTarget.length > 0" class="selected-count">已选 {{ pushTarget.length }} 台</div>
          </div>
        </div>

        <div class="form-row" v-if="editor.error">
          <label class="error-hint">{{ editor.error }}</label>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="editor.show = false">取消</button>
          <button class="btn btn-primary" :disabled="saving || pushing" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
          <button class="btn btn-success" :disabled="pushing || pushTarget.length === 0" @click="pushToDevice({ id: editor.agentId })">{{ pushing ? '下发中…' : '保存并下发' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { inject, onMounted, reactive, ref, watch } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi, getToken } from '../../lib/api'

const toast = inject('toast')
const agents = ref([])
const loading = ref(false)
const saving = ref(false)
const onlineDevices = ref([])
const allDevices = ref([])
const threshold = ref(60)
const duration = ref(500)
const pushTarget = ref([]) // selected device ids
const pushing = ref(false)
const editor = reactive({
  show: false,
  agentId: '',
  agentName: '',
  rawInput: '',
  preview: [],
  error: ''
})

// 解析唤醒词输入
// 注：>5 词不阻断保存——前 5 个同步为设备硬件唤醒词，其余作为寒暄词（预览区有提示）
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
        headers: { Authorization: 'Bearer ' + getToken() }
      })
      if (devRes.ok) {
        const d = await devRes.json()
        onlineDevices.value = d.data?.devices || []
        allDevices.value = d.data?.devices || []
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
    // 长文案给足阅读时间；说明生效条件：在线设备实时、离线设备下次连接
    const overLimit = words.length > 5
    toast(overLimit
      ? `已保存（${words.length} 个）。前 5 个已同步为硬件唤醒词：在线设备实时更新，离线设备下次连接时生效；第 6 个起仅作为寒暄词`
      : '已保存。硬件唤醒词将同步到设备：在线设备实时更新，离线设备下次连接时生效', 'success', 5200)
    editor.show = false
    load()
  } catch (e) {
    toast(e.msg || '保存失败', 'error')
  } finally {
    saving.value = false
  }
}

onMounted(load)

async function toggleDeviceSelect(deviceId) {
  const idx = pushTarget.value.indexOf(deviceId)
  if (idx >= 0) pushTarget.value.splice(idx, 1)
  else pushTarget.value.push(deviceId)
}

async function pushToDevice(agent) {
  if (pushTarget.value.length === 0) {
    toast('请先选择目标设备', 'error')
    return
  }
  pushing.value = true
  try {
    const words = editor.preview.filter(w => w.length > 0 && w.length <= 30)
    await adminApi.wakeWordPush(agent.id, {
      deviceIds: pushTarget.value,
      wakeWords: words,
      threshold: threshold.value,
      duration: duration.value
    })
    const count = pushTarget.value.length
    toast(`已下发至 ${count} 台设备`, 'success', 3000)
    editor.show = false
    pushTarget.value = []
    load()
  } catch (e) {
    toast(e.msg || '下发失败', 'error')
  } finally {
    pushing.value = false
  }
}
</script>

<style scoped>
.wake-word-guide {
  border: 1.5px solid var(--border);
  border-radius: 16px;
  padding: 14px 16px;
  margin-bottom: 16px;
  background: var(--bg-soft, #F8FAFD);
}
.guide-title {
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 8px;
}
.guide-list {
  margin: 0;
  padding-left: 18px;
  font-size: 12.5px;
  color: var(--text-sub);
  line-height: 1.7;
}
.guide-list b { color: var(--text); }
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
.wake-word-tag.hw-word {
  border: 1px solid var(--primary, #0066cc);
}
.tag-badge {
  font-style: normal;
  font-size: 10px;
  margin-left: 4px;
  opacity: 0.75;
}
.error-hint {
  color: #dc3545;
  font-size: 12px;
}
.warn-hint {
  color: #b8860b;
}
.field-hint {
  font-size: 11.5px;
  color: var(--text-sub);
  margin: 2px 0 0;
  line-height: 1.6;
}

/* 阈值与时长滑块 */
.config-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.config-field label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
}
.slider-group {
  display: flex;
  align-items: center;
  gap: 10px;
}
.range-input {
  flex: 1;
  accent-color: var(--primary, #0066cc);
  cursor: pointer;
}
.range-value {
  min-width: 48px;
  text-align: right;
  font-size: 13px;
  font-weight: 700;
  color: var(--primary, #0066cc);
}

/* 设备选择框 */
.device-select-box {
  border: 1.5px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  background: var(--bg-soft, #F8FAFD);
}
.device-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 8px;
}
.device-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border: 1.5px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color .15s, background .15s;
  font-size: 12.5px;
}
.device-item:hover { border-color: var(--primary, #0066cc); }
.device-item.active {
  border-color: var(--primary, #0066cc);
  background: var(--primary-light, #e8f4ff);
}
.device-item input[type="checkbox"] { cursor: pointer; accent-color: var(--primary, #0066cc); }
.device-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.device-status {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 8px;
  font-weight: 600;
  flex-shrink: 0;
}
.device-status.online { background: #d1fae5; color: #065f46; }
.device-status.offline { background: #fee2e2; color: #991b1b; }
.selected-count {
  margin-top: 8px;
  font-size: 12px;
  color: var(--primary, #0066cc);
  font-weight: 600;
}

/* 成功按钮 */
.btn-success {
  background: #10b981;
  color: #fff;
  border: none;
  padding: 7px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity .15s;
}
.btn-success:hover:not(:disabled) { opacity: 0.88; }
.btn-success:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
