<template>
  <div class="memory-engine-params">
    <el-collapse v-model="activeNames" class="engine-params-collapse">
      <el-collapse-item name="engineParams">
        <template slot="title">
          <div class="collapse-title">
            <i class="el-icon-set-up collapse-title__icon"></i>
            <span class="collapse-title__text">{{ $t('memoryManagement.engineParams.title') }}</span>
            <span v-if="engineChipText" class="collapse-title__chip" :class="{ 'collapse-title__chip--active': isHolographic }">
              {{ engineChipText }}
            </span>
          </div>
        </template>

        <!-- 非 holographic 引擎：引导文案（参数仅 holographic 适用） -->
        <div v-if="!isHolographic" class="engine-params-guide">
          <i class="el-icon-info guide__icon"></i>
          <p class="guide__title">{{ $t('memoryManagement.engineParams.guideTitle') }}</p>
          <p class="guide__desc">{{ $t('memoryManagement.engineParams.guideDesc') }}</p>
          <CustomButton type="confirm" size="small" icon="el-icon-setting" @click="$emit('go-model-config')">
            {{ $t('memoryManagement.goModelConfig') }}
          </CustomButton>
        </div>

        <!-- memModelId 缺失降级提示（后端 J-6 未就绪时） -->
        <div v-else-if="!agent.memModelId" class="engine-params-guide">
          <i class="el-icon-warning guide__icon guide__icon--warn"></i>
          <p class="guide__title">{{ $t('memoryManagement.engineParams.noModelBinding') }}</p>
        </div>

        <!-- 无权限降级：引擎参数接口仅 superAdmin 可访问（HTTP 200 + code=403） -->
        <div v-else-if="permissionDenied" class="engine-params-guide">
          <i class="el-icon-lock guide__icon guide__icon--warn"></i>
          <p class="guide__title">{{ $t('memoryManagement.engineParams.permissionDenied') }}</p>
        </div>

        <!-- 加载失败 -->
        <div v-else-if="loadError" class="engine-params-guide">
          <i class="el-icon-warning guide__icon guide__icon--warn"></i>
          <p class="guide__desc">{{ $t('memoryManagement.engineParams.loadFailed') }}</p>
          <CustomButton type="confirm" size="small" icon="el-icon-refresh" @click="loadAll">
            {{ $t('memoryManagement.engineParams.retry') }}
          </CustomButton>
        </div>

        <!-- 加载中 -->
        <div v-else-if="loading" class="engine-params-loading" v-loading="true" :element-loading-text="$t('memoryManagement.loading')"></div>

        <!-- 参数表单 -->
        <template v-else-if="form">
          <div class="params-meta">
            <div class="params-meta__row">
              <span class="params-meta__label">{{ $t('memoryManagement.engineParams.scopeDefault') }}</span>
              <span class="params-meta__desc">{{ $t('memoryManagement.engineParams.scopeDesc') }}</span>
            </div>
            <div class="params-effect">
              <i class="el-icon-time params-effect__icon"></i>
              <span>{{ $t('memoryManagement.engineParams.effectNote') }}</span>
            </div>
          </div>

          <el-form class="params-form" label-position="top" size="small" @submit.native.prevent>
            <!-- db_dir：只读 + 复制按钮 -->
            <el-form-item v-if="fieldVisible('db_dir')">
              <template slot="label">
                <span class="field-label">{{ fieldLabel('db_dir') }}</span>
              </template>
              <div class="db-dir-row">
                <el-input :value="form.db_dir" readonly class="db-dir-input">
                  <template slot="prepend"><i class="el-icon-folder-open"></i></template>
                </el-input>
                <el-tooltip :content="$t('memoryManagement.engineParams.copy')" placement="top">
                  <el-button class="copy-btn" icon="el-icon-document-copy" size="small" @click="copyDbDir"></el-button>
                </el-tooltip>
              </div>
              <div class="field-hint">{{ $t('memoryManagement.engineParams.dbDirHint') }}</div>
            </el-form-item>

            <!-- auto_extract：开关 -->
            <el-form-item v-if="fieldVisible('auto_extract')">
              <template slot="label">
                <span class="field-label">{{ fieldLabel('auto_extract') }}</span>
              </template>
              <div class="switch-row">
                <el-switch
                  v-model="form.auto_extract"
                  active-color="var(--kawaii-primary)"
                  inactive-color="var(--kawaii-border-strong)"
                />
                <span class="field-hint">{{ $t('memoryManagement.engineParams.autoExtractHint') }}</span>
              </div>
            </el-form-item>

            <!-- default_trust：滑杆（步进 0.05）+ 数值 -->
            <el-form-item v-if="fieldVisible('default_trust')">
              <template slot="label">
                <span class="field-label">{{ fieldLabel('default_trust') }}</span>
              </template>
              <div class="slider-row">
                <el-slider
                  v-model="form.default_trust"
                  :min="0"
                  :max="1"
                  :step="0.05"
                  class="slider-control"
                  :format-tooltip="formatTrustTooltip"
                  @change="roundTrustField('default_trust')"
                />
                <span class="slider-value">{{ trustText(form.default_trust) }}</span>
              </div>
              <div class="field-hint">{{ $t('memoryManagement.engineParams.defaultTrustHint') }}</div>
            </el-form-item>

            <!-- min_trust_threshold：滑杆（步进 0.05）+ 数值 + 三色条 + 即时语义说明 -->
            <el-form-item v-if="fieldVisible('min_trust_threshold')">
              <template slot="label">
                <span class="field-label">{{ fieldLabel('min_trust_threshold') }}</span>
              </template>
              <div class="slider-row">
                <el-slider
                  v-model="form.min_trust_threshold"
                  :min="0"
                  :max="1"
                  :step="0.05"
                  class="slider-control"
                  :format-tooltip="formatTrustTooltip"
                  @change="roundTrustField('min_trust_threshold')"
                />
                <span class="slider-value">{{ trustText(form.min_trust_threshold) }}</span>
              </div>
              <div class="trust-scale" role="img" :aria-label="trustScaleAria">
                <div class="trust-scale__segment trust-scale__segment--low" :style="{ width: scaleLowWidth + '%' }"></div>
                <div class="trust-scale__segment trust-scale__segment--mid" :style="{ width: scaleMidWidth + '%' }"></div>
                <div class="trust-scale__segment trust-scale__segment--high" :style="{ width: scaleHighWidth + '%' }"></div>
              </div>
              <div class="trust-scale-legend">
                <span class="trust-scale-legend__item">{{ $t('memoryManagement.engineParams.scaleFiltered') }}</span>
                <span class="trust-scale-legend__item trust-scale-legend__item--high">{{ $t('memoryManagement.engineParams.scaleHigh') }}</span>
              </div>
              <div class="field-hint">{{ $t('memoryManagement.engineParams.minTrustThresholdHint') }}</div>
              <div class="field-hint field-hint--live">{{ thresholdHint }}</div>
            </el-form-item>

            <!-- temporal_decay_half_life：数字输入 + 关闭说明（高级项折叠） -->
            <el-collapse v-if="fieldVisible('temporal_decay_half_life')" v-model="advancedNames" class="advanced-collapse">
              <el-collapse-item name="advanced">
                <template slot="title">
                  <span class="advanced-title">{{ $t('memoryManagement.engineParams.advanced') }}</span>
                </template>
                <el-form-item>
                  <template slot="label">
                    <span class="field-label">{{ fieldLabel('temporal_decay_half_life') }}</span>
                  </template>
                  <div class="decay-row">
                    <el-input-number
                      v-model="form.temporal_decay_half_life"
                      :min="0"
                      :max="3650"
                      :step="1"
                      :precision="0"
                      controls-position="right"
                      class="decay-input"
                    />
                    <span class="decay-unit">{{ $t('memoryManagement.engineParams.decayUnit') }}</span>
                    <el-tag v-if="isDecayOff" size="mini" class="decay-tag">
                      {{ $t('memoryManagement.engineParams.decayOff') }}
                    </el-tag>
                  </div>
                  <div class="field-hint">{{ $t('memoryManagement.engineParams.decayHint') }}</div>
                  <div v-if="!isDecayOff" class="field-hint field-hint--live">
                    {{ $t('memoryManagement.engineParams.decayActive', { days: form.temporal_decay_half_life }) }}
                  </div>
                </el-form-item>
              </el-collapse-item>
            </el-collapse>

            <!-- provider 元数据中的扩展字段：按 type 通用映射控件 -->
            <el-form-item v-for="field in extraFields" :key="field.key">
              <template slot="label">
                <span class="field-label">{{ field.label }}</span>
              </template>
              <el-switch
                v-if="field.type === 'boolean'"
                v-model="form[field.key]"
                active-color="var(--kawaii-primary)"
                inactive-color="var(--kawaii-border-strong)"
              />
              <el-input-number
                v-else-if="field.type === 'number'"
                v-model="form[field.key]"
                :step="1"
                controls-position="right"
                class="decay-input"
              />
              <el-input
                v-else
                v-model="form[field.key]"
                :show-password="field.type === 'password'"
                :placeholder="field.label"
              />
            </el-form-item>
          </el-form>

          <div class="params-footer">
            <CustomButton size="small" :disabled="!dirty || saving" @click="revert">
              {{ $t('memoryManagement.engineParams.revert') }}
            </CustomButton>
            <CustomButton type="confirm" size="small" :loading="saving" :disabled="!dirty || permissionDenied" @click="handleSave">
              {{ $t('memoryManagement.engineParams.saveParams') }}
            </CustomButton>
          </div>
        </template>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script>
