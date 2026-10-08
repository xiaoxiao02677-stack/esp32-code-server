import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import './styles/global.css'

import CustomerHome from './views/customer/Home.vue'
import CustomerDevices from './views/customer/Devices.vue'
import CustomerVoices from './views/customer/Voices.vue'
import CustomerPoints from './views/customer/Points.vue'
import AdminHome from './views/admin/Home.vue'
import AdminTemplates from './views/admin/Templates.vue'
import AdminKnowledge from './views/admin/Knowledge.vue'
import AdminUsers from './views/admin/Users.vue'
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
    { path: '/admin/templates', component: AdminTemplates },
    { path: '/admin/knowledge', component: AdminKnowledge },
    { path: '/admin/users', component: AdminUsers }
  ]
})

createApp(App).use(router).mount('#app')
