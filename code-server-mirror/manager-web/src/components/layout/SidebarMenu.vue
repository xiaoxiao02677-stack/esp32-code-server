<template>
  <nav class="sidebar-menu" :class="{ 'sidebar-menu--collapsed': isCollapsed }" aria-label="Main navigation">
    <div v-for="group in visibleGroups" :key="group.key" class="sidebar-menu__group">
      <div class="sidebar-menu__group-title" :title="$t(group.titleKey)">
        {{ $t(group.titleKey) }}
      </div>
      <div class="sidebar-menu__list">
        <div
          v-for="item in group.items"
          :key="item.key"
          class="sidebar-menu__item"
          :class="{ 'sidebar-menu__item--active': isActive(item) }"
          :title="$t(item.titleKey)"
          role="button"
          tabindex="0"
          @click="navigate(item)"
          @keyup.enter="navigate(item)"
        >
          <img loading="lazy" alt="" :src="item.icon" class="sidebar-menu__icon" />
          <span v-if="!isCollapsed" class="sidebar-menu__label">{{ $t(item.titleKey) }}</span>
        </div>
      </div>
    </div>
  </nav>
</template>

<script>
import { mapState } from 'vuex';

// ============================================================
// 分组导航（PRD §3.2 七分组映射 + 可见性规则）
// 菜单可见性逻辑源 = HeaderBar.vue（V-11 退役对象），逐条对照：
//   superAdmin → HeaderBar 各处 v-if="userInfo.superAdmin"
//   featureStatus → HeaderBar mapState: state.pubConfig.systemWebMenu?.features?.*.enabled
// ============================================================

// 菜单图标：P1-3 粉彩化重绘的 kawaii SVG（src/assets/kawaii/，静态文件无外部依赖）
// 七枚分组图标对应 PRD §3.2 七分组，同组菜单项共用该组图标
const icons = {
  home: require('@/assets/kawaii/icon-module-overview.svg'),
  role: require('@/assets/kawaii/icon-module-agent.svg'),
  device: require('@/assets/kawaii/icon-module-agent.svg'),
  template: require('@/assets/kawaii/icon-module-agent.svg'),
  quick: require('@/assets/kawaii/icon-module-agent.svg'),
  clone: require('@/assets/kawaii/icon-module-voice.svg'),
  resource: require('@/assets/kawaii/icon-module-voice.svg'),
  memory: require('@/assets/kawaii/icon-module-knowledge.svg'),
  knowledge: require('@/assets/kawaii/icon-module-knowledge.svg'),
  model: require('@/assets/kawaii/icon-module-model.svg'),
  provider: require('@/assets/kawaii/icon-module-model.svg'),
  params: require('@/assets/kawaii/icon-module-model.svg'),
  dict: require('@/assets/kawaii/icon-module-model.svg'),
  replacement: require('@/assets/kawaii/icon-module-model.svg'),
  feature: require('@/assets/kawaii/icon-module-model.svg'),
  addressBook: require('@/assets/kawaii/icon-module-contact.svg'),
  serverSide: require('@/assets/kawaii/icon-module-system.svg'),
  ota: require('@/assets/kawaii/icon-module-system.svg'),
  user: require('@/assets/kawaii/icon-module-system.svg')
};

