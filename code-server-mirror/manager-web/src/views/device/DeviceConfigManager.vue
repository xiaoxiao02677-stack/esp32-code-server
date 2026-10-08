<template>
    <div class="device-config-page">
        <div class="main-wrapper">
            <div class="content-panel">
                <div class="content-area">
                    <el-card class="params-card" shadow="never">
                        <div class="operation-header">
                            <div class="dc-title-block">
                                <h2 class="page-title">{{ $t('deviceConfigManagement.title') }}</h2>
                                <p class="dc-subtitle">{{ $t('deviceConfigManagement.subtitle') }}</p>
                            </div>
                            <div class="right-operations">
                                <el-input v-model="searchId" :placeholder="$t('deviceConfigManagement.searchPlaceholder')"
                                    class="search-input" clearable @keyup.enter.native="handleSearch" />
                                <CustomButton icon="el-icon-search" type="confirm" @click="handleSearch">
                                    {{ $t('deviceConfigManagement.search') }}
                                </CustomButton>
                                <CustomButton icon="el-icon-delete" type="delete" @click="confirmClearAll">
                                    {{ $t('deviceConfigManagement.clearAll') }}
                                </CustomButton>
                            </div>
                        </div>

                        <CustomTable :data="configList" :columns="tableColumns" :loading="loading"
                            :show-operations="true" :operations-label="$t('deviceConfigManagement.action')"
                            :operations-width="140" :total="total" :current-page="currentPage" :page-size="pageSize"
                            :page-size-options="pageSizeOptions" @size-change="handlePageSizeChange"
                            @page-change="goToPage">
                            <template slot="configJson" slot-scope="scope">
                                <span class="dc-json-preview">{{ truncateJson(scope.row.configJson) }}</span>
                            </template>
                            <template slot="createDate" slot-scope="scope">
                                {{ formatDate(scope.row.createDate) }}
                            </template>
                            <template slot="updateDate" slot-scope="scope">
                                {{ formatDate(scope.row.updateDate) }}
                            </template>
                            <template slot="operations" slot-scope="scope">
                                <el-button size="mini" type="text" @click="showJsonDialog(scope.row)">
                                    {{ $t('deviceConfigManagement.view') }}
                                </el-button>
                                <el-button size="mini" type="text" class="dc-danger-link"
                                    @click="confirmDelete(scope.row)">
                                    {{ $t('deviceConfigManagement.delete') }}
                                </el-button>
                            </template>
                        </CustomTable>

                        <div v-if="!loading && configList.length === 0" class="dc-empty-tip">
                            {{ $t('deviceConfigManagement.empty') }}
                        </div>
                    </el-card>
                </div>
            </div>
        </div>

        <!-- 单设备配置 JSON 查看 -->
        <el-dialog :title="$t('deviceConfigManagement.viewTitle')" :visible.sync="dialogVisible" width="560px"
            class="dc-json-dialog">
            <div class="dc-dialog-body">
                <div class="dc-device-id">
                    <span class="dc-label">{{ $t('deviceConfigManagement.deviceId') }}</span>
                    <span class="dc-value">{{ dialogDeviceId }}</span>
                </div>
                <pre v-if="dialogJson" class="dc-json">{{ dialogJson }}</pre>
                <div v-else class="dc-no-record">{{ $t('deviceConfigManagement.noRecord') }}</div>
                <div class="dc-dialog-footer">
                    <CustomButton v-if="dialogRaw" icon="el-icon-document-copy" type="default" size="small"
                        @click="copyJson">
                        {{ $t('deviceConfigManagement.copy') }}
                    </CustomButton>
                </div>
            </div>
        </el-dialog>
    </div>
</template>

<script>
import Api from "@/apis/api";
import CustomButton from "@/components/CustomButton.vue";
import CustomTable from "@/components/CustomTable.vue";
import { formatDate } from "@/utils/format";

