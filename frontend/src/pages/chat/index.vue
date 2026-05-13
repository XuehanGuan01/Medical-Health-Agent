<template>
  <div class="chat-page">
    <div class="chat-header">
      <span class="header-btn" @click="showSessions = true">☰ 会话</span>
      <span class="header-title">健康顾问</span>
      <span class="header-btn" @click="chatStore.newChat()">✚ 新对话</span>
    </div>

    <div class="msg-list" ref="msgList">
      <div v-if="chatStore.messages.length === 0" class="empty-state">
        <span class="empty-icon">💬</span>
        <span class="empty-text">我是您的私人健康顾问</span>
        <span class="empty-hint">可以问我健康问题，或查询今日身体状况</span>
      </div>
      <div v-for="(m, i) in chatStore.messages" :key="i" class="msg-row" :class="m.role">
        <div class="msg-bubble" :class="[m.role, m.safety === 'emergency' ? 'emergency' : '']">
          <span class="msg-text" v-if="m.role === 'user'">{{ m.content }}</span>
          <span class="msg-text md-content" v-else v-html="renderMd(m.content)"></span>
          <span v-if="m.intent" class="msg-tag">{{ m.intent }}</span>
        </div>
      </div>
      <div v-if="chatStore.loading" class="msg-row assistant">
        <div class="msg-bubble assistant loading">
          <div class="progress-info">
            <span class="progress-label">{{ progressLabel }}</span>
            <span class="dot-pulse"></span>
          </div>
        </div>
      </div>
    </div>

    <div class="input-bar">
      <input class="input-field" v-model="inputText" placeholder="输入您的问题..." @keyup.enter="handleSend" />
      <button class="send-btn" :disabled="!inputText.trim() || chatStore.loading" @click="handleSend">发送</button>
    </div>

    <!-- 侧边栏 -->
    <div class="session-overlay" v-if="showSessions" @click="showSessions = false">
      <div class="session-panel" @click.stop>
        <span class="panel-title">历史会话</span>
        <div class="session-list">
          <div v-for="s in chatStore.sessions" :key="s.session_id" class="session-item" @click="selectSession(s.session_id)">
            <div class="session-info">
              <span class="session-query">{{ s.first_query || s.session_id }}</span>
              <span class="session-meta">{{ s.turns }} turns · {{ s.last_active?.slice(0, 10) }}</span>
            </div>
            <button class="session-del" @click.stop="deleteSession(s.session_id)">✕</button>
          </div>
          <div v-if="!chatStore.sessions.length" class="empty-session">暂无历史会话</div>
        </div>
        <button class="close-btn" @click="showSessions = false">关闭</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, watch, onMounted, onUnmounted, computed } from 'vue'
import { useChatStore } from '@/stores/chat'
import { renderMarkdown } from '@/api/markdown'

const renderMd = (text) => renderMarkdown(text)

const chatStore = useChatStore()
const inputText = ref('')
const msgList = ref(null)
const showSessions = ref(false)
const loadingStart = ref(0)
const elapsed = ref(0)
let progressTimer = null

const progressLabel = computed(() => {
  if (elapsed.value < 3) return '意图分析中...'
  if (elapsed.value < 8) return '检索医疗知识库中...'
  if (elapsed.value < 20) return '生成回答草稿...'
  if (elapsed.value < 45) return '自检修正中...'
  return '即将完成...'
})

watch(() => chatStore.loading, (v) => {
  if (v) {
    loadingStart.value = Date.now()
    elapsed.value = 0
    progressTimer = setInterval(() => {
      elapsed.value = Math.floor((Date.now() - loadingStart.value) / 1000)
    }, 500)
  } else {
    clearInterval(progressTimer)
    elapsed.value = 0
  }
})

const scrollToBottom = () => {
  nextTick(() => {
    if (msgList.value) msgList.value.scrollTop = msgList.value.scrollHeight
  })
}

watch(() => chatStore.messages.length, scrollToBottom)

const handleSend = async () => {
  const q = inputText.value.trim()
  if (!q || chatStore.loading) return
  inputText.value = ''
  await chatStore.send(q)
}

const selectSession = async (sid) => {
  try {
    await chatStore.switchSession(sid)
    showSessions.value = false
    scrollToBottom()
    showToast('已切换会话')
  } catch {
    showToast('加载会话失败')
  }
}

