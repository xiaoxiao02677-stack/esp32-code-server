<template>
  <div class="nf">
    <div class="nf-code">404</div>
    <strong>页面不存在或已被移动</strong>
    <p>检查一下地址，或从下面的入口继续</p>
    <div class="nf-actions">
      <button class="btn btn-primary" @click="$router.push('/')">回首页</button>
      <button class="btn btn-ghost" @click="$router.back()">返回上一页</button>
    </div>
  </div>
</template>

<script setup>
</script>

<style scoped>
.nf {
  display: flex; flex-direction: column; align-items: center; gap: 10px;
  padding: 72px 0 88px; text-align: center;
}
.nf-code {
  font-size: 72px; font-weight: 800; line-height: 1;
  letter-spacing: 2px; color: var(--primary);
  font-variant-numeric: tabular-nums;
}
.nf strong { font-size: 16px; color: var(--text); }
.nf p { font-size: 13px; color: var(--text-sub); margin-bottom: 10px; }
.nf-actions { display: flex; gap: 10px; }
</style>