export default {
    name: "DeviceConfigManager",
    components: { CustomButton, CustomTable },
    data() {
        return {
            searchId: "",
            loading: false,
            configList: [],
            currentPage: 1,
            pageSize: 10,
            pageSizeOptions: [10, 20, 50, 100],
            total: 0,
            dialogVisible: false,
            dialogDeviceId: "",
            dialogJson: "",
            dialogRaw: "",
            tableColumns: []
        };
    },
    created() {
        this.initTableColumns();
        this.fetchConfigList();
    },
    methods: {
        initTableColumns() {
            this.tableColumns = [
                { prop: 'deviceId', label: this.$t('deviceConfigManagement.deviceId'), align: 'center', minWidth: 220 },
                { prop: 'configJson', label: this.$t('deviceConfigManagement.configJson'), align: 'left', minWidth: 260 },
                { prop: 'createDate', label: this.$t('deviceConfigManagement.createTime'), align: 'center' },
                { prop: 'updateDate', label: this.$t('deviceConfigManagement.updateTime'), align: 'center' }
            ];
        },
        handlePageSizeChange(val) {
            this.pageSize = val;
            this.currentPage = 1;
            this.fetchConfigList();
        },
        goToPage(page) {
            if (page !== this.currentPage) {
                this.currentPage = page;
                this.fetchConfigList();
            }
        },
        handleSearch() {
            this.currentPage = 1;
            this.fetchConfigList();
        },
        fetchConfigList() {
            this.loading = true;
            const params = {
                page: this.currentPage,
                limit: this.pageSize,
                deviceId: this.searchId || "",
                orderField: "update_date",
                order: "desc"
            };
            Api.deviceConfig.getDeviceConfigList(params, (res) => {
                this.loading = false;
                res = res.data;
                if (res.code === 0) {
                    this.configList = (res.data && res.data.list) || [];
                    this.total = (res.data && res.data.total) || 0;
                } else {
                    this.configList = [];
                    this.total = 0;
                    this.$message.error({
                        message: res.msg || this.$t('deviceConfigManagement.fetchFailed'),
                        showClose: true
                    });
                }
            });
        },
        truncateJson(raw) {
            const text = raw == null ? "" : String(raw);
            return text.length > 60 ? text.slice(0, 60) + "..." : text;
        },
        showJsonDialog(row) {
            if (!row || !row.deviceId) {
                this.$message.warning(this.$t('deviceConfigManagement.invalidRecord'));
                return;
            }
            this.dialogDeviceId = row.deviceId;
            this.dialogRaw = row.configJson || "";
            try {
                this.dialogJson = JSON.stringify(JSON.parse(row.configJson), null, 2);
            } catch (e) {
                // 历史脏数据兜底：原样展示
                this.dialogJson = this.dialogRaw;
            }
            this.dialogVisible = true;
        },
        confirmDelete(row) {
            if (!row || !row.deviceId) {
                this.$message.warning(this.$t('deviceConfigManagement.invalidRecord'));
                return;
            }
            this.$confirm(this.$t('deviceConfigManagement.confirmDelete', { deviceId: row.deviceId }),
                this.$t('common.warning'), {
                    confirmButtonText: this.$t('common.confirm'),
                    cancelButtonText: this.$t('common.cancel'),
                    type: 'warning',
                    distinguishCancelAndClose: true
                }).then(() => {
                    Api.deviceConfig.deleteDeviceConfig(row.deviceId, (res) => {
                        res = res.data;
                        if (res.code === 0) {
                            this.$message.success({
                                message: this.$t('deviceConfigManagement.deleteSuccess'),
                                showClose: true
                            });
                            this.fetchConfigList();
                        } else {
                            this.$message.error({
                                message: res.msg || this.$t('deviceConfigManagement.deleteFailed'),
                                showClose: true
                            });
                        }
                    });
                }).catch((action) => {
                    if (action === 'cancel') {
                        this.$message({
                            type: 'info',
                            message: this.$t('common.cancel'),
                            duration: 1000
                        });
                    }
                });
        },
        confirmClearAll() {
            this.$confirm(this.$t('deviceConfigManagement.confirmClearAll'),
                this.$t('common.warning'), {
                    confirmButtonText: this.$t('common.confirm'),
                    cancelButtonText: this.$t('common.cancel'),
                    type: 'error',
                    distinguishCancelAndClose: true
                }).then(() => {
                    Api.deviceConfig.clearAllDeviceConfigs((res) => {
                        res = res.data;
                        if (res.code === 0) {
                            this.$message.success({
                                message: this.$t('deviceConfigManagement.clearSuccess', { count: res.data || 0 }),
                                showClose: true
                            });
                            this.currentPage = 1;
                            this.fetchConfigList();
                        } else {
                            this.$message.error({
                                message: res.msg || this.$t('deviceConfigManagement.clearFailed'),
                                showClose: true
                            });
                        }
                    });
                }).catch(() => {
                    // 取消/关闭静默处理
                });
        },
        copyJson() {
            const text = this.dialogRaw || this.dialogJson;
            const done = () => this.$message.success(this.$t('deviceConfigManagement.copied'));
            const fail = () => this.$message.error(this.$t('deviceConfigManagement.copyFailed'));
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(done).catch(fail);
                return;
            }
            // 非安全上下文兜底
            const textarea = document.createElement("textarea");
            textarea.value = text;
            textarea.style.position = "fixed";
            textarea.style.opacity = "0";
            document.body.appendChild(textarea);
            textarea.select();
            try {
                document.execCommand("copy");
                done();
            } catch (e) {
                fail();
            }
            document.body.removeChild(textarea);
        },
        formatDate
    }
};
</script>

