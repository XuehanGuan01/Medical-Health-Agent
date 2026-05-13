<template>
  <div class="settings-page">
    <!-- 数据同步 -->
    <div class="card" v-if="healthStore.syncInfo">
      <span class="card-title">Sync Status</span>
      <div class="sync-row">
        <span class="sync-label">Last Sync</span>
        <span class="sync-val">{{ healthStore.syncInfo.last_sync?.time?.slice(0, 19) || 'N/A' }}</span>
      </div>
      <div class="sync-row">
        <span class="sync-label">Total Records</span>
        <span class="sync-val">{{ (healthStore.syncInfo.database?.total_raw_samples || 0).toLocaleString() }}</span>
      </div>
      <div class="sync-row">
        <span class="sync-label">Aggregated Days</span>
        <span class="sync-val">{{ healthStore.syncInfo.database?.total_daily_metrics || 0 }}</span>
      </div>
      <div class="sync-row">
        <span class="sync-label">Sync App</span>
        <span class="sync-val">Health Auto Export (Lybron Sobers)</span>
      </div>
      <div class="sync-row">
        <span class="sync-label">Data Source</span>
        <span class="sync-val">Apple Health + Apple Watch</span>
      </div>
    </div>

    <!-- 关于 -->
    <div class="card">
      <span class="card-title">About</span>
      <div class="about-row">
        <span class="about-label">Version</span>
        <span class="about-val">v3.0 (Phase 5)</span>
      </div>
      <div class="about-row">
        <span class="about-label">LLM Engine</span>
        <span class="about-val">Qwen3-Max / DeepSeek V4</span>
      </div>
      <div class="about-row">
        <span class="about-label">Embedding</span>
        <span class="about-val">DashScope text-embedding-v4</span>
      </div>
      <div class="about-row">
        <span class="about-label">RAG Knowledge</span>
        <span class="about-val">HuatuoGPT 276K QA pairs</span>
      </div>
      <div class="about-row">
        <span class="about-label">Data Pipeline</span>
        <span class="about-val">FastAPI + SQLite + ChromaDB</span>
      </div>
      <div class="about-row">
        <span class="about-label">Agent Graph</span>
        <span class="about-val">LangGraph StateGraph (Self-RAG)</span>
      </div>
      <div class="about-row">
        <span class="about-label">Frontend</span>
        <span class="about-val">Vue 3 + Vite + Pinia</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useHealthStore } from '@/stores/health'

const healthStore = useHealthStore()

onMounted(async () => {
  await healthStore.loadAll()
})
</script>

<style scoped>
.settings-page { padding: 16px; min-height: calc(100vh - 56px); background: #f0f2f5; padding-bottom: 20px; }

.card { background: #fff; border-radius: 12px; padding: 16px; margin-bottom: 14px; }
.card-title { font-size: 16px; font-weight: 600; color: #333; margin-bottom: 10px; display: block; }

.sync-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f5f5f5; }
.sync-label { font-size: 13px; color: #888; min-width: 100px; }
.sync-val { font-size: 13px; color: #333; text-align: right; }

.about-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f5f5f5; }
.about-label { font-size: 13px; color: #888; min-width: 100px; }
.about-val { font-size: 13px; color: #333; text-align: right; }
</style>
