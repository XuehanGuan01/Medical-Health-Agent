<template>
  <div class="page-content set-page">
    <div class="set-head">
      <h1 class="set-title">设置</h1>
    </div>

    <!-- 外观 -->
    <div class="sec">
      <span class="sec-label">外观</span>
      <div class="card set-row" @click="toggleDark">
        <div class="sr-left">
          <span class="sr-icon">{{ isDark ? '🌙' : '☀️' }}</span>
          <span class="sr-text">深色模式</span>
        </div>
        <div class="toggle" :class="{ on: isDark }"><div class="tog-knob"></div></div>
      </div>
    </div>

    <!-- 模型 -->
    <div class="sec">
      <span class="sec-label">模型</span>

      <!-- 当前模型 -->
      <div class="card set-row" @click="showPicker = true">
        <div class="sr-left">
          <span class="sr-icon">🤖</span>
          <div class="model-info">
            <span class="sr-text">当前模型</span>
            <span class="model-desc">{{ currentDesc }}</span>
          </div>
        </div>
        <div class="sr-right">
          <span class="model-name">{{ currentModel }}</span>
          <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
        </div>
      </div>

      <!-- 测试连通性 -->
      <div class="card set-row" @click="handleTest">
        <div class="sr-left">
          <span class="sr-icon">📡</span>
          <span class="sr-text">连通性测试</span>
        </div>
        <div class="sr-right">
          <span class="sr-hint" :style="{ color: testColor }">{{ testText }}</span>
          <span v-if="testLatency" class="sr-val sm">{{ testLatency }}ms</span>
        </div>
      </div>

      <!-- 切换历史 -->
      <div class="card set-row" v-if="history.length" @click="showHistory = !showHistory">
        <div class="sr-left">
          <span class="sr-icon">🕐</span>
          <span class="sr-text">切换历史</span>
        </div>
        <div class="sr-right">
          <span class="sr-hint">{{ history.length }} 条记录</span>
          <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
               :style="{ transform: showHistory ? 'rotate(90deg)' : '' }"><polyline points="9 18 15 12 9 6"/></svg>
        </div>
      </div>
      <div v-if="showHistory && history.length" class="card history-list">
        <div v-for="(h, i) in history" :key="i" class="history-item">
          <span class="h-from">{{ h.from }}</span>
          <span class="h-arrow">→</span>
          <span class="h-to">{{ h.to }}</span>
          <span class="h-time">{{ formatTime(h.timestamp) }}</span>
        </div>
      </div>
    </div>

    <!-- 数据 -->
    <div class="sec">
      <span class="sec-label">数据</span>

      <div class="card set-row" @click="$router.push('/aggregation')">
        <div class="sr-left">
          <span class="sr-icon">📁</span>
          <span class="sr-text">数据聚合</span>
        </div>
        <div class="sr-right">
          <span class="sr-hint">上传 JSON · 周聚合</span>
          <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
        </div>
      </div>

      <div class="card set-row" @click="checkHealth">
        <div class="sr-left">
          <span class="sr-icon">📡</span>
          <span class="sr-text">同步状态</span>
        </div>
        <div class="sr-right">
          <span class="sr-hint" :style="{ color: syncColor }">{{ syncText }}</span>
        </div>
      </div>

      <div class="card set-row" v-if="totalSamples > 0" @click="$router.push('/data-calendar')">
        <div class="sr-left">
          <span class="sr-icon">📊</span>
          <span class="sr-text">数据总量</span>
        </div>
        <div class="sr-right">
          <span class="sr-val">{{ totalSamples.toLocaleString() }} 条</span>
          <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
        </div>
      </div>

      <div class="card set-row" v-if="lastSync">
        <div class="sr-left">
          <span class="sr-icon">🕐</span>
          <span class="sr-text">最近同步</span>
        </div>
        <div class="sr-right">
          <span class="sr-val sm">{{ lastSync }}</span>
        </div>
      </div>
    </div>

    <!-- API -->
    <div class="sec">
      <span class="sec-label">API 配置</span>
      <div class="card" style="padding:14px;">
        <div class="api-row">
          <input class="api-inp" v-model="apiUrl" placeholder="留空使用代理" />
          <button class="api-btn" @click="saveApi">保存</button>
        </div>
        <div class="api-hint">留空使用 Vite 代理。远程访问请填完整地址。</div>
      </div>
    </div>

    <!-- 关于 -->
    <div class="sec">
      <span class="sec-label">关于</span>
      <div class="card" style="padding:16px;">
        <div class="ab-row"><span>AI 个人健康管家</span><span class="ab-meta">v4.0 · Neutral Modern</span></div>
        <div class="ab-row"><span>技术栈</span><span class="ab-meta">Vue 3 · FastAPI · LangGraph</span></div>
        <div class="ab-row"><span>数据源</span><span class="ab-meta">Apple Health · Health Auto Export</span></div>
      </div>
    </div>

    <!-- 模型选择弹窗 -->
    <teleport to="body">
      <div v-if="showPicker" class="picker-overlay" @click.self="showPicker = false">
        <div class="picker-sheet">
          <div class="picker-header">
            <span class="picker-title">选择模型</span>
            <button class="picker-close" @click="showPicker = false">✕</button>
          </div>
          <div class="picker-body">
            <div v-for="(models, series) in groupedModels" :key="series" class="picker-group">
              <span class="picker-group-label">{{ seriesLabels[series] || series }}</span>
              <div
                v-for="m in models"
                :key="m.key"
                class="picker-item"
                :class="{ active: m.key === selectedProvider, disabled: !m.available }"
                @click="handleSelect(m)"
              >
                <div class="pi-left">
                  <span class="pi-name">{{ m.model_name }}</span>
                  <span class="pi-desc">{{ m.desc }}</span>
                </div>
                <div class="pi-right">
                  <span v-if="!m.available" class="pi-badge warn">无 Key</span>
                  <span v-if="m.key === selectedProvider" class="pi-check">✓</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { inject } from 'vue'
