import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import Chat from './pages/chat/index.vue'
import Dashboard from './pages/dashboard/index.vue'
import Report from './pages/report/index.vue'
import Aggregation from './pages/aggregation/index.vue'
import DataCalendar from './pages/data-calendar/index.vue'
import Settings from './pages/settings/index.vue'

const routes = [
  { path: '/', redirect: '/chat' },
  { path: '/chat', component: Chat },
  { path: '/dashboard', component: Dashboard },
  { path: '/report', component: Report },
  { path: '/aggregation', component: Aggregation },  // 从设置页跳入
  { path: '/data-calendar', component: DataCalendar },  // 日历看板
  { path: '/settings', component: Settings },
]

const router = createRouter({ history: createWebHashHistory(), routes })
const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
