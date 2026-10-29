<script setup>
import { RouterLink, useRoute } from 'vue-router'
import TextAiSettings from '../../components/teacher/TextAiSettings.vue'
import TeacherAiSettingsView from './TeacherAiSettingsView.vue'
const route = useRoute()
</script>
<template>
  <div class="view-stack"><header class="page-heading"><div><p class="eyebrow">COURSE ASSISTANTS</p><h1>AI 辅助</h1><p class="muted">连接老师自己的模型服务，为学习、编程与评阅提供辅助。</p></div></header>
    <nav class="ai-tabs" aria-label="AI 配置类型"><RouterLink to="/teacher/ai" :class="{ selected: route.query.tab !== 'video' }" :aria-current="route.query.tab !== 'video' ? 'page' : undefined">文字助教</RouterLink><RouterLink to="/teacher/ai?tab=video" :class="{ selected: route.query.tab === 'video' }" :aria-current="route.query.tab === 'video' ? 'page' : undefined">视频辅助评阅</RouterLink></nav>
    <TeacherAiSettingsView v-if="route.query.tab === 'video'" embedded /><TextAiSettings v-else />
  </div>
</template>
<style scoped>
.ai-tabs { display: flex; gap: 8px; border-bottom: 1px solid var(--border); padding-bottom: 12px; } .ai-tabs a { padding: 12px 22px; border-radius: 24px; color: var(--muted); text-decoration: none; } .ai-tabs a.selected { color: var(--primary-hover); background: var(--primary-soft); font-weight: 600; }
</style>
