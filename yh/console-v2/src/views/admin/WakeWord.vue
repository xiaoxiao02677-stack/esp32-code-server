<template>
  <div>
    <div class="page-head">
      <div>
        <h1>唤醒词 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">配置智能体的自定义唤醒词，支持多词，最多 10 个，每个不超过 8 个汉字</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="wake-word-guide">
      <div class="guide-title">ℹ️ 唤醒词生效说明</div>
      <ul class="guide-list">
        <li><b>硬件唤醒词</b>：设备待机时喊它唤醒设备（前 5 个生效，单词 ≤8 个汉字）。保存后在线设备实时更新；离线设备下次连接时自动生效。</li>
        <li><b>寒暄词</b>：对话进行中说这些词，获得简短回应，不唤醒待机设备（第 6 个起仅作寒暄词）。</li>
        <li>自定义唤醒词请使用常见汉字（如"你好小智"），生僻字可能不被设备语音模型支持。</li>
      </ul>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="volume" label="智能体总数" :value="agents.length" />
      <StatCard icon="check-circle" label="已配置唤醒词" :value="configuredCount" />
      <StatCard icon="device" label="在线设备" :value="onlineDevices.length" note="实时状态" />
    </div>

    <DataTable title="智能体唤醒词配置" :loading="loading">
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
        <div class="empty-icon"><YhIcon name="volume" /></div><strong>暂无智能体</strong>
        <p>请先在「智能体管理」中创建智能体</p>
      </div>
    </DataTable>

    <!-- 编辑弹窗 -->
    <div v-if="editor.show" class="modal-mask" @click.self="editor.show = false">
      <div class="modal" style="width:min(600px,96vw)">
        <h3>编辑唤醒词 — {{ editor.agentName }}</h3>

        <div class="form-row">
          <label>唤醒词列表 <span class="field-hint">（最多 10 个，每个 ≤8 个汉字，用逗号或换行分隔）</span></label>
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

        <!-- 阈值入口说明：原「识别阈值 / 最短时长」两个滑块绑定的键
             Python /api/wake-word/push 并不接收（handler 只读 agent_id/device_id/
             wake_words/wake_word_display/tts_rate），是纯空操作控件，已移除。
             唤醒词灵敏度请去「智能体」页配置（走 device_config.wake_word_threshold，
             0~100，真正下发到固件并持久 NVS）。 -->
        <div class="config-row" v-if="false"></div>

        <!-- 实时打断阈值：与「智能体」编辑页同一入口（updateAgent →
             applyDeviceConfigToDevices 落 ai_device_config + 推 Python 热更新
             conn.interrupt_confirm_ms + WS 下发固件人声确认窗）。在此直接暴露，
             免得用户在智能体页找不到。 -->
        <div class="form-row">
          <label>实时打断阈值（0~100，拉选调节）</label>
          <div class="slider-row">
            <input v-model.number="editor.interruptThreshold" type="range" min="0" max="100" step="1"
                   class="slider" :style="{ '--pct': editor.interruptThreshold + '%' }" />
            <span class="slider-value">{{ editor.interruptThreshold }}</span>
          </div>
          <p class="field-hint">
            播放时用户说话打断的灵敏度：0 最灵敏（立即打断）· 100 最难打断（连续 2 秒人声才打断）· 默认 15 ≈ 300ms。调大可缓解"设备自言自语/误打断"。保存后立即下发绑定设备热生效。
          </p>
        </div>

        <!-- 下发范围：恒为该智能体绑定的全部在线设备。
             原「设备列表 + 勾选」整块删除，因为它是双重失效：
               ① 数据源 /api/wake-word/devices 返回的是 deviceId 字符串数组，
                  模板却按 {name, deviceId, online} 对象取值 → 永远渲染成空名 + 离线；
               ② 勾选结果传的 deviceIds 键 Python handler 根本不读（只读 device_id），
                  所以勾不勾选对下发范围毫无影响。
             留着只会让用户以为能按选下发。按选下发需 Python 侧支持 device_ids，另行排期。 -->
        <div class="form-row">
          <label>下发范围</label>
          <p class="field-hint">保存后自动下发到该智能体绑定的全部在线设备；离线设备重连后自动补投。</p>
        </div>

        <div class="form-row" v-if="editor.error">
          <label class="error-hint">{{ editor.error }}</label>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="editor.show = false">取消</button>
          <button class="btn btn-primary" :disabled="saving || pushing" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
          <button class="btn btn-success" :disabled="pushing" @click="pushToDevice({ id: editor.agentId })">{{ pushing ? '下发中…' : '保存并下发' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import YhIcon from '../../components/YhIcon.vue'
import { computed, inject, onMounted, reactive, ref, watch } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const agents = ref([])
// 顶部统计卡「已配置唤醒词」：模板一直引用 configuredCount，但它从未声明，
// 渲染出来是 undefined（Vue 只打警告不报错，所以长期没被发现）
const configuredCount = computed(
  () => agents.value.filter(a => (a.wakeWords || []).length > 0).length
)
const loading = ref(false)
const saving = ref(false)
const onlineDevices = ref([])
// 注：原 threshold / duration 两个 ref 已移除——它们绑定的键 Python push 端点不接收，
// 是纯空操作控件（唤醒词灵敏度请走「智能体」页的 wake_word_threshold）
// allDevices / pushTarget / toggleDeviceSelect 也已移除：设备区数据源从未对上
//（返回 deviceId 字符串数组，模板按对象取 name/online），已整块删除
const pushing = ref(false)
const editor = reactive({
  show: false,
  agentId: '',
  agentName: '',
  rawInput: '',
  preview: [],
  interruptThreshold: 15,   // 实时打断阈值（0~100）：openEdit 时从 agentDetail 回显
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
  } else if (words.some(w => w.length > 8)) {
    // 改 8：设备按拼音识别，单条上限 60 字符。最坏音节 zhuang（6 字母）时
    // N 个音节长 7N-1，N=8 → 55 字符安全，N=9 → 62 超限会被服务端丢弃。
    // 原阈值 30 个汉字（最坏 209 字符）必然被丢弃，是静默失效。
    editor.error = '每个唤醒词最多 8 个汉字（设备按拼音识别，超长会失效）'
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
    // 「在线设备」统计卡：必须走 adminApi（/xiaozhi 前缀，由 manager-api 注入 server secret）。
    // 原来直接 fetch('/api/wake-word/devices') 有三个错：少了 /xiaozhi 前缀打到静态站
    // 返回 200 text/html（json 解析抛错被空 catch 吞掉）、没带 agent_id、用的是用户 JWT
    // 而 Python 只认 server auth_key ⇒ 该卡片长期恒为 0。
    try {
      const devRes = await adminApi.wakeWordDevices()
      onlineDevices.value = devRes.data?.devices || []
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
    interruptThreshold: 15,
    error: ''
  })
  // 阈值回显：列表接口（/agent/list）不带 interruptThreshold，详情接口才有
  // （getAgentById → readDeviceConfigInt("interrupt_threshold")，无绑定设备为 null = 固件默认 15）
  adminApi.agentDetail(agent.id).then(res => {
    if (editor.show && editor.agentId === agent.id) {
      editor.interruptThreshold = res?.data?.interruptThreshold ?? 15
    }
  }).catch(() => {})
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
    // 不再在这里按 30 过滤：超长判定已由 watch 的 8 汉字校验拦截（editor.error），
  // 两处阈值不一致会让"界面不报错但词被悄悄丢掉"
  const words = editor.preview.filter(w => w.length > 0)
    if (words.length === 0) {
      toast('唤醒词不能为空', 'error')
      return
    }
    await adminApi.setAgentWakeWords(editor.agentId, words)
    // 实时打断阈值与唤醒词一起保存（updateAgent → 落库 + 推设备热生效）。
    // setAgentWakeWords 走专用唤醒词链路不含阈值键，单独 PUT /agent/{id}。
    if (Number.isInteger(editor.interruptThreshold) && editor.interruptThreshold >= 0 && editor.interruptThreshold <= 100) {
      await adminApi.updateAgent(editor.agentId, { interruptThreshold: editor.interruptThreshold })
    }
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

async function pushToDevice(agent) {
  if (editor.error) {
    toast(editor.error, 'error')
    return
  }
  // 不再在这里按 30 过滤：超长判定已由 watch 的 8 汉字校验拦截（editor.error），
  // 两处阈值不一致会让"界面不报错但词被悄悄丢掉"
  const words = editor.preview.filter(w => w.length > 0)
  if (words.length === 0) {
    toast('请填写唤醒词', 'error')
    return
  }
  pushing.value = true
  try {
    // 必须走 manager-api（POST /agent/wake-word/{id}）：汉字→无调拼音的转换在那一侧，
    // 且它负责写 ai_device_config（离线设备重连的唯一持久源）再转发 Python 推送。
    // 直连 Python /api/wake-word/push 有两个硬问题：
    //   ① 传上去的是汉字，固件 MultiNet 只认拼音 → 下发即失效；
    //   ② deviceIds / threshold / duration 三个键 Python handler 根本不读，
    //      所以"选设备下发"从来就是空操作（device_id 为 None 反而是全部设备）。
    await adminApi.setAgentWakeWords(agent.id, words)
    // 打断阈值同样随「保存并下发」生效（与 save() 一致的双链路）
    if (Number.isInteger(editor.interruptThreshold) && editor.interruptThreshold >= 0 && editor.interruptThreshold <= 100) {
      await adminApi.updateAgent(agent.id, { interruptThreshold: editor.interruptThreshold })
    }
    toast('已保存并下发至该智能体的全部在线设备', 'success', 3000)
    editor.show = false
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
/* 实时打断阈值进度条（与 Agents.vue 同款）：--pct 由 v-bind 传入渐变填充宽度 */
.slider-row { display: flex; align-items: center; gap: 12px; }
.slider {
  -webkit-appearance: none; appearance: none; flex: 1; height: 8px; border-radius: 999px;
  background: linear-gradient(to right, var(--primary) 0%, var(--primary) var(--pct, 15%),
              #E6EAF2 var(--pct, 15%), #E6EAF2 100%);
  outline: none; cursor: pointer; padding: 0; border: none;
}
.slider::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none; width: 20px; height: 20px; border-radius: 50%;
  background: #fff; border: 2.5px solid var(--primary); box-shadow: 0 1px 4px rgba(0,0,0,.18);
  cursor: grab;
}
.slider::-webkit-slider-thumb:active { cursor: grabbing; }
.slider::-moz-range-thumb {
  width: 20px; height: 20px; border-radius: 50%; background: #fff;
  border: 2.5px solid var(--primary); box-shadow: 0 1px 4px rgba(0,0,0,.18); cursor: grab;
}
.slider-value {
  flex: 0 0 44px; text-align: center; font-size: 13px; font-weight: 700;
  color: var(--primary); background: #fff; border: 1.5px solid var(--border);
  border-radius: 10px; padding: 4px 0; font-variant-numeric: tabular-nums;
}
</style>
