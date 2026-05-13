<template>
  <div id="app-root">
    <router-view />

    <!-- 底部 TabBar -->
    <div class="tab-bar">
      <div class="tab-item" :class="{ active: $route.path === '/chat' }" @click="$router.push('/chat')">
        <span class="tab-icon">💬</span><span class="tab-text">对话</span>
      </div>
      <div class="tab-item" :class="{ active: $route.path === '/dashboard' }" @click="$router.push('/dashboard')">
        <span class="tab-icon">📊</span><span class="tab-text">看板</span>
      </div>
      <div class="tab-item" :class="{ active: $route.path === '/report' }" @click="$router.push('/report')">
        <span class="tab-icon">📝</span><span class="tab-text">周报</span>
      </div>
      <div class="tab-item" :class="{ active: $route.path === '/settings' }" @click="$router.push('/settings')">
        <span class="tab-icon">⚙️</span><span class="tab-text">设置</span>
      </div>
    </div>
  </div>
</template>

<script setup>
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { height: 100%; overflow: hidden; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; color: #333; }

/* 手机屏幕适配: 页面内容居中, 最大宽度 480px */
#app-root { max-width: 480px; margin: 0 auto; height: 100vh; overflow: hidden; position: relative; }

/* 所有按钮: 手型光标 */
button { cursor: pointer; }
button:disabled { cursor: not-allowed; }

/* 可点击元素: 手型 */
[class*="btn"], .tab-item, .session-item, .header-btn { cursor: pointer; }

.tab-bar { position: fixed; bottom: 0; left: 0; right: 0; height: 56px; background: #fff; border-top: 1px solid #e8e8e8; display: flex; z-index: 50; padding-bottom: env(safe-area-inset-bottom); }
.tab-item { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; font-size: 11px; color: #999; }
.tab-item.active { color: #4A90D9; }
.tab-icon { font-size: 22px; line-height: 1; }
.tab-text { font-size: 10px; margin-top: 2px; }

.global-toast { position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%); background: rgba(0,0,0,0.8); color: #fff; padding: 10px 24px; border-radius: 20px; font-size: 14px; z-index: 999; transition: opacity 0.3s; }
.global-toast.fade { opacity: 0; }
</style>
