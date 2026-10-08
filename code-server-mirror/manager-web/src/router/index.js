import Vue from 'vue'
import VueRouter from 'vue-router'

Vue.use(VueRouter)

const routes = [
  // ============================================================
  // 控制台布局（嵌套路由父级）：双栏骨架
  // 左栏 232px KawaiiSidebar + 右侧 KawaiiTopbar/router-view/VersionFooter
  // 17 个管理页作为 children（原 path/name/meta 不变，URL 完全兼容）
  // ============================================================
  {
    path: '/',
    name: 'console',
    component: function () {
      return import('../components/layout/KawaiiLayout.vue')
    },
    redirect: '/home',
    children: [
      {
        path: '/home',
        name: 'home',
        component: function () {
          return import('../views/home.vue')
        },
        meta: { groupKey: 'overview', titleKey: 'sidebar.myXiaozhi' }
      },
      {
        path: '/role-config',
        name: 'RoleConfig',
        component: function () {
          return import('../views/roleConfig.vue')
        },
        meta: { groupKey: 'agent', titleKey: 'sidebar.agentConfig' }
      },
      // 设备管理页面路由
      {
        path: '/device-management',
        name: 'DeviceManagement',
        component: function () {
          return import('../views/DeviceManagement.vue')
        },
        meta: { groupKey: 'agent', titleKey: 'sidebar.deviceManagement' }
      },
      // 添加用户管理路由
      {
        path: '/user-management',
        name: 'UserManagement',
        component: function () {
          return import('../views/UserManagement.vue')
        },
        meta: { groupKey: 'system', titleKey: 'header.userManagement' }
      },
      {
        path: '/model-config',
        name: 'ModelConfig',
        component: function () {
          return import('../views/ModelConfig.vue')
        },
        meta: { groupKey: 'modelParams', titleKey: 'header.modelConfig' }
      },
      {
        path: '/params-management',
        name: 'ParamsManagement',
        component: function () {
          return import('../views/ParamsManagement.vue')
        },
        meta: {
          requiresAuth: true,
          title: '参数管理',
          groupKey: 'modelParams',
          titleKey: 'header.paramManagement'
        }
      },
      {
        path: '/knowledge-base-management',
        name: 'KnowledgeBaseManagement',
        component: function () {
          return import('../views/KnowledgeBaseManagement.vue')
        },
        meta: {
          requiresAuth: true,
          title: '知识库管理',
          groupKey: 'knowledgeMemory',
          titleKey: 'header.knowledgeBase'
        }
      },
      {
        path: '/server-side-management',
        name: 'ServerSideManager',
        component: function () {
          return import('../views/ServerSideManager.vue')
        },
        meta: {
          requiresAuth: true,
          title: '服务端管理',
          groupKey: 'system',
          titleKey: 'header.serverSideManagement'
        }
      },
      {
        path: '/ota-management',
        name: 'OtaManagement',
        component: function () {
          return import('../views/OtaManagement.vue')
        },
        meta: {
          requiresAuth: true,
          title: 'OTA管理',
          groupKey: 'system',
          titleKey: 'header.otaManagement'
        }
      },
      {
        path: '/voice-resource-management',
        name: 'VoiceResourceManagement',
        component: function () {
          return import('../views/VoiceResourceManagement.vue')
        },
        meta: {
          requiresAuth: true,
          title: '音色资源开通',
          groupKey: 'voice',
          titleKey: 'header.voiceResourceManagement'
        }
      },
      {
        path: '/voice-clone-management',
        name: 'VoiceCloneManagement',
        component: function () {
          return import('../views/VoiceCloneManagement.vue')
        },
        meta: {
          requiresAuth: true,
          title: '音色克隆管理',
          groupKey: 'voice',
          titleKey: 'header.voiceCloneManagement'
        }
      },
      {
        path: '/dict-management',
        name: 'DictManagement',
        component: function () {
          return import('../views/DictManagement.vue')
        },
        meta: { groupKey: 'modelParams', titleKey: 'header.dictManagement' }
      },
      {
        path: '/provider-management',
        name: 'ProviderManagement',
        component: function () {
          return import('../views/ProviderManagement.vue')
        },
        meta: { groupKey: 'modelParams', titleKey: 'header.providerManagement' }
      },
      // 添加默认角色管理路由
      {
        path: '/agent-template-management',
        name: 'AgentTemplateManagement',
        component: function () {
          return import('../views/AgentTemplateManagement.vue')
        },
        meta: { groupKey: 'agent', titleKey: 'header.agentTemplate' }
      },
      // 添加模板快速配置路由
      {
        path: '/template-quick-config',
        name: 'TemplateQuickConfig',
        component: function () {
          return import('../views/TemplateQuickConfig.vue')
        },
        meta: { groupKey: 'agent', titleKey: 'sidebar.templateQuickConfig' }
      },
      // 功能配置页面路由
      {
        path: '/feature-management',
        name: 'FeatureManagement',
        component: function () {
          return import('../views/FeatureManagement.vue')
        },
        meta: {
          requiresAuth: true,
          title: '功能配置',
          groupKey: 'modelParams',
          titleKey: 'header.featureManagement'
        }
      },
      // 替换词管理
      {
        path: '/replacement-word-management',
        name: 'ReplacementWordManagement',
        component: function () {
          return import('../views/ReplacementWordManagement.vue')
        },
        meta: {
          requiresAuth: true,
          title: '替换词管理',
          groupKey: 'modelParams',
          titleKey: 'header.replacementWordManagement'
        }
      },
      // 通讯录管理页面路由
      {
        path: '/address-book-management',
        name: 'AddressBookManagement',
        component: function () {
          return import('../views/AddressBookManagement.vue')
        },
        meta: {
          requiresAuth: true,
          title: '通讯录管理',
          groupKey: 'contact',
          titleKey: 'header.addressBook'
        }
      },
      // 记忆管理页面路由
      {
        path: '/memory-management',
        name: 'MemoryManagement',
        component: function () {
          return import('../views/MemoryManagement.vue')
        },
        meta: {
          requiresAuth: true,
          title: '记忆管理',
          groupKey: 'knowledgeMemory',
          titleKey: 'header.memoryManagement'
        }
      },
      // 设备云端配置管理页面路由（P1-4 管理后台查看/清库入口）
      {
        path: '/device-config-management',
        name: 'DeviceConfigManagement',
        component: function () {
          return import('../views/device/DeviceConfigManager.vue')
        },
        meta: {
          requiresAuth: true,
          title: '设备配置管理',
          groupKey: 'system',
          titleKey: 'deviceConfigManagement.title'
        }
      },
      // API 控制台：15 模块全量 API 台账 + 在线调试（独立于原 17 管理页）
      {
        path: '/cc',
        name: 'ApiConsole',
        component: function () {
          return import('../views/ApiConsole.vue')
        },
        meta: {
          requiresAuth: true,
          title: 'API 控制台',
          groupKey: 'system',
          titleKey: 'apiConsole.title'
        }
      }
    ]
  },
  // ============================================================
  // 免登录/独立全屏页（平级外置，不进双栏骨架）
  // ============================================================
  {
    path: '/login',
    name: 'login',
    component: function () {
      return import('../views/login.vue')
    }
  },
  {
    path: '/register',
    name: 'Register',
    component: function () {
      return import('../views/register.vue')
    }
  },
  {
    path: '/retrieve-password',
    name: 'RetrievePassword',
    component: function () {
      return import('../views/retrievePassword.vue')
    }
  },
  // 声纹管理：依赖 ?agentId= 的设备级独立页（入口在设备卡片，不进侧边栏）
  {
    path: '/voice-print',
    name: 'VoicePrint',
    component: function () {
      return import('../views/VoicePrint.vue')
    }
  }
]
const router = new VueRouter({
  base: process.env.VUE_APP_PUBLIC_PATH || '/',
  routes
})

