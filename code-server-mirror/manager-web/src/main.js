import 'element-ui/lib/theme-chalk/index.css';
import 'normalize.css/normalize.css'; // A modern alternative to CSS resets
import Vue from 'vue';
import ElementUI from 'element-ui';
import App from './App.vue';
import router from './router';
import store from './store';
import i18n from './i18n';
import locale from 'element-ui/lib/locale'
import './styles/global.scss';
import './styles/kawaii/index.scss';
import { register as registerServiceWorker } from './registerServiceWorker';
import featureManager from './utils/featureManager';

// 创建事件总线，用于组件间通信
Vue.prototype.$eventBus = new Vue();

Vue.use(ElementUI);
locale.i18n((key, value) => i18n.t(key, value))

Vue.config.productionTip = false

// 路径直达重写：router 为 hash 模式，直接访问 /cc（无 hash）会被默认路由
// 吸收并跳回 /home。在应用挂载前把裸路径翻译成 hash 路由，保证 /cc 直达可用。
(function rewritePathToHash() {
  const path = window.location.pathname;
  const directPaths = ['/cc'];
  if (directPaths.includes(path) && !window.location.hash) {
    window.location.replace(window.location.origin + '/#' + path);
  }
})();

// 注册Service Worker
registerServiceWorker();

// 创建Vue实例
new Vue({
  router,
  store,
  i18n,
  render: function (h) { return h(App) }
}).$mount('#app')
