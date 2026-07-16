import request from './request'

export const sendMessage = (query, sessionId = null) =>
  request('/api/v1/chat', { method: 'POST', data: { query, session_id: sessionId } })

export const getSessions = () =>
  request('/api/v1/memory/sessions')

export const getHistory = (sessionId, n = 20) =>
  request('/api/v1/memory/history', { data: { session_id: sessionId, n } })

export const deleteSession = (sessionId) =>
  request(`/api/v1/memory/sessions/${sessionId}`, { method: 'DELETE' })

// ── 进度轮询 ──
export const getChatProgress = (sessionId) =>
  request('/api/v1/chat/progress', { data: { session_id: sessionId } })
