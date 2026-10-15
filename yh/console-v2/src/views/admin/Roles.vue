<template>
  <div>
    <div class="page-head">
      <div>
        <h1>角色 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">角色、权限点与内置标记</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="openCreate">＋ 新增角色</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="hero-row">
      <div class="hero-blob" style="min-height:170px">
        <div>
          <div class="en">ROLES / RBAC</div>
          <h2>角色</h2>
          <p>权限点实时生效，内置角色不可删除</p>
        </div>
        <div class="blob-3d">🎭</div>
      </div>
      <div class="stats-grid">
        <StatCard icon="🎭" label="角色总数" :value="total" />
        <StatCard icon="🧩" label="本页" :value="roles.length" note="当前页" />
        <StatCard icon="✅" label="启用中" :value="enabledCount" />
        <StatCard icon="🔒" label="内置角色" :value="builtinCount" />
      </div>
    </div>

    <DataTable title="角色清单" :total="total" :pages="pages" v-model:page="page" v-model:pageSize="pageSize">
      <template #actions>
        <input v-model="keyword" placeholder="搜索编码 / 名称" style="border:1.5px solid var(--border);border-radius:10px;padding:6px 12px;font-size:12.5px;outline:none" @keyup.enter="search" />
        <button class="btn btn-ghost" style="padding:6px 14px;font-size:12.5px" @click="search">搜索</button>
      </template>
      <table class="data-table">
        <thead>
          <tr><th>角色</th><th>权限点</th><th>用户数</th><th>状态</th><th>备注</th><th>创建时间</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in roles" :key="r.id">
            <td>
              <div class="cell-main">
                {{ r.roleName }}
                <span v-if="r.isBuiltIn === 1" class="badge badge-blue" style="margin-left:6px"><span class="dot"></span>内置</span>
              </div>
              <div class="cell-sub mono">{{ r.roleCode }}</div>
            </td>
            <td>
              <span v-if="r.hasWildcard" class="badge badge-blue" title="拥有全部权限"><span class="dot"></span>全部 *</span>
              <span v-else class="badge" :class="r.permCount > 0 ? 'badge-blue' : 'badge-gray'" :title="(r.permissions || []).join('\n')"><span class="dot"></span>{{ r.permCount }} 项</span>
            </td>
            <td>{{ r.userCount ?? '—' }}</td>
            <td>
              <span class="badge" :class="r.status === 1 ? 'badge-green' : 'badge-gray'">
                <span class="dot"></span>{{ r.status === 1 ? '正常' : '已停用' }}
              </span>
            </td>
            <td style="color:var(--text-sub);max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="r.remark">{{ r.remark || '—' }}</td>
            <td style="color:var(--text-sub)" :title="r.creatorName ? '创建人：' + r.creatorName : ''">{{ r.createDate || '—' }}</td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="openEdit(r)">编辑</button>
                <button class="link-btn danger" :disabled="r.isBuiltIn === 1" :title="r.isBuiltIn === 1 ? '内置角色不可删除' : ''" @click="remove(r)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="roles.length === 0" class="empty-state">
        <div class="empty-icon">🎭</div>
        <strong>暂无角色</strong>
        <p>点击右上角「新增角色」创建第一个</p>
      </div>
    </DataTable>

    <!-- 新增/编辑弹窗 -->
    <div v-if="editor.show" class="modal-mask" @click.self="editor.show = false">
      <div class="modal" style="width:min(720px,94vw);max-height:88vh;overflow:auto">
        <h3>{{ editor.id ? '编辑角色' : '新建角色' }}</h3>
        <div class="edit-grid">
          <div class="form-row">
            <label>角色编码</label>
            <input v-model="editor.roleCode" :readonly="isBuiltinEditing" placeholder="如 operator" />
          </div>
          <div class="form-row">
            <label>角色名称</label>
            <input v-model="editor.roleName" :readonly="isBuiltinEditing" placeholder="如 运营专员" />
          </div>
          <div class="form-row">
            <label>状态</label>
            <select v-model.number="editor.status" :disabled="isBuiltinEditing">
              <option :value="1">启用</option>
              <option :value="0">停用</option>
            </select>
          </div>
          <div class="form-row">
            <label>排序（小的在前）</label>
            <input v-model.number="editor.sort" type="number" min="0" :readonly="isBuiltinEditing" placeholder="0" />
          </div>
        </div>
        <p v-if="isBuiltinEditing" class="field-hint builtin-hint">🔒 内置角色：仅允许修改权限点与备注</p>
        <div class="form-row"><label>备注</label><input v-model="editor.remark" maxlength="200" placeholder="选填" /></div>

        <div class="form-row">
          <label>权限点（已选 {{ editor.permissions.length }} 项）</label>
          <p v-if="editor.permissions.includes('*')" class="field-hint wildcard-hint">该角色含 * 通配符，拥有全部权限</p>
          <div class="perm-groups">
            <div v-for="g in PERM_GROUPS" :key="g.label" class="perm-group">
              <div class="perm-group-head">
                <span class="perm-group-title">{{ g.label }}</span>
                <button type="button" class="link-btn" style="font-size:12px" @click="toggleGroup(g)">{{ isGroupAll(g) ? '✓ 取消全选' : '全选' }}</button>
              </div>
              <div class="perm-items">
                <label v-for="p in g.perms" :key="p" class="perm-item">
                  <input type="checkbox" :value="p" v-model="editor.permissions" style="width:auto" />
                  <span class="perm-code">{{ p }}</span>
                </label>
              </div>
            </div>
          </div>
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
import { computed, inject, onMounted, reactive, ref, watch } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')

