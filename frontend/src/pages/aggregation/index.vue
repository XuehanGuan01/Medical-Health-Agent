<template>
  <div class="page-content agg-page">
    <!-- Back nav -->
    <div class="agg-head">
      <button class="agg-back" @click="$router.push('/settings')">
        <svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"/></svg>
      </button>
      <h1 class="agg-title">数据聚合</h1>
    </div>
    <p class="agg-desc">上传 Health Auto Export 导出的每周 JSON 文件</p>

    <!-- Upload zone -->
    <div
      class="card up-zone" :class="{ drag: dragging, up: uploading }"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <template v-if="!uploading">
        <div class="up-icon">📁</div>
        <div class="up-text">拖拽 JSON 文件到此处</div>
        <div class="up-or">或</div>
        <label class="up-btn">
          选择文件
          <input type="file" accept=".json" @change="onSelect" hidden />
        </label>
        <div class="up-limit">仅支持 .json · 单周 &lt; 200KB</div>
      </template>
      <template v-else>
        <div class="up-prog">
          <span class="dot-pulse"></span>
          正在导入 {{ upName }}…
        </div>
      </template>
    </div>

    <!-- Result -->
    <div v-if="result" class="card res-card" :class="result.error ? 'res-err' : 'res-ok'">
      <div class="res-title">{{ result.error ? '❌ 导入失败' : '✅ 导入成功' }}</div>
      <div v-if="result.error" class="res-msg">{{ result.error }}</div>
      <div v-else class="res-grid">
        <div><span>文件</span><span>{{ result.filename }}</span></div>
        <div><span>周期</span><span>{{ result.week_start }} ~ {{ result.week_end }}</span></div>
        <div><span>指标数</span><span>{{ result.metrics_count }}</span></div>
        <div><span>入库数据</span><span>{{ result.data_points_inserted?.toLocaleString() }} 条</span></div>
        <div><span>聚合天数</span><span>{{ result.days_aggregated }} 天</span></div>
      </div>
    </div>

    <!-- Uploaded files -->
    <div class="sec">
      <div class="sec-title">已导入的周文件</div>
      <div v-if="fileList.length" class="file-list">
        <div v-for="f in fileList" :key="f.filename" class="card file-item">
          <div class="fi-left">
            <span class="fi-icon">✅</span>
            <div>
              <div class="fi-name">{{ f.filename }}</div>
              <div class="fi-meta">{{ fmtSize(f.size_bytes) }} · {{ fmtTime(f.imported_at) }}</div>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="card" style="padding:20px;text-align:center;color:var(--muted);font-size:13px;">暂无已导入文件</div>
    </div>

    <!-- Tips -->
    <div class="card tips">
      <div class="tips-title">💡 提示</div>
      <ul>
        <li>请确保每周日统一导出上一周的数据（周一 ~ 周日）</li>
        <li>同名文件不可重复导入，避免数据重复</li>
        <li>上传后系统会自动执行日聚合，看板即刻更新</li>
        <li>导出软件：Health Auto Export（App Store）</li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, inject } from 'vue'
import { uploadJSON, getUploadList } from '../../api/health.js'

const toast = inject('toast')

const dragging = ref(false)
const uploading = ref(false)
const upName = ref('')
const result = ref(null)
const fileList = ref([])

const doUpload = async (file) => {
  if (!file.name.endsWith('.json')) { toast('仅支持 .json 文件'); return }
  uploading.value = true; upName.value = file.name; result.value = null
  try {
    const r = await uploadJSON(file)
    result.value = r
    toast(`导入完成：${r.data_points_inserted} 条，${r.days_aggregated} 天聚合`)
    loadFiles()
  } catch (e) {
    result.value = { error: e.message }
    const m = e.message || ''
    if (m.includes('已导入过')) toast('该文件已导入过')
    else if (m.includes('缺少')) toast('格式错误：' + m)
    else toast('导入失败：' + m)
  } finally { uploading.value = false; upName.value = '' }
}