import Api from '@/apis/api';
import CustomButton from '@/components/CustomButton.vue';

/**
 * provider fields 接口异常/为空时的内置兜底元数据（与 202610051800.sql 种子一致）。
 * 已知五参数的 label 走 i18n，此处 label 仅作最终回退。
 */
const BUILTIN_FIELDS = [
  { key: 'db_dir', label: 'db_dir', type: 'string', default: 'data/memory/' },
  { key: 'auto_extract', label: 'auto_extract', type: 'boolean', default: true },
  { key: 'default_trust', label: 'default_trust', type: 'number', default: 0.5 },
  { key: 'min_trust_threshold', label: 'min_trust_threshold', type: 'number', default: 0.3 },
  { key: 'temporal_decay_half_life', label: 'temporal_decay_half_life', type: 'number', default: 0 }
];

const KNOWN_LABEL_KEYS = {
  db_dir: 'memoryManagement.engineParams.fieldDbDir',
  auto_extract: 'memoryManagement.engineParams.fieldAutoExtract',
  default_trust: 'memoryManagement.engineParams.fieldDefaultTrust',
  min_trust_threshold: 'memoryManagement.engineParams.fieldMinTrustThreshold',
  temporal_decay_half_life: 'memoryManagement.engineParams.fieldTemporalDecay'
};

