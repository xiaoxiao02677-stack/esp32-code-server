# console-v2 前端骨架侦察报告（用户管理模块改造模板基线）

> 侦察范围：`G:/demo/21_xiaozhi/console-v2`（只读）。Vue 3.4 + Vite 5 + vue-router 4（**hash 路由**），**无 UI 库、无状态管理库**，全部手写组件 + 全局 CSS。本文档是用户管理模块前端实施的唯一信息来源。

---

## 0. 技术栈与项目结构速览

```
console-v2/
├── index.html                  # <title>屿禾工坊</title>，挂载点 #app
├── vite.config.js              # base: mode==='admin' ? '/admincc/' : '/'；outDir: dist-admin / dist
├── package.json                # scripts: dev / build / preview（无 lint、无 test）
│     deps: vue ^3.4, vue-router ^4.3, sm-crypto 0.3.14（SM2 登录加密）
├── deploy.sh                   # npm run build → scp -P 22222 dist/* → /var/www/console-v2/admin/
├── scripts/deploy.py           # paramiko 打包上传 dist→/var/www/console-v2/app、dist-admin→/admin
├── src/
│   ├── main.js                 # 路由表 + 路由守卫 + startTokenCheck（88 行）
│   ├── App.vue                 # provide('toast') / provide('askConfirm')，95 行
│   ├── lib/api.js              # request 封装 + authApi + customerApi + adminApi（380 行）
│   ├── lib/apiCatalog.js       # 原控制台 173 接口目录（ApiDebug 页展示用，非运行时依赖）
│   ├── components/             # DataTable / DockNav / StatCard / Toasts / TopBar
│   ├── styles/global.css       # 唯一样式文件（446 行，设计系统 + 6 主题 + 紧凑模式）
│   └── views/
│       ├── Login.vue           # 账密+验证码，SM2 加密
│       ├── admin/              # 23 个管理端页面
│       └── customer/           # 4 个用户端页面（Home/Devices/Voices/Points）
└── dist/ dist-admin/           # 构建产物（dist/index.html 标题被手动改为「测试环境」）
```

**构建**：`npm run build`（客户端 → `dist/`，base `/`）；管理端构建需 `vite build --mode admin`（→ `dist-admin/`，base `/admincc/`）。dev 端口 5180。

---

## 1. 用户管理页现状（src/views/admin/Users.vue，151 行）

现有功能：用户分页列表 + 手机号搜索 + 重置密码 + 封禁/解封 + 删除。

### 1.1 调用的 API（全部在 `adminApi`）

| 调用处 | API | HTTP |
|---|---|---|
| load() L92 | `adminApi.userPage({ page, limit: 4, mobile })` | GET /admin/users |
| resetPwd() L116 | `adminApi.resetPassword(u.id)` | PUT /admin/users/{id} |
| toggleStatus() L130 | `adminApi.changeUserStatus([u.id], next)` | PUT /admin/users/changeStatus/{status}，body=[ids] |
| remove() L142 | `adminApi.deleteUser(u.id)` | DELETE /admin/users/{id} |

### 1.2 数据规约（load 函数 L88-107）

- 响应 `res.data = { list: [...], total }`，`list[]` 字段：`userid`（或 `id`）、`username`、`mobile`、`status`、`deviceCount`、`createDate`。
- 映射为 `id: u.userid ?? u.id`、`createDate: String(u.createDate).slice(0, 10)`。
- **status 语义（manager-api Oauth2Realm:100）**：`status=1 正常`，`status=0 锁定/封禁`。
- `changeUserStatus` body 是 **id 数组**（契约对齐 cc-console）。
- 分页 page **从 1 开始**；当前页写死 limit=4（改造点：可接 pageSize）。

### 1.3 页面结构

- `page-head`（标题+刷新按钮）→ `hero-row`（hero-blob + 4 个 StatCard）→ `DataTable`（含搜索 actions slot + table + empty-state）。
- 表格列：用户(cell-main/cell-sub) / 设备数 / 状态 badge / 注册时间 / row-actions。
- 操作按钮用 `.row-actions > .link-btn`（danger 类红色），危险操作前一律 `askConfirm`。
- **无新增用户入口**（后端 Login.vue 提示「新用户注册请联系管理员」；apiCatalog 有 `POST /user/register registerForm(body)` 契约但前端未实现调用）。

---

## 2. API 层（src/lib/api.js）

### 2.1 request() 封装（L106-157）

