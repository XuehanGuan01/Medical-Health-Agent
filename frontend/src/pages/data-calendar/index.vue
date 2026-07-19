<template>
  <div class="page-content cal-page">
    <!-- Header -->
    <div class="cal-head">
      <button class="cal-back" @click="$router.push('/settings')">
        <svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"/></svg>
      </button>
      <h1 class="cal-title">数据日历</h1>
    </div>

    <!-- Month navigation -->
    <div class="cal-nav">
      <button class="cal-nav-btn" @click="prevMonth">
        <svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"/></svg>
      </button>
      <span class="cal-month-label">{{ monthLabel }}</span>
      <button class="cal-nav-btn" @click="nextMonth">
        <svg viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"/></svg>
      </button>
    </div>

    <!-- Calendar grid -->
    <div class="card cal-card">
      <div class="cal-weekdays">
        <span v-for="w in weekdays" :key="w">{{ w }}</span>
      </div>
      <div class="cal-grid">
        <div
          v-for="(cell, i) in calendarCells"
          :key="i"
          class="cal-cell"
          :class="{
            empty: !cell.day,
            today: cell.isToday,
            selected: cell.dateStr === selectedDate,
            'has-data': cell.hasData
          }"
          @click="cell.day && selectDate(cell.dateStr)"
        >
          <span v-if="cell.day" class="cal-day-num">{{ cell.day }}</span>
          <span v-if="cell.hasData" class="cal-dot"></span>
        </div>
      </div>
    </div>

    <!-- Selected date detail -->
    <div v-if="selectedDate" class="detail-section">
      <div class="detail-header">
        <span class="detail-date">{{ selectedDate }}</span>
        <span class="detail-weekday">{{ selectedWeekday }}</span>
      </div>

      <div v-if="selectedMetrics" class="metrics-grid">
        <!-- Heart Rate -->
        <div v-if="selectedMetrics.heart_rate" class="card metric-card">
          <div class="mc-icon">❤️</div>
          <div class="mc-label">心率</div>
          <div class="mc-value" style="color: #ef4444;">{{ formatVal(selectedMetrics.heart_rate.avg) }}</div>
          <div class="mc-unit">bpm</div>
        </div>

        <!-- Resting Heart Rate -->
        <div v-if="selectedMetrics.resting_heart_rate" class="card metric-card">
          <div class="mc-icon">💓</div>
          <div class="mc-label">静息心率</div>
          <div class="mc-value" style="color: #ef4444;">{{ formatVal(selectedMetrics.resting_heart_rate.avg) }}</div>
          <div class="mc-unit">bpm</div>
        </div>

        <!-- HRV -->
        <div v-if="selectedMetrics.heart_rate_variability" class="card metric-card">
          <div class="mc-icon">📈</div>
          <div class="mc-label">心率变异性</div>
          <div class="mc-value" style="color: #8b5cf6;">{{ formatVal(selectedMetrics.heart_rate_variability.avg) }}</div>
          <div class="mc-unit">ms</div>
        </div>

        <!-- Steps -->
        <div v-if="selectedMetrics.step_count" class="card metric-card">
          <div class="mc-icon">👟</div>
          <div class="mc-label">步数</div>
          <div class="mc-value" style="color: #22c55e;">{{ formatInt(selectedMetrics.step_count.total) }}</div>
          <div class="mc-unit">步</div>
        </div>

        <!-- Active Energy -->
        <div v-if="selectedMetrics.active_energy" class="card metric-card">
          <div class="mc-icon">🔥</div>
          <div class="mc-label">活动能量</div>
          <div class="mc-value" style="color: #eab308;">{{ formatVal(selectedMetrics.active_energy.total) }}</div>
          <div class="mc-unit">kcal</div>
        </div>

        <!-- Sleep -->
        <div v-if="selectedMetrics.sleep_analysis" class="card metric-card">
          <div class="mc-icon">😴</div>
          <div class="mc-label">睡眠</div>
          <div class="mc-value" style="color: #8b5cf6;">{{ formatHours(selectedMetrics.sleep_analysis.total) }}</div>
          <div class="mc-unit">小时</div>
        </div>

        <!-- Exercise Time -->
        <div v-if="selectedMetrics.apple_exercise_time" class="card metric-card">
          <div class="mc-icon">⏱️</div>
          <div class="mc-label">运动时长</div>
          <div class="mc-value" style="color: #22c55e;">{{ formatVal(selectedMetrics.apple_exercise_time.total) }}</div>
          <div class="mc-unit">分钟</div>
        </div>

        <!-- Distance -->
        <div v-if="selectedMetrics.walking_running_distance" class="card metric-card">
          <div class="mc-icon">🏃</div>
          <div class="mc-label">步行距离</div>
          <div class="mc-value" style="color: #22c55e;">{{ formatVal(selectedMetrics.walking_running_distance.total) }}</div>
          <div class="mc-unit">公里</div>
        </div>

        <!-- Flights -->
        <div v-if="selectedMetrics.flights_climbed" class="card metric-card">
          <div class="mc-icon">🪜</div>
          <div class="mc-label">爬楼</div>
          <div class="mc-value" style="color: #eab308;">{{ formatVal(selectedMetrics.flights_climbed.total) }}</div>
          <div class="mc-unit">层</div>
        </div>

        <!-- VO2 Max -->
        <div v-if="selectedMetrics.vo2_max" class="card metric-card">
          <div class="mc-icon">🫁</div>
          <div class="mc-label">最大摄氧量</div>
          <div class="mc-value" style="color: #22c55e;">{{ formatVal(selectedMetrics.vo2_max.avg) }}</div>
          <div class="mc-unit">ml/kg/min</div>
        </div>

        <!-- Respiratory Rate -->
        <div v-if="selectedMetrics.respiratory_rate" class="card metric-card">
          <div class="mc-icon">🌬️</div>
          <div class="mc-label">呼吸频率</div>
          <div class="mc-value" style="color: #2f6feb;">{{ formatVal(selectedMetrics.respiratory_rate.avg) }}</div>
          <div class="mc-unit">次/分</div>
        </div>

        <!-- Basal Energy -->
        <div v-if="selectedMetrics.basal_energy_burned" class="card metric-card">
          <div class="mc-icon">⚡</div>
          <div class="mc-label">基础代谢</div>
          <div class="mc-value" style="color: #eab308;">{{ formatVal(selectedMetrics.basal_energy_burned.total) }}</div>
          <div class="mc-unit">kcal</div>
        </div>
      </div>

      <div v-else class="card empty-card">
        <div class="empty-icon">📭</div>
        <div class="empty-text">该日期暂无数据</div>
        <div class="empty-hint">请确认已上传并聚合了对应日期的数据</div>
      </div>
    </div>

    <!-- Legend -->
    <div class="legend">
      <div class="legend-item">
        <span class="legend-dot has-data"></span>
        <span>有数据</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot today"></span>
        <span>今天</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import request from '../../api/request.js'

