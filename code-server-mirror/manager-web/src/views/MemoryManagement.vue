<template>
  <div class="welcome">
    <div class="main-wrapper">
      <el-card class="main-card" shadow="never">
        <div class="operation-header">
          <h2 class="page-title">{{ $t('memoryManagement.title') }}</h2>
          <div class="header-right-area">
            <div class="agent-selector">
              <span class="agent-label">{{ $t('memoryManagement.agentLabel') }}</span>
              <el-select
                v-model="selectedAgentId"
                filterable
                size="small"
                class="agent-select"
                :loading="agentsLoading"
                :placeholder="$t('memoryManagement.agentPlaceholder')"
                :no-data-text="$t('memoryManagement.noAgents')"
                @change="handleAgentChange"
              >
                <el-option
                  v-for="agent in agents"
                  :key="agent.agentId"
                  :label="agent.agentName + '（' + agent.factCount + ' ' + $t('memoryManagement.entriesUnit') + '）'"
                  :value="agent.agentId"
                />
              </el-select>
              <span v-if="currentAgent" class="engine-badge" :class="engineBadgeClass">{{ engineBadgeText }}</span>
            </div>
            <div class="view-switch">
              <CustomButton size="small" :type="viewMode === 'list' ? 'confirm' : 'default'" @click="viewMode = 'list'">
                {{ $t('memoryManagement.viewList') }}
              </CustomButton>
              <CustomButton size="small" :type="viewMode === 'timeline' ? 'confirm' : 'default'" @click="switchView('timeline')">
                {{ $t('memoryManagement.viewTimeline') }}
              </CustomButton>
              <CustomButton size="small" :type="viewMode === 'graph' ? 'confirm' : 'default'" @click="switchView('graph')">
                {{ $t('memoryManagement.viewGraph') }}
              </CustomButton>
            </div>
          </div>
        </div>

        <!-- C 线：引擎参数面板（Agent 选择器下方，默认收起） -->
        <div v-if="currentAgent" class="engine-params-slot">
          <MemoryEngineParams
            :agent="currentAgent"
            @go-model-config="goModelConfig"
            @saved="handleEngineParamsSaved"
          />
        </div>

        <div class="content-area" v-loading="loading" :element-loading-text="$t('memoryManagement.loading')">
          <!-- 无 Agent -->
          <div v-if="!agentsLoading && agents.length === 0" class="engine-guide">
            <i class="el-icon-data-analysis guide-icon"></i>
            <p class="guide-title">{{ $t('memoryManagement.noAgents') }}</p>
          </div>

          <!-- 引擎引导页：mem_local_short -->
          <div v-else-if="currentAgent && engine === 'mem_local_short'" class="engine-guide">
            <i class="el-icon-box guide-icon"></i>
            <p class="guide-title">{{ $t('memoryManagement.localShortTitle') }}</p>
            <p class="guide-desc">{{ $t('memoryManagement.localShortDesc') }}</p>
            <CustomButton type="confirm" icon="el-icon-setting" @click="goModelConfig">
              {{ $t('memoryManagement.goModelConfig') }}
            </CustomButton>
          </div>

          <!-- 引擎引导页：nomem / mem_report_only / 未配置引擎 -->
          <div v-else-if="currentAgent && !engineManageable" class="engine-guide">
            <i class="el-icon-warning-outline guide-icon"></i>
            <p class="guide-title">{{ $t('memoryManagement.engineNotManageable') }}</p>
            <CustomButton type="confirm" icon="el-icon-setting" @click="goModelConfig">
              {{ $t('memoryManagement.goModelConfig') }}
            </CustomButton>
          </div>

          <!-- 引擎降级引导页：mem0 未配置（available=false）或 facts 接口降级文案 -->
          <div v-else-if="currentAgent && (mem0Unavailable || engineNotice)" class="engine-guide">
            <i class="el-icon-warning guide-icon warning"></i>
            <p class="guide-title">{{ engineBadgeText }}</p>
            <p class="guide-desc">{{ engineNotice || $t('memoryManagement.mem0UnavailableDesc') }}</p>
            <CustomButton type="confirm" icon="el-icon-setting" @click="goModelConfig">
              {{ $t('memoryManagement.goModelConfig') }}
            </CustomButton>
          </div>

          <!-- 时间轴视图 -->
          <div v-else-if="viewMode === 'timeline'" class="viz-view">
            <MemoryTimeline :facts="factList" :loading="loading" @fact-click="openFactDetail" />
          </div>

          <!-- 实体关系图谱视图 -->
          <div v-else-if="viewMode === 'graph'" class="viz-view">
            <MemoryGraph :facts="factList" :loading="loading" />
          </div>

          <!-- 列表视图 -->
          <template v-else>
            <div class="filter-bar">
              <el-input
                v-model="filters.keyword"
                class="filter-keyword"
                clearable
                maxlength="200"
                :placeholder="$t('memoryManagement.keywordPlaceholder')"
                prefix-icon="el-icon-search"
                @keyup.enter.native="handleSearch"
                @clear="handleSearch"
              />
              <el-select v-model="filters.category" size="small" class="filter-item" :placeholder="$t('memoryManagement.categoryAll')" @change="handleSearch">
                <el-option :label="$t('memoryManagement.categoryAll')" value="" />
                <el-option :label="$t('memoryManagement.categoryPreference')" value="preference" />
                <el-option :label="$t('memoryManagement.categoryProfile')" value="profile" />
                <el-option :label="$t('memoryManagement.categoryHabit')" value="habit" />
                <el-option :label="$t('memoryManagement.categoryEvent')" value="event" />
                <el-option :label="$t('memoryManagement.categoryGeneral')" value="general" />
              </el-select>
              <el-select v-if="isHolographic" v-model="filters.status" size="small" class="filter-item" :placeholder="$t('memoryManagement.statusAll')" @change="handleSearch">
                <el-option :label="$t('memoryManagement.statusAll')" value="" />
                <el-option :label="$t('memoryManagement.statusActive')" value="active" />
                <el-option :label="$t('memoryManagement.statusRejected')" value="rejected" />
              </el-select>
              <div v-if="isHolographic" class="trust-filter">
                <span class="trust-filter-label">{{ $t('memoryManagement.trustRange') }}</span>
                <el-slider
                  v-model="filters.trustRange"
                  range
                  :min="0"
                  :max="1"
                  :step="0.05"
                  class="trust-slider"
                  :format-tooltip="formatTrustTooltip"
                  @change="handleSearch"
                />
                <span class="trust-filter-value">{{ filters.trustRange[0].toFixed(2) }} - {{ filters.trustRange[1].toFixed(2) }}</span>
              </div>
              <el-date-picker
                v-model="filters.dateRange"
                type="daterange"
                size="small"
                class="filter-daterange"
                value-format="yyyy-MM-dd"
                range-separator="-"
                :start-placeholder="$t('memoryManagement.dateStart')"
                :end-placeholder="$t('memoryManagement.dateEnd')"
                @change="handleSearch"
              />
              <el-select v-model="sortMode" size="small" class="filter-item" @change="handleSearch">
                <el-option :label="$t('memoryManagement.sortCreatedDesc')" value="created-desc" />
                <el-option :label="$t('memoryManagement.sortTrustDesc')" value="trust-desc" />
                <el-option :label="$t('memoryManagement.sortTrustAsc')" value="trust-asc" />
              </el-select>
              <CustomButton size="small" icon="el-icon-search" @click="handleSearch">
                {{ $t('common.search') }}
              </CustomButton>
              <CustomButton size="small" icon="el-icon-refresh" @click="handleReset">
                {{ $t('memoryManagement.reset') }}
              </CustomButton>
              <div class="filter-bar-right">
                <CustomButton v-if="isHolographic" type="confirm" size="small" icon="el-icon-plus" @click="showAddDrawer">
                  {{ $t('memoryManagement.addFact') }}
                </CustomButton>
              </div>
            </div>

            <div class="table-container">
              <el-table
                :data="factList"
                style="width: 100%"
                height="100%"
                v-loading="loading"
                :element-loading-text="$t('memoryManagement.loading')"
              >
                <el-table-column :label="$t('memoryManagement.content')" min-width="260" align="left">
                  <template slot-scope="scope">
                    <el-tooltip
                      :content="scope.row.content"
                      placement="top"
                      effect="dark"
                      :disabled="!scope.row.content || scope.row.content.length <= 40"
                    >
                      <div class="fact-content" v-html="highlightContent(scope.row)"></div>
                    </el-tooltip>
                  </template>
                </el-table-column>
                <el-table-column :label="$t('memoryManagement.category')" width="100" align="center">
                  <template slot-scope="scope">
                    <el-tag size="mini" :type="categoryTagType(scope.row.category)">
                      {{ categoryLabel(scope.row.category) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column :label="$t('memoryManagement.tags')" min-width="140" align="center">
                  <template slot-scope="scope">
                    <template v-if="parseTags(scope.row.tags).length > 0">
                      <el-tag
                        v-for="tag in parseTags(scope.row.tags).slice(0, 3)"
                        :key="tag"
                        size="mini"
                        type="info"
                        class="fact-tag"
                      >
                        {{ tag }}
                      </el-tag>
                      <span v-if="parseTags(scope.row.tags).length > 3" class="tag-more">+{{ parseTags(scope.row.tags).length - 3 }}</span>
                    </template>
                    <span v-else>—</span>
                  </template>
                </el-table-column>
                <el-table-column v-if="isHolographic" :label="$t('memoryManagement.trustScore')" width="150" align="center">
                  <template slot-scope="scope">
                    <div class="trust-cell">
                      <el-progress
                        :percentage="trustPercent(scope.row.trustScore)"
                        :color="trustColor(scope.row.trustScore)"
                        :stroke-width="8"
                        :show-text="false"
                        class="trust-progress"
                      />
                      <span class="trust-value">{{ scope.row.trustScore.toFixed(2) }}</span>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column :label="$t('memoryManagement.sourceDevice')" min-width="110" align="center">
                  <template slot-scope="scope">
                    <el-tooltip
                      :content="scope.row.sessionId ? ($t('memoryManagement.sourceDevice') + ': ' + scope.row.sessionId) : $t('memoryManagement.noSession')"
                      placement="top"
                      effect="dark"
                    >
                      <span>{{ scope.row.deviceId || '—' }}</span>
                    </el-tooltip>
                  </template>
                </el-table-column>
                <el-table-column v-if="isHolographic" :label="$t('memoryManagement.retrievalCount')" width="90" align="center">
                  <template slot-scope="scope">{{ scope.row.retrievalCount }}</template>
                </el-table-column>
                <el-table-column v-if="isHolographic" :label="$t('memoryManagement.helpfulCount')" width="90" align="center">
                  <template slot-scope="scope">{{ scope.row.helpfulCount }}</template>
                </el-table-column>
                <el-table-column :label="$t('memoryManagement.createdAt')" width="150" align="center">
                  <template slot-scope="scope">{{ formatDateTime(scope.row.createdAt) }}</template>
                </el-table-column>
                <el-table-column v-if="isHolographic" :label="$t('memoryManagement.status')" width="100" align="center">
                  <template slot-scope="scope">
                    <el-tag size="mini" :type="scope.row.status === 'rejected' ? 'danger' : 'success'">
                      {{ scope.row.status === 'rejected' ? $t('memoryManagement.statusRejected') : $t('memoryManagement.statusActive') }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column :label="$t('memoryManagement.operations')" width="200" align="center" fixed="right">
                  <template slot-scope="scope">
                    <el-button v-if="isHolographic" type="text" size="mini" @click="showEditDrawer(scope.row)">
                      {{ $t('common.edit') }}
                    </el-button>
                    <el-button type="text" size="mini" class="delete-btn" @click="handleDelete(scope.row)">
                      {{ $t('common.delete') }}
                    </el-button>
                    <el-tooltip v-if="isHolographic" :content="$t('memoryManagement.helpful')" placement="top">
                      <el-button type="text" size="mini" class="feedback-btn" @click="handleFeedback(scope.row, true)">👍</el-button>
                    </el-tooltip>
                    <el-tooltip v-if="isHolographic" :content="$t('memoryManagement.notHelpful')" placement="top">
                      <el-button type="text" size="mini" class="feedback-btn" @click="handleFeedback(scope.row, false)">👎</el-button>
                    </el-tooltip>
                  </template>
                </el-table-column>
                <template slot="empty">
                  <el-empty :description="$t('memoryManagement.noData')"></el-empty>
                </template>
              </el-table>
            </div>

            <div class="table-footer">
              <CustomPagination
                :total="total"
                :current-page="currentPage"
                :page-size="pageSize"
                :page-size-options="[10, 20, 50, 100]"
                @size-change="handlePageSizeChange"
                @page-change="handlePageChange"
              />
            </div>
          </template>
        </div>
      </el-card>
    </div>

    <!-- 新增/编辑抽屉 -->
    <el-drawer
      :visible.sync="drawerVisible"
      direction="rtl"
      size="480px"
      :wrapper-closable="false"
      :with-header="false"
      custom-class="memory-drawer"
    >
      <div class="drawer-container">
        <div class="drawer-header">
          <h3 class="drawer-title">{{ drawerMode === 'add' ? $t('memoryManagement.addTitle') : $t('memoryManagement.editTitle') }}</h3>
          <button class="drawer-close-btn" @click="drawerVisible = false">×</button>
        </div>
        <div class="drawer-body">
          <el-form ref="factForm" :model="factForm" :rules="formRules" label-position="top">
            <el-form-item :label="$t('memoryManagement.contentLabel')" prop="content" :error="contentError">
              <el-input
                v-model="factForm.content"
                type="textarea"
                :rows="4"
                maxlength="500"
                show-word-limit
                :placeholder="$t('memoryManagement.contentPlaceholder')"
                @input="contentError = ''"
              />
            </el-form-item>
            <el-form-item :label="$t('memoryManagement.categoryLabel')" prop="category">
              <el-select v-model="factForm.category" style="width: 100%">
                <el-option :label="$t('memoryManagement.categoryPreference')" value="preference" />
                <el-option :label="$t('memoryManagement.categoryProfile')" value="profile" />
                <el-option :label="$t('memoryManagement.categoryHabit')" value="habit" />
                <el-option :label="$t('memoryManagement.categoryEvent')" value="event" />
                <el-option :label="$t('memoryManagement.categoryGeneral')" value="general" />
              </el-select>
            </el-form-item>
            <el-form-item :label="$t('memoryManagement.tagsLabel')" prop="tags">
              <el-input v-model="factForm.tags" :placeholder="$t('memoryManagement.tagsPlaceholder')" />
            </el-form-item>
            <el-form-item :label="$t('memoryManagement.trustLabel')" prop="trustScore">
              <div class="trust-input-row">
                <el-input-number
                  v-model="factForm.trustScore"
                  :min="0"
                  :max="1"
                  :step="0.05"
                  :precision="2"
                  :controls="true"
                  style="width: 180px"
                />
                <span class="trust-hint">0 - 1</span>
              </div>
            </el-form-item>
          </el-form>
        </div>
        <div class="drawer-footer">
          <CustomButton @click="drawerVisible = false">{{ $t('memoryManagement.cancel') }}</CustomButton>
          <CustomButton type="confirm" :loading="saving" @click="handleSave">
            {{ $t('memoryManagement.save') }}
          </CustomButton>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script>
import Api from '@/apis/api';
import CustomButton from '@/components/CustomButton.vue';
import MemoryGraph from '@/components/MemoryGraph.vue';
import MemoryTimeline from '@/components/MemoryTimeline.vue';
import CustomPagination from '@/components/CustomPagination.vue';
import MemoryEngineParams from '@/components/memory/MemoryEngineParams.vue';

/**
 * 从对象中按候选 key 顺序取第一个非空值（兼容 snake_case / camelCase 两种返回格式）
 */
function pickFirst(obj, keys, fallback) {
  if (!obj) return fallback;
  for (let i = 0; i < keys.length; i++) {
    const value = obj[keys[i]];
    if (value !== undefined && value !== null) return value;
  }
  return fallback;
}

export default {
  name: 'MemoryManagement',
  components: {
    CustomButton,
    CustomPagination,
    MemoryEngineParams,
    MemoryGraph,
    MemoryTimeline
  },
  data() {
    return {
      viewMode: 'list',
      vizLoaded: false,
      agents: [],
      agentsLoading: false,
      selectedAgentId: '',
      loading: false,
      // 引擎降级文案（mem0 未配置 / 服务不可用等，来自 facts 接口 code=500 的 msg）
      engineNotice: '',
      filters: {
        keyword: '',
        category: '',
        status: '',
        trustRange: [0, 1],
        dateRange: null
      },
      appliedKeyword: '',
      sortMode: 'created-desc',
      factList: [],
      total: 0,
      currentPage: 1,
      pageSize: 20,
      drawerVisible: false,
      drawerMode: 'add',
      editingFactId: null,
      saving: false,
      contentError: '',
      factForm: {
        content: '',
        category: 'general',
        tags: '',
        trustScore: 0.5
      },
      formRules: {
        content: [
          { required: true, message: this.$t('memoryManagement.contentRequired'), trigger: 'blur' }
        ]
      }
    };
  },
  computed: {
    currentAgent() {
      return this.agents.find((agent) => agent.agentId === this.selectedAgentId) || null;
    },
    engine() {
      return this.currentAgent ? String(this.currentAgent.engine || '') : '';
    },
    isHolographic() {
      // mem_hybrid 长期层与 holographic 同库同锁，条目管理能力一致
      return this.engine === 'mem_holographic' || this.engine === 'mem_hybrid';
    },
    isMem0() {
      return this.engine === 'mem0ai' || this.engine === 'mem0';
    },
    engineManageable() {
      return this.isHolographic || this.isMem0;
    },
    // mem0 是否已降级：available 字段（agents 接口）优先，engineNotice（facts 降级文案）兜底
    mem0Unavailable() {
      if (!this.isMem0) return false;
      return this.currentAgent.available === false || !!this.engineNotice;
    },
    engineBadgeClass() {
      if (this.isHolographic) return 'engine-holographic';
      if (this.isMem0) return this.mem0Unavailable ? 'engine-disabled' : 'engine-mem0';
      if (this.engine === 'mem_local_short') return 'engine-local-short';
      return 'engine-none';
    },
    engineBadgeText() {
      if (this.isHolographic) return this.$t('memoryManagement.engineHolographic');
      if (this.isMem0) {
        return this.mem0Unavailable
          ? this.$t('memoryManagement.engineMem0Unconfigured')
          : this.$t('memoryManagement.engineMem0');
      }
      if (this.engine === 'mem_local_short') return this.$t('memoryManagement.engineLocalShort');
      return this.$t('memoryManagement.engineNone');
    }
  },
  created() {
    this.fetchAgents();
  },
  methods: {
    /* ========== 数据加载 ========== */
    fetchAgents() {
      this.agentsLoading = true;
      Api.memory.getMemoryAgents(
        (res) => {
          this.agentsLoading = false;
          if (res.data && res.data.code === 0) {
            const list = res.data.data || [];
            this.agents = (Array.isArray(list) ? list : []).map((raw) => ({
              agentId: pickFirst(raw, ['agent_id', 'agentId', 'id'], ''),
              agentName: pickFirst(raw, ['agent_name', 'agentName', 'name'], ''),
              engine: pickFirst(raw, ['engine', 'engine_type', 'engineType', 'memoryType'], ''),
              // C 线：记忆引擎参数面板数据源（J-6 透传字段，后端未就绪时为空 → 面板降级提示）
              memModelId: pickFirst(raw, ['mem_model_id', 'memModelId'], ''),
              // mem0 未配置 API Key 时后端返回 false（J-9 脱敏标记）；字段缺失视为 true
              available: pickFirst(raw, ['available'], true) !== false,
              factCount: Number(pickFirst(raw, ['fact_count', 'factCount'], 0)) || 0,
              pendingCount: Number(pickFirst(raw, ['pending_count', 'pendingCount'], 0)) || 0
            })).filter((agent) => agent.agentId);
            if (this.agents.length > 0 && !this.selectedAgentId) {
              const withData = this.agents.find((agent) => agent.factCount > 0);
              this.selectedAgentId = (withData || this.agents[0]).agentId;
              this.fetchFacts();
            }
          } else {
            this.$message.error((res.data && res.data.msg) || this.$t('memoryManagement.loadAgentsFailed'));
          }
        },
        () => {
          this.agentsLoading = false;
          this.$message.error(this.$t('memoryManagement.loadAgentsFailed'));
        }
      );
    },

    normalizeFact(raw) {
      return {
        factId: pickFirst(raw, ['fact_id', 'factId'], null),
        content: pickFirst(raw, ['content'], ''),
        category: pickFirst(raw, ['category'], 'general'),
        tags: pickFirst(raw, ['tags'], ''),
        trustScore: Number(pickFirst(raw, ['trust_score', 'trustScore'], 0)) || 0,
        status: pickFirst(raw, ['status'], 'active'),
        deviceId: pickFirst(raw, ['device_id', 'deviceId'], ''),
        sessionId: pickFirst(raw, ['session_id', 'sessionId'], ''),
        retrievalCount: Number(pickFirst(raw, ['retrieval_count', 'retrievalCount'], 0)) || 0,
        helpfulCount: Number(pickFirst(raw, ['helpful_count', 'helpfulCount'], 0)) || 0,
        createdAt: pickFirst(raw, ['created_at', 'createdAt'], ''),
        updatedAt: pickFirst(raw, ['updated_time', 'updated_at', 'updatedAt'], ''),
        matchedTerms: (function (value) {
          return Array.isArray(value) ? value : [];
        })(pickFirst(raw, ['matched_terms', 'matchedTerms'], []))
      };
    },

    /**
     * 引擎降级文案识别：非 holographic 引擎调 facts 时后端返回 code=500 + 中文 msg。
     * 命中降级文案时存入 engineNotice，页面渲染引导页而非裸 toast。
     */
    isEngineNotice(msg) {
      return !!(msg && /压缩档案式|暂不支持|未配置 API Key|记忆服务不可用|功能建设中/.test(msg));
    },

    fetchFacts() {
      if (!this.selectedAgentId) return;
      // available=false（mem0 未配置）时无需发请求，直接显示引导页
      if (this.currentAgent && this.currentAgent.available === false) {
        this.factList = [];
        this.total = 0;
        return;
      }
      this.loading = true;
      this.engineNotice = '';
      this.appliedKeyword = (this.filters.keyword || '').trim();
      const sortParts = this.sortMode.split('-');
      const params = {
        agent_id: this.selectedAgentId,
        page: this.currentPage,
        size: this.pageSize,
        keyword: this.appliedKeyword || undefined,
        category: this.filters.category || undefined,
        sort_by: sortParts[0],
        order: sortParts[1]
      };
      if (this.isHolographic) {
        params.status = this.filters.status || undefined;
        params.trust_min = this.filters.trustRange[0];
        params.trust_max = this.filters.trustRange[1];
      }
      if (this.filters.dateRange && this.filters.dateRange.length === 2) {
        params.start = this.filters.dateRange[0];
        params.end = this.filters.dateRange[1];
      }
      Api.memory.getFactList(
        params,
        (res) => {
          this.loading = false;
          if (res.data && res.data.code === 0) {
            const payload = res.data.data || {};
            const list = payload.list || payload.items || [];
            this.factList = (Array.isArray(list) ? list : []).map(this.normalizeFact);
            this.total = payload.total !== undefined && payload.total !== null ? Number(payload.total) : this.factList.length;
          } else {
            const msg = (res.data && res.data.msg) || '';
            if (this.isEngineNotice(msg)) {
              // 引擎降级：渲染引导页（含"前往模型配置"入口）
              this.engineNotice = msg;
            } else {
              this.$message.error(msg || this.$t('memoryManagement.loadFailed'));
            }
            this.factList = [];
            this.total = 0;
          }
        },
        () => {
          this.loading = false;
          this.$message.error(this.$t('memoryManagement.loadFailed'));
          this.factList = [];
          this.total = 0;
        }
      );
    },

    /* ========== 视图切换（图谱/时间轴需要全量数据，一次拉 200 条） ========== */
    switchView(mode) {
      this.viewMode = mode;
      if (mode !== 'list' && !this.vizLoaded) {
        this.loadVizData();
      }
    },
    loadVizData() {
      this.loading = true;
      const params = {
        agent_id: this.currentAgent,
        page: 1,
        size: 200,
        sort_by: 'created',
        order: 'desc'
      };
      Api.memory.getFactList(
        params,
        (res) => {
          this.loading = false;
          if (res.data && res.data.code === 0) {
            const payload = res.data.data || {};
            const list = payload.list || payload.items || [];
            const facts = (Array.isArray(list) ? list : []).map(this.normalizeFact);
            this.factList = facts;
            this.total = payload.total !== undefined ? Number(payload.total) : facts.length;
            this.vizLoaded = true;
          } else {
            this.$message.error((res.data && res.data.msg) || this.$t('memoryManagement.loadFailed'));
          }
        },
        () => {
          this.loading = false;
          this.$message.error(this.$t('memoryManagement.loadFailed'));
        }
      );
    },

    /* ========== 交互 ========== */
    handleAgentChange() {
      this.vizLoaded = false;
      if (this.viewMode !== 'list') this.loadVizData();
      this.currentPage = 1;
      this.factList = [];
      this.total = 0;
      this.engineNotice = '';
      if (this.currentAgent && this.engineManageable) {
        this.fetchFacts();
      }
    },

    handleSearch() {
      this.vizLoaded = false;
      this.currentPage = 1;
      this.fetchFacts();
    },

    handleReset() {
      this.filters = {
        keyword: '',
        category: '',
        status: '',
        trustRange: [0, 1],
        dateRange: null
      };
      this.sortMode = 'created-desc';
      this.currentPage = 1;
      this.fetchFacts();
    },

    handlePageSizeChange(val) {
      this.pageSize = val;
      this.currentPage = 1;
      this.fetchFacts();
    },

    handlePageChange(page) {
      if (page !== this.currentPage) {
        this.currentPage = page;
        this.fetchFacts();
      }
    },

    goModelConfig() {
      this.$router.push('/model-config');
    },

    /** 引擎参数保存成功回调（面板自身已提示，此处仅触发列表刷新以同步信任分展示） */
    handleEngineParamsSaved() {
      if (this.currentAgent && this.engineManageable) {
        this.fetchFacts();
      }
    },

    /* ========== 新增 / 编辑 ========== */
    showAddDrawer() {
      if (!this.selectedAgentId) {
        this.$message.warning(this.$t('memoryManagement.selectAgentFirst'));
        return;
      }
      this.drawerMode = 'add';
      this.editingFactId = null;
      this.contentError = '';
      this.factForm = {
        content: '',
        category: 'general',
        tags: '',
        trustScore: 0.5
      };
      this.drawerVisible = true;
      this.$nextTick(() => {
        if (this.$refs.factForm) this.$refs.factForm.clearValidate();
      });
    },

    showEditDrawer(row) {
      this.drawerMode = 'edit';
      this.editingFactId = row.factId;
      this.contentError = '';
      this.factForm = {
        content: row.content,
        category: row.category || 'general',
        tags: row.tags || '',
        trustScore: typeof row.trustScore === 'number' ? row.trustScore : 0.5
      };
      this.drawerVisible = true;
      this.$nextTick(() => {
        if (this.$refs.factForm) this.$refs.factForm.clearValidate();
      });
    },

    handleSave() {
      if (!this.selectedAgentId || this.saving) return;
      this.$refs.factForm.validate((valid) => {
        if (!valid) return;
        const content = (this.factForm.content || '').trim();
        if (!content) {
          this.contentError = this.$t('memoryManagement.contentRequired');
          return;
        }
        this.saving = true;
        const payload = {
          agent_id: this.selectedAgentId,
          content: content,
          category: this.factForm.category || 'general',
          tags: (this.factForm.tags || '').trim(),
          trust_score: this.factForm.trustScore
        };
        const handleSuccess = (messageKey) => {
          this.saving = false;
          this.drawerVisible = false;
          this.$message.success(this.$t(messageKey));
          this.fetchFacts();
        };
        const handleError = (err, defaultKey) => {
          this.saving = false;
          const msg = (err && err.data && err.data.msg) || '';
          if (msg && /已存在|重复|exist|duplicate/i.test(msg)) {
            this.contentError = this.$t('memoryManagement.contentDuplicate');
          } else {
            this.$message.error(msg || this.$t(defaultKey));
          }
        };
        if (this.drawerMode === 'add') {
          Api.memory.createFact(
            payload,
            (res) => {
              if (res.data && res.data.code === 0) {
                handleSuccess('memoryManagement.addSuccess');
              } else {
                this.saving = false;
                const msg = (res.data && res.data.msg) || '';
                if (msg && /已存在|重复|exist|duplicate/i.test(msg)) {
                  this.contentError = this.$t('memoryManagement.contentDuplicate');
                } else {
                  this.$message.error(msg || this.$t('memoryManagement.addFailed'));
                }
              }
            },
            (err) => handleError(err, 'memoryManagement.addFailed')
          );
        } else {
          Api.memory.updateFact(
            this.editingFactId,
            payload,
            (res) => {
              if (res.data && res.data.code === 0) {
                handleSuccess('memoryManagement.updateSuccess');
              } else {
                this.saving = false;
                const msg = (res.data && res.data.msg) || '';
                if (msg && /已存在|重复|exist|duplicate/i.test(msg)) {
                  this.contentError = this.$t('memoryManagement.contentDuplicate');
                } else {
                  this.$message.error(msg || this.$t('memoryManagement.updateFailed'));
                }
              }
            },
            (err) => handleError(err, 'memoryManagement.updateFailed')
          );
        }
      });
    },

    /* ========== 删除 / 反馈 ========== */
    handleDelete(row) {
      this.$confirm(
        this.$t('memoryManagement.confirmDelete'),
        this.$t('message.warning'),
        {
          confirmButtonText: this.$t('memoryManagement.confirm'),
          cancelButtonText: this.$t('memoryManagement.cancel'),
          type: 'warning'
        }
      ).then(() => {
        Api.memory.deleteFact(
          row.factId,
          this.selectedAgentId,
          (res) => {
            if (res.data && res.data.code === 0) {
              this.$message.success(this.$t('memoryManagement.deleteSuccess'));
              if (this.factList.length === 1 && this.currentPage > 1) {
                this.currentPage -= 1;
              }
              this.fetchFacts();
            } else {
              this.$message.error((res.data && res.data.msg) || this.$t('memoryManagement.deleteFailed'));
            }
          },
          (err) => {
            this.$message.error((err && err.data && err.data.msg) || this.$t('memoryManagement.deleteFailed'));
          }
        );
      }).catch(() => {});
    },

    handleFeedback(row, helpful) {
      Api.memory.sendFeedback(
        row.factId,
        this.selectedAgentId,
        helpful,
        (res) => {
          if (res.data && res.data.code === 0) {
            const newTrust = pickFirst(res.data.data || {}, ['new_trust', 'newTrust'], null);
            const tip = newTrust !== null && newTrust !== undefined
              ? this.$t('memoryManagement.trustFeedbackApplied', { score: Number(newTrust).toFixed(2) })
              : this.$t('memoryManagement.feedbackDone');
            this.$message.success(tip);
            this.fetchFacts();
          } else {
            this.$message.error((res.data && res.data.msg) || this.$t('memoryManagement.feedbackFailed'));
          }
        },
        (err) => {
          this.$message.error((err && err.data && err.data.msg) || this.$t('memoryManagement.feedbackFailed'));
        }
      );
    },

    /* ========== 展示辅助 ========== */
    escapeHtml(text) {
      return String(text === null || text === undefined ? '' : text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    },

    /**
     * 关键词高亮：先对原文做 HTML 转义，再对转义后的文本按 matched_terms（或关键词）
     * 包 <mark> 标签。按 HTML 实体分段替换，避免误伤实体内部字符，防 XSS。
     * 防御：term 超长（>200）丢弃；构造与执行（V8 惰性编译，replace 才真正编译）均在 try 内，
     * 任何正则异常都降级返回纯转义文本，绝不上抛白屏。
     */
    highlightContent(row) {
      const escaped = this.escapeHtml(row.content);
      let terms = (row.matchedTerms || []).map((term) => String(term || '').trim());
      if (!terms.length && this.appliedKeyword) {
        terms = [this.appliedKeyword];
      }
      terms = terms.filter((term) => term.length > 0 && term.length <= 200);
      const uniqueTerms = [];
      terms.forEach((term) => {
        if (uniqueTerms.indexOf(term) === -1) uniqueTerms.push(term);
      });
      if (!uniqueTerms.length) return escaped;
      const escapedTerms = uniqueTerms.map((term) => this.escapeHtml(term));
      const pattern = escapedTerms
        .map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
        .join('|');
      try {
        const regex = new RegExp('(' + pattern + ')', 'gi');
        const segments = escaped.split(/(&[a-zA-Z#0-9]+;)/g);
        return segments
          .map((segment) => (/^&[a-zA-Z#0-9]+;$/.test(segment) ? segment : segment.replace(regex, '<mark>$1</mark>')))
          .join('');
      } catch (e) {
        return escaped;
      }
    },

    categoryLabel(category) {
      const map = {
        preference: 'memoryManagement.categoryPreference',
        profile: 'memoryManagement.categoryProfile',
        habit: 'memoryManagement.categoryHabit',
        event: 'memoryManagement.categoryEvent',
        general: 'memoryManagement.categoryGeneral'
      };
      return this.$t(map[category] || 'memoryManagement.categoryGeneral');
    },

    categoryTagType(category) {
      const map = {
        preference: '',
        profile: 'success',
        habit: 'warning',
        event: 'danger',
        general: 'info'
      };
      return map[category] || 'info';
    },

    parseTags(tags) {
      if (!tags) return [];
      return String(tags)
        .split(',')
        .map((tag) => tag.trim())
        .filter((tag) => tag.length > 0);
    },

    trustPercent(trust) {
      const percent = Math.round((Number(trust) || 0) * 100);
      return Math.min(100, Math.max(0, percent));
    },

    trustColor(trust) {
      const value = Number(trust) || 0;
      if (value < 0.3) return '#f56c6c';
      if (value <= 0.7) return '#e6a23c';
      return '#67c23a';
    },

    formatTrustTooltip(val) {
      return Number(val).toFixed(2);
    },

    formatDateTime(value) {
      if (!value) return '—';
      const str = String(value);
      if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(str)) {
        return str.slice(0, 16);
      }
      const date = new Date(str);
      if (!isNaN(date.getTime())) {
        const pad = (num) => String(num).padStart(2, '0');
        return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate()) +
          ' ' + pad(date.getHours()) + ':' + pad(date.getMinutes());
      }
      return str;
    }
  }
};
</script>

<style lang="scss" scoped>
.welcome {
  min-height: 506px;
  display: flex;
  position: relative;
  flex-direction: column;
  overflow: hidden;
}

.main-wrapper {
  flex: 1;
  min-height: 0;
  padding: 20px 22px 0;
  position: relative;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}

.main-card {
  background: white;
  flex: 1;
  display: flex;
  flex-direction: column;
  border: none;
  border-radius: 15px;
  overflow: hidden;

  ::v-deep .el-card__body {
    padding: 0;
    display: flex;
    flex-direction: column;
    flex: 1;
    overflow: hidden;
  }
}

.operation-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  flex-shrink: 0;
  flex-wrap: wrap;
  gap: 10px;
}

.page-title {
  font-weight: 500;
  font-size: 24px;
  margin: 0;
}

.header-right-area {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-left: auto;
  flex-wrap: wrap;
}

.agent-selector {
  display: flex;
  align-items: center;
  gap: 10px;
}

.agent-label {
  font-size: 14px;
  color: #606266;
  font-weight: 500;
}

.agent-select {
  width: 260px;
}

.engine-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;

  &.engine-holographic {
    background: #f0f9eb;
    color: #67c23a;
    border: 1px solid #e1f3d8;
  }

  &.engine-mem0 {
    background: #ecf5ff;
    color: #409eff;
    border: 1px solid #d9ecff;
  }

  &.engine-disabled,
  &.engine-none {
    background: #f4f4f5;
    color: #909399;
    border: 1px solid #e9e9eb;
  }

  &.engine-local-short {
    background: #fdf6ec;
    color: #e6a23c;
    border: 1px solid #faecd8;
  }
}

.view-switch {
  display: flex;
  align-items: center;
  gap: 8px;
}

.disabled-switch-wrap {
  display: inline-flex;
}

.content-area {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0 20px 16px;
  overflow: hidden;
}

/* C 线：引擎参数面板槽位（与 content-area 左右内边距对齐） */
.engine-params-slot {
  padding: 0 20px;
  flex-shrink: 0;
}

/* ========== 引擎引导 ========== */
.engine-guide {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 20px;

  .guide-icon {
    font-size: 48px;
    color: #c0c4cc;

    &.warning {
      color: #e6a23c;
    }
  }

  .guide-title {
    font-size: 16px;
    font-weight: 500;
    color: #303133;
    margin: 8px 0 0;
  }

  .guide-desc {
    font-size: 14px;
    color: #909399;
    margin: 0 0 16px;
    text-align: center;
    max-width: 420px;
    line-height: 1.6;
  }
}

/* ========== 筛选区 ========== */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 12px 0;
  flex-shrink: 0;
}

.filter-keyword {
  width: 220px;
}

.filter-item {
  width: 140px;
}

.filter-daterange {
  width: 240px;
}

.trust-filter {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 4px;

  .trust-filter-label {
    font-size: 13px;
    color: #606266;
    white-space: nowrap;
  }

  .trust-slider {
    width: 130px;
  }

  .trust-filter-value {
    font-size: 12px;
    color: #909399;
    white-space: nowrap;
  }
}

.filter-bar-right {
  margin-left: auto;
}

/* ========== 表格 ========== */
.table-container {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.table-footer {
  display: flex;
  justify-content: center;
  padding: 12px 0 4px;
  flex-shrink: 0;
}

.fact-content {
  max-width: 100%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.6;

  ::v-deep mark {
    background: #ffd666;
    color: #303133;
    padding: 0 1px;
    border-radius: 2px;
    font-weight: 600;
  }
}

.fact-tag {
  margin-right: 4px;
}

.tag-more {
  font-size: 12px;
  color: #909399;
}

.trust-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: center;

  .trust-progress {
    width: 80px;
    flex-shrink: 0;
  }

  .trust-value {
    font-size: 12px;
    color: #606266;
  }
}

.feedback-btn {
  font-size: 14px;
  padding: 3px 4px;
}

:deep(.el-table .el-button--text) {
  color: #7079aa;
}

:deep(.el-table .el-button--text:hover) {
  color: #5a64b5;
}

:deep(.el-table .el-button--text.delete-btn:hover) {
  color: #f56c6c;
}

/* ========== 抽屉 ========== */
.drawer-container {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #ebeef5;
  flex-shrink: 0;
}

.drawer-title {
  margin: 0;
  font-size: 16px;
  font-weight: 500;
  color: #303133;
}

.drawer-close-btn {
  border: none;
  background: transparent;
  font-size: 20px;
  color: #909399;
  cursor: pointer;
  line-height: 1;
  padding: 4px;

  &:hover {
    color: #409eff;
  }
}

.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 12px 20px;
  border-top: 1px solid #ebeef5;
  flex-shrink: 0;
}

.trust-input-row {
  display: flex;
  align-items: center;
  gap: 12px;

  .trust-hint {
    font-size: 12px;
    color: #909399;
  }
}

/* ===== 可视化视图容器（图谱 / 时间轴） ===== */
.viz-view {
  animation: kawaii-fade-up 0.4s ease both;
}
@media (prefers-reduced-motion: reduce) {
  .viz-view { animation: none; }
}
</style>