- `API_BASE = '/yuhe'`（反代 → manager-api:8002，同源无 CORS）。
- 鉴权：`headers.Authorization = 'Bearer ' + getToken()`，token 存 localStorage key `cc_token`（JSON: `{token, expire, loginAt}`；自动从旧 `v2_token` 迁移）。
- body 默认 JSON.stringify + Content-Type: application/json；`formData` 走 FormData；`rawBody` 直传（ASR 音频）；`raw: true` 返回原始 Response（ttsPreview 等自己 fetch）。
- **错误行为**：
  - fetch 网络异常 → `throw { code: -1, msg: '网络异常，请检查连接' }`
  - 响应非 JSON → `throw { code: resp.status, msg: '响应解析失败 (HTTP x)' }`
  - `data.code === 401`：会话类接口（`/user/info`、`/user/pub-config`）或 token 已过期 → 清 token + 跳 `#/login`；非会话接口 401 仅抛 `{code:401, msg}` 给调用方（HTTP 层可能 200）
  - `data.code !== 0` → `throw { code, msg: data.msg || '操作失败' }`（**Java 业务约定 code=0 成功**）
  - 成功 → 返回整个 `data`（即 `{code, msg, data}`；调用方 `res.data` 取业务数据）
- **调用方约定**：catch 里 `toast(e.msg || 'xx失败', 'error')`。
- HTTP 403 无特殊处理，走 `code!==0` 分支抛错。

### 2.2 api 快捷方法（L159-165）

```js
export const api = {
  get: (p, params) => request('GET', p, { params }),
  post: (p, body) => request('POST', p, { body }),
  put: (p, body) => request('PUT', p, { body }),
  del: (p) => request('DELETE', p),
  upload: (p, formData) => request('POST', p, { formData })
}
```
页面可直接 `import { api } from '../../lib/api'` 调未封装端点（见 admin/Devices.vue L183 `api.post('/device/bind/...')`）。

### 2.3 authApi（L168-187）

- `captchaUrl(uuid)`：`/yuhe/user/captcha?uuid=...`（img src 直用）
- `pubConfig()`：GET /user/pub-config → `{ sm2PublicKey, ... }`
- `login(username, password, captcha, captchaId)`：password = `'04' + sm2.doEncrypt(captcha + password, pubKey, 1)`，POST /user/login；成功后 `setToken(JSON.stringify({...res.data, loginAt: Date.now()}))`
- `userInfo()`：GET /user/info
- token 30s 定时检查（main.js 里 `startTokenCheck`），过期自动踢登录页。

### 2.4 adminApi 端点全表（按 api.js 分组，L202-380）

**智能体（L204-220）**
| 方法 | 路径 | 用途 |
|---|---|---|
| GET | /agent/list | 智能体列表 |
| GET | /agent/{id} | 智能体详情 |
| POST | /agent | 创建（body 含 agentName 等，可带 templateId） |
| PUT | /agent/{id} | 更新 |
| DELETE | /agent/{id} | 删除 |
| POST | /device/bind/{agentId}（body={}） | 查已绑定设备 |
| POST | /device/bind/{agentId}/{code} | 按 6 位验证码绑定 |
| GET | /agent/{agentId}/sessions?page&limit | 会话分页 |
| GET | /agent/mcp/address/{agentId} | MCP 接入点 |
| GET | /agent/mcp/tools/{agentId} | MCP 工具列表 |
| GET | /agent/mcp/test/{agentId} | MCP 测试 |
| GET | /agent/mcp/config/{agentId} | MCP 配置读取 |
| POST | /agent/mcp/config | 保存 MCP 配置 |
| DELETE | /agent/mcp/config/{agentId} | 删 MCP 配置 |
| POST | /agent/mcp/config/validate | 校验 serverJson |

**聊天记录（L223-232）**
| GET | /agent/{agentId}/chat-history/{sessionId} | 聊天记录 |
| POST | /agent/audio/{audioId} | 换 realId |
| DELETE | /agent/{agentId}/chat-history/{sessionId} | 删会话 |
| GET(fetch blob) | /agent/play/{realId} | 播音频 blob |

**音色/TTS（L235-248）**
| GET | /models/list?modelType=TTS&page&limit | TTS 引擎列表 |
| GET | /models/{modelId}/voices | 引擎下音色 |
| GET(fetch blob) | /models/ttsPreview?modelId&voice&text | 试听 |
| GET | /ttsVoice（params） | 音色分页 |
| POST | /ttsVoice | 建音色 |
| PUT | /ttsVoice/{id} | 改音色 |
| POST | /ttsVoice/delete（body=[id]） | 删音色 |
| GET | /voiceClone/play/{id} | 克隆音色播放 |

