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
          <span class="metric-val">{{ v.week_avg?.toFixed(1) || '--' }} {{ v.unit || '' }}</span>
          <span class="metric-days">{{ v.days || 0 }} 天</span>
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
  const map = { heart_rate: '心率 (Heart Rate)', resting_heart_rate: '静息心率 (Resting HR)', heart_rate_variability: '心率变异性 (HRV)', step_count: '步数 (Steps)', active_energy: '活动能量 (Active Energy)', basal_energy_burned: '基础代谢 (Basal Energy)', apple_exercise_time: '运动时长 (Exercise)', apple_stand_time: '站立时长 (Stand)', apple_stand_hour: '站立小时 (Stand Hr)', respiratory_rate: '呼吸频率 (Respiratory)', walking_running_distance: '步行距离 (Distance)', walking_speed: '步行速度 (Walk Speed)', walking_step_length: '步长 (Step Len)', walking_asymmetry_percentage: '步行不对称 (Asymmetry)', walking_double_support_percentage: '双支撑 (Dbl Support)', walking_heart_rate_average: '步行心率 (Walk HR)', flights_climbed: '爬楼 (Flights)', physical_effort: '身体负荷 (Effort)', environmental_audio_exposure: '环境噪音 (Env Noise)', headphone_audio_exposure: '耳机噪音 (HP Noise)', time_in_daylight: '日照时长 (Daylight)', sleep_analysis: '睡眠 (Sleep)', mindful_minutes: '正念分钟 (Mindful)', handwashing: '洗手 (Handwash)', vo2_max: '最大摄氧量 (VO2 Max)', cardio_recovery: '心率恢复 (Cardio Rec)', stair_speed_down: '下楼梯速度 (Stair Down)', stair_speed_up: '上楼梯速度 (Stair Up)', running_power: '跑步功率 (Run Power)', running_speed: '跑步速度 (Run Speed)', running_ground_contact_time: '触地时间 (Grd Contact)', running_vertical_oscillation: '垂直摆动 (Vert Osc)', running_stride_length: '跑步步幅 (Run Stride)', cycling_distance: '骑行距离 (Cycling)', weight_body_mass: '体重 (Weight)', body_fat_percentage: '体脂率 (Body Fat)', body_mass_index: 'BMI', height: '身高 (Height)', six_minute_walking_test_distance: '6分钟步行 (6min Walk)', blood_oxygen_saturation: '血氧 (SpO2)', wrist_temperature: '手腕温度 (Wrist Temp)' }
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
.report-page { padding: 16px; height: calc(100vh - 56px); overflow-y: auto; background: #f0f2f5; -webkit-overflow-scrolling: touch; }
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
