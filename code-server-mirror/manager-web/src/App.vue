<template>
  <div id="app">
    <!-- 控制台进场进度条：0.3s 填满后自动淡出（motion-plus.scss） -->
    <div v-if="bootVisible" class="kawaii-boot-progress" :class="{ 'is-done': bootDone }">
      <div class="kawaii-boot-progress__bar"></div>
    </div>
    <!-- 光晕指针：柔粉径向光斑跟随鼠标（触屏/reduced-motion 自动隐藏） -->
    <div ref="cursorHalo" class="kawaii-cursor-halo"></div>
    <router-view />
    <cache-viewer v-if="isCDNEnabled" :visible.sync="showCacheViewer" />
  </div>
</template>

<style lang="scss">
#app {
  font-family: Avenir, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-align: center;
  color: #2c3e50;
}

nav {
  padding: 30px;

  a {
    font-weight: bold;
    color: #2c3e50;

    &.router-link-exact-active {
      color: #42b983;
    }
  }
}

.copyright {
  padding: 0 !important;
  color: rgb(0, 0, 0);
  font-size: 12px;
  font-weight: 400;
  margin-top: auto;
  width: 100%;
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
}

.el-message {
  top: 70px !important;
}
</style>
<script>
import CacheViewer from '@/components/CacheViewer.vue';
import { logCacheStatus } from '@/utils/cacheViewer';

