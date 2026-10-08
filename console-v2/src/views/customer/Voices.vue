<template>
  <div>
    <div class="page-head">
      <div>
        <h1>音色 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">试听与管理你的声音资源</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary">＋ 新建音色</button>
        <button class="btn btn-ghost" :disabled="!selected">▶ 试听音色</button>
      </div>
    </div>

    <div class="hero-row">
      <div class="hero-blob" style="min-height:170px">
        <div>
          <div class="en">VOICE / CLONING</div>
          <h2>音色工坊</h2>
          <p>豆包声音复刻 V3 · 30 秒克隆你的声音</p>
        </div>
        <div class="blob-3d">🎙</div>
      </div>
      <div class="stats-grid">
        <StatCard icon="🎙" label="音色" :value="voices.length" />
        <StatCard icon="✅" label="可用" :value="usable" />
        <StatCard icon="📦" label="已用配额" :value="usable + '/ 3'" />
        <StatCard icon="🔒" label="配额上限" value="3" note="当前套餐" />
      </div>
    </div>

    <DataTable title="音色清单" :total="voices.length" :page="1" :pages="1">
      <table class="data-table">
        <thead>
          <tr><th>试听</th><th>音色信息</th><th>配额</th><th>创建时间</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="v in voices" :key="v.id" @click="selected = v.id">
            <td><button class="link-btn" @click.stop>▶</button></td>
            <td>
              <div class="cell-main">{{ v.name }}</div>
              <div class="cell-sub">{{ v.desc }}</div>
            </td>
            <td>
              <span class="badge" :class="v.ready ? 'badge-green' : 'badge-orange'">
                <span class="dot"></span>{{ v.ready ? '可用' : '训练中' }}
              </span>
            </td>
            <td style="color:var(--text-sub)">{{ v.createdAt }}</td>
            <td>
              <div class="row-actions">
                <button class="link-btn">编辑</button>
                <button class="link-btn danger">删除</button>
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

const selected = ref(null)
const voices = ref([
  { id: 1, name: '豆包小何', desc: '预付费音色 · 元气少女', ready: true, createdAt: '2026-09-30' },
  { id: 2, name: '克隆-我的声音', desc: '声音复刻 V3 · 自定义', ready: true, createdAt: '2026-10-05' },
  { id: 3, name: '温柔姐姐', desc: '声音复刻 V3 · 训练中', ready: false, createdAt: '2026-10-08' }
])
const usable = computed(() => voices.value.filter(v => v.ready).length)
</script>
