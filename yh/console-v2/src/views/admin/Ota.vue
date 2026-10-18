<template>
  <div>
    <div class="page-head">
      <div>
        <h1>OTA <span style="color:var(--primary)">固件</span></h1>
        <p class="sub">上传与管理固件升级包</p>
      </div>
      <div class="head-actions">
        <label class="btn btn-primary" style="cursor:pointer">
          {{ uploading ? '上传中…' : '⬆ 上传固件' }}
          <input type="file" accept=".bin,.apk" style="display:none" @change="onFilePicked" />
        </label>
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <div class="stats-grid" style="margin-bottom:20px">
      <StatCard icon="package" label="固件包" :value="otas.length" />
      <StatCard icon="upload" label="最高版本" :value="maxVersion" />
    </div>

    <DataTable title="固件列表" :loading="loading">
      <table class="data-table">
        <thead><tr><th>版本</th><th>文件</th><th>时间</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="o in otas" :key="o.id">
            <td><div class="cell-main">{{ o.firmwareVersion || o.appVersion || o.version }}</div></td>
            <td style="font-size:12px">{{ o.fileName || o.filePath || o.path || '—' }}</td>
            <td style="font-size:12px">{{ o.createDate || '' }}</td>
            <td>
              <div class="row-actions">
                <button class="link-btn" @click="download(o)">⬇ 下载</button>
                <button class="link-btn danger" @click="remove(o)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="otas.length === 0" class="empty-state"><div class="empty-icon"><YhIcon name="package" /></div><strong>暂无固件</strong></div>
    </DataTable>
  </div>
</template>

<script setup>
import YhIcon from '../../components/YhIcon.vue'
import { computed, inject, onMounted, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')
const otas = ref([])
const loading = ref(false)
const uploading = ref(false)
// 版本比较：按数值段比较，避免字符串排序把 "2.10.0" 排到 "2.9.0" 前面
const cmpVer = (a, b) => {
  const pa = String(a).split('.').map(n => parseInt(n, 10) || 0)
  const pb = String(b).split('.').map(n => parseInt(n, 10) || 0)
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const d = (pa[i] || 0) - (pb[i] || 0)
    if (d) return d
  }
  return 0
}
const maxVersion = computed(() => otas.value.map(o => o.firmwareVersion || o.appVersion || o.version).filter(Boolean).sort(cmpVer).pop() || '—')

async function load() {
  loading.value = true
  try {
    const res = await adminApi.otaPage({ page: 1, limit: 100 })
    otas.value = res.data?.list || []
  } catch (e) { toast(e.msg || '加载失败', 'error') }
  finally { loading.value = false }
}

async function onFilePicked(e) {
  const file = e.target.files?.[0]
  if (!file) return
  uploading.value = true
  try {
    // 契约：POST /otaMag/upload multipart file（仅 .bin/.apk，超管权限）
    const res = await adminApi.uploadOta(file)
    if (res.code === 0) { toast('固件已上传'); load() }
    else toast('上传失败：' + (res.msg || '仅支持 .bin/.apk，且需超级管理员权限'), 'error')
  } catch (e) { toast('上传失败：' + (e.msg || ''), 'error') }
  finally { uploading.value = false; e.target.value = '' }
}

async function download(o) {
  // 两段式（契约 D3）：先 GET /otaMag/getDownloadUrl/{id} 取 JSON 包装的真实 URL，再新窗口下载；
  // 失败时回退直连二进制流端点 /otaMag/download/{uuid}（与原控制台行为一致）
  try {
    const res = await adminApi.get('/otaMag/getDownloadUrl/' + (o.uuid || o.id))
    const url = (res && res.data) || ''
    if (url) { window.open(url, '_blank'); return }
  } catch (e) { /* 回退直连 */ }
  window.open(API_BASE_FALLBACK + '/otaMag/download/' + (o.uuid || o.id), '_blank')
}
const API_BASE_FALLBACK = '/yuhe'

function remove(o) {
  askConfirm({
    title: '删除固件', message: `确定删除固件「${o.firmwareVersion || o.id}」吗？`, danger: true,
    onOk: async () => {
      try { await adminApi.deleteOta(o.id); toast('已删除'); load() }
      catch (e) { toast(e.msg || '删除失败', 'error') }
    }
  })
}

onMounted(load)
</script>