export default {
  name: 'App',
  components: {
    CacheViewer
  },
  data() {
    return {
      showCacheViewer: false,
      isCDNEnabled: process.env.VUE_APP_USE_CDN === 'true',
      // 进场进度条：挂载即显示，0.3s 动画跑完后整体淡出并移除 DOM
      bootVisible: true,
      bootDone: false,
      // 光晕指针 rAF 句柄
      cursorRafId: null,
      cursorX: 0,
      cursorY: 0,
      haloX: 0,
      haloY: 0
    };
  },
  created() {
    // 挂载 store 状态
    this.$store.commit('setUserInfo', JSON.parse(localStorage.getItem('userInfo') || '{}'));
    this.$store.commit('setPubConfig', JSON.parse(localStorage.getItem('pubConfig') || '{}'));
  },
  mounted() {
    // 进场进度条：0.3s 填满 → 0.25s 淡出 → 移除 DOM
    setTimeout(() => { this.bootDone = true; }, 320);
    setTimeout(() => { this.bootVisible = false; }, 650);

    // 光晕指针：rAF 惯性跟随（reduced-motion / 触屏设备跳过）
    if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches && window.matchMedia('(hover: hover)').matches) {
      this.bindCursorHalo();
    }

    // 检测是否为移动设备且VUE_APP_H5_URL不为空，如果两个条件都满足则跳转到H5页面
    if (this.isMobileDevice() && process.env.VUE_APP_H5_URL) {
      window.location.href = process.env.VUE_APP_H5_URL;
      return;
    }
    
    // 只有在启用CDN时才添加相关事件和功能
    if (this.isCDNEnabled) {
      // 添加全局快捷键Alt+C用于显示缓存查看器
      document.addEventListener('keydown', this.handleKeyDown);

      // 在全局对象上添加缓存检查方法，便于调试
      window.checkCDNCacheStatus = () => {
        this.showCacheViewer = true;
      };

      // 在控制台输出提示信息
      console.info(
        '%c[' + this.$t('system.name') + '] ' + this.$t('cache.cdnEnabled'),
        'color: #409EFF; font-weight: bold;'
      );
      console.info(
        '按下 Alt+C 组合键或在控制台运行 checkCDNCacheStatus() 可以查看CDN缓存状态'
      );

      // 检查Service Worker状态
      this.checkServiceWorkerStatus();
    } else {
      console.info(
        '%c[' + this.$t('system.name') + '] ' + this.$t('cache.cdnDisabled'),
        'color: #67C23A; font-weight: bold;'
      );
    }
  },
  beforeDestroy() {
    // 光晕指针：解绑防泄漏
    if (this.cursorRafId !== null) {
      cancelAnimationFrame(this.cursorRafId);
      window.removeEventListener('mousemove', this.handleCursorMove);
      this.cursorRafId = null;
    }
    // 只有在启用CDN时才需要移除事件监听
    if (this.isCDNEnabled) {
      document.removeEventListener('keydown', this.handleKeyDown);
    }
  },
  methods: {
    // ---------- 光晕指针 ----------
    handleCursorMove(e) {
      this.cursorX = e.clientX;
      this.cursorY = e.clientY;
      const halo = this.$refs.cursorHalo;
      if (halo && !halo.classList.contains('is-active')) {
        halo.classList.add('is-active');
      }
    },
    bindCursorHalo() {
      window.addEventListener('mousemove', this.handleCursorMove, { passive: true });
      const halo = this.$refs.cursorHalo;
      const tick = () => {
        // 轻微惯性滞后（0.12 插值），光斑像果冻一样跟手
        this.haloX += (this.cursorX - this.haloX) * 0.12;
        this.haloY += (this.cursorY - this.haloY) * 0.12;
        if (halo) {
          halo.style.transform = `translate3d(${this.haloX}px, ${this.haloY}px, 0)`;
        }
        this.cursorRafId = requestAnimationFrame(tick);
      };
      this.cursorRafId = requestAnimationFrame(tick);
    },
    handleKeyDown(e) {
      // Alt+C 快捷键
      if (e.altKey && e.key === 'c') {
        this.showCacheViewer = true;
      }
    },
    isMobileDevice() {
      // 检测是否为移动设备的函数
      return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    },
    
    async checkServiceWorkerStatus() {
      // 检查Service Worker是否已注册
      if ('serviceWorker' in navigator) {
        try {
          const registrations = await navigator.serviceWorker.getRegistrations();
          if (registrations.length > 0) {
            console.info(
              '%c[' + this.$t('system.name') + '] ' + this.$t('cache.serviceWorkerRegistered'),
              'color: #67C23A; font-weight: bold;'
            );

            // 输出缓存状态到控制台
            setTimeout(async () => {
              const hasCaches = await logCacheStatus();
              if (!hasCaches) {
                console.info(
                '%c[' + this.$t('system.name') + '] ' + this.$t('cache.noCacheDetected'),
                'color: #E6A23C; font-weight: bold;'
              );

              // 开发环境下提供额外提示
              if (process.env.NODE_ENV === 'development') {
                console.info(
                  '%c[' + this.$t('system.name') + '] ' + this.$t('cache.swDevEnvWarning'),
                  'color: #E6A23C; font-weight: bold;'
                );
                console.info(this.$t('cache.swCheckMethods'));
                console.info('1. ' + this.$t('cache.swCheckMethod1'));
                console.info('2. ' + this.$t('cache.swCheckMethod2'));
                console.info('3. ' + this.$t('cache.swCheckMethod3'));
              }
              }
            }, 2000);
          } else {
            console.info(
                  '%c[' + this.$t('system.name') + '] ' + this.$t('cache.serviceWorkerNotRegistered'),
                  'color: #F56C6C; font-weight: bold;'
                );

                if (process.env.NODE_ENV === 'development') {
                  console.info(
                    '%c[' + this.$t('system.name') + '] ' + this.$t('cache.swDevEnvNormal'),
                    'color: #E6A23C; font-weight: bold;'
                  );
                  console.info(this.$t('cache.swProdOnly'));
                  console.info(this.$t('cache.swTestingTitle'));
                  console.info('1. ' + this.$t('cache.swTestingStep1'));
                  console.info('2. ' + this.$t('cache.swTestingStep2'));
                }
          }
        } catch (error) {
          console.error('检查Service Worker状态失败:', error);
        }
      } else {
          console.warn(this.$t('cache.swNotSupported'));
        }
    }
  }
};
</script>