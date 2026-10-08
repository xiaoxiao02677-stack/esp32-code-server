<template>
  <div class="kawaii-topbar">
    <!-- 移动端（<768px）汉堡按钮：点开侧边栏抽屉；桌面端隐藏，行为零变化 -->
    <button
      type="button"
      class="kawaii-topbar__menu-btn"
      aria-label="menu"
      @click="$emit('open-drawer')"
    >
      <i class="el-icon-menu" aria-hidden="true"></i>
    </button>

    <!-- 左：当前页面标题/面包屑 -->
    <div class="kawaii-topbar__crumbs">
      <span class="kawaii-topbar__crumb-home" @click="goHome">{{ $t('sidebar.group.overview') }}</span>
      <span v-if="activeGroupTitle" class="kawaii-topbar__crumb-sep">/</span>
      <span v-if="activeGroupTitle" class="kawaii-topbar__crumb-group">{{ activeGroupTitle }}</span>
      <span class="kawaii-topbar__crumb-sep">/</span>
      <span class="kawaii-topbar__crumb-page">{{ pageTitle }}</span>
    </div>

    <div class="kawaii-topbar__actions">
      <!-- 粉/绿主题切换（P1-7；仅本行新增，不改动上方 e-pi2 抽屉按钮等既有内容） -->
      <ThemeToggle />

      <!-- 全局设备搜索（原 HeaderBar/home.vue 搜索能力迁移，含搜索历史） -->
      <SidebarSearch />

      <!-- 语言切换 -->
      <el-dropdown trigger="click" @command="handleLanguageCommand">
        <span class="kawaii-topbar__lang" :title="$t('sidebar.language')">
          <i class="el-icon-collection-tag" aria-hidden="true"></i>
          <span>{{ currentLanguageText }}</span>
          <i class="el-icon-arrow-down"></i>
        </span>
        <el-dropdown-menu slot="dropdown">
          <el-dropdown-item v-for="lang in languageOptions" :key="lang.value" :command="lang.value">
            {{ lang.label }}
          </el-dropdown-item>
        </el-dropdown-menu>
      </el-dropdown>

      <!-- 用户下拉兜底（修改密码等，吸收 HeaderBar cascader 用户菜单） -->
      <el-dropdown trigger="click" @command="handleUserCommand">
        <span class="kawaii-topbar__user">
          <img loading="lazy" alt="" src="@/assets/home/avatar.png" class="kawaii-topbar__avatar" />
          <span class="kawaii-topbar__username">{{ displayName }}</span>
          <i class="el-icon-arrow-down"></i>
        </span>
        <el-dropdown-menu slot="dropdown">
          <el-dropdown-item command="changePassword">{{ $t('header.changePassword') }}</el-dropdown-item>
          <el-dropdown-item command="logout">{{ $t('header.logout') }}</el-dropdown-item>
        </el-dropdown-menu>
      </el-dropdown>
    </div>

    <!-- 修改密码弹窗（吸收 HeaderBar） -->
    <ChangePasswordDialog v-model="isChangePasswordDialogVisible" />
  </div>
</template>

<script>
import i18n, { changeLanguage } from '@/i18n';
import { mapActions, mapState } from 'vuex';
import ChangePasswordDialog from '../ChangePasswordDialog.vue';
import SidebarSearch from './SidebarSearch.vue';
import ThemeToggle from './ThemeToggle.vue';

