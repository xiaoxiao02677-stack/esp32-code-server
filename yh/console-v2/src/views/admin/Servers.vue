<template>
  <div>
    <div class="page-head">
      <div>
        <h1>服务器 <span style="color:var(--primary)">节点</span></h1>
        <p class="sub">迁移自 /cc/ 服务器节点页：WS 接入节点列表</p>
      </div>
      <div class="head-actions">
        <button
          class="btn btn-ghost btn-restart"
          @click="confirmRestartPy"
          :disabled="restartingPy || restartingJava || loading"
        >{{ restartingPy ? '重启中…' : '♻️ 重启语音服务' }}</button>
        <button
          class="btn btn-ghost btn-restart"
          @click="confirmRestartJava"
          :disabled="restartingPy || restartingJava || loading"
        >{{ restartingJava ? '重启中…' : '♻️ 重启管理服务' }}</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="🖥" label="节点总数" :value="servers.length" />
      <StatCard icon="🟢" label="启用" :value="servers.filter(s => s.enable).length" />
    </div>

    <DataTable title="节点列表">
      <table class="data-table">
        <thead><tr><th>名称</th><th>地址</th><th>状态</th><th>说明</th></tr></thead>
        <tbody>
          <tr v-for="s in servers" :key="s.id || s.name">
            <td><div class="cell-main">{{ s.name || s.serverName || s.id }}</div></td>
            <td style="font-size:12px">{{ s.wsUrl || s.url || s.address || '—' }}</td>
            <td>
              <span class="badge" :class="s.enable ? 'badge-green' : 'badge-gray'">
                <span class="dot"></span>{{ s.enable ? '启用' : '停用' }}
              </span>
            </td>
            <td style="font-size:12px">{{ s.remark || s.description || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="servers.length === 0" class="empty-state"><div class="empty-icon">🖥</div><strong>暂无节点</strong></div>
    </DataTable>
  </div>
</template>

<script setup>
import { inject, onMounted, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')
const servers = ref([])
const loading = ref(false)
const restartingPy = ref(false)
const restartingJava = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await adminApi.serverList()
    const data = res.data
    // 契约：data 为字符串数组（WS 地址列表）
    servers.value = (Array.isArray(data) ? data : (data?.list || [])).map((s, i) =>
      typeof s === 'string'
        ? { id: 'srv-' + i, name: '节点 ' + (i + 1), wsUrl: s, enable: true }
        : { id: s.id || s.name, name: s.name || s.serverName, wsUrl: s.wsUrl || s.url || s.address, enable: s.enable }
    )
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

function confirmRestartPy() {
  // 需要一个启用的 WS 节点作为 emit-action 目标
  const target = servers.value.find(s => s.enable && s.wsUrl)
  if (!target) {
    toast('未获取到可用的 WS 节点地址，请先刷新节点列表', 'error')
    load()
    return
  }
  askConfirm({
    title: '重启语音服务',
    message: `将向节点 ${target.wsUrl} 下发重启指令，xiaozhi-server 会平滑自重启，设备短暂断线后自动重连。确定继续吗？`,
    danger: true,
    onOk: async () => {
      restartingPy.value = true
      try {
        // 既有链路：POST /admin/server/emit-action {targetWs, action:'restart'} → Python handle_restart()
        await adminApi.serverAction({ targetWs: target.wsUrl, action: 'restart' })
        toast('重启指令已发出，设备将短暂断线后自动重连')
      } catch (e) {
        toast(e.msg || '重启指令发送失败', 'error')
      } finally {
        restartingPy.value = false
      }
    }
  })
}

function confirmRestartJava() {
  askConfirm({
    title: '重启管理服务',
    message: '将重启 manager-api 管理服务，当前页面会短暂不可用，约 10 秒后自动恢复。确定继续吗？',
    danger: true,
    onOk: async () => {
      restartingJava.value = true
      try {
        await adminApi.restartJavaApi()
        toast('重启指令已发出，约 10 秒后生效')
      } catch (e) {
        // 服务自杀重启时该请求可能无响应/报错，属正常现象
        toast('重启指令已发出；若页面无响应属正常，请稍后刷新')
      } finally {
        restartingJava.value = false
      }
    }
  })
}

onMounted(load)
</script>

<style scoped>
.btn-restart { color: var(--primary); font-weight: 600; }
.btn-restart:disabled { opacity: 0.55; cursor: not-allowed; }
</style>