function parseJsonSafe(text, fallback) {
  if (text === null || text === undefined || text === '') return fallback;
  if (typeof text === 'object') return text;
  try {
    const parsed = JSON.parse(text);
    return parsed === null || typeof parsed !== 'object' ? fallback : parsed;
  } catch (e) {
    return fallback;
  }
}

function coerceBool(value, fallback) {
  if (typeof value === 'boolean') return value;
  if (value === 'true' || value === 1 || value === '1') return true;
  if (value === 'false' || value === 0 || value === '0') return false;
  return fallback;
}

function coerceTrust(value, fallback) {
  const num = Number(value);
  if (value === null || value === undefined || value === '' || isNaN(num)) return fallback;
  return Math.min(1, Math.max(0, Math.round(num * 100) / 100));
}

export default {
  name: 'MemoryEngineParams',
  components: { CustomButton },
  props: {
    /** 当前选中 Agent（含 agentId/engine/memModelId 等字段，来自 MemoryManagement 的 agents 列表项） */
    agent: {
      type: Object,
      required: true
    }
  },
  data() {
    return {
      activeNames: [],
      advancedNames: [],
      loading: false,
      loadError: false,
      /** 引擎参数接口需要 superAdmin 权限；后端返回 code=403 时进入无权限降级态 */
      permissionDenied: false,
      /** getModelConfig 返回的 ModelConfigDTO 原始对象 */
      modelInfo: null,
      /** 加载时的完整 configJson（保存时全量回传的基底） */
      originalConfigJson: {},
      /** provider.fields 元数据（key/label/type/default） */
      providerFields: [],
      providersLoaded: false,
      form: null,
      snapshot: null,
      saving: false,
      /** 竞态令牌：Agent 切换后忽略过期响应 */
      loadToken: 0
    };
  },
  computed: {
    engine() {
      return this.agent ? String(this.agent.engine || '') : '';
    },
    isHolographic() {
      // mem_hybrid 长期层与 holographic 同库，引擎参数面板同样适用
      return this.engine === 'mem_holographic' || this.engine === 'mem_hybrid';
    },
    engineChipText() {
      if (this.isHolographic) return this.$t('memoryManagement.engineHolographic');
      if (this.engine === 'mem0ai' || this.engine === 'mem0') return this.$t('memoryManagement.engineMem0');
      if (this.engine === 'mem_local_short') return this.$t('memoryManagement.engineLocalShort');
      return this.$t('memoryManagement.engineNone');
    },
    /** 生效的 fields 元数据（provider 接口不可用时回退内置五参数） */
    effectiveFields() {
      return this.providerFields.length > 0 ? this.providerFields : BUILTIN_FIELDS;
    },
    extraFields() {
      return this.effectiveFields.filter((field) => !KNOWN_LABEL_KEYS[field.key]);
    },
    dirty() {
      if (!this.form || !this.snapshot) return false;
      return JSON.stringify(this.form) !== this.snapshot;
    },
    isDecayOff() {
      if (!this.form) return true;
      const value = Number(this.form.temporal_decay_half_life);
      return !value || value <= 0 || isNaN(value);
    },
    thresholdValue() {
      if (!this.form) return 0;
      return coerceTrust(this.form.min_trust_threshold, 0);
    },
    thresholdHint() {
      const value = this.thresholdValue;
      if (value < 0.25) return this.$t('memoryManagement.engineParams.thresholdHintLow');
      if (value <= 0.55) return this.$t('memoryManagement.engineParams.thresholdHintMid');
      return this.$t('memoryManagement.engineParams.thresholdHintHigh');
    },
    scaleLowWidth() {
      return Math.round(this.thresholdValue * 1000) / 10;
    },
    scaleMidWidth() {
      const width = Math.max(0, 0.7 - this.thresholdValue);
      return Math.round(width * 1000) / 10;
    },
    scaleHighWidth() {
      const width = Math.max(0, 1 - Math.max(0.7, this.thresholdValue));
      return Math.round(width * 1000) / 10;
    },
    trustScaleAria() {
      return this.$t('memoryManagement.engineParams.minTrustThresholdHint');
    }
  },
  watch: {
    agent: {
      immediate: true,
      handler(next, prev) {
        if (prev && next && prev.agentId === next.agentId && prev.memModelId === next.memModelId) return;
        this.resetState();
        this.loadAll();
      }
    }
  },
  methods: {
    resetState() {
      this.modelInfo = null;
      this.originalConfigJson = {};
      this.form = null;
      this.snapshot = null;
      this.loadError = false;
      this.permissionDenied = false;
      this.loading = false;
      this.advancedNames = [];
    },
    loadAll() {
      if (!this.isHolographic || !this.agent || !this.agent.memModelId) return;
      const token = ++this.loadToken;
      this.loading = true;
      this.loadError = false;
      this.loadProvidersOnce();
      Api.model.getModelConfig(
        this.agent.memModelId,
        (res) => {
          if (token !== this.loadToken) return;
          this.loading = false;
          const payload = res && res.data;
          if (payload && payload.code === 0 && payload.data) {
            this.modelInfo = payload.data;
            this.originalConfigJson = parseJsonSafe(payload.data.configJson, {});
            this.buildForm();
          } else {
            this.loadError = true;
          }
        },
        () => {
          if (token !== this.loadToken) return;
          this.loading = false;
          // 权限拒绝链路：后端 @RequiresPermissions 拒绝 → RenExceptionHandler 返回 HTTP 200 + body.code=403
          // httpRequest.js 对 200 且 code!==0/401 走 fail 回调，err.data.code 可取到 403
          if (err && err.data && err.data.code === 403) {
            this.permissionDenied = true;
            this.loadError = false;
          } else {
            this.loadError = true;
          }
        }
      );
    },
    /** 拉取 Memory 类型 provider 元数据（组件生命周期内只请求一次，失败静默回退内置字段） */
    loadProvidersOnce() {
      if (this.providersLoaded) return;
      Api.model.getModelProviders(
        'Memory',
        (data) => {
          this.providersLoaded = true;
          const list = Array.isArray(data) ? data : [];
          const provider = list.find((item) => String(item.providerCode) === this.engine);
          const fields = provider ? parseJsonSafe(provider.fields, []) : [];
          this.providerFields = (Array.isArray(fields) ? fields : [])
            .filter((field) => field && field.key)
            .map((field) => ({
              key: String(field.key),
              label: field.label || field.key,
              type: field.type || 'string',
              default: field.default
            }));
          // 元数据晚于表单构建到达时，用默认值补齐缺失字段
          if (this.form) this.ensureProviderDefaults();
        },
        () => {
          this.providersLoaded = true;
        }
      );
    },
    buildForm() {
      const config = this.originalConfigJson || {};
      const form = {};
      Object.keys(config).forEach((key) => {
        form[key] = config[key];
      });
      this.effectiveFields.forEach((field) => {
        if (!(field.key in form)) form[field.key] = field.default;
      });
      const defaults = this.fieldDefaultMap();
      form.db_dir = form.db_dir === null || form.db_dir === undefined ? '' : String(form.db_dir);
      form.auto_extract = coerceBool(form.auto_extract, coerceBool(defaults.auto_extract, true));
      form.default_trust = coerceTrust(form.default_trust, coerceTrust(defaults.default_trust, 0.5));
      form.min_trust_threshold = coerceTrust(form.min_trust_threshold, coerceTrust(defaults.min_trust_threshold, 0.3));
      const decayValue = Number(form.temporal_decay_half_life);
      form.temporal_decay_half_life = isNaN(decayValue) || decayValue < 0 ? 0 : Math.round(decayValue);
      this.form = form;
      this.snapshot = JSON.stringify(form);
    },
    ensureProviderDefaults() {
      if (!this.form) return;
      this.effectiveFields.forEach((field) => {
        if (!(field.key in this.form)) {
          this.$set(this.form, field.key, field.default);
        }
      });
    },
    fieldDefaultMap() {
      const map = {};
      this.effectiveFields.forEach((field) => {
        map[field.key] = field.default;
      });
      return map;
    },
    fieldVisible(key) {
      return this.effectiveFields.some((field) => field.key === key);
    },
    fieldLabel(key) {
      const providerField = this.providerFields.find((field) => field.key === key);
      const i18nKey = KNOWN_LABEL_KEYS[key];
      if (i18nKey) return this.$t(i18nKey);
      return providerField ? providerField.label : key;
    },
    formatTrustTooltip(value) {
      return Number(value).toFixed(2);
    },
    trustText(value) {
      return coerceTrust(value, 0).toFixed(2);
    },
    /** 滑杆步进 0.05 的浮点残差修正（0.15000000002 → 0.15） */
    roundTrustField(key) {
      if (!this.form) return;
      this.form[key] = coerceTrust(this.form[key], 0);
    },
    copyDbDir() {
      const text = this.form ? String(this.form.db_dir || '') : '';
      if (!text) return;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard
          .writeText(text)
          .then(() => this.notifyCopied())
          .catch(() => this.fallbackCopy(text));
      } else {
        this.fallbackCopy(text);
      }
    },
    fallbackCopy(text) {
      try {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        const successful = document.execCommand('copy');
        document.body.removeChild(textarea);
        if (successful) {
          this.notifyCopied();
        } else {
          this.$message.warning(this.$t('memoryManagement.engineParams.copyFailed'));
        }
      } catch (e) {
        this.$message.warning(this.$t('memoryManagement.engineParams.copyFailed'));
      }
    },
    notifyCopied() {
      this.$message.success(this.$t('memoryManagement.engineParams.copied'));
    },
    revert() {
      if (!this.snapshot) return;
      this.form = JSON.parse(this.snapshot);
    },
    handleSave() {
      if (this.permissionDenied || !this.dirty || this.saving || !this.modelInfo) return;
      this.saving = true;
      // configJson 全量回传：以加载时的原始配置为基底，叠加面板编辑值（复用模型配置编辑语义）
      const mergedConfig = Object.assign({}, this.originalConfigJson, this.form);
      mergedConfig.type = this.originalConfigJson.type || this.engine;
      const formData = {
        id: this.modelInfo.id,
        modelCode: this.modelInfo.modelCode,
        modelName: this.modelInfo.modelName,
        isDefault: this.modelInfo.isDefault,
        isEnabled: this.modelInfo.isEnabled,
        docLink: this.modelInfo.docLink,
        remark: this.modelInfo.remark,
        sort: this.modelInfo.sort,
        configJson: mergedConfig
      };
      Api.model.updateModel(
        {
          modelType: this.modelInfo.modelType || 'Memory',
          provideCode: mergedConfig.type,
          id: this.modelInfo.id,
          formData
        },
        (res) => {
          this.saving = false;
          const payload = res && res.data;
          if (payload && payload.code === 0) {
            this.$message.success(this.$t('memoryManagement.engineParams.saveSuccess'));
            this.originalConfigJson = mergedConfig;
            this.snapshot = JSON.stringify(this.form);
            this.$emit('saved', mergedConfig);
          } else {
            this.$message.error((payload && payload.msg) || this.$t('memoryManagement.engineParams.saveFailed'));
          }
        },
        (err) => {
          this.saving = false;
          this.$message.error((err && err.data && err.data.msg) || this.$t('memoryManagement.engineParams.saveFailed'));
        }
      );
    }
  }
};
</script>

