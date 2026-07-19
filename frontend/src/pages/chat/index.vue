<template>
  <div class="page-content chat-page">
    <!-- Header -->
    <div class="chat-header">
      <button class="hdr-btn" @click="showSessions = true">
        <svg viewBox="0 0 24 24"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="15" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
        会话
      </button>
      <span class="hdr-title">AI 健康管家</span>
      <button class="hdr-btn" @click="newChat">
        <svg viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        新对话
      </button>
    </div>

    <!-- Tab switcher -->
    <div class="tab-switch">
      <button :class="{ active: mode === 'data' }" @click="mode = 'data'">健康数据</button>
      <button :class="{ active: mode === 'ai' }" @click="mode = 'ai'">AI 分析</button>
    </div>

    <!-- ── 健康数据 Tab ── -->
    <div v-show="mode === 'data'" class="tab-content" style="display:flex;flex-direction:column;flex:1 1 auto;overflow:hidden;">

      <!-- 欢迎页 / 聊天视图切换 -->
      <template v-if="!inConversation">
        <div class="content-area">
          <section class="welcome-greeting">
            <div class="welcome-avatar">
              <svg viewBox="0 0 48 48" style="stroke:var(--accent);fill:none;stroke-width:1.5;">
                <circle cx="24" cy="16" r="8"/>
                <path d="M10 42c0-7.7 6.3-14 14-14s14 6.3 14 14" stroke-linecap="round"/>
              </svg>
            </div>
            <h2 class="welcome-title">我是您的私人健康顾问</h2>
            <p class="welcome-sub">可以问我健康问题，或查询今日身体状况</p>
          </section>

          <section class="pad">
            <span class="quick-ask-label">快捷提问</span>
            <div class="quick-ask-track">
              <button v-for="q in quickQuestions" :key="q" class="pill" @click="send(q)">{{ q }}</button>
            </div>
          </section>
        </div>
      </template>

      <template v-else>
        <!-- Conversation header -->
        <div class="conv-header">
          <button class="conv-back" @click="closeConversation">
            <svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"/></svg>
          </button>
          <span class="conv-title">{{ convTitle }}</span>
        </div>
        <!-- Messages -->
        <div class="msg-list" ref="msgListRef">
          <div v-for="(m, i) in messages" :key="i" class="msg-row" :class="m.role">
            <div class="msg-avatar" :style="m.role==='user' ? userAvatarStyle : aiAvatarStyle">{{ m.role==='user' ? convTitle[0] : 'AI' }}</div>
            <div class="msg-bubble" :class="{ emergency: m.safety === 'emergency' }">
              <div v-if="m.role === 'assistant'" v-html="renderMd(m.content)"></div>
              <div v-else>{{ m.content }}</div>
              <span v-if="m.intent" style="display:inline-block;margin-top:4px;font-size:10px;color:var(--muted);background:var(--fg-soft);padding:2px 8px;border-radius:999px;">{{ intentLabel(m.intent) }}</span>
            </div>
          </div>
          <div v-if="loading" class="msg-row assistant">
            <div class="msg-avatar" :style="aiAvatarStyle">AI</div>
            <div class="msg-bubble loading-bubble">
              <span class="progress-msg">{{ currentProgress }}</span>
              <span class="dot-ani"></span>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- ── AI 分析 Tab ── -->
    <div v-show="mode === 'ai'" class="tab-content" style="flex:1 1 auto;overflow-y:auto;">
      <div class="ai-panel">
        <div class="date-row">
          <div class="date-display" @click="showCal = true">
            <svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
            <span class="date-text">{{ fmtDate(calDate) }}</span>
          </div>
        </div>
        <div v-if="dupWarning" class="warn-banner">
          <svg viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          <span>{{ dupWarning }}</span>
          <button class="warn-dismiss" @click="dupWarning = ''">忽略</button>
        </div>
        <div v-if="!dupWarning">
          <button class="btn-accent" :disabled="aiLoading" @click="genAnalysis">
            <svg v-if="!aiLoading" viewBox="0 0 24 24" width="16" height="16" style="stroke:currentColor;fill:none;stroke-width:2;"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
            <span v-else class="dot-pulse" style="background:#fff;"></span>
            {{ aiLoading ? '分析中…' : '生成分析报告' }}
          </button>
        </div>
        <div v-else style="display:flex;flex-direction:column;gap:8px;">
          <button class="btn-view-report" @click="viewReport">
            <svg viewBox="0 0 24 24" width="15" height="15" style="stroke:currentColor;fill:none;stroke-width:2;"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            查看已有报告
          </button>
          <button style="width:100%;min-height:42px;background:transparent;color:var(--accent);border:1.5px solid var(--accent);border-radius:14px;font:inherit;font-size:14px;font-weight:600;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:6px;" @click="genAnalysis(true)">
            <svg viewBox="0 0 24 24" width="15" height="15" style="stroke:currentColor;fill:none;stroke-width:2;"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
            仍然重新生成
          </button>
        </div>
        <p class="hint-text" v-if="!dupWarning">分析将调用 LLM，请选择目标日期后点击按钮，避免自动消耗 Token。</p>
        <div v-if="aiResult" class="result-card-wrap">
          <div class="result-card" v-html="aiResult"></div>
          <button class="result-close" @click="aiResult = ''">
            <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            删除报告
          </button>
        </div>

        <!-- Report history -->
        <div style="margin-top:10px;">
          <button class="btn-view-report" style="margin-bottom:0;" @click="showHistory = !showHistory">
            <svg v-if="!showHistory" viewBox="0 0 24 24" width="15" height="15" style="stroke:currentColor;fill:none;stroke-width:2;"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            <svg v-else viewBox="0 0 24 24" width="15" height="15" style="stroke:currentColor;fill:none;stroke-width:2;"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            {{ showHistory ? '关闭历史' : '历史报告' }}
          </button>
          <div v-if="showHistory" class="report-history">
            <span class="report-history-label">历史报告</span>
            <!-- 日分析 -->
            <div v-if="dailyList.length" class="report-history-sublabel">单日分析</div>
            <div class="report-history-list" v-if="dailyList.length">
              <div v-for="d in dailyList" :key="'d'+d.date" class="report-history-item">
                <div class="rh-body" @click="selectDailyFromHistory(d.date)">
                  <div class="rh-date">{{ d.date }}</div>
                  <div class="rh-preview" v-if="d.created_at">生成于 {{ d.created_at.slice(0,10) }}</div>
                </div>
                <button class="rh-del" @click.stop="removeDaily(d.date)" title="删除此报告">
                  <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </div>
            </div>
            <!-- 周报 -->
            <div v-if="reportList.length" class="report-history-sublabel">周报</div>
            <div class="report-history-list" v-if="reportList.length">
              <div v-for="r in reportList" :key="'w'+r.week_start" class="report-history-item">
                <div class="rh-body" @click="selectReport(r)">
                  <div class="rh-date">{{ r.week_start }} ~ {{ r.week_end }}</div>
                  <div class="rh-preview" v-if="r.created_at">生成于 {{ r.created_at.slice(0,10) }}</div>
                </div>
                <button class="rh-del" @click.stop="removeReport(r.week_start)" title="删除此报告">
                  <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </div>
            </div>
            <div v-if="!dailyList.length && !reportList.length" class="report-history-empty">暂无已生成报告</div>
          </div>
        </div>

        <!-- Delete confirmation -->
        <div v-if="pendingDelete" class="confirm-overlay" @click="cancelDelete">
          <div class="confirm-box" @click.stop>
            <p class="confirm-msg">确定要删除该报告吗？<br/><span class="confirm-id">{{ pendingDelete?.key }}</span></p>
            <div class="confirm-actions">
              <button class="confirm-cancel" @click="cancelDelete">取消</button>
              <button class="confirm-ok" @click="confirmDelete">确认删除</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Input bar（健康数据模式显示） -->
    <div v-if="mode === 'data'" class="input-bar">
      <input type="text" v-model="inputText" placeholder="Hello~ How are you feeling today?" @keydown.enter="handleSend" />
      <button class="send-btn" :disabled="!inputText.trim() || loading" @click="handleSend">
        <svg viewBox="0 0 24 24" width="15" height="15" style="stroke:currentColor;fill:none;stroke-width:2.5;"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>
      </button>
    </div>

    <!-- Calendar overlay -->
    <div class="cal-overlay" :class="{ show: showCal }">
      <div class="cal-overlay-bg" @click="showCal = false"></div>
      <div class="cal-picker">
        <div class="cal-header">
          <button class="cal-nav" @click="prevMonth"><svg viewBox="0 0 24 24" style="stroke:currentColor;fill:none;stroke-width:2;"><polyline points="15 18 9 12 15 6"/></svg></button>
          <span class="month-label">{{ calYear }}年{{ calMonth + 1 }}月</span>
          <button class="cal-nav" @click="nextMonth"><svg viewBox="0 0 24 24" style="stroke:currentColor;fill:none;stroke-width:2;"><polyline points="9 18 15 12 9 6"/></svg></button>
        </div>
        <div class="cal-weekdays"><span>日</span><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span></div>
        <div class="cal-grid">
          <template v-for="cell in calCells" :key="cell.key">
            <span v-if="cell.other" class="cal-cell other">{{ cell.day }}</span>
            <button v-else class="cal-cell" :class="{ today: cell.isToday, selected: cell.isSelected }" @click="pickDate(cell)">{{ cell.day }}</button>
          </template>
        </div>
        <div class="cal-actions">
          <button class="btn-clear" @click="calDate = new Date(); showCal = false">回到今天</button>
          <button class="btn-confirm" @click="showCal = false">确定</button>
        </div>
      </div>
    </div>

    <!-- Session sidebar -->
    <div class="session-overlay" :class="{ open: showSessions }" @click="closeSessions">
      <div class="session-panel" @click.stop>
        <div class="panel-header">
          <span class="panel-title">历史会话</span>
          <button class="panel-close" @click="showSessions = false">
            <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="session-list-scroll">
          <div v-for="s in sessions" :key="s.session_id" class="session-item" @click="openSession(s.session_id)">
            <div>
              <div class="sess-title">{{ s.first_query || s.session_id?.slice(0,16) }}</div>
              <div class="sess-meta">{{ s.turns || 0 }} 轮 · {{ (s.last_active||'').slice(0,10) }}</div>
            </div>
            <button class="sess-del" @click.stop="requestDeleteSession(s.session_id, s.first_query)" title="删除会话">
              <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <div v-if="!sessions.length" class="empty-sess">暂无历史会话</div>
        </div>
      </div>
    </div>

    <!-- Session delete confirmation -->
    <div v-if="pendingDeleteSession" class="confirm-overlay" @click="cancelDeleteSession">
      <div class="confirm-box" @click.stop>
        <p class="confirm-msg">确定要删除这个会话吗？<br/><span class="confirm-id">{{ pendingDeleteSession.label }}</span></p>
        <div class="confirm-actions">
          <button class="confirm-cancel" @click="cancelDeleteSession">取消</button>
          <button class="confirm-ok" @click="confirmDeleteSession">确认删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineOptions({ name: 'ChatPage' })
