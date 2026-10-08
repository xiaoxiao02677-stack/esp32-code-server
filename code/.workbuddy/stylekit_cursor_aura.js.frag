(function cursorAura() {
  if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  var aura = document.createElement("div");
  aura.className = "cursor-aura";
  document.body.appendChild(aura);
  var raf = 0, x = 0, y = 0;
  function render() { raf = 0; aura.style.transform = "translate3d(" + x + "px," + y + "px,0)"; }
  window.addEventListener("pointermove", function (e) {
    x = e.clientX; y = e.clientY;
    if (!raf) raf = requestAnimationFrame(render);
  }, { passive: true });
})();