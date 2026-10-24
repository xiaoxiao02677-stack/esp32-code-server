<template>
  <div>
    <div class="page-head">
      <div>
        <h1>用户 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">账号、角色、会话与回收站</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="openCreate">＋ 新增用户</button>
        <button class="btn btn-ghost" @click="openSessions">🔐 会话</button>
        <button class="btn btn-ghost" @click="openImport">⬆ 导入</button>
        <button class="btn btn-ghost" @click="doExport">⬇ 导出</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">{{ loading ? '加载中…' : '↻ 刷新' }}</button>
      </div>
    </div>

    <div class="hero-row">
      <div class="hero-blob" style="min-height:170px">
        <div>
          <div class="en">USERS / ACCOUNTS</div>
          <h2>用户</h2>
          <p>全平台账号、角色与在线会话管理</p>
        </div>
        <div class="blob-3d">👥</div>
      </div>
      <div class="stats-grid">
        <StatCard icon="users" label="用户总数" :value="total" :note="deleted === 1 ? '已删除列表' : '正常用户'" />
        <StatCard icon="📋" label="本页" :value="users.length" note="当前页" />
        <StatCard icon="⚠️" label="异常账号" :value="abnormalCount" note="本页停用/锁定" />
        <StatCard icon="file" label="页码" :value="page + '/' + pages" note="page 从 1 开始" />
      </div>
    </div>

    <!-- chip 筛选：正常用户 / 已删除（回收站）+ 角色类别筛选 + 分组视图开关 -->
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:16px">
      <button type="button" class="chip" :class="{ active: deleted === 0 }" @click="pickDeleted(0)">👤 正常用户</button>
      <button type="button" class="chip" :class="{ active: deleted === 1 }" @click="pickDeleted(1)">🗑 已删除（回收站）</button>
      <span class="filter-sep"></span>
      <select v-model="roleFilter" class="filter-select" @change="applyRoleFilter">
        <option value="">全部角色</option>
        <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.roleName }}</option>
      </select>
      <button type="button" class="chip" :class="{ active: groupByRole }" :disabled="deleted === 1"
              title="按角色类别分组展示本页用户" @click="toggleGroupByRole">🧩 按角色分组</button>
    </div>

    <DataTable :title="deleted === 1 ? '已删除用户' : '用户清单'" :total="total" :pages="pages"
               v-model:page="page" v-model:pageSize="pageSize" :loading="loading">
      <template #actions>
        <input v-model="keyword" placeholder="搜索用户名" class="filter-input" @keyup.enter="search" />
        <button class="btn btn-ghost" style="padding:6px 14px;font-size:12.5px" @click="search">搜索</button>
      </template>

      <!-- 批量操作工具条（仅正常列表） -->
      <div v-if="deleted === 0 && selectedIds.length" class="batch-bar">
        <span class="batch-info">已选 {{ selectedIds.length }} 项</span>
        <button class="btn btn-ghost batch-btn" @click="batchStatus(0)">🚫 批量禁用</button>
        <button class="btn btn-ghost batch-btn" @click="batchStatus(1)">✅ 批量启用</button>
        <button class="btn btn-ghost batch-btn danger-text" @click="batchRemove">🗑 批量删除</button>
        <button class="link-btn" @click="selectedIds = []">清空选择</button>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th v-if="deleted === 0" style="width:36px">
              <input type="checkbox" :checked="allSelected" @change="toggleAll" style="width:auto" title="全选/反选" />
            </th>
            <th class="sortable" @click="toggleSort('username')">用户 <span class="sort-ind" :class="{ on: sort === 'username' }">{{ sort === 'username' ? (order === 'asc' ? '↑' : '↓') : '↕' }}</span></th>
            <th class="sortable" @click="toggleSort('status')">状态 <span class="sort-ind" :class="{ on: sort === 'status' }">{{ sort === 'status' ? (order === 'asc' ? '↑' : '↓') : '↕' }}</span></th>
            <th class="sortable" @click="toggleSort('lastLoginDate')">最后登录 <span class="sort-ind" :class="{ on: sort === 'lastLoginDate' }">{{ sort === 'lastLoginDate' ? (order === 'asc' ? '↑' : '↓') : '↕' }}</span></th>
            <th class="sortable" @click="toggleSort('createDate')">注册时间 <span class="sort-ind" :class="{ on: sort === 'createDate' }">{{ sort === 'createDate' ? (order === 'asc' ? '↑' : '↓') : '↕' }}</span></th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <!-- 分组视图：按角色聚合，组头行 + 成员行 -->
          <template v-if="groupByRole && roleGroups && roleGroups.length">
            <template v-for="g in roleGroups" :key="g.name">
              <tr class="group-head">
                <td v-if="deleted === 0"></td>
                <td colspan="5">
                  <span class="group-tag">{{ g.name }}</span>
                  <span class="group-count">{{ g.users.length }} 人</span>
                </td>
              </tr>
              <tr v-for="u in g.users" :key="u.id" class="group-member">
                <td v-if="deleted === 0"><input type="checkbox" :value="u.id" v-model="selectedIds" style="width:auto" /></td>
                <td>
                  <div class="cell-main">{{ u.username }}</div>
                  <div class="cell-sub role-tags">
                    <span v-if="!u.roleNames.length" class="no-role">未分配角色</span>
                    <span v-for="name in u.roleNames" :key="name" class="role-tag">{{ name }}</span>
                  </div>
                </td>
                <td>
                  <span class="badge" :class="statusBadge(u).cls"><span class="dot"></span>{{ statusBadge(u).text }}</span>
                </td>
                <td style="color:var(--text-sub)">{{ u.lastLoginDate || '—' }}</td>
                <td style="color:var(--text-sub)">{{ u.createDate }}</td>
                <td>
                  <div v-if="deleted === 1" class="row-actions">
                    <button class="link-btn" @click="restore(u)">恢复</button>
                    <button class="link-btn danger" @click="purge(u)">彻底删除</button>
                  </div>
                  <div v-else class="row-actions">
                    <button class="link-btn" @click="openRoles(u)">角色</button>
                    <button class="link-btn" @click="resetPwd(u)">重置密码</button>
                    <button class="link-btn" @click="toggleStatus(u)">{{ u.status === 1 ? '封禁' : '解封' }}</button>
                    <button class="link-btn" @click="forceLogout(u)">下线</button>
                    <button class="link-btn danger" @click="remove(u)">删除</button>
                  </div>
                </td>
              </tr>
            </template>
          </template>
          <!-- 平铺视图（默认） -->
          <template v-else>
            <tr v-for="u in users" :key="u.id">
              <td v-if="deleted === 0"><input type="checkbox" :value="u.id" v-model="selectedIds" style="width:auto" /></td>
              <td>
                <div class="cell-main">{{ u.username }}</div>
                <div class="cell-sub role-tags">
                  <span v-if="!u.roleNames.length" class="no-role">未分配角色</span>
                  <span v-for="name in u.roleNames" :key="name" class="role-tag">{{ name }}</span>
                </div>
              </td>
              <td>
                <span class="badge" :class="statusBadge(u).cls"><span class="dot"></span>{{ statusBadge(u).text }}</span>
              </td>
              <td style="color:var(--text-sub)">{{ u.lastLoginDate || '—' }}</td>
              <td style="color:var(--text-sub)">{{ u.createDate }}</td>
              <td>
              <!-- 已删用户：恢复 / 彻底删除（物理删除释放用户名） -->
              <div v-if="deleted === 1" class="row-actions">
                <button class="link-btn" @click="restore(u)">恢复</button>
                <button class="link-btn danger" @click="purge(u)">彻底删除</button>
              </div>
                <div v-else class="row-actions">
                  <button class="link-btn" @click="openRoles(u)">角色</button>
                  <button class="link-btn" @click="resetPwd(u)">重置密码</button>
                  <button class="link-btn" @click="toggleStatus(u)">{{ u.status === 1 ? '封禁' : '解封' }}</button>
                  <button class="link-btn" @click="forceLogout(u)">下线</button>
                  <button class="link-btn danger" @click="remove(u)">删除</button>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <div v-if="users.length === 0" class="empty-state">
        <div class="empty-icon">{{ deleted === 1 ? '🗑' : '👥' }}</div>
        <strong>{{ deleted === 1 ? '回收站是空的' : '暂无用户' }}</strong>
        <p v-if="deleted === 0 && keyword">没有匹配「{{ keyword }}」的用户，换个关键词试试</p>
        <p v-else-if="deleted === 0">点击右上角「＋ 新增用户」创建第一个账号</p>
        <p v-else>软删除的用户会出现在这里，可随时恢复</p>
      </div>
    </DataTable>

    <!-- 新增用户弹窗 -->
    <div v-if="creator.show" class="modal-mask" @click.self="creator.show = false">
      <div class="modal" style="width:min(520px,94vw);max-height:88vh;overflow:auto">
        <h3>新增用户</h3>
        <div class="form-row">
          <label>用户名 *</label>
          <input v-model="creator.username" maxlength="50" placeholder="登录用户名" />
        </div>
        <div class="form-row">
          <label>初始密码</label>
          <input v-model="creator.password" placeholder="留空则自动生成 12 位密码" />
          <p class="field-hint">留空自动生成；创建后展示初始密码，请妥善保管并告知用户</p>
        </div>
        <div class="form-row">
          <label>角色（可多选）</label>
          <div v-if="roles.length" class="role-checks">
            <label v-for="r in roles" :key="r.id" class="role-check">
              <input type="checkbox" :value="r.id" v-model="creator.roleIds" style="width:auto" />
              <span>{{ r.roleName }}<span class="role-code">{{ r.roleCode }}</span></span>
            </label>
          </div>
          <p v-else class="field-hint">角色加载中或暂无可用角色…</p>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="creator.show = false">取消</button>
          <button class="btn btn-primary" :disabled="creating" @click="createUser">{{ creating ? '创建中…' : '创建' }}</button>
        </div>
      </div>
    </div>

    <!-- 编辑角色弹窗 -->
    <div v-if="rolesEditor.show" class="modal-mask" @click.self="rolesEditor.show = false">
      <div class="modal" style="width:min(520px,94vw);max-height:88vh;overflow:auto">
        <h3>编辑角色 — {{ rolesEditor.username }}</h3>
        <div class="form-row">
          <label>分配角色（已选 {{ rolesEditor.roleIds.length }} 项）</label>
          <div v-if="roles.length" class="role-checks">
            <label v-for="r in roles" :key="r.id" class="role-check">
              <input type="checkbox" :value="r.id" v-model="rolesEditor.roleIds" style="width:auto" />
              <span>{{ r.roleName }}<span class="role-code">{{ r.roleCode }}</span></span>
            </label>
          </div>
          <p v-else class="field-hint">角色加载中或暂无可用角色…</p>
          <p class="field-hint">保存后立即生效（权限实时鉴权，无需用户重新登录）</p>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="rolesEditor.show = false">取消</button>
          <button class="btn btn-primary" :disabled="savingRoles" @click="saveRoles">{{ savingRoles ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>

    <!-- 密码展示弹窗（初始密码 / 重置后的新密码） -->
    <div v-if="pwdBox.show" class="modal-mask" @click.self="pwdBox.show = false">
      <div class="modal" style="width:min(460px,92vw)">
        <h3>{{ pwdBox.title }}</h3>
        <p class="pwd-tip">用户「{{ pwdBox.username }}」的{{ pwdBox.title }}如下，请妥善保管并告知用户：</p>
        <div class="pwd-display">{{ pwdBox.password }}</div>
        <p class="field-hint" style="text-align:center">请妥善保管并告知用户，初始密码可直接登录使用</p>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="pwdBox.show = false">关闭</button>
          <button class="btn btn-primary" @click="copyPwd">⧉ 复制密码</button>
        </div>
      </div>
    </div>

    <!-- 导入弹窗 -->
    <div v-if="importer.show" class="modal-mask" @click.self="importer.show = false">
      <div class="modal" style="width:min(560px,94vw);max-height:88vh;overflow:auto">
        <h3>导入用户</h3>
        <template v-if="!importer.result">
          <div class="form-row">
            <label>导入内容</label>
            <textarea v-model="importer.text" rows="8" placeholder="每行一个：用户名,密码&#10;如：zhangsan,Pass@123&#10;lisi（密码可省略，自动生成）"></textarea>
            <p class="field-hint">每行格式「用户名,密码」，密码可省略（自动生成）；自动忽略空行与重复用户名</p>
          </div>
          <div class="modal-actions">
            <button class="btn btn-ghost" @click="importer.show = false">取消</button>
            <button class="btn btn-primary" :disabled="importer.importing" @click="doImport">{{ importer.importing ? '导入中…' : '⬆ 开始导入' }}</button>
          </div>
        </template>
        <template v-else>
          <p class="imp-summary">
            导入完成：成功 <strong style="color:var(--success)">{{ (importer.result.success || []).length }}</strong> 个，
            失败 <strong style="color:var(--danger)">{{ (importer.result.failed || []).length }}</strong> 个
          </p>
          <div v-if="(importer.result.success || []).length" class="imp-list">
            <div v-for="(s, i) in importer.result.success" :key="'s' + i" class="imp-item ok">✅ {{ impName(s) }}</div>
          </div>
          <div v-if="(importer.result.failed || []).length" class="imp-list">
            <div v-for="(f, i) in importer.result.failed" :key="'f' + i" class="imp-item fail">❌ {{ f.username }} — {{ f.reason || '未知原因' }}</div>
          </div>
          <div class="modal-actions">
            <button class="btn btn-ghost" @click="importer.result = null">再导一批</button>
            <button class="btn btn-primary" @click="importer.show = false">完成</button>
          </div>
        </template>
      </div>
    </div>

    <!-- 在线会话弹窗 -->
    <div v-if="sessions.show" class="modal-mask" @click.self="sessions.show = false">
      <div class="modal" style="width:min(760px,94vw);max-height:88vh;overflow:auto">
        <h3>在线会话</h3>
        <p class="field-hint" style="margin:-10px 0 12px">当前持有有效 token 的登录会话；下线仅清该用户的服务端会话，不发送设备指令。</p>
        <table class="data-table">
          <thead><tr><th>用户</th><th>Token</th><th>过期时间</th><th>创建时间</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="(s, i) in sessions.list" :key="i" :class="{ 'self-session': isSelf(s) }">
              <td><div class="cell-main">{{ s.username }}<span v-if="isSelf(s)" class="self-mark">（你自己）</span></div></td>
              <td class="mono" style="font-size:12px">{{ s.token }}</td>
              <td style="color:var(--text-sub)">{{ s.expireDate }}</td>
              <td style="color:var(--text-sub)">{{ s.createDate }}</td>
              <td>
                <div class="row-actions">
                  <button class="link-btn danger" :disabled="!s.userId" :title="s.userId ? (isSelf(s) ? '注意：这会把你自己的登录踢下线' : '') : '缺少用户ID，无法下线'" @click="kickSession(s)">下线</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="!sessions.loading && sessions.list.length === 0" class="empty-state" style="padding:32px 0">
          <div class="empty-icon">🔐</div>
          <strong>暂无活跃会话</strong>
          <p>当前没有用户持有有效 token</p>
        </div>
        <div class="session-pager">
          <span>共 {{ sessions.total }} 条 · 第 {{ sessions.page }}/{{ sessionPages }} 页</span>
          <button class="page-btn" :disabled="sessions.page <= 1" @click="sessionGo(sessions.page - 1)">‹</button>
          <button class="page-btn" :disabled="sessions.page >= sessionPages" @click="sessionGo(sessions.page + 1)">›</button>
          <button class="link-btn" style="font-size:12px" :disabled="sessions.loading" @click="loadSessions">{{ sessions.loading ? '加载中…' : '↻ 刷新' }}</button>
        </div>
        <div class="modal-actions" style="margin-top:16px">
          <button class="btn btn-ghost" @click="sessions.show = false">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, reactive, ref, watch } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')

// ===== 列表状态（真分页：page 从 1 开始，limit=20） =====
const users = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const keyword = ref('')
const deleted = ref(0) // 0 正常用户 / 1 已删除（回收站）
const selectedIds = ref([])
// 列排序（表头点击）：sort 取 username/status/lastLoginDate/createDate，order 取 asc/desc
const sort = ref('')
const order = ref('desc')

const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const abnormalCount = computed(() => users.value.filter(u => u.locked === 1 || u.status !== 1).length)
const allSelected = computed(() => users.value.length > 0 && users.value.every(u => selectedIds.value.includes(u.id)))

// 角色分组视图：本页用户按角色聚合（"未分配角色"自成一组，排最后）
const groupByRole = ref(false)
const roleGroups = computed(() => {
  if (!groupByRole.value) return null
  const groups = []
  const idx = new Map()
  for (const u of users.value) {
    const names = u.roleNames.length ? u.roleNames : ['未分配角色']
    for (const name of names) {
      if (!idx.has(name)) {
        idx.set(name, groups.length)
        groups.push({ name, users: [] })
      }
      groups[idx.get(name)].users.push(u)
    }
  }
  // "未分配角色"组排最后
  groups.sort((a, b) => {
    const aNone = a.name === '未分配角色' ? 1 : 0
    const bNone = b.name === '未分配角色' ? 1 : 0
    return aNone - bNone
  })
  return groups
})

// 表头排序：同列再点切方向，不同列从 desc 开始（与后端 adminPage sort/order 对应）
function toggleSort(field) {
  if (sort.value === field) {
    order.value = order.value === 'asc' ? 'desc' : 'asc'
  } else {
    sort.value = field
    order.value = 'desc'
  }
  if (page.value !== 1) page.value = 1
  else load()
}

// SPEC §4.2：列表 VO 含 roleNames[]、deleted、locked、lastLoginDate
function normalizeUser(u) {
  return {
    id: u.userid ?? u.id,
    username: u.username || '未命名',
    roleNames: Array.isArray(u.roleNames) ? u.roleNames : [],
    status: u.status ?? 1,
    locked: u.locked ?? 0,
    deleted: u.deleted ?? deleted.value,
    lastLoginDate: u.lastLoginDate ? String(u.lastLoginDate).slice(0, 16) : '',
    createDate: u.createDate ? String(u.createDate).slice(0, 10) : '—'
  }
}

// 组合状态徽章：已删除 > 已锁定 > 已停用 > 正常
function statusBadge(u) {
  if (u.deleted === 1) return { cls: 'badge-gray', text: '已删除' }
  if (u.locked === 1) return { cls: 'badge-orange', text: '已锁定' }
  if (u.status === 1) return { cls: 'badge-green', text: '正常' }
  return { cls: 'badge-gray', text: '已停用' }
}

async function load() {
  loading.value = true
  try {
    // GET /admin/users —— keyword 匹配 username；deleted 0/1；sort/order 表头排序；roleId 角色筛选
    const params = {
      page: page.value,
      limit: pageSize.value,
      deleted: deleted.value
    }
    if (keyword.value) params.keyword = keyword.value
    if (sort.value) {
      params.sort = sort.value
      params.order = order.value
    }
    if (roleFilter.value) params.roleId = roleFilter.value
    const res = await adminApi.userPage(params)
    const data = res.data || {}
    users.value = (data.list || []).map(normalizeUser)
    total.value = data.total ?? users.value.length
  } catch (e) {
    toast(e.msg || '加载失败', 'error')
  } finally {
    loading.value = false
  }
  // 勾选仅对当前页有效：翻页/删除后自动清理失效项
  selectedIds.value = selectedIds.value.filter(id => users.value.some(u => u.id === id))
}

function search() {
  // 页码不为 1 时置 1 由 watch 触发 load，避免双请求
  if (page.value !== 1) page.value = 1
  else load()
}

function pickDeleted(d) {
  if (deleted.value === d) return
  deleted.value = d
  selectedIds.value = []
  // 回收站不支持分组视图（无角色语义）
  if (d === 1) groupByRole.value = false
  if (page.value !== 1) page.value = 1
  else load()
}

// 角色筛选变化：回第 1 页重新加载（后端 EXISTS 过滤）
function applyRoleFilter() {
  if (page.value !== 1) page.value = 1
  else load()
}

// 分组视图开关（仅前端展示层聚合，不触发请求）
function toggleGroupByRole() {
  groupByRole.value = !groupByRole.value
}

function toggleAll(e) {
  selectedIds.value = e.target.checked ? users.value.map(u => u.id) : []
}

// ===== 角色选项（roleList：启用角色下拉 + 分组视图角色统计） =====
const roles = ref([])
// 角色筛选（需求1：按角色类别分组查看）：空 = 全部
const roleFilter = ref('')

async function loadRoles() {
  try {
    const res = await adminApi.roleList()
    roles.value = (res.data || []).map(r => ({ id: r.id, roleCode: r.roleCode || '', roleName: r.roleName || r.roleCode }))
  } catch (e) {
    toast(e.msg || '角色列表加载失败', 'error')
  }
}

// ===== 新增用户（成功后展示初始密码） =====
const creator = reactive({ show: false, username: '', password: '', roleIds: [] })
const creating = ref(false)

function openCreate() {
  Object.assign(creator, { show: true, username: '', password: '', roleIds: [] })
  loadRoles()
}

async function createUser() {
  if (!creator.username.trim()) { toast('请填写用户名', 'error'); return }
  creating.value = true
  try {
    // SPEC §4.2：{username, password?, roleIds?}；密码缺省自动生成，data=初始密码
    const body = { username: creator.username.trim() }
    if (creator.password) body.password = creator.password
    if (creator.roleIds.length) body.roleIds = [...creator.roleIds]
    const res = await adminApi.userCreate(body)
    creator.show = false
    showPwd(body.username, res.data, '初始密码')
    toast('用户已创建')
    load()
  } catch (e) {
    // 10220 用户名已存在；10237 用户名被回收站同名账号占用 → 明确指引
    if (e.code === 10237) {
      toast('该用户名被回收站中的已删账号占用，请到「已删除（回收站）」中恢复或彻底删除该账号后重试', 'error', 6000)
    } else {
      toast(e.msg || '创建失败', 'error')
    }
  } finally {
    creating.value = false
  }
}

// ===== 密码展示框（初始密码 / 重置密码共用） =====
const pwdBox = reactive({ show: false, title: '', username: '', password: '' })

function showPwd(username, password, title) {
  Object.assign(pwdBox, { show: true, title: title || '密码', username, password: String(password || '') })
}

async function copyPwd() {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(pwdBox.password)
    } else {
      const el = document.createElement('textarea')
      el.value = pwdBox.password
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
    }
    toast('已复制')
  } catch (e) {
    toast('复制失败', 'error')
  }
}

