import request from './request'

export const generateReport = (weekStart = null) =>
  request('/api/v1/report/weekly', { method: 'POST', data: { week_start: weekStart } })

export const getReport = (weekStart) =>
  request('/api/v1/report/weekly', { data: { week_start: weekStart } })

export const getReportList = () =>
  request('/api/v1/report/weekly/list')