export default {
  name: 'KawaiiTopbar',
  components: {
    SidebarSearch,
    ChangePasswordDialog,
    ThemeToggle
  },
  data() {
    return {
      isChangePasswordDialogVisible: false
    };
  },
  computed: {
    ...mapState({
      userInfo: (state) => state.userInfo
    }),
    displayName() {
      return this.userInfo.username || this.$t('sidebar.loading');
    },
    currentLanguage() {
      return i18n.locale || 'zh_CN';
    },
    currentLanguageText() {
      const currentLang = this.currentLanguage;
      switch (currentLang) {
        case 'zh_CN':
          return this.$t('language.zhCN');
        case 'zh_TW':
          return this.$t('language.zhTW');
        case 'en':
          return this.$t('language.en');
        case 'de':
          return this.$t('language.de');
        case 'vi':
          return this.$t('language.vi');
        case 'pt_BR':
          return this.$t('language.ptBR');
        default:
          return this.$t('language.zhCN');
      }
    },
    languageOptions() {
      return [
        { value: 'zh_CN', label: this.$t('language.zhCN') },
        { value: 'zh_TW', label: this.$t('language.zhTW') },
        { value: 'en', label: this.$t('language.en') },
        { value: 'de', label: this.$t('language.de') },
        { value: 'vi', label: this.$t('language.vi') },
        { value: 'pt_BR', label: this.$t('language.ptBR') }
      ];
    },
    // 当前页面标题（菜单未覆盖页兜底用路由 name/title）
    pageTitle() {
      const key = this.$route.meta && this.$route.meta.titleKey;
      if (key && this.$te(key)) {
        return this.$t(key);
      }
      const metaTitle = this.$route.meta && this.$route.meta.title;
      if (metaTitle) {
        return metaTitle;
      }
      return this.$t('header.smartManagement');
    },
    activeGroupTitle() {
      const key = this.$route.meta && this.$route.meta.groupKey;
      // 总览组与首级面包屑同名，去重不显示
      if (key && key !== 'overview' && this.$te(`sidebar.group.${key}`)) {
        return this.$t(`sidebar.group.${key}`);
      }
      return '';
    }
  },
  methods: {
    goHome() {
      if (this.$route.path !== '/home') {
        this.$router.push('/home');
      }
    },
    handleLanguageCommand(lang) {
      changeLanguage(lang);
      this.$message.success({
        message: this.$t('message.success'),
        showClose: true
      });
    },
    handleUserCommand(command) {
      switch (command) {
        case 'changePassword':
          this.isChangePasswordDialogVisible = true;
          break;
        case 'logout':
          this.handleLogout();
          break;
      }
    },
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
// ============================================================
// 56px 顶栏：页面标题/面包屑 + 全局设备搜索 + 语言切换 + 用户下拉兜底
// ============================================================
.kawaii-topbar {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--kawaii-space-4);
  padding: 0 var(--kawaii-space-4);
  background: var(--kawaii-surface);
  border: 1px solid var(--kawaii-border);
  border-radius: var(--kawaii-radius);
  box-shadow: var(--kawaii-shadow);
  box-sizing: border-box;
}

.kawaii-topbar__crumbs {
  display: flex;
  align-items: center;
  gap: var(--kawaii-space-2);
  min-width: 0;
  overflow: hidden;
}

.kawaii-topbar__crumb-home {
  color: var(--kawaii-text-secondary);
  font-size: var(--kawaii-font-size-sm);
  cursor: pointer;
  white-space: nowrap;

  &:hover {
    color: var(--kawaii-primary);
  }
}

.kawaii-topbar__crumb-sep {
  color: var(--kawaii-text-placeholder);
}

.kawaii-topbar__crumb-group {
  color: var(--kawaii-text-secondary);
  font-size: var(--kawaii-font-size-sm);
  white-space: nowrap;
}

.kawaii-topbar__crumb-page {
  color: var(--kawaii-text);
  font-weight: 600;
  font-size: var(--kawaii-font-size-base);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kawaii-topbar__actions {
  display: flex;
  align-items: center;
  gap: var(--kawaii-space-4);
  flex-shrink: 0;
}

.kawaii-topbar__lang,
.kawaii-topbar__user {
  display: flex;
  align-items: center;
  gap: var(--kawaii-space-1);
  cursor: pointer;
  font-size: var(--kawaii-font-size-sm);
  color: var(--kawaii-text);
  white-space: nowrap;
}

.kawaii-topbar__lang:hover,
.kawaii-topbar__user:hover {
  color: var(--kawaii-primary);
}

.kawaii-topbar__avatar {
  width: 26px;
  height: 26px;
  border-radius: var(--kawaii-radius-full);
}

.kawaii-topbar__username {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kawaii-topbar .el-icon-arrow-down {
  font-size: 12px;
  transition: transform var(--kawaii-duration-fast) var(--kawaii-ease-out);
}

// ---------- 移动端汉堡按钮（仅 <768px 显示，点开侧边栏抽屉） ----------
.kawaii-topbar__menu-btn {
  display: none; // ≥768px 桌面端隐藏，保持现状
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  align-items: center;
  justify-content: center;
  background: var(--kawaii-surface-2);
  border: 1px solid var(--kawaii-border);
  border-radius: var(--kawaii-radius); // 圆角 14px kawaii 风
  color: var(--kawaii-text);
  font-size: 18px;
  cursor: pointer;
  padding: 0;
  box-sizing: border-box;

  &:hover {
    color: var(--kawaii-primary);
  }
}

// 顶栏在窄屏（<1024px）时隐藏面包屑，保搜索与用户菜单
@media (max-width: 1023px) {
  .kawaii-topbar__crumbs {
    display: none;
  }
}

// <768px：显示汉堡按钮（侧边栏抽屉入口）
@media (max-width: 767px) {
  .kawaii-topbar__menu-btn {
    display: inline-flex;
  }
}
</style>
