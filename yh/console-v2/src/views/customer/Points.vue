<template>
  <div>
    <div class="page-head">
      <div>
        <h1>积分 <span style="color:var(--primary)">中心</span></h1>
        <p class="sub">充值、兑换与用量扣费</p>
      </div>
    </div>

    <div class="panel wip-panel">
      <div class="empty-state">
        <div class="empty-icon"><YhIcon name="gem" /></div>
        <strong>积分功能即将上线</strong>
        <p>当前版本暂未开通积分服务。上线后，充值、兑换与按量计费的完整记录都会在这里展示。</p>
        <span class="badge badge-orange"><span class="dot"></span>排期中</span>
      </div>
    </div>

    <div class="panel wip-panel" style="margin-top:16px">
      <div class="panel-head"><h3>上线后将支持</h3></div>
      <ul class="wip-list">
        <li>积分充值与兑换码兑换</li>
        <li>按量计费明细：每次调用的扣费记录</li>
        <li>积分动态：获得、消耗与余额一目了然</li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import YhIcon from '../../components/YhIcon.vue'
// 说明：原页面为空壳（假统计卡、空表格、disabled 死按钮），
// 已改为规范占位页；积分服务契约就绪后再接入真实数据。
</script>

<style scoped>
.wip-panel { max-width: 640px; }
.wip-list {
  margin: 0; padding: 14px 24px 20px 40px; color: var(--text-sub);
  font-size: 13.5px; line-height: 1.9;
}
</style>