const GROUP_DEFS = [
  {
    key: 'overview',
    titleKey: 'sidebar.group.overview',
    items: [
      { key: 'home', path: '/home', titleKey: 'sidebar.myXiaozhi', icon: icons.home }
    ]
  },
  {
    key: 'agent',
    titleKey: 'sidebar.group.agent',
    items: [
      { key: 'role', path: '/role-config', titleKey: 'sidebar.agentConfig', icon: icons.role },
      { key: 'device', path: '/device-management', titleKey: 'sidebar.deviceManagement', icon: icons.device },
      { key: 'template', path: '/agent-template-management', titleKey: 'header.agentTemplate', icon: icons.template, superAdmin: true },
      { key: 'quick', path: '/template-quick-config', titleKey: 'sidebar.templateQuickConfig', icon: icons.quick, superAdmin: true }
    ]
  },
  {
    key: 'voice',
    titleKey: 'sidebar.group.voice',
    items: [
      { key: 'clone', path: '/voice-clone-management', titleKey: 'header.voiceCloneManagement', icon: icons.clone, feature: 'voiceClone' },
      { key: 'resource', path: '/voice-resource-management', titleKey: 'header.voiceResourceManagement', icon: icons.resource, superAdmin: true, feature: 'voiceClone' }
    ]
  },
  {
    key: 'knowledgeMemory',
    titleKey: 'sidebar.group.knowledgeMemory',
    items: [
      { key: 'memory', path: '/memory-management', titleKey: 'header.memoryManagement', icon: icons.memory, superAdmin: true },
      { key: 'knowledge', path: '/knowledge-base-management', titleKey: 'header.knowledgeBase', icon: icons.knowledge, feature: 'knowledgeBase' }
    ]
  },
  {
    key: 'modelParams',
    titleKey: 'sidebar.group.modelParams',
    items: [
      { key: 'model', path: '/model-config', titleKey: 'header.modelConfig', icon: icons.model, superAdmin: true },
      { key: 'provider', path: '/provider-management', titleKey: 'header.providerManagement', icon: icons.provider, superAdmin: true },
      { key: 'params', path: '/params-management', titleKey: 'header.paramManagement', icon: icons.params, superAdmin: true },
      { key: 'dict', path: '/dict-management', titleKey: 'header.dictManagement', icon: icons.dict, superAdmin: true },
      { key: 'replacement', path: '/replacement-word-management', titleKey: 'header.replacementWordManagement', icon: icons.replacement, superAdmin: true },
      { key: 'feature', path: '/feature-management', titleKey: 'header.featureManagement', icon: icons.feature, superAdmin: true }
    ]
  },
  {
    key: 'contact',
    titleKey: 'sidebar.group.contact',
    items: [
      { key: 'addressBook', path: '/address-book-management', titleKey: 'header.addressBook', icon: icons.addressBook, feature: 'addressBook' }
    ]
  },
  {
    key: 'system',
    titleKey: 'sidebar.group.system',
    items: [
      { key: 'serverSide', path: '/server-side-management', titleKey: 'header.serverSideManagement', icon: icons.serverSide, superAdmin: true },
      { key: 'ota', path: '/ota-management', titleKey: 'header.otaManagement', icon: icons.ota, superAdmin: true },
      { key: 'user', path: '/user-management', titleKey: 'header.userManagement', icon: icons.user, superAdmin: true },
      { key: 'cc', path: '/cc', titleKey: 'apiConsole.title', icon: icons.serverSide }
    ]
  }
];

export default {
  name: 'SidebarMenu',
  data() {
    return {
      isCollapsed: false // <1024px 折叠态（与 KawaiiLayout 断点一致）
    };
  },
  computed: {
    ...mapState({
      userInfo: (state) => state.userInfo,
      featureStatus: (state) => ({
        voiceClone: state.pubConfig.systemWebMenu?.features?.voiceClone?.enabled, // 音色克隆功能状态
        knowledgeBase: state.pubConfig.systemWebMenu?.features?.knowledgeBase?.enabled, // 知识库功能状态
        addressBook: state.pubConfig.systemWebMenu?.features?.addressBook?.enabled // 通讯录功能状态
      })
    }),
    // 按可见性规则过滤分组
    visibleGroups() {
      return GROUP_DEFS.map((group) => ({
        ...group,
        items: group.items.filter((item) => this.isItemVisible(item))
      })).filter((group) => group.items.length > 0);
    }
  },
  mounted() {
    this.handleResize();
    window.addEventListener('resize', this.handleResize);
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.handleResize);
  },
  methods: {
    // 与 KawaiiLayout 的 @media (max-width:1023px) 断点保持一致
    handleResize() {
      this.isCollapsed = window.innerWidth < 1024;
    },
    // 可见性判断（吸收 HeaderBar 的 v-if 规则）
    isItemVisible(item) {
      if (item.superAdmin && !this.userInfo.superAdmin) {
        return false; // HeaderBar: v-if="userInfo.superAdmin"
      }
      if (item.feature && !this.featureStatus[item.feature]) {
        return false; // HeaderBar: v-if="featureStatus.xxx"
      }
      return true;
    },
    isActive(item) {
      const path = this.$route.path;
      if (item.key === 'knowledge') {
        // 知识库子路由（knowledge-file-upload）保持入口高亮
        return path === '/knowledge-base-management' || path === '/knowledge-file-upload';
      }
      return path === item.path;
    },
    navigate(item) {
      if (item.path !== this.$route.path) {
        this.$router.push(item.path);
      }
    }
  }
};
</script>