// 权限点分组清单（SPEC §2）
const PERM_GROUPS = [
  { label: '用户管理', perms: ['admin:user:list', 'admin:user:create', 'admin:user:update', 'admin:user:delete', 'admin:user:assign', 'admin:user:resetPwd'] },
  { label: '角色管理', perms: ['admin:role:list', 'admin:role:save', 'admin:role:update', 'admin:role:delete'] },
  { label: '配置', perms: ['admin:display:config', 'admin:default:config', 'admin:audit:list', 'admin:custom:audit'] },
  { label: '用户端', perms: ['user:custom:create', 'user:custom:update', 'user:custom:delete', 'user:custom:list'] },
  { label: '菜单', perms: ['menu:admin', 'menu:customer'] }
]

const roles = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const pages = ref(1)
const loading = ref(false)
const saving = ref(false)
const keyword = ref('')

const editor = reactive({
  show: false, id: null, roleCode: '', roleName: '', remark: '',
  sort: 0, status: 1, isBuiltIn: 0, permissions: []
})

const enabledCount = computed(() => roles.value.filter(r => r.status === 1).length)
const builtinCount = computed(() => roles.value.filter(r => r.isBuiltIn === 1).length)
// SPEC §4.1：内置角色仅允许改 permissions/remark，编辑时锁定其余字段
const isBuiltinEditing = computed(() => !!editor.id && editor.isBuiltIn === 1)

function normalizeRole(r) {
  const perms = Array.isArray(r.permissions) ? r.permissions : []
  return {
    id: r.id,
    roleCode: r.roleCode || '',
    roleName: r.roleName || '未命名',
    remark: r.remark || '',
    status: r.status ?? 1,
    isBuiltIn: r.isBuiltIn ?? 0,
    userCount: r.userCount,
    creatorName: r.creatorName || '',
    createDate: r.createDate ? String(r.createDate).slice(0, 10) : '—',
    permCount: perms.length,
    hasWildcard: perms.includes('*'),
    permissions: perms
  }
}

async function load() {
  loading.value = true
  try {
    // GET /admin/role/page —— page 从 1 开始
    const res = await adminApi.rolePage({ page: page.value, limit: pageSize.value, keyword: keyword.value || undefined })
    const data = res.data || {}
    roles.value = (data.list || []).map(normalizeRole)
    total.value = data.total ?? roles.value.length
  } catch (e) {
    toast(e.msg || '加载失败', 'error')
  } finally {
    pages.value = Math.max(1, Math.ceil(total.value / pageSize.value))
    loading.value = false
  }
}

