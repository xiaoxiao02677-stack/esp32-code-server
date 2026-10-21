import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import './styles/global.css'
import { getToken, getUserInfo, hasAdminRole, startTokenCheck, defaultRouteAfterLogin, refreshUserInfo, loadMyDisplayConfig, isModuleConfigLoaded, isModuleVisible } from './lib/api'

import CustomerHome from './views/customer/Home.vue'
import CustomerDevices from './views/customer/Devices.vue'
import CustomerVoices from './views/customer/Voices.vue'
import CustomerPoints from './views/customer/Points.vue'
import AdminHome from './views/admin/Home.vue'
import AdminTemplates from './views/admin/Templates.vue'
import AdminKnowledge from './views/admin/Knowledge.vue'
import AdminUsers from './views/admin/Users.vue'
import AdminAgents from './views/admin/Agents.vue'
import AdminVoices from './views/admin/Voices.vue'
import AdminChat from './views/admin/Chat.vue'
import AdminMemory from './views/admin/Memory.vue'
import AdminModels from './views/admin/Models.vue'
import AdminDevices from './views/admin/Devices.vue'
import AdminParams from './views/admin/Params.vue'
import AdminOta from './views/admin/Ota.vue'
import AdminDicts from './views/admin/Dicts.vue'
import AdminServers from './views/admin/Servers.vue'
import AdminApiDebug from './views/admin/ApiDebug.vue'
import AdminMcp from './views/admin/Mcp.vue'
import AdminLinkSimulator from './views/admin/LinkSimulator.vue'
import AdminWakeWord from './views/admin/WakeWord.vue'
import AdminEntityGraph from './views/admin/EntityGraph.vue'
import AdminTimelineChart from './views/admin/TimelineChart.vue'
import AdminPushScheduler from './views/admin/PushScheduler.vue'
import AdminWeChatOpenClaw from './views/admin/WeChatOpenClaw.vue'
import AdminWeChatClaw from './views/admin/WeChatClaw.vue'
// 用户模块新增页面（admin 端）
import AdminRoles from './views/admin/Roles.vue'
import AdminAuditLog from './views/admin/AuditLog.vue'
import AdminDisplayConfig from './views/admin/DisplayConfig.vue'
import AdminUserDefaults from './views/admin/UserDefaults.vue'
import AdminCustomReview from './views/admin/CustomReview.vue'
// 订单管理页面
import AdminOrders from './views/admin/Orders.vue'
// 用户模块新增页面（customer 端）
import CustomerProfile from './views/customer/Profile.vue'
import CustomerMyModels from './views/customer/MyModels.vue'
import Login from './views/Login.vue'
import NotFound from './views/NotFound.vue'

// 老登录态身份补全：TokenDTO 缺角色字段的旧登录态，刷新后用 /user/info 异步修正按钮可见性
if (getToken()) refreshUserInfo().catch(() => {})

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/customer' },
    { path: '/login', component: Login },
    { path: '/customer', component: CustomerHome },
    { path: '/customer/devices', component: CustomerDevices },
    { path: '/customer/voices', component: CustomerVoices },
    { path: '/customer/points', component: CustomerPoints },
    { path: '/customer/profile', component: CustomerProfile },
    { path: '/customer/my-models', component: CustomerMyModels },
    { path: '/admin', component: AdminHome },
    { path: '/admin/orders', component: AdminOrders },
    { path: '/admin/agents', component: AdminAgents },
    { path: '/admin/voices', component: AdminVoices },
    { path: '/admin/chat', component: AdminChat },
    { path: '/admin/memory', component: AdminMemory },
    { path: '/admin/templates', component: AdminTemplates },
    { path: '/admin/knowledge', component: AdminKnowledge },
    { path: '/admin/models', component: AdminModels },
    { path: '/admin/devices', component: AdminDevices },
    { path: '/admin/params', component: AdminParams },
    { path: '/admin/users', component: AdminUsers },
    { path: '/admin/roles', component: AdminRoles },
    { path: '/admin/audit', component: AdminAuditLog },
    { path: '/admin/display', component: AdminDisplayConfig },
    { path: '/admin/defaults', component: AdminUserDefaults },
    { path: '/admin/custom-review', component: AdminCustomReview },
    { path: '/admin/ota', component: AdminOta },
    { path: '/admin/dicts', component: AdminDicts },
    { path: '/admin/servers', component: AdminServers },
    { path: '/admin/apis', component: AdminApiDebug },
    { path: '/admin/mcp', component: AdminMcp },
    { path: '/admin/linksim', component: AdminLinkSimulator },
    { path: '/admin/wake-word', component: AdminWakeWord },
    { path: '/admin/entity-graph', component: AdminEntityGraph },
    { path: '/admin/timeline-chart', component: AdminTimelineChart },
    { path: '/admin/push-scheduler', component: AdminPushScheduler },
    { path: '/admin/wechat-openclaw', component: AdminWeChatOpenClaw },
    { path: '/admin/wechat-claw', component: AdminWeChatClaw },
    // 404 兜底：未知路径不再渲染空白页
    { path: '/:pathMatch(.*)*', component: NotFound }
  ]
})

// A7 路由守卫：无 token 一律跳登录；已登录不再回登录页
router.beforeEach(async (to) => {
  const has = !!getToken()
  if (!has && to.path !== '/login') return '/login'
  if (has && to.path === '/login') return defaultRouteAfterLogin()
  if (has && to.path.startsWith('/admin')) {
    const info = getUserInfo()
    if (info && !hasAdminRole(info)) return '/customer'
    // 模块可见性（展示配置）：配置未加载时先拉一次（登录后首次导航/刷新直达）
    if (!isModuleConfigLoaded()) await loadMyDisplayConfig()
    // 被展示配置隐藏的模块：URL 直达也拦截（防手输绕过导航）
    if (!isModuleVisible(to.path)) return '/admin'
  }
  return true
})

createApp(App).use(router).mount('#app')

// 启动token过期检查：每30秒检查一次，过期时自动跳转登录页
startTokenCheck(() => {
  // token过期，跳转
  if (!location.hash.startsWith('#/login')) {
    location.hash = '#/login'
  }
})

// 登录态启动时预取生效展示配置（导航模块过滤；失败静默全部可见）
if (getToken()) loadMyDisplayConfig()