<style lang="scss" scoped>
.memory-engine-params {
  flex-shrink: 0;
}

.engine-params-collapse {
  border: 1px solid var(--kawaii-border);
  border-radius: var(--kawaii-radius-sm);
  background: var(--kawaii-surface);
  overflow: hidden;

  ::v-deep .el-collapse-item__header {
    border-bottom-color: transparent;
    color: var(--kawaii-text);
    font-size: 14px;
    padding: 0 14px;
    background: transparent;

    &.is-active {
      border-bottom-color: var(--kawaii-border);
    }
  }

  ::v-deep .el-collapse-item__wrap {
    border-bottom-color: transparent;
    background: transparent;
  }

  ::v-deep .el-collapse-item__content {
    padding: 14px 16px 16px;
  }
}

.collapse-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;

  .collapse-title__icon {
    color: var(--kawaii-primary);
    font-size: 16px;
  }

  .collapse-title__text {
    font-weight: 600;
    color: var(--kawaii-text);
  }

  .collapse-title__chip {
    display: inline-flex;
    align-items: center;
    padding: 2px 10px;
    border-radius: 10px;
    font-size: 12px;
    white-space: nowrap;
    background: var(--kawaii-surface-2);
    color: var(--kawaii-text-secondary);
    border: 1px solid var(--kawaii-border);

    &.collapse-title__chip--active {
      background: var(--kawaii-success-light);
      color: var(--kawaii-success-deep);
    }
  }
}