// ===== 编辑角色（userDetail 取当前角色 → userAssignRoles 保存） =====
const rolesEditor = reactive({ show: false, userId: null, username: '', roleIds: [] })
const savingRoles = ref(false)

async function openRoles(u) {
  // 详情返回 data={user, roles, ...}；失败则不打开弹窗，避免误清空角色
  let current = []
  try {
    const res = await adminApi.userDetail(u.id)
    const rs = res.data?.roles || []
    current = rs.map(r => (typeof r === 'object' && r !== null ? r.id : r))
  } catch (e) {
    toast(e.msg || '用户详情加载失败', 'error')
    return
  }
  Object.assign(rolesEditor, { show: true, userId: u.id, username: u.username, roleIds: current })
  loadRoles()
}

async function saveRoles() {
  savingRoles.value = true
  try {
    await adminApi.userAssignRoles({ userId: rolesEditor.userId, roleIds: [...rolesEditor.roleIds] })
    toast('角色已更新')
    rolesEditor.show = false
    load()
  } catch (e) {
    toast(e.msg || '保存失败', 'error')
  } finally {
    savingRoles.value = false
  }
}

// ===== 重置密码（确认后调用，展示新密码） =====
function resetPwd(u) {
  askConfirm({
    title: '重置密码',
    message: `确定重置用户「${u.username}」的密码吗？将生成新密码，请及时告知用户。`,
    onOk: async () => {
      try {
        // SPEC §4.2：PUT /admin/users/{id} → data=新密码
        const res = await adminApi.resetPassword(u.id)
        showPwd(u.username, res.data, '新密码')
        toast('密码已重置')
      } catch (e) { toast(e.msg || '重置失败', 'error') }
    }
  })
}

