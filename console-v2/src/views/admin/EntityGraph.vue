<template>
  <div>
    <div class="page-head">
      <div>
        <h1>实体图谱 <span style="color:var(--primary)">管理</span></h1>
        <p class="sub">可视化智能体记忆中的实体及其关系，支持搜索、筛选与详情查看</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" @click="load" :disabled="loading">↻ 刷新</button>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="toolbar">
      <input
        v-model="searchQuery"
        class="search-input"
        placeholder="搜索实体名称…"
        @input="onSearch"
      />
      <select v-model="filterType" class="mini-select" @change="onFilter">
        <option value="">全部类型</option>
        <option v-for="t in typeOptions" :key="t" :value="t">{{ t }}</option>
      </select>
      <select v-model="trustRange" class="mini-select" @change="onFilter">
        <option value="">全部信任度</option>
        <option value="high">高 (≥0.8)</option>
        <option value="mid">中 (0.4–0.8)</option>
        <option value="low">低 (<0.4)</option>
      </select>
    </div>

    <!-- 左右分栏：实体列表 + Canvas 图谱 -->
    <div class="layout">
      <!-- 实体列表 -->
      <div class="entity-panel">
        <div class="panel-header">
          <span class="panel-title">实体列表</span>
          <span class="panel-count">{{ filteredEntities.length }} / {{ entities.length }}</span>
        </div>
        <div class="entity-list">
          <div
            v-for="e in filteredEntities"
            :key="e.name"
            class="entity-item"
            :class="{ active: selectedEntity === e.name }"
            @click="selectEntity(e)"
          >
            <span class="e-dot" :style="{ background: entityColor(e.type) }"></span>
            <div class="e-info">
              <div class="e-name">{{ e.name }}</div>
              <div class="e-meta">
                <span class="e-type badge" :style="{ background: typeBg(e.type) }">{{ e.type || 'unknown' }}</span>
                <span class="e-trust">{{ trustLabel(e.trust_score) }}</span>
              </div>
            </div>
          </div>
          <div v-if="!loading && !filteredEntities.length" class="empty-state">
            <div class="empty-icon">🔍</div>
            <strong>暂无匹配实体</strong>
          </div>
        </div>
      </div>

      <!-- Canvas 图谱 -->
      <div class="graph-panel">
        <div class="panel-header">
          <span class="panel-title">关系图谱</span>
          <span class="panel-hint" v-if="selectedEntity">点击空白处取消选中</span>
          <span class="panel-hint" v-else>点击实体查看详情</span>
        </div>
        <div class="canvas-wrap">
          <canvas ref="graphCanvas" class="graph-canvas"></canvas>
        </div>

        <!-- 实体详情面板 -->
        <div v-if="selectedEntityData" class="detail-panel">
          <div class="detail-header">
            <span class="detail-name">{{ selectedEntityData.name }}</span>
            <button class="link-btn" @click="selectedEntityData = null">✕</button>
          </div>
          <div class="detail-row">
            <span class="detail-label">类型</span>
            <span class="badge" :style="{ background: typeBg(selectedEntityData.type) }">{{ selectedEntityData.type || 'unknown' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">信任度</span>
            <div class="trust-bar-wrap">
              <div class="trust-bar">
                <div class="trust-fill" :style="{ width: trustPct(selectedEntityData.trust_score) + '%' }"></div>
              </div>
              <span class="trust-num">{{ Number(selectedEntityData.trust_score).toFixed(2) }}</span>
            </div>
          </div>
          <div class="detail-row" v-if="selectedEdges.length">
            <span class="detail-label">关联实体（{{ selectedEdges.length }}）</span>
          </div>
          <div class="detail-edges">
            <div v-for="edge in selectedEdges" :key="edge.target" class="edge-tag">
              <span class="edge-label">{{ edge.relation || '关联' }}</span>
              <span class="edge-target">{{ edge.target }}</span>
              <span class="edge-weight">{{ edge.weight ? Number(edge.weight).toFixed(2) : '—' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
<script setup>
import { computed, inject, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { adminApi } from '../../lib/api'

const toast = inject('toast')
const loading = ref(false)
const entities = ref([])
const graphEdges = ref([])
const searchQuery = ref('')
const filterType = ref('')
const trustRange = ref('')
const selectedEntity = ref('')
const selectedEntityData = ref(null)
const graphCanvas = ref(null)
const typeOptions = ref([])
const nodeMap = ref(new Map())
let dragNode = null
let dragOffset = { x: 0, y: 0 }

const filteredEntities = computed(() => {
  return entities.value.filter(e => {
    const matchSearch = !searchQuery.value || e.name.toLowerCase().includes(searchQuery.value.toLowerCase())
    const matchType = !filterType.value || e.type === filterType.value
    let matchTrust = true
    if (trustRange.value === 'high') matchTrust = (e.trust_score || 0) >= 0.8
    else if (trustRange.value === 'mid') matchTrust = (e.trust_score || 0) >= 0.4 && (e.trust_score || 0) < 0.8
    else if (trustRange.value === 'low') matchTrust = (e.trust_score || 0) < 0.4
    return matchSearch && matchType && matchTrust
  })
})

const selectedEdges = computed(() => {
  if (!selectedEntity.value) return []
  return graphEdges.value.filter(e => e.source === selectedEntity.value || e.target === selectedEntity.value)
})

const PALETTE = ['#FF8FAB', '#FFB6C6', '#FFD86B', '#9EE6D0', '#B8A9F5', '#8FC7FF', '#FFC3A0', '#A8E6CF', '#F8B500', '#50C878']
const TYPE_COLORS = {
  person: '#FF8FAB', organization: '#8FC7FF', location: '#9EE6D0',
  product: '#FFD86B', event: '#B8A9F5', concept: '#FFC3A0'
}

function entityColor(type) { return TYPE_COLORS[type] || '#B8A9F5' }
function typeBg(type) { return (TYPE_COLORS[type] || '#B8A9F5') + '22' }
function trustLabel(v) { const n=Number(v); if(n>=0.8) return String.fromCharCode(10003)+' \u9ad8\u53ef\u4fe1'; if(n>=0.4) return String.fromCharCode(9675)+' \u4e2d\u53ef\u4fe1'; return String.fromCharCode(9651)+' \u4f4e\u53ef\u4fe1' }
function trustPct(v) { return Math.round((Number(v)||0)*100) }
function hashStr(s) { let h=0; for(let i=0;i<s.length;i++) h=((h<<5)-h+s.charCodeAt(i))|0; return Math.abs(h) }
function onSearch() { selectedEntity.value = '' }
function onFilter() { selectedEntity.value = '' }
function selectEntity(e) { selectedEntity.value = e.name; selectedEntityData.value = e; drawGraph() }

function dprCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  canvas.width = rect.width * dpr; canvas.height = rect.height * dpr
  const ctx = canvas.getContext('2d'); ctx.scale(dpr, dpr)
  return { ctx, w: rect.width, h: rect.height }
}

function computeLayout(W, H) {
  const list = filteredEntities.value, map = new Map()
  const cx = W/2, cy = H/2, R = Math.min(W,H)*0.36
  list.forEach((e,i) => {
    const angle = (2*Math.PI*i)/Math.max(list.length,1) - Math.PI/2
    map.set(e.name, { ...e, x: cx+R*Math.cos(angle), y: cy+R*Math.sin(angle), r: Math.min(14+(e.trust_score||0)*12,30), color: TYPE_COLORS[e.type]||PALETTE[hashStr(e.name)%PALETTE.length] })
  })
  return map
}

function drawGraph() {
  const canvas = graphCanvas.value; if(!canvas) return
  const {ctx,w,h} = dprCanvas(canvas); ctx.clearRect(0,0,w,h)
  const nodes = computeLayout(w,h); nodeMap.value = nodes
  const selected = selectedEntity.value
  const neighborNames = new Set()
  graphEdges.value.forEach(e => { if(e.source===selected) neighborNames.add(e.target); if(e.target===selected) neighborNames.add(e.source) })
  neighborNames.add(selected)
  ctx.lineWidth = 1.5
  graphEdges.value.forEach(edge => {
    const s = nodes.get(edge.source), t = nodes.get(edge.target); if(!s||!t) return
    const isHL = selected && neighborNames.has(edge.source) && neighborNames.has(edge.target)
    ctx.strokeStyle = isHL ? 'rgba(255,143,171,0.7)' : 'rgba(160,142,150,0.25)'
    ctx.beginPath(); ctx.moveTo(s.x,s.y); ctx.lineTo(t.x,t.y); ctx.stroke()
    if(edge.relation && isHL) { const mx=(s.x+t.x)/2, my=(s.y+t.y)/2; ctx.fillStyle='rgba(75,59,68,0.7)'; ctx.font='10px system-ui,sans-serif'; ctx.textAlign='center'; ctx.fillText(edge.relation,mx,my-5) }
  })
  nodes.forEach((n,name) => {
    const isSelected = name===selected, isNeighbor = neighborNames.has(name)&&!isSelected
    const alpha = selected && !neighborNames.has(name) ? 0.25 : 1
    ctx.globalAlpha = alpha
    if(isSelected){ctx.shadowBlur=16;ctx.shadowColor=n.color+'AA'} else if(isNeighbor){ctx.shadowBlur=8;ctx.shadowColor=n.color+'66'} else{ctx.shadowBlur=3;ctx.shadowColor=n.color+'33'}
    ctx.fillStyle=n.color; ctx.beginPath(); ctx.arc(n.x,n.y,n.r,0,2*Math.PI); ctx.fill()
    ctx.shadowBlur=0; ctx.strokeStyle=isSelected?'#fff':'rgba(255,255,255,0.6)'; ctx.lineWidth=isSelected?2.5:1.5; ctx.stroke()
    ctx.fillStyle='#4b3b44'; ctx.font=(isSelected?'700':'500')+' 11px system-ui,sans-serif'; ctx.textAlign='center'
    ctx.fillText(n.name.length>8?n.name.slice(0,8)+'...':n.name, n.x, n.y+n.r+13)
    ctx.globalAlpha=1
  })
}

function getCanvasPos(e) { const r=graphCanvas.value.getBoundingClientRect(); return {x:e.clientX-r.left,y:e.clientY-r.top} }
function findNodeAt(x,y) { for(const[name,n] of nodeMap.value){const dx=x-n.x,dy=y-n.y; if(dx*dx+dy*dy<=(n.r+4)*(n.r+4)) return {name,...n}} return null }
function onCanvasMouseDown(e) { const h=findNodeAt(getCanvasPos(e).x,getCanvasPos(e).y); if(h){dragNode=h.name;dragOffset={x:getCanvasPos(e).x-h.x,y:getCanvasPos(e).y-h.y}} }
function onCanvasMouseMove(e) { if(!dragNode)return; const pos=getCanvasPos(e), node=nodeMap.value.get(dragNode); if(!node)return; const c=graphCanvas.value.getBoundingClientRect(); node.x=Math.max(node.r,Math.min(c.width-node.r,pos.x-dragOffset.x)); node.y=Math.max(node.r,Math.min(c.height-node.r,pos.y-dragOffset.y)); drawGraph() }
function onCanvasMouseUp() { dragNode=null }
function onCanvasClick(e) { const h=findNodeAt(getCanvasPos(e).x,getCanvasPos(e).y); if(h){const ent=entities.value.find(en=>en.name===h.name); if(ent)selectEntity(ent)} else {selectedEntity.value='';selectedEntityData.value=null;drawGraph()} }

async function load() {
  loading.value=true
  try {
    const agentId=window.__selectedAgentId||''
    if(!agentId){entities.value=[];graphEdges.value=[];return}
    const [entRes,graphRes]=await Promise.all([adminApi.memoryEntities(agentId),adminApi.memoryEntityGraph(agentId)])
    entities.value=entRes.data?.entities||[]; graphEdges.value=graphRes.data?.edges||[]
    const types=new Set(entities.value.map(e=>e.type).filter(Boolean)); typeOptions.value=Array.from(types).sort()
    if(graphCanvas.value) nextTick(drawGraph)
  } catch(e) { toast(e.msg||'\u52a0\u8f7d\u5b9e\u4f53\u8c31\u8c31\u5931\u8d25','error') }
  finally { loading.value=false }
}

onMounted(()=>{ const c=graphCanvas.value; if(c){c.addEventListener('mousedown',onCanvasMouseDown);c.addEventListener('mousemove',onCanvasMouseMove);c.addEventListener('mouseup',onCanvasMouseUp);c.addEventListener('click',onCanvasClick)} window.addEventListener('resize',()=>{if(graphCanvas.value)nextTick(drawGraph)}) ; load() })
onUnmounted(()=>{ const c=graphCanvas.value; if(c){c.removeEventListener('mousedown',onCanvasMouseDown);c.removeEventListener('mousemove',onCanvasMouseMove);c.removeEventListener('mouseup',onCanvasMouseUp);c.removeEventListener('click',onCanvasClick)} })
</script>
<style scoped>
.toolbar { display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; align-items: center; }
.search-input { border: 1.5px solid var(--border); border-radius: 10px; padding: 8px 14px; font-size: 13px; outline: none; background: #fff; min-width: 240px; }
.search-input:focus { border-color: var(--primary); }
.layout { display: grid; grid-template-columns: 320px 1fr; gap: 16px; min-height: 500px; }
@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }
.entity-panel, .graph-panel { border: 1.5px solid var(--border); border-radius: var(--radius-md); background: var(--surface); display: flex; flex-direction: column; overflow: hidden; }
.panel-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--border); background: var(--bg-soft, #F8FAFD); }
.panel-title { font-size: 14px; font-weight: 700; }
.panel-count { font-size: 12px; color: var(--text-sub); }
.panel-hint { font-size: 11px; color: var(--text-sub); }
.entity-list { flex: 1; overflow-y: auto; padding: 8px; }
.entity-item { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 10px; cursor: pointer; transition: all 0.2s; margin-bottom: 4px; }
.entity-item:hover { background: var(--bg-soft, #F0F4F8); }
.entity-item.active { background: var(--primary-soft, #F0F4FF); border: 1px solid var(--primary); }
.e-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.e-info { flex: 1; min-width: 0; }
.e-name { font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.e-meta { display: flex; align-items: center; gap: 8px; margin-top: 3px; }
.e-type { font-size: 10px; padding: 2px 8px; border-radius: var(--radius-pill); font-weight: 600; }
.e-trust { font-size: 11px; color: var(--text-sub); }
.graph-panel { position: relative; }
.canvas-wrap { flex: 1; min-height: 400px; position: relative; background: linear-gradient(135deg, #FAFBFC 0%, #F0F4F8 100%); }
.graph-canvas { width: 100%; height: 100%; display: block; cursor: crosshair; }
.detail-panel { border-top: 1px solid var(--border); padding: 16px; background: var(--bg-soft, #F8FAFD); }
.detail-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.detail-name { font-size: 15px; font-weight: 700; }
.detail-row { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.detail-label { font-size: 12px; color: var(--text-sub); font-weight: 600; min-width: 60px; }
.trust-bar-wrap { display: flex; align-items: center; gap: 10px; flex: 1; }
.trust-bar { flex: 1; height: 8px; border-radius: var(--radius-pill); background: var(--primary-soft); overflow: hidden; }
.trust-fill { height: 100%; border-radius: var(--radius-pill); background: linear-gradient(90deg, #FF8FAB, #F9A8D4); transition: width 0.4s; }
.trust-num { font-size: 12px; color: var(--text-sub); min-width: 36px; text-align: right; }
.detail-edges { display: flex; flex-direction: column; gap: 6px; margin-top: 10px; }
.edge-tag { display: flex; align-items: center; gap: 8px; padding: 6px 10px; background: #fff; border: 1px solid var(--border); border-radius: 8px; font-size: 12px; }
.edge-label { font-weight: 600; color: var(--primary); min-width: 60px; }
.edge-target { flex: 1; font-weight: 500; }
.edge-weight { font-size: 11px; color: var(--text-sub); }
.empty-state { text-align: center; padding: 40px 20px; color: var(--text-sub); }
.empty-icon { font-size: 32px; margin-bottom: 8px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: var(--radius-pill); font-size: 11px; font-weight: 600; }
</style>
