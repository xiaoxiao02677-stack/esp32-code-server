<template>
  <div>
    <div class="page-head">
      <div>
        <h1>设备 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">绑定与查看你的小智设备</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary">＋ 绑定新设备</button>
        <button class="btn btn-ghost">↻ 刷新</button>
      </div>
    </div>

    <div class="hero-row">
      <div class="hero-blob" style="min-height:180px">
        <div>
          <div class="en">DEVICES / ONLINE</div>
          <h2>我的设备</h2>
          <p>圆屏 · 方屏 · 无屏全部支持</p>
        </div>
        <div class="blob-actions">
          <button class="btn btn-primary" @click="$router.push('/customer')">返回智能体</button>
        </div>
        <div class="blob-3d">📡</div>
      </div>
      <div class="stats-grid">
        <StatCard icon="📡" label="设备总数" :value="devices.length" />
        <StatCard icon="🟢" label="在线" :value="onlineCount" note="实时" />
        <StatCard icon="⏸" label="离线" :value="devices.length - onlineCount" />
        <StatCard icon="🔋" label="低电量" :value="lowBat" note="≤ 20%" />
      </div>
    </div>

    <DataTable title="设备清单" :total="devices.length" :page="1" :pages="1">
      <table class="data-table">
        <thead>
          <tr><th>设备信息</th><th>型号 / MAC</th><th>电量</th><th>状态</th><th>最近连接</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="d in devices" :key="d.id">
            <td>
              <div class="cell-main">{{ d.name }}</div>
              <div class="cell-sub">{{ d.agent }}</div>
            </td>
            <td>
              <div>{{ d.model }}</div>
              <div class="cell-sub">{{ d.mac }}</div>
            </td>
            <td>{{ d.battery }}%</td>
            <td>
              <span class="badge" :class="d.online ? 'badge-green' : 'badge-gray'">
                <span class="dot"></span>{{ d.online ? '在线' : '离线' }}
              </span>
            </td>
            <td style="color:var(--text-sub)">{{ d.lastSeen }}</td>
            <td>
              <div class="row-actions">
                <button class="link-btn">详情</button>
                <button class="link-btn">解绑</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </DataTable>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'

const devices = ref([
  { id: 1, name: '小智圆屏', agent: '豆包小何-副本', model: 'my-s3-tft', mac: '14:C1:9F:D1:33:48', battery: 76, online: true, lastSeen: '刚刚' },
  { id: 2, name: '客厅音箱', agent: '英语老师', model: 'bread-compact-wifi', mac: 'AA:BB:CC:DD:EE:FF', battery: 15, online: false, lastSeen: '2 小时前' }
])
const onlineCount = computed(() => devices.value.filter(d => d.online).length)
const lowBat = computed(() => devices.value.filter(d => d.battery <= 20).length)
</script>
