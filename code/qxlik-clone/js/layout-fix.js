/* layout-fix.js —— 全站排版可读性补丁 (2026-10-24)
 *
 * 职责：
 *  1. document.documentElement.lang 补全（原页面 lang=""）
 *  2. 为所有 .ellipsis-text 补 title 属性（悬浮查看全文）
 *  3. >24 字的长文本加 .qx-long-text 切换两行截断（配合 layout-fix.css）
 *  4. MutationObserver 兜底：demo-data.js 渲染完成后补扫
 *
 * 加载顺序：置于 static.js 与 demo-data.js 之后（DOM ready 后执行一轮 + observer 持续兜底）。
 */
(function () {
  'use strict';

  var LONG_TEXT_THRESHOLD = 24;

  if (document.documentElement && !document.documentElement.lang) {
    document.documentElement.lang = 'zh-CN';
  }

  /* ---------- title 补全 + 长文本标记 ---------- */
  function applyToNode(root) {
    if (!root || !root.querySelectorAll) return;
    var spans = root.querySelectorAll('.ellipsis-text:not([data-qx-fixed])');
    for (var i = 0; i < spans.length; i++) {
      var el = spans[i];
      el.setAttribute('data-qx-fixed', '1');
      var text = (el.textContent || '').trim();
      if (text && text !== '-' && !el.getAttribute('title')) {
        el.setAttribute('title', text);
      }
      // 长文本标记两行截断（CSS 里 .qx-long-text 定义）
      if (text.length > LONG_TEXT_THRESHOLD) {
        el.classList.add('qx-long-text');
      }
    }
  }

  function applyAll() {
    applyToNode(document);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', applyAll);
  } else {
    applyAll();
  }

  /* ---------- MutationObserver 兜底 demo-data.js 动态渲染 ---------- */
  if (window.MutationObserver) {
    var pending = false;
    var observer = new MutationObserver(function () {
      if (pending) return;
      pending = true;
      requestAnimationFrame(function () {
        pending = false;
        applyAll();
      });
    });
    var target = document.getElementById('app') || document.body;
    if (target) {
      observer.observe(target, { childList: true, subtree: true });
    }
  }
})();