import { getSyncStatus } from '../../api/health.js'
import { setBaseURL } from '../../api/request.js'
import { getModels, switchModel, testModel, getModelHistory } from '../../api/settings.js'

const isDark = inject('darkMode')
const toggleDark = inject('toggleDark')
const toast = inject('toast')

// ── 数据同步 ──
const syncText = ref('检测中…')
const syncColor = ref('var(--muted)')
const totalSamples = ref(0)
const lastSync = ref(null)
const apiUrl = ref(localStorage.getItem('baseURL') || '')

const checkHealth = async () => {
  syncText.value = '检测中…'
  syncColor.value = 'var(--muted)'
  try {
    const s = await getSyncStatus()
    totalSamples.value = s.database?.total_raw_samples || 0
    if (s.last_sync?.time) lastSync.value = new Date(s.last_sync.time).toLocaleString('zh-CN')
    syncText.value = '🟢 已连接'
    syncColor.value = '#22c55e'
  } catch {
    syncText.value = '🔴 未连接'
    syncColor.value = '#ef4444'
  }
}

const saveApi = () => {
  setBaseURL(apiUrl.value)
  toast('已保存')
  checkHealth()
}

// ── 模型管理 ──
const currentModel = ref('')
const currentDesc = ref('加载中…')
const selectedProvider = ref('')
const groupedModels = ref({})
const showPicker = ref(false)
const showHistory = ref(false)
const history = ref([])

// 测试状态
const testText = ref('点击测试')
const testColor = ref('var(--muted)')
const testLatency = ref(null)

const seriesLabels = {
  qwen: 'Qwen · 通义千问',
  deepseek: 'DeepSeek · 深度求索',
  kimi: 'Kimi · 月之暗面',
  glm: 'GLM · 智谱',
}

const loadModels = async () => {
  try {
    const data = await getModels()
    currentModel.value = data.current
    selectedProvider.value = data.current
    groupedModels.value = data.grouped

    // 从分组数据中提取当前模型描述
    for (const models of Object.values(data.grouped)) {
      const found = models.find(m => m.key === data.current)
      if (found) {
        currentDesc.value = found.desc
        break
      }
    }
  } catch {
    currentDesc.value = '加载失败'
  }
}

const loadHistory = async () => {
  try {
    const data = await getModelHistory()
    history.value = (data.history || []).reverse().slice(0, 10)
  } catch { /* ignore */ }
}

const handleSelect = async (m) => {
  if (!m.available) {
    toast('该模型的 API Key 未配置')
    return
  }
  if (m.key === selectedProvider.value) {
    showPicker.value = false
    return
  }
  try {
    const res = await switchModel(m.key)
    selectedProvider.value = res.current
    currentModel.value = res.current
    currentDesc.value = res.desc
    showPicker.value = false
    toast(`已切换: ${res.previous} → ${res.current}`)
    loadHistory()
  } catch (e) {
    toast('切换失败: ' + (e.message || '未知错误'))
  }
}

const handleTest = async () => {
  testText.value = '测试中…'
  testColor.value = 'var(--muted)'
  testLatency.value = null
  try {
    const res = await testModel(currentModel.value)
    if (res.ok) {
      testText.value = '🟢 连通'
      testColor.value = '#22c55e'
      testLatency.value = Math.round(res.latency_ms)
    } else {
      testText.value = '🔴 失败'
      testColor.value = '#ef4444'
    }
  } catch {
    testText.value = '🔴 网络错误'
    testColor.value = '#ef4444'
  }
}