**记忆（L251-262）**
| GET | /memory/agents | 有记忆的智能体 |
| GET | /memory/facts | 事实分页 |
| POST | /memory/facts（body: agent_id, content） | 建事实 |
| PUT | /memory/facts/{factId} | 改事实 |
| DELETE | /memory/facts/{factId}?agent_id= | 删事实 |
| POST | /memory/facts/{factId}/feedback | 反馈 |
| POST | /memory/facts/{factId}/review | 审核 |
| PUT | /models/Memory/{providerCode}/{engine} | 记忆引擎配置 |
| GET | /memory/entities/{agentId} | 实体列表 |
| GET | /memory/entities/{agentId}/graph | 实体图谱 |
| POST | /memory/agents/{agentId}/summarize | 快速总结 |
| GET | /memory/timeline/{agentId}/chart?days=30 | 时间线图 |

**模型（L265-273）**
| GET | /models/list?modelType=&page=&limit= | 模型分页 |
| GET | /models/names?modelType= | 模型名下拉 [{id, modelName}] |
| GET | /models/{id} | 模型详情 |
| GET | /models/{type}/provideTypes | 供应器列表（动态表单） |
| POST | /models/{type}/{providerCode} | 建模型 |
| PUT | /models/{type}/{providerCode}/{id} | 改模型 |
| DELETE | /models/{id} | 删模型 |
| GET | /models/modelTest?modelId&modelType | 连通测试 |
| PUT | /models/enable/{id}/{status} | 启停 |

**设备（L275-278）**
| GET | /admin/device/all（params） | 全量设备分页 |
| PUT | /device/update/{id}（body:{alias}） | 设备改名 |
| POST | /device/manual-add（body:{board,appVersion,macAddress}） | 手动加设备 |
| POST | /device/unbind（body:{deviceId}） | 解绑 |

**系统参数（L281-284）**
| GET | /admin/params/page | 参数分页 |
| PUT | /admin/params | 改参数 |
| POST | /admin/params | 建参数 |
| DELETE | /admin/params/{id} | 删参数 |

**运维（L288-289）**
| POST | /admin/server/emit-action | 服务动作（Python 重启等） |
| POST | /admin/server/restart-manager | 重启 Java |

**用户（L294-298）★本模块核心**
| 方法 | 路径 | 用途 |
|---|---|---|
| GET | /admin/users（params: page, limit, mobile） | 用户分页列表 → data={list,total} |
| PUT | /admin/users/{id} | 重置密码（重置为默认密码） |
| DELETE | /admin/users/{id} | 删除用户 |
| PUT | /admin/users/changeStatus/{status}（body: ids[]） | 批量封禁/解封，status: 1正常/0锁定 |

**模板（L301-308）**
| GET | /agent/template | 模板列表 |
| GET | /agent/template/page | 模板分页 |
| GET | /agent/template/{id} | 模板详情 |
| POST | /agent/template | 建模板 |
| PUT | /agent/template | 改模板 |
| DELETE | /agent/template/{id} | 删模板 |
| POST | /agent/template/batch-remove（body: ids） | 批量删 |
| GET | /agent/tag/list | 标签列表 |

**知识库（L311-317）**：GET/POST/PUT/DELETE /datasets、GET /datasets/{id}/documents、GET /datasets/rag-models

**OTA（L320-329）**：GET /otaMag、POST /otaMag/upload（FormData fetch）、DELETE /otaMag/{id}、GET /otaMag/getDownloadUrl/{id}

**字典（L332-335）**：GET /admin/dict/type/page、GET /admin/dict/data/type/{dictType}、POST /admin/dict/data/update|/save（按有无 id 分路径）、POST /admin/dict/data/delete（body: ids）

**替换词（L338-341）**：GET /correct-word/file/list、POST/PUT/DELETE /correct-word/file

**服务器节点（L344）**：GET /admin/server/server-list

**链路模拟（L347-350）**：POST /models/asrRecognize（rawBody blob）、GET /models/llmPreview

**唤醒词（L353-356）**：GET/POST /agent/wake-word/{agentId}、GET /api/wake-word/devices、POST /api/wake-word/push

**推送调度（L361-367）**：GET /api/push/tasks、POST /api/push/schedule、GET /api/push/tasks/{pushId}、GET /api/wake-word/devices