import { ref, computed, onMounted, nextTick, inject } from 'vue'
import { sendMessage, getSessions, getHistory, deleteSession, getChatProgress } from '../../api/chat.js'
import { renderMarkdown } from '../../api/markdown.js'
import { generateReport, getReportList, getReport, deleteReport, getDailyAnalysis, getDailyList, deleteDaily } from '../../api/report.js'

const toast = inject('toast')

// ── Mode ──
const mode = ref('data')

// ── Chat state ──
const messages = ref([])
const inputText = ref('')
const loading = ref(false)
const currentSessionId = ref(null)
const currentProgress = ref('正在处理…')
const progressTimer = ref(null)

// ── 进度轮询 ──
const startProgressPoll = (sid) => {
  currentProgress.value = '正在处理…'
  if (progressTimer.value) clearInterval(progressTimer.value)
  progressTimer.value = setInterval(async () => {
    try {
      const data = await getChatProgress(sid)
      const events = data?.events || []
      if (events.length > 0) {
        currentProgress.value = events[events.length - 1].msg
      }
    } catch { /* 轮询失败忽略 */ }
  }, 600)
}

const stopProgressPoll = () => {
  if (progressTimer.value) { clearInterval(progressTimer.value); progressTimer.value = null }
}
const inConversation = ref(false)
const convTitle = ref('会话')
const msgListRef = ref(null)

