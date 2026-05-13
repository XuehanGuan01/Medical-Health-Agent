<template>
  <div class="dashboard-page">
    <div class="status-bar" v-if="healthStore.syncInfo">
      <span class="status-dot" :class="healthStore.syncInfo.last_sync ? 'online' : 'offline'"></span>
      <span class="status-text" v-if="healthStore.syncInfo.last_sync">
        Last sync: {{ healthStore.syncInfo.last_sync.time?.slice(11, 19) }}
        | {{ (healthStore.syncInfo.database?.total_raw_samples || 0).toLocaleString() }} records
      </span>
      <span class="status-text" v-else>No sync data</span>
    </div>

    <!-- 指标卡片 -->
    <div class="section-header">
      <span class="section-title">Today's Data — {{ todayDate }}</span>
    </div>
    <div class="cards-grid">
      <div class="metric-card" v-for="m in healthStore.metrics" :key="m.metric_type">
        <span class="card-icon">{{ iconFor(m.metric_type) }}</span>
        <span class="card-label">{{ labelFor(m.metric_type) }}</span>
        <span class="card-value">{{ displayValue(m) }}</span>
        <span class="card-unit">{{ m.unit }}</span>
        <span class="card-status" :class="statusClass(m)">{{ statusText(m) }}</span>
      </div>
    </div>

    <!-- 趋势图 -->
    <div class="section" v-for="t in trendMetrics" :key="t.metric">
      <span class="section-title">{{ labelFor(t.metric) }} — Last 4 Weeks</span>

      <!-- 有数据 -->
      <template v-if="healthStore.trends[t.metric] && !healthStore.trends[t.metric].error">
        <svg class="line-chart" :viewBox="'0 0 ' + chartW + ' ' + chartH" preserveAspectRatio="none">
          <polyline :points="linePoints(t.metric)" fill="none" stroke="#4A90D9" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
          <circle v-for="(p, i) in scatterPoints(t.metric)" :key="i" :cx="p.x" :cy="p.y" r="4" fill="#fff" stroke="#4A90D9" stroke-width="2.5" />
        </svg>
        <!-- x轴标签 -->
        <div class="chart-x-labels">
          <span v-for="(w, i) in healthStore.trends[t.metric].weeks_data" :key="i" class="x-label">{{ w.week_start?.slice(5) }}</span>
        </div>
        <span class="trend-text">
          {{ healthStore.trends[t.metric].trend_direction === 'rising' ? '↑ Rising' : healthStore.trends[t.metric].trend_direction === 'falling' ? '↓ Falling' : '→ Stable' }}
          <template v-if="healthStore.trends[t.metric].change_pct !== undefined">
            ({{ formatChange(healthStore.trends[t.metric].change_pct) }})
          </template>
          <template v-if="healthStore.trends[t.metric].overall_mean">
            | avg: {{ healthStore.trends[t.metric].overall_mean.toFixed(1) }}
          </template>
        </span>
      </template>

      <!-- 加载中 / 无数据 -->
      <div class="chart-box" v-else>
        <span class="no-data">Loading trend data...</span>
      </div>
    </div>

    <div v-if="!healthStore.loading && healthStore.metrics.length === 0" class="empty-state">
      <span class="empty-icon">📊</span>
      <span class="empty-text">No data collected yet. Please keep syncing.</span>
    </div>
    <div style="height: 20px"></div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useHealthStore } from '@/stores/health'

const healthStore = useHealthStore()
const todayDate = new Date().toISOString().slice(0, 10)

const trendMetrics = [
  { metric: 'heart_rate' }, { metric: 'step_count' }, { metric: 'active_energy' },
]
const cumulativeMetrics = new Set(['step_count', 'active_energy', 'basal_energy_burned',
  'apple_exercise_time', 'apple_stand_time', 'walking_running_distance', 'flights_climbed',
  'sleep_analysis', 'cycling_distance', 'handwashing', 'environmental_audio_exposure',
  'headphone_audio_exposure', 'time_in_daylight', 'mindful_minutes'])
