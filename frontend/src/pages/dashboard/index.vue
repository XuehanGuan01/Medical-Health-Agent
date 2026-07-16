<template>
  <div class="page-content db-page">
    <!-- Sync status -->
    <div class="sync-bar" v-if="syncOk !== null">
      <span class="sync-dot" :class="syncOk ? 'ok' : 'err'"></span>
      <span>{{ syncOk ? '已同步' : '同步异常' }}</span>
      <span v-if="lastSync" class="sync-time">{{ lastSync }}</span>
      <span style="flex:1;"></span>
      <span class="sync-total">{{ totalSamples?.toLocaleString() || 0 }} 条数据</span>
    </div>

    <!-- View switcher -->
    <div class="view-row">
      <button v-for="v in ['day','week','month']" :key="v" class="view-chip" :class="{ active: view === v }" @click="view = v">{{ {day:'日',week:'周',month:'月'}[v] }}</button>
    </div>

    <!-- Metrics grid -->
    <div class="m-grid">
      <div v-for="m in cards" :key="m.key" class="card m-card">
        <div class="m-top">
          <span class="m-icon">{{ m.icon }}</span>
          <span class="m-name">{{ m.label }}</span>
        </div>
        <div class="m-value">{{ m.value ?? '--' }}</div>
        <div class="m-unit">{{ m.unit }}</div>
      </div>
    </div>

    <!-- Trend: Heart rate -->
    <div class="card chart-card" v-if="heartBars.length">
      <div class="chart-title">❤️ 心率趋势 (7日)</div>
      <div class="bar-row">
        <div v-for="(b,i) in heartBars" :key="i" class="bar-col">
          <span class="bar-num">{{ b.value ?? '--' }}</span>
          <div class="bar-track"><div class="bar-fill" :style="{ height: bpct(b.value, 40, 100) }"></div></div>
          <span class="bar-label">{{ b.date?.slice(5) }}</span>
        </div>
      </div>
      <div class="chart-tag" v-if="heartDir">{{ heartDir }}</div>
    </div>

    <!-- Trend: Steps -->
    <div class="card chart-card" v-if="stepBars.length">
      <div class="chart-title">👟 步数趋势 (7日)</div>
      <div class="bar-row">
        <div v-for="(b,i) in stepBars" :key="i" class="bar-col">
          <span class="bar-num">{{ b.value != null ? b.value.toLocaleString() : '--' }}</span>
          <div class="bar-track"><div class="bar-fill step" :style="{ height: bpct(b.value, 0, 15000) }"></div></div>
          <span class="bar-label">{{ b.date?.slice(5) }}</span>
        </div>
      </div>
      <div class="chart-tag" v-if="stepDir">{{ stepDir }}</div>
    </div>

    <!-- Empty -->
    <div v-if="syncOk === null" class="empty-state">
      <div class="empty-icon">📊</div>
      <div class="empty-title">数据收集中…</div>
      <div class="empty-hint">上传周数据后即可查看健康看板</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getSyncStatus, getTodayMetrics, getTrend } from '../../api/health.js'

const syncOk = ref(null)
const lastSync = ref(null)
const totalSamples = ref(0)
const view = ref('day')

const heartBars = ref([])
const stepBars = ref([])
const heartDir = ref('')
const stepDir = ref('')

const defs = [
  { key:'heart_rate', label:'心率', icon:'❤️', unit:'bpm' },
  { key:'resting_heart_rate', label:'静息心率', icon:'💓', unit:'bpm' },
  { key:'heart_rate_variability', label:'HRV', icon:'📈', unit:'ms' },
  { key:'step_count', label:'步数', icon:'👟', unit:'步' },
  { key:'active_energy', label:'活动能量', icon:'🔥', unit:'kJ' },
  { key:'basal_energy_burned', label:'基础代谢', icon:'⚡', unit:'kJ' },
  { key:'apple_exercise_time', label:'锻炼时长', icon:'🏃', unit:'min' },
  { key:'apple_stand_time', label:'站立时间', icon:'🧍', unit:'min' },
  { key:'sleep_analysis', label:'睡眠', icon:'😴', unit:'hr' },
  { key:'respiratory_rate', label:'呼吸频率', icon:'🫁', unit:'/min' },
  { key:'walking_running_distance', label:'步行距离', icon:'📏', unit:'km' },
  { key:'flights_climbed', label:'爬楼', icon:'🪜', unit:'层' },
  { key:'vo2_max', label:'VO₂ Max', icon:'🫀', unit:'ml/kg/min' },
  { key:'walking_speed', label:'步行速度', icon:'🚶', unit:'km/h' },
  { key:'time_in_daylight', label:'日照时间', icon:'☀️', unit:'min' },
  { key:'environmental_audio_exposure', label:'环境噪音', icon:'🔊', unit:'dB', alt:'environmental_audio_exposure' },
  { key:'physical_effort', label:'体力消耗', icon:'💪', unit:'MET' },
  { key:'cycling_distance', label:'骑行距离', icon:'🚴', unit:'km' },
]
const cards = ref(defs.map(d => ({ ...d, value: null })))