// 全局处理重复导航，改为刷新页面
const originalPush = VueRouter.prototype.push
VueRouter.prototype.push = function push(location) {
  return originalPush.call(this, location).catch(err => {
    if (err.name === 'NavigationDuplicated') {
      // 如果是重复导航，刷新页面
      window.location.reload()
    } else {
      // 其他错误正常抛出
      throw err
    }
  })
}

// 需要登录才能访问的路由
// 注：'console' 为嵌套路由的父级（path: '/'），未登录时访问根路径会直接渲染骨架页
// 导致 home 接口 401 白屏，故一并纳入保护，让根路径先落到 /login
const protectedRoutes = ['console', 'home', 'RoleConfig', 'DeviceManagement', 'UserManagement', 'ModelConfig', 'KnowledgeBaseManagement', 'KnowledgeFileUpload', 'AddressBookManagement', 'MemoryManagement', 'DeviceConfigManagement', 'ApiConsole']

// 路由守卫
router.beforeEach((to, from, next) => {
  // 检查是否是需要保护的路由
  if (protectedRoutes.includes(to.name)) {
    // 从localStorage获取token
    const token = localStorage.getItem('token')
    if (!token) {
      // 未登录，跳转到登录页
      next({ name: 'login', query: { redirect: to.fullPath } })
      return
    }
  }
  next()
})

export default router