const quickQuestions = ['今日报告','本周总结','运动计划','睡眠分析','心率趋势','步数追踪','恢复建议','健康评分','VO₂ Max','HRV 分析']

const userAvatarStyle = { background: 'linear-gradient(135deg, #2f6feb, #5b8ff7)', color: '#fff' }
const aiAvatarStyle = { background: 'linear-gradient(135deg, #2f6feb, #5b8ff7)', color: '#fff' }

const intentLabel = (i) => ({ health_data:'📊 数据', medical_qa:'🏥 问答', emergency:'🚨 紧急', general:'💬' }[i] || i)

// ── Sessions ──
const sessions = ref([])
const showSessions = ref(false)

const scrollBottom = () => nextTick(() => {
  const el = msgListRef.value
  if (el) el.scrollTop = el.scrollHeight
})

const newChat = () => {
  messages.value = []
  currentSessionId.value = null
  inConversation.value = false
  inputText.value = ''
}

const closeConversation = () => { newChat() }

const send = async (text) => {
  if (text) inputText.value = text
  const q = inputText.value.trim()
  if (!q || loading.value) return
  inputText.value = ''

  if (!inConversation.value) {
    inConversation.value = true
    convTitle.value = q.length > 20 ? q.slice(0,20)+'…' : q
    // 生成临时 session_id 确保进度轮询 key 与后端一致
    currentSessionId.value = 'c' + Date.now().toString(36)
  }

  messages.value.push({ role: 'user', content: q })
  loading.value = true
  currentProgress.value = '正在处理…'
  scrollBottom()

  startProgressPoll(currentSessionId.value)

  try {
    const resp = await sendMessage(q, currentSessionId.value)
    currentSessionId.value = resp.session_id
    convTitle.value = q.length > 16 ? q.slice(0,16)+'…' : q
    messages.value.push({ role: 'assistant', content: resp.response, intent: resp.intent, safety: resp.safety_level })
  } catch {
    messages.value.push({ role: 'assistant', content: '⚠️ 请求失败，请检查网络连接后重试。' })
  } finally {
    stopProgressPoll()
    loading.value = false
    scrollBottom()
    loadSessions()
  }
}

const handleSend = () => send()