const formatTime = (ts) => {
  const d = new Date(ts * 1000)
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

onMounted(() => {
  checkHealth()
  loadModels()
  loadHistory()
})
</script>

<style scoped>
.set-page { padding: 0 12px 24px; }
.set-head { padding: 10px 4px 12px; }
.set-title { font-family: var(--font-display); font-size: var(--fs-h1); font-weight: 600; letter-spacing: -0.025em; }

.sec { margin-bottom: 20px; }
.sec-label { display: block; font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.06em; color: var(--muted); text-transform: uppercase; margin-bottom: 8px; padding: 0 4px; }

.set-row { display: flex; align-items: center; justify-content: space-between; padding: 14px; margin-bottom: 8px; cursor: pointer; transition: background 0.15s; }
.set-row:active { background: var(--fg-soft); }
.sr-left { display: flex; align-items: center; gap: 10px; }
.sr-icon { font-size: 20px; }
.sr-text { font-size: 14px; font-weight: 500; }
.sr-right { display: flex; align-items: center; gap: 8px; }
.sr-hint { font-size: 12px; color: var(--muted); }
.sr-val { font-family: var(--font-mono); font-size: 13px; }
.sr-val.sm { font-size: 11px; }
.chev { width: 16px; height: 16px; color: var(--muted); flex-shrink: 0; transition: transform 0.2s; }

.toggle { width: 48px; height: 28px; border-radius: 14px; background: var(--border); position: relative; transition: background 0.25s; flex-shrink: 0; }
.toggle.on { background: var(--accent); }
.tog-knob { position: absolute; top: 3px; left: 3px; width: 22px; height: 22px; border-radius: 50%; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.15); transition: transform 0.25s; }
.toggle.on .tog-knob { transform: translateX(20px); }

/* ── 模型信息 ── */
.model-info { display: flex; flex-direction: column; gap: 2px; }
.model-desc { font-size: 11px; color: var(--muted); }
.model-name { font-family: var(--font-mono); font-size: 12px; color: var(--accent); max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── 切换历史 ── */
.history-list { padding: 12px 14px; margin-bottom: 8px; }
.history-item { display: flex; align-items: center; gap: 6px; font-size: 12px; font-family: var(--font-mono); padding: 4px 0; }
.history-item + .history-item { border-top: 1px solid var(--border); }
.h-from { color: var(--muted); }
.h-arrow { color: var(--muted); font-size: 10px; }
.h-to { color: var(--accent); }
.h-time { margin-left: auto; color: var(--muted); font-size: 10px; }

/* ── API 配置 ── */
.api-row { display: flex; gap: 8px; margin-bottom: 6px; }
.api-inp { flex: 1; border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px 12px; font-size: 13px; font-family: var(--font-mono); background: var(--bg); color: var(--fg); outline: none; }
.api-inp:focus { border-color: var(--accent); }
.api-btn { padding: 8px 16px; border-radius: var(--radius-sm); border: 0; background: var(--accent); color: #fff; font-size: 13px; font-family: var(--font-body); cursor: pointer; }
.api-hint { font-size: 11px; color: var(--muted); padding-top: 4px; }

.ab-row { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; font-size: 14px; }
.ab-row + .ab-row { border-top: 1px solid var(--border); }
.ab-meta { font-size: var(--fs-meta); color: var(--muted); }

/* ── 模型选择弹窗 ── */
.picker-overlay {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0,0,0,0.4);
  display: flex; align-items: flex-end; justify-content: center;
  animation: fadeIn 0.2s;
}
.picker-sheet {
  width: 100%; max-width: 500px; max-height: 75vh;
  background: var(--surface); border-radius: 20px 20px 0 0;
  display: flex; flex-direction: column; overflow: hidden;
  animation: slideUp 0.25s ease-out;
}
.picker-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px 12px; border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.picker-title { font-size: 16px; font-weight: 600; }
.picker-close {
  width: 28px; height: 28px; border-radius: 50%;
  background: var(--fg-soft); border: 0; color: var(--muted);
  font-size: 14px; display: flex; align-items: center; justify-content: center;
  cursor: pointer;
}
.picker-body {
  flex: 1; overflow-y: auto; padding: 8px 16px 24px;
  -webkit-overflow-scrolling: touch;
}
.picker-body::-webkit-scrollbar { display: none; }

.picker-group { margin-bottom: 12px; }
.picker-group-label {
  display: block; font-family: var(--font-mono); font-size: 10px;
  letter-spacing: 0.06em; color: var(--muted); text-transform: uppercase;
  padding: 8px 4px 4px;
}

.picker-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px; border-radius: var(--radius-sm); cursor: pointer;
  transition: background 0.15s;
}
.picker-item:active { background: var(--fg-soft); }
.picker-item.active { background: var(--accent-soft); }
.picker-item.disabled { opacity: 0.45; cursor: not-allowed; }

.pi-left { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.pi-name { font-family: var(--font-mono); font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pi-desc { font-size: 11px; color: var(--muted); }

.pi-right { display: flex; align-items: center; gap: 6px; flex-shrink: 0; margin-left: 8px; }
.pi-badge {
  font-size: 10px; padding: 2px 6px; border-radius: 4px;
  font-family: var(--font-mono);
}
.pi-badge.warn { background: #fef3cd; color: #856404; }
.pi-check { color: var(--accent); font-size: 16px; font-weight: 700; }

@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
</style>
