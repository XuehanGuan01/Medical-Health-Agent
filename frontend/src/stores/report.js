import { defineStore } from 'pinia'
import { generateReport, getReport, getReportList } from '@/api/report'

export const useReportStore = defineStore('report', {
  state: () => ({
    currentWeek: null,      // 当前查看的周报
    reportList: [],         // 历史周报列表
    narrative: '',          // LLM 叙事
    metrics: {},            // 结构化指标
    loading: false,
    generating: false,
  }),
  actions: {
    async loadList() {
      try {
        const res = await getReportList()
        this.reportList = res.reports || []
      } catch { /* ignore */ }
    },
    async loadWeek(weekStart) {
      this.loading = true
      try {
        const res = await getReport(weekStart)
        this.currentWeek = weekStart
        this.narrative = res.narrative || ''
        this.metrics = res.metrics || {}
      } catch {
        this.narrative = '该周周报尚未生成'
        this.metrics = {}
      }
      this.loading = false
    },
    async generate(weekStart = null) {
      this.generating = true
      try {
        const res = await generateReport(weekStart)
        this.currentWeek = res.week_start
        this.narrative = res.narrative
        this.metrics = res.metrics || {}
        await this.loadList()
      } catch {
        uni.showToast({ title: '生成失败', icon: 'none' })
      }
      this.generating = false
    },
  },
})
