<template>
  <div class="kawaii-sidebar">
    <!-- 品牌区：logo + 版本徽标 -->
    <div class="kawaii-sidebar__brand" @click="goHome">
      <img loading="lazy" alt="" src="@/assets/xiaozhi-logo.png" class="kawaii-sidebar__logo" />
      <img
        v-if="!isCollapsed"
        loading="lazy"
        alt=""
        :src="xiaozhiAiIcon"
        class="kawaii-sidebar__brand-name"
      />
      <span v-if="version && !isCollapsed" class="kawaii-sidebar__version">v{{ version }}</span>
    </div>

    <!-- 分组导航 -->
    <SidebarMenu />

    <!-- 用户卡片：头像 + 昵称 + 退出（吸收 HeaderBar 右区逻辑） -->
    <div class="kawaii-sidebar__user">
      <img loading="lazy" alt="" src="@/assets/home/avatar.png" class="kawaii-sidebar__avatar" />
      <div v-if="!isCollapsed" class="kawaii-sidebar__user-info">
        <span class="kawaii-sidebar__username" :title="displayName">{{ displayName }}</span>
        <span
          class="kawaii-sidebar__logout"
          role="button"
          tabindex="0"
          @click="handleLogout"
          @keyup.enter="handleLogout"
        >
          {{ $t('header.logout') }}
        </span>
      </div>
    </div>
  </div>
</template>

<script>
import i18n from '@/i18n';
import { mapActions, mapState } from 'vuex';
import SidebarMenu from './SidebarMenu.vue';

export default {
  name: 'KawaiiSidebar',
  components: {
    SidebarMenu
  },
  data() {
    return {
      isCollapsed: false // <1024px 折叠态（与 KawaiiLayout 断点一致）
    };
  },
  computed: {
    ...mapState({
      userInfo: (state) => state.userInfo,
      version: (state) => state.pubConfig.version
    }),
    displayName() {
      return this.userInfo.username || this.$t('sidebar.loading');
    },
    // 根据当前语言获取对应的 xiaozhi-ai 品牌图（沿用 HeaderBar 逻辑）
    xiaozhiAiIcon() {
      const currentLang = i18n.locale || 'zh_CN';
      switch (currentLang) {
        case 'zh_CN':
          return require('@/assets/xiaozhi-ai.png');
        case 'zh_TW':
          return require('@/assets/xiaozhi-ai_zh_TW.png');
        case 'en':
          return require('@/assets/xiaozhi-ai_en.png');
        case 'de':
          return require('@/assets/xiaozhi-ai_de.png');
        case 'vi':
          return require('@/assets/xiaozhi-ai_vi.png');
        case 'pt_BR':
          return require('@/assets/xiaozhi-ai_en.png');
        default:
          return require('@/assets/xiaozhi-ai.png');
      }
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
    goHome() {
      this.$router.push('/home');
    },
    // 退出登录（沿用 HeaderBar.handleLogout）
    async handleLogout() {
      try {
        await this.logout();
        this.$message.success({
          message: this.$t('message.success'),
          showClose: true
        });
      } catch (error) {
        console.error('退出登录失败:', error);
        this.$message.error({
          message: this.$t('message.error'),
          showClose: true
        });
      }
    },
    ...mapActions(['logout'])
  }
};
</script>

<style lang="scss" scoped>
.kawaii-sidebar {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--kawaii-surface);
  border: 1px solid var(--kawaii-border);
  border-radius: var(--kawaii-radius);
  box-shadow: var(--kawaii-shadow);
  padding: var(--kawaii-space-4);
  box-sizing: border-box;
  overflow: hidden;
  text-align: left;
}

// ---------- 品牌区 ----------
.kawaii-sidebar__brand {
  display: flex;
  align-items: center;
  gap: var(--kawaii-space-2);
  cursor: pointer;
  flex-shrink: 0;
}

.kawaii-sidebar__logo {
  width: 38px;
  height: 38px;
  flex-shrink: 0;
}

.kawaii-sidebar__brand-name {
  height: 18px;
  max-width: 120px;
  object-fit: contain;
}

.kawaii-sidebar__version {
  font-size: var(--kawaii-font-size-xs);
  color: var(--kawaii-text-secondary);
  background: var(--kawaii-surface-2);
  border-radius: var(--kawaii-radius-full);
  padding: 1px var(--kawaii-space-2);
  flex-shrink: 0;
  white-space: nowrap;
}

// ---------- 用户卡片 ----------
.kawaii-sidebar__user {
  margin-top: auto;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: var(--kawaii-space-2);
  padding: var(--kawaii-space-2);
  background: var(--kawaii-surface-2);
  border-radius: var(--kawaii-radius-sm);
}

.kawaii-sidebar__avatar {
  width: 32px;
  height: 32px;
  border-radius: var(--kawaii-radius-full);
  flex-shrink: 0;
}

.kawaii-sidebar__user-info {
  min-width: 0;
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}

.kawaii-sidebar__username {
  font-size: var(--kawaii-font-size-sm);
  font-weight: 600;
  color: var(--kawaii-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kawaii-sidebar__logout {
  font-size: var(--kawaii-font-size-xs);
  color: var(--kawaii-primary);
  cursor: pointer;
  align-self: flex-start;

  &:hover {
    color: var(--kawaii-primary-hover);
  }
}

// ---------- 折叠态（<1024px 由父级 64px 容器驱动） ----------
@media (max-width: 1023px) {
  .kawaii-sidebar__brand {
    justify-content: center;
  }

  .kawaii-sidebar__user {
    justify-content: center;
    padding: var(--kawaii-space-1);
  }
}
</style>