**微信 Claw（L370-379）**：/wechat/claw/* 系列（users/bind/unbind/conversations/messages/schedules）

### 2.5 customerApi（L190-199）

agentList / agentDetail / createAgent / deleteAgent / boundDevices(GET) / voiceClonePage / voiceResourcePage / ttsVoicePage。

### 2.6 用户注册相关契约（apiCatalog.js L39，前端未接入）

```
POST /user/register   registerForm(body)   注册账号
POST /user/smsVerification  data(body)     发送短信验证码
PUT  /user/retrieve-password phone,code,password(body)  找回密码
PUT  /user/change-password  old/newPassword(body)       修改密码
```
新增注册/改密功能时在 api.js 里新增封装即可（参考现有写法：`api.post('/user/register', body)`）。

---

## 3. 标准页面骨架（模板代码，摘自 Agents.vue / Models.vue / Devices.vue / Templates.vue）

### 3.1 列表页整体骨架（Agents.vue L1-45）

```html
<template>
  <div>
    <!-- ① 页头：标题 + 动作按钮 -->
    <div class="page-head">
      <div>
        <h1>智能体 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">副标题说明</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" @click="openCreate">＋ 新增智能体</button>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <!-- ② 统计卡（可选 hero-row：左 hero-blob + 右 stats-grid） -->
    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="🤖" label="智能体" :value="agents.length" />
      <StatCard icon="📡" label="绑定设备" :value="boundTotal" />
    </div>

    <!-- ③ DataTable 面板：#actions slot 放搜索，默认 slot 放表格 -->
    <DataTable title="智能体清单" :total="agents.length" :page="1" :pages="1">
      <template #actions>
        <input v-model="mobile" placeholder="搜索手机号" style="border:1.5px solid var(--border);border-radius:10px;padding:6px 12px;font-size:12.5px;outline:none" @keyup.enter="search" />
        <button class="btn btn-ghost" style="padding:6px 14px;font-size:12.5px" @click="search">搜索</button>
      </template>
      <table class="data-table">
        <thead><tr><th>智能体</th><th>模型</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="a in agents" :key="a.id">
            <td>
              <div class="cell-main">{{ a.name }}</div>
              <div class="cell-sub">{{ a.boundCount ? `📡 ${a.boundCount} 台设备` : '未绑定设备' }}</div>
            </td>
            <td>
              <span class="badge" :class="a.status === 1 ? 'badge-green' : 'badge-gray'">
                <span class="dot"></span>{{ a.status === 1 ? '正常' : '已封禁' }}
              </span>
            </td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="openEdit(a)">编辑</button>
                <button class="link-btn danger" @click="remove(a)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <!-- 空状态 -->
      <div v-if="agents.length === 0" class="empty-state">
        <div class="empty-icon">🤖</div><strong>暂无智能体</strong>
        <p>点击右上角「新增智能体」创建第一个</p>
      </div>
    </DataTable>
  </div>
</template>
```

### 3.2 真分页写法（DataTable 的 v-model，admin/Devices.vue L20 + L212）

```html
<DataTable title="设备列表" :total="total" :pages="pages"
           v-model:page="page" v-model:pageSize="pageSize">
```
```js
const page = ref(1); const pageSize = ref(20); const pages = ref(1)
watch([page, pageSize], () => load())
// load 里：pages.value = Math.max(1, Math.ceil(total.value / pageSize.value))
```
DataTable 组件（src/components/DataTable.vue）：props `title/hint/total/page/pageSize(默认20)/pages`，emits `update:page`/`update:pageSize`，pageSize 选项 [4,8,20,50]，`total>0` 时渲染 pager。Templates.vue 的 watch 写法（L160-164）处理了改 pageSize 回第 1 页。

### 3.3 新增/编辑弹窗骨架（Agents.vue L67-164 + Dicts.vue L48-60）

```html
<!-- 编辑弹窗：modal-mask + modal，@click.self 点遮罩关闭 -->
<div v-if="editor.show" class="modal-mask" @click.self="editor.show = false">
  <div class="modal" style="width:min(640px,94vw);max-height:88vh;overflow:auto">
    <h3>{{ editor.id ? '编辑智能体' : '新建智能体' }}</h3>
    <!-- 单列表单 -->
    <div class="form-row"><label>名字</label><input v-model="form.agentName" placeholder="..." /></div>
    <!-- 下拉 -->
    <div class="form-row"><label>大脑（LLM）</label>
      <select v-model="form.llmModelId">
        <option v-for="m in opts.LLM" :key="m.id" :value="m.id">{{ m.modelName }}</option>
      </select>
    </div>
    <!-- 多列网格（Agents scoped style .edit-grid） -->
    <!-- <div class="edit-grid"> ...多个 form-row... </div> -->
    <div class="form-row"><label>人设提示词</label>
      <textarea v-model="form.systemPrompt" rows="5" placeholder="..."></textarea>
    </div>
    <div class="modal-actions">
      <button class="btn btn-ghost" @click="editor.show = false">取消</button>
      <button class="btn btn-primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
    </div>
  </div>
</div>
```

script 模式（reactive editor + openCreate/openEdit/save 三件套，Dicts.vue L103-108）：
```js
const editor = reactive({ show: false, id: '', fieldA: '', fieldB: '' })
const saving = ref(false)

function openCreate() { Object.assign(editor, { show: true, id: '', fieldA: '', fieldB: '' }) }
function openEdit(row) { Object.assign(editor, { show: true, id: row.id, fieldA: row.a, fieldB: row.b }) }

async function save() {
  if (!editor.fieldA) { toast('请填写xx', 'error'); return }
  saving.value = true
  try {
    const body = { fieldA: editor.fieldA, fieldB: editor.fieldB }
    if (editor.id) await adminApi.updateXxx({ ...body, id: editor.id })
    else await adminApi.createXxx(body)
    toast('已保存'); editor.show = false; load()
  } catch (e) { toast(e.msg || '保存失败', 'error') }
  finally { saving.value = false }
}
```

### 3.4 删除确认（askConfirm 标准用法，Agents.vue L408-416）

```js
function remove(a) {
  askConfirm({
    title: '删除智能体',
    message: `确定删除「${a.name}」吗？此操作不可恢复。`,
    danger: true,           // 确定按钮变红
    okText: '确定',          // 可选，默认「确定」
    onOk: async () => {      // 关窗后立即执行；失败由调用方 toast
      try { await adminApi.deleteAgent(a.id); toast('已删除'); load() }
      catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}
```

### 3.5 toast 调用（Users.vue L76）

```js
const toast = inject('toast')
toast('密码已重置')                 // 成功（绿，默认 2600ms）
toast(e.msg || '加载失败', 'error') // 错误（红）
toast('功能即将上线', 'info')       // 提示（蓝）
toast('长文案', 'success', 5000)   // 第 3 参自定义时长 ms
```

### 3.6 开关/标签/复选等控件写法

- **状态徽章**（Users.vue L47-49）：
  ```html
  <span class="badge" :class="u.status === 1 ? 'badge-green' : 'badge-gray'">
    <span class="dot"></span>{{ u.status === 1 ? '正常' : '已封禁' }}
  </span>
  ```
- **启停切换按钮**（Models.vue L53 + L262-270）：`<button class="link-btn" @click="toggle(m)">{{ m.isEnabled ? '停用' : '启用' }}</button>`，成功后就地翻转 `m.isEnabled = next` + toast，不整页刷新。
- **类型 chip 筛选**（Models.vue L21-25 + scoped `.chip`）：
  ```html
  <div v-for="t in MODEL_TYPES" :key="t.value" class="chip" :class="{ active: activeType === t.value }" @click="pickType(t.value)">{{ t.label }}</div>
  ```
  `.chip` scoped 样式（Models.vue L399-400）：`padding:8px 14px; border-radius:999px; background:var(--bg-card); border:1.5px solid var(--border)`，`.chip.active` 高亮 primary。Dicts.vue 也用同款。
- **checkbox**（Voices.vue L64-67）：
  ```html
  <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
    <input type="checkbox" v-model="editor.dynamicInstruction" style="width:auto" /> ✔ 动态更新
  </label>
  ```
  批量勾选（PushScheduler.vue L75-79）：`<input type="checkbox" :value="d" v-model="form.deviceIds" />` + 全选 `<input type="checkbox" :checked="allSelected" @change="toggleAll" />`。
- **select 数字绑定**：`<select v-model.number="form.chatHistoryConf">` 配 `<option :value="0">`。
- **行内提示**：`<p class="field-hint">说明文字</p>`（Agents.vue scoped L430）。

---

## 4. 路由与导航（新增页面必改 4 处）

### 4.1 src/main.js

- import 区（L7-34）：`import AdminUsers from './views/admin/Users.vue'`
- 路由表（L38-68）：`{ path: '/admin/users', component: AdminUsers }`（当前 L55）
- hash 路由 `createWebHashHistory()`，URL 形如 `https://host/#/admin/users`
- 路由守卫（L72-77）：无 token 一律 → /login；已登录访问 /login → /customer。**新增页面无需动守卫**。
- 带 query 跳转参考：`router.push({ path: '/admin/chat', query: { agentId, sessionId } })`（Agents.vue L398）

### 4.2 src/components/DockNav.vue —— adminItems 数组（L104-124）

```js
const adminItems = [
  { to: '/admin', icon: '🏠', label: '概览' },
  ...
  { to: '/admin/users', icon: '👥', label: '用户' },   // L115
  ...
]
```
customerItems（L98-103）同理。**新页面在此加一行**，图标用 emoji。

### 4.3 src/components/TopBar.vue —— adminNav 数组（L60-84）

Ctrl+K 快速跳转搜索的映射表，**与 DockNav 保持一致**（注释 L59 明确要求「路径与 DockNav.vue 完全一致」，当前两表有几项不同步如 entity-graph，新页面建议两处都加）：
```js
const adminNav = [
  { label: '用户', path: '/admin/users', icon: '👥' },   // L71
  ...
]
```
customerNav（L85-90）。

### 4.4 src/lib/api.js —— 新端点封装

adminApi 对象内按分组注释追加（用户组在 L294-298 `// ===== 用户 =====` 段）。新端点写法一行：
```js
userCreate: (body) => api.post('/user/register', body),
```

---

## 5. App.vue：provide 与组件挂载（95 行）

```
provide('toast', toast)        // toast(msg, type='success', ms=2600)
provide('askConfirm', askConfirm)  // askConfirm({ title, message, okText, danger, onOk })
```
- toast 实现（L44-48）：转发给 `<Toasts ref="toastsRef" />`（fixed 右上角堆叠，success 绿/error 红/info 蓝，slideIn 动画）。
- askConfirm 实现（L51-55）：填充 reactive `confirm`，App.vue 模板 L9-20 渲染确认弹窗（.modal-mask > .modal.confirm，取消/确定按钮，danger 时确定键变红 `.btn.danger`）。**点击 OK 立即关窗再执行回调**（L58-62），异步失败靠调用方 toast。
- 组件挂载（L5-8）：`<TopBar :role="role" @switch-role="switchRole" />` + `<router-view />` + `<DockNav :role="role" @toggle-compact="onToggleCompact" />` + `<Toasts ref="toastsRef" />`。
- role = `route.path.startsWith('/admin') ? 'admin' : 'customer'`（L34），body class `role-admin`。
- 页面里标准 inject 组合：`const toast = inject('toast'); const askConfirm = inject('askConfirm')`。

---

## 6. 样式系统（src/styles/global.css，446 行）

### 6.1 CSS 变量（:root L2-27）

| 变量 | 值 | 用途 |
|---|---|---|
| --primary | #1B6CFF | 主色（按钮/链接/高亮） |
| --primary-hover / --primary-soft | #0F5AE0 / #EAF2FF | 悬停 / 浅底 |
| --bg / --surface | #F5F7FA / #FFFFFF | 页面底 / 卡片面 |
| --text / --text-sub | #1A2233 / #8A94A6 | 主文字 / 次文字 |
| --border | #E8ECF2 | 边框 |
| --teal-1/2/3 | #B8F3E2/#6FE0C6/#37C8A8 | hero-blob 渐变 |
| --orange / --success / --danger / --warning | #FF7A45 / #2FBF71 / #F0534D / #F5A623 | 语义色 |
| --radius-lg/md/pill | 24/16/999px | 圆角 |
| --shadow-dock / --shadow-card | ... | 阴影 |
| --font | PingFang SC... | 全局字体 |

### 6.2 可复用类清单

**布局/页面**
| 类 | 效果 |
|---|---|
| `.page-head` + `.sub` + `.head-actions` | 页头：标题行 + 副标题 + 右侧按钮组（flex between） |
| `.hero-row` | 300px hero + 1fr 统计的双列 grid（<900px 折单列） |
| `.hero-blob` + `.en`/`h2`/`p`/`.blob-3d`/`.blob-actions` | 青绿渐变有机插画区（圆角 26px，blobFloat 动画） |
| `.stats-grid` | 4 列统计卡 grid（<900px 折 2 列） |
| `.panel` / `.panel-head`(+`h3::before` 圆点 / `.hint`) | 白底圆角卡片 / 卡片头（DataTable 外壳） |
| `.app-shell` / `.app-canvas` | 全局画布（左 padding 让位 dock） |

**按钮**
| 类 | 效果 |
|---|---|
| `.btn` | 基础按钮（pill 圆角，inline-flex） |
| `.btn-primary` | 蓝底白字带投影，hover 上浮 |
| `.btn-ghost` | 白底描边，hover 变蓝 |
| `.btn:disabled` | 透明度 .45 禁用 |
| `.btn.danger` | 红底（App.vue 定义） |
| `.link-btn` | 行内文字按钮（蓝字），hover 浅蓝底 |
| `.link-btn.danger` | 红字，hover 红底 |
| `.row-actions` | 表格操作列 flex 容器 |

**表格**
| 类 | 效果 |
|---|---|
| `.data-table` | 全宽表格，th 灰底小字，td 底边框，行 hover #F8FAFE |
| `.cell-main` / `.cell-sub` | 单元格主行（粗体 14px）/ 副行（灰 12px） |

**徽章**
| 类 | 效果 |
|---|---|
| `.badge`（内含 `.dot`） | pill 徽章 + 前置圆点 |
| `.badge-green` / `.badge-gray` / `.badge-blue` / `.badge-orange` | 绿(正常)/灰(停用)/蓝(信息)/橙(警告) |

**空状态**
| 类 | 效果 |
|---|---|
| `.empty-state` | 居中列布局 padding 52px 0 |
| `.empty-icon` | 74px 虚线圆 + emoji |
| 用法：`<div class="empty-state"><div class="empty-icon">👥</div><strong>暂无用户</strong><p>引导文案</p></div>` |

**分页**
| 类 | 效果 |
|---|---|
| `.pager` / `.page-btn(.active/.wide)` | DataTable 内置（共 N 条 + 条/页 select + 首页/‹/页码/›/下一页） |

**弹窗（modal-mask/modal 定义在 App.vue 的非 scoped style，全局可用）**
| 类 | 效果 |
|---|---|
| `.modal-mask` | fixed 全屏遮罩 rgba(15,22,40,.45) grid 居中，z-index 150 |
| `.modal` | 白底圆角 20px，宽 min(440px,92vw)，可 inline style 加宽 `width:min(640px,94vw);max-height:88vh;overflow:auto` |
| `.modal.confirm h3/p` | 确认弹窗排版 |
| `.modal-actions` | 右对齐按钮组 |

**表单**（⚠️ `.form-row` 不在 global.css！各页面 scoped 自带，标准定义如下，新页面照抄进 scoped）
```css
.form-row { margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--text-sub); font-weight: 600; }
.form-row input, .form-row textarea, .form-row select {
  border: 1.5px solid var(--border); border-radius: 12px; padding: 10px 14px;
  font-size: 14px; outline: none; font-family: var(--font); background: #fff;
}
.form-row input:focus, .form-row textarea:focus, .form-row select:focus { border-color: var(--primary); }
.field-hint { font-size: 11.5px; color: var(--text-sub); margin: 2px 0 0; }
/* 多列表单网格（Agents.vue） */
.edit-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px 16px; }
```

### 6.3 主题机制

- `<html data-theme="blue|kawaii|dark|purple|green|morandi">` 覆盖 CSS 变量（L359-437）；localStorage key `cc_theme`；DockNav 底部色板切换（DockNav.vue L67-82）。
- dark 主题对 .dock/.data-table/.badge-gray/.searchbox/.modal 有专门覆盖。**写新页面只用 var(--xxx) 就自动适配全部主题；硬编码色值（如 #fff 背景）在 dark 下会突兀，弹窗内 input 背景 global 无定义、各页 scoped 写 `background:#fff`，dark 主题 .modal 背景被覆盖为深色，可接受（现有页均如此）。**