// ===== 封禁/解封（changeUserStatus 数组传参；自禁/最后超管由后端拒绝） =====
function toggleStatus(u) {
  // status=1 正常，status=0 停用
  const next = u.status === 1 ? 0 : 1
  const label = next === 0 ? '封禁' : '解封'
  askConfirm({
    title: label + '用户',
    message: `确定${label}用户「${u.username}」吗？${next === 0 ? '封禁后该用户无法登录。' : ''}`,
    danger: next === 0,
    onOk: async () => {
      try {
        await adminApi.changeUserStatus([u.id], next)
        toast('已' + label)
        load()
      } catch (e) { toast(e.msg || label + '失败', 'error') }
    }
  })
}

// ===== 软删除 / 恢复 =====
function remove(u) {
  askConfirm({
    title: '删除用户',
    message: `确定删除用户「${u.username}」吗？软删除后可在「已删除」列表中恢复。`,
    danger: true,
    onOk: async () => {
      try {
        await adminApi.deleteUser(u.id)
        toast('已删除，可在回收站恢复')
        load()
      } catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}

function restore(u) {
  askConfirm({
    title: '恢复用户',
    message: `确定恢复用户「${u.username}」吗？恢复后该用户即可正常登录。`,
    onOk: async () => {
      try {
        await adminApi.userRestore(u.id)
        toast('已恢复')
        load()
      } catch (e) { toast(e.msg || '恢复失败', 'error') }
    }
  })
}

// ===== 彻底删除（物理删除，释放用户名；级联清理设备/智能体/角色/会话） =====
function purge(u) {
  askConfirm({
    title: '彻底删除',
    message: `确定彻底删除用户「${u.username}」吗？⚠️ 此操作不可恢复：账号将被物理删除，名下设备、智能体（含聊天记录）、角色绑定、音色克隆一并清除，用户名随之释放。`,
    danger: true,
    onOk: async () => {
      try {
        await adminApi.userPurge(u.id)
        toast('已彻底删除，用户名已释放')
        load()
      } catch (e) { toast(e.msg || '彻底删除失败', 'error') }
    }
  })
}

// ===== 强制下线（过期该用户全部 token） =====
// 会话判"自己"：与本地登录用户名比对（管理员通常只有自己一个活跃会话，误点会把自己踢出登录）
function isSelf(s) {
  const me = JSON.parse(localStorage.getItem('cc_user_info') || 'null')
  return !!(me && me.username && s.username && String(me.username) === String(s.username))
}

function forceLogout(u) {
  const self = isSelf({ username: u.username })
  askConfirm({
    title: '强制下线',
    message: `确定将用户「${u.username}」的全部会话强制下线吗？${self ? '⚠️ 这是你自己的账号，下线后需要重新登录！' : ''}`,
    danger: true,
    onOk: async () => {
      try {
        await adminApi.userForceLogout(u.id)
        toast('已强制下线')
        // 刷新列表与可见反馈（此前无 load()，用户看不到任何变化）
        load()
        if (sessions.show) loadSessions()
      } catch (e) { toast(e.msg || '操作失败', 'error') }
    }
  })
}

// ===== 批量操作（数组接口 + askConfirm） =====
function batchStatus(next) {
  const ids = [...selectedIds.value]
  const label = next === 0 ? '禁用' : '启用'
  askConfirm({
    title: '批量' + label,
    message: `确定批量${label}选中的 ${ids.length} 个用户吗？`,
    danger: next === 0,
    onOk: async () => {
      try {
        await adminApi.changeUserStatus(ids, next)
        toast(`已${label} ${ids.length} 个用户`)
        selectedIds.value = []
        load()
      } catch (e) { toast(e.msg || '批量' + label + '失败', 'error') }
    }
  })
}

function batchRemove() {
  const ids = [...selectedIds.value]
  askConfirm({
    title: '批量删除',
    message: `确定删除选中的 ${ids.length} 个用户吗？软删除后可在「已删除」列表中恢复。`,
    danger: true,
    onOk: async () => {
      // deleteUser 为单条接口，逐条并发执行后汇总结果
      const results = await Promise.allSettled(ids.map(id => adminApi.deleteUser(id)))
      const ok = results.filter(r => r.status === 'fulfilled').length
      const fail = results.length - ok
      if (fail === 0) toast(`已删除 ${ok} 个用户`)
      else toast(`删除成功 ${ok} 个、失败 ${fail} 个`, 'error')
      selectedIds.value = []
      load()
    }
  })
}

// ===== 会话管理（弹窗内分页表） =====
const sessions = reactive({ show: false, list: [], page: 1, total: 0, loading: false })
const sessionPages = computed(() => Math.max(1, Math.ceil(sessions.total / 10)))

function openSessions() {
  Object.assign(sessions, { show: true, page: 1, list: [], total: 0 })
  loadSessions()
}

async function loadSessions() {
  sessions.loading = true
  try {
    const res = await adminApi.userSessions({ page: sessions.page, limit: 10 })
    const data = res.data || {}
    sessions.list = (data.list || []).map(s => ({
      userId: s.userId ?? s.userid,
      username: s.username || '—',
      token: s.token || '—', // 后端已做前 8 位掩码
      expireDate: s.expireDate ? String(s.expireDate).slice(0, 16) : '—',
      createDate: s.createDate ? String(s.createDate).slice(0, 16) : '—'
    }))
    sessions.total = data.total ?? sessions.list.length
  } catch (e) {
    toast(e.msg || '会话加载失败', 'error')
  } finally {
    sessions.loading = false
  }
}

function sessionGo(p) {
  const target = Math.min(Math.max(1, p), sessionPages.value)
  if (target !== sessions.page) {
    sessions.page = target
    loadSessions()
  }
}

function kickSession(s) {
  const self = isSelf(s)
  askConfirm({
    title: '强制下线',
    message: `确定将用户「${s.username}」的全部会话下线吗？${self ? '⚠️ 这是你自己当前的登录会话，确认后你将被踢出并需要重新登录！' : ''}`,
    danger: true,
    onOk: async () => {
      try {
        await adminApi.userForceLogout(s.userId)
        if (self) {
          // 踢的是自己：清本地登录态，直接回登录页（后续请求全部免发）
          localStorage.removeItem('cc_token')
          localStorage.removeItem('cc_user_info')
          toast('已下线，请重新登录', 'info', 4000)
          location.hash = '#/login'
          return
        }
        toast('已下线')
        loadSessions()
        load()
      } catch (e) { toast(e.msg || '操作失败', 'error') }
    }
  })
}

// ===== 导入 / 导出 =====
const importer = reactive({ show: false, text: '', importing: false, result: null })

function openImport() {
  Object.assign(importer, { show: true, text: '', importing: false, result: null })
}

// 每行「用户名,密码」→ [{username, password?}]；忽略空行、去重、兼容中文逗号
function parseImportLines() {
  const list = []
  const seen = new Set()
  for (const raw of importer.text.split('\n')) {
    const line = raw.trim()
    if (!line) continue
    const parts = line.split(/[,，]/).map(s => s.trim())
    const username = parts[0]
    const password = parts[1]
    if (!username || seen.has(username)) continue
    seen.add(username)
    const item = { username }
    if (password) item.password = password
    list.push(item)
  }
  return list
}

// success 元素可能是用户名字符串或对象，统一取展示名
function impName(s) {
  return typeof s === 'object' && s !== null ? (s.username || s.name || '') : s
}

async function doImport() {
  const list = parseImportLines()
  if (!list.length) { toast('请先输入要导入的用户（每行：用户名,密码）', 'error'); return }
  importer.importing = true
  try {
    const res = await adminApi.userImport(list)
    // code=0：全部成功，data={success:[], failed:[]}
    importer.result = res.data || { success: list.map(i => i.username), failed: [] }
    toast('导入完成')
    load()
  } catch (e) {
    // 10225 部分失败：后端把明细放 data（{success, failed}），透传到 e.data 时展示清单
    if (e.data && (Array.isArray(e.data.failed) || Array.isArray(e.data.success))) {
      importer.result = e.data
      load()
    } else {
      toast(e.msg || '导入失败', 'error')
    }
  } finally {
    importer.importing = false
  }
}

function doExport() {
  // 导出为 CSV 附件流，带当前搜索词与列表范围；过滤空 keyword 避免 URL 出现 undefined
  const params = { deleted: deleted.value }
  if (keyword.value) params.keyword = keyword.value
  window.open(adminApi.userExportUrl(params), '_blank')
}

// ===== 真分页 watch（改 pageSize 回第 1 页） =====
watch(page, () => load())
watch(pageSize, () => {
  if (page.value !== 1) page.value = 1
  else load()
})

onMounted(() => {
  load()
  // 角色选项：筛选下拉 + 分组视图都用（失败不打扰，下拉退化为"全部角色"）
  loadRoles()
})
</script>

<style scoped>
/* .chip 已收敛到 global.css */

/* .chip 已收敛到 global.css */

.form-row { margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row select, .form-row textarea {
  border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px;
  font-size: 14px; outline: none; font-family: var(--font); background: #fff; color: var(--text);
}
.form-row input:focus, .form-row select:focus, .form-row textarea:focus { border-color: var(--primary); }
.field-hint { font-size: 11.5px; color: var(--text-sub); margin: 2px 0 0; }
.modal h3 { font-size: 17px; margin-bottom: 18px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }

/* 用户列角色小徽章 */
.role-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.role-tag { font-size: 11px; padding: 1px 8px; border-radius: 999px; background: var(--primary-soft); color: var(--primary); font-weight: 600; white-space: nowrap; }
.no-role { color: var(--text-sub); }

/* 批量操作工具条 */
.batch-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 12px 20px 0; padding: 10px 14px; background: var(--primary-soft); border-radius: 12px; }
.batch-info { font-weight: 700; color: var(--primary); font-size: 12.5px; }
.batch-btn { padding: 6px 14px; font-size: 12.5px; }
.danger-text { color: var(--danger); }

/* 角色多选框组 */
.role-checks { display: flex; flex-wrap: wrap; gap: 8px 16px; border: 1.5px solid var(--border); border-radius: 12px; padding: 12px 14px; }
.role-check { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; }
.role-code { color: var(--text-sub); font-size: 11.5px; margin-left: 4px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }

/* 密码展示框 */
.pwd-tip { font-size: 13px; color: var(--text-sub); line-height: 1.6; }
.pwd-display {
  margin: 14px 0 8px; padding: 18px 16px; background: #F8FAFE;
  border: 1.5px dashed var(--border); border-radius: 14px; text-align: center;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 22px; font-weight: 700; letter-spacing: 1.5px; color: var(--text);
  user-select: all; word-break: break-all;
}

/* 导入结果清单 */
.imp-summary { font-size: 13.5px; margin-bottom: 10px; color: var(--text); }
.imp-list { max-height: 220px; overflow: auto; border: 1.5px solid var(--border); border-radius: 12px; padding: 8px 12px; margin-bottom: 12px; font-size: 13px; line-height: 1.9; }
.imp-item.ok { color: var(--text); }
.imp-item.fail { color: var(--danger); }

/* 会话弹窗分页 */
.session-pager { display: flex; align-items: center; gap: 10px; justify-content: flex-end; margin-top: 12px; font-size: 12.5px; color: var(--text-sub); flex-wrap: wrap; }

/* ===== 需求1/2/3 新增样式 ===== */
/* 表头排序：可点击 + 排序指示符 */
th.sortable { cursor: pointer; user-select: none; white-space: nowrap; }
th.sortable:hover { color: var(--primary); }
.sort-ind { display: inline-block; min-width: 14px; font-size: 11px; color: var(--text-sub); opacity: .55; transition: all .15s; }
.sort-ind.on { color: var(--primary); opacity: 1; font-weight: 800; }
th.sortable:hover .sort-ind { opacity: .9; }

/* 角色分组视图 */
.group-head td {
  background: var(--primary-soft);
  padding: 8px 14px !important;
  border-top: none;
}
.group-tag {
  font-size: 12.5px; font-weight: 800; color: var(--primary);
  padding: 2px 10px; background: #fff; border-radius: 999px;
  box-shadow: 0 1px 4px rgba(27,108,255,.15);
}
.group-count { font-size: 11.5px; color: var(--text-sub); margin-left: 8px; }
.group-member td { border-top: 1px dashed var(--border); }

/* 角色筛选下拉 */
.filter-sep { width: 1px; height: 22px; background: var(--border); margin: 0 4px; }
.filter-select {
  border: 1.5px solid var(--border); border-radius: 999px; padding: 5px 12px;
  font-size: 12.5px; font-family: var(--font); background: #fff; color: var(--text);
  outline: none; cursor: pointer; max-width: 160px;
}
.filter-select:focus { border-color: var(--primary); }

/* 会话弹窗：自己所在行高亮提示 */
.self-session td { background: #FFF9EC !important; }
.self-mark { font-size: 11.5px; color: var(--warning); font-weight: 700; margin-left: 4px; }
</style>
