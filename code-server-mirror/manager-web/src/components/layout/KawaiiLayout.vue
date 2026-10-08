<template>
  <div class="kawaii-layout">
    <aside class="kawaii-layout__sidebar">
      <KawaiiSidebar />
    </aside>
    <div class="kawaii-layout__main">
      <header class="kawaii-layout__topbar">
        <KawaiiTopbar @open-drawer="mobileDrawerVisible = true" />
      </header>
      <main class="kawaii-layout__content">
        <div class="kawaii-layout__page">
          <transition name="kawaii-page" mode="out-in">
            <router-view :key="$route.fullPath" />
          </transition>
        </div>
        <div class="kawaii-layout__footer">
          <version-footer />
        </div>
      </main>
    </div>

    <!-- 移动端（<768px）侧边栏抽屉，桌面端不可见（按钮隐藏，且默认关闭） -->
    <KawaiiMobileDrawer :value.sync="mobileDrawerVisible" />
  </div>
</template>

<script>
import KawaiiSidebar from './KawaiiSidebar.vue';
import KawaiiTopbar from './KawaiiTopbar.vue';
import KawaiiMobileDrawer from './KawaiiMobileDrawer.vue';
import VersionFooter from '../VersionFooter.vue';

export default {
  name: 'KawaiiLayout',
  components: {
    KawaiiSidebar,
    KawaiiTopbar,
    KawaiiMobileDrawer,
    VersionFooter
  },
  data() {
    return {
      // 移动端侧边栏抽屉开合（仅 <768px 断点使用，桌面端恒为 false）
      mobileDrawerVisible: false
    };
  },
  watch: {
    // 路由变化时自动关闭移动端抽屉（切页后回到目标页，避免遮挡）
    $route() {
      if (this.mobileDrawerVisible) {
        this.mobileDrawerVisible = false;
      }
    }
  },
  mounted() {
    window.addEventListener('resize', this.handleLayoutResize);
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.handleLayoutResize);
  },
  methods: {
    // 回到桌面（≥768px）时强制收起移动端抽屉，保证桌面端零残留状态
    handleLayoutResize() {
      if (window.innerWidth >= 768 && this.mobileDrawerVisible) {
        this.mobileDrawerVisible = false;
      }
    }
  }
};
</script>

<style lang="scss" scoped>
// ============================================================
// Kawaii 双栏布局骨架：左栏 232px 固定 sticky + 右侧弹性内容
// 消费 --kawaii-* tokens（styles/kawaii/tokens.scss）
// <1024px 侧栏折叠 64px 图标栏（P1 可降级为常开，P0 保桌面展开）
// ============================================================
.kawaii-layout {
  display: flex;
  align-items: stretch;
  min-height: 100vh;
  min-width: 900px; // 页面内容（表格等）需要的基础宽度兜底
  background: var(--kawaii-bg);
  font-family: var(--kawaii-font-family);
  color: var(--kawaii-text);
  text-align: left;
}

// ---------- 左栏：232px 固定 sticky ----------
.kawaii-layout__sidebar {
  position: sticky;
  top: 0;
  flex: 0 0 232px;
  width: 232px;
  height: 100vh;
  padding: var(--kawaii-space-4);
  box-sizing: border-box;
  overflow: hidden;
}

// ---------- 右侧：顶栏 + 内容 + 底栏 ----------
.kawaii-layout__main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.kawaii-layout__topbar {
  flex: 0 0 auto;
  padding: var(--kawaii-space-2) var(--kawaii-space-4) 0;
}

.kawaii-layout__content {
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding: var(--kawaii-space-4);
  box-sizing: border-box;
}

.kawaii-layout__page {
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
}

// 页面自身的滚动：手术批次（#5/#6）将删除页面根的
// height:100vh / min-width:900px 后由本容器统一提供
.kawaii-layout__page > ::v-deep .welcome,
.kawaii-layout__page > ::v-deep > div {
  min-height: 100%;
}

.kawaii-layout__footer {
  flex: 0 0 auto;
  margin-top: var(--kawaii-space-4);
}

// ---------- 响应式：<1024px 折叠 64px 图标栏（P1 降级，P0 保桌面） ----------
@media (max-width: 1023px) {
  .kawaii-layout {
    min-width: 0;
  }

  .kawaii-layout__sidebar {
    flex-basis: 64px;
    width: 64px;
    padding: var(--kawaii-space-3);
  }
}

// ---------- 响应式：<768px 侧栏改为顶栏汉堡按钮驱动的抽屉（桌面端零变化） ----------
@media (max-width: 767px) {
  .kawaii-layout__sidebar {
    display: none;
  }
}
</style>