/* ========== 引导 / 降级态 ========== */
.engine-params-guide {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 20px 16px;
  text-align: center;

  .guide__icon {
    font-size: 32px;
    color: var(--kawaii-primary);

    &.guide__icon--warn {
      color: var(--kawaii-warning);
    }
  }

  .guide__title {
    margin: 4px 0 0;
    font-size: 14px;
    font-weight: 600;
    color: var(--kawaii-text);
    max-width: 420px;
    line-height: 1.6;
  }

  .guide__desc {
    margin: 0 0 10px;
    font-size: 13px;
    color: var(--kawaii-text-secondary);
    max-width: 460px;
    line-height: 1.6;
  }
}

.engine-params-loading {
  min-height: 120px;
}

/* ========== 作用域与生效说明 ========== */
.params-meta {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  margin-bottom: 14px;
  background: var(--kawaii-surface-2);
  border-radius: var(--kawaii-radius-sm);

  .params-meta__row {
    display: flex;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
  }

  .params-meta__label {
    font-size: 13px;
    font-weight: 600;
    color: var(--kawaii-text);
    white-space: nowrap;
  }

  .params-meta__desc {
    font-size: 12px;
    color: var(--kawaii-text-secondary);
  }
}

.params-effect {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--kawaii-text-secondary);
  line-height: 1.6;

  .params-effect__icon {
    color: var(--kawaii-primary);
    font-size: 14px;
    flex-shrink: 0;
  }
}