function search() {
  // 页码不为 1 时置 1 由 watch 触发 load，避免双请求
  if (page.value !== 1) page.value = 1
  else load()
}

function openCreate() {
  Object.assign(editor, {
    show: true, id: null, roleCode: '', roleName: '', remark: '',
    sort: 0, status: 1, isBuiltIn: 0, permissions: []
  })
}

async function openEdit(r) {
  // 优先拉详情，失败降级用行数据
  let perms = Array.isArray(r.permissions) ? [...r.permissions] : []
  let src = r
  try {
    const res = await adminApi.roleDetail(r.id)
    if (res.data) {
      const d = res.data
      src = { ...r, ...d }
      perms = Array.isArray(d.permissions) ? [...d.permissions] : perms
    }
  } catch (e) { /* 降级：直接用列表行数据 */ }
  Object.assign(editor, {
    show: true, id: r.id,
    roleCode: src.roleCode || '',
    roleName: src.roleName || '',
    remark: src.remark || '',
    sort: src.sort ?? 0,
    status: src.status ?? 1,
    isBuiltIn: r.isBuiltIn ?? 0,
    permissions: perms
  })
}

function isGroupAll(g) {
  return g.perms.every(p => editor.permissions.includes(p))
}

function toggleGroup(g) {
  if (isGroupAll(g)) {
    const remove = new Set(g.perms)
    editor.permissions = editor.permissions.filter(p => !remove.has(p))
  } else {
    const set = new Set(editor.permissions)
    g.perms.forEach(p => set.add(p))
    editor.permissions = Array.from(set)
  }
}

async function save() {
  if (!editor.roleCode.trim()) { toast('请填写角色编码', 'error'); return }
  if (!editor.roleName.trim()) { toast('请填写角色名称', 'error'); return }
  saving.value = true
  try {
    const body = {
      roleCode: editor.roleCode.trim(),
      roleName: editor.roleName.trim(),
      permissions: editor.permissions,
      remark: editor.remark.trim(),
      sort: Number(editor.sort) || 0,
      status: editor.status
    }
    if (editor.id) await adminApi.roleUpdate({ ...body, id: editor.id })
    else await adminApi.roleSave(body)
    toast('已保存')
    editor.show = false
    load()
  } catch (e) {
    toast(e.msg || '保存失败', 'error')
  } finally {
    saving.value = false
  }
}

function remove(r) {
  askConfirm({
    title: '删除角色',
    message: `确定删除角色「${r.roleName}（${r.roleCode}）」吗？`,
    danger: true,
    onOk: async () => {
      try {
        await adminApi.roleDelete([r.id])
        toast('已删除')
        load()
      } catch (e) {
        // 10227 内置角色不可删 → 后端 msg 直接展示
        toast(e.msg || '删除失败', 'error')
      }
    }
  })
}

watch(page, () => load())
watch(pageSize, () => {
  if (page.value !== 1) page.value = 1
  else load()
})

onMounted(load)
</script>

<style scoped>
.form-row { margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row select, .form-row textarea {
  border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px;
  font-size: 14px; outline: none; font-family: var(--font); background: #fff; color: var(--text);
}
.form-row input:focus, .form-row select:focus { border-color: var(--primary); }
.form-row input[readonly] { background: #F6F8FA; color: var(--text-sub); cursor: not-allowed; }
.field-hint { font-size: 11.5px; color: var(--text-sub); margin: 2px 0 0; }
.wildcard-hint { color: var(--warning); }
.builtin-hint { margin: 6px 0 12px; color: var(--warning); }
.form-row select:disabled { background: #F6F8FA; color: var(--text-sub); cursor: not-allowed; }
.edit-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px 16px; }
.modal h3 { font-size: 17px; margin-bottom: 18px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.perm-groups { display: flex; flex-direction: column; gap: 10px; }
.perm-group { border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 12px; }
.perm-group-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.perm-group-title { font-size: 13px; font-weight: 600; color: var(--text); }
.perm-items { display: flex; flex-wrap: wrap; gap: 8px 14px; }
.perm-item { display: flex; align-items: center; gap: 6px; cursor: pointer; }
.perm-code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; color: var(--text-sub); }
</style>