<style lang="scss" scoped>
.device-config-page {
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

.operation-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 0 16px 0;
}

.dc-title-block {
    .page-title {
        font-weight: 500;
        font-size: 24px;
        margin: 0;
    }

    .dc-subtitle {
        margin: 4px 0 0;
        font-size: 13px;
        color: #b0727f;
    }
}

.right-operations {
    display: flex;
    gap: 10px;
    margin-left: auto;
}

.search-input {
    width: 240px;
}

.content-panel {
    display: flex;
    overflow: hidden;
    height: 100%;
    border-radius: 14px;
    background: transparent;
}

.content-area {
    flex: 1;
    height: 100%;
    min-width: 600px;
    overflow: auto;
    display: flex;
    flex-direction: column;
}

.params-card {
    flex: 1;
    display: flex;
    flex-direction: column;
    border-radius: 14px;
    border: 1px solid #ffe3ea;
    background: #fffafb;
}

.dc-empty-tip {
    padding: 40px 0;
    text-align: center;
    color: #b0727f;
    font-size: 14px;
}

.dc-json-preview {
    color: #6b5b60;
    font-family: "SFMono-Regular", Consolas, monospace;
    font-size: 12px;
}

.dc-danger-link {
    color: #ff8fab;
}

.dc-dialog-body {
    .dc-device-id {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 12px;

        .dc-label {
            color: #b0727f;
            font-size: 13px;
        }

        .dc-value {
            font-family: Consolas, monospace;
            font-size: 13px;
            color: #5c444a;
            word-break: break-all;
        }
    }

    .dc-json {
        margin: 0;
        padding: 14px 16px;
        border: 1px solid #ffe3ea;
        border-radius: 14px;
        background: #fff5f8;
        color: #5c444a;
        font-size: 13px;
        line-height: 1.6;
        max-height: 360px;
        overflow: auto;
        white-space: pre-wrap;
        word-break: break-all;
    }

    .dc-no-record {
        padding: 24px 0;
        text-align: center;
        color: #b0727f;
        font-size: 13px;
    }

    .dc-dialog-footer {
        display: flex;
        justify-content: flex-end;
        margin-top: 14px;
    }
}
</style>
