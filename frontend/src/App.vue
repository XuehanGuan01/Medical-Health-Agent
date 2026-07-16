<template>
  <div id="app-root" :class="{ dark: isDark }">
    <!-- 页面内容 -->
    <keep-alive>
      <router-view />
    </keep-alive>

    <!-- 底部 TabBar — 4项 -->
    <nav class="tabbar">
      <div class="tab" :class="{ active: $route.path === '/chat' }" @click="$router.push('/chat')">
        <svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        对话
      </div>
      <div class="tab" :class="{ active: $route.path === '/dashboard' }" @click="$router.push('/dashboard')">
        <svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/></svg>
        看板
      </div>
      <div class="tab" :class="{ active: $route.path === '/report' }" @click="$router.push('/report')">
        <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
        周报
      </div>
      <div class="tab" :class="{ active: $route.path === '/settings' || $route.path === '/aggregation' }" @click="$router.push('/settings')">
        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>
        设置
      </div>
    </nav>

    <!-- Toast -->
    <div v-if="toast.show" class="global-toast" :class="{ fade: toast.fading }">{{ toast.msg }}</div>
  </div>
</template>

<script setup>
import { ref, provide, onMounted } from 'vue'

// ── 暗黑模式 ──
const isDark = ref(false)
const toggleDark = () => {
  isDark.value = !isDark.value
  localStorage.setItem('darkMode', isDark.value ? 'on' : 'off')
}
provide('darkMode', isDark)
provide('toggleDark', toggleDark)

onMounted(() => {
  isDark.value = localStorage.getItem('darkMode') === 'on'
})

// ── Toast ──
const toast = ref({ show: false, msg: '', fading: false })
let toastTimer = null
const showToast = (msg, duration = 2000) => {
  if (toastTimer) clearTimeout(toastTimer)
  toast.value = { show: true, msg, fading: false }
  toastTimer = setTimeout(() => {
    toast.value.fading = true
    setTimeout(() => { toast.value.show = false }, 300)
  }, duration)
}
provide('toast', showToast)
</script>

<style>
/* ================================================================
   Neutral Modern 设计系统 — 移动端全屏布局
   ================================================================ */
