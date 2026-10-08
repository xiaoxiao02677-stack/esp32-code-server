<template>
  <div class="mem-timeline-wrap">
    <div class="mem-timeline-track" ref="track">
      <div
        v-for="(group, gi) in grouped"
        :key="group.date"
        class="mem-tl-group"
        :style="{ animationDelay: (gi * 0.06) + 's' }"
      >
        <div class="mem-tl-date">
          <span class="mem-tl-date-dot"></span>
          <span class="mem-tl-date-text">{{ group.date }}</span>
          <span class="mem-tl-date-count">{{ group.items.length }}</span>
        </div>
        <div class="mem-tl-items">
          <div
            v-for="fact in group.items"
            :key="fact.factId || fact.id"
            class="mem-tl-item"
            :class="'mem-tl-item--' + (fact.category || 'general')"
            @click="$emit('fact-click', fact)"
          >
            <div class="mem-tl-item-head">
              <span class="mem-tl-cat">{{ categoryLabel(fact.category) }}</span>
              <span class="mem-tl-time">{{ timeOf(fact.createdAt) }}</span>
              <span v-if="fact.trustScore !== undefined" class="mem-tl-trust" :style="trustStyle(fact.trustScore)">
                {{ Number(fact.trustScore).toFixed(2) }}
              </span>
              <span v-if="fact.retrievalCount" class="mem-tl-rc">↺{{ fact.retrievalCount }}</span>
            </div>
            <div class="mem-tl-content">{{ fact.content }}</div>
            <div v-if="fact.tags" class="mem-tl-tags">
              <span v-for="t in tagList(fact.tags)" :key="t" class="mem-tl-tag">{{ t }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div v-if="!loading && grouped.length === 0" class="mem-tl-empty">{{ $t('memoryManagement.graphEmpty') }}</div>
  </div>
</template>

<script>
/* 记忆时间轴：按日期分组倒序，粉彩卡片流 + 类别色标 + 信任分热度
 * 信任分着色：≥0.75 粉（牢）、0.4~0.75 黄（中）、<0.4 灰（弱） */
export default {
  name: 'MemoryTimeline',
  props: {
    facts: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false }
  },
  computed: {
    grouped() {
      const map = new Map();
      (this.facts || []).forEach((f) => {
        const d = this.dateOf(f.createdAt);
        if (!map.has(d)) map.set(d, []);
        map.get(d).push(f);
      });
      return Array.from(map.entries())
        .sort((a, b) => (a[0] < b[0] ? 1 : -1))
        .map(([date, items]) => ({
          date,
          items: items.slice().sort((a, b) => this.timeOf(b.createdAt).localeCompare(this.timeOf(a.createdAt)))
        }));
    }
  },
  methods: {
    dateOf(ts) {
      if (!ts) return '—';
      return String(ts).slice(0, 10);
    },
    timeOf(ts) {
      if (!ts) return '';
      return String(ts).slice(11, 19) || '';
    },
    tagList(tags) {
      return String(tags || '').split(',').map((t) => t.trim()).filter(Boolean);
    },
    categoryLabel(c) {
      const keyMap = {
        preference: 'memoryManagement.categoryPreference',
        profile: 'memoryManagement.categoryProfile',
        habit: 'memoryManagement.categoryHabit',
        event: 'memoryManagement.categoryEvent',
        general: 'memoryManagement.categoryGeneral'
      };
      const key = keyMap[c] || keyMap.general;
      return this.$t(key);
    },
    trustStyle(v) {
      const n = Number(v);
      let color = '#a08e96';
      if (n >= 0.75) color = '#FF8FAB';
      else if (n >= 0.4) color = '#d98a2b';
      return { color, borderColor: color };
    }
  }
};
</script>

<style lang="scss" scoped>
.mem-timeline-wrap {
  position: relative;
  max-height: 640px;
  overflow-y: auto;
  padding: 6px 4px;
}
.mem-timeline-track {
  position: relative;
  padding-left: 18px;
  &::before {
    content: '';
    position: absolute;
    left: 6px;
    top: 8px;
    bottom: 8px;
    width: 3px;
    border-radius: 3px;
    background: linear-gradient(180deg, #FF8FAB, #FFD86B, #9EE6D0);
    opacity: 0.5;
  }
}
.mem-tl-group {
  animation: kawaii-fade-up 0.45s ease both;
  margin-bottom: 18px;
}
.mem-tl-date {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.mem-tl-date-dot {
  position: absolute;
  left: 0;
  width: 13px;
  height: 13px;
  border-radius: 50%;
  background: #fff;
  border: 3px solid #FF8FAB;
  box-shadow: 0 0 8px rgba(255, 143, 171, 0.5);
  margin-left: 1px;
}
.mem-tl-date-text {
  font-weight: 600;
  font-size: 0.92rem;
  color: var(--kawaii-text, #4b3b44);
}
.mem-tl-date-count {
  font-size: 0.72rem;
  background: var(--kawaii-surface-2, #fff0f5);
  color: var(--kawaii-text-soft, #a08e96);
  border-radius: 9999px;
  padding: 1px 9px;
}
.mem-tl-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.mem-tl-item {
  background: var(--kawaii-surface, #fff);
  border: 1px solid var(--kawaii-border, #ffd9e3);
  border-radius: 12px;
  padding: 10px 14px;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  text-align: left;
  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 5px 16px rgba(255, 143, 171, 0.22);
  }
  &.mem-tl-item--preference { border-left: 4px solid #FF8FAB; }
  &.mem-tl-item--profile { border-left: 4px solid #8FC7FF; }
  &.mem-tl-item--habit { border-left: 4px solid #FFD86B; }
  &.mem-tl-item--event { border-left: 4px solid #9EE6D0; }
  &.mem-tl-item--general { border-left: 4px solid #B8A9F5; }
}
.mem-tl-item-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}
.mem-tl-cat {
  font-size: 0.7rem;
  font-weight: 600;
  color: #4b3b44;
  background: #fff0f5;
  border-radius: 9999px;
  padding: 1px 9px;
}
.mem-tl-time {
  font-size: 0.74rem;
  color: var(--kawaii-text-soft, #a08e96);
  font-family: monospace;
}
.mem-tl-trust {
  font-size: 0.72rem;
  font-weight: 600;
  border: 1.5px solid;
  border-radius: 9999px;
  padding: 0 8px;
}
.mem-tl-rc {
  font-size: 0.72rem;
  color: #d98a2b;
}
.mem-tl-content {
  font-size: 0.86rem;
  color: var(--kawaii-text, #4b3b44);
  line-height: 1.55;
  word-break: break-word;
}
.mem-tl-tags {
  margin-top: 6px;
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}
.mem-tl-tag {
  font-size: 0.68rem;
  color: #8d7f86;
  background: #faf6f8;
  border-radius: 6px;
  padding: 1px 7px;
}
.mem-tl-empty {
  text-align: center;
  color: var(--kawaii-text-soft, #a08e96);
  padding: 60px 0;
}
@media (prefers-reduced-motion: reduce) {
  .mem-tl-group { animation: none; }
  .mem-tl-item:hover { transform: none; }
}
</style>