const today = new Date()
const currentYear = ref(today.getFullYear())
const currentMonth = ref(today.getMonth()) // 0-indexed
const selectedDate = ref(null)
const monthData = ref({})

const weekdays = ['日', '一', '二', '三', '四', '五', '六']

const monthLabel = computed(() => {
  return `${currentYear.value}年${currentMonth.value + 1}月`
})

const selectedWeekday = computed(() => {
  if (!selectedDate.value) return ''
  const d = new Date(selectedDate.value)
  return ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getDay()]
})

const selectedMetrics = computed(() => {
  if (!selectedDate.value || !monthData.value.days) return null
  return monthData.value.days[selectedDate.value] || null
})

// Calendar cells generation
const calendarCells = computed(() => {
  const year = currentYear.value
  const month = currentMonth.value
  const firstDay = new Date(year, month, 1).getDay()
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const todayStr = formatDate(today)

  const cells = []

  // Empty cells for days before month starts
  for (let i = 0; i < firstDay; i++) {
    cells.push({ day: null, dateStr: null, isToday: false, hasData: false })
  }

  // Days of the month
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    const hasData = monthData.value.days && !!monthData.value.days[dateStr]
    cells.push({
      day: d,
      dateStr,
      isToday: dateStr === todayStr,
      hasData
    })
  }

  // Fill remaining cells to complete the grid (6 rows x 7 cols = 42)
  while (cells.length < 42) {
    cells.push({ day: null, dateStr: null, isToday: false, hasData: false })
  }

  return cells
})