:root {
  --bg:      #fafafa;
  --surface: #ffffff;
  --fg:      #111111;
  --muted:   #6b6b6b;
  --border:  #e5e5e5;
  --accent:  #2f6feb;
  --accent-soft: color-mix(in oklch, #2f6feb 14%, transparent);
  --fg-soft:     color-mix(in oklch, #111111 6%, transparent);
  --font-display: 'Inter', -apple-system, system-ui, sans-serif;
  --font-body:    'Inter', -apple-system, 'SF Pro Text', system-ui, sans-serif;
  --font-mono:    ui-monospace, 'SF Mono', Menlo, monospace;
  --fs-h1: 22px; --fs-h2: 18px; --fs-h3: 15px; --fs-body: 14px; --fs-meta: 11px;
  --radius-card: 16px; --radius-sm: 8px; --radius-pill: 999px;
}
.dark {
  --bg:      #111111;
  --surface: #1a1a1a;
  --fg:      #f0f0f0;
  --muted:   #999999;
  --border:  #2a2a2a;
  --accent:  #5b8ff7;
  --accent-soft: color-mix(in oklch, #5b8ff7 18%, transparent);
  --fg-soft:     color-mix(in oklch, #f0f0f0 8%, transparent);
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html {
  width: 100%; height: 100%;
  overflow: hidden;
  background: var(--bg);             /* 延伸到安全区 */
  font-family: var(--font-body);
  -webkit-font-smoothing: antialiased;
  -webkit-tap-highlight-color: transparent;
}
body {
  width: 100%; height: 100%;
  overflow: hidden;
  background: var(--bg);
  margin: 0; padding: 0;
}

/* ── 全屏应用容器 ── */
#app-root {
  width: 100%; height: 100%;
  height: 100dvh;
  display: flex; flex-direction: column;
  background: var(--bg); color: var(--fg);
  font-size: var(--fs-body); line-height: 1.4;
  position: relative; overflow: hidden;
  transition: background 0.3s, color 0.3s;
  /* 为刘海屏状态栏 + 底部横条留出安全区 */
  padding-top: env(safe-area-inset-top, 0px);
  padding-bottom: env(safe-area-inset-bottom, 0px);
}

/* ── 页面内容区 ── */
.page-content {
  flex: 1 1 auto;
  overflow-y: auto; overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
}
.page-content::-webkit-scrollbar { display: none; }

/* 聊天页内部自管滚动，禁用 page-content 滚动以免双滚动条 */

/* ── TabBar ── */
.tabbar {
  flex: 0 0 auto; display: grid; grid-template-columns: repeat(4, 1fr);
  padding: 6px 8px 0; border-top: 1px solid var(--border);
  background: color-mix(in oklch, var(--surface) 92%, transparent); backdrop-filter: blur(20px);
  padding-bottom: env(safe-area-inset-bottom, 0px);
  transition: border-color 0.3s;
}
.tab {
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  padding: 6px 0; color: var(--muted); font-size: 10px; letter-spacing: 0.02em;
  cursor: pointer; text-decoration: none; transition: color 0.15s;
}
.tab.active { color: var(--accent); }
.tab svg { width: 22px; height: 22px; stroke: currentColor; fill: none; stroke-width: 1.7; }
.tab.active svg { stroke-width: 2; }

/* ── Toast ── */
.global-toast {
  position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%);
  background: var(--fg); color: var(--bg); padding: 10px 24px;
  border-radius: var(--radius-pill); font-size: 13px; z-index: 999;
  pointer-events: none; white-space: nowrap;
  transition: opacity 0.3s;
}
.global-toast.fade { opacity: 0; }

/* ── 通用工具类 ── */
.card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius-card); padding: 16px;
  transition: background 0.3s, border-color 0.3s;
}
.pad { padding-inline: 20px; }
.stack { display: flex; flex-direction: column; gap: 12px; }
.row { display: flex; align-items: center; gap: 10px; }
.row-between { display: flex; align-items: center; justify-content: space-between; gap: 12px; }

.pill {
  display: inline-flex; align-items: center; gap: 4px; flex-shrink: 0;
  padding: 6px 12px; background: var(--accent-soft); color: var(--accent);
  border-radius: 999px; font-family: var(--font-mono); font-size: 10px;
  letter-spacing: 0.05em; text-transform: uppercase; cursor: pointer;
  border: 0; transition: background 0.15s;
}
.pill:active { background: color-mix(in oklch, var(--accent) 24%, transparent); }

.quick-ask-label {
  display: block; font-family: var(--font-mono); font-size: 10px;
  letter-spacing: 0.06em; color: var(--muted); text-transform: uppercase;
  margin-bottom: 6px; padding-left: 2px;
}
.quick-ask-track {
  display: flex; gap: 6px; overflow-x: auto; padding-bottom: 4px;
  -webkit-overflow-scrolling: touch;
  mask-image: linear-gradient(to left, transparent 0%, black 28px, black 100%);
  -webkit-mask-image: linear-gradient(to left, transparent 0%, black 28px, black 100%);
}
.quick-ask-track::-webkit-scrollbar { display: none; }
.tag {
  display: inline-flex; flex-shrink: 0; padding: 5px 10px;
  background: transparent; color: var(--muted); border: 1px solid var(--border);
  border-radius: 999px; font-size: 12px; cursor: pointer; border: 0;
}

button { cursor: pointer; font-family: inherit; }
button:disabled { cursor: not-allowed; opacity: 0.5; }

/* Empty state */
.empty-state { text-align: center; padding: 60px 20px; }
.empty-state .empty-icon { width: 44px; height: 44px; margin: 0 auto 12px; display: block; stroke: var(--muted); fill: none; stroke-width: 1.3; }
.empty-state .empty-title { font-size: 16px; font-weight: 500; color: var(--fg); margin-bottom: 4px; }
.empty-state .empty-hint { font-size: 13px; color: var(--muted); }
</style>