<style lang="scss" scoped>
// ============================================================
// 侧边栏模块项样式（按 PRD §3.1 / 任务要求）
// 模块项：rounded-2xl p-4 transition-all font-medium
// 选中态：bg-pink-100；hover:scale-103 hover:shadow-sm
// 容器：rounded-3xl shadow-md bg-white p-6；模块列表 gap-4
// ============================================================

.sidebar-menu {
  flex: 1 1 auto;
  overflow-y: auto;
  margin: var(--kawaii-space-4) 0;
  text-align: left;

  // 侧栏容器（rounded-3xl shadow-md bg-white p-6）
  &--collapsed {
    margin: var(--kawaii-space-4) 0;
  }
}

.sidebar-menu__group {
  margin-bottom: var(--kawaii-space-4);
}

.sidebar-menu__group-title {
  font-size: var(--kawaii-font-size-xs);
  font-weight: 500;
  color: var(--kawaii-text-secondary);
  padding: 0 var(--kawaii-space-2);
  margin-bottom: var(--kawaii-space-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar-menu__list {
  display: flex;
  flex-direction: column;
  gap: var(--kawaii-space-2); // 模块列表 gap-4 适度收紧（28px 分组内间隔过大）
}

.sidebar-menu__item {
  display: flex;
  align-items: center;
  gap: var(--kawaii-space-2);
  padding: var(--kawaii-space-3); // p-4 等效（16px 需求 → 12px 紧凑可读）
  border-radius: var(--kawaii-radius); // rounded-2xl（16px，与 --kawaii-radius 一致）
  font-size: var(--kawaii-font-size-base);
  font-weight: 500; // font-medium
  color: var(--kawaii-text);
  cursor: pointer;
  transition: all var(--kawaii-duration-base) var(--kawaii-ease-out);

  &:hover {
    background: var(--kawaii-primary-light);
    box-shadow: var(--kawaii-shadow); // hover:shadow-sm
    transform: scale(1.03); // hover:scale-103
  }

  &:active {
    transform: scale(0.95); // active:scale-95
  }

  &--active {
    background: var(--kawaii-primary-light); // 选中态 bg-pink-100（#FFE3EA）
    color: var(--kawaii-primary-active);
  }

  &--active .sidebar-menu__icon {
    // 选中态图标加深（不反白，PRD P0-6 禁用 brightness(0) invert(1) hack）
    filter: none;
  }
}

.sidebar-menu__icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.sidebar-menu__label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

// 折叠态：只显图标
.sidebar-menu--collapsed {
  .sidebar-menu__item {
    justify-content: center;
    padding: var(--kawaii-space-3) 0;
  }

  .sidebar-menu__group-title {
    text-align: center;
    padding: 0;
  }
}

// prefers-reduced-motion：关闭缩放动效（PRD P0-7）
@media (prefers-reduced-motion: reduce) {
  .sidebar-menu__item {
    transition: none;

    &:hover,
    &:active {
      transform: none;
    }
  }
}
</style>