### 6.4 紧凑模式 & dock 折叠

- 紧凑：`.app-shell.shell-compact` 下缩表格 padding 等（L440-445）；由 DockNav 底部 ⚅ 按钮触发 emit → App.vue 存 localStorage `cc_compact`。
- dock 折叠：`html.dock-collapsed`（--dock-w 56px，隐藏文字），localStorage `cc_dock_collapsed`。

---

## 7. 用户端（customer/）页面模式

4 页：Home（智能体+创建弹窗）、Devices（设备列表+详情弹窗+解绑）、Voices（音色列表+试听）、Points（占位页）。

**模式总结**（与 admin 的差异）：
1. API 用 `customerApi`（数据视角=当前登录用户自己的资源），但 Voices.vue 也直接用了 `adminApi.ttsPreview` 试听。
2. 页面骨架与 admin 完全一致：page-head → hero-row（hero-blob 带 `.blob-actions` 按钮组 + stats-grid）→ DataTable → 弹窗。
3. **加载失败静默降级**：catch 里 `if (!warned) { warned = true; toast(...) }`——只提示一次，数据置空数组（Home L132-136、Devices L163-168、Voices L106-109），admin 页则每次都 toast。
4. 空状态文案更引导性：「还没有绑定任何设备，去创建智能体并绑定设备吧」。
5. 设备数据是聚合出来的：agentList → 对每个 agent `boundDevices(agentId)` → 按 id/macAddress 去重（Devices.vue L126-169）。
6. **Points.vue 是纯占位页模板**（58 行）：StatCard 全部 value="—" note="敬请期待"，按钮 `disabled title="功能即将上线"`，表体空 + `.empty-state` 引导 + `toast('功能即将上线', 'info')`。**模型为 0 / 功能未上线时的空状态参考此页**。
7. Voices.vue（音色选择 UI）：可试听行 `▶` link-btn + playingId 防重入；不可试听（缺 ttsModelId）行 disabled 按钮 + title 提示「请到管理端试听」——**权限/数据缺失的降级交互范式**。
8. 弹窗 scoped 样式自带完整 `.modal-mask/.modal/.form-row/.modal-actions`（Home L178-190）——用户端页面 modal 类不走 App.vue（App.vue 的 style 非 scoped 其实全局生效，两处定义重复但不冲突）。

