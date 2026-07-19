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

// ── 手动上传 ──
export const uploadJSON = async (file) => {
  const formData = new FormData()
  formData.append('file', file)
  const base = localStorage.getItem('baseURL') || ''
  const res = await fetch(base + '/api/v1/health/upload', {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export const getUploadList = () =>
  request('/api/v1/health/upload/list')

export const deleteUpload = (filename) =>
  request(`/api/v1/health/upload/${encodeURIComponent(filename)}`, { method: 'DELETE' })