const loadSessions = async () => {
  try { const d = await getSessions(); sessions.value = d.sessions || [] } catch {}
}

const openSession = async (sid) => {
  showSessions.value = false
  try {
    const d = await getHistory(sid)
    const h = d.history || []
    currentSessionId.value = sid
    inConversation.value = true
    convTitle.value = h[0]?.content?.slice(0,16) || '会话'
    messages.value = h.map(m => ({ role: m.role, content: m.content, intent: m.intent, safety: m.safety_level }))
    scrollBottom()
  } catch { toast('加载会话失败') }
}

const removeSession = async (sid) => {
  try {
    await deleteSession(sid)
    if (currentSessionId.value === sid) newChat()
    loadSessions()
    toast('会话已删除')
  } catch { toast('删除失败') }
}

// ── 会话删除确认 ──
const pendingDeleteSession = ref(null)  // { sid, label }

const requestDeleteSession = (sid, label) => {
  pendingDeleteSession.value = { sid, label: label || sid?.slice(0,16) }
}

const confirmDeleteSession = async () => {
  const sid = pendingDeleteSession.value?.sid
  pendingDeleteSession.value = null
  if (sid) await removeSession(sid)
}

const cancelDeleteSession = () => { pendingDeleteSession.value = null }

const closeSessions = () => { showSessions.value = false }

// ── AI Analysis ──
const calDate = ref(new Date())
const showCal = ref(false)
const aiLoading = ref(false)
const aiResult = ref('')
const dupWarning = ref('')
const showHistory = ref(false)
const reportList = ref([])          // 周报列表
const dailyList = ref([])          // 日分析列表
const pendingDelete = ref(null)    // {type:'daily'|'weekly', key: str}，null = 关闭确认弹窗

const calYear = ref(new Date().getFullYear())
const calMonth = ref(new Date().getMonth())

const calCells = computed(() => {
  const y = calYear.value, m = calMonth.value
  const firstDay = new Date(y, m, 1).getDay()
  const daysInMonth = new Date(y, m + 1, 0).getDate()
  const daysInPrev = new Date(y, m, 0).getDate()
  const today = new Date()
  const todayStr = fmtDateStr(today)
  const selStr = fmtDateStr(calDate.value)
  const cells = []
  for (let i = firstDay - 1; i >= 0; i--) cells.push({ key: 'p'+i, day: daysInPrev - i, other: true })
  for (let d = 1; d <= daysInMonth; d++) {
    const ds = `${y}-${String(m+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`
    cells.push({ key: 'd'+d, day: d, other: false, isToday: ds === todayStr, isSelected: ds === selStr, dateStr: ds })
  }
  const total = firstDay + daysInMonth
  const rem = total <= 35 ? 35 - total : 42 - total
  for (let d = 1; d <= rem; d++) cells.push({ key: 'n'+d, day: d, other: true })
  return cells
})

const pickDate = (cell) => {
  const [cy, cm, cd] = cell.dateStr.split('-').map(Number)
  calDate.value = new Date(cy, cm - 1, cd)
}

const prevMonth = () => { calMonth.value--; if (calMonth.value < 0) { calMonth.value = 11; calYear.value-- } }
const nextMonth = () => { calMonth.value++; if (calMonth.value > 11) { calMonth.value = 0; calYear.value++ } }

