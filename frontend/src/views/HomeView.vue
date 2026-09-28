<script setup>
import { onMounted, ref } from 'vue'

import DevTokenPanel from '../components/development/DevTokenPanel.vue'
import ServiceHealthCard from '../components/development/ServiceHealthCard.vue'
import { getBackendHealth } from '../api/system/health'

const isDevelopment = import.meta.env.DEV
const health = ref(null)
const healthError = ref('')
const isHealthLoading = ref(false)

async function checkHealth() {
  isHealthLoading.value = true
  healthError.value = ''
  try {
    health.value = await getBackendHealth()
  } catch (err) {
    health.value = null
    healthError.value = err.message
  } finally {
    isHealthLoading.value = false
  }
}

onMounted(checkHealth)
</script>

<template>
  <section class="console-header">
    <p class="console-header__kicker">AlgoPeer</p>
    <h1>开发测试台</h1>
    <p>确认后端连接，再使用测试身份进入学生工作台验证当前功能。</p>
  </section>

  <div class="console-grid">
    <ServiceHealthCard
      :health="health"
      :error="healthError"
      :is-loading="isHealthLoading"
      @refresh="checkHealth"
    />
    <DevTokenPanel v-if="isDevelopment" @updated="checkHealth" />
  </div>

  <section class="guide-card" aria-labelledby="guide-title">
    <h2 id="guide-title">当前可验证功能</h2>
    <ol>
      <li>检查后端服务状态。</li>
      <li>保存有效学生 JWT。</li>
      <li>进入“我的作业”查看真实作业与提交摘要。</li>
    </ol>
  </section>
</template>

<style scoped>
.console-header { max-width: 680px; margin-bottom: 24px; }
.console-header__kicker { margin: 0; color: #b8e0ca; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
h1 { margin: 8px 0; color: white; font-size: clamp(30px, 5vw, 42px); }
.console-header > p:last-child { margin: 0; color: #d7e5dc; }
.console-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.guide-card { margin-top: 16px; padding: 20px; border-radius: 10px; color: #eaf6ee; background: #0d4d3a; }
.guide-card h2 { margin: 0 0 10px; font-size: 18px; }
ol { margin: 0; padding-left: 20px; }
li + li { margin-top: 6px; }
@media (max-width: 760px) { .console-grid { grid-template-columns: 1fr; } }
</style>
