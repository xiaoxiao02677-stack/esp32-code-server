<template>
  <button
    type="button"
    class="theme-toggle"
    :aria-pressed="isGreen"
    :title="isGreen ? '当前：薄荷绿主题，点击切回蜜桃粉' : '当前：蜜桃粉主题，点击切换薄荷绿'"
    @click="toggleTheme"
  >
    <span class="theme-toggle__dot" :class="isGreen ? 'theme-toggle__dot--green' : 'theme-toggle__dot--pink'" aria-hidden="true"></span>
    <span class="theme-toggle__label">{{ isGreen ? '薄荷绿' : '蜜桃粉' }}</span>
  </button>
</template>

<script>
/**
 * Kawaii 双主题切换（P1-7）
 * - 默认蜜桃粉（tokens.scss :root），零变化
 * - 切换后在 <html> 与 <body> 上加 .theme-green class，
 *   由 styles/kawaii/theme-green.scss 的 --kawaii-* 覆盖层接管
 * - 持久化：localStorage key = 'kawaii-theme'（'green' | 'pink'）
 */
const THEME_STORAGE_KEY = 'kawaii-theme';
const THEME_CLASS = 'theme-green';
const THEMES = ['pink', 'green'];

export default {
  name: 'ThemeToggle',
  data() {
    return {
      theme: 'pink'
    };
  },
  computed: {
    isGreen() {
      return this.theme === 'green';
    }
  },
  created() {
    this.theme = this.readStoredTheme();
    // 组件通常随 KawaiiLayout 挂载：在首帧渲染前应用持久化主题
    this.applyThemeClass();
  },
  beforeDestroy() {
    if (typeof window !== 'undefined') {
      window.removeEventListener('storage', this.onStorageChange);
    }
  },
  mounted() {
    if (typeof window !== 'undefined') {
      // 多标签页切换主题时同步
      window.addEventListener('storage', this.onStorageChange);
    }
  },
  methods: {
    readStoredTheme() {
      try {
        const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
        return THEMES.indexOf(stored) !== -1 ? stored : 'pink';
      } catch (e) {
        return 'pink'; // 隐私模式等场景兜底
      }
    },
    applyThemeClass() {
      if (typeof document === 'undefined') {
        return;
      }
      const targets = [document.documentElement, document.body];
      targets.forEach((el) => {
        if (el) {
          el.classList.toggle(THEME_CLASS, this.isGreen);
        }
      });
    },
    persistTheme() {
      try {
        window.localStorage.setItem(THEME_STORAGE_KEY, this.theme);
      } catch (e) {
        // localStorage 不可用时仅本次会话生效，不阻断交互
      }
    },
    toggleTheme() {
      this.theme = this.isGreen ? 'pink' : 'green';
      this.persistTheme();
      this.applyThemeClass();
    },
    onStorageChange(event) {
      if (event.key === THEME_STORAGE_KEY) {
        const next = THEMES.indexOf(event.newValue) !== -1 ? event.newValue : 'pink';
        if (next !== this.theme) {
          this.theme = next;
          this.applyThemeClass();
        }
      }
    }
  }
};
</script>

<!-- 全局（非 scoped）：绿主题覆盖层必须注入到组件树外才全局生效；
     组件随 KawaiiTopbar（KawaiiLayout 常驻子节点）加载，:root 粉彩主题不受影响 -->
<style lang="scss">
@import '@/styles/kawaii/theme-green.scss';
</style>

<style lang="scss" scoped>
.theme-toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--kawaii-space-1);
  height: 32px;
  padding: 0 var(--kawaii-space-3);
  border: 1px solid var(--kawaii-border);
  border-radius: var(--kawaii-radius-full);
  background: var(--kawaii-surface);
  box-shadow: var(--kawaii-shadow);
  cursor: pointer;
  font-family: var(--kawaii-font-family);
  font-size: var(--kawaii-font-size-sm);
  color: var(--kawaii-text);
  transition:
    box-shadow var(--kawaii-duration-fast) var(--kawaii-ease-out),
    border-color var(--kawaii-duration-fast) var(--kawaii-ease-out);

  &:hover {
    border-color: var(--kawaii-primary);
    box-shadow: var(--kawaii-shadow-hover);
  }

  &:focus-visible {
    outline: 2px solid var(--kawaii-primary-focus);
    outline-offset: 1px;
  }
}

// 主题色点：固定双色（不随 var 变化），表达「另一侧」预览
.theme-toggle__dot {
  width: 10px;
  height: 10px;
  border-radius: var(--kawaii-radius-full);
  flex-shrink: 0;

  &--pink {
    background: #FF8FAB;
    box-shadow: inset 0 0 0 2px #FFE3EA;
  }

  &--green {
    background: #7BC8A4;
    box-shadow: inset 0 0 0 2px #D2EDDF;
  }
}

.theme-toggle__label {
  white-space: nowrap;
  user-select: none;
}

// 窄屏顶栏空间紧张时隐藏文字标签，仅留色点
@media (max-width: 767px) {
  .theme-toggle__label {
    display: none;
  }

  .theme-toggle {
    width: 32px;
    padding: 0;
    justify-content: center;
  }
}
</style>
