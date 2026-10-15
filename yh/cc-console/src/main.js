import { createApp } from 'vue';
import App from './App.vue';
import './styles/kawaii.css';

createApp(App).mount('#app');

/* ===== stylekit: cursor-aura 光晕指针（MIT，rAF 驱动） ===== */
(function cursorAura() {
  if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const aura = document.createElement('div');
  aura.className = 'cursor-aura';
  document.body.appendChild(aura);
  let raf = 0;
  let x = 0;
  let y = 0;
  function render() {
    raf = 0;
    aura.style.transform = `translate3d(${x}px, ${y}px, 0)`;
  }
  window.addEventListener(
    'pointermove',
    (event) => {
      x = event.clientX;
      y = event.clientY;
      if (!raf) raf = requestAnimationFrame(render);
    },
    { passive: true }
  );
})();
