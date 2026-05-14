import request from './request'

const today = () => new Date().toISOString().slice(0, 10)

export const getSyncStatus = () =>
  request('/api/v1/health/status')

export const getTodayMetrics = (date) =>
  request('/api/v1/health/daily', { data: { date: date || today() } })

export const getBaseline = (metric, days = 30) =>
  request('/api/v1/health/baseline', { data: { metric_type: metric, days } })

export const getTrend = (metric, days = 7) =>
  request('/api/v1/health/trend', { data: { metric, weeks: days, granularity: 'day' } })