---

## 8. 空状态约定

- 无独立组件，纯 CSS 类组合（global.css L244-251），模板惯例：
  ```html
  <div v-if="list.length === 0" class="empty-state">
    <div class="empty-icon">🎯emoji</div>
    <strong>主文案</strong>
    <p>引导副文案（可省）</p>
    <!-- 可选加按钮，如 Points.vue： -->
    <!-- <button class="btn btn-ghost" @click="...">引导动作</button> -->
  </div>
  ```
- 放在 DataTable 默认 slot 内、`</table>` 之后；条件用 `v-if="xxx.length === 0"`（Dicts.vue 还有二级态：未选类型时 `v-if="!activeType"` 显示「先选择字典类型」）。
- loading 中不隐藏表格（现有页不做 loading 骨架屏，仅按钮文案变「加载中…」+ disabled）。

---

## 9. 新增/改造页面 checklist（改动文件清单）

以「新增管理端页面 /admin/xxx」为例：

| # | 文件 | 改动 |
|---|---|---|
| 1 | `src/views/admin/Xxx.vue` | 新建页面（复制 Users.vue/Dicts.vue 骨架） |
| 2 | `src/main.js` | L7-34 import 区加一行 import；L38-68 routes 数组加 `{ path: '/admin/xxx', component: AdminXxx }` |
| 3 | `src/components/DockNav.vue` | L104-124 adminItems 数组加 `{ to: '/admin/xxx', icon: '🎯', label: 'xx' }` |
| 4 | `src/components/TopBar.vue` | L60-84 adminNav 数组加 `{ label: 'xx', path: '/admin/xxx', icon: '🎯' }` |
| 5 | `src/lib/api.js` | adminApi 对象内对应分组注释下加端点（用户相关加在 L294-298「===== 用户 =====」段） |
| 6 | （仅用户端页面）main.js customer 路由 + DockNav customerItems + TopBar customerNav 三处同步加 |

