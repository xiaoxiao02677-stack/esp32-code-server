/* 主题切换：深色（源站默认）/ 浅色，CSS 变量整包替换 */
(function () {
  'use strict';

  var DARK = {
    '--ant-color-primary': '#FFFFFF',
    '--ant-color-primary-hover': '#E4E4E7',
    '--ant-color-primary-border': '#A1A1AA',
    '--ant-color-info': '#6366F1',
    '--ant-color-error': '#EF4444',
    '--ant-color-error-bg': 'rgba(239, 68, 68, 0.08)',
    '--ant-color-success': '#10B981',
    '--ant-color-warning': '#F59E0B',
    '--ant-color-bg-base': '#09090B',
    '--ant-color-bg-container': '#18181B',
    '--ant-color-bg-elevated': '#27272A',
    '--ant-color-border': '#3F3F46',
    '--ant-color-border-secondary': '#27272A',
    '--ant-color-text': '#FAFAFA',
    '--ant-color-text-secondary': '#A1A1AA',
    '--ant-color-text-tertiary': '#71717A',
    '--ant-color-text-quaternary': '#52525B',
    '--ant-color-text-inverse': '#09090B',
    '--ant-color-fill-quaternary': '#27272A',
    '--ant-color-fill-tertiary': '#3F3F46',
    '--ant-color-fill-secondary': '#27272A',
    '--ant-color-error-hover': '#F87171',
    '--ant-color-primary-bg': 'rgba(255, 255, 255, 0.12)',
    '--box-shadow': '0 4px 24px 0 rgba(0, 0, 0, 0.4)',
    '--box-shadow-secondary': '0 8px 32px 0 rgba(0, 0, 0, 0.48)',
    '--primary-color': '#FAFAFA',
    '--text-color': '#FAFAFA',
    '--text-secondary': '#A1A1AA',
    '--bg-secondary': '#27272A'
  };

  var LIGHT = {
    '--ant-color-primary': '#111827',
    '--ant-color-primary-hover': '#374151',
    '--ant-color-primary-border': '#4B5563',
    '--ant-color-info': '#4F46E5',
    '--ant-color-error': '#DC2626',
    '--ant-color-error-bg': 'rgba(220, 38, 38, 0.06)',
    '--ant-color-success': '#059669',
    '--ant-color-warning': '#D97706',
    '--ant-color-bg-base': '#F4F5F7',
    '--ant-color-bg-container': '#FFFFFF',
    '--ant-color-bg-elevated': '#FFFFFF',
    '--ant-color-border': '#E5E7EB',
    '--ant-color-border-secondary': '#F3F4F6',
    '--ant-color-text': '#111827',
    '--ant-color-text-secondary': '#4B5563',
    '--ant-color-text-tertiary': '#9CA3AF',
    '--ant-color-text-quaternary': '#D1D5DB',
    '--ant-color-text-inverse': '#FFFFFF',
    '--ant-color-fill-quaternary': '#F3F4F6',
    '--ant-color-fill-tertiary': '#E5E7EB',
    '--ant-color-fill-secondary': '#EEF0F3',
    '--ant-color-error-hover': '#EF4444',
    '--ant-color-primary-bg': 'rgba(17, 24, 39, 0.08)',
    '--box-shadow': '0 4px 24px 0 rgba(0, 0, 0, 0.02)',
    '--box-shadow-secondary': '0 8px 32px 0 rgba(0, 0, 0, 0.04)',
    '--primary-color': '#111827',
    '--text-color': '#111827',
    '--text-secondary': '#4B5563',
    '--bg-secondary': '#F9FAFB'
  };

  function applyTheme(name) {
    var tokens = name === 'dark' ? DARK : LIGHT;
    var root = document.documentElement;
    Object.keys(tokens).forEach(function (k) {
      root.style.setProperty(k, tokens[k]);
    });
    root.dataset.theme = name;
    try { localStorage.setItem('qx-clone-theme', name); } catch (e) {}
  }

  // 初始化：记忆 > 深色（源站默认）
  var saved = null;
  try { saved = localStorage.getItem('qx-clone-theme'); } catch (e) {}
  applyTheme(saved === 'light' ? 'light' : 'dark');

  window.QXTheme = {
    toggle: function () {
      var next = (document.documentElement.dataset.theme === 'dark') ? 'light' : 'dark';
      applyTheme(next);
      return next;
    },
    current: function () { return document.documentElement.dataset.theme; }
  };
})();
