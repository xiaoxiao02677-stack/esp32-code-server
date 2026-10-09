import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import './styles/global.css'
import { getToken } from './lib/api'

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
import AdminCorrectWords from './views/admin/CorrectWords.vue'
import AdminServers from './views/admin/Servers.vue'
import AdminApiDebug from './views/admin/ApiDebug.vue'
import AdminMcp from './views/admin/Mcp.vue'
import AdminLinkSimulator from './views/admin/LinkSimulator.vue'
import Login from './views/Login.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/customer' },
    { path: '/login', component: Login },
    { path: '/customer', component: CustomerHome },
    { path: '/customer/devices', component: CustomerDevices },
    { path: '/customer/voices', component: CustomerVoices },
    { path: '/customer/points', component: CustomerPoints },
    { path: '/admin', component: AdminHome },
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
    { path: '/admin/ota', component: AdminOta },
    { path: '/admin/dicts', component: AdminDicts },
    { path: '/admin/correctwords', component: AdminCorrectWords },
    { path: '/admin/servers', component: AdminServers },
    { path: '/admin/apis', component: AdminApiDebug },
    { path: '/admin/mcp', component: AdminMcp },
    { path: '/admin/linksim', component: AdminLinkSimulator }
  ]
})

// A7 路由守卫：无 token 一律跳登录；已登录不再回登录页
router.beforeEach((to) => {
  const has = !!getToken()
  if (!has && to.path !== '/login') return '/login'
  if (has && to.path === '/login') return '/customer'
  return true
})

createApp(App).use(router).mount('#app')