/* ========== 表单 ========== */
.params-form {
  .field-label {
    font-size: 13px;
    font-weight: 600;
    color: var(--kawaii-text);
    line-height: 1.5;
  }

  ::v-deep .el-form-item {
    margin-bottom: 16px;
  }
}

.field-hint {
  font-size: 12px;
  color: var(--kawaii-text-secondary);
  line-height: 1.6;
  margin-top: 4px;

  &.field-hint--live {
    color: var(--kawaii-text);
  }
}

.db-dir-row {
  display: flex;
  align-items: center;
  gap: 8px;

  .db-dir-input {
    flex: 1;

    ::v-deep .el-input__inner {
      background: var(--kawaii-surface-2);
      color: var(--kawaii-text-secondary);
    }

    ::v-deep .el-input-group__prepend {
      background: var(--kawaii-surface-2);
      border-color: var(--kawaii-border);
      color: var(--kawaii-text-secondary);
      padding: 0 10px;
    }
  }

  .copy-btn {
    border-color: var(--kawaii-border);
    color: var(--kawaii-text-secondary);
    background: var(--kawaii-surface);

    &:hover,
    &:focus {
      color: var(--kawaii-primary);
      border-color: var(--kawaii-primary);
      background: var(--kawaii-surface);
    }
  }
}