const formatDate = (d) => {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const formatVal = (v) => {
  if (v == null) return '--'
  return Math.round(v * 10) / 10
}

const formatInt = (v) => {
  if (v == null) return '--'
  return Math.round(v).toLocaleString()
}

const formatHours = (minutes) => {
  if (minutes == null) return '--'
  return Math.round(minutes / 60 * 10) / 10
}

const selectDate = (dateStr) => {
  selectedDate.value = dateStr
}

const prevMonth = () => {
  currentMonth.value--
  if (currentMonth.value < 0) {
    currentMonth.value = 11
    currentYear.value--
  }
  selectedDate.value = null
  loadMonthData()
}

const nextMonth = () => {
  currentMonth.value++
  if (currentMonth.value > 11) {
    currentMonth.value = 0
    currentYear.value++
  }
  selectedDate.value = null
  loadMonthData()
}

const loadMonthData = async () => {
  const month = `${currentYear.value}-${String(currentMonth.value + 1).padStart(2, '0')}`
  try {
    const data = await request('/api/v1/health/daily/batch', { data: { month } })
    monthData.value = data
  } catch (e) {
    console.error('Failed to load month data:', e)
    monthData.value = {}
  }
}

onMounted(() => {
  // Select today by default
  selectedDate.value = formatDate(today)
  loadMonthData()
})
</script>

<style scoped>
.cal-page { padding: 0 16px 24px; }

.cal-head { display: flex; align-items: center; gap: 10px; padding: 10px 0 4px; }
.cal-back {
  width: 32px; height: 32px; border-radius: 50%; background: var(--fg-soft);
  border: 0; display: grid; place-items: center; cursor: pointer; color: var(--fg); flex-shrink: 0;
}
.cal-back svg { width: 16px; height: 16px; stroke: currentColor; fill: none; stroke-width: 2; }
.cal-title {
  font-family: var(--font-display); font-size: var(--fs-h1); font-weight: 600; letter-spacing: -0.025em;
}

/* Month navigation */
.cal-nav {
  display: flex; align-items: center; justify-content: center; gap: 20px;
  padding: 12px 0; margin-bottom: 8px;
}
.cal-nav-btn {
  width: 36px; height: 36px; border-radius: 50%; background: var(--fg-soft);
  border: 0; display: grid; place-items: center; cursor: pointer; color: var(--fg);
  transition: background 0.15s;
}
.cal-nav-btn:hover { background: var(--border); }
.cal-nav-btn svg { width: 16px; height: 16px; stroke: currentColor; fill: none; stroke-width: 2; }
.cal-month-label {
  font-family: var(--font-display); font-size: 18px; font-weight: 600; letter-spacing: -0.01em;
  min-width: 120px; text-align: center;
}

/* Calendar card */
.cal-card { padding: 16px; margin-bottom: 16px; }

.cal-weekdays {
  display: grid; grid-template-columns: repeat(7, 1fr); text-align: center;
  font-size: 11px; color: var(--muted); margin-bottom: 8px;
  font-family: var(--font-mono); letter-spacing: 0.04em;
}

.cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; }

.cal-cell {
  aspect-ratio: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 2px;
  border-radius: 12px; cursor: pointer; transition: all 0.15s;
  position: relative;
}
.cal-cell.empty { cursor: default; }
.cal-cell:not(.empty):hover { background: var(--fg-soft); }

.cal-day-num {
  font-family: var(--font-mono); font-size: 14px; font-variant-numeric: tabular-nums;
  line-height: 1;
}

.cal-dot {
  width: 5px; height: 5px; border-radius: 50%;
  background: var(--accent);
}

.cal-cell.today .cal-day-num {
  font-weight: 700; color: var(--accent);
}

.cal-cell.selected {
  background: var(--accent);
}
.cal-cell.selected .cal-day-num {
  color: #fff; font-weight: 600;
}
.cal-cell.selected .cal-dot {
  background: rgba(255,255,255,0.8);
}

.cal-cell.has-data:not(.selected) {
  background: var(--accent-soft);
}

/* Detail section */
.detail-section { margin-bottom: 16px; }

.detail-header {
  display: flex; align-items: center; gap: 8px; margin-bottom: 12px; padding: 0 4px;
}
.detail-date {
  font-family: var(--font-mono); font-size: 15px; font-weight: 600; color: var(--accent);
}
.detail-weekday {
  font-size: 13px; color: var(--muted);
}

/* Metrics grid */
.metrics-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px;
}

.metric-card {
  padding: 12px 8px; text-align: center;
  display: flex; flex-direction: column; align-items: center; gap: 2px;
}
.mc-icon { font-size: 20px; margin-bottom: 2px; }
.mc-label {
  font-size: 10px; color: var(--muted); line-height: 1.2;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%;
}
.mc-value {
  font-family: var(--font-mono); font-size: 20px; font-weight: 700;
  letter-spacing: -0.01em; line-height: 1.1;
}
.mc-unit { font-size: 10px; color: var(--muted); }

/* Empty state */
.empty-card {
  padding: 32px; text-align: center;
}
.empty-icon { font-size: 40px; margin-bottom: 12px; }
.empty-text { font-size: 15px; font-weight: 500; margin-bottom: 4px; }
.empty-hint { font-size: 12px; color: var(--muted); }

/* Legend */
.legend {
  display: flex; align-items: center; justify-content: center; gap: 16px;
  padding: 8px 0;
}
.legend-item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--muted); }
.legend-dot {
  width: 8px; height: 8px; border-radius: 50%;
}
.legend-dot.has-data { background: var(--accent-soft); border: 1px solid var(--accent); }
.legend-dot.today { background: var(--accent); }

/* Responsive: 2 columns on very small screens */
@media (max-width: 340px) {
  .metrics-grid { grid-template-columns: repeat(2, 1fr); }
  .mc-value { font-size: 18px; }
}
</style>