改造现有 Users.vue 则只需改 1、5。

**构建部署**：`npm run build`（dist/，客户端 base=/）+ `vite build --mode admin`（dist-admin/，base=/admincc/）。服务器 sandyun.top:22222，目录 /var/www/console-v2/app 与 /admin（nginx location / 与 /admincc/）。dist/index.html 标题当前被手动改为「测试环境」（源码 index.html 是「屿禾工坊」）。

---

## 10. 关键惯例速记（实施 agent 必读）

1. **script setup** + `inject('toast')` / `inject('askConfirm')`；组件从 `../../components/Xxx.vue` 相对导入。
2. API 一律 `import { adminApi } from '../../lib/api'`（或 customerApi / api）。
3. 列表 load()：`loading.value = true → try{ res = await api(...); 映射字段 } catch(e){ toast(e.msg||'加载失败','error') } finally{ loading.value = false }`；`onMounted(load)`。
4. 写操作三件套：校验 → `saving.value = true` → try/catch/finally → 成功 `toast('已xx'); 关弹窗; load()`。
5. 危险操作（删除/解绑/封禁）必须 `askConfirm({ danger: true, onOk: async () => {...} })`。
6. 时间显示惯例：`String(ts).slice(0, 10)`（日期）或 `.slice(5, 16)`（月日时分），不引日期库。
7. 响应结构统一 `res.data`；列表页 `data.list` + `data.total`；`total ?? list.length` 兜底。
8. 表格行 key 用业务 id；操作列固定在最后一列 `.row-actions`。
9. emoji 做图标；按钮文案「＋ 新增」「↻ 刷新」「✎ 改名」等前缀风格。
10. 所有新 CSS 优先复用 global.css 类；页面特有样式写 scoped（参考各页的 .form-row 拷贝惯例）。
