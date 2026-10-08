<template>
  <div>
    <div class="page-head">
      <div>
        <h1>积分中心</h1>
        <p class="sub">充值、兑换与用量扣费</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary">🎁 积分商城兑换</button>
        <button class="btn btn-ghost">🎟 兑换码兑换</button>
      </div>
    </div>

    <div class="hero-row">
      <div class="hero-blob" style="min-height:170px">
        <div>
          <div class="en">POINTS / BILLING</div>
          <h2>积分动态</h2>
          <p>按量计费 · 透明消费</p>
        </div>
        <div class="blob-actions">
          <button class="btn btn-primary">充值积分</button>
        </div>
        <div class="blob-3d">💎</div>
      </div>
      <div class="stats-grid">
        <StatCard icon="📈" label="累计获得" :value="earned" />
        <StatCard icon="📉" label="累计消耗" :value="spent" />
        <StatCard icon="💎" label="可用积分" :value="balance" />
        <StatCard icon="⚙️" label="计费模式" value="ENFORCE" note="按量扣费" />
      </div>
    </div>

    <DataTable title="积分动态" hint="全部记录 / 获得 / 消耗" :total="records.length" :page="1" :pages="1">
      <template #actions>
        <div style="display:flex;gap:8px">
          <button class="btn btn-ghost" style="padding:6px 14px;font-size:12.5px">全部记录</button>
          <button class="btn btn-ghost" style="padding:6px 14px;font-size:12.5px">获得</button>
          <button class="btn btn-ghost" style="padding:6px 14px;font-size:12.5px">消耗</button>
        </div>
      </template>
      <table class="data-table">
        <thead>
          <tr><th>类型</th><th>说明</th><th>积分变动</th><th>余额</th><th>时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in records" :key="r.id">
            <td>
              <span class="badge" :class="r.delta > 0 ? 'badge-green' : 'badge-orange'">
                <span class="dot"></span>{{ r.delta > 0 ? '获得' : '消耗' }}
              </span>
            </td>
            <td>{{ r.desc }}</td>
            <td :style="{ color: r.delta > 0 ? 'var(--success)' : 'var(--danger)', fontWeight: 700 }">
              {{ r.delta > 0 ? '+' : '' }}{{ r.delta.toFixed(1) }}
            </td>
            <td>{{ r.balanceAfter.toFixed(1) }}</td>
            <td style="color:var(--text-sub)">{{ r.time }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="records.length === 0" class="empty-state">
        <div class="empty-icon">💎</div>
        <strong>暂无积分记录</strong>
      </div>
    </DataTable>
  </div>
</template>

<script setup>
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'

const earned = '200.0'
const spent = '71.5'
const balance = '128.5'

const records = [
  { id: 1, desc: '充值 100 元赠送', delta: 100.0, balanceAfter: 200.0, time: '10-06 20:12' },
  { id: 2, desc: '对话用量扣费 · 豆包小何', delta: -1.2, balanceAfter: 130.9, time: '10-08 17:47' },
  { id: 3, desc: 'TTS 合成扣费', delta: -2.4, balanceAfter: 128.5, time: '10-08 17:48' }
]
</script>