const deleteSession = async (sid) => {
  try {
    await fetch(`/api/v1/memory/sessions/${sid}`, { method: 'DELETE' })
    chatStore.sessions = chatStore.sessions.filter(s => s.session_id !== sid)
    showToast('Session deleted')
  } catch { showToast('Delete failed') }
}

const showToast = (msg) => {
  const el = document.createElement('div')
  el.className = 'global-toast'
  el.textContent = msg
  document.body.appendChild(el)
  setTimeout(() => { el.classList.add('fade'); setTimeout(() => el.remove(), 300) }, 1500)
}

onMounted(() => chatStore.loadSessions())
onUnmounted(() => clearInterval(progressTimer))
</script>

<style scoped>
.chat-page { display: flex; flex-direction: column; height: calc(100vh - 56px); background: #f0f2f5; }
.chat-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: #fff; border-bottom: 1px solid #e8e8e8; flex-shrink: 0; }
.header-title { font-size: 17px; font-weight: 600; }
.header-btn { font-size: 14px; color: #4A90D9; cursor: pointer; padding: 4px 8px; }

.msg-list { flex: 1; overflow-y: auto; padding: 12px; }
.empty-state { text-align: center; padding: 80px 20px; }
.empty-icon { font-size: 48px; }
.empty-text { display: block; font-size: 16px; color: #333; margin: 12px 0 4px; }
.empty-hint { font-size: 13px; color: #999; display: block; }

.msg-row { margin-bottom: 16px; display: flex; }
.msg-row.user { justify-content: flex-end; }
.msg-bubble { max-width: 80%; padding: 10px 14px; border-radius: 12px; font-size: 15px; line-height: 1.5; }
.msg-bubble.user { background: #4A90D9; color: #fff; border-bottom-right-radius: 4px; }
.msg-bubble.assistant { background: #fff; color: #333; border-bottom-left-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.msg-bubble.emergency { border: 2px solid #e74c3c; }
.msg-bubble.loading { color: #999; min-width: 120px; }
.progress-info { display: flex; align-items: center; gap: 8px; }
.progress-label { font-size: 13px; }
.dot-pulse { width: 8px; height: 8px; background: #4A90D9; border-radius: 50%; animation: pulse 1.2s infinite; }
@keyframes pulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }
.msg-tag { display: block; font-size: 11px; margin-top: 4px; opacity: 0.6; }
.md-content p { margin: 6px 0; }
.md-content ul { margin: 4px 0; padding-left: 18px; }
.md-content li { margin: 2px 0; }
.md-content strong { color: #2c3e50; }

.input-bar { display: flex; padding: 10px 12px; background: #fff; border-top: 1px solid #e8e8e8; align-items: center; gap: 8px; flex-shrink: 0; }
.input-field { flex: 1; height: 40px; border: 1px solid #ddd; border-radius: 20px; padding: 0 16px; font-size: 14px; background: #f5f5f5; outline: none; }
.send-btn { width: 60px; height: 38px; background: #4A90D9; color: #fff; border: none; border-radius: 20px; font-size: 14px; cursor: pointer; }
.send-btn:disabled { background: #b0cee8; cursor: not-allowed; }

.session-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 100; }
.session-panel { position: absolute; left: 0; top: 0; bottom: 0; width: 280px; background: #fff; padding: 16px; display: flex; flex-direction: column; }
.panel-title { font-size: 17px; font-weight: 600; margin-bottom: 12px; }
.session-list { flex: 1; overflow-y: auto; }
.session-item { padding: 12px 0; border-bottom: 1px solid #f0f0f0; cursor: pointer; display: flex; justify-content: space-between; align-items: center; }
.session-info { flex: 1; }
.session-del { background: none; border: none; color: #ccc; font-size: 16px; padding: 4px 8px; }
.session-del:hover { color: #e74c3c; }
.session-query { font-size: 14px; color: #333; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; }
.session-meta { font-size: 12px; color: #999; margin-top: 2px; display: block; }
.empty-session { text-align: center; color: #999; padding: 40px 0; }
.close-btn { margin-top: 12px; background: #f5f5f5; border: none; padding: 10px; border-radius: 8px; cursor: pointer; }
</style>
