<template>
  <div>
    <div class="page-head">
      <div>
        <h1>OTA <span style="color:var(--primary)">固件</span></h1>
        <p class="sub">上传与管理固件升级包（上传后需注册固件信息设备才能收到升级）</p>
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
        <thead><tr><th>版本</th><th>类型 / 轨道</th><th>文件</th><th>时间</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="o in otas" :key="o.id">
            <td><div class="cell-main">{{ o.firmwareVersion || o.appVersion || o.version }}</div></td>
            <td style="font-size:12px">{{ o.type || '—' }}</td>
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
      <div v-if="otas.length === 0" class="empty-state">
        <div class="empty-icon"><YhIcon name="package" /></div>
        <strong>暂无固件</strong>
        <p class="empty-hint">上传 .bin 后会弹出「注册固件信息」，选择类型并确认版本号即完成登记。<br>
          登记后到 <router-link to="/admin/devices" class="empty-link">设备管理</router-link> 页，
          点击设备行的「⬆ OTA」可给单台设备指定固件或切换主题轨道。</p>
      </div>
    </DataTable>

    <!-- 固件信息注册弹窗：上传文件成功后弹出，补齐 type/version 才会进 ai_ota -->
    <div v-if="reg.show" class="modal-mask" @click.self="reg.show = false">
      <div class="modal">
        <h3>注册固件信息</h3>
        <p class="reg-tip">文件已上传（{{ reg.filePath }}）。设备按「类型 + 版本」匹配固件，
          注册后同类型且版本更高的设备会收到升级推送。</p>
        <div class="form-row">
          <label>固件类型（OTA 轨道）</label>
          <select v-model="reg.type">
            <option v-for="t in typeOptions" :key="t" :value="t">{{ t }}</option>
          </select>
        </div>
        <div class="form-row">
          <label>版本号（须与固件内嵌版本一致）</label>
          <input v-model="reg.version" placeholder="如 2.5.2" />
        </div>
        <div class="form-row">
          <label>固件名称</label>
          <input v-model="reg.firmwareName" placeholder="如 屿禾-1.54寸TFT-WiFi版" />
        </div>
        <div class="form-row">
          <label>备注</label>
          <input v-model="reg.remark" placeholder="可选" />
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="reg.show = false">取消</button>
          <button class="btn btn-primary" :disabled="!reg.type || !reg.version || saving" @click="doRegister">
            {{ saving ? '保存中…' : '注册' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import YhIcon from '../../components/YhIcon.vue'
import { computed, inject, onMounted, reactive, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import DataTable from '../../components/DataTable.vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const askConfirm = inject('askConfirm')
const otas = ref([])
const loading = ref(false)
const uploading = ref(false)
const saving = ref(false)

// 固件类型候选：已知版型轨道（默认 + 主题后缀）∪ 已注册记录里的 type
const KNOWN_TYPES = [
  'yh-154tft-wifi', 'yh-154tft-wifi-emopet', 'yh-154tft-wifi-pixel-pet',
  'yh-big-ili9341', 'yh-big-ili9341-emopet', 'yh-big-ili9341-pixel-pet',
  'yh-cam', 'yh-cam-emopet', 'yh-cam-pixel-pet',
  'yh-n16r8-st7789', 'yh-n16r8-st7789-emopet', 'yh-n16r8-st7789-pixel-pet',
]
const typeOptions = computed(() => {
  const extra = otas.value.map(o => o.type).filter(Boolean)
  return [...new Set([...KNOWN_TYPES, ...extra])]
})

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

/** 解析 ESP32 app 描述符（esp_app_desc_t）内嵌 version：
 *  镜像里找魔数 0xABCD5432（小端），version 字段在魔数偏移 +16 处、32 字节。 */
function readBinVersionFrom(bytes) {
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  for (let i = 0; i + 20 <= bytes.length; i += 1) {
    if (dv.getUint32(i, true) === 0xABCD5432) {
      const raw = bytes.subarray(i + 16, i + 16 + 32)
      const s = new TextDecoder().decode(raw)
      const v = s.split('\u0000')[0].trim()
      if (v) return v
      break
    }
  }
  return ''
}

/** 从 bin 里扫 BOARD_TYPE 字符串字面量识别固件类型（OTA 轨道）。
 *  固件宏 BOARD_TYPE="<type>" 会以字符串编进 rodata；已知类型集合精确匹配，
 *  取最长命中（防前缀误报：'yh-154tft-wifi' 是 'yh-154tft-wifi-emopet' 的前缀，
 *  命中位置的后一个字符必须是结尾或非类型字符）。 */
function detectBoardType(bytes) {
  const text = new TextDecoder('latin1').decode(bytes)
  let best = ''
  for (const t of KNOWN_TYPES) {
    let idx = text.indexOf(t)
    while (idx >= 0) {
      const next = text[idx + t.length]
      if (next === undefined || !/[a-z0-9.-]/.test(next)) {
        if (t.length > best.length) best = t
        break
      }
      idx = text.indexOf(t, idx + 1)
    }
  }
  return best
}

const reg = reactive({ show: false, filePath: '', type: '', version: '', firmwareName: '', remark: '' })

async function onFilePicked(e) {
  const file = e.target.files?.[0]
  if (!file) return
  uploading.value = true
  try {
    // 先本地解析（bin 全量读入识别类型 + 版本，apk 跳过）
    let ver = '', btype = ''
    if (file.name.toLowerCase().endsWith('.bin')) {
      const bytes = new Uint8Array(await file.arrayBuffer())
      ver = readBinVersionFrom(bytes)
      btype = detectBoardType(bytes)
    }
    // 契约：POST /otaMag/upload multipart file（仅 .bin/.apk，超管权限）
    const res = await adminApi.uploadOta(file)
    if (res.code === 0 && res.data) {
      reg.filePath = res.data
      reg.version = ver
      reg.firmwareName = file.name.replace(/\.(bin|apk)$/i, '')
      reg.remark = ''
      reg.type = btype
      reg.show = true
      const hints = []
      if (btype) hints.push(`类型 ${btype}`)
      if (ver) hints.push(`版本 ${ver}`)
      toast(hints.length ? `上传成功，已识别${hints.join(' / ')}` : '上传成功，请补齐固件类型与版本')
    } else {
      toast('上传失败：' + (res.msg || '仅支持 .bin/.apk，且需超级管理员权限'), 'error')
    }
  } catch (e) { toast('上传失败：' + (e.msg || ''), 'error') }
  finally { uploading.value = false; e.target.value = '' }
}

async function doRegister() {
  saving.value = true
  try {
    // 契约：POST /otaMag 保存固件记录（type+version+firmwarePath 进 ai_ota）
    const res = await adminApi.otaSave({
      firmwareName: reg.firmwareName || reg.type,
      type: reg.type,
      version: reg.version,
      firmwarePath: reg.filePath,
      remark: reg.remark || '',
    })
    if (res.code === 0) { toast('固件已注册，设备可收到升级'); reg.show = false; load() }
    else toast('注册失败：' + (res.msg || ''), 'error')
  } catch (e) { toast('注册失败：' + (e.msg || ''), 'error') }
  finally { saving.value = false }
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

<style scoped>
.reg-tip { color: var(--text-sub); font-size: 13px; line-height: 1.6; margin-bottom: 14px; }
.reg-tip code { background: var(--bg-2, #f4f6fa); border-radius: 6px; padding: 1px 6px; font-size: 12px; }
.empty-hint { color: var(--text-sub); font-size: 13px; line-height: 1.8; margin-top: 8px; }
.empty-link { color: var(--primary); font-weight: 600; }
</style>