const displayValue = (m) => {
  if (m.metric_type === 'sleep_analysis' && m.total_value != null) {
    return (m.total_value / 60).toFixed(1) + 'h'  // 分钟→小时
  }
  if (cumulativeMetrics.has(m.metric_type) && m.total_value != null) {
    return m.total_value.toFixed(0)
  }
  return m.avg_value?.toFixed(1) || '--'
}

const iconMap = {
  heart_rate: '❤️', resting_heart_rate: '💓', heart_rate_variability: '📈',
  step_count: '👣', active_energy: '🔥', basal_energy_burned: '⚡',
  apple_exercise_time: '🏃', apple_stand_time: '🧍', apple_stand_hour: '🕐',
  respiratory_rate: '🫁', walking_running_distance: '📏',
  walking_speed: '🚶', walking_step_length: '📐',
  walking_asymmetry_percentage: '⚖️', walking_double_support_percentage: '🦿',
  walking_heart_rate_average: '💗', flights_climbed: '🪜', physical_effort: '💪',
  environmental_audio_exposure: '🔊', headphone_audio_exposure: '🎧',
  time_in_daylight: '☀️', sleep_analysis: '💤', mindful_minutes: '🧘',
  handwashing: '🧼', vo2_max: '🫀', cardio_recovery: '💖',
  stair_speed_down: '🪜⬇', stair_speed_up: '🪜⬆',
  running_power: '🏃‍♂️⚡', running_speed: '🏃‍♂️💨',
  running_ground_contact_time: '👟', running_vertical_oscillation: '↕️',
  running_stride_length: '📏🏃', cycling_distance: '🚴',
  weight_body_mass: '⚖️', body_fat_percentage: '🧬', body_mass_index: '📊',
  height: '📏', six_minute_walking_test_distance: '🚶6min',
  blood_oxygen_saturation: '🩸', wrist_temperature: '🌡️',
}
const labelMap = {
  heart_rate: 'Heart Rate', resting_heart_rate: 'Resting HR',
  heart_rate_variability: 'HRV', step_count: 'Steps',
  active_energy: 'Active Energy', basal_energy_burned: 'Basal Energy',
  apple_exercise_time: 'Exercise', apple_stand_time: 'Stand Time',
  apple_stand_hour: 'Stand Hours', respiratory_rate: 'Respiratory',
  walking_running_distance: 'Distance', walking_speed: 'Walk Speed',
  walking_step_length: 'Step Length', walking_asymmetry_percentage: 'Asymmetry',
  walking_double_support_percentage: 'Dbl Support',
  walking_heart_rate_average: 'Walk HR Avg', flights_climbed: 'Flights',
  physical_effort: 'Effort', environmental_audio_exposure: 'Env Noise',
  headphone_audio_exposure: 'HP Noise', time_in_daylight: 'Daylight',
  sleep_analysis: 'Sleep', mindful_minutes: 'Mindful', handwashing: 'Handwash',
  vo2_max: 'VO2 Max', cardio_recovery: 'Cardio Rec',
  stair_speed_down: 'Stair Down', stair_speed_up: 'Stair Up',
  running_power: 'Run Power', running_speed: 'Run Speed',
  running_ground_contact_time: 'Grd Contact',
  running_vertical_oscillation: 'Vert Osc', running_stride_length: 'Run Stride',
  cycling_distance: 'Cycling', weight_body_mass: 'Weight',
  body_fat_percentage: 'Body Fat', body_mass_index: 'BMI', height: 'Height',
  six_minute_walking_test_distance: '6min Walk',
  blood_oxygen_saturation: 'SpO2', wrist_temperature: 'Wrist Temp',
}
const iconFor = (m) => iconMap[m] || '📊'
const labelFor = (m) => labelMap[m] || m.replace(/_/g, ' ')
const formatChange = (v) => (v > 0 ? '+' : '') + v.toFixed(1) + '%'

