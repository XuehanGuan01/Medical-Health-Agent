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

      <div class="card set-row" v-if="totalSamples > 0">
        <div class="sr-left">
          <span class="sr-icon">📊</span>
          <span class="sr-text">数据总量</span>
        </div>
        <div class="sr-right">
          <span class="sr-val">{{ totalSamples.toLocaleString() }} 条</span>
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
  </div>
</template>

<script setup>
import { ref, inject, onMounted } from 'vue'
import { getSyncStatus } from '../../api/health.js'
import { setBaseURL } from '../../api/request.js'

const isDark = inject('darkMode')
const toggleDark = inject('toggleDark')
const toast = inject('toast')

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

onMounted(() => checkHealth())
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
.chev { width: 16px; height: 16px; color: var(--muted); flex-shrink: 0; }

.toggle { width: 48px; height: 28px; border-radius: 14px; background: var(--border); position: relative; transition: background 0.25s; flex-shrink: 0; }
.toggle.on { background: var(--accent); }
.tog-knob { position: absolute; top: 3px; left: 3px; width: 22px; height: 22px; border-radius: 50%; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.15); transition: transform 0.25s; }
.toggle.on .tog-knob { transform: translateX(20px); }

.api-row { display: flex; gap: 8px; margin-bottom: 6px; }
.api-inp { flex: 1; border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px 12px; font-size: 13px; font-family: var(--font-mono); background: var(--bg); color: var(--fg); outline: none; }
.api-inp:focus { border-color: var(--accent); }
.api-btn { padding: 8px 16px; border-radius: var(--radius-sm); border: 0; background: var(--accent); color: #fff; font-size: 13px; font-family: var(--font-body); cursor: pointer; }
.api-hint { font-size: 11px; color: var(--muted); padding-top: 4px; }

.ab-row { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; font-size: 14px; }
.ab-row + .ab-row { border-top: 1px solid var(--border); }
.ab-meta { font-size: var(--fs-meta); color: var(--muted); }
</style>
