<template>
  <div>
    <div class="page-head">
      <div>
        <h1>推送调度 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">定时向设备推送消息配置</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="showCreate = true">＋ 新建任务</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <!-- 任务列表 -->
    <div class="task-list">
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <div v-else-if="!tasks.length" class="empty">暂无推送任务</div>
      <div v-else class="tasks">
        <div v-for="task in tasks" :key="task.id" class="task-card">
          <div class="task-header">
            <span class="task-name">{{ task.name || '未命名任务' }}</span>
            <span class="task-status" :class="task.enabled ? 'active' : 'inactive'">
              {{ task.enabled ? '启用' : '禁用' }}
            </span>
          </div>
          <div class="task-body">
            <p class="task-content">{{ task.content || '无内容' }}</p>
            <p class="task-time">调度时间：{{ task.schedule || '立即' }}</p>
          </div>
          <div class="task-actions">
            <button class="btn btn-sm" @click="toggleTask(task)">
              {{ task.enabled ? '禁用' : '启用' }}
            </button>
            <button class="btn btn-sm btn-danger" @click="deleteTask(task.id)">删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 创建弹窗 -->
    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal">
        <div class="modal-header">
          <h3>新建推送任务</h3>
          <button class="close" @click="showCreate = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>任务名称</label>
            <input v-model="form.name" placeholder="请输入任务名称" />
          </div>
          <div class="form-group">
            <label>推送内容</label>
            <textarea v-model="form.content" placeholder="请输入推送内容" rows="4"></textarea>
          </div>
          <div class="form-group">
            <label>调度时间</label>
            <input v-model="form.schedule" type="datetime-local" />
          </div>
          <div class="form-group">
            <label>目标设备</label>
            <select v-model="form.deviceId">
              <option value="">全部设备</option>
              <option value="all">所有在线设备</option>
            </select>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" @click="createTask" :disabled="creating">创建</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../../lib/api'

const tasks = ref([])
const loading = ref(false)
const error = ref('')
const showCreate = ref(false)
const creating = ref(false)
const form = ref({ name: '', content: '', schedule: '', deviceId: '' })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.get('/api/push/tasks')
    if (res.code === 0) {
      tasks.value = res.data || []
    } else {
      error.value = res.msg || '加载失败'
    }
  } catch (e) {
    error.value = e.message || '网络错误'
  } finally {
    loading.value = false
  }
}

async function createTask() {
  if (!form.value.content) {
    alert('请输入推送内容')
    return
  }
  creating.value = true
  try {
    const res = await api.post('/api/push/schedule', form.value)
    if (res.code === 0) {
      showCreate.value = false
      form.value = { name: '', content: '', schedule: '', deviceId: '' }
      await load()
    } else {
      alert(res.msg || '创建失败')
    }
  } catch (e) {
    alert(e.message || '网络错误')
  } finally {
    creating.value = false
  }
}

async function toggleTask(task) {
  try {
    const res = await api.put(`/api/push/tasks/${task.id}`, { enabled: !task.enabled })
    if (res.code === 0) {
      await load()
    }
  } catch (e) {
    alert('操作失败')
  }
}

async function deleteTask(id) {
  if (!confirm('确定删除此任务？')) return
  try {
    await api.delete(`/api/push/tasks/${id}`)
    await load()
  } catch (e) {
    alert('删除失败')
  }
}

onMounted(load)
</script>

<style scoped>
.task-list { margin-top: 20px; }
.tasks { display: grid; gap: 16px; }
.task-card {
  background: white;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.task-name { font-weight: 600; font-size: 16px; }
.task-status {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}
.task-status.active { background: #dcfce7; color: #16a34a; }
.task-status.inactive { background: #fee2e2; color: #dc2626; }
.task-body { margin: 12px 0; }
.task-content { color: #333; margin-bottom: 8px; }
.task-time { color: #666; font-size: 14px; }
.task-actions { display: flex; gap: 8px; }
.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal {
  background: white;
  border-radius: 12px;
  width: 500px;
  max-width: 90vw;
}
.modal-header {
  padding: 16px 20px;
  border-bottom: 1px solid #eee;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.modal-header h3 { margin: 0; }
.modal-header .close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
}
.modal-body { padding: 20px; }
.form-group { margin-bottom: 16px; }
.form-group label {
  display: block;
  margin-bottom: 4px;
  font-weight: 500;
}
.form-group input,
.form-group textarea,
.form-group select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
}
.modal-footer {
  padding: 16px 20px;
  border-top: 1px solid #eee;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.btn-sm { padding: 6px 12px; font-size: 14px; }
.btn-danger { background: #dc2626; color: white; }
.loading, .error, .empty {
  text-align: center;
  padding: 40px;
  color: #666;
}
.error { color: #dc2626; }
</style>
