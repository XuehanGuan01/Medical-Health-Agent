import request from './request'

export const generateReport = (weekStart = null) =>
  request('/api/v1/report/weekly', { method: 'POST', data: { week_start: weekStart } })

export const getReport = (weekStart) =>
  request('/api/v1/report/weekly', { data: { week_start: weekStart } })

export const getReportList = () =>
  request('/api/v1/report/weekly/list')

export const deleteReport = (weekStart) =>
  request('/api/v1/report/weekly', { method: 'DELETE', data: { week_start: weekStart } })

// ── 单日健康分析 ──
export const getDailyAnalysis = (date) =>
  request('/api/v1/health/daily-analysis', { method: 'POST', data: { date } })

export const getDailyList = () =>
  request('/api/v1/health/daily-analysis/list')

export const deleteDaily = (date) =>
  request('/api/v1/health/daily-analysis', { method: 'DELETE', data: { date } })
