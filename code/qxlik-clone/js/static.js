/* static.js —— 静态克隆站的运行时交互
 * 1. 主题切换（dark/light/auto）：切换 <style data-qx-theme> 的 disabled、
 *    同步 DOM 上 css-97cec0/css-1p8u2sp class、重设 html --ant-* 变量
 * 2. 侧栏菜单：子菜单展开收起、选中态互斥
 * 3. 顶栏：语言/主题下拉菜单、用户下拉菜单
 * 4. 页面内交互：modal 开关（创建按钮 -> 弹窗）、抽屉
 */
(function () {
  'use strict';

  var DARK_HASH = 'css-97cec0';
  var LIGHT_HASH = 'css-1p8u2sp';

  var THEME_VARS = {
    dark: {
      '--ant-color-primary': '#FFFFFF', '--ant-color-info': '#6366F1',
      '--ant-color-error': '#EF4444', '--ant-color-success': '#10B981',
      '--ant-color-warning': '#F59E0B', '--ant-color-bg-base': '#09090B',
      '--ant-color-bg-container': '#18181B', '--ant-color-bg-elevated': '#27272A',
      '--ant-color-border': '#3F3F46', '--ant-color-text': '#FAFAFA',
      '--ant-color-text-secondary': '#A1A1AA', '--ant-color-text-tertiary': '#71717A',
      '--ant-color-text-quaternary': '#52525B', '--ant-color-fill-quaternary': '#27272A',
      '--ant-color-fill-tertiary': '#3F3F46', '--ant-color-error-hover': '#F87171',
      '--ant-border-radius': '12', '--ant-border-radius-l-g': '16', '--ant-border-radius-s-m': '8',
      '--ant-font-family': "'DM Sans', sans-serif",
      '--ant-box-shadow': '0 3px 6px -4px rgba(0, 0, 0, 0.48), 0 6px 16px 0 rgba(0, 0, 0, 0.32), 0 9px 28px 8px rgba(0, 0, 0, 0.20)',
      '--ant-box-shadow-secondary': '0 8px 32px 0 rgba(0, 0, 0, 0.48)',
      '--ant-control-height': '40', '--ant-color-primary-hover': '#40a9ff',
      '--ant-color-primary-bg': '#111d2c', '--ant-color-success-bg': '#162312',
      '--ant-color-error-bg': '#2c1618', '--ant-color-warning-bg': '#2b2111',
      '--ant-color-text-inverse': '#ffffff', '--ant-color-white': '#ffffff',
      '--ant-color-text-placeholder': '#595959', '--ant-color-border-secondary': '#303030'
    },
    light: {
      '--ant-color-primary': '#111827', '--ant-color-info': '#4F46E5',
      '--ant-color-error': '#DC2626', '--ant-color-success': '#059669',
      '--ant-color-warning': '#D97706', '--ant-color-bg-base': '#F4F5F7',
      '--ant-color-bg-container': '#FFFFFF', '--ant-color-bg-elevated': '#FFFFFF',
      '--ant-color-border': '#E5E7EB', '--ant-color-text': '#111827',
      '--ant-color-text-secondary': '#4B5563', '--ant-color-text-tertiary': '#9CA3AF',
      '--ant-color-text-quaternary': '#D1D5DB', '--ant-color-fill-quaternary': '#F3F4F6',
      '--ant-color-fill-tertiary': '#E5E7EB', '--ant-color-error-hover': '#EF4444',
      '--ant-border-radius': '12', '--ant-border-radius-l-g': '16', '--ant-border-radius-s-m': '8',
      '--ant-font-family': "'DM Sans', sans-serif",
      '--ant-box-shadow': '0 3px 6px -4px rgba(0, 0, 0, 0.12), 0 6px 16px 0 rgba(0, 0, 0, 0.08), 0 9px 28px 8px rgba(0, 0, 0, 0.05)',
      '--ant-box-shadow-secondary': '0 8px 32px 0 rgba(0, 0, 0, 0.04)',
      '--ant-control-height': '40', '--ant-color-primary-hover': '#40a9ff',
      '--ant-color-primary-bg': '#e6f7ff', '--ant-color-success-bg': '#f6ffed',
      '--ant-color-error-bg': '#fff1f0', '--ant-color-warning-bg': '#fffbe6',
      '--ant-color-text-inverse': '#ffffff', '--ant-color-white': '#ffffff',
      '--ant-color-text-placeholder': '#bfbfbf', '--ant-color-border-secondary': '#f0f0f0'
    }
  };

  var MODE_KEY = 'theme-mode';

  function resolveMode() {
    var mode = localStorage.getItem(MODE_KEY) || 'auto';
    if (mode === 'auto') {
      mode = (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
    }
    return mode;
  }

  function applyTheme(mode) {
    var root = document.documentElement;
    var vars = THEME_VARS[mode];
    Object.keys(vars).forEach(function (k) {
      root.style.setProperty(k, vars[k]);
    });
    // 切换样式块
    document.querySelectorAll('style[data-qx-theme]').forEach(function (st) {
      st.disabled = (st.getAttribute('data-qx-theme') !== mode);
    });
    // 切换 DOM class 哈希
    var from = mode === 'dark' ? LIGHT_HASH : DARK_HASH;
    var to = mode === 'dark' ? DARK_HASH : LIGHT_HASH;
    document.querySelectorAll('.' + from).forEach(function (el) {
      el.classList.remove(from);
      el.classList.add(to);
    });
    // 更新主题按钮文案
    updateThemeLabel(mode);
    // 通知 demo 数据等运行时渲染的内容同步哈希
    document.dispatchEvent(new CustomEvent('qx-theme-change', { detail: { mode: mode } }));
  }

  function updateThemeLabel(mode) {
    var label = document.querySelector('.theme-dropdown .btn-text');
    if (label) {
      var names = { dark: '🌙 暗色', light: '☀️ 亮色', auto: '🔄 自动' };
      var stored = localStorage.getItem(MODE_KEY) || 'auto';
      label.textContent = names[stored];
    }
  }

  function toggleTheme() {
    var cur = localStorage.getItem(MODE_KEY) || 'auto';
    var next = cur === 'light' ? 'dark' : cur === 'dark' ? 'auto' : 'light';
    localStorage.setItem(MODE_KEY, next);
    applyTheme(resolveMode());
  }

  /* ---------- 下拉菜单 ---------- */
  function closeAllDropdowns() {
    document.querySelectorAll('.qx-dd-open').forEach(function (el) {
      el.classList.remove('qx-dd-open');
      var menu = document.getElementById(el.getAttribute('data-dd-menu'));
      if (menu) menu.style.display = 'none';
    });
  }

  function buildDropdownMenu(trigger, items, onSelect) {
    var uid = 'qxdd_' + Math.random().toString(36).slice(2, 8);
    var menu = document.createElement('div');
    menu.id = uid;
    menu.className = 'qx-dd-menu';
    menu.style.cssText = 'position:absolute;z-index:10001;display:none;' +
      'background-color:var(--ant-color-bg-elevated);border:1px solid var(--ant-color-border);' +
      'border-radius:16px;box-shadow:var(--ant-box-shadow-secondary);padding:4px;min-width:140px;';
    items.forEach(function (it) {
      var item = document.createElement('div');
      item.className = 'qx-dd-item';
      item.textContent = it.label;
      item.style.cssText = 'padding:9px 12px;border-radius:8px;cursor:pointer;color:var(--ant-color-text);' +
        'font-size:14px;font-family:var(--ant-font-family);transition:background-color .2s;';
      item.addEventListener('mouseenter', function () { item.style.backgroundColor = 'var(--ant-color-fill-quaternary)'; });
      item.addEventListener('mouseleave', function () { item.style.backgroundColor = ''; });
      item.addEventListener('click', function () {
        closeAllDropdowns();
        if (it.action) it.action();
        else if (onSelect) onSelect(it);
      });
      menu.appendChild(item);
    });
    document.body.appendChild(menu);
    trigger.setAttribute('data-dd-menu', uid);
    trigger.addEventListener('click', function (e) {
      e.stopPropagation();
      var isOpen = trigger.classList.contains('qx-dd-open');
      closeAllDropdowns();
      if (!isOpen) {
        trigger.classList.add('qx-dd-open');
        var r = trigger.getBoundingClientRect();
        menu.style.display = 'block';
        menu.style.left = (r.left - (menu.offsetWidth - r.width)) + 'px';
        menu.style.top = (r.bottom + 6) + 'px';
      }
    });
  }

  function setupHeaderDropdowns() {
    // 主题下拉
    var themeBtn = document.querySelector('.theme-dropdown');
    if (themeBtn) {
      buildDropdownMenu(themeBtn, [
        { label: '☀️ 亮色模式', action: function () { localStorage.setItem(MODE_KEY, 'light'); applyTheme('light'); } },
        { label: '🌙 暗色模式', action: function () { localStorage.setItem(MODE_KEY, 'dark'); applyTheme('dark'); } },
        { label: '🔄 跟随系统', action: function () { localStorage.setItem(MODE_KEY, 'auto'); applyTheme(resolveMode()); } }
      ]);
    }
    // 语言下拉
    var localeBtn = document.querySelector('.locale-dropdown');
    if (localeBtn) {
      buildDropdownMenu(localeBtn, [
        { label: '简体中文', action: function () { var t = localeBtn.querySelector('.btn-text'); if (t) t.textContent = '简体中文'; } },
        { label: 'English', action: function () { var t = localeBtn.querySelector('.btn-text'); if (t) t.textContent = 'English'; } },
        { label: '日本語', action: function () { var t = localeBtn.querySelector('.btn-text'); if (t) t.textContent = '日本語'; } }
      ]);
    }
    // 用户下拉
    var userInfo = document.querySelector('.user-info');
    if (userInfo) {
      buildDropdownMenu(userInfo, [
        { label: '👤 个人中心', action: function () { window.location.href = 'setting-account.html'; } },
        {
          label: '🚪 退出登录',
          action: function () {
            if (window.QXAuth && QXAuth.getToken()) {
              QXAuth.logout();   // 调 /api/auth/logout 注销 token 后跳登录
            } else {
              window.location.href = '../login.html';
            }
          }
        }
      ]);
    }
    document.addEventListener('click', closeAllDropdowns);
  }

  /* ---------- 侧栏菜单 ---------- */
  function setupSidebar() {
    var menu = document.querySelector('.sidebar-menu');
    if (!menu) return;
    // 菜单项点击 -> 跳转
    menu.querySelectorAll('li.ant-menu-item[data-menu-id]').forEach(function (li) {
      li.style.cursor = 'pointer';
      li.addEventListener('click', function () {
        var id = li.getAttribute('data-menu-id');
        var map = {
          '/dashboard': 'index.html', '/user': 'user.html', '/device': 'device.html',
          '/role': 'role.html', '/memory/chat': 'memory-chat.html',
          '/memory/summary': 'memory-summary.html', '/memory/long': 'memory-long.html',
          '/config/model': 'config-model.html', '/config/agent': 'config-agent.html',
          '/config/stt': 'config-stt.html', '/config/tts': 'config-tts.html',
          '/config/mcp': 'config-mcp.html', '/config/oss': 'config-oss.html',
          '/chat': 'chat.html', '/firmware': 'firmware.html', '/template': 'template.html',
          '/reminder': 'reminder.html', '/knowledge': 'knowledge.html', '/music': 'music.html',
          '/auth-role': 'auth-role.html', '/voiceprint': 'voiceprint.html',
          '/setting/account': 'setting-account.html'
        };
        if (map[id]) window.location.href = map[id];
      });
    });
    // 子菜单折叠
    menu.querySelectorAll('li.ant-menu-submenu > div.ant-menu-submenu-title').forEach(function (title) {
      title.style.cursor = 'pointer';
      title.addEventListener('click', function () {
        var li = title.parentElement;
        var wasOpen = li.classList.contains('ant-menu-submenu-open');
        if (wasOpen) {
          li.classList.remove('ant-menu-submenu-open');
          li.classList.remove('ant-menu-submenu-selected');
        } else {
          li.classList.add('ant-menu-submenu-open');
        }
        var ul = li.querySelector(':scope > ul.ant-menu-sub');
        if (ul) ul.style.display = wasOpen ? 'none' : '';
      });
    });
    // logo 点击回首页
    var logoLink = document.querySelector('.logo-link');
    if (logoLink) logoLink.href = 'index.html';
  }

  /* ---------- 页面内 modal ---------- */
  var MODAL_DEFS = {
    template: {
      trigger: '创建模板', width: 800, title: '创建模板',
      body: '<form class="ant-form ant-form-horizontal ' + DARK_HASH + '">' +
        '<div class="ant-form-item ' + DARK_HASH + '"><div class="ant-row ant-form-item-row ' + DARK_HASH + '">' +
        '<div class="ant-col ant-col-4 ant-form-item-label ' + DARK_HASH + '"><label class="ant-form-item-required">模板名称</label></div>' +
        '<div class="ant-col ant-col-20 ant-form-item-control ' + DARK_HASH + '"><div class="ant-form-item-control-input"><div class="ant-form-item-control-input-content">' +
        '<input type="text" class="ant-input ' + DARK_HASH + '" placeholder="请输入模板名称"></div></div></div></div></div>' +
        '<div class="ant-form-item ' + DARK_HASH + '"><div class="ant-row ant-form-item-row ' + DARK_HASH + '">' +
        '<div class="ant-col ant-col-4 ant-form-item-label ' + DARK_HASH + '"><label class="ant-form-item-required">模板分类</label></div>' +
        '<div class="ant-col ant-col-20 ant-form-item-control ' + DARK_HASH + '"><div class="ant-form-item-control-input"><div class="ant-form-item-control-input-content">' +
        '<input type="text" class="ant-input ' + DARK_HASH + '" placeholder="请输入模板分类"></div></div></div></div></div>' +
        '<div class="ant-form-item ' + DARK_HASH + '"><div class="ant-row ant-form-item-row ' + DARK_HASH + '">' +
        '<div class="ant-col ant-col-4 ant-form-item-label ' + DARK_HASH + '"><label>模板描述</label></div>' +
        '<div class="ant-col ant-col-20 ant-form-item-control ' + DARK_HASH + '"><div class="ant-form-item-control-input"><div class="ant-form-item-control-input-content">' +
        '<input type="text" class="ant-input ' + DARK_HASH + '" placeholder="请输入模板描述"></div></div></div></div></div>' +
        '<div class="ant-form-item ' + DARK_HASH + '"><div class="ant-row ant-form-item-row ' + DARK_HASH + '">' +
        '<div class="ant-col ant-col-4 ant-form-item-label ' + DARK_HASH + '"><label>默认</label></div>' +
        '<div class="ant-col ant-col-20 ant-form-item-control ' + DARK_HASH + '"><div class="ant-form-item-control-input"><div class="ant-form-item-control-input-content">' +
        '<button type="button" class="ant-switch qx-switch ' + DARK_HASH + '"><div class="ant-switch-handle"></div></button></div></div></div></div></div>' +
        '<div class="ant-form-item ' + DARK_HASH + '"><div class="ant-row ant-form-item-row ' + DARK_HASH + '">' +
        '<div class="ant-col ant-col-4 ant-form-item-label ' + DARK_HASH + '"><label>模板内容</label></div>' +
        '<div class="ant-col ant-col-20 ant-form-item-control ' + DARK_HASH + '"><div class="ant-form-item-control-input"><div class="ant-form-item-control-input-content">' +
        '<textarea class="ant-input ' + DARK_HASH + '" placeholder="请输入模板内容" rows="6"></textarea></div></div></div></div></div>' +
        '</form>'
    }
  };

  function setupModals() {
    Object.keys(MODAL_DEFS).forEach(function (page) {
      var def = MODAL_DEFS[page];
      var btns = document.querySelectorAll('.bento-content-panel button');
      var triggerBtn = null;
      btns.forEach(function (b) {
        if (b.textContent.trim().indexOf(def.trigger) === 0) triggerBtn = b;
      });
      if (!triggerBtn) return;
      triggerBtn.addEventListener('click', function () {
        var hash = resolveMode() === 'light' ? LIGHT_HASH : DARK_HASH;
        var wrap = document.createElement('div');
        wrap.className = 'ant-modal-wrap';
        var modal = document.createElement('div');
        modal.className = 'ant-modal ' + hash;
        modal.style.cssText = 'width:' + def.width + 'px;margin:0 auto;';
        var inner = '<div tabindex="0"><div class="ant-modal-content">' +
          '<button type="button" aria-label="Close" class="ant-modal-close"><span class="ant-modal-close-x">' +
          '<span role="img" aria-label="close" class="anticon anticon-close ant-modal-close-icon"><svg focusable="false" data-icon="close" width="1em" height="1em" fill="currentColor" aria-hidden="true" viewBox="64 64 896 896"><path d="M799.86 166.31c.02 0 .04.02.08.06l57.69 57.7c.04.03.05.05.06.08a.12.12 0 010 .06c0 .03-.02.05-.06.09L569.93 512l287.7 287.7c.04.04.05.06.06.09a.12.12 0 010 .07c0 .02-.02.04-.06.08l-57.7 57.69c-.03.04-.05.05-.07.06a.12.12 0 01-.07 0c-.03 0-.05-.02-.09-.06L512 569.93l-287.7 287.7c-.04.04-.06.05-.09.06a.12.12 0 01-.07 0c-.02 0-.04-.02-.08-.06l-57.69-57.7c-.04-.03-.05-.05-.06-.07a.12.12 0 010-.07c0-.03.02-.05.06-.09L454.07 512l-287.7-287.7c-.04-.04-.05-.05-.06-.09a.12.12 0 010-.07c0-.02.02-.04.06-.08l57.7-57.69c.03-.04.05-.05.07-.06a.12.12 0 01.07 0c.03 0 .05.02.09.06L512 454.07l287.7-287.7c.04-.04.06-.05.09-.06a.12.12 0 01.07 0z"></path></svg></span></span></button>' +
          '<div class="ant-modal-header"><div class="ant-modal-title">' + def.title + '</div></div>' +
          '<div class="ant-modal-body">' + def.body + '</div>' +
          '<div class="ant-modal-footer"><div class="ant-modal-footer-buttons">' +
          '<button type="button" class="ant-btn ' + hash + '"><span>取 消</span></button>' +
          '<button type="button" class="ant-btn ant-btn-primary ' + hash + '"><span>确 定</span></button>' +
          '</div></div></div></div>';
        modal.innerHTML = inner;
        wrap.appendChild(modal);
        // 遮罩
        var mask = document.createElement('div');
        mask.className = 'ant-modal-mask';
        document.body.appendChild(mask);
        document.body.appendChild(wrap);
        function close() {
          wrap.remove();
          mask.remove();
        }
        modal.querySelector('.ant-modal-close').addEventListener('click', close);
        modal.querySelectorAll('.ant-modal-footer .ant-btn').forEach(function (b) {
          b.addEventListener('click', close);
        });
        mask.addEventListener('click', close);
        // switch toggle
        var sw = modal.querySelector('.qx-switch');
        if (sw) {
          sw.addEventListener('click', function () {
            sw.classList.toggle('ant-switch-checked');
          });
        }
      });
    });
  }

  /* ---------- 搜索/筛选交互（保留原生） ---------- */
  function setupTableButtons() {
    // 表格行"编辑/删除/查看"等按钮 hover 已有样式，无需 JS；删除按钮给确认
    document.querySelectorAll('.bento-content-panel').forEach(function (panel) {
      panel.addEventListener('click', function (e) {
        var t = e.target.closest ? e.target.closest('button, a') : null;
        if (!t) return;
        var txt = (t.textContent || '').trim();
        if (txt === '删 除' || txt === '删除') {
          if (!window.confirm('确认删除该条数据吗？')) {
            e.preventDefault();
            e.stopPropagation();
          } else {
            // 静态演示：删除所在行
            var tr = t.closest('tr');
            if (tr) tr.remove();
          }
        }
      });
    });
  }

  /* ---------- Tabs 切换（config/role 页的 创建/列表 Tab） ---------- */
  function setupTabs() {
    document.querySelectorAll('.ant-tabs').forEach(function (tabs) {
      var tabBtns = tabs.querySelectorAll('[role=tab]');
      var inkBar = tabs.querySelector('.ant-tabs-ink-bar');
      // 与 rc-tabs 运行时一致: 非激活 pane 用内联 display:none 收起（懒加载空槽/隐藏面板不占轨道高度）
      var syncPanes = function (activeId) {
        var holder = tabs.querySelector('.ant-tabs-content-holder') || tabs.parentElement;
        if (!holder) return;
        holder.querySelectorAll('.ant-tabs-tabpane').forEach(function (pane) {
          var isActive = pane.id === activeId;
          pane.classList.toggle('ant-tabs-tabpane-active', isActive);
          pane.setAttribute('aria-hidden', isActive ? 'false' : 'true');
          pane.setAttribute('tabindex', isActive ? '0' : '-1');
          if (pane.id === activeId) {
            pane.style.display = '';
          } else {
            pane.style.display = 'none';
          }
        });
      };
      // 初始: 以当前 active pane 为准收起其余
      var initActive = null;
      var holder0 = tabs.querySelector('.ant-tabs-content-holder') || tabs.parentElement;
      if (holder0) {
        holder0.querySelectorAll('.ant-tabs-tabpane').forEach(function (pane) {
          if (pane.classList.contains('ant-tabs-tabpane-active')) initActive = pane.id;
        });
      }
      if (initActive) syncPanes(initActive);
      tabBtns.forEach(function (btn) {
        btn.style.cursor = 'pointer';
        btn.addEventListener('click', function () {
          var target = btn.getAttribute('aria-controls');
          // tab 选中态
          tabBtns.forEach(function (b) {
            var tab = b.closest('.ant-tabs-tab');
            if (tab) tab.classList.remove('ant-tabs-tab-active');
            b.setAttribute('aria-selected', 'false');
          });
          var curTab = btn.closest('.ant-tabs-tab');
          if (curTab) curTab.classList.add('ant-tabs-tab-active');
          btn.setAttribute('aria-selected', 'true');
          // ink bar 位置
          if (inkBar && curTab) {
            inkBar.style.left = curTab.offsetLeft + 'px';
            inkBar.style.width = curTab.offsetWidth + 'px';
          }
          // 面板切换
          syncPanes(target);
        });
      });
    });
  }

  /* ---------- 表单控件静态行为 ---------- */
  function setupFormControls() {
    // switch 开关
    document.addEventListener('click', function (e) {
      var sw = e.target.closest ? e.target.closest('.ant-switch') : null;
      if (sw) {
        e.preventDefault();
        sw.classList.toggle('ant-switch-checked');
      }
      // select 下拉（表单里的 ant-select：简单开合演示）
      var sel = e.target.closest ? e.target.closest('.ant-select:not(.ant-select-open)') : null;
      if (sel && sel.querySelector('.ant-select-selector')) {
        sel.classList.add('ant-select-open');
        return;
      }
      var selOpen = e.target.closest ? e.target.closest('.ant-select.ant-select-open') : null;
      if (selOpen) {
        if (!e.target.closest('.ant-select-dropdown')) selOpen.classList.remove('ant-select-open');
      }
    });
    // radio 点击选中
    document.addEventListener('click', function (e) {
      var radio = e.target.closest ? e.target.closest('.ant-radio-wrapper') : null;
      if (radio) {
        var group = radio.closest('.ant-radio-group');
        if (group) group.querySelectorAll('.ant-radio-wrapper').forEach(function (r) {
          var input = r.querySelector('.ant-radio');
          if (input) input.classList.remove('ant-radio-checked');
        });
        var inp = radio.querySelector('.ant-radio');
        if (inp) inp.classList.add('ant-radio-checked');
      }
    });
  }

  function init() {
    // 初始主题
    var mode = resolveMode();
    applyTheme(mode);
    // 标记 html 当前模式（供动态元素选择哈希）
    document.documentElement.setAttribute('data-qx-mode', mode);
    setupHeaderDropdowns();
    setupSidebar();
    setupModals();
    setupTableButtons();
    setupTabs();
    setupFormControls();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
