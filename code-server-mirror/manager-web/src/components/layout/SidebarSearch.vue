<template>
  <div class="sidebar-search">
    <el-input
      v-model="search"
      :placeholder="$t('header.searchPlaceholder')"
      class="sidebar-search__input"
      @keyup.enter.native="handleSearch"
      @clear="handleSearchReset"
      clearable
      ref="searchInput"
      @focus="showSearchHistory"
      @blur="hideSearchHistory"
    >
      <i slot="suffix" class="el-icon-search sidebar-search__icon" @click="handleSearch"></i>
    </el-input>

    <!-- 搜索历史下拉框（原 home.vue 逻辑完整迁移） -->
    <div v-if="showHistory && searchHistory.length > 0" class="sidebar-search__dropdown">
      <div class="sidebar-search__history-header">
        <span>{{ $t('header.searchHistory') }}</span>
        <el-button type="text" size="small" class="sidebar-search__clear-btn" @mousedown.native.prevent="clearSearchHistory">
          {{ $t('header.clearHistory') }}
        </el-button>
      </div>
      <div class="sidebar-search__history-list">
        <div
          v-for="(item, index) in searchHistory"
          :key="index"
          class="sidebar-search__history-item"
          @click.stop="selectSearchHistory(item)"
        >
          <span class="sidebar-search__history-text">{{ item }}</span>
          <i class="el-icon-close sidebar-search__history-remove" @click.stop="removeSearchHistory(index)"></i>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import Api from '@/apis/api';

// 搜索历史存储键（与 home.vue 现状保持一致，跨页共享同一份历史）
const SEARCH_HISTORY_KEY = 'agentSearchHistory';
const MAX_HISTORY_COUNT = 10;

export default {
  name: 'SidebarSearch',
  data() {
    return {
      search: '',
      showHistory: false,
      searchHistory: []
    };
  },
  mounted() {
    this.loadSearchHistory();
  },
  methods: {
    // 处理搜索（原 home.vue handleSearch：MAC 正则 → searchAgent API）
    handleSearch() {
      const searchValue = this.search.trim();

      // 如果搜索内容为空，触发重置事件
      if (!searchValue) {
        this.handleSearchReset();
        return;
      }

      // 保存搜索历史
      this.saveSearchHistory(searchValue);

      // 搜索完成后让输入框失去焦点，从而触发 blur 事件隐藏搜索历史
      if (this.$refs.searchInput) {
        this.$refs.searchInput.blur();
      }

      // 检测MAC地址格式：包含4个冒号（原文注释如此，实际为5个冒号格式校验）
      const isMac = /^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$/.test(searchValue);
      const searchType = isMac ? 'mac' : 'name';
      Api.agent.searchAgent(searchValue, searchType, () => {
        // 结果列表仍在 home 页网格中呈现（#5 批次将做深度联动）
      }, (error) => {
        console.error('搜索智能体失败:', error);
        this.$message.error(this.$t('message.searchFailed'));
      });

      // 跳转到首页查看搜索结果
      if (this.$route.path !== '/home') {
        this.$router.push({ path: '/home', query: { keyword: searchValue, searchType } });
      } else {
        this.$eventBus.$emit('globalAgentSearch', { keyword: searchValue, searchType });
      }
    },

    // 重置搜索（通知 home 页恢复完整列表）
    handleSearchReset() {
      if (this.$route.path === '/home') {
        this.$eventBus.$emit('globalAgentSearchReset');
      }
    },

    // 显示搜索历史
    showSearchHistory() {
      this.showHistory = true;
    },

    // 隐藏搜索历史（延迟，以便点击事件能够执行）
    hideSearchHistory() {
      setTimeout(() => {
        this.showHistory = false;
      }, 200);
    },

    // 加载搜索历史
    loadSearchHistory() {
      try {
        const history = localStorage.getItem(SEARCH_HISTORY_KEY);
        if (history) {
          this.searchHistory = JSON.parse(history);
        }
      } catch (error) {
        console.error('加载搜索历史失败:', error);
        this.searchHistory = [];
      }
    },

    // 保存搜索历史
    saveSearchHistory(keyword) {
      if (!keyword || this.searchHistory.includes(keyword)) {
        return;
      }

      // 添加到历史记录开头
      this.searchHistory.unshift(keyword);

      // 限制历史记录数量
      if (this.searchHistory.length > MAX_HISTORY_COUNT) {
        this.searchHistory = this.searchHistory.slice(0, MAX_HISTORY_COUNT);
      }

      // 保存到 localStorage
      try {
        localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(this.searchHistory));
      } catch (error) {
        console.error('保存搜索历史失败:', error);
      }
    },

    // 选择搜索历史项
    selectSearchHistory(keyword) {
      this.search = keyword;
      this.handleSearch();
    },

    // 移除单个搜索历史项
    removeSearchHistory(index) {
      this.searchHistory.splice(index, 1);
      try {
        localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(this.searchHistory));
      } catch (error) {
        console.error('更新搜索历史失败:', error);
      }
    },

    // 清空所有搜索历史
    clearSearchHistory() {
      this.searchHistory = [];
      try {
        localStorage.removeItem(SEARCH_HISTORY_KEY);
      } catch (error) {
        console.error('清空搜索历史失败:', error);
      }
    }
  }
};
</script>

<style lang="scss" scoped>
// ============================================================
// 全局设备搜索（顶栏版）：含搜索历史 localStorage 逻辑
// 迁移自 home.vue（功能不丢）+ HeaderBar 搜索能力
// ============================================================
.sidebar-search {
  position: relative;
  width: 280px;
  text-align: left;
}

.sidebar-search__input ::v-deep .el-input__inner {
  border-radius: var(--kawaii-radius-full);
  background: var(--kawaii-surface-2);
  border-color: var(--kawaii-border);
  height: 34px;
  line-height: 34px;
}

.sidebar-search__icon {
  cursor: pointer;
  color: var(--kawaii-text-secondary);

  &:hover {
    color: var(--kawaii-primary);
  }
}

.sidebar-search__dropdown {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  width: 280px;
  background: var(--kawaii-surface);
  border: 1px solid var(--kawaii-border);
  border-radius: var(--kawaii-radius);
  box-shadow: var(--kawaii-shadow-md);
  padding: var(--kawaii-space-3);
  z-index: 100;
  box-sizing: border-box;
}

.sidebar-search__history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: var(--kawaii-font-size-sm);
  color: var(--kawaii-text-secondary);
  margin-bottom: var(--kawaii-space-2);
}

.sidebar-search__clear-btn {
  padding: 0;
}

.sidebar-search__history-list {
  max-height: 240px;
  overflow-y: auto;
}

.sidebar-search__history-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--kawaii-space-2);
  border-radius: var(--kawaii-radius-sm);
  font-size: var(--kawaii-font-size-sm);
  color: var(--kawaii-text);
  cursor: pointer;
  transition: background var(--kawaii-duration-fast) var(--kawaii-ease-out);

  &:hover {
    background: var(--kawaii-surface-2);
  }
}

.sidebar-search__history-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-search__history-remove {
  color: var(--kawaii-text-placeholder);
  flex-shrink: 0;

  &:hover {
    color: var(--kawaii-danger-hover);
  }
}

@media (max-width: 1023px) {
  .sidebar-search {
    width: 180px;
  }
}
</style>
