<template>
  <div>
    <div class="page-head">
      <div>
        <h1>微信 <span style="color:var(--primary)">绑定</span></h1>
        <p class="sub">绑定微信账号，通过微信与设备对话</p>
      </div>
    </div>

    <div class="panel wip-panel">
      <div class="empty-state">
        <div class="empty-icon"><YhIcon name="chat" /></div>
        <strong>微信绑定功能开发中</strong>
        <p>正在与微信 OpenClaw 平台对接，上线后将在这里提供扫码绑定入口。当前页面暂无可配置内容。</p>
        <span class="badge badge-orange"><span class="dot"></span>排期中</span>
      </div>
    </div>

    <div class="panel wip-panel" style="margin-top:16px">
      <div class="panel-head"><h3>上线后将支持</h3></div>
      <ul class="wip-list">
        <li>扫码绑定微信账号，一个微信管理多台设备</li>
        <li>微信内直接与设备对话，无需打开控制台</li>
        <li>设备消息推送到微信，离线也不错过</li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import YhIcon from '../../components/YhIcon.vue'
// 说明：原页面为 TODO 空壳（接口调用全部注释、按钮 alert「开发中」），
// 已改为规范占位页；后端 /api/wechat/openclaw/status 契约就绪后再接入真实绑定流程。
</script>

<style scoped>
.wip-panel { max-width: 640px; }
.wip-list {
  margin: 0; padding: 14px 24px 20px 40px; color: var(--text-sub);
  font-size: 13.5px; line-height: 1.9;
}
</style>