const fmtDate = (d) => {
  const wk = ['周日','周一','周二','周三','周四','周五','周六']
  return `${d.getFullYear()}年${d.getMonth()+1}月${d.getDate()}日 · ${wk[d.getDay()]}`
}
const fmtDateStr = (d) => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`

const genAnalysis = async (force = false) => {
  aiLoading.value = true
  dupWarning.value = ''
  try {
    const dateKey = fmtDateStr(calDate.value)
    // 调用单日分析 API（而非周报）
    const resp = await getDailyAnalysis(dateKey)
    if (resp.error) { toast(resp.error); aiLoading.value = false; return }
    const label = calDate.value.toLocaleDateString('zh-CN', { month:'long', day:'numeric' })
    aiResult.value = `<div class="result-card"><h3>${label} 日健康分析</h3>` +
      (resp.narrative || '').split('\n').map(l => `<p>${l}</p>`).join('') + '</div>'
    toast('分析已生成')
    aiLoading.value = false
  } catch { toast('生成失败'); aiLoading.value = false }
}

const viewReport = async () => {
  try {
    const dateKey = fmtDateStr(calDate.value)
    const r = await getReport(dateKey)
    if (r?.narrative) aiResult.value = `<div class="result-card"><h3>${fmtDate(calDate.value)} 健康分析</h3>` + r.narrative.split('\n').map(l => `<p>${l}</p>`).join('') + '</div>'
  } catch { toast('报告加载失败') }
}

const loadReports = async () => {
  try { const d = await getReportList(); reportList.value = d.reports || [] } catch {}
  try { const d = await getDailyList(); dailyList.value = d.analyses || [] } catch {}
}

const selectReport = async (r) => {
  try {
    const d = await getReport(r.week_start)
    if (d?.narrative) aiResult.value = `<div class="result-card"><h3>${r.week_start} ~ ${r.week_end} 健康分析</h3>` + d.narrative.split('\n').map(l => `<p>${l}</p>`).join('') + '</div>'
    const el = document.querySelector('.result-card-wrap')
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  } catch {}
}

const selectDailyFromHistory = async (dateStr) => {
  try {
    // 直接调 GET 获取已存储的报告，不重复调 LLM
    const d = await getDailyAnalysis(dateStr)
    const label = new Date(dateStr + 'T00:00:00').toLocaleDateString('zh-CN', { month:'long', day:'numeric' })
    aiResult.value = `<div class="result-card"><h3>${label} 日健康分析</h3>` + (d.narrative || '').split('\n').map(l => `<p>${l}</p>`).join('') + '</div>'
    const el = document.querySelector('.result-card-wrap')
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  } catch {}
}

const removeReport = (ws) => {
  pendingDelete.value = { type: 'weekly', key: ws }
}
const removeDaily = (dateStr) => {
  pendingDelete.value = { type: 'daily', key: dateStr }
}
const confirmDelete = async () => {
  const p = pendingDelete.value
  pendingDelete.value = null
  try {
    if (p.type === 'daily') {
      await deleteDaily(p.key)
    } else {
      await deleteReport(p.key)
    }
    toast('报告已删除')
    loadReports()
  } catch { toast('删除失败，请确认后端已重启并包含最新代码') }
}
const cancelDelete = () => { pendingDelete.value = null }

const renderMd = (t) => renderMarkdown(t)

onMounted(() => { loadSessions(); loadReports() })
</script>

<style scoped>
/* 本页 flex 列 + 禁 page-content 自滚动，由子区域负责 */
.chat-page { display: flex; flex-direction: column; overflow: hidden !important; }
/* ── Header ── */
.chat-header { flex: 0 0 auto; display: flex; align-items: center; justify-content: space-between; padding: 6px 16px 8px; gap: 8px; }
.hdr-btn { font-size: 13px; color: var(--accent); cursor: pointer; padding: 6px 8px; border: 0; background: none; font-family: var(--font-body); white-space: nowrap; border-radius: 8px; transition: background 0.15s; display: inline-flex; align-items: center; gap: 4px; }
.hdr-btn svg { width: 15px; height: 15px; stroke: currentColor; fill: none; stroke-width: 1.8; }
.hdr-btn:active { background: var(--fg-soft); }
.hdr-title { font-family: var(--font-display); font-size: 17px; font-weight: 600; letter-spacing: -0.015em; text-align: center; }

/* ── Tab switch ── */
.tab-switch { flex: 0 0 auto; display: flex; margin: 0 20px 6px; background: var(--fg-soft); border-radius: 999px; padding: 3px; gap: 2px; }
.tab-switch button { flex: 1; padding: 7px 0; border: 0; border-radius: 999px; background: transparent; font: inherit; font-size: 13px; font-weight: 500; color: var(--muted); cursor: pointer; transition: all 0.2s; }
.tab-switch button.active { background: var(--surface); color: var(--fg); box-shadow: 0 1px 3px rgba(0,0,0,0.08); }

/* ── Tab content ── */
.tab-content { overflow-y: auto; }
.tab-content::-webkit-scrollbar { display: none; }

/* ── Welcome ── */
.content-area { flex: 1 1 auto; overflow-y: auto; }
.content-area::-webkit-scrollbar { display: none; }
.welcome-greeting { text-align: center; padding: 24px 24px 8px; }
.welcome-avatar { width: 56px; height: 56px; margin: 0 auto 16px; background: var(--accent-soft); border-radius: 50%; display: grid; place-items: center; }
.welcome-avatar svg { width: 32px; height: 32px; }
.welcome-title { font-family: var(--font-display); font-size: 18px; font-weight: 600; letter-spacing: -0.015em; margin: 0 0 6px; }
.welcome-sub { font-size: 14px; color: var(--muted); margin: 0 0 4px; line-height: 1.5; }

/* ── Conversation ── */
.conv-header { flex: 0 0 auto; display: flex; align-items: center; gap: 8px; padding: 6px 16px 8px; border-bottom: 1px solid var(--border); }
.conv-back { width: 32px; height: 32px; border-radius: 50%; background: var(--fg-soft); border: 0; display: grid; place-items: center; cursor: pointer; color: var(--fg); flex-shrink: 0; }
.conv-back svg { width: 16px; height: 16px; stroke: currentColor; fill: none; stroke-width: 2; }
.conv-title { font-family: var(--font-display); font-size: 16px; font-weight: 600; letter-spacing: -0.01em; flex: 1; text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding-right: 32px; }

.msg-list { flex: 1 1 auto; padding: 12px 16px; display: flex; flex-direction: column; gap: 14px; overflow-y: auto; }
.msg-list::-webkit-scrollbar { display: none; }
.msg-row { display: flex; gap: 8px; max-width: 90%; }
.msg-row.user { align-self: flex-end; flex-direction: row-reverse; }
.msg-row.assistant { align-self: flex-start; }
.msg-avatar { width: 30px; height: 30px; border-radius: 50%; flex-shrink: 0; display: grid; place-items: center; font-size: 11px; font-weight: 600; }
.msg-bubble { padding: 10px 14px; border-radius: 18px; font-size: 14px; line-height: 1.55; word-break: break-word; }
.msg-row.user .msg-bubble { background: var(--accent); color: #fff; border-bottom-right-radius: 6px; }
.msg-row.assistant .msg-bubble { background: var(--surface); border: 1px solid var(--border); border-bottom-left-radius: 6px; }
.msg-bubble.emergency { border-color: #dc2626; background: #fff5f5; }
.msg-bubble :deep(h2) { font-family: var(--font-display); font-size: 16px; margin: 0 0 8px; font-weight: 600; }
.msg-bubble :deep(h3) { font-family: var(--font-display); font-size: 14px; margin: 0 0 4px; font-weight: 600; }
.msg-bubble :deep(p) { margin: 0 0 6px; }
.msg-bubble :deep(strong) { font-weight: 600; }
.msg-bubble :deep(ul), .msg-bubble :deep(ol) { margin: 4px 0; padding-left: 18px; }
.msg-bubble :deep(li) { margin-bottom: 2px; }
.msg-bubble :deep(table) { width: 100%; border-collapse: collapse; font-size: 12px; margin: 6px 0; }
.msg-bubble :deep(th), .msg-bubble :deep(td) { padding: 4px 8px; border-bottom: 1px solid var(--border); text-align: left; }
.msg-bubble :deep(code) { background: var(--fg-soft); padding: 2px 5px; border-radius: 4px; font-size: 12px; font-family: var(--font-mono); }

.dot-pulse { display: inline-block; width: 8px; height: 8px; background: var(--accent); border-radius: 50%; animation: pulse 1.2s infinite; }
@keyframes pulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }

/* ── Loading bubble with animated dots ── */
.loading-bubble { display: inline-flex; align-items: center; gap: 6px; padding: 12px 16px !important; }
.progress-msg { font-size: 14px; color: var(--muted); }
.dot-ani {
  display: inline-block; width: 4px; height: 4px; border-radius: 50%; background: var(--muted);
  animation: dotSeq 1.4s steps(1, end) infinite;
  box-shadow:
    8px 0 0 0 var(--muted),
    16px 0 0 0 var(--muted);
}
@keyframes dotSeq {
  0%   { box-shadow: 8px 0 0 0 transparent, 16px 0 0 0 transparent; }
  25%  { box-shadow: 8px 0 0 0 var(--muted), 16px 0 0 0 transparent; }
  50%  { box-shadow: 8px 0 0 0 var(--muted), 16px 0 0 0 var(--muted); }
  75%  { box-shadow: 8px 0 0 0 var(--muted), 16px 0 0 0 var(--muted); }
}

/* ── Input ── */
.input-bar { flex: 0 0 auto; display: flex; align-items: center; gap: 8px; padding: 8px 16px 10px; background: var(--bg); }
.input-bar input { flex: 1; height: 40px; border: 1px solid var(--border); border-radius: 20px; padding: 0 16px; font: inherit; font-size: 14px; color: var(--fg); background: var(--surface); outline: none; }
.input-bar input:focus { border-color: var(--accent); }
.send-btn { width: 40px; height: 40px; border-radius: 50%; background: var(--accent); color: #fff; border: 0; display: grid; place-items: center; cursor: pointer; flex-shrink: 0; }
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── AI Analysis ── */
.ai-panel { padding: 8px 20px 16px; }
.date-row { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; }
.date-display { flex: 1; height: 42px; border: 1px solid var(--border); border-radius: 12px; padding: 0 14px; font: inherit; font-size: 14px; color: var(--fg); background: var(--surface); display: flex; align-items: center; cursor: pointer; gap: 8px; }
.date-display:hover { border-color: var(--accent); }
.date-display svg { width: 16px; height: 16px; stroke: var(--muted); fill: none; stroke-width: 1.8; flex-shrink: 0; }
.date-text { flex: 1; }
.btn-accent { display: flex; align-items: center; justify-content: center; gap: 6px; width: 100%; min-height: 46px; padding: 12px 20px; background: var(--accent); color: #fff; border: 0; border-radius: 14px; font: inherit; font-size: 15px; font-weight: 600; letter-spacing: -0.005em; cursor: pointer; transition: opacity 0.15s; }
.btn-accent:disabled { opacity: 0.5; cursor: not-allowed; }
.hint-text { font-size: 11px; color: var(--muted); margin-top: 10px; font-family: var(--font-mono); }
.result-card-wrap { position: relative; }
.result-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-card); padding: 16px; margin-top: 14px; font-size: 13px; line-height: 1.65; }
.result-card :deep(h3) { font-family: var(--font-display); font-size: 16px; margin: 0 0 10px; font-weight: 600; }
.result-card :deep(p) { margin: 0 0 8px; }
.result-close {
  display: inline-flex; align-items: center; gap: 4px; margin-top: 8px;
  padding: 6px 14px; border-radius: var(--radius-pill); border: 1px solid var(--border);
  background: var(--surface); color: var(--muted); font-size: 12px;
  font-family: var(--font-body); cursor: pointer; transition: all 0.15s;
}
.result-close svg { width: 12px; height: 12px; stroke: currentColor; fill: none; stroke-width: 2; }
.result-close:active { background: var(--fg-soft); color: var(--fg); }

.warn-banner { display: flex; align-items: flex-start; gap: 8px; padding: 10px 12px; background: color-mix(in oklch, #eab308 12%, transparent); border: 1px solid color-mix(in oklch, #eab308 25%, transparent); border-radius: 10px; margin-bottom: 10px; font-size: 12px; line-height: 1.5; }
.warn-banner svg { width: 16px; height: 16px; stroke: #eab308; fill: none; stroke-width: 2; flex-shrink: 0; margin-top: 1px; }
.warn-dismiss { flex-shrink: 0; color: var(--muted); cursor: pointer; font-size: 12px; background: none; border: 0; padding: 0; margin-left: auto; }

.btn-view-report { display: flex; align-items: center; justify-content: center; gap: 6px; width: 100%; min-height: 44px; padding: 10px 20px; background: transparent; color: var(--accent); border: 1.5px solid var(--accent); border-radius: 14px; font: inherit; font-size: 15px; font-weight: 600; letter-spacing: -0.005em; cursor: pointer; transition: background 0.15s; margin-bottom: 8px; }
.btn-view-report:active { background: var(--accent-soft); }

.report-history { margin-top: 6px; }
.report-history-label { display: block; font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.06em; color: var(--muted); text-transform: uppercase; margin-bottom: 2px; padding: 0 2px; }
.report-history-sublabel { font-size: 11px; font-weight: 600; color: var(--fg); margin: 8px 0 4px 2px; }
.report-history-list { display: flex; flex-direction: column; gap: 2px; }
.report-history-item { display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 6px; padding: 10px 12px; border-radius: 12px; transition: background 0.15s; border: 1px solid transparent; }
.report-history-item:hover { background: var(--fg-soft); }
.report-history-item:active { border-color: var(--border); }
/* 可点击的文本区 */
.rh-body { cursor: pointer; overflow: hidden; min-width: 0; }
.rh-date { font-size: 13px; font-weight: 500; line-height: 1.3; }
.rh-preview { font-size: 11px; color: var(--muted); line-height: 1.35; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-top: 1px; }
/* 删除按钮 — 移动端足够大的触摸区 */
.rh-del {
  width: 32px; height: 32px; border-radius: 50%; border: 0;
  background: transparent; color: var(--muted); cursor: pointer;
  display: grid; place-items: center; flex-shrink: 0; z-index: 2;
  transition: color 0.15s, background 0.15s;
  -webkit-tap-highlight-color: transparent;
}
.rh-del svg { width: 16px; height: 16px; stroke: currentColor; fill: none; stroke-width: 2; }
.rh-del:active { color: #dc2626; background: color-mix(in oklch, #dc2626 12%, transparent); }
.report-history-empty { text-align: center; padding: 16px; color: var(--muted); font-size: 12px; }

/* ── Calendar ── */
.cal-overlay { position: absolute; inset: 0; background: rgba(0,0,0,0.35); z-index: 20; display: none; align-items: center; justify-content: center; border-radius: 44px; }
.cal-overlay.show { display: flex; }
.cal-overlay-bg { position: absolute; inset: 0; border-radius: 44px; }
.cal-picker { position: relative; background: var(--surface); border-radius: 20px; width: calc(100% - 48px); padding: 20px; box-shadow: 0 12px 40px rgba(0,0,0,0.2); }
.cal-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.month-label { font-family: var(--font-display); font-size: 18px; font-weight: 600; letter-spacing: -0.01em; }
.cal-nav { width: 32px; height: 32px; border-radius: 999px; background: var(--fg-soft); border: 0; display: grid; place-items: center; cursor: pointer; color: var(--fg); }
.cal-nav svg { width: 16px; height: 16px; }
.cal-weekdays { display: grid; grid-template-columns: repeat(7, 1fr); text-align: center; font-size: 11px; color: var(--muted); margin-bottom: 6px; font-family: var(--font-mono); }
.cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; }
.cal-cell { aspect-ratio: 1; display: grid; place-items: center; font-size: 14px; font-family: var(--font-mono); font-variant-numeric: tabular-nums; border-radius: 999px; background: transparent; border: 0; color: var(--fg); cursor: pointer; transition: background 150ms; }
.cal-cell:hover { background: var(--fg-soft); }
.cal-cell.other { color: var(--border); pointer-events: none; }
.cal-cell.today { font-weight: 700; color: var(--accent); }
.cal-cell.selected { background: var(--accent); color: #fff; font-weight: 600; }
.cal-actions { display: flex; gap: 8px; margin-top: 14px; }
.cal-actions button { flex: 1; padding: 8px 0; border-radius: 999px; border: 0; font: inherit; font-size: 13px; font-weight: 500; cursor: pointer; }
.btn-clear { background: transparent; color: var(--accent); }
.btn-confirm { background: var(--accent); color: #fff; }

/* ── Session sidebar ── */
.session-overlay { position: absolute; inset: 0; z-index: 20; background: transparent; opacity: 0; pointer-events: none; transition: opacity 0.2s; }
.session-overlay.open { opacity: 1; pointer-events: auto; }
.session-panel {
  position: absolute; left: 0; top: 0; bottom: 0; width: 280px; max-width: 85vw;
  background: var(--surface); color: var(--fg);
  display: flex; flex-direction: column;
  transform: translateX(-100%);
  transition: transform 0.25s cubic-bezier(0.2,0,0,1);
  border-radius: 0;
  overflow-x: hidden; overflow-y: hidden;
  touch-action: pan-y;
  user-select: none; -webkit-user-select: none;
  box-shadow: none;
}
.session-overlay.open .session-panel { transform: translateX(0); }
.panel-header {
  flex: 0 0 auto; padding: 60px 18px 14px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
  background: var(--surface);
}
.panel-title { font-family: var(--font-display); font-size: 18px; font-weight: 600; color: var(--fg); }
.panel-close { width: 30px; height: 30px; border-radius: 50%; background: var(--fg-soft); border: 0; display: grid; place-items: center; cursor: pointer; color: var(--muted); }
.panel-close svg { width: 14px; height: 14px; stroke: currentColor; fill: none; stroke-width: 2; }
.session-list-scroll { flex: 1; overflow-y: auto; overflow-x: hidden; padding: 4px 0 80px; touch-action: pan-y; }
.session-list-scroll::-webkit-scrollbar { display: none; }
.session-item {
  display: grid; grid-template-columns: 1fr auto; align-items: center;
  gap: 8px; padding: 14px 18px; cursor: pointer;
  border-bottom: 1px solid var(--fg-soft); transition: background 0.15s;
  overflow: hidden;                   /* 阻断子元素溢出撑大 layout */
}
.session-item:active { background: var(--fg-soft); }
/* 标题文本容器 — 负责承载截断 */
.session-item > div {
  overflow: hidden; min-width: 0;
}
.sess-title {
  font-size: 14px !important;         /* 强制统一字号 */
  font-weight: 500; line-height: 1.3;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  display: block;                     /* 块级确保 ellipsis 生效 */
}
.sess-meta { font-size: 11px; color: var(--muted); margin-top: 2px; font-family: var(--font-mono); }
.sess-del {
  width: 28px; height: 28px; border-radius: 50%; border: 0;
  background: transparent; color: var(--muted); cursor: pointer;
  display: grid; place-items: center; flex-shrink: 0;
  transition: color 0.15s, background 0.15s;
  -webkit-tap-highlight-color: transparent;
}
.sess-del svg { width: 14px; height: 14px; stroke: currentColor; fill: none; stroke-width: 2; }
.sess-del:hover { color: #dc2626; background: color-mix(in oklch, #dc2626 10%, transparent); }
.sess-del:active { color: #dc2626; background: color-mix(in oklch, #dc2626 16%, transparent); }
.empty-sess { text-align: center; padding: 40px 20px; color: var(--muted); font-size: 13px; }

/* ── Delete confirmation overlay ── */
.confirm-overlay {
  position: fixed; inset: 0; z-index: 100;
  background: rgba(0,0,0,0.45);
  display: flex; align-items: center; justify-content: center;
  animation: fadeIn 0.15s ease;
}
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
.confirm-box {
  background: var(--surface); border-radius: var(--radius-card);
  padding: 24px 20px 20px; width: 280px; max-width: 85vw;
  box-shadow: 0 12px 40px rgba(0,0,0,0.25);
  text-align: center;
}
.confirm-msg { font-size: 15px; font-weight: 500; margin-bottom: 4px; line-height: 1.5; }
.confirm-id { font-size: 12px; color: var(--muted); font-family: var(--font-mono); }
.confirm-actions { display: flex; gap: 10px; margin-top: 18px; }
.confirm-cancel {
  flex: 1; padding: 10px 0; border-radius: var(--radius-pill);
  border: 1px solid var(--border); background: var(--surface);
  color: var(--fg); font-size: 14px; font-family: var(--font-body); cursor: pointer;
}
.confirm-ok {
  flex: 1; padding: 10px 0; border-radius: var(--radius-pill);
  border: 0; background: #dc2626; color: #fff;
  font-size: 14px; font-family: var(--font-body); font-weight: 600; cursor: pointer;
}
</style>