const statusClass = (m) => {
  const b = healthStore.baseline[m.metric_type]
  if (!b?.mean || !b?.std || !b.std) return ''
  const dev = (m.avg_value - b.mean) / b.std
  if (dev > 1.5) return 'high'
  if (dev < -1.5) return 'low'
  return 'normal'
}
const statusText = (m) => {
  const b = healthStore.baseline[m.metric_type]
  if (!b?.mean || !b?.std || !b.std) return '--'
  const dev = (m.avg_value - b.mean) / b.std
  if (dev > 1.5) return 'High'
  if (dev < -1.5) return 'Low'
  return 'OK'
}
const chartW = 320
const chartH = 100
const padX = 20
const padY = 15

const linePoints = (metric) => {
  const pts = scatterPoints(metric)
  return pts.map(p => `${p.x},${p.y}`).join(' ')
}

const scatterPoints = (metric) => {
  const data = healthStore.trends[metric]?.weeks_data || []
  if (!data.length) return []
  const vals = data.map(w => w.avg).filter(v => v != null)
  const vMin = Math.min(...vals, 1) * 0.9
  const vMax = Math.max(...vals, 1) * 1.1
  const range = vMax - vMin || 1
  const w = (chartW - padX * 2) / Math.max(data.length - 1, 1)
  return data.map((d, i) => ({
    x: padX + i * w,
    y: chartH - padY - ((d.avg ?? vMin) - vMin) / range * (chartH - padY * 2),
  }))
}

onMounted(async () => {
  await healthStore.loadAll()
  trendMetrics.forEach(t => healthStore.loadTrend(t.metric))
})
</script>

<style scoped>
.dashboard-page {
  height: calc(100vh - 56px);
  overflow-y: auto;
  padding: 12px;
  background: #f0f2f5;
  -webkit-overflow-scrolling: touch;
}
.status-bar { display: flex; align-items: center; padding: 10px 14px; background: #fff; border-radius: 10px; margin-bottom: 12px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; margin-right: 8px; display: inline-block; flex-shrink: 0; }
.status-dot.online { background: #2ecc71; }
.status-dot.offline { background: #e74c3c; }
.status-text { font-size: 12px; color: #666; }

.section-header { padding: 4px 0 8px; }
.section-header .section-title { font-size: 14px; font-weight: 600; color: #555; }

.cards-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-bottom: 16px; }
.metric-card { background: #fff; border-radius: 10px; padding: 12px 8px; text-align: center; }
.card-icon { font-size: 20px; }
.card-label { display: block; font-size: 11px; color: #999; margin: 2px 0; }
.card-value { display: block; font-size: 24px; font-weight: 700; color: #333; }
.card-unit { font-size: 11px; color: #bbb; display: block; }
.card-status { display: inline-block; font-size: 11px; margin-top: 2px; padding: 1px 6px; border-radius: 8px; }
.card-status.normal { color: #2ecc71; background: #e8f8ef; }
.card-status.high { color: #e67e22; background: #fef5ec; }
.card-status.low { color: #3498db; background: #ebf5fb; }

.section { background: #fff; border-radius: 12px; padding: 14px; margin-bottom: 12px; overflow: hidden; }
.section-title { font-size: 14px; font-weight: 600; margin-bottom: 10px; color: #333; display: block; }
.line-chart { width: 100%; height: 110px; }
.chart-x-labels { display: flex; justify-content: space-between; padding: 0 16px; margin-top: 2px; }
.x-label { font-size: 10px; color: #999; }
.trend-text { font-size: 12px; color: #666; display: block; margin-top: 4px; text-align: center; }
.chart-box { min-height: 60px; display: flex; align-items: center; justify-content: center; }
.no-data { font-size: 13px; color: #999; }
.empty-state { text-align: center; padding: 80px 20px; }
.empty-icon { font-size: 48px; }
.empty-text { display: block; font-size: 14px; color: #999; margin-top: 12px; }
</style>
