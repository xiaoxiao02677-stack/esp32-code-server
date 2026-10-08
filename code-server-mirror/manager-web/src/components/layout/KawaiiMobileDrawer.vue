<template>
  <el-drawer
    class="kawaii-mobile-drawer"
    direction="rtl"
    :visible.sync="visibleProxy"
    :size="drawerSize"
    :wrapper-closable="true"
    :show-close="false"
    destroy-on-close="true"
  >
    <div class="kawaii-mobile-drawer__panel kawaii-jelly-enter">
      <!-- 品牌区（与 KawaiiSidebar 保持一致） -->
      <div class="kawaii-mobile-drawer__brand" @click="goHome">
        <img loading="lazy" alt="" src="@/assets/xiaozhi-logo.png" class="kawaii-mobile-drawer__logo" />
      </div>

      <!-- 分组导航（复用桌面侧栏的 SidebarMenu） -->
      <div class="kawaii-mobile-drawer__nav">
        <SidebarMenu />
      </div>
    </div>
  </el-drawer>
</template>

<script>
import SidebarMenu from './SidebarMenu.vue';

export default {
  name: 'KawaiiMobileDrawer',
  components: {
    SidebarMenu
  },
  props: {
    // 抽屉开合状态（父级 :value.sync 控制）
    value: {
      type: Boolean,
      default: false
    }
  },
  data() {
    return {
      // 宽度：80% 视口，上限 320px（<768px 断点下最大 320px）
      drawerSize: Math.min(Math.floor(window.innerWidth * 0.8), 320)
    };
  },
  computed: {
    visibleProxy: {
      get() {
        return this.value;
      },
      set(val) {
        this.$emit('input', val);
      }
    }
  },
  methods: {
    goHome() {
      this.$router.push('/home');
    }
  }
};
</script>

<style lang="scss" scoped>
// ============================================================
// 移动端（<768px）侧边栏抽屉：rtl 方向，宽度 80% 上限 320px
// 粉彩 kawaii 风格，圆角 var(--kawaii-radius)，禁止深色底
// ============================================================
.kawaii-mobile-drawer {
  ::v-deep .el-drawer {
    background: var(--kawaii-bg);
    border-radius: var(--kawaii-radius) 0 0 var(--kawaii-radius);
    display: flex;
    flex-direction: column;
  }

  // 面板主体
  &__panel {
    height: 100%;
    display: flex;
    flex-direction: column;
    padding: var(--kawaii-space-4);
    box-sizing: border-box;
    background: var(--kawaii-surface);
    border-radius: var(--kawaii-radius);
  }

  // 品牌区
  &__brand {
    display: flex;
    align-items: center;
    padding-bottom: var(--kawaii-space-3);
    cursor: pointer;
    flex-shrink: 0;
  }

  &__logo {
    width: 42px;
    height: 42px;
  }

  // 导航区：SidebarMenu 内部可滚动
  &__nav {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
  }
}
</style>
