<template>
  <div>
    <div class="page-head">
      <div>
        <h1>微信绑定 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">绑定微信OpenClaw账号，实现微信消息推送</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="bind-card">
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <div v-else>
        <div class="bind-status">
          <div class="status-icon">{{ bindInfo.bound ? '✅' : '⭕' }}</div>
          <div class="status-info">
            <h3>{{ bindInfo.bound ? '已绑定微信' : '未绑定微信' }}</h3>
            <p v-if="bindInfo.bound">
              微信号：{{ bindInfo.wechatId || '未知' }}<br/>
              绑定时间：{{ bindInfo.boundTime || '未知' }}
            </p>
            <p v-else>绑定后可通过微信发送消息给设备</p>
          </div>
        </div>

        <div v-if="!bindInfo.bound" class="bind-actions">
          <button class="btn btn-primary" @click="startBind">开始绑定</button>
        </div>
        <div v-else class="bind-actions">
          <button class="btn btn-danger" @click="unbind">解除绑定</button>
        </div>
      </div>
    </div>

    <div class="help-box">
      <h4>绑定说明</h4>
      <ol>
        <li>点击"开始绑定"生成绑定二维码</li>
        <li>用微信扫描二维码</li>
        <li>在微信中确认绑定</li>
        <li>绑定成功后可通过微信发送消息</li>
      </ol>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../../lib/api'

const loading = ref(false)
const error = ref('')
const bindInfo = ref({ bound: false, wechatId: '', boundTime: '' })

async function load() {
  loading.value = true
  error.value = ''
  try {
    // TODO: 调用后端API获取绑定状态
    // const res = await api.get('/api/wechat/openclaw/status')
    // bindInfo.value = res.data
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function startBind() {
  alert('绑定功能开发中，请稍后使用')
}

function unbind() {
  if (!confirm('确定解除微信绑定？')) return
  alert('解绑功能开发中，请稍后使用')
}

onMounted(load)
</script>

<style scoped>
.bind-card {
  background: white;
  border-radius: 8px;
  padding: 24px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  max-width: 600px;
}
.bind-status {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 20px;
}
.status-icon { font-size: 48px; }
.status-info h3 { margin: 0 0 8px 0; }
.status-info p { margin: 4px 0; color: #666; }
.bind-actions { display: flex; gap: 12px; }
.help-box {
  margin-top: 24px;
  background: #f8fafc;
  border-radius: 8px;
  padding: 16px 20px;
}
.help-box h4 { margin: 0 0 12px 0; }
.help-box ol { margin: 0; padding-left: 20px; }
.help-box li { margin: 8px 0; color: #666; }
.loading, .error { text-align: center; padding: 40px; color: #666; }
.error { color: #dc2626; }
.btn-danger { background: #dc2626; color: white; }
</style>
