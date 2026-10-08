<template>
  <div class="mem-graph-wrap">
    <div ref="graphChart" class="mem-graph-chart" :style="{ height: chartHeight }"></div>
    <div v-if="!loading && nodes.length === 0" class="mem-graph-empty">{{ $t('memoryManagement.graphEmpty') }}</div>
    <div class="mem-graph-legend">
      <span class="legend-item"><i class="dot dot--entity"></i>{{ $t('memoryManagement.legendEntity') }}</span>
      <span class="legend-item"><i class="dot dot--fact"></i>{{ $t('memoryManagement.legendFact') }}</span>
      <span class="legend-item"><i class="dot dot--hot"></i>{{ $t('memoryManagement.legendHot') }}</span>
    </div>
  </div>
</template>

<script>
import * as echarts from 'echarts';

/* 记忆实体关系图：实体节点 + 记忆节点（按实体聚合）
 * 数据来源：factList（含 entities 数组，由详情接口或 holographic 引擎提供）
 * 无 entities 的条目归入"未关联"虚拟节点，保证图不丢数据 */
const PALETTE = ['#FF8FAB', '#FFB6C6', '#FFD86B', '#9EE6D0', '#B8A9F5', '#8FC7FF', '#FFC3A0', '#A8E6CF'];

export default {
  name: 'MemoryGraph',
  props: {
    facts: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false },
    chartHeight: { type: String, default: '560px' }
  },
  data() {
    return { chart: null, nodes: [], links: [] };
  },
  watch: {
    facts: {
      handler() { this.renderChart(); },
      deep: false
    }
  },
  mounted() {
    this.renderChart();
    window.addEventListener('resize', this.handleResize);
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.handleResize);
    if (this.chart) { this.chart.dispose(); this.chart = null; }
  },
  methods: {
    handleResize() {
      if (this.chart) this.chart.resize();
    },
    buildGraph() {
      const entityMap = new Map(); // 实体名 → {count, facts:[]}
      const nodes = [];
      const links = [];
      const factsWithEntities = [];
      const orphanFacts = [];

      (this.facts || []).forEach((f) => {
        const ents = Array.isArray(f.entities) && f.entities.length
          ? f.entities
          : [];
        if (ents.length) factsWithEntities.push({ fact: f, ents });
        else orphanFacts.push(f);
        ents.forEach((e) => {
          if (!entityMap.has(e)) entityMap.set(e, { count: 0, facts: [] });
          entityMap.get(e).count += 1;
          entityMap.get(e).facts.push(f);
        });
      });

      /* 实体节点：大小随出现次数，颜色按类别轮转 */
      let ci = 0;
      entityMap.forEach((info, name) => {
        const hot = info.count >= 3;
        nodes.push({
          id: 'e:' + name,
          name,
          symbolSize: Math.min(28 + info.count * 8, 64),
          category: hot ? 'hot' : 'entity',
          itemStyle: {
            color: hot ? '#FF8FAB' : PALETTE[ci++ % PALETTE.length],
            borderColor: '#fff',
            borderWidth: 2,
            shadowBlur: hot ? 14 : 6,
            shadowColor: 'rgba(255,143,171,0.45)'
          },
          label: { show: true, fontSize: 12, color: '#4b3b44' },
          value: info.count
        });
      });

      /* 记忆节点（圆角胶囊不好做，用小圆）+ 实体↔记忆 连线 */
      factsWithEntities.forEach(({ fact, ents }, idx) => {
        const fid = 'f:' + (fact.factId || fact.id || idx);
        nodes.push({
          id: fid,
          name: this.shortText(fact.content, 14),
          tooltip: this.factTooltip(fact),
          symbolSize: 12,
          category: 'fact',
          itemStyle: { color: '#FFF0F5', borderColor: '#FFB6C6', borderWidth: 1.5 }
        });
        ents.forEach((e) => {
          links.push({
            source: 'e:' + e,
            target: fid,
            lineStyle: { color: 'rgba(255,143,171,0.35)', width: 1.5, curveness: 0.15 }
          });
        });
      });

      /* 无实体记忆 → 汇聚到虚拟节点 */
      if (orphanFacts.length) {
        nodes.push({
          id: 'e:__orphan__',
          name: this.$t('memoryManagement.orphanNode'),
          symbolSize: 30,
          category: 'entity',
          itemStyle: { color: '#E8E3E8', borderColor: '#fff', borderWidth: 2 },
          label: { show: true, fontSize: 12, color: '#8d7f86' }
        });
        orphanFacts.forEach((fact, idx) => {
          const fid = 'f:' + (fact.factId || fact.id || 'o' + idx);
          nodes.push({
            id: fid,
            name: this.shortText(fact.content, 14),
            tooltip: this.factTooltip(fact),
            symbolSize: 12,
            category: 'fact',
            itemStyle: { color: '#FFF0F5', borderColor: '#FFB6C6', borderWidth: 1.5 }
          });
          links.push({
            source: 'e:__orphan__',
            target: fid,
            lineStyle: { color: 'rgba(160,150,158,0.3)', width: 1, curveness: 0.1 }
          });
        });
      }

      return { nodes, links };
    },
    shortText(t, n) {
      t = String(t || '');
      return t.length > n ? t.slice(0, n) + '…' : t;
    },
    factTooltip(fact) {
      const cat = fact.category || 'general';
      const trust = fact.trustScore !== undefined ? Number(fact.trustScore).toFixed(2) : '—';
      return `${fact.content}<br/><b>${cat}</b> · 信任 ${trust} · ${fact.createdAt || ''}`;
    },
    renderChart() {
      if (!this.$refs.graphChart) return;
      const { nodes, links } = this.buildGraph();
      this.nodes = nodes;
      this.links = links;
      if (!this.chart) {
        this.chart = echarts.init(this.$refs.graphChart);
      }
      const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      this.chart.setOption({
        backgroundColor: 'transparent',
        tooltip: {
          trigger: 'item',
          backgroundColor: 'rgba(255,247,250,0.96)',
          borderColor: '#ffd9e3',
          borderWidth: 1,
          textStyle: { color: '#4b3b44', fontSize: 12 },
          formatter: (p) => {
            if (p.dataType === 'node') {
              if (p.data.category === 'fact') return p.data.tooltip || p.data.name;
              const cnt = p.data.value || 1;
              return `<b>${p.name}</b><br/>出现 ${cnt} 次`;
            }
            return '';
          }
        },
        animationDuration: reduced ? 0 : 900,
        animationEasing: 'elasticOut',
        series: [{
          type: 'graph',
          layout: 'force',
          roam: true,
          draggable: true,
          data: nodes,
          links,
          force: {
            repulsion: 130,
            edgeLength: [50, 120],
            gravity: 0.08,
            layoutAnimation: !reduced
          },
          emphasis: {
            focus: 'adjacency',
            lineStyle: { color: '#FF8FAB', width: 2.5 }
          },
          lineStyle: { opacity: 0.8 }
        }]
      }, true);
    }
  }
};
</script>

<style lang="scss" scoped>
.mem-graph-wrap {
  position: relative;
  width: 100%;
  border-radius: var(--kawaii-radius, 14px);
  background: var(--kawaii-surface, #fff);
  border: 1px solid var(--kawaii-border, #ffd9e3);
  overflow: hidden;
}
.mem-graph-chart {
  width: 100%;
}
.mem-graph-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--kawaii-text-soft, #a08e96);
  background: var(--kawaii-bg, #FFF7FA);
  font-size: 0.9rem;
}
.mem-graph-legend {
  display: flex;
  gap: 16px;
  justify-content: center;
  padding: 8px 0 10px;
  border-top: 1px dashed var(--kawaii-border, #ffd9e3);
  background: var(--kawaii-surface, #fff);
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  color: var(--kawaii-text-soft, #a08e96);
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}
.dot--entity { background: #9EE6D0; }
.dot--fact { background: #FFF0F5; border: 1.5px solid #FFB6C6; box-sizing: border-box; }
.dot--hot { background: #FF8FAB; }
</style>
