/* ===== stylekit: fade-in-up (MIT) ===== */
@keyframes fade-in-up {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.fade-in-up {
  --sk-duration: 600ms;
  --sk-delay: 0ms;
  --sk-ease: cubic-bezier(0.16, 1, 0.3, 1);
  will-change: transform, opacity;
  animation: fade-in-up var(--sk-duration) var(--sk-ease) var(--sk-delay) both;
}

@media (prefers-reduced-motion: reduce) {
  .fade-in-up {
    animation: none;
    opacity: 1;
    transform: none;
  }
}

/* ===== stylekit: slide-in-left (MIT) ===== */
@keyframes slide-in-left {
  from {
    opacity: 0;
    transform: translateX(-30px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.slide-in-left {
  --sk-duration: 500ms;
  --sk-delay: 0ms;
  --sk-ease: cubic-bezier(0.16, 1, 0.3, 1);
  will-change: transform, opacity;
  animation: slide-in-left var(--sk-duration) var(--sk-ease) var(--sk-delay) both;
}

@media (prefers-reduced-motion: reduce) {
  .slide-in-left {
    animation: none;
    opacity: 1;
    transform: none;
  }
}

/* ===== stylekit: border-trace (MIT) ===== */
/* Approach 1: Gradient border with background-size animation */
@keyframes border-trace {
  0% {
    background-size: 0 2px, 2px 0, 0 2px, 2px 0;
  }
  25% {
    background-size: 100% 2px, 2px 0, 0 2px, 2px 0;
  }
  50% {
    background-size: 100% 2px, 2px 100%, 0 2px, 2px 0;
  }
  75% {
    background-size: 100% 2px, 2px 100%, 100% 2px, 2px 0;
  }
  100% {
    background-size: 100% 2px, 2px 100%, 100% 2px, 2px 100%;
  }
}

.border-trace {
  position: relative;
  background:
    linear-gradient(currentColor, currentColor) top left / 0 2px no-repeat,
    linear-gradient(currentColor, currentColor) top right / 2px 0 no-repeat,
    linear-gradient(currentColor, currentColor) bottom right / 0 2px no-repeat,
    linear-gradient(currentColor, currentColor) bottom left / 2px 0 no-repeat;
  transition: background-size 600ms ease-in-out;
}

.border-trace:hover {
  background-size: 100% 2px, 2px 100%, 100% 2px, 2px 100%;
}

@media (prefers-reduced-motion: reduce) {
  .border-trace {
    transition: none;
    border: 2px solid currentColor;
  }
  .border-trace:hover {
    background: none;
  }
}

/* ===== stylekit: progress-bar (MIT) ===== */
@keyframes progress-fill {
  from { width: 0%; }
  to { width: 100%; }
}

@keyframes progress-shimmer {
  from { background-position: -200% 0; }
  to { background-position: 200% 0; }
}

.progress-bar {
  height: 4px;
  border-radius: 9999px;
  background: #e5e7eb;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  border-radius: 9999px;
  background: linear-gradient(
    90deg,
    #6366f1 0%,
    #818cf8 50%,
    #6366f1 100%
  );
  background-size: 200% 100%;
  animation:
    progress-fill 2s ease-in-out both,
    progress-shimmer 1.5s linear infinite;
}

@media (prefers-reduced-motion: reduce) {
  .progress-bar-fill {
    animation: none;
    width: 100%;
  }
}



/* ===== stylekit: hover-glow (MIT, 粉彩适配) ===== */
.hover-glow {
  position: relative;
}
.hover-glow::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  box-shadow: 0 0 15px rgba(249, 168, 212, 0.45), 0 0 30px rgba(249, 168, 212, 0.22);
  opacity: 0;
  transition: opacity 300ms ease-out;
  pointer-events: none;
  z-index: 0;
}
.hover-glow:hover::before { opacity: 1; }
@media (prefers-reduced-motion: reduce) { .hover-glow::before { display: none; } }

/* ===== stylekit: cursor-aura (MIT, 粉彩适配) ===== */
.cursor-aura {
  position: fixed;
  left: 0; top: 0;
  width: 34px; height: 34px;
  border-radius: 999px;
  translate: -50% -50%;
  pointer-events: none;
  background: radial-gradient(circle, rgba(249,168,212,0.22), transparent 62%);
  will-change: transform;
  z-index: 9999;
}