const bpct = (v, min, max) => v != null ? Math.max(2, Math.min(100, ((v-min)/(max-min))*100)) + '%' : '0%'

const td = (dir, pct) => {
  const m = { rising:'↑ 上升', falling:'↓ 下降', stable:'→ 平稳' }
  const s = m[dir] || dir
  return pct != null ? `${s} ${Math.abs(pct).toFixed(1)}%` : s
}

onMounted(async () => {
  try {
    const s = await getSyncStatus()
    syncOk.value = true
    totalSamples.value = s.database?.total_raw_samples || 0
    if (s.last_sync?.time) lastSync.value = new Date(s.last_sync.time).toLocaleString('zh-CN')
  } catch { syncOk.value = null }

  try {
    const d = await getTodayMetrics()
    if (d?.metrics) {
      const map = {}
      for (const m of d.metrics) map[m.metric_type] = m
      cards.value = cards.value.map(c => {
        const m = map[c.alt || c.key]
        if (!m) return c
        let v = m.avg_value
        if (v != null && ['step_count','flights_climbed'].includes(c.key)) v = Math.round(v)
        else if (v != null) v = Number(v).toFixed(1)
        return { ...c, value: v }
      })
    }
  } catch {}

  try {
    const r = await getTrend('heart_rate', 7)
    if (r?.data_points) {
      heartBars.value = r.data_points.map(d => ({ date: d.date, value: d.value }))
      heartDir.value = td(r.trend_direction, r.change_pct)
    }
  } catch {}
  try {
    const r = await getTrend('step_count', 7)
    if (r?.data_points) {
      stepBars.value = r.data_points.map(d => ({ date: d.date, value: d.value }))
      stepDir.value = td(r.trend_direction, r.change_pct)
    }
  } catch {}
})
</script>

<style scoped>
.db-page { padding: 0 12px 12px; }

.sync-bar { display: flex; align-items: center; gap: 6px; padding: 10px 12px; margin-bottom: 10px; background: var(--surface); border-radius: var(--radius-sm); font-size: 12px; color: var(--muted); border: 1px solid var(--border); }
.sync-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.sync-dot.ok { background: #22c55e; } .sync-dot.err { background: #ef4444; }
.sync-total { font-family: var(--font-mono); font-size: 11px; color: var(--fg); }

.view-row { display: flex; gap: 6px; margin-bottom: 12px; }
.view-chip { padding: 6px 16px; border-radius: 999px; border: 1px solid var(--border); background: var(--surface); font-size: 12px; font-family: var(--font-body); color: var(--muted); cursor: pointer; }
.view-chip.active { background: var(--accent); border-color: var(--accent); color: #fff; }

.m-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px; }
.m-card { padding: 14px; }
.m-top { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }
.m-icon { font-size: 16px; }
.m-name { font-size: 12px; color: var(--muted); font-weight: 500; }
.m-value { font-family: var(--font-display); font-size: 22px; font-weight: 600; letter-spacing: -0.02em; }
.m-unit { font-size: 11px; color: var(--muted); margin-top: 2px; }

.chart-card { padding: 16px; margin-bottom: 12px; }
.chart-title { font-family: var(--font-display); font-size: 14px; font-weight: 600; margin-bottom: 12px; }
.chart-tag { font-size: 12px; color: var(--accent); margin-top: 8px; }
.bar-row { display: flex; align-items: flex-end; gap: 6px; height: 100px; }
.bar-col { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; justify-content: flex-end; }
.bar-num { font-size: 9px; color: var(--muted); margin-bottom: 2px; font-family: var(--font-mono); }
.bar-track { width: 100%; height: 64px; display: flex; align-items: flex-end; justify-content: center; }
.bar-fill { width: 70%; background: var(--accent); border-radius: 3px 3px 0 0; min-height: 2px; transition: height 0.4s; }
.bar-fill.step { background: #22c55e; }
.bar-label { font-size: 9px; color: var(--muted); margin-top: 2px; }

.empty-state { text-align: center; padding: 60px 20px; }
.empty-title { font-size: 16px; font-weight: 500; margin-bottom: 4px; }
.empty-hint { font-size: 13px; color: var(--muted); }
</style>
