import { defineStore } from 'pinia'
import { getTodayMetrics, getBaseline, getTrend, getSyncStatus } from '@/api/health'

export const useHealthStore = defineStore('health', {
  state: () => ({
    metrics: [],             // daily 指标列表
    syncInfo: null,          // 同步状态
    baseline: {},            // { metric: { mean, upper_bound, ... } }
    trends: {},              // { metric: { weeks_data, trend_direction, ... } }
    loading: false,
  }),
  actions: {
    async loadAll() {
      this.loading = true
      try {
        const syncRes = await getSyncStatus()
        this.syncInfo = syncRes

        // 先试今天，无数据则试昨天和前天
        let metricsRes = await getTodayMetrics()
        if (!metricsRes.metrics?.length) {
          const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10)
          metricsRes = await getTodayMetrics(yesterday)
        }
        if (!metricsRes.metrics?.length) {
          const dayBefore = new Date(Date.now() - 172800000).toISOString().slice(0, 10)
          metricsRes = await getTodayMetrics(dayBefore)
        }
        this.metrics = metricsRes.metrics || []
      } catch { /* ignore */ }
      this.loading = false
    },
    async loadBaseline(metric) {
      try {
        const res = await getBaseline(metric)
        this.baseline[metric] = res
      } catch { /* ignore */ }
    },
    async loadTrend(metric) {
      try {
        const res = await getTrend(metric, 4)
        this.trends[metric] = res
      } catch { /* ignore */ }
    },
  },
})