.switch-row {
  display: flex;
  align-items: center;
  gap: 12px;

  .field-hint {
    margin-top: 0;
  }
}

.slider-row {
  display: flex;
  align-items: center;
  gap: 14px;

  .slider-control {
    flex: 1;

    ::v-deep .el-slider__bar {
      background: var(--kawaii-primary);
    }

    ::v-deep .el-slider__button {
      border-color: var(--kawaii-primary);
    }
  }

  .slider-value {
    width: 44px;
    text-align: right;
    font-size: 14px;
    font-weight: 600;
    color: var(--kawaii-text);
    font-variant-numeric: tabular-nums;
  }
}

/* ========== 三色条 ========== */
.trust-scale {
  display: flex;
  width: 100%;
  height: 8px;
  margin-top: 10px;
  border-radius: 4px;
  overflow: hidden;

  .trust-scale__segment {
    height: 100%;

    &.trust-scale__segment--low {
      background: var(--kawaii-danger);
    }

    &.trust-scale__segment--mid {
      background: var(--kawaii-warning);
    }

    &.trust-scale__segment--high {
      background: var(--kawaii-success);
    }
  }
}

.trust-scale-legend {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;

  .trust-scale-legend__item {
    font-size: 12px;
    color: var(--kawaii-text-secondary);

    &.trust-scale-legend__item--high {
      color: var(--kawaii-success-deep);
    }
  }
}

/* ========== 高级项折叠 ========== */
.advanced-collapse {
  border-top: 1px dashed var(--kawaii-border);
  border-bottom: none;

  ::v-deep .el-collapse-item__header {
    padding: 0 2px;
    font-size: 13px;
    color: var(--kawaii-text-secondary);
    background: transparent;
    border-bottom-color: transparent;

    &.is-active {
      border-bottom-color: transparent;
    }
  }

  ::v-deep .el-collapse-item__wrap {
    border-bottom-color: transparent;
    background: transparent;
  }

  .advanced-title {
    font-size: 13px;
    color: var(--kawaii-text-secondary);
    font-weight: 500;
  }
}

.decay-row {
  display: flex;
  align-items: center;
  gap: 10px;

  .decay-input {
    width: 160px;
  }

  .decay-unit {
    font-size: 13px;
    color: var(--kawaii-text-secondary);
  }

  .decay-tag {
    background: var(--kawaii-surface-2);
    color: var(--kawaii-text-secondary);
    border-color: var(--kawaii-border);
  }
}

/* ========== 底部操作 ========== */
.params-footer {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 10px;
  padding-top: 4px;
  border-top: 1px solid var(--kawaii-border);
}
</style>
