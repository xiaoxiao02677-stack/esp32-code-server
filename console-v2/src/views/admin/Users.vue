<template>
  <div>
    <div class="page-head">
      <div>
        <h1>用户 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">账号、状态与设备归属</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="hero-row">
      <div class="hero-blob" style="min-height:170px">
        <div>
          <div class="en">USERS / ACCOUNTS</div>
          <h2>用户</h2>
          <p>管理全平台用户与状态</p>
        </div>
        <div class="blob-3d">👥</div>
      </div>
      <div class="stats-grid">
        <StatCard icon="👥" label="用户总数" :value="total" />
        <StatCard icon="✅" label="本页" :value="users.length" note="当前页" />
        <StatCard icon="🚫" label="已封禁" :value="bannedCount" />
        <StatCard icon="📄" label="页码" :value="page + '/' + pages" note="page 从 1 开始" />
      </div>
    </div>

    <DataTable title="用户清单" :total="total" :page="page" :pages="pages">
      <template #actions>
        <input v-model="mobile" placeholder="搜索手机号" style="border:1.5px solid var(--border);border-radius:10px;padding:6px 12px;font-size:12.5px;outline:none" @keyup.enter="search" />
        <button class="btn btn-ghost" style="padding:6px 14px;font-size:12.5px" @click="search">搜索</button>
      </template>
      <table class="data-table">
        <thead>
          <tr><th>用户</th><th>设备</th><th>状态</th><th>注册时间</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td>
              <div class="cell-main">{{ u.username }}</div>
              <div class="cell-sub">{{ u.mobile || u.id?.slice(0, 12) }}</div>
            </td>
            <td>{{ u.deviceCount ?? '—' }}</td>
            <td>
              <span class="badge" :class="u.status === 1 ? 'badge-green' : 'badge-gray'">
                <span class="dot"></span>{{ u.status === 1 ? '正常' : '已封禁' }}
              </span>
            </td>
            <td style="color:var(--text-sub)">{{ u.createDate || '—' }}</td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="resetPwd(u)">重置密码</button>
                <button class="link-btn" @click="toggleStatus(u)">{{ u.status === 1 ? '封禁' : '解封' }}</button>
                <button class="link-btn danger" @click="remove(u)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="users.length === 0" class="empty-state">
        <div class="empty-icon">👥</div>
        <strong>暂无用户</strong>
      </div>
    </DataTable>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')

const users = ref([])
const total = ref(0)
const page = ref(1)
const pages = ref(1)
const loading = ref(false)
const mobile = ref('')

const bannedCount = computed(() => users.value.filter(u => u.status !== 0).length)

async function load() {
  loading.value = true
  try {
    // GET /admin/users —— page 从 1 开始（契约）
    const res = await adminApi.userPage({ page: page.value, limit: 4, mobile: mobile.value || undefined })
    const data = res.data || {}
    users.value = (data.list || []).map(u => ({
      id: u.id, username: u.username || u.mobile || '未命名',
      mobile: u.mobile, status: u.status ?? 1, deviceCount: u.deviceCount,
      createDate: u.createDate ? String(u.createDate).slice(0, 10) : '—'
    }))
    total.value = data.total ?? users.value.length
    pages.value = Math.max(1, Math.ceil(total.value / 4))
  } catch (e) {
    toast(e.msg || '加载失败', 'error')
  } finally {
    loading.value = false
  }
}

function search() { page.value = 1; load() }

function resetPwd(u) {
  askConfirm({
    title: '重置密码', message: `确定将用户「${u.username}」的密码重置为默认密码吗？`,
    onOk: async () => {
      try {
        await adminApi.resetPassword(u.id)
        toast('密码已重置')
      } catch (e) { toast(e.msg || '重置失败', 'error') }
    }
  })
}
function toggleStatus(u) {
  // manager-api 语义（Oauth2Realm:100）：status=1 正常，status=0 锁定
  const next = u.status === 1 ? 0 : 1
  const label = next === 0 ? '封禁' : '解封'
  askConfirm({
    title: label + '用户', message: `确定${label}用户「${u.username}」吗？`, danger: next === 0,
    onOk: async () => {
      try {
        await adminApi.changeUserStatus([u.id], next)
        toast('已' + label)
        load()
      } catch (e) { toast(e.msg || label + '失败', 'error') }
    }
  })
}
function remove(u) {
  askConfirm({
    title: '删除用户', message: `确定删除用户「${u.username}」吗？此操作不可恢复。`, danger: true,
    onOk: async () => {
      try {
        await adminApi.deleteUser(u.id)
        toast('用户已删除')
        load()
      } catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}

onMounted(load)
</script>
