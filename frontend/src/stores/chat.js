import { defineStore } from 'pinia'
import { sendMessage, getSessions, getHistory } from '@/api/chat'

export const useChatStore = defineStore('chat', {
  state: () => ({
    messages: [],
    currentSessionId: null,
    sessions: [],
    loading: false,
  }),
  actions: {
    async send(query) {
      this.messages.push({ role: 'user', content: query, time: Date.now() })
      this.loading = true
      try {
        const res = await sendMessage(query, this.currentSessionId)
        this.currentSessionId = res.session_id
        this.messages.push({
          role: 'assistant', content: res.response,
          intent: res.intent, safety: res.safety_level, time: Date.now(),
        })
      } catch {
        this.messages.push({ role: 'assistant', content: '网络连接失败', time: Date.now() })
      } finally {
        this.loading = false
      }
    },
    async loadSessions() {
      try {
        const res = await getSessions()
        this.sessions = res.sessions || []
      } catch { /* ignore */ }
    },
    async switchSession(sessionId) {
      this.currentSessionId = sessionId
      try {
        const res = await getHistory(sessionId)
        this.messages = (res.history || []).map(h => ({
          role: h.role, content: h.content, time: Date.now(),
        }))
      } catch { /* ignore */ }
    },
    newChat() {
      this.currentSessionId = null
      this.messages = []
    },
  },
})
