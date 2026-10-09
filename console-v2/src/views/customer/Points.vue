<template>
  <div>
    <div class="page-head">
      <div>
        <h1>积分中心</h1>
        <p class="sub">充值、兑换与用量扣费</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" disabled title="功能即将上线">🎁 积分商城兑换</button>
        <button class="btn btn-ghost" disabled title="功能即将上线">🎟 兑换码兑换</button>
      </div>
    </div>

    <div class="hero-row">
      <div class="hero-blob" style="min-height:170px">
        <div>
          <div class="en">POINTS / BILLING</div>
          <h2>积分动态</h2>
          <p>按量计费 · 透明消费</p>
        </div>
        <div class="blob-3d">💎</div>
      </div>
      <div class="stats-grid">
        <StatCard icon="📈" label="累计获得" value="—" note="敬请期待" />
        <StatCard icon="📉" label="累计消耗" value="—" note="敬请期待" />
        <StatCard icon="💎" label="可用积分" value="—" note="敬请期待" />
        <StatCard icon="⚙️" label="计费模式" value="—" note="敬请期待" />
      </div>
    </div>

    <DataTable title="积分动态" hint="全部记录 / 获得 / 消耗" :total="0" :page="1" :pages="1">
      <table class="data-table">
        <thead>
          <tr><th>类型</th><th>说明</th><th>积分变动</th><th>余额</th><th>时间</th></tr>
        </thead>
        <tbody></tbody>
      </table>
      <div class="empty-state">
        <div class="empty-icon">💎</div>
        <strong>积分功能即将上线，敬请期待</strong>
        <p>当前版本暂未开通积分服务，充值、兑换与用量扣费记录将在功能上线后展示</p>
        <button class="btn btn-ghost" style="margin-top:6px" @click="comingSoon">充值积分</button>
      </div>
    </DataTable>
  </div>
</template>

<script setup>
import { inject } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'

const toast = inject('toast')

function comingSoon() {
  toast('功能即将上线', 'info')
}
</script>
