<template>
  <div class="report-page">
    <span class="page-title">健康周报</span>

    <div class="week-tabs">
      <div v-for="r in reportStore.reportList" :key="r.week_start"
           class="week-tab" :class="{ active: reportStore.currentWeek === r.week_start }"
           @click="reportStore.loadWeek(r.week_start)">
        <span>{{ r.week_start }} ~ {{ r.week_end }}</span>
      </div>
    </div>

    <div v-if="reportStore.loading" class="loading-box">
      <span>加载中...</span>
    </div>

    <template v-else-if="reportStore.narrative">
      <div class="card narrative-card">
        <span class="card-title">📋 本周总览</span>
        <span class="narrative-text">{{ reportStore.narrative }}</span>
      </div>

      <div class="card metrics-card" v-if="Object.keys(reportStore.metrics).length">
        <span class="card-title">📈 核心指标</span>
        <div class="metric-row" v-for="(v, k) in reportStore.metrics" :key="k">
          <span class="metric-name">{{ labelFor(k) }}</span>
          <span class="metric-val">{{ v.week_avg?.toFixed(1) || '--' }}</span>
          <span class="metric-days">{{ v.days || 0 }}天</span>
        </div>
      </div>
    </template>

    <div v-else class="empty-state">
      <span class="empty-icon">📝</span>
      <span class="empty-text">暂无周报，点击下方按钮生成</span>
    </div>

    <button class="gen-btn" :disabled="reportStore.generating" @click="reportStore.generate()">
      {{ reportStore.generating ? '生成中...' : '生成本周周报' }}
    </button>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useReportStore } from '@/stores/report'

const reportStore = useReportStore()

const labelFor = (m) => {
  const map = { heart_rate: 'Heart Rate', resting_heart_rate: 'Resting HR', heart_rate_variability: 'HRV', step_count: 'Steps', active_energy: 'Active Energy', basal_energy_burned: 'Basal Energy', apple_exercise_time: 'Exercise', apple_stand_time: 'Stand Time', apple_stand_hour: 'Stand Hours', respiratory_rate: 'Respiratory', walking_running_distance: 'Distance', walking_speed: 'Walk Speed', walking_step_length: 'Step Length', walking_asymmetry_percentage: 'Asymmetry', walking_double_support_percentage: 'Dbl Support', walking_heart_rate_average: 'Walk HR Avg', flights_climbed: 'Flights', physical_effort: 'Effort', environmental_audio_exposure: 'Env Noise', headphone_audio_exposure: 'HP Noise', time_in_daylight: 'Daylight', sleep_analysis: 'Sleep', mindful_minutes: 'Mindful', handwashing: 'Handwash', vo2_max: 'VO2 Max', cardio_recovery: 'Cardio Rec', stair_speed_down: 'Stair Down', stair_speed_up: 'Stair Up', running_power: 'Run Power', running_speed: 'Run Speed', running_ground_contact_time: 'Grd Contact', running_vertical_oscillation: 'Vert Osc', running_stride_length: 'Run Stride', cycling_distance: 'Cycling', weight_body_mass: 'Weight', body_fat_percentage: 'Body Fat', body_mass_index: 'BMI', height: 'Height', six_minute_walking_test_distance: '6min Walk', blood_oxygen_saturation: 'SpO2', wrist_temperature: 'Wrist Temp' }
  return map[m] || m.replace(/_/g, ' ')
}

onMounted(async () => {
  await reportStore.loadList()
  if (reportStore.reportList.length > 0) {
    reportStore.loadWeek(reportStore.reportList[0].week_start)
  }
})
</script>

<style scoped>
.report-page { padding: 16px; min-height: calc(100vh - 56px); background: #f0f2f5; }
.page-title { font-size: 22px; font-weight: 700; color: #333; margin-bottom: 12px; display: block; }

.week-tabs { overflow-x: auto; white-space: nowrap; margin-bottom: 16px; }
.week-tab { display: inline-block; padding: 8px 14px; margin-right: 8px; background: #fff; border-radius: 8px; font-size: 13px; color: #666; }
.week-tab.active { background: #4A90D9; color: #fff; }

.loading-box { text-align: center; padding: 40px; color: #999; }

.card { background: #fff; border-radius: 12px; padding: 16px; margin-bottom: 12px; }
.card-title { font-size: 15px; font-weight: 600; color: #333; margin-bottom: 10px; display: block; }
.narrative-text { font-size: 14px; line-height: 1.7; color: #444; white-space: pre-line; }

.metric-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f5f5f5; }
.metric-name { font-size: 14px; color: #666; }
.metric-val { font-size: 16px; font-weight: 600; color: #333; }
.metric-days { font-size: 12px; color: #999; }

.empty-state { text-align: center; padding: 80px 20px; }
.empty-icon { font-size: 48px; }
.empty-text { display: block; font-size: 14px; color: #999; margin-top: 12px; }

.gen-btn { width: 100%; padding: 14px; background: #4A90D9; color: #fff; border: none; border-radius: 12px; font-size: 16px; font-weight: 600; margin-top: 16px; }
.gen-btn:disabled { background: #b0cee8; }
</style>
