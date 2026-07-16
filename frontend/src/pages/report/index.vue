<template>
  <div class="page-content rpt-page">
    <!-- Header -->
    <div class="rpt-head">
      <h1 class="rpt-title">健康周报</h1>
      <button class="pill" :disabled="genning" @click="doGenerate">
        {{ genning ? '生成中…' : '✨ 生成周报' }}
      </button>
    </div>

    <!-- Week chips -->
    <div class="week-scroll" v-if="weeks.length">
      <button
        v-for="w in weeks" :key="w.week_start"
        class="week-chip" :class="{ active: selWeek === w.week_start }"
        @click="loadReport(w.week_start)"
      >{{ w.week_start }} ~ {{ w.week_end }}</button>
    </div>

    <div v-if="!weeks.length" class="empty-state">
      <div class="empty-icon">📝</div>
      <div class="empty-title">暂无周报</div>
      <div class="empty-hint">上传健康数据后可生成周报</div>
    </div>

    <!-- Report content -->
    <div v-if="report" class="rpt-body">
      <!-- Narrative -->
      <div class="card nar-card">
        <div v-html="renderMd(report.narrative || '')"></div>
      </div>

      <!-- Metrics table -->
      <div class="card tbl-card" v-if="table.length">
        <div class="tbl-title">📋 本周指标均值</div>
        <div class="tbl-wrap">
          <table>
            <thead><tr><th>指标</th><th>周均值</th><th>单位</th><th>天数</th></tr></thead>
            <tbody>
              <tr v-for="m in table" :key="m.name">
                <td>{{ labelMap[m.name] || m.name }}</td>
                <td class="num">{{ m.avg != null ? m.avg.toFixed(1) : '--' }}</td>
                <td class="unit">{{ m.unit }}</td>
                <td class="num">{{ m.days }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="rpt-meta" v-if="report.week_start">
        {{ report.week_start }} ~ {{ report.week_end }}
        <span v-if="report.created_at"> · {{ report.created_at.slice(0,10) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import { generateReport, getReport, getReportList } from '../../api/report.js'
import { renderMarkdown } from '../../api/markdown.js'

const toast = inject('toast')

const weeks = ref([])
const selWeek = ref(null)
const report = ref(null)
const genning = ref(false)

const labelMap = {
  heart_rate:'心率', resting_heart_rate:'静息心率', heart_rate_variability:'HRV',
  step_count:'步数', active_energy:'活动能量', basal_energy_burned:'基础代谢',
  apple_exercise_time:'锻炼时长', apple_stand_time:'站立时间', apple_stand_hour:'站立小时',
  sleep_analysis:'睡眠', respiratory_rate:'呼吸频率', walking_running_distance:'步行距离',
  flights_climbed:'爬楼', vo2_max:'VO₂ Max', walking_speed:'步行速度',
  time_in_daylight:'日照', environmental_audio_exposure:'环境噪音',
  physical_effort:'体力消耗', cycling_distance:'骑行', walking_heart_rate_average:'步行心率',
  stair_speed_down:'下楼梯', stair_speed_up:'上楼梯', walking_step_length:'步幅',
  walking_asymmetry_percentage:'不对称', walking_double_support_percentage:'双支撑',
  headphone_audio_exposure:'耳机音量', six_minute_walking_test_distance:'6分钟步行',
}

const table = computed(() => {
  if (!report.value?.metrics) return []
  return Object.entries(report.value.metrics).map(([k,v]) => ({
    name: k, avg: v.week_avg, total: v.week_total, unit: v.unit||'', days: v.days||0
  }))
})

const renderMd = (t) => renderMarkdown(t)

const loadWeeks = async () => {
  try {
    const d = await getReportList()
    weeks.value = d.reports || []
  } catch {}
}

const loadReport = async (ws) => {
  selWeek.value = ws
  try { report.value = await getReport(ws) } catch { report.value = null }
}

const doGenerate = async () => {
  genning.value = true
  try {
    const r = await generateReport()
    if (r.error) { toast(r.error); return }
    report.value = r
    selWeek.value = r.week_start
    toast('周报已生成')
    loadWeeks()
  } catch { toast('生成失败') }
  finally { genning.value = false }
}

onMounted(() => loadWeeks())
</script>

<style scoped>
.rpt-page { padding: 0 12px 24px; }

.rpt-head { display: flex; align-items: center; justify-content: space-between; padding: 10px 4px 12px; }
.rpt-title { font-family: var(--font-display); font-size: var(--fs-h1); font-weight: 600; letter-spacing: -0.025em; }

.week-scroll { display: flex; gap: 8px; overflow-x: auto; padding: 0 0 12px; -webkit-overflow-scrolling: touch; }
.week-scroll::-webkit-scrollbar { display: none; }
.week-chip { flex-shrink: 0; padding: 7px 14px; border-radius: var(--radius-pill); border: 1px solid var(--border); background: var(--surface); font-size: 12px; font-family: var(--font-mono); color: var(--muted); cursor: pointer; }
.week-chip.active { background: var(--accent); border-color: var(--accent); color: #fff; }

.rpt-body { display: flex; flex-direction: column; gap: 12px; }

.nar-card { padding: 18px; font-size: 14px; line-height: 1.7; }
.nar-card :deep(h2) { font-family: var(--font-display); font-size: 16px; margin: 0 0 10px; font-weight: 600; }
.nar-card :deep(h3) { font-family: var(--font-display); font-size: 14px; margin: 0 0 4px; font-weight: 600; }
.nar-card :deep(p) { margin: 0 0 8px; }
.nar-card :deep(strong) { font-weight: 600; }
.nar-card :deep(ul), .nar-card :deep(ol) { margin: 6px 0; padding-left: 20px; }

.tbl-card { padding: 16px; }
.tbl-title { font-family: var(--font-display); font-size: 14px; font-weight: 600; margin-bottom: 12px; }
.tbl-wrap { overflow-x: auto; }
.tbl-wrap table { width: 100%; border-collapse: collapse; font-size: 12px; }
.tbl-wrap th, .tbl-wrap td { padding: 7px 8px; text-align: left; border-bottom: 1px solid var(--border); }
.tbl-wrap th { font-weight: 600; color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; }
.tbl-wrap .num { text-align: right; font-family: var(--font-mono); font-size: 12px; }
.tbl-wrap .unit { text-align: center; color: var(--muted); font-size: 11px; }

.rpt-meta { text-align: center; padding: 8px 0 16px; font-size: var(--fs-meta); color: var(--muted); }

.empty-state { text-align: center; padding: 60px 20px; }
.empty-title { font-size: 16px; font-weight: 500; margin-bottom: 4px; }
.empty-hint { font-size: 13px; color: var(--muted); }
</style>