const onSelect = (e) => { const f = e.target.files?.[0]; if (f) doUpload(f); e.target.value = '' }
const onDrop = (e) => { dragging.value = false; const f = e.dataTransfer?.files?.[0]; if (f) doUpload(f) }

const loadFiles = async () => {
  try { const d = await getUploadList(); fileList.value = d.files || [] } catch {}
}

const fmtSize = (b) => b ? (b < 1024 ? b + ' B' : (b/1024).toFixed(1) + ' KB') : '--'
const fmtTime = (t) => { try { return new Date(t).toLocaleString('zh-CN') } catch { return t } }

onMounted(() => loadFiles())
</script>

<style scoped>
.agg-page { padding: 0 16px 24px; }

.agg-head { display: flex; align-items: center; gap: 10px; padding: 10px 0 4px; }
.agg-back { width: 32px; height: 32px; border-radius: 50%; background: var(--fg-soft); border: 0; display: grid; place-items: center; cursor: pointer; color: var(--fg); flex-shrink: 0; }
.agg-back svg { width: 16px; height: 16px; stroke: currentColor; fill: none; stroke-width: 2; }
.agg-title { font-family: var(--font-display); font-size: var(--fs-h1); font-weight: 600; letter-spacing: -0.025em; }
.agg-desc { font-size: 13px; color: var(--muted); margin: 4px 0 16px; padding-left: 42px; }

/* Upload zone */
.up-zone { padding: 36px 20px; text-align: center; margin-bottom: 16px; border-style: dashed; border-width: 2px; transition: all 0.2s; }
.up-zone.drag { border-color: var(--accent); background: var(--accent-soft); }
.up-zone.up { opacity: 0.7; pointer-events: none; }
.up-icon { font-size: 40px; margin-bottom: 12px; }
.up-text { font-size: 15px; font-weight: 500; margin-bottom: 8px; }
.up-or { font-size: 12px; color: var(--muted); margin-bottom: 12px; }
.up-btn { display: inline-block; padding: 10px 24px; border-radius: var(--radius-pill); background: var(--accent); color: #fff; font-size: 14px; cursor: pointer; font-weight: 500; margin-bottom: 12px; }
.up-limit { font-size: 11px; color: var(--muted); }
.up-prog { display: flex; align-items: center; justify-content: center; gap: 10px; font-size: 14px; }

.dot-pulse { display: inline-block; width: 8px; height: 8px; background: var(--accent); border-radius: 50%; animation: pulse 1.2s infinite; }
@keyframes pulse { 0%,100%{ opacity:0.3; } 50%{ opacity:1; } }

/* Result */
.res-card { padding: 16px; margin-bottom: 16px; }
.res-ok { border-color: #22c55e; }
.res-err { border-color: #ef4444; }
.res-title { font-weight: 600; font-size: 14px; margin-bottom: 8px; }
.res-msg { color: #ef4444; font-size: 13px; }
.res-grid { display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
.res-grid div { display: flex; justify-content: space-between; }
.res-grid div span:first-child { color: var(--muted); }
.res-grid div span:last-child { font-family: var(--font-mono); font-size: 12px; }

/* File list */
.sec { margin-bottom: 20px; }
.sec-title { font-family: var(--font-display); font-size: var(--fs-h3); font-weight: 600; margin-bottom: 8px; padding: 0 4px; letter-spacing: -0.01em; }
.file-list { display: flex; flex-direction: column; gap: 6px; }
.file-item { padding: 12px 14px; display: flex; align-items: center; }
.fi-left { display: flex; align-items: center; gap: 10px; }
.fi-icon { font-size: 18px; flex-shrink: 0; }
.fi-name { font-size: 13px; font-family: var(--font-mono); word-break: break-all; }
.fi-meta { font-size: 11px; color: var(--muted); margin-top: 2px; }

/* Tips */
.tips { padding: 16px; }
.tips-title { font-weight: 600; font-size: 14px; margin-bottom: 8px; }
.tips ul { padding-left: 18px; font-size: 12px; color: var(--muted); line-height: 1.7; }
</style>